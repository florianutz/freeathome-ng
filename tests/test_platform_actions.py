"""Entity actions of every writable platform, end to end against the mock SysAP."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from mock_sysap_server import MockSysApServer
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.freeathome_ng.api import FreeAtHomeApiError
from custom_components.freeathome_ng.const import DOMAIN

from .conftest import entity_id_for
from .test_platforms import _broadcast_dp, _wait_for_state

DIMMER = ("light", "ABB700D10002/ch0000")
TUNABLE = ("light", "ABB700D10002/ch0001")
RGB = ("light", "ABB700D10002/ch0002")
GROUP = ("light", "FFFF40000001/ch0000")
THERMOSTAT = ("climate", "ABB700D10004/ch0000")
SHUTTER = ("cover", "ABB700D10003/ch0000")
FAN = ("fan", "ABB700D10005/ch0000")
LOCK = ("lock", "ABB700D10010/ch0000")

# Entities are looked up by unique ID: generated entity IDs differ between HA releases.


def _writes(server: MockSysApServer, prefix: str) -> list[tuple[str, str]]:
    """Return `(path, value)` of every datapoint or parameter write below `prefix`."""
    return [
        (path, body)
        for kind, path, body in server.recorded
        if kind in ("PUT_DP", "PUT_PARAM") and path.startswith(prefix)
    ]


@pytest.mark.parametrize(
    ("domain", "service", "entity", "data", "prefix"),
    [
        ("light", "turn_on", DIMMER, {"brightness": 128}, "ABB700D10002.ch0000."),
        ("light", "turn_on", DIMMER, {"brightness": 0}, "ABB700D10002.ch0000."),
        ("light", "turn_off", DIMMER, {}, "ABB700D10002.ch0000."),
        ("light", "turn_on", TUNABLE, {"color_temp_kelvin": 3000}, "ABB700D10002.ch0001."),
        ("light", "turn_on", RGB, {"rgb_color": [1, 2, 3]}, "ABB700D10002.ch0002."),
        ("light", "turn_off", GROUP, {}, "FFFF40000001.ch0000."),
        ("climate", "set_hvac_mode", THERMOSTAT, {"hvac_mode": "off"}, "ABB700D10004.ch0000."),
        ("climate", "set_preset_mode", THERMOSTAT, {"preset_mode": "eco"}, "ABB700D10004."),
        ("climate", "set_preset_mode", THERMOSTAT, {"preset_mode": "none"}, "ABB700D10004."),
        ("climate", "set_temperature", THERMOSTAT, {"temperature": 22.5}, "ABB700D10004."),
        ("climate", "turn_off", THERMOSTAT, {}, "ABB700D10004.ch0000."),
        ("cover", "open_cover", SHUTTER, {}, "ABB700D10003.ch0000."),
        ("cover", "close_cover", SHUTTER, {}, "ABB700D10003.ch0000."),
        ("cover", "set_cover_position", SHUTTER, {"position": 40}, "ABB700D10003.ch0000."),
        ("cover", "set_cover_tilt_position", SHUTTER, {"tilt_position": 30}, "ABB700D10003."),
        ("fan", "turn_on", FAN, {"percentage": 50}, "ABB700D10005.ch0000."),
        ("fan", "set_percentage", FAN, {"percentage": 25}, "ABB700D10005.ch0000."),
        ("fan", "turn_off", FAN, {}, "ABB700D10005.ch0000."),
        ("lock", "unlock", LOCK, {}, "ABB700D10010.ch0000."),
        ("lock", "lock", LOCK, {}, "ABB700D10010.ch0000."),
        (DOMAIN, "cover_force_position", SHUTTER, {"forced_position": "closed"}, "ABB700D10003."),
        (
            DOMAIN,
            "thermostat_temperature_correction",
            THERMOSTAT,
            {"temperature_correction": -1.5},
            "ABB700D10004.",
        ),
    ],
)
async def test_entity_action_writes_to_sysap(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_sysap: MockSysApServer,
    domain: str,
    service: str,
    entity: tuple[str, str],
    data: dict[str, Any],
    prefix: str,
) -> None:
    """Every entity action results in a write to the matching channel."""
    entity_id = entity_id_for(hass, *entity)
    assert hass.states.get(entity_id) is not None
    mock_sysap.recorded.clear()
    await hass.services.async_call(domain, service, {"entity_id": entity_id, **data}, blocking=True)
    await hass.async_block_till_done()
    assert _writes(mock_sysap, prefix), mock_sysap.recorded


async def test_light_attributes(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """Dimmer, tunable and RGB lights expose their color modes and values."""
    dimmer = hass.states.get(entity_id_for(hass, *DIMMER))
    assert dimmer.attributes["color_mode"] == "brightness"
    assert dimmer.attributes["brightness"] == 153
    tunable = hass.states.get(entity_id_for(hass, *TUNABLE))
    assert tunable.attributes["color_mode"] == "color_temp"
    assert tunable.attributes["color_temp_kelvin"] == 4600
    assert tunable.attributes["min_color_temp_kelvin"] == 2700
    assert tunable.attributes["max_color_temp_kelvin"] == 6500
    rgb = hass.states.get(entity_id_for(hass, *RGB))
    assert rgb.attributes["color_mode"] == "rgb"
    assert rgb.attributes["rgb_color"] == (255, 128, 0)


async def test_climate_and_cover_attributes(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_sysap: MockSysApServer
) -> None:
    """Thermostat and cover expose their state attributes; off hides the target."""
    climate = hass.states.get(entity_id_for(hass, *THERMOSTAT))
    assert climate.state == HVACMode.HEAT_COOL
    assert "valve" in climate.attributes
    assert "temperature_correction" in climate.attributes
    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": entity_id_for(hass, *THERMOSTAT), "hvac_mode": "off"},
        blocking=True,
    )
    await hass.async_block_till_done()
    await hass.services.async_call(
        "climate", "turn_on", {"entity_id": entity_id_for(hass, *THERMOSTAT)}, blocking=True
    )
    await hass.async_block_till_done()
    cover = hass.states.get(entity_id_for(hass, *SHUTTER))
    assert "forced_position" in cover.attributes
    assert cover.attributes["device_class"] == "shutter"


async def test_entity_action_api_error_is_translated(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """A failing SysAP write surfaces as a translated `HomeAssistantError`."""
    with (
        patch(
            "custom_components.freeathome_ng.api.client.FreeAtHomeLocalApiClient.set_datapoint",
            side_effect=FreeAtHomeApiError("boom"),
        ),
        pytest.raises(HomeAssistantError) as err,
    ):
        await hass.services.async_call(
            "lock", "unlock", {"entity_id": entity_id_for(hass, *LOCK)}, blocking=True
        )
    assert err.value.translation_key == "action_failed"
    assert err.value.translation_placeholders["entity_id"] == entity_id_for(hass, *LOCK)


async def test_cover_stop_only_while_moving(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_sysap: MockSysApServer
) -> None:
    """Stop is sent only while the cover reports movement; movement is reflected."""
    mock_sysap.recorded.clear()
    await hass.services.async_call(
        "cover", "stop_cover", {"entity_id": entity_id_for(hass, *SHUTTER)}, blocking=True
    )
    assert not _writes(mock_sysap, "ABB700D10003.")

    await _broadcast_dp(mock_sysap, "ABB700D10003/ch0000/odp0000", "3")
    await _wait_for_state(hass, entity_id_for(hass, *SHUTTER), "closing")
    await hass.services.async_call(
        "cover", "stop_cover", {"entity_id": entity_id_for(hass, *SHUTTER)}, blocking=True
    )
    assert ("ABB700D10003.ch0000.idp0001", "1") in _writes(mock_sysap, "ABB700D10003.")

    await _broadcast_dp(mock_sysap, "ABB700D10003/ch0000/odp0000", "2")
    await _wait_for_state(hass, entity_id_for(hass, *SHUTTER), "opening")
