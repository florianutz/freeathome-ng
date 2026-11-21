"""Support for free@home NG binary sensors and wall switch events."""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant

try:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
except ImportError:  # pragma: no cover - fallback for older HA typing
    from homeassistant.helpers.entity_platform import (  # type: ignore[no-redef]
        AddEntitiesCallback as AddConfigEntryEntitiesCallback,
    )

from . import FreeAtHomeNgConfigEntry, register_platform_adder
from .api.devices.binary_sensor import FahBinarySensor
from .const import EVENT_FREEATHOME_NG
from .entity import FreeAtHomeNgEntity
from .fah_event import create_event_data

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: FreeAtHomeNgConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up free@home NG binary sensor entities."""
    runtime = config_entry.runtime_data
    hub_device_id = runtime.hub_device_id
    entry_id = config_entry.entry_id
    sensors = runtime.controller.get_devices("binary_sensor")
    async_add_entities(
        FreeAtHomeNgBinarySensor(
            dev,  # type: ignore[arg-type]
            hass,
            hub_device_id=hub_device_id,
            entry_id=entry_id,
        )
        for dev in sensors
    )

    register_platform_adder(
        hass,
        entry_id,
        "binary_sensor",
        lambda new_devs: async_add_entities(
            FreeAtHomeNgBinarySensor(
                dev,  # type: ignore[arg-type]
                hass,
                hub_device_id=hub_device_id,
                entry_id=entry_id,
            )
            for dev in new_devs
        ),
    )


class FreeAtHomeNgBinarySensor(FreeAtHomeNgEntity, BinarySensorEntity):
    """Representation of a free@home NG binary sensor."""

    def __init__(
        self,
        device: FahBinarySensor,
        hass: HomeAssistant | None = None,
        *,
        hub_device_id: str | None = None,
        entry_id: str | None = None,
    ) -> None:
        """Initialize the binary sensor entity."""
        super().__init__(device, hub_device_id=hub_device_id, entry_id=entry_id)
        self.binary_device = device
        self._fallback_hass = hass
        self._reset_task: asyncio.Task[None] | None = None
        if device.is_door_call_sensor():
            device.state = "0"

    @property
    def is_on(self) -> bool:
        """Return True if the binary sensor is active."""
        return self.binary_device.state == "1"

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Return device class for safety, window, motion, and weather sensors."""
        if self.binary_device.is_fire_sensor():
            return BinarySensorDeviceClass.SMOKE
        if self.binary_device.is_co_sensor():
            return BinarySensorDeviceClass.CO
        if self.binary_device.is_door_call_sensor():
            return BinarySensorDeviceClass.OCCUPANCY
        if self.binary_device.is_window_door_sensor():
            return BinarySensorDeviceClass.WINDOW
        if self.binary_device.is_motion_sensor():
            return BinarySensorDeviceClass.MOTION
        if self.binary_device.is_rain_sensor():
            return BinarySensorDeviceClass.MOISTURE
        if self.binary_device.is_frost_sensor():
            return BinarySensorDeviceClass.COLD
        if self.binary_device.is_wind_sensor():
            return BinarySensorDeviceClass.SAFETY
        return None

    @property
    def icon(self) -> str | None:
        """Return doorbell icon for door call sensors."""
        if self.binary_device.is_door_call_sensor():
            return "mdi:doorbell"
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return window tilt/open position when available."""
        pos = self.binary_device.window_position
        if pos == "0":
            return {"window_position": "closed"}
        if pos == "33":
            return {"window_position": "tilted"}
        if pos == "100":
            return {"window_position": "open"}
        return {}

    async def _async_auto_reset(self) -> None:
        """Reset door call sensor state after a 2-second pulse."""
        try:
            await asyncio.sleep(2)
            if self.binary_device.state == "1":
                self.binary_device.state = "0"
                self.async_write_ha_state()
        except asyncio.CancelledError:
            return

    async def async_added_to_hass(self) -> None:
        """Register update and event callbacks."""

        async def _after_update(_dev: Any) -> None:
            target_hass = self.hass or self._fallback_hass
            if self.binary_device.is_door_call_sensor() and self.binary_device.state == "1":
                self.async_write_ha_state()
                if self._reset_task and not self._reset_task.done():
                    self._reset_task.cancel()
                if target_hass is not None:
                    self._reset_task = target_hass.async_create_task(self._async_auto_reset())
            else:
                self.async_write_ha_state()

        async def _on_dp_event(device: FahBinarySensor, event: dict[str, Any]) -> None:
            target_hass = self.hass or self._fallback_hass
            if target_hass is None:
                return
            payload = create_event_data(
                self.name or device.name,
                device.serialnumber,
                self.unique_id or device.unique_id,
                event,
            )
            target_hass.bus.async_fire(EVENT_FREEATHOME_NG, payload)

        self.binary_device.register_device_updated_cb(_after_update)
        self.binary_device.register_datapoint_updated_cb(_on_dp_event)
        self.async_on_remove(lambda: self.binary_device.unregister_device_updated_cb(_after_update))
        self.async_on_remove(
            lambda: self.binary_device.unregister_datapoint_updated_cb(_on_dp_event)
        )

    async def async_will_remove_from_hass(self) -> None:
        """Cancel pending door call reset task."""
        if self._reset_task and not self._reset_task.done():
            self._reset_task.cancel()
