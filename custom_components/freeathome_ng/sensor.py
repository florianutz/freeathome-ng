"""Support for free@home NG sensors (weather, air quality, valve, energy, dimmer status)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    LIGHT_LUX,
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant

try:
    from homeassistant.const import UnitOfDensity, UnitOfRatio
except ImportError:  # pragma: no cover - fallback for older HA Core
    from homeassistant.const import (
        CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        CONCENTRATION_PARTS_PER_MILLION,
    )

    CO2_CONCENTRATION_UNIT = CONCENTRATION_PARTS_PER_MILLION
    VOC_CONCENTRATION_UNIT = CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
else:
    CO2_CONCENTRATION_UNIT = UnitOfRatio.PARTS_PER_MILLION
    VOC_CONCENTRATION_UNIT = UnitOfDensity.MICROGRAMS_PER_CUBIC_METER

try:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
except ImportError:  # pragma: no cover - fallback for older HA typing
    from homeassistant.helpers.entity_platform import (  # type: ignore[no-redef]
        AddEntitiesCallback as AddConfigEntryEntitiesCallback,
    )

from . import FreeAtHomeNgConfigEntry, register_platform_adder
from .api.devices.base import FahBaseDevice
from .api.devices.binary_sensor import FahBinarySensor
from .api.devices.climate import FahThermostat
from .api.devices.sensor import FahSensor
from .entity import FreeAtHomeNgEntity
from .fah_event import (
    DIMMING_STATUS_DEFAULT,
    DIMMING_STATUS_OPTIONS,
    dimming_status_sequence_from_event,
)

PARALLEL_UPDATES = 0


@dataclass(frozen=True)
class SensorDescription:
    """Metadata describing a free@home NG numeric sensor type."""

    label: str
    unit: str | None
    icon: str | None
    device_class: SensorDeviceClass | None
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT


SENSOR_TYPES: dict[str, SensorDescription] = {
    "temperature": SensorDescription(
        "Temperature",
        UnitOfTemperature.CELSIUS,
        "mdi:thermometer",
        SensorDeviceClass.TEMPERATURE,
    ),
    "windstrength": SensorDescription(
        "Wind Strength",
        UnitOfSpeed.KILOMETERS_PER_HOUR,
        "mdi:weather-windy",
        SensorDeviceClass.WIND_SPEED,
    ),
    "windforce": SensorDescription(
        "Wind Force",
        None,
        "mdi:weather-windy-variant",
        None,
    ),
    "rain": SensorDescription(
        "Rain",
        None,
        "mdi:weather-rainy",
        None,
        None,
    ),
    "lux": SensorDescription(
        "Illumination",
        LIGHT_LUX,
        None,
        SensorDeviceClass.ILLUMINANCE,
    ),
    "valve_volume_flow": SensorDescription(
        "Heating valve volume flow",
        PERCENTAGE,
        None,
        None,
    ),
    "humidity": SensorDescription(
        "Humidity",
        PERCENTAGE,
        None,
        SensorDeviceClass.HUMIDITY,
    ),
    "co2": SensorDescription(
        "CO2",
        CO2_CONCENTRATION_UNIT,
        None,
        SensorDeviceClass.CO2,
    ),
    "voc": SensorDescription(
        "VOC",
        VOC_CONCENTRATION_UNIT,
        None,
        SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS,
    ),
    "pv_power": SensorDescription(
        "PV Power",
        UnitOfPower.WATT,
        "mdi:solar-power",
        SensorDeviceClass.POWER,
    ),
    "battery_power": SensorDescription(
        "Battery Power",
        UnitOfPower.WATT,
        "mdi:battery-charging",
        SensorDeviceClass.POWER,
    ),
    "battery_soc": SensorDescription(
        "Battery SoC",
        PERCENTAGE,
        "mdi:battery",
        SensorDeviceClass.BATTERY,
    ),
    "grid_power": SensorDescription(
        "Grid Power",
        UnitOfPower.WATT,
        "mdi:transmission-tower",
        SensorDeviceClass.POWER,
    ),
    "home_power": SensorDescription(
        "Home Power Consumption",
        UnitOfPower.WATT,
        "mdi:home-lightning-bolt",
        SensorDeviceClass.POWER,
    ),
    "consumed_energy": SensorDescription(
        "Consumed Energy",
        UnitOfEnergy.KILO_WATT_HOUR,
        "mdi:lightning-bolt",
        SensorDeviceClass.ENERGY,
        SensorStateClass.TOTAL_INCREASING,
    ),
    "injected_energy": SensorDescription(
        "Injected Energy",
        UnitOfEnergy.KILO_WATT_HOUR,
        "mdi:transmission-tower-export",
        SensorDeviceClass.ENERGY,
        SensorStateClass.TOTAL_INCREASING,
    ),
    "self_consumption": SensorDescription(
        "Self Consumption",
        PERCENTAGE,
        "mdi:percent",
        None,
    ),
    "self_sufficiency": SensorDescription(
        "Self Sufficiency",
        PERCENTAGE,
        "mdi:percent",
        None,
    ),
}


def _build_sensor_entities(
    devices: list[FahBaseDevice],
    *,
    hub_device_id: str | None = None,
    entry_id: str | None = None,
) -> list[SensorEntity]:
    """Create Home Assistant sensor entities from free@home device models."""
    entities: list[SensorEntity] = []
    for dev in devices:
        if isinstance(dev, FahSensor):
            entities.append(FreeAtHomeNgSensor(dev, hub_device_id=hub_device_id, entry_id=entry_id))
        elif isinstance(dev, FahThermostat):
            entities.append(
                FreeAtHomeNgThermostatTemperatureSensor(
                    dev, hub_device_id=hub_device_id, entry_id=entry_id
                )
            )
        elif isinstance(dev, FahBinarySensor) and dev.supports_dimming_status():
            entities.append(
                FreeAtHomeNgDimmingStatusSensor(dev, hub_device_id=hub_device_id, entry_id=entry_id)
            )
    return entities


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: FreeAtHomeNgConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up free@home NG sensor entities."""
    runtime = config_entry.runtime_data
    ctrl = runtime.controller
    hub_device_id = runtime.hub_device_id
    entry_id = config_entry.entry_id

    initial_sources: list[FahBaseDevice] = [
        *ctrl.get_devices("sensor"),
        *ctrl.get_devices("thermostat"),
        *ctrl.get_devices("binary_sensor"),
    ]
    async_add_entities(
        _build_sensor_entities(initial_sources, hub_device_id=hub_device_id, entry_id=entry_id)
    )

    register_platform_adder(
        hass,
        entry_id,
        "sensor",
        lambda new_devs: async_add_entities(
            _build_sensor_entities(new_devs, hub_device_id=hub_device_id, entry_id=entry_id)
        ),
    )


