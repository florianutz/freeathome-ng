"""Pure helpers of the legacy takeover: parsing, filtering and legacy entry matching."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_registry import RegistryEntryDisabler
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.freeathome_ng.const import CONF_SWITCH_AS_X, CONF_USE_ROOM_NAMES, DOMAIN
from custom_components.freeathome_ng.migration import (
    _candidate_sysap_uuids,
    _extract_aliases,
    _extract_entity_options,
    _is_user_reason,
    _legacy_config_entries,
    _lookup_device,
    find_matching_legacy_entry,
    get_legacy_setup_defaults,
    parse_serialnumbers_text,
)

LEGACY = "freeathome"
DEFAULT_UUID = "00000000-0000-0000-0000-000000000000"


def _legacy(hass: HomeAssistant, unique_id: str | None, host: str, **data: Any) -> MockConfigEntry:
    entry = MockConfigEntry(domain=LEGACY, unique_id=unique_id, data={CONF_HOST: host, **data})
    entry.add_to_hass(hass)
    return entry


def test_parse_serialnumbers_text() -> None:
    """Serials are split on commas and whitespace, upper-cased and de-duplicated."""
    assert parse_serialnumbers_text(" abb1, ABB1\nabb2  abb3,,") == ["ABB1", "ABB2", "ABB3"]
    assert parse_serialnumbers_text("   ") == []


@pytest.mark.parametrize(
    ("reason", "expected"),
    [(None, False), (RegistryEntryDisabler.USER, True), ("integration", False), ("USER", True)],
)
def test_is_user_reason(reason: Any, expected: bool) -> None:
    """Only user-made disable/hide reasons are carried over."""
    assert _is_user_reason(reason) is expected


def test_extract_entity_options_and_aliases() -> None:
    """Legacy-only and default options are dropped; aliases need a real string."""
    assert _extract_entity_options(None) == {}
    assert _extract_entity_options(
        {
            LEGACY: {"x": 1},
            1: {"x": 1},
            "light": "junk",
            "sensor": {"suggested_display_precision": 2},
            "conversation": {"should_expose": True},
        }
    ) == {"conversation": {"should_expose": True}}
    assert _extract_aliases(None) is None
    assert _extract_aliases(["", None]) is None
    assert _extract_aliases(["Lamp", "Lamp", None]) == ["Lamp", None]


async def test_lookup_device_needs_entry(
    hass: HomeAssistant, device_registry: dr.DeviceRegistry
) -> None:
    """Device lookups without an owning entry find nothing."""
    assert _lookup_device(device_registry, LEGACY, "x", config_entry_id=None) is None
    assert _legacy_config_entries(None) == []


async def test_find_matching_legacy_entry(hass: HomeAssistant) -> None:
    """Legacy entries match by serial first, then host, then as the only one."""
    hub = MockConfigEntry(domain=DOMAIN, unique_id="abb700999999", data={CONF_HOST: "SysAP.local"})
    assert find_matching_legacy_entry(hass, hub) is None

    only = _legacy(hass, None, "other.local")
    assert find_matching_legacy_entry(hass, hub) is only

    by_host = _legacy(hass, None, "sysap.local")
    assert find_matching_legacy_entry(hass, hub) is by_host

    by_serial = _legacy(hass, "ABB700999999", "x.local")
    assert find_matching_legacy_entry(hass, hub) is by_serial

    stranger = MockConfigEntry(domain=DOMAIN, unique_id=None, data={CONF_HOST: "nowhere"})
    assert find_matching_legacy_entry(hass, stranger) is None


async def test_get_legacy_setup_defaults(hass: HomeAssistant) -> None:
    """Setup defaults are read from the legacy entry matching serial or host."""
    assert get_legacy_setup_defaults(hass, host="sysap.local") == {}

    _legacy(hass, "ABB700000001", "first.local", **{CONF_USE_ROOM_NAMES: 1})
    assert get_legacy_setup_defaults(hass) == {
        CONF_HOST: "first.local",
        CONF_USE_ROOM_NAMES: True,
    }
    _legacy(hass, "ABB700000002", "second.local", **{CONF_SWITCH_AS_X: 0})
    assert get_legacy_setup_defaults(hass) == {}
    assert get_legacy_setup_defaults(hass, serial_number="abb700000002") == {
        CONF_HOST: "second.local",
        CONF_SWITCH_AS_X: False,
    }
    assert get_legacy_setup_defaults(hass, serial_number="none", host="FIRST.local") == {
        CONF_HOST: "first.local",
        CONF_USE_ROOM_NAMES: True,
    }


def test_candidate_sysap_uuids() -> None:
    """SysAP UUIDs come from the controller, with the primary UUID as fallback."""

    def _hub(**controller: Any) -> Any:
        return SimpleNamespace(
            runtime_data=SimpleNamespace(controller=SimpleNamespace(**controller))
        )

    assert _candidate_sysap_uuids(SimpleNamespace()) == [DEFAULT_UUID]  # type: ignore[arg-type]
    assert _candidate_sysap_uuids(_hub(sysap_uuids=["a", "b"])) == ["a", "b"]
    assert _candidate_sysap_uuids(_hub(sysap_uuids=[], primary_sysap_uuid="p")) == ["p"]
    assert _candidate_sysap_uuids(_hub(sysap_uuids=[], primary_sysap_uuid="")) == [DEFAULT_UUID]
