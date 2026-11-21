"""Support for free@home NG switches and timer profile switches."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant

try:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
except ImportError:  # pragma: no cover - fallback for older HA typing
    from homeassistant.helpers.entity_platform import (  # type: ignore[no-redef]
        AddEntitiesCallback as AddConfigEntryEntitiesCallback,
    )

from . import FreeAtHomeNgConfigEntry, register_platform_adder
from .api.devices.switch import FahSwitch
from .entity import FreeAtHomeNgEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: FreeAtHomeNgConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up free@home NG switch entities."""
    runtime = config_entry.runtime_data
    hub_device_id = runtime.hub_device_id
    entry_id = config_entry.entry_id
    switches = runtime.controller.get_devices("switch")
    async_add_entities(
        FreeAtHomeNgSwitch(
            dev,  # type: ignore[arg-type]
            hub_device_id=hub_device_id,
            entry_id=entry_id,
        )
        for dev in switches
    )

    register_platform_adder(
        hass,
        entry_id,
        "switch",
        lambda new_devs: async_add_entities(
            FreeAtHomeNgSwitch(
                dev,  # type: ignore[arg-type]
                hub_device_id=hub_device_id,
                entry_id=entry_id,
            )
            for dev in new_devs
        ),
    )


class FreeAtHomeNgSwitch(FreeAtHomeNgEntity, SwitchEntity):
    """Representation of a free@home NG switch."""

    def __init__(
        self,
        device: FahSwitch,
        *,
        hub_device_id: str | None = None,
        entry_id: str | None = None,
    ) -> None:
        """Initialize the switch entity."""
        super().__init__(device, hub_device_id=hub_device_id, entry_id=entry_id)
        self.switch_device = device

    @property
    def is_on(self) -> bool | None:
        """Return True if the switch is on."""
        return self.switch_device.is_on()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self.switch_device.turn_on()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self.switch_device.turn_off()
        self.async_write_ha_state()