class FreeAtHomeNgSensor(FreeAtHomeNgEntity, SensorEntity):
    """Representation of a free@home NG numeric sensor."""

    def __init__(
        self,
        device: FahSensor,
        *,
        hub_device_id: str | None = None,
        entry_id: str | None = None,
    ) -> None:
        """Initialize the sensor entity."""
        desc = SENSOR_TYPES.get(device.type or "")
        if device.type is not None and desc is not None:
            self._attr_has_entity_name = True
            self._attr_translation_key = device.type
            self._attr_translation_placeholders = {"channel_name": device.base_name}
        super().__init__(device, hub_device_id=hub_device_id, entry_id=entry_id)
        self.sensor_device = device
        if desc is not None:
            self._attr_native_unit_of_measurement = desc.unit
            self._attr_icon = desc.icon
            self._attr_device_class = desc.device_class
            self._attr_state_class = desc.state_class

    @property
    def native_value(self) -> Any:
        """Return sensor value, converting wind speed from m/s to km/h."""
        raw = self.sensor_device.state
        if raw is None:
            return None
        if self._attr_native_unit_of_measurement == UnitOfSpeed.KILOMETERS_PER_HOUR:
            try:
                return round(float(raw) * 3.6, 2)
            except (TypeError, ValueError):
                return raw
        if self._attr_device_class is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                return raw
        return raw


class FreeAtHomeNgThermostatTemperatureSensor(FreeAtHomeNgEntity, SensorEntity):
    """Dedicated temperature sensor exposed alongside each thermostat."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_translation_key = "thermostat_temperature"

    def __init__(
        self,
        device: FahThermostat,
        *,
        hub_device_id: str | None = None,
        entry_id: str | None = None,
    ) -> None:
        """Initialize thermostat temperature sensor."""
        super().__init__(device, hub_device_id=hub_device_id, entry_id=entry_id)
        self.thermostat_device = device
        self._attr_translation_placeholders = {"channel_name": device.name}
        self._attr_unique_id = f"{device.unique_id}/current_temperature"

    @property
    def native_value(self) -> float | None:
        """Return measured thermostat temperature."""
        return self.thermostat_device.current_temperature


class FreeAtHomeNgDimmingStatusSensor(FreeAtHomeNgEntity, SensorEntity):
    """Enum sensor exposing dimmer rocker press/hold actions."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_has_entity_name = True
    _attr_options = DIMMING_STATUS_OPTIONS
    _attr_translation_key = "dimming_status"

    def __init__(
        self,
        device: FahBinarySensor,
        *,
        hub_device_id: str | None = None,
        entry_id: str | None = None,
    ) -> None:
        """Initialize dimmer status sensor."""
        super().__init__(device, hub_device_id=hub_device_id, entry_id=entry_id)
        self.binary_device = device
        self._attr_native_value = DIMMING_STATUS_DEFAULT
        self._attr_translation_placeholders = {"channel_id": device.channel_id}
        self._attr_unique_id = f"{device.unique_id}/dimming_status"

    async def async_added_to_hass(self) -> None:
        """Subscribe to decoded rocker events."""
        await super().async_added_to_hass()

        async def _on_dp_event(_device: FahBinarySensor, event: dict[str, Any]) -> None:
            for status in dimming_status_sequence_from_event(event):
                self._attr_native_value = status
                self.async_write_ha_state()

        self.binary_device.register_datapoint_updated_cb(_on_dp_event)
        self.async_on_remove(
            lambda: self.binary_device.unregister_datapoint_updated_cb(_on_dp_event)
        )
