"""Home Assistant integration setup for ABB / Busch-Jaeger free@home NG."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import event as ha_event
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    FreeAtHomeApiError,
    FreeAtHomeAuthError,
    FreeAtHomeConnectionError,
    FreeAtHomeController,
    FreeAtHomeLocalApiClient,
)
from .api.devices.base import FahBaseDevice
from .const import (
    CONF_INCLUDE_ORPHAN_CHANNELS,
    CONF_NAME_PREFIX,
    CONF_SWITCH_AS_X,
    CONF_USE_HTTPS,
    CONF_USE_ROOM_NAMES,
    CONF_VERIFY_SSL,
    CONF_VIRTUAL_DEVICES,
    DEFAULT_INCLUDE_ORPHAN_CHANNELS,
    DEFAULT_NAME_PREFIX,
    DEFAULT_SWITCH_AS_X,
    DEFAULT_USE_HTTPS,
    DEFAULT_USE_ROOM_NAMES,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    EVENT_SCENE_TRIGGERED,
    EVENT_VIRTUAL_DEVICE_COMMAND,
    SERVICE_DUMP_CONFIG,
    SERVICE_MIGRATE_FROM_LEGACY,
    SERVICE_MONITOR,
    SERVICE_REGISTER_VIRTUAL_DEVICE,
    SERVICE_SEND_NOTIFICATION,
    SERVICE_SET_DATAPOINT,
    SERVICE_TRIGGER_PROXY_DEVICE,
    SERVICE_UNREGISTER_VIRTUAL_DEVICE,
    VIRTUAL_DEVICE_TYPES,
)
from .migration import async_migrate_from_legacy, parse_serialnumbers_text

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.FAN,
    Platform.LIGHT,
    Platform.LOCK,
    Platform.SCENE,
    Platform.SENSOR,
    Platform.SWITCH,
]


@dataclass
class FreeAtHomeNgRuntime:
    """Runtime container stored on `entry.runtime_data`."""

    controller: FreeAtHomeController
    entry: ConfigEntry[Any]
    config_snapshot: dict[str, Any] = field(default_factory=dict)
    platform_adders: dict[str, Callable[[list[FahBaseDevice]], None]] = field(default_factory=dict)
    hub_device_id: str | None = None
    suppress_reload: bool = False


type FreeAtHomeNgConfigEntry = ConfigEntry[FreeAtHomeNgRuntime]


def _connection_snapshot(entry: ConfigEntry[Any]) -> dict[str, Any]:
    """Return connection and option fields whose change warrants an entry reload."""
    merged = {**entry.data, **entry.options}
    merged.pop(CONF_VIRTUAL_DEVICES, None)
    return merged


def register_platform_adder(
    hass: HomeAssistant,
    entry_id: str,
    platform: str,
    adder: Callable[[list[FahBaseDevice]], None],
) -> None:
    """Allow a platform to receive dynamically added devices at runtime."""
    domain_data = hass.data.get(DOMAIN, {})
    cfg_entry = domain_data.get("loaded_entries", {}).get(entry_id)
    runtime: FreeAtHomeNgRuntime | None = getattr(cfg_entry, "runtime_data", None)
    if runtime is None:
        legacy_rt = domain_data.get(entry_id)
        if isinstance(legacy_rt, FreeAtHomeNgRuntime):
            runtime = legacy_rt
    if runtime is not None:
        runtime.platform_adders[platform] = adder


def _resolve_target_runtimes(
    hass: HomeAssistant,
    host: str | None = None,
) -> list[FreeAtHomeNgRuntime]:
    """Return matching `FreeAtHomeNgRuntime` instances or raise ServiceValidationError."""
    loaded_entries: dict[str, FreeAtHomeNgConfigEntry] = hass.data.get(DOMAIN, {}).get(
        "loaded_entries", {}
    )
    runtimes: list[FreeAtHomeNgRuntime] = [
        rt
        for cfg_entry in loaded_entries.values()
        if (rt := getattr(cfg_entry, "runtime_data", None)) is not None
    ]
    if not runtimes:
        raise ServiceValidationError("No free@home NG entries are currently loaded")
    if host:
        filtered = [rt for rt in runtimes if rt.controller.client.host == host]
        if not filtered:
            raise ServiceValidationError(f"No loaded free@home NG entry matches host '{host}'")
        return filtered
    return runtimes


def _resolve_target_controllers(
    hass: HomeAssistant,
    host: str | None = None,
) -> list[FreeAtHomeController]:
    """Return matching `FreeAtHomeController` instances for service calls."""
    return [rt.controller for rt in _resolve_target_runtimes(hass, host)]


def _resolve_single_target_entry(
    hass: HomeAssistant,
    *,
    entry_id: str | None = None,
    host: str | None = None,
) -> FreeAtHomeNgConfigEntry:
    """Resolve exactly one loaded config entry by entry_id or host."""
    loaded_entries: dict[str, FreeAtHomeNgConfigEntry] = hass.data.get(DOMAIN, {}).get(
        "loaded_entries", {}
    )
    candidates = [
        cfg_entry
        for cfg_entry in loaded_entries.values()
        if getattr(cfg_entry, "runtime_data", None) is not None
    ]
    if not candidates:
        raise ServiceValidationError("No free@home NG entries are currently loaded")

    if entry_id:
        match = loaded_entries.get(entry_id)
        if match is None or getattr(match, "runtime_data", None) is None:
            raise ServiceValidationError(f"free@home NG hub entry '{entry_id}' is not loaded")
        if host and match.runtime_data.controller.client.host != host:
            raise ServiceValidationError(
                f"free@home NG hub entry '{entry_id}' does not match host '{host}'"
            )
        return match

    if host:
        matching = [
            cfg_entry
            for cfg_entry in candidates
            if cfg_entry.runtime_data.controller.client.host == host
        ]
        if not matching:
            raise ServiceValidationError(f"No loaded free@home NG entry matches host '{host}'")
        if len(matching) > 1:
            raise ServiceValidationError(
                f"Multiple free@home NG entries match host '{host}'; specify entry_id."
            )
        return matching[0]

    if len(candidates) > 1:
        raise ServiceValidationError(
            "Multiple free@home NG hubs are loaded; specify entry_id or host."
        )
    return candidates[0]


async def _async_reload_entry(hass: HomeAssistant, entry: FreeAtHomeNgConfigEntry) -> None:
    """Schedule a config entry reload when options or connection data change."""
    runtime = getattr(entry, "runtime_data", None)
    if runtime is not None and (
        runtime.suppress_reload or _connection_snapshot(entry) == runtime.config_snapshot
    ):
        return
    if hasattr(hass.config_entries, "async_schedule_reload"):
        hass.config_entries.async_schedule_reload(entry.entry_id)
    else:
        await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: FreeAtHomeNgConfigEntry) -> bool:
    """Set up free@home NG from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    loaded_entries: dict[str, FreeAtHomeNgConfigEntry] = domain_data.setdefault(
        "loaded_entries", {}
    )

    config = {**entry.data, **entry.options}
    use_https = bool(config.get(CONF_USE_HTTPS, DEFAULT_USE_HTTPS))
    verify_ssl = bool(config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL))
    session = async_get_clientsession(hass, verify_ssl=verify_ssl)

    client = FreeAtHomeLocalApiClient(
        host=config[CONF_HOST],
        username=config[CONF_USERNAME],
        password=config[CONF_PASSWORD],
        session=session,
        use_https=use_https,
        verify_ssl=verify_ssl,
    )
    controller = FreeAtHomeController(
        client,
        use_room_names=bool(config.get(CONF_USE_ROOM_NAMES, DEFAULT_USE_ROOM_NAMES)),
        switch_as_x=bool(config.get(CONF_SWITCH_AS_X, DEFAULT_SWITCH_AS_X)),
        name_prefix=str(config.get(CONF_NAME_PREFIX, DEFAULT_NAME_PREFIX)),
        include_orphan_channels=bool(
            config.get(CONF_INCLUDE_ORPHAN_CHANNELS, DEFAULT_INCLUDE_ORPHAN_CHANNELS)
        ),
    )

    try:
        await controller.initialize()
    except FreeAtHomeAuthError as err:
        await controller.close()
        raise ConfigEntryAuthFailed(
            f"Authentication rejected by free@home SysAP at {config[CONF_HOST]}"
        ) from err
    except (FreeAtHomeConnectionError, FreeAtHomeApiError) as err:
        await controller.close()
        raise ConfigEntryNotReady(
            f"Cannot connect to free@home SysAP at {config[CONF_HOST]}: {err}"
        ) from err

    device_registry = dr.async_get(hass)
    hub_name = (
        entry.title
        or controller.sysap_names.get(controller.primary_sysap_uuid)
        or f"free@home SysAP ({config[CONF_HOST]})"
    )
    hub_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"hub_{entry.entry_id}")},
        name=hub_name,
        manufacturer="ABB / Busch-Jaeger",
        model="free@home System Access Point",
        sw_version=controller.sysap_version,
        serial_number=controller.sysap_serial,
        configuration_url=client.base_http_url,
        entry_type=dr.DeviceEntryType.SERVICE,
    )
    raw_hub_device_id = getattr(hub_device, "id", None)
    hub_device_id = raw_hub_device_id if isinstance(raw_hub_device_id, str) else None

    runtime = FreeAtHomeNgRuntime(
        controller=controller,
        entry=entry,
        config_snapshot=_connection_snapshot(entry),
        hub_device_id=hub_device_id,
    )
    entry.runtime_data = runtime
    loaded_entries[entry.entry_id] = entry

    # Restore persisted virtual devices so TTL heartbeats resume after HA restarts.
    for native_id, vdev_cfg in (entry.data.get(CONF_VIRTUAL_DEVICES) or {}).items():
        if not isinstance(vdev_cfg, dict):
            continue
        try:
            await controller.client.register_virtual_device(
                sysap_uuid=str(vdev_cfg.get("sysap_uuid") or controller.primary_sysap_uuid),
                native_id=native_id,
                device_type=str(vdev_cfg["device_type"]),
                display_name=vdev_cfg.get("display_name"),
                ttl=int(vdev_cfg.get("ttl", 180)),
                flavor=vdev_cfg.get("flavor"),
                capabilities=vdev_cfg.get("capabilities"),
            )
        except Exception as err:
            _LOGGER.warning("Failed restoring virtual device %s on startup: %s", native_id, err)

    reauth_started = False

    def _handle_rejected_login() -> None:
        nonlocal reauth_started
        if reauth_started:
            return
        reauth_started = True
        entry.async_start_reauth(hass)
        if hasattr(hass.config_entries, "async_schedule_reload"):
            hass.config_entries.async_schedule_reload(entry.entry_id)
        else:
            hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))

    controller.set_auth_failed_callback(_handle_rejected_login)

    async def _on_scene_triggered(sysap_uuid: str, scenes_triggered: dict[str, Any]) -> None:
        hass.bus.async_fire(
            EVENT_SCENE_TRIGGERED,
            {
                "entry_id": entry.entry_id,
                "sysap_uuid": sysap_uuid,
                "scenes": scenes_triggered,
            },
        )

    async def _on_virtual_command(
        sysap_uuid: str,
        serialnumber: str,
        channel_id: str,
        datapoint_id: str,
        value: str,
    ) -> None:
        hass.bus.async_fire(
            EVENT_VIRTUAL_DEVICE_COMMAND,
            {
                "entry_id": entry.entry_id,
                "sysap_uuid": sysap_uuid,
                "serialnumber": serialnumber,
                "channel_id": channel_id,
                "datapoint_id": datapoint_id,
                "value": value,
            },
        )

    async def _on_devices_added(new_devices: list[FahBaseDevice]) -> None:
        new_set = set(new_devices)
        for platform, adder in list(runtime.platform_adders.items()):
            if platform == "sensor":
                candidates = (
                    controller.get_devices("sensor")
                    + controller.get_devices("thermostat")
                    + controller.get_devices("binary_sensor")
                )
            else:
                candidates = controller.get_devices(platform)
            matching = [dev for dev in candidates if dev in new_set]
            if matching:
                adder(matching)

    controller.register_scene_triggered_cb(_on_scene_triggered)
    controller.register_virtual_device_command_cb(_on_virtual_command)
    controller.register_devices_added_cb(_on_devices_added)

    controller.start_listening()

    async def _shutdown(_event: Any) -> None:
        await controller.close()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _shutdown))
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_services(hass)

    return True


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: FreeAtHomeNgConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """Allow deleting a device from HA only if it is no longer on this SysAP."""
    active_identifiers: set[tuple[str, str]] = {(DOMAIN, f"hub_{config_entry.entry_id}")}
    runtime = getattr(config_entry, "runtime_data", None)
    if runtime is not None:
        for dev in runtime.controller.devices:
            active_identifiers.add((DOMAIN, f"{dev.sysap_uuid}_{dev.serialnumber}"))
    return not any(ident in active_identifiers for ident in device_entry.identifiers)


