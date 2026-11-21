"""Shared base entity class for free@home NG Home Assistant entities."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Coroutine
from functools import wraps
from typing import Any, Concatenate

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .api import FreeAtHomeApiError
from .api.devices.base import FahBaseDevice
from .const import DOMAIN


def api_action[EntityT: "FreeAtHomeNgEntity", **P, R](
    func: Callable[Concatenate[EntityT, P], Awaitable[R]],
) -> Callable[Concatenate[EntityT, P], Coroutine[Any, Any, R]]:
    """Re-raise SysAP API errors of an entity action as a translated `HomeAssistantError`."""

    @wraps(func)
    async def _wrapper(self: EntityT, *args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await func(self, *args, **kwargs)
        except FreeAtHomeApiError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="action_failed",
                translation_placeholders={"entity_id": self.entity_id, "error": str(err)},
            ) from err

    return _wrapper


class FreeAtHomeNgEntity(Entity):
    """Base entity binding a `FahBaseDevice` model to Home Assistant."""

    _attr_should_poll = False

    def __init__(
        self,
        device: FahBaseDevice,
        *,
        hub_device_id: str | None = None,
        entry_id: str | None = None,
    ) -> None:
        """Initialize common entity attributes."""
        self.fah_device = device
        if not getattr(self, "_attr_translation_key", None):
            self._attr_name = device.name
        self._attr_unique_id = device.unique_id

        info = dict(device.device_info)
        if hub_device_id:
            info["via_device_id"] = hub_device_id
        self._attr_device_info = DeviceInfo(**info)

    @property
    def available(self) -> bool:
        """Return True if the device and SysAP connection are available."""
        return self.fah_device.available and self.fah_device.controller.ws_connected

    async def async_added_to_hass(self) -> None:
        """Register state update callback when added to Home Assistant."""

        async def _after_update(_device: FahBaseDevice) -> None:
            self._sync_from_device()
            self.async_write_ha_state()

        self.fah_device.register_device_updated_cb(_after_update)
        self.async_on_remove(lambda: self.fah_device.unregister_device_updated_cb(_after_update))
        self._sync_from_device()

    def _sync_from_device(self) -> None:
        """Hook for subclasses to synchronize cached state if needed."""

    def get_extra_attr(self, key: str, default: Any = None) -> Any:
        """Safely read an attribute from the underlying device."""
        return getattr(self.fah_device, key, default)
