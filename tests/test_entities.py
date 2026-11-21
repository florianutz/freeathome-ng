"""Tests for integration setup/unload, runtime_data, Hub device hierarchy, platforms, and mock server."""

from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import freeathome_ng
import pytest
from freeathome_ng import (
    FreeAtHomeNgRuntime,
    _async_reload_entry,
    async_remove_config_entry_device,
    async_setup_entry,
    async_unload_entry,
)
from freeathome_ng.api.client import FreeAtHomeLocalApiClient
from freeathome_ng.api.controller import FreeAtHomeController
from freeathome_ng.const import (
    CONF_VIRTUAL_DEVICES,
    DOMAIN,
    SERVICE_DUMP_CONFIG,
    SERVICE_MIGRATE_FROM_LEGACY,
    SERVICE_MONITOR,
    SERVICE_REGISTER_VIRTUAL_DEVICE,
    SERVICE_SEND_NOTIFICATION,
    SERVICE_SET_DATAPOINT,
    SERVICE_TRIGGER_PROXY_DEVICE,
    SERVICE_UNREGISTER_VIRTUAL_DEVICE,
)
from freeathome_ng.entity import FreeAtHomeNgEntity
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    ServiceValidationError,
)
from mock_sysap_server import MockSysApServer


def _make_hass() -> tuple[SimpleNamespace, dict[str, list], dict[str, dict]]:
    forwarded: list[tuple[str, list[Platform]]] = []
    registered_services: dict[str, dict] = {}
    scheduled_reloads: list[str] = []
    created_hub_devices: dict[str, SimpleNamespace] = {}

    def _get_or_create_device(**kwargs):
        dev = SimpleNamespace(id="hub_dev_001", **kwargs)
        created_hub_devices[dev.id] = dev
        return dev

    async def _forward_setups(entry, platforms):
        forwarded.append((entry.entry_id, list(platforms)))

    async def _unload_platforms(_entry, _platforms):
        return True

    def _schedule_reload(entry_id: str) -> None:
        scheduled_reloads.append(entry_id)

    def _update_entry(entry, *, data=None, options=None) -> None:
        if data is not None:
            entry.data = dict(data)
        if options is not None:
            entry.options = dict(options)

    def _register_service(domain, name, handler, schema=None, **_kw):
        registered_services[f"{domain}.{name}"] = {
            "handler": handler,
            "schema": schema,
        }

    def _has_service(domain, name) -> bool:
        return f"{domain}.{name}" in registered_services

    def _remove_service(domain, name) -> None:
        registered_services.pop(f"{domain}.{name}", None)

    hass = SimpleNamespace(
        data={},
        device_registry=SimpleNamespace(async_get_or_create=_get_or_create_device),
        config_entries=SimpleNamespace(
            async_forward_entry_setups=_forward_setups,
            async_unload_platforms=_unload_platforms,
            async_schedule_reload=_schedule_reload,
            async_update_entry=_update_entry,
        ),
        services=SimpleNamespace(
            async_register=_register_service,
            has_service=_has_service,
            async_remove=_remove_service,
        ),
        bus=SimpleNamespace(
            async_listen_once=lambda *_a, **_kw: lambda: None,
            async_fire=lambda *_a, **_kw: None,
        ),
        config=SimpleNamespace(path=lambda filename: filename),
        async_create_task=lambda coro: asyncio.create_task(coro),
    )
    return (
        hass,
        {
            "forwarded": forwarded,
            "scheduled_reloads": scheduled_reloads,
        },
        {
            "services": registered_services,
            "devices": created_hub_devices,
        },
    )


def _make_entry(
    host: str,
    *,
    username: str = "apiuser",
    password: str = "secret",
    entry_id: str = "entry_1",
    reauth_log: list[str] | None = None,
) -> SimpleNamespace:
    unload_cbs: list = []
    return SimpleNamespace(
        entry_id=entry_id,
        title="Test SysAP",
        data={
            CONF_HOST: host,
            CONF_USERNAME: username,
            CONF_PASSWORD: password,
        },
        options={},
        runtime_data=None,
        unload_cbs=unload_cbs,
        async_on_unload=lambda cb: unload_cbs.append(cb),
        add_update_listener=lambda _cb: lambda: None,
        async_start_reauth=lambda _hass: (
            reauth_log.append(entry_id) if reauth_log is not None else None
        ),
    )


