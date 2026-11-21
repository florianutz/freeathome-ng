"""Tests for guided legacy `freeathome` -> `freeathome_ng` migration."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import freeathome_ng
import pytest
from freeathome_ng import FreeAtHomeNgRuntime, async_setup_entry, async_unload_entry
from freeathome_ng.const import (
    CONF_NAME_PREFIX,
    CONF_SWITCH_AS_X,
    CONF_USE_ROOM_NAMES,
    DOMAIN,
    LEGACY_DOMAIN,
    SERVICE_MIGRATE_FROM_LEGACY,
)
from freeathome_ng.migration import (
    ParsedLegacyUniqueId,
    async_migrate_from_legacy,
    get_legacy_setup_defaults,
    parse_legacy_unique_id,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_registry import (
    RegistryEntryDisabler,
    RegistryEntryHider,
)
from mock_sysap_server import MockSysApServer

SYSAP_UUID = "00000000-0000-0000-0000-000000000000"


@dataclass
class FakeDevice:
    """In-memory DeviceEntry test double."""

    id: str
    identifiers: set[tuple[str, str]]
    config_entries: set[str]
    name: str | None = None
    name_by_user: str | None = None
    area_id: str | None = None
    labels: set[str] = field(default_factory=set)


@dataclass
class FakeEntity:
    """In-memory RegistryEntry test double."""

    entity_id: str
    unique_id: str
    platform: str
    domain: str
    config_entry_id: str | None = None
    device_id: str | None = None
    name: str | None = None
    icon: str | None = None
    area_id: str | None = None
    aliases: set[Any] | None = None
    labels: set[str] = field(default_factory=set)
    disabled_by: Any = None
    hidden_by: Any = None
    options: dict[str, dict[str, Any]] = field(default_factory=dict)


class FakeDeviceRegistry:
    """Device registry test double supporting HA 2026.8+ lookup APIs."""

    def __init__(self, *, forbid_deprecated: bool = True) -> None:
        self.devices: dict[str, FakeDevice] = {}
        self.forbid_deprecated = forbid_deprecated
        self.updated_calls: list[tuple[str, dict[str, Any]]] = []
        self.lookup_calls: list[str] = []

    def add(self, dev: FakeDevice) -> None:
        self.devices[dev.id] = dev

    def async_get(self, device_id: str) -> FakeDevice | None:
        self.lookup_calls.append("async_get")
        return self.devices.get(device_id)

    def async_get_device_by_identifier(
        self,
        identifier: tuple[str, str],
        config_entry_id: str | None = None,
    ) -> FakeDevice | None:
        self.lookup_calls.append("async_get_device_by_identifier")
        for dev in self.devices.values():
            if identifier in dev.identifiers and (
                config_entry_id is None or config_entry_id in dev.config_entries
            ):
                return dev
        return None

    def async_get_devices(
        self,
        *,
        identifiers: set[tuple[str, str]] | None = None,
    ) -> list[FakeDevice]:
        self.lookup_calls.append("async_get_devices")
        if not identifiers:
            return []
        return [dev for dev in self.devices.values() if dev.identifiers & identifiers]

    def async_get_device(
        self,
        *,
        identifiers: set[tuple[str, str]] | None = None,
    ) -> FakeDevice | None:
        if self.forbid_deprecated:
            raise AssertionError("Deprecated async_get_device must not be called")
        self.lookup_calls.append("async_get_device")
        if not identifiers:
            return None
        for dev in self.devices.values():
            if dev.identifiers & identifiers:
                return dev
        return None

    def async_get_or_create(self, **kwargs: Any) -> FakeDevice:
        ident = next(iter(kwargs["identifiers"]))
        existing = self.async_get_device_by_identifier(ident, kwargs.get("config_entry_id"))
        if existing is not None:
            return existing
        dev = FakeDevice(
            id=f"dev_{len(self.devices) + 1}",
            identifiers=set(kwargs["identifiers"]),
            config_entries={kwargs["config_entry_id"]},
            name=kwargs.get("name"),
        )
        self.devices[dev.id] = dev
        return dev

    def async_update_device(self, device_id: str, **kwargs: Any) -> FakeDevice:
        dev = self.devices[device_id]
        for key, value in kwargs.items():
            setattr(dev, key, value)
        self.updated_calls.append((device_id, dict(kwargs)))
        return dev


class LegacyOnlyDeviceRegistry:
    """Minimal HA < 2026.8 device registry stub exposing only async_get_device."""

    def __init__(self, devices: list[FakeDevice]) -> None:
        self._devices = devices
        self.updated_calls: list[tuple[str, dict[str, Any]]] = []

    def async_get_device(
        self, *, identifiers: set[tuple[str, str]] | None = None
    ) -> FakeDevice | None:
        if not identifiers:
            return None
        return next(
            (dev for dev in self._devices if dev.identifiers & identifiers),
            None,
        )

    def async_update_device(self, device_id: str, **kwargs: Any) -> FakeDevice:
        dev = next(d for d in self._devices if d.id == device_id)
        for key, value in kwargs.items():
            setattr(dev, key, value)
        self.updated_calls.append((device_id, dict(kwargs)))
        return dev


class FakeEntityRegistry:
    """In-memory EntityRegistry tracking call order for rename + post-rename options."""

    def __init__(self) -> None:
        self.entities: dict[str, FakeEntity] = {}
        self.operations: list[tuple[str, str, Any]] = []

    def add(self, ent: FakeEntity) -> None:
        self.entities[ent.entity_id] = ent

    def async_remove(self, entity_id: str) -> None:
        self.entities.pop(entity_id, None)
        self.operations.append(("remove", entity_id, None))

    def async_update_entity(self, entity_id: str, **kwargs: Any) -> FakeEntity:
        ent = self.entities[entity_id]
        new_eid = kwargs.pop("new_entity_id", None)
        for key, value in kwargs.items():
            setattr(ent, key, value)
        if new_eid and new_eid != entity_id:
            if new_eid in self.entities:
                raise ValueError(f"Entity id {new_eid} is already registered")
            del self.entities[entity_id]
            ent.entity_id = new_eid
            self.entities[new_eid] = ent
        self.operations.append(("update_entity", ent.entity_id, kwargs))
        return ent

    def async_update_entity_options(
        self, entity_id: str, opt_domain: str, opt_values: dict[str, Any]
    ) -> None:
        if entity_id not in self.entities:
            raise AssertionError(f"Missing entity_id {entity_id} during options update")
        self.entities[entity_id].options[opt_domain] = dict(opt_values)
        self.operations.append(("update_options", entity_id, opt_domain))


def _make_fake_hass(
    *,
    legacy_entries: list[SimpleNamespace],
    hub_entry: SimpleNamespace,
    dev_reg: FakeDeviceRegistry,
    ent_reg: FakeEntityRegistry,
) -> tuple[SimpleNamespace, list[str]]:
    removed_entries: list[str] = []
    all_entries = [*legacy_entries, hub_entry]

    def _async_entries(domain: str | None = None) -> list[SimpleNamespace]:
        if domain is None:
            return list(all_entries)
        return [e for e in all_entries if getattr(e, "domain", None) == domain]

    async def _async_remove(entry_id: str) -> None:
        removed_entries.append(entry_id)
        all_entries[:] = [e for e in all_entries if e.entry_id != entry_id]
        # Emulate HA cascading removal of entities & devices bound to removed entry.
        for eid in [k for k, v in ent_reg.entities.items() if v.config_entry_id == entry_id]:
            del ent_reg.entities[eid]
        for dev in dev_reg.devices.values():
            dev.config_entries.discard(entry_id)

    hass = SimpleNamespace(
        config_entries=SimpleNamespace(
            async_entries=_async_entries,
            async_remove=_async_remove,
        ),
        device_registry=dev_reg,
        entity_registry=ent_reg,
        data={},
    )
    return hass, removed_entries


def _build_fixture_env(
    *,
    ng_switch_as_x: bool = True,
    legacy_switch_as_x: bool = True,
    name_prefix: str = "",
) -> tuple[
    SimpleNamespace,
    SimpleNamespace,
    SimpleNamespace,
    FakeDeviceRegistry,
    FakeEntityRegistry,
    list[str],
]:
    dev_reg = FakeDeviceRegistry()
    ent_reg = FakeEntityRegistry()

    legacy_entry = SimpleNamespace(
        entry_id="leg_entry_1",
        domain=LEGACY_DOMAIN,
        title="192.168.8.23",
        unique_id="ABB700D86147",
        data={
            CONF_HOST: "192.168.8.23",
            CONF_USE_ROOM_NAMES: False,
            CONF_SWITCH_AS_X: legacy_switch_as_x,
        },
        options={},
    )
    hub_entry = SimpleNamespace(
        entry_id="ng_hub_1",
        domain=DOMAIN,
        title="SysAP NG",
        unique_id="ABB700D86147",
        data={
            CONF_HOST: "192.168.8.23",
            CONF_USE_ROOM_NAMES: False,
            CONF_SWITCH_AS_X: ng_switch_as_x,
            CONF_NAME_PREFIX: name_prefix,
        },
        options={},
        runtime_data=FreeAtHomeNgRuntime(
            controller=SimpleNamespace(
                sysap_uuids=[SYSAP_UUID],
                primary_sysap_uuid=SYSAP_UUID,
                sysap_serial="ABB700D86147",
                client=SimpleNamespace(host="192.168.8.23"),
            ),  # type: ignore[arg-type]
            entry=None,  # type: ignore[arg-type]
        ),
    )
    hub_entry.runtime_data.entry = hub_entry

    # Legacy devices + matching NG devices
    dev_reg.add(
        FakeDevice(
            id="leg_dev_switch",
            identifiers={(LEGACY_DOMAIN, "ABB700DA1DDF")},
            config_entries={"leg_entry_1"},
            name="Bad Doppeltaster",
            name_by_user="Mein Bad Doppeltaster",
            area_id="bad",
            labels={"licht", "bad"},
        )
    )
    dev_reg.add(
        FakeDevice(
            id="ng_dev_switch",
            identifiers={(DOMAIN, f"{SYSAP_UUID}_ABB700DA1DDF")},
            config_entries={"ng_hub_1"},
            name="Bad Doppeltaster (ABB700DA1DDF)",
            labels={"ng"},
        )
    )
    dev_reg.add(
        FakeDevice(
            id="leg_dev_rt",
            identifiers={(LEGACY_DOMAIN, "ABB700DB3F2C")},
            config_entries={"leg_entry_1"},
            name="Bad RTRegler",
            area_id="bad",
        )
    )
    dev_reg.add(
        FakeDevice(
            id="ng_dev_rt",
            identifiers={(DOMAIN, f"{SYSAP_UUID}_ABB700DB3F2C")},
            config_entries={"ng_hub_1"},
            name="Bad RTRegler (ABB700DB3F2C)",
        )
    )

    # Legacy entities (switch, dimmer status, climate, thermostat temp, scene, multi-sensor)
    ent_reg.add(
        FakeEntity(
            entity_id="switch.bad_deckenlicht",
            unique_id="ABB700DA1DDF/ch0006",
            platform=LEGACY_DOMAIN,
            domain="switch",
            config_entry_id="leg_entry_1",
            device_id="leg_dev_switch",
            name="Deckenlicht Custom",
            icon="mdi:ceiling-light",
            area_id="bad",
            aliases={"Bad Licht", None},
            labels={"wichtig"},
            options={
                "conversation": {"should_expose": True},
                "cloud.google_assistant": {"should_expose": False},
                LEGACY_DOMAIN: {"ignored": True},
            },
        )
    )
    ent_reg.add(
        FakeEntity(
            entity_id="sensor.bad_dimming_status",
            unique_id="ABB700DA1DDF/ch0000/dimming_status",
            platform=LEGACY_DOMAIN,
            domain="sensor",
            config_entry_id="leg_entry_1",
            device_id="leg_dev_switch",
            disabled_by=RegistryEntryDisabler.USER,
            hidden_by=RegistryEntryHider.USER,
            aliases={None},
        )
    )
    ent_reg.add(
        FakeEntity(
            entity_id="sensor.bad_rt_temp",
            unique_id="ABB700DB3F2C/ch0000/current_temperature",
            platform=LEGACY_DOMAIN,
            domain="sensor",
            config_entry_id="leg_entry_1",
            device_id="leg_dev_rt",
            disabled_by=RegistryEntryDisabler.INTEGRATION,
            hidden_by=RegistryEntryHider.INTEGRATION,
            options={
                "sensor": {"suggested_display_precision": 1, "display_precision": 2},
                "conversation": {"should_expose": True},
            },
        )
    )
    ent_reg.add(
        FakeEntity(
            entity_id="scene.abdunkeln",
            unique_id="ABB700D86147/FFFF48000002/ch0000",
            platform=LEGACY_DOMAIN,
            domain="scene",
            config_entry_id="leg_entry_1",
            options={"conversation": {"should_expose": True}},
        )
    )
    ent_reg.add(
        FakeEntity(
            entity_id="sensor.living_co2",
            unique_id="ABB700D10007/ch0000/odp0001",
            platform=LEGACY_DOMAIN,
            domain="sensor",
            config_entry_id="leg_entry_1",
            options={"sensor": {"suggested_display_precision": 0}},
        )
    )

    # Matching NG entities
    ng_switch_domain = "switch" if ng_switch_as_x else "light"
    ent_reg.add(
        FakeEntity(
            entity_id=f"{ng_switch_domain}.ng_bad_deckenlicht",
            unique_id=f"{SYSAP_UUID}/ABB700DA1DDF/ch0006",
            platform=DOMAIN,
            domain=ng_switch_domain,
            config_entry_id="ng_hub_1",
            device_id="ng_dev_switch",
            labels={"existing_ng"},
        )
    )
    ent_reg.add(
        FakeEntity(
            entity_id="sensor.ng_bad_dimming_status",
            unique_id=f"{SYSAP_UUID}/ABB700DA1DDF/ch0000/dimming_status",
            platform=DOMAIN,
            domain="sensor",
            config_entry_id="ng_hub_1",
            device_id="ng_dev_switch",
        )
    )
    ent_reg.add(
        FakeEntity(
            entity_id="sensor.ng_bad_rt_temp",
            unique_id=f"{SYSAP_UUID}/ABB700DB3F2C/ch0000/current_temperature",
            platform=DOMAIN,
            domain="sensor",
            config_entry_id="ng_hub_1",
            device_id="ng_dev_rt",
        )
    )
    ent_reg.add(
        FakeEntity(
            entity_id="scene.ng_abdunkeln",
            unique_id=f"{SYSAP_UUID}/FFFF48000002/ch0000",
            platform=DOMAIN,
            domain="scene",
            config_entry_id="ng_hub_1",
        )
    )
    ent_reg.add(
        FakeEntity(
            entity_id="sensor.ng_living_co2",
            unique_id=f"{SYSAP_UUID}/ABB700D10007/ch0000/odp0001",
            platform=DOMAIN,
            domain="sensor",
            config_entry_id="ng_hub_1",
        )
    )

    # Helper entities that must remain completely untouched
    ent_reg.add(
        FakeEntity(
            entity_id="light.bad_deckenlicht",
            unique_id="helper_switch_as_x_1",
            platform="switch_as_x",
            domain="light",
            device_id="leg_dev_switch",
        )
    )
    ent_reg.add(
        FakeEntity(
            entity_id="sensor.bad_heizbedarf_heute",
            unique_id="helper_utility_1",
            platform="utility_meter",
            domain="sensor",
            device_id="leg_dev_rt",
        )
    )

    hass, removed = _make_fake_hass(
        legacy_entries=[legacy_entry],
        hub_entry=hub_entry,
        dev_reg=dev_reg,
        ent_reg=ent_reg,
    )
    return hass, hub_entry, legacy_entry, dev_reg, ent_reg, removed


def test_parse_legacy_unique_id_formats() -> None:
    """Verify parsing of hardware, suffix, multi-sensor, and SysAP-prefixed IDs."""
    assert parse_legacy_unique_id("ABB700DA1DDF/ch0006") == ParsedLegacyUniqueId(
        serialnumber="ABB700DA1DDF", channel_id="ch0006", suffix=""
    )
    assert parse_legacy_unique_id("ABB700DA1DDF/ch0000/dimming_status") == ParsedLegacyUniqueId(
        serialnumber="ABB700DA1DDF",
        channel_id="ch0000",
        suffix="/dimming_status",
    )
    assert parse_legacy_unique_id(
        "ABB700DB3F2C/ch0000/current_temperature"
    ) == ParsedLegacyUniqueId(
        serialnumber="ABB700DB3F2C",
        channel_id="ch0000",
        suffix="/current_temperature",
    )
    assert parse_legacy_unique_id("ABB700D10007/ch0000/odp0001") == ParsedLegacyUniqueId(
        serialnumber="ABB700D10007",
        channel_id="ch0000",
        suffix="/odp0001",
    )
    assert parse_legacy_unique_id("ABB700D86147/FFFF48000002/ch0000") == ParsedLegacyUniqueId(
        serialnumber="FFFF48000002",
        channel_id="ch0000",
        suffix="",
        sysap_prefix="ABB700D86147",
    )
    assert parse_legacy_unique_id("FFFF48000002/ch0000") == ParsedLegacyUniqueId(
        serialnumber="FFFF48000002", channel_id="ch0000", suffix=""
    )
    assert parse_legacy_unique_id("invalid_unique_id") is None
    assert parse_legacy_unique_id("ABB700DA1DDF/bad_channel") is None


async def test_dry_run_preview_non_destructive() -> None:
    """Verify dry_run=True performs zero writes and surfaces mismatch/prefix warnings."""
    hass, hub_entry, _, dev_reg, ent_reg, removed = _build_fixture_env(
        ng_switch_as_x=False,
        legacy_switch_as_x=True,
        name_prefix="NG ",
    )
    # Add an unrecognized legacy unique_id
    ent_reg.add(
        FakeEntity(
            entity_id="sensor.bad_unparsed",
            unique_id="corrupt_uid",
            platform=LEGACY_DOMAIN,
            domain="sensor",
            config_entry_id="leg_entry_1",
        )
    )

    result = await async_migrate_from_legacy(hass, hub_entry, dry_run=True, cutover=True)

    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["cutover"] is True
    assert removed == []
    assert dev_reg.updated_calls == []
    assert ent_reg.operations == []

    summary = result["summary"]
    assert summary["discovered_legacy_devices"] == 2
    assert summary["discovered_legacy_entities"] == 5
    assert summary["same_domain_entities"] == 4
    assert summary["domain_changed_entities"] == 1
    assert summary["skipped_entities"] == 1
    assert summary["conflicts"] == 0
    assert summary["legacy_entries_to_remove"] == 1

    assert result["domain_changed_entities"][0]["legacy_domain"] == "switch"
    assert result["domain_changed_entities"][0]["ng_domain"] == "light"
    assert any("name_prefix" in w for w in result["warnings"])
    assert any("switch_as_x mismatch" in w for w in result["warnings"])
    assert any("freeathome_ng_event" in w for w in result["warnings"])


async def test_side_by_side_metadata_sync() -> None:
    """Verify cutover=False transfers metadata and Assist options while preserving legacy."""
    hass, hub_entry, legacy_entry, dev_reg, ent_reg, removed = _build_fixture_env()

    result = await async_migrate_from_legacy(hass, hub_entry, dry_run=False, cutover=False)

    assert result["success"] is True
    assert removed == []
    assert legacy_entry in hass.config_entries.async_entries(LEGACY_DOMAIN)

    # Device metadata merged cleanly
    ng_dev = dev_reg.devices["ng_dev_switch"]
    assert ng_dev.name_by_user == "Mein Bad Doppeltaster"
    assert ng_dev.area_id == "bad"
    assert ng_dev.labels == {"ng", "licht", "bad"}

    # Entity metadata & options copied onto NG entity ID without renaming
    ng_sw = ent_reg.entities["switch.ng_bad_deckenlicht"]
    assert ng_sw.name == "Deckenlicht Custom"
    assert ng_sw.icon == "mdi:ceiling-light"
    assert ng_sw.area_id == "bad"
    assert ng_sw.aliases == {"Bad Licht", None}
    assert ng_sw.labels == {"existing_ng", "wichtig"}
    assert ng_sw.options == {
        "conversation": {"should_expose": True},
        "cloud.google_assistant": {"should_expose": False},
    }

    # User-only disablers/hiders copied; integration disablers/hiders NOT copied; [None] aliases skipped
    ng_dim = ent_reg.entities["sensor.ng_bad_dimming_status"]
    assert ng_dim.disabled_by == RegistryEntryDisabler.USER
    assert ng_dim.hidden_by == RegistryEntryHider.USER
    assert ng_dim.aliases is None

    ng_temp = ent_reg.entities["sensor.ng_bad_rt_temp"]
    assert ng_temp.disabled_by is None
    assert ng_temp.hidden_by is None
    assert ng_temp.options == {
        "sensor": {"display_precision": 2},
        "conversation": {"should_expose": True},
    }


async def test_full_cutover_preserves_entity_ids_history_and_helpers() -> None:
    """Verify cutover=True removes legacy, renames same-domain IDs, and handles conflicts."""
    hass, hub_entry, _, _, ent_reg, removed = _build_fixture_env()

    # Add an orphaned legacy entity
    ent_reg.add(
        FakeEntity(
            entity_id="sensor.orphaned_co2",
            unique_id="ABB700D10007/ch0000/odp0001",
            platform=LEGACY_DOMAIN,
            domain="sensor",
            config_entry_id=None,
        )
    )

    # Simulate a third-party entity reclaiming sensor.bad_rt_temp immediately after removal
    orig_remove = hass.config_entries.async_remove

    async def _remove_with_reclaim(entry_id: str) -> None:
        await orig_remove(entry_id)
        ent_reg.add(
            FakeEntity(
                entity_id="sensor.bad_rt_temp",
                unique_id="other_rt_temp",
                platform="other_integration",
                domain="sensor",
                config_entry_id="other_entry",
            )
        )

    hass.config_entries.async_remove = _remove_with_reclaim

    result = await async_migrate_from_legacy(hass, hub_entry, dry_run=False, cutover=True)

    assert result["success"] is True
    assert removed == ["leg_entry_1"]
    assert hub_entry.runtime_data.suppress_reload is False

    # Same-domain NG entities now occupy original legacy entity_ids
    assert "switch.bad_deckenlicht" in ent_reg.entities
    assert ent_reg.entities["switch.bad_deckenlicht"].platform == DOMAIN
    assert "switch.ng_bad_deckenlicht" not in ent_reg.entities

    assert "scene.abdunkeln" in ent_reg.entities
    assert ent_reg.entities["scene.abdunkeln"].platform == DOMAIN
    assert ent_reg.entities["scene.abdunkeln"].options == {"conversation": {"should_expose": True}}

    # Conflicting sensor.bad_rt_temp kept NG entity_id while still receiving options
    assert result["summary"]["conflicts"] == 1
    assert result["conflicts"][0]["entity_id"] == "sensor.bad_rt_temp"
    assert ent_reg.entities["sensor.ng_bad_rt_temp"].options["sensor"] == {"display_precision": 2}

    # Verify options update happened AFTER rename onto final_entity_id
    sw_ops = [op for op in ent_reg.operations if op[1] == "switch.bad_deckenlicht"]
    assert [op[0] for op in sw_ops] == [
        "update_entity",
        "update_options",
        "update_options",
    ]

    # Downstream helpers untouched
    assert ent_reg.entities["light.bad_deckenlicht"].platform == "switch_as_x"
    assert ent_reg.entities["sensor.bad_heizbedarf_heute"].platform == "utility_meter"


async def test_cutover_aborts_safely_when_no_matching_ng_entities() -> None:
    """Verify legacy entry is never removed if zero NG entities matched."""
    hass, hub_entry, legacy_entry, _, ent_reg, removed = _build_fixture_env()
    for eid in [k for k, v in ent_reg.entities.items() if v.platform == DOMAIN]:
        del ent_reg.entities[eid]

    result = await async_migrate_from_legacy(hass, hub_entry, dry_run=False, cutover=True)

    assert result["success"] is False
    assert removed == []
    assert legacy_entry in hass.config_entries.async_entries(LEGACY_DOMAIN)
    assert any("zero matching freeathome_ng entities" in w for w in result["warnings"])


async def test_selective_serialnumbers_filter_and_partial_cutover_guard() -> None:
    """Verify serialnumbers filter scopes dry_run/sync and rejects cutover=True."""
    hass, hub_entry, _, dev_reg, ent_reg, removed = _build_fixture_env()

    preview = await async_migrate_from_legacy(
        hass,
        hub_entry,
        dry_run=True,
        cutover=False,
        serialnumbers_filter={"abb700da1ddf", "MISSING01"},
    )
    assert preview["summary"]["discovered_legacy_devices"] == 1
    assert preview["summary"]["discovered_legacy_entities"] == 2
    assert any("MISSING01" in w for w in preview["warnings"])

    synced = await async_migrate_from_legacy(
        hass,
        hub_entry,
        dry_run=False,
        cutover=False,
        serialnumbers_filter={"ABB700DA1DDF"},
    )
    assert synced["summary"]["same_domain_entities_migrated"] == 2
    assert dev_reg.devices["ng_dev_switch"].area_id == "bad"
    assert dev_reg.devices["ng_dev_rt"].area_id is None
    assert ent_reg.entities["sensor.ng_bad_rt_temp"].options == {}

    with pytest.raises(ServiceValidationError):
        await async_migrate_from_legacy(
            hass,
            hub_entry,
            dry_run=False,
            cutover=True,
            serialnumbers_filter={"ABB700DA1DDF"},
        )
    assert removed == []


async def test_device_lookup_avoids_deprecated_async_get_device() -> None:
    """Verify HA 2026.8+ lookup uses async_get_device_by_identifier and HA < 2026.8 fallback works."""
    hass, hub_entry, _, dev_reg, _, _ = _build_fixture_env()

    result = await async_migrate_from_legacy(hass, hub_entry, dry_run=False, cutover=False)
    assert result["summary"]["device_metadata_updates"] == 2
    assert "async_get_device_by_identifier" in dev_reg.lookup_calls

    # HA < 2026.8 fallback test when only async_get_device exists
    legacy_only_reg = LegacyOnlyDeviceRegistry(list(dev_reg.devices.values()))
    legacy_only_reg._devices[1].name_by_user = None
    legacy_only_reg._devices[1].area_id = None
    hass.device_registry = legacy_only_reg

    fallback_res = await async_migrate_from_legacy(hass, hub_entry, dry_run=False, cutover=False)
    assert fallback_res["summary"]["device_metadata_updates"] == 2
    assert len(legacy_only_reg.updated_calls) == 2


async def test_migrate_service_multi_hub_and_legacy_flow_defaults() -> None:
    """Verify service registration, multi-hub disambiguation, and config_flow defaults."""
    server = MockSysApServer(port=0)
    await server.start()
    try:
        registered_services: dict[str, dict[str, Any]] = {}

        def _register_svc(domain, name, handler, schema=None, supports_response=None):
            registered_services[f"{domain}.{name}"] = {
                "handler": handler,
                "schema": schema,
                "supports_response": supports_response,
            }

        legacy_entry = SimpleNamespace(
            entry_id="leg_1",
            domain=LEGACY_DOMAIN,
            unique_id="ABB700999999",
            data={
                CONF_HOST: "192.168.8.23",
                CONF_USE_ROOM_NAMES: True,
                CONF_SWITCH_AS_X: False,
            },
        )
        entry1 = SimpleNamespace(
            entry_id="entry_1",
            domain=DOMAIN,
            title="SysAP 1",
            unique_id="ABB700999999",
            data={
                CONF_HOST: server.host_port,
                CONF_USERNAME: "apiuser",
                CONF_PASSWORD: "secret",
            },
            options={},
            runtime_data=None,
            async_on_unload=lambda _cb: None,
            add_update_listener=lambda _cb: lambda: None,
            async_start_reauth=lambda _h: None,
        )

        hass = SimpleNamespace(
            data={},
            device_registry=FakeDeviceRegistry(),
            entity_registry=FakeEntityRegistry(),
            config_entries=SimpleNamespace(
                async_entries=lambda d=None: [legacy_entry] if d == LEGACY_DOMAIN else [],
                async_forward_entry_setups=lambda *_a, **_kw: __import__("asyncio").sleep(0),
                async_unload_platforms=lambda *_a, **_kw: __import__("asyncio").sleep(
                    0, result=True
                ),
                async_schedule_reload=lambda _id: None,
                async_update_entry=lambda *_a, **_kw: None,
            ),
            services=SimpleNamespace(
                async_register=_register_svc,
                has_service=lambda dom, name: f"{dom}.{name}" in registered_services,
                async_remove=lambda dom, name: registered_services.pop(f"{dom}.{name}", None),
            ),
            bus=SimpleNamespace(
                async_listen_once=lambda *_a, **_kw: lambda: None,
                async_fire=lambda *_a, **_kw: None,
            ),
            config=SimpleNamespace(path=lambda p: p),
        )

        assert get_legacy_setup_defaults(hass) == {
            CONF_HOST: "192.168.8.23",
            CONF_USE_ROOM_NAMES: True,
            CONF_SWITCH_AS_X: False,
        }

        await async_setup_entry(hass, entry1)  # type: ignore[arg-type]
        svc_key = f"{DOMAIN}.{SERVICE_MIGRATE_FROM_LEGACY}"
        assert svc_key in registered_services
        assert registered_services[svc_key]["supports_response"] == SupportsResponse.ONLY

        # Simulate a second loaded hub -> omitting entry_id/host must raise ServiceValidationError
        entry2 = SimpleNamespace(
            entry_id="entry_2",
            runtime_data=SimpleNamespace(
                controller=SimpleNamespace(client=SimpleNamespace(host="10.0.0.2"))
            ),
        )
        hass.data[DOMAIN]["loaded_entries"]["entry_2"] = entry2

        handler = registered_services[svc_key]["handler"]
        with pytest.raises(ServiceValidationError):
            await handler(SimpleNamespace(data={"dry_run": True}))

        res = await handler(SimpleNamespace(data={"entry_id": "entry_1", "dry_run": True}))
        assert res["success"] is True
        assert res["hub_entry_id"] == "entry_1"

        hass.data[DOMAIN]["loaded_entries"].pop("entry_2", None)
        assert await async_unload_entry(hass, entry1) is True  # type: ignore[arg-type]
        assert svc_key not in registered_services
        assert freeathome_ng.PLATFORMS
    finally:
        await server.stop()
