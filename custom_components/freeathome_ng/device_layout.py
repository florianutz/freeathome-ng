"""Device registry layout (ADR-001): SysAP hub -> physical device -> channel device.

Every free@home channel that produces entities becomes a child device of its physical
device, named like the channel and placed in the channel's room. SysAP-level functions
(scenes, groups, timer programs) stay single devices linked to the hub.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .api.devices.base import FahBaseDevice
from .const import DOMAIN


def hub_identifier(entry_id: str) -> tuple[str, str]:
    """Return the device identifier of the SysAP hub device."""
    return (DOMAIN, f"hub_{entry_id}")


def physical_identifier(device: FahBaseDevice) -> tuple[str, str]:
    """Return the device identifier of a channel's physical device."""
    return (DOMAIN, device.physical_device_key)


def channel_identifier(device: FahBaseDevice) -> tuple[str, str]:
    """Return the device identifier of a channel device."""
    return (DOMAIN, device.channel_device_key)


@callback
def async_get_or_create_physical_device(
    hass: HomeAssistant, entry_id: str, device: FahBaseDevice
) -> dr.DeviceEntry:
    """Register (or update) the physical device of `device`, linked to the hub."""
    dev_reg = dr.async_get(hass)
    info: dict[str, Any] = dict(device.device_info)
    hub = dev_reg.async_get_device_by_identifier(hub_identifier(entry_id), entry_id)
    if hub is not None:
        info["via_device_id"] = hub.id
    return dev_reg.async_get_or_create(config_entry_id=entry_id, **info)


@callback
def async_entity_device_info(
    hass: HomeAssistant, entry_id: str, device: FahBaseDevice
) -> dr.DeviceInfo | dr.ChildDeviceInfo:
    """Return the device info an entity of `device` attaches to."""
    physical = async_get_or_create_physical_device(hass, entry_id, device)
    if device.is_sysap_function:
        return dr.DeviceInfo(identifiers={physical_identifier(device)})

    # A channel in the same room as its physical device inherits the device's area,
    # so areas the user assigned to the physical device keep applying. Only channels
    # in another room get an area of their own.
    room = device.room_name
    own_area = room if room and room != device.device_info.get("suggested_area") else None
    return dr.ChildDeviceInfo(
        identifiers={channel_identifier(device)},
        name=device.channel_name,
        parent_device_id=physical.id,
        suggested_area=own_area,
    )


def active_identifiers(entry_id: str, devices: list[FahBaseDevice]) -> set[tuple[str, str]]:
    """Return all device identifiers the current SysAP configuration still uses."""
    identifiers = {hub_identifier(entry_id)}
    for device in devices:
        identifiers.add(physical_identifier(device))
        if not device.is_sysap_function:
            identifiers.add(channel_identifier(device))
    return identifiers