async def test_setup_unload_hub_device_and_runtime_data() -> None:
    """Verify setup stores entry.runtime_data, creates Hub device, and unloads cleanly."""
    server = MockSysApServer(port=0)
    await server.start()
    try:
        hass, logs, registries = _make_hass()
        entry = _make_entry(server.host_port)

        assert await async_setup_entry(hass, entry) is True  # type: ignore[arg-type]
        assert isinstance(entry.runtime_data, FreeAtHomeNgRuntime)
        assert entry.runtime_data.hub_device_id == "hub_dev_001"
        assert hass.data[DOMAIN]["loaded_entries"] == {"entry_1": entry}

        hub_dev = registries["devices"]["hub_dev_001"]
        assert hub_dev.entry_type == "service"
        assert hub_dev.identifiers == {(DOMAIN, "hub_entry_1")}
        assert hub_dev.serial_number == "ABB700999999"
        assert hub_dev.sw_version == "3.2.1"

        assert logs["forwarded"][0][1] == list(freeathome_ng.PLATFORMS)
        for svc in (
            SERVICE_DUMP_CONFIG,
            SERVICE_MIGRATE_FROM_LEGACY,
            SERVICE_MONITOR,
            SERVICE_SET_DATAPOINT,
            SERVICE_REGISTER_VIRTUAL_DEVICE,
            SERVICE_UNREGISTER_VIRTUAL_DEVICE,
            SERVICE_TRIGGER_PROXY_DEVICE,
            SERVICE_SEND_NOTIFICATION,
        ):
            assert f"{DOMAIN}.{svc}" in registries["services"]

        assert await async_unload_entry(hass, entry) is True  # type: ignore[arg-type]
        assert hass.data[DOMAIN]["loaded_entries"] == {}
        assert registries["services"] == {}
    finally:
        await server.stop()


async def test_setup_auth_and_connection_failures() -> None:
    """Verify ConfigEntryAuthFailed on 401 and ConfigEntryNotReady when unreachable."""
    server = MockSysApServer(port=0)
    await server.start()
    try:
        hass, _, _ = _make_hass()
        bad_auth_entry = _make_entry(server.host_port, password="wrong")
        with pytest.raises(ConfigEntryAuthFailed):
            await async_setup_entry(hass, bad_auth_entry)  # type: ignore[arg-type]

        unreachable_entry = _make_entry("127.0.0.1:1")
        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, unreachable_entry)  # type: ignore[arg-type]
    finally:
        await server.stop()


async def test_reload_listener_and_suppress_reload() -> None:
    """Verify _async_reload_entry uses async_schedule_reload and honors guards."""
    server = MockSysApServer(port=0)
    await server.start()
    try:
        hass, logs, _ = _make_hass()
        entry = _make_entry(server.host_port)
        await async_setup_entry(hass, entry)  # type: ignore[arg-type]

        # Virtual device persistence alone must NOT trigger a reload
        entry.data = {
            **entry.data,
            CONF_VIRTUAL_DEVICES: {"v1": {"device_type": "SwitchingActuator"}},
        }
        await _async_reload_entry(hass, entry)  # type: ignore[arg-type]
        assert logs["scheduled_reloads"] == []

        # Changing real option with suppress_reload=True must skip reload
        entry.options = {"name_prefix": "NG "}
        entry.runtime_data.suppress_reload = True
        await _async_reload_entry(hass, entry)  # type: ignore[arg-type]
        assert logs["scheduled_reloads"] == []

        # With suppress_reload=False, option change schedules reload
        entry.runtime_data.suppress_reload = False
        await _async_reload_entry(hass, entry)  # type: ignore[arg-type]
        assert logs["scheduled_reloads"] == ["entry_1"]

        await async_unload_entry(hass, entry)  # type: ignore[arg-type]
    finally:
        await server.stop()


