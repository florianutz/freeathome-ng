"""Shared fixtures for the free@home NG test suite (real Home Assistant core)."""

from __future__ import annotations

import sys
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any
from unittest.mock import PropertyMock, patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from syrupy.assertion import SnapshotAssertion

TESTS_DIR = Path(__file__).parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from mock_sysap_server import MockSysApServer  # noqa: E402

from custom_components.freeathome_ng.const import DOMAIN  # noqa: E402

SYSAP_UUID = "00000000-0000-0000-0000-000000000000"
SYSAP_SERIAL = "ABB700999999"
USERNAME = "apiuser"
PASSWORD = "secret"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load `custom_components/freeathome_ng` in every test."""


@pytest.fixture(autouse=True)
def _allow_localhost_sockets(socket_enabled: None) -> None:
    """Allow real sockets so tests can talk to the local mock SysAP.

    `pytest-homeassistant-custom-component` still restricts connections to 127.0.0.1.
    """


@pytest.fixture
async def mock_sysap() -> AsyncGenerator[MockSysApServer]:
    """Start a mock SysAP (REST + WebSocket) on a free localhost port."""
    server = MockSysApServer(port=0, username=USERNAME, password=PASSWORD)
    await server.start()
    try:
<<<<<<< HEAD
        yield server
    finally:
        await server.stop()

=======
        import homeassistant  # noqa: F401

        return
    except ImportError:
        pass

    if "voluptuous" not in sys.modules:
        vol = types.ModuleType("voluptuous")
        vol.Schema = lambda schema, **kwargs: schema
        vol.Required = lambda key, default=None: key
        vol.Optional = lambda key, default=None: key
        vol.All = lambda *args: args
        vol.Coerce = lambda typ: typ
        vol.Range = lambda **kwargs: lambda x: x
        vol.In = lambda choices: choices
        vol.ALLOW_EXTRA = object()
        sys.modules["voluptuous"] = vol
>>>>>>> origin/claude/project-thread-02ukwt

def entry_data(server: MockSysApServer, **overrides: Any) -> dict[str, Any]:
    """Return config entry data pointing at the mock SysAP."""
    return {
        CONF_HOST: server.host_port,
        CONF_USERNAME: USERNAME,
        CONF_PASSWORD: PASSWORD,
        **overrides,
    }


<<<<<<< HEAD
@pytest.fixture
def mock_config_entry(mock_sysap: MockSysApServer) -> MockConfigEntry:
    """Return a config entry for the mock SysAP (not yet added to hass)."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Mock SysAP",
        unique_id=SYSAP_SERIAL,
        data=entry_data(mock_sysap),
        entry_id="01JNGTESTENTRY0000000000000",
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> MockConfigEntry:
    """Set up the integration against the mock SysAP and return the entry."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry
=======
    class Platform(StrEnum):
        BINARY_SENSOR = "binary_sensor"
        BUTTON = "button"
        CLIMATE = "climate"
        COVER = "cover"
        FAN = "fan"
        LIGHT = "light"
        LOCK = "lock"
        SCENE = "scene"
        SENSOR = "sensor"
        SWITCH = "switch"

    const = _make_mod("homeassistant.const")
    const.CONF_HOST = "host"
    const.CONF_NAME = "name"
    const.CONF_PASSWORD = "password"
    const.CONF_USERNAME = "username"
    const.ATTR_TEMPERATURE = "temperature"
    const.EVENT_HOMEASSISTANT_STOP = "homeassistant_stop"
    const.LIGHT_LUX = "lx"
    const.PERCENTAGE = "%"
    const.CONCENTRATION_MICROGRAMS_PER_CUBIC_METER = "µg/m³"
    const.CONCENTRATION_PARTS_PER_MILLION = "ppm"
    const.Platform = Platform
    const.UnitOfDensity = types.SimpleNamespace(MICROGRAMS_PER_CUBIC_METER="µg/m³")
    const.UnitOfEnergy = types.SimpleNamespace(KILO_WATT_HOUR="kWh")
    const.UnitOfPower = types.SimpleNamespace(WATT="W")
    const.UnitOfRatio = types.SimpleNamespace(PARTS_PER_MILLION="ppm")
    const.UnitOfSpeed = types.SimpleNamespace(KILOMETERS_PER_HOUR="km/h")
    const.UnitOfTemperature = types.SimpleNamespace(CELSIUS="°C")

    core = _make_mod("homeassistant.core")
    core.HomeAssistant = object
    core.ServiceCall = object
    core.SupportsResponse = types.SimpleNamespace(
        NONE="none",
        OPTIONAL="optional",
        ONLY="only",
    )
    core.callback = lambda fn: fn

    exceptions = _make_mod("homeassistant.exceptions")
    HomeAssistantError = type("HomeAssistantError", (Exception,), {})
    exceptions.HomeAssistantError = HomeAssistantError
    exceptions.ServiceValidationError = type("ServiceValidationError", (HomeAssistantError,), {})
    exceptions.ConfigEntryAuthFailed = type("ConfigEntryAuthFailed", (Exception,), {})
    exceptions.ConfigEntryNotReady = type("ConfigEntryNotReady", (Exception,), {})

    class AbortFlow(Exception):
        def __init__(
            self,
            reason: str,
            description_placeholders: dict[str, str] | None = None,
        ) -> None:
            super().__init__(reason)
            self.reason = reason
            self.description_placeholders = description_placeholders or {}

    data_entry_flow = _make_mod("homeassistant.data_entry_flow")
    data_entry_flow.AbortFlow = AbortFlow

    class ConfigEntry:
        def __class_getitem__(cls, _item: Any) -> type[ConfigEntry]:
            return cls

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs: Any) -> None:
            pass

        def __new__(cls, *args: Any, **kwargs: Any) -> ConfigFlow:
            instance = super().__new__(cls)
            instance.hass = None
            instance.context = {}
            instance.source = "user"
            instance.unique_id = None
            return instance

        def __init__(self) -> None:
            self.hass: Any = getattr(self, "hass", None)
            self.context: dict[str, Any] = getattr(self, "context", {})
            self.source: str = getattr(self, "source", "user")
            self.unique_id: str | None = getattr(self, "unique_id", None)

        async def async_set_unique_id(
            self, unique_id: str | None, *, raise_on_progress: bool = True
        ) -> None:
            self.unique_id = unique_id

        def _abort_if_unique_id_configured(
            self,
            updates: dict[str, Any] | None = None,
            reload_on_update: bool = True,
        ) -> None:
            if self.hass is None or self.unique_id is None:
                return
            entries = self.hass.config_entries.async_entries()
            for entry in entries:
                if getattr(entry, "unique_id", None) == self.unique_id:
                    if updates is not None:
                        entry.data = {**entry.data, **updates}
                    raise AbortFlow("already_configured")

        def async_show_form(
            self,
            *,
            step_id: str,
            data_schema: Any = None,
            errors: dict[str, str] | None = None,
            description_placeholders: dict[str, str] | None = None,
        ) -> dict[str, Any]:
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": errors or {},
                "description_placeholders": description_placeholders or {},
            }

        def async_abort(
            self,
            *,
            reason: str,
            description_placeholders: dict[str, str] | None = None,
        ) -> dict[str, Any]:
            return {
                "type": "abort",
                "reason": reason,
                "description_placeholders": description_placeholders or {},
            }

        def async_create_entry(
            self,
            *,
            title: str,
            data: dict[str, Any],
            options: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            return {
                "type": "create_entry",
                "title": title,
                "data": data,
                "options": options or {},
            }

        def _get_reauth_entry(self) -> Any:
            return self.hass.config_entries.async_get_entry(self.context["entry_id"])

        def _get_reconfigure_entry(self) -> Any:
            return self.hass.config_entries.async_get_entry(self.context["entry_id"])

        def async_update_and_abort(
            self,
            entry: Any,
            *,
            data: dict[str, Any] | None = None,
            data_updates: dict[str, Any] | None = None,
            reason: str = "reconfigure_successful",
        ) -> dict[str, Any]:
            if data is not None:
                entry.data = dict(data)
            elif data_updates is not None:
                entry.data = {**entry.data, **data_updates}
            return {"type": "abort", "reason": reason, "entry": entry}

        def async_update_reload_and_abort(
            self,
            entry: Any,
            *,
            data: dict[str, Any] | None = None,
            data_updates: dict[str, Any] | None = None,
            reason: str = "reconfigure_successful",
        ) -> dict[str, Any]:
            if data is not None:
                entry.data = dict(data)
            elif data_updates is not None:
                entry.data = {**entry.data, **data_updates}
            return {"type": "abort", "reason": reason, "entry": entry}

    class OptionsFlow:
        config_entry: Any = None

        def __init__(self) -> None:
            self.hass: Any = None

        def async_show_form(
            self,
            *,
            step_id: str,
            data_schema: Any = None,
            errors: dict[str, str] | None = None,
            description_placeholders: dict[str, str] | None = None,
        ) -> dict[str, Any]:
            return {
                "type": "form",
                "step_id": step_id,
                "data_schema": data_schema,
                "errors": errors or {},
                "description_placeholders": description_placeholders or {},
            }

        def async_create_entry(
            self,
            *,
            title: str,
            data: dict[str, Any],
        ) -> dict[str, Any]:
            return {"type": "create_entry", "title": title, "data": data}

    config_entries = _make_mod("homeassistant.config_entries")
    config_entries.ConfigEntry = ConfigEntry
    config_entries.ConfigFlowResult = dict
    config_entries.ConfigFlow = ConfigFlow
    config_entries.OptionsFlow = OptionsFlow

    _make_mod("homeassistant.helpers")
    helpers_cv = _make_mod("homeassistant.helpers.config_validation")
    helpers_cv.string = str
    helpers_cv.boolean = bool
    _make_mod("homeassistant.helpers.event").async_call_later = lambda *a, **kw: None
    _make_mod("homeassistant.helpers.aiohttp_client").async_get_clientsession = lambda *a, **kw: (
        None
    )

    dr = _make_mod("homeassistant.helpers.device_registry")
    dr.DeviceEntryType = types.SimpleNamespace(SERVICE="service")
    dr.DeviceEntry = object
    dr.DeviceInfo = dict
    dr.async_get = lambda hass: getattr(
        hass,
        "device_registry",
        types.SimpleNamespace(
            devices={},
            async_get=lambda _id: None,
            async_get_or_create=lambda **kw: types.SimpleNamespace(id="hub_dev_id", **kw),
            async_get_device_by_identifier=lambda _ident, _entry_id=None: None,
            async_get_devices=lambda **kw: [],
            async_get_device=lambda **kw: None,
            async_update_device=lambda *a, **kw: None,
        ),
    )

    er = _make_mod("homeassistant.helpers.entity_registry")
    er.RegistryEntryDisabler = types.SimpleNamespace(
        USER="user",
        CONFIG_ENTRY="config_entry",
        INTEGRATION="integration",
    )
    er.RegistryEntryHider = types.SimpleNamespace(
        USER="user",
        INTEGRATION="integration",
    )
    er.async_get = lambda hass: getattr(
        hass,
        "entity_registry",
        types.SimpleNamespace(
            entities={},
            entries=[],
            async_remove=lambda _eid: None,
            async_update_entity=lambda eid, **kw: types.SimpleNamespace(
                entity_id=kw.get("new_entity_id", eid)
            ),
            async_update_entity_options=lambda *_a, **_kw: None,
        ),
    )

    def _entries_for_config_entry(reg: Any, entry_id: str) -> list[Any]:
        source = (
            reg.entities.values()
            if hasattr(reg, "entities") and hasattr(reg.entities, "values")
            else getattr(reg, "entries", [])
        )
        return [e for e in source if getattr(e, "config_entry_id", None) == entry_id]

    er.async_entries_for_config_entry = _entries_for_config_entry

    class Entity:
        hass: Any = None

        @property
        def name(self) -> str | None:
            return getattr(self, "_attr_name", None)

        @property
        def unique_id(self) -> str | None:
            return getattr(self, "_attr_unique_id", None)

        @property
        def device_info(self) -> Any:
            return getattr(self, "_attr_device_info", None)

        def async_on_remove(self, func: Any) -> None:
            if not hasattr(self, "_on_remove_cbs"):
                self._on_remove_cbs = []
            self._on_remove_cbs.append(func)

        def async_write_ha_state(self) -> None:
            pass

        async def async_added_to_hass(self) -> None:
            pass

    _make_mod("homeassistant.helpers.entity").Entity = Entity

    entity_platform_mod = _make_mod("homeassistant.helpers.entity_platform")
    entity_platform_mod.AddEntitiesCallback = object
    entity_platform_mod.AddConfigEntryEntitiesCallback = object
    entity_platform_mod.async_get_current_platform = lambda: None

    _make_mod("homeassistant.helpers.service_info")

    class ZeroconfServiceInfo:
        def __init__(
            self,
            *,
            host: str = "",
            port: int = 80,
            hostname: str = "",
            type: str = "_http._tcp.local.",
            name: str = "",
            ip_address: Any = None,
            properties: dict[str, Any] | None = None,
        ) -> None:
            self.host = host
            self.port = port
            self.hostname = hostname
            self.type = type
            self.name = name
            self.ip_address = ip_address
            self.properties = properties or {}

    _make_mod(
        "homeassistant.helpers.service_info.zeroconf"
    ).ZeroconfServiceInfo = ZeroconfServiceInfo

    _make_mod("homeassistant.components")

    light_mod = _make_mod("homeassistant.components.light")
    light_mod.ATTR_BRIGHTNESS = "brightness"
    light_mod.ATTR_COLOR_TEMP_KELVIN = "color_temp_kelvin"
    light_mod.ATTR_RGB_COLOR = "rgb_color"
    light_mod.ColorMode = types.SimpleNamespace(
        RGB="rgb", COLOR_TEMP="color_temp", BRIGHTNESS="brightness", ONOFF="onoff"
    )
    light_mod.LightEntity = type("LightEntity", (), {})

    switch_mod = _make_mod("homeassistant.components.switch")
    switch_mod.SwitchEntity = type("SwitchEntity", (), {})

    cover_mod = _make_mod("homeassistant.components.cover")
    cover_mod.ATTR_POSITION = "position"
    cover_mod.ATTR_TILT_POSITION = "tilt_position"
    cover_mod.CoverDeviceClass = types.SimpleNamespace(
        WINDOW="window", AWNING="awning", SHUTTER="shutter", BLIND="blind"
    )
    cover_mod.CoverEntityFeature = types.SimpleNamespace(
        OPEN=1, CLOSE=2, SET_POSITION=4, STOP=8, SET_TILT_POSITION=128
    )
    cover_mod.CoverEntity = type("CoverEntity", (), {})

    climate_mod = _make_mod("homeassistant.components.climate")
    climate_mod.HVACMode = types.SimpleNamespace(HEAT_COOL="heat_cool", OFF="off")
    climate_mod.ClimateEntityFeature = types.SimpleNamespace(
        TARGET_TEMPERATURE=1, PRESET_MODE=16, FAN_MODE=8, TURN_OFF=128, TURN_ON=256
    )
    climate_mod.ClimateEntity = type("ClimateEntity", (), {})

    fan_mod = _make_mod("homeassistant.components.fan")
    fan_mod.FanEntityFeature = types.SimpleNamespace(SET_SPEED=1, TURN_OFF=16, TURN_ON=32)
    fan_mod.FanEntity = type("FanEntity", (), {})

    sensor_mod = _make_mod("homeassistant.components.sensor")
    sensor_mod.SensorDeviceClass = types.SimpleNamespace(
        TEMPERATURE="temperature",
        WIND_SPEED="wind_speed",
        ILLUMINANCE="illuminance",
        HUMIDITY="humidity",
        CO2="co2",
        VOLATILE_ORGANIC_COMPOUNDS="volatile_organic_compounds",
        POWER="power",
        BATTERY="battery",
        ENERGY="energy",
        ENUM="enum",
    )
    sensor_mod.SensorStateClass = types.SimpleNamespace(
        MEASUREMENT="measurement", TOTAL_INCREASING="total_increasing"
    )
    sensor_mod.SensorEntity = type("SensorEntity", (), {})

    bs_mod = _make_mod("homeassistant.components.binary_sensor")
    bs_mod.BinarySensorDeviceClass = types.SimpleNamespace(
        SMOKE="smoke",
        CO="co",
        OCCUPANCY="occupancy",
        WINDOW="window",
        MOTION="motion",
        MOISTURE="moisture",
        COLD="cold",
        SAFETY="safety",
    )
    bs_mod.BinarySensorEntity = type("BinarySensorEntity", (), {})

    button_mod = _make_mod("homeassistant.components.button")
    button_mod.ButtonEntity = type("ButtonEntity", (), {})

    lock_mod = _make_mod("homeassistant.components.lock")
    lock_mod.LockEntity = type("LockEntity", (), {})

    scene_mod = _make_mod("homeassistant.components.scene")
    scene_mod.Scene = type("Scene", (), {})
>>>>>>> origin/claude/project-thread-02ukwt


@pytest.fixture
def mock_setup_entry() -> Generator[Any]:
    """Prevent the integration from being set up during config flow tests."""
    with patch(
        "custom_components.freeathome_ng.async_setup_entry", return_value=True
    ) as mock_setup:
        yield mock_setup


@pytest.fixture
def entity_registry_enabled_by_default() -> Generator[None]:
    """Enable entities that are disabled by default, so snapshots cover all of them."""
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        new_callable=PropertyMock,
        return_value=True,
    ):
        yield


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Return snapshot assertion fixture with the Home Assistant extension."""
    return snapshot.use_extension(HomeAssistantSnapshotExtension)