def _async_register_services(hass: HomeAssistant) -> None:
    """Register `freeathome_ng.*` services once."""
    if hass.services.has_service(DOMAIN, SERVICE_DUMP_CONFIG):
        return

    async def _handle_dump_config(call: ServiceCall) -> None:
        host = call.data.get("host")
        for ctrl in _resolve_target_controllers(hass, host):
            config_data = await ctrl.client.get_configuration()
            timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
            safe_host = ctrl.client.host.replace(":", "_")
            filename = f"freeathome_ng_dump_{safe_host}_{timestamp}.json"
            path = hass.config.path(filename)
            await hass.async_add_executor_job(_write_json_file, path, config_data)
            _LOGGER.info("Dumped free@home NG config for %s to %s", ctrl.client.host, path)

    async def _handle_monitor(call: ServiceCall) -> None:
        duration = int(call.data.get("duration", 10))
        host = call.data.get("host")
        for ctrl in _resolve_target_controllers(hass, host):
            timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
            safe_host = ctrl.client.host.replace(":", "_")
            filename = f"freeathome_ng_monitor_{safe_host}_{timestamp}.jsonl"
            path = hass.config.path(filename)
            frames: list[dict[str, Any]] = []

            def _capture(frame: dict[str, Any], target: list[dict[str, Any]] = frames) -> None:
                target.append(frame)

            ctrl.add_ws_frame_listener(_capture)

            async def _finish(
                _now: Any,
                c: FreeAtHomeController = ctrl,
                listener: Callable[[dict[str, Any]], None] = _capture,
                captured: list[dict[str, Any]] = frames,
                out_path: str = path,
            ) -> None:
                c.remove_ws_frame_listener(listener)
                await hass.async_add_executor_job(_write_jsonl_file, out_path, captured)
                _LOGGER.info(
                    "Recorded %d WebSocket frames for %s to %s",
                    len(captured),
                    c.client.host,
                    out_path,
                )

            ha_event.async_call_later(hass, duration, _finish)

    async def _handle_set_datapoint(call: ServiceCall) -> None:
        host = call.data.get("host")
        serial = call.data["serialnumber"]
        channel = call.data["channel_id"]
        datapoint = call.data["datapoint_id"]
        value = str(call.data["value"])
        for ctrl in _resolve_target_controllers(hass, host):
            sysap_uuid = call.data.get("sysap_uuid") or ctrl.primary_sysap_uuid
            await ctrl.client.set_datapoint(sysap_uuid, serial, channel, datapoint, value)

    async def _handle_register_virtual_device(call: ServiceCall) -> None:
        host = call.data.get("host")
        native_id = call.data["native_id"]
        device_type = call.data["device_type"]
        display_name = call.data.get("display_name")
        ttl = int(call.data.get("ttl", 180))
        flavor = call.data.get("flavor")
        capabilities = call.data.get("capabilities")
        for rt in _resolve_target_runtimes(hass, host):
            ctrl = rt.controller
            sysap_uuid = call.data.get("sysap_uuid") or ctrl.primary_sysap_uuid
            await ctrl.client.register_virtual_device(
                sysap_uuid=sysap_uuid,
                native_id=native_id,
                device_type=device_type,
                display_name=display_name,
                ttl=ttl,
                flavor=flavor,
                capabilities=capabilities,
            )
            saved = dict(rt.entry.data.get(CONF_VIRTUAL_DEVICES) or {})
            saved[native_id] = {
                "sysap_uuid": sysap_uuid,
                "device_type": device_type,
                "display_name": display_name,
                "ttl": ttl,
                "flavor": flavor,
                "capabilities": capabilities,
            }
            hass.config_entries.async_update_entry(
                rt.entry, data={**rt.entry.data, CONF_VIRTUAL_DEVICES: saved}
            )

    async def _handle_unregister_virtual_device(call: ServiceCall) -> None:
        host = call.data.get("host")
        native_id = call.data["native_id"]
        for rt in _resolve_target_runtimes(hass, host):
            ctrl = rt.controller
            sysap_uuid = call.data.get("sysap_uuid") or ctrl.primary_sysap_uuid
            await ctrl.client.unregister_virtual_device(sysap_uuid, native_id)
            saved = dict(rt.entry.data.get(CONF_VIRTUAL_DEVICES) or {})
            if native_id in saved:
                saved.pop(native_id)
                hass.config_entries.async_update_entry(
                    rt.entry, data={**rt.entry.data, CONF_VIRTUAL_DEVICES: saved}
                )

    async def _handle_trigger_proxy_device(call: ServiceCall) -> None:
        host = call.data.get("host")
        device_class = call.data["device_class"]
        device_id = call.data["device_id"]
        action = call.data["action"]
        for ctrl in _resolve_target_controllers(hass, host):
            sysap_uuid = call.data.get("sysap_uuid") or ctrl.primary_sysap_uuid
            await ctrl.client.trigger_proxy_device(
                sysap_uuid=sysap_uuid,
                device_class=device_class,
                device_id=device_id,
                action=action,
            )

    async def _handle_send_notification(call: ServiceCall) -> None:
        host = call.data.get("host")
        payload: dict[str, Any] = {
            "subject": call.data["subject"],
            "body": call.data["body"],
        }
        if "timeout_minutes" in call.data:
            payload["timeoutMinutes"] = int(call.data["timeout_minutes"])
        for ctrl in _resolve_target_controllers(hass, host):
            await ctrl.client.send_notification(payload)

    async def _handle_migrate_from_legacy(call: ServiceCall) -> dict[str, Any]:
        """Preview or execute migration from legacy `freeathome` to `freeathome_ng`."""
        entry_id = call.data.get("entry_id")
        host = call.data.get("host")
        target_entry = _resolve_single_target_entry(
            hass,
            entry_id=str(entry_id).strip() if entry_id else None,
            host=str(host).strip() if host else None,
        )
        dry_run = bool(call.data.get("dry_run", True))
        cutover = bool(call.data.get("cutover", False))
        raw_serials = str(call.data.get("serialnumbers") or "").strip()
        filter_serials = set(parse_serialnumbers_text(raw_serials)) if raw_serials else None
        return await async_migrate_from_legacy(
            hass,
            target_entry,
            dry_run=dry_run,
            cutover=cutover,
            serialnumbers_filter=filter_serials,
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_DUMP_CONFIG,
        _handle_dump_config,
        schema=vol.Schema({vol.Optional("host"): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_MONITOR,
        _handle_monitor,
        schema=vol.Schema(
            {
                vol.Optional("duration", default=10): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=300)
                ),
                vol.Optional("host"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_DATAPOINT,
        _handle_set_datapoint,
        schema=vol.Schema(
            {
                vol.Required("serialnumber"): cv.string,
                vol.Required("channel_id"): cv.string,
                vol.Required("datapoint_id"): cv.string,
                vol.Required("value"): cv.string,
                vol.Optional("sysap_uuid"): cv.string,
                vol.Optional("host"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REGISTER_VIRTUAL_DEVICE,
        _handle_register_virtual_device,
        schema=vol.Schema(
            {
                vol.Required("native_id"): cv.string,
                vol.Required("device_type"): vol.In(VIRTUAL_DEVICE_TYPES),
                vol.Optional("display_name"): cv.string,
                vol.Optional("ttl", default=180): vol.Coerce(int),
                vol.Optional("flavor"): cv.string,
                vol.Optional("capabilities"): list,
                vol.Optional("sysap_uuid"): cv.string,
                vol.Optional("host"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UNREGISTER_VIRTUAL_DEVICE,
        _handle_unregister_virtual_device,
        schema=vol.Schema(
            {
                vol.Required("native_id"): cv.string,
                vol.Optional("sysap_uuid"): cv.string,
                vol.Optional("host"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TRIGGER_PROXY_DEVICE,
        _handle_trigger_proxy_device,
        schema=vol.Schema(
            {
                vol.Required("device_class"): cv.string,
                vol.Required("device_id"): cv.string,
                vol.Required("action"): cv.string,
                vol.Optional("sysap_uuid"): cv.string,
                vol.Optional("host"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_NOTIFICATION,
        _handle_send_notification,
        schema=vol.Schema(
            {
                vol.Required("subject"): cv.string,
                vol.Required("body"): cv.string,
                vol.Optional("timeout_minutes"): vol.Coerce(int),
                vol.Optional("host"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_MIGRATE_FROM_LEGACY,
        _handle_migrate_from_legacy,
        schema=vol.Schema(
            {
                vol.Optional("entry_id"): cv.string,
                vol.Optional("host"): cv.string,
                vol.Optional("dry_run", default=True): cv.boolean,
                vol.Optional("cutover", default=False): cv.boolean,
                vol.Optional("serialnumbers"): cv.string,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )


def _write_json_file(path: str, data: Any) -> None:
    """Write formatted JSON to disk."""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def _write_jsonl_file(path: str, frames: list[dict[str, Any]]) -> None:
    """Write captured WebSocket JSON frames as newline-delimited JSON."""
    with open(path, "w", encoding="utf-8") as handle:
        for frame in frames:
            handle.write(json.dumps(frame, ensure_ascii=False) + "\n")


async def async_unload_entry(hass: HomeAssistant, entry: FreeAtHomeNgConfigEntry) -> bool:
    """Unload free@home NG config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unload_ok:
        return False

    domain_data = hass.data.get(DOMAIN, {})
    loaded_entries: dict[str, Any] = domain_data.get("loaded_entries", {})
    loaded_entries.pop(entry.entry_id, None)

    runtime = getattr(entry, "runtime_data", None)
    if runtime is not None:
        runtime.controller.set_auth_failed_callback(None)
        await runtime.controller.close()

    if not loaded_entries:
        for service_name in (
            SERVICE_DUMP_CONFIG,
            SERVICE_MIGRATE_FROM_LEGACY,
            SERVICE_MONITOR,
            SERVICE_SET_DATAPOINT,
            SERVICE_REGISTER_VIRTUAL_DEVICE,
            SERVICE_UNREGISTER_VIRTUAL_DEVICE,
            SERVICE_TRIGGER_PROXY_DEVICE,
            SERVICE_SEND_NOTIFICATION,
        ):
            if hass.services.has_service(DOMAIN, service_name):
                hass.services.async_remove(DOMAIN, service_name)

    return True