async def test_entity_via_device_id_and_remove_device_guard() -> None:
    """Verify via_device_id vs fallback and async_remove_config_entry_device logic."""
    server = MockSysApServer(port=0)
    await server.start()
    try:
        hass, _, _ = _make_hass()
        entry = _make_entry(server.host_port)
        await async_setup_entry(hass, entry)  # type: ignore[arg-type]

        ctrl = entry.runtime_data.controller
        dev = ctrl.devices[0]

        entity_modern = FreeAtHomeNgEntity(dev, hub_device_id="hub_dev_001", entry_id="entry_1")
        assert entity_modern.device_info["via_device_id"] == "hub_dev_001"
        assert "via_device" not in entity_modern.device_info

        entity_fallback = FreeAtHomeNgEntity(dev, hub_device_id=None, entry_id="entry_1")
        assert entity_fallback.device_info["via_device"] == (DOMAIN, "hub_entry_1")

        # Hub device cannot be removed
        assert (
            await async_remove_config_entry_device(
                hass,  # type: ignore[arg-type]
                entry,  # type: ignore[arg-type]
                SimpleNamespace(identifiers={(DOMAIN, "hub_entry_1")}),  # type: ignore[arg-type]
            )
            is False
        )
        # Active device cannot be removed
        sysap_uuid = ctrl.primary_sysap_uuid
        assert (
            await async_remove_config_entry_device(
                hass,  # type: ignore[arg-type]
                entry,  # type: ignore[arg-type]
                SimpleNamespace(identifiers={(DOMAIN, f"{sysap_uuid}_ABB700D10001")}),  # type: ignore[arg-type]
            )
            is False
        )
        # Stale / removed device CAN be removed
        assert (
            await async_remove_config_entry_device(
                hass,  # type: ignore[arg-type]
                entry,  # type: ignore[arg-type]
                SimpleNamespace(identifiers={(DOMAIN, f"{sysap_uuid}_REMOVED99")}),  # type: ignore[arg-type]
            )
            is True
        )

        await async_unload_entry(hass, entry)  # type: ignore[arg-type]
    finally:
        await server.stop()


async def test_all_platforms_setup_runtime_data_and_dynamic_add() -> None:
    """Verify all 10 platforms define PARALLEL_UPDATES=0, use runtime_data, and handle runtime adds."""
    server = MockSysApServer(port=0)
    await server.start()
    try:
        hass, _, _ = _make_hass()
        entry = _make_entry(server.host_port)
        await async_setup_entry(hass, entry)  # type: ignore[arg-type]

        platform_names = (
            "binary_sensor",
            "button",
            "climate",
            "cover",
            "fan",
            "light",
            "lock",
            "scene",
            "sensor",
            "switch",
        )
        total_entities = 0
        for pname in platform_names:
            mod = importlib.import_module(f"freeathome_ng.{pname}")
            assert mod.PARALLEL_UPDATES == 0
            added: list = []
            await mod.async_setup_entry(hass, entry, lambda ents, _out=added: _out.extend(ents))
            assert added, f"Expected entities for platform {pname}"
            total_entities += len(added)
            for entity in added:
                assert entity.device_info["via_device_id"] == "hub_dev_001"
            assert pname in entry.runtime_data.platform_adders

        assert total_entities > 15

        # Trigger dynamic runtime addition of a switch device
        switch_added: list = []
        entry.runtime_data.platform_adders["switch"] = lambda ents: switch_added.extend(ents)
        await entry.runtime_data.controller.handle_ws_message(
            {
                entry.runtime_data.controller.primary_sysap_uuid: {
                    "devices": {
                        "ABB700NEW01": {
                            "displayName": "Runtime Switch",
                            "deviceId": "100C",
                            "floor": "01",
                            "room": "01",
                            "channels": {
                                "ch0000": {
                                    "displayName": "Dynamic Lamp",
                                    "functionID": "0007",
                                    "inputs": {"idp0000": {"pairingID": 1, "value": "0"}},
                                    "outputs": {"odp0000": {"pairingID": 256, "value": "0"}},
                                }
                            },
                        }
                    }
                }
            }
        )
        assert len(switch_added) == 1
        assert switch_added[0].unique_id.endswith("/ABB700NEW01/ch0000")

        await async_unload_entry(hass, entry)  # type: ignore[arg-type]
    finally:
        await server.stop()


