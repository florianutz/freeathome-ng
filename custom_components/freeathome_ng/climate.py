"""Support for free@home NG room temperature controllers (thermostats)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform

try:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
except ImportError:  # pragma: no cover - fallback for older HA typing
    from homeassistant.helpers.entity_platform import (  # type: ignore[no-redef]
        AddEntitiesCallback as AddConfigEntryEntitiesCallback,
    )

from . import FreeAtHomeNgConfigEntry, register_platform_adder
from .api.devices.climate import FahThermostat
from .entity import FreeAtHomeNgEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: FreeAtHomeNgConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up free@home NG climate entities."""
    runtime = config_entry.runtime_data
    hub_device_id = runtime.hub_device_id
    entry_id = config_entry.entry_id
    thermostats = runtime.controller.get_devices("thermostat")
    async_add_entities(
        FreeAtHomeNgThermostat(
            dev,  # type: ignore[arg-type]
            hub_device_id=hub_device_id,
            entry_id=entry_id,
        )
        for dev in thermostats
    )

    register_platform_adder(
        hass,
        entry_id,
        "climate",
        lambda new_devs: async_add_entities(
            FreeAtHomeNgThermostat(
                dev,  # type: ignore[arg-type]
                hub_device_id=hub_device_id,
                entry_id=entry_id,
            )
            for dev in new_devs
        ),
    )

    platform = entity_platform.async_get_current_platform()
    if platform is not None:
        platform.async_register_entity_service(
            "thermostat_temperature_correction",
            {vol.Required("temperature_correction"): vol.Coerce(float)},
            "async_set_temperature_correction",
        )


class FreeAtHomeNgThermostat(FreeAtHomeNgEntity, ClimateEntity):
    """Representation of a free@home NG thermostat."""

    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_hvac_modes = [HVACMode.HEAT_COOL, HVACMode.OFF]
    _attr_preset_modes = ["none", "eco"]
    _attr_fan_modes = ["auto", "low", "medium", "high"]
    _attr_icon = "mdi:thermometer-lines"

    def __init__(
        self,
        device: FahThermostat,
        *,
        hub_device_id: str | None = None,
        entry_id: str | None = None,
    ) -> None:
        """Initialize the thermostat entity."""
        super().__init__(device, hub_device_id=hub_device_id, entry_id=entry_id)
        self.thermostat_device = device

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return supported climate features."""
        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.PRESET_MODE
            | getattr(ClimateEntityFeature, "TURN_OFF", 0)
            | getattr(ClimateEntityFeature, "TURN_ON", 0)
        )
        if self.thermostat_device.supports_fan_stage():
            features |= ClimateEntityFeature.FAN_MODE
        return features

    @property
    def native_current_temperature(self) -> float | None:
        """Return current room temperature."""
        return self.thermostat_device.current_temperature

    @property
    def native_target_temperature(self) -> float | None:
        """Return target temperature when active."""
        if self.hvac_mode == HVACMode.OFF:
            return None
        return self.thermostat_device.target_temperature

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        return HVACMode.HEAT_COOL if self.thermostat_device.state else HVACMode.OFF

    @property
    def preset_mode(self) -> str:
        """Return current preset mode."""
        return "eco" if self.thermostat_device.ecomode else "none"

    @property
    def fan_mode(self) -> str | None:
        """Return current fan stage if supported."""
        if not self.thermostat_device.supports_fan_stage():
            return None
        return self.thermostat_device.fan_stage

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return valve demand and temperature correction offset."""
        return {
            "valve": self.thermostat_device.current_actuator,
            "temperature_correction": self.thermostat_device.temperature_correction,
        }

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new HVAC mode."""
        if hvac_mode == HVACMode.HEAT_COOL:
            await self.thermostat_device.turn_on()
        elif hvac_mode == HVACMode.OFF:
            await self.thermostat_device.turn_off()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set eco or normal preset."""
        if preset_mode == "eco":
            await self.thermostat_device.eco_mode()
        else:
            await self.thermostat_device.turn_on()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is not None:
            await self.thermostat_device.set_target_temperature(float(temperature))

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan mode stage."""
        await self.thermostat_device.set_fan_stage(fan_mode)

    async def async_set_temperature_correction(
        self, temperature_correction: float
    ) -> None:
        """Update temperature correction offset parameter."""
        await self.thermostat_device.set_temperature_correction(temperature_correction)

    async def async_turn_on(self) -> None:
        """Turn thermostat on."""
        await self.async_set_hvac_mode(HVACMode.HEAT_COOL)

    async def async_turn_off(self) -> None:
        """Turn thermostat off."""
        await self.async_set_hvac_mode(HVACMode.OFF)
