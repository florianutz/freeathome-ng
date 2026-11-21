"""Diagnostics support for free@home NG."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .const import DOMAIN

TO_REDACT = {
    CONF_PASSWORD,
    CONF_USERNAME,
    "password",
    "username",
    "jid",
    "serialNumber",
    "sysap_serial",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry[Any]
) -> dict[str, Any]:
    """Return redacted diagnostics for a free@home NG config entry."""
    runtime = getattr(entry, "runtime_data", None)
    if runtime is None:
        return {
            "entry": {
                "entry_id": entry.entry_id,
                "title": entry.title,
                "data": async_redact_data(dict(entry.data), TO_REDACT),
                "options": dict(entry.options),
            },
            "status": "not_loaded",
        }

    ctrl = runtime.controller
    platform_counts = {
        platform: len(ctrl.get_devices(platform))
        for platform in (
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
    }

    return {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "controller": {
            "host": ctrl.client.host,
            "use_https": ctrl.client.use_https,
            "ws_connected": ctrl.ws_connected,
            "sysap_uuids": ctrl.sysap_uuids,
            "sysap_names": ctrl.sysap_names,
            "sysap_version": ctrl.sysap_version,
            "sysap_serial": "**REDACTED**" if ctrl.sysap_serial else None,
            "total_devices": len(ctrl.devices),
            "platform_counts": platform_counts,
        },
        "raw_configuration": async_redact_data(ctrl.raw_configuration, TO_REDACT),
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry[Any], device: DeviceEntry
) -> dict[str, Any]:
    """Return redacted diagnostics scoped to a single free@home device."""
    target_sysap_uuid: str | None = None
    target_serial: str | None = None

    for ident_domain, ident_value in device.identifiers:
        if ident_domain == DOMAIN and not ident_value.startswith("hub_") and "_" in ident_value:
            target_sysap_uuid, target_serial = ident_value.split("_", 1)
            break

    if target_sysap_uuid is None or target_serial is None:
        return await async_get_config_entry_diagnostics(hass, entry)

    runtime = getattr(entry, "runtime_data", None)
    if runtime is None:
        return {
            "entry_id": entry.entry_id,
            "device_identifiers": [list(item) for item in sorted(device.identifiers)],
            "status": "not_loaded",
        }

    ctrl = runtime.controller
    matching_devices = [
        dev
        for dev in ctrl.devices
        if dev.sysap_uuid == target_sysap_uuid and dev.serialnumber == target_serial
    ]
    raw_device_config = (
        (ctrl.raw_configuration.get(target_sysap_uuid) or {}).get("devices", {}).get(target_serial)
    )

    return {
        "device": {
            "sysap_uuid": target_sysap_uuid,
            "serialnumber": target_serial,
            "model": (matching_devices[0].device_info.get("model") if matching_devices else None),
            "suggested_area": (
                matching_devices[0].device_info.get("suggested_area") if matching_devices else None
            ),
            "sw_version": (
                matching_devices[0].device_info.get("sw_version") if matching_devices else None
            ),
        },
        "controller": {
            "host": ctrl.client.host,
            "use_https": ctrl.client.use_https,
            "ws_connected": ctrl.ws_connected,
        },
        "channels": [
            {
                "channel_id": dev.channel_id,
                "function_id": (
                    f"0x{dev.function_id:04X}" if dev.function_id is not None else None
                ),
                "name": dev.name,
                "available": dev.available,
                "is_virtual": dev.is_virtual,
                "platform_class": type(dev).__name__,
            }
            for dev in matching_devices
        ],
        "raw_device_config": (
            async_redact_data(raw_device_config, TO_REDACT)
            if raw_device_config is not None
            else None
        ),
    }