async def test_service_validation_and_virtual_device_persistence() -> None:
    """Verify services raise ServiceValidationError on missing/bad host and persist vdevs cleanly."""
    server = MockSysApServer(port=0)
    await server.start()
    try:
        hass, logs, registries = _make_hass()
        entry = _make_entry(server.host_port)
        await async_setup_entry(hass, entry)  # type: ignore[arg-type]

        set_dp = registries["services"][f"{DOMAIN}.{SERVICE_SET_DATAPOINT}"]["handler"]
        with pytest.raises(ServiceValidationError):
            await set_dp(
                SimpleNamespace(
                    data={
                        "host": "10.99.99.99",
                        "serialnumber": "ABB700D10001",
                        "channel_id": "ch0003",
                        "datapoint_id": "idp0000",
                        "value": "1",
                    }
                )
            )

        reg_vdev = registries["services"][f"{DOMAIN}.{SERVICE_REGISTER_VIRTUAL_DEVICE}"]["handler"]
        unreg_vdev = registries["services"][f"{DOMAIN}.{SERVICE_UNREGISTER_VIRTUAL_DEVICE}"][
            "handler"
        ]

        await reg_vdev(
            SimpleNamespace(
                data={
                    "native_id": "ha_test_switch",
                    "device_type": "SwitchingActuator",
                    "display_name": "Test Switch",
                    "ttl": 180,
                }
            )
        )
        assert "ha_test_switch" in entry.data[CONF_VIRTUAL_DEVICES]
        await _async_reload_entry(hass, entry)  # type: ignore[arg-type]
        assert logs["scheduled_reloads"] == []

        await unreg_vdev(SimpleNamespace(data={"native_id": "ha_test_switch"}))
        assert "ha_test_switch" not in entry.data[CONF_VIRTUAL_DEVICES]

        await async_unload_entry(hass, entry)  # type: ignore[arg-type]
        with pytest.raises(ServiceValidationError):
            await set_dp(
                SimpleNamespace(
                    data={
                        "serialnumber": "ABB700D10001",
                        "channel_id": "ch0003",
                        "datapoint_id": "idp0000",
                        "value": "1",
                    }
                )
            )
    finally:
        await server.stop()


async def test_mock_sysap_server_health_and_ws_broadcast() -> None:
    """Verify standalone MockSysApServer serves /health, REST, and broadcasts WS updates."""
    server = MockSysApServer(port=0)
    await server.start()
    client = FreeAtHomeLocalApiClient(server.host_port, "apiuser", "secret")
    controller = FreeAtHomeController(client)
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get(f"http://{server.host_port}/health") as resp,
        ):
            assert resp.status == 200
            health = await resp.json()
            assert health["status"] == "healthy"
            assert health["device_count"] > 10

        await controller.initialize()
        switch = next(
            d for d in controller.get_devices("switch") if d.serialnumber == "ABB700D10001"
        )
        assert switch.is_on() is True  # type: ignore[attr-defined]

        updated = asyncio.Event()
        switch.register_device_updated_cb(AsyncMock(side_effect=lambda _d: updated.set()))
        controller.start_listening()
        await asyncio.sleep(0.05)

        await client.set_datapoint(
            controller.primary_sysap_uuid, "ABB700D10001", "ch0003", "odp0000", "0"
        )
        await asyncio.wait_for(updated.wait(), timeout=2.0)
        assert switch.is_on() is False  # type: ignore[attr-defined]
    finally:
        await controller.close()
        await server.stop()
