"""Tests for guided legacy `freeathome` -> `freeathome_ng` migration (real HA registries)."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from homeassistant.helpers.entity_registry import (
    COMPUTED_NAME,
    RegistryEntryDisabler,
    RegistryEntryHider,
)
from mock_sysap_server import MockSysApServer
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.freeathome_ng import FreeAtHomeNgRuntime
from custom_components.freeathome_ng.const import (
    CONF_NAME_PREFIX,
    CONF_SWITCH_AS_X,
    CONF_USE_ROOM_NAMES,
    DOMAIN,
    LEGACY_DOMAIN,
    SERVICE_MIGRATE_FROM_LEGACY,
)
from custom_components.freeathome_ng.migration import (
    ParsedLegacyUniqueId,
    async_migrate_from_legacy,
    get_legacy_setup_defaults,
    parse_legacy_unique_id,
)

from .conftest import entry_data

SYSAP_UUID = "00000000-0000-0000-0000-000000000000"
LEGACY_SERIAL = "ABB700D86147"


@dataclass
class Env:
    """Registries and entries of one migration scenario."""

    hub_entry: MockConfigEntry
    legacy_entry: MockConfigEntry
    dev_reg: dr.DeviceRegistry
    ent_reg: er.EntityRegistry
    devices: dict[str, str]  # key -> device_id


def _entity(
    ent_reg: er.EntityRegistry,
    *,
    entity_id: str,
    unique_id: str,
    platform: str,
    config_entry: MockConfigEntry | None = None,
    device_id: str | None = None,
    options: dict[str, dict[str, Any]] | None = None,
    **updates: Any,
) -> str:
    domain, object_id = entity_id.split(".", 1)
    entry = ent_reg.async_get_or_create(
        domain,
        platform,
        unique_id,
        config_entry=config_entry,
        device_id=device_id,
        suggested_object_id=object_id,
    )
    assert entry.entity_id == entity_id
    if updates:
        ent_reg.async_update_entity(entity_id, **updates)
    for opt_domain, values in (options or {}).items():
        ent_reg.async_update_entity_options(entity_id, opt_domain, values)
    return entity_id


def _build_env(
    hass: HomeAssistant,
    *,
    ng_switch_as_x: bool = True,
    legacy_switch_as_x: bool = True,
    name_prefix: str = "",
) -> Env:
    """Create a legacy entry, an NG hub entry and matching registry content."""
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    area_reg = ar.async_get(hass)
    label_reg = lr.async_get(hass)
    area_reg.async_create("bad")
    for label in ("licht", "bad", "ng", "wichtig", "existing_ng"):
        label_reg.async_create(label)

    legacy_entry = MockConfigEntry(
        domain=LEGACY_DOMAIN,
        title="192.168.8.23",
        unique_id=LEGACY_SERIAL,
        data={
            CONF_HOST: "192.168.8.23",
            CONF_USE_ROOM_NAMES: False,
            CONF_SWITCH_AS_X: legacy_switch_as_x,
        },
    )
    legacy_entry.add_to_hass(hass)
    hub_entry = MockConfigEntry(
        domain=DOMAIN,
        title="SysAP NG",
        unique_id=LEGACY_SERIAL,
        data={
            CONF_HOST: "192.168.8.23",
            CONF_USE_ROOM_NAMES: False,
            CONF_SWITCH_AS_X: ng_switch_as_x,
            CONF_NAME_PREFIX: name_prefix,
        },
    )
    hub_entry.add_to_hass(hass)
    hub_entry.runtime_data = FreeAtHomeNgRuntime(
        controller=SimpleNamespace(  # type: ignore[arg-type]
            sysap_uuids=[SYSAP_UUID],
            primary_sysap_uuid=SYSAP_UUID,
            sysap_serial=LEGACY_SERIAL,
            client=SimpleNamespace(host="192.168.8.23"),
        ),
        entry=hub_entry,
    )

    def _device(entry: MockConfigEntry, identifier: tuple[str, str], **kw: Any) -> str:
        name_by_user = kw.pop("name_by_user", None)
        area_id = kw.pop("area_id", None)
        labels = kw.pop("labels", None)
        device = dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={identifier}, **kw
        )
        dev_reg.async_update_device(
            device.id,
            name_by_user=name_by_user,
            area_id=area_id,
            labels=labels or set(),
        )
        return device.id

    devices = {
        "leg_switch": _device(
            legacy_entry,
            (LEGACY_DOMAIN, "ABB700DA1DDF"),
            name="Bad Doppeltaster",
            name_by_user="Mein Bad Doppeltaster",
            area_id="bad",
            labels={"licht", "bad"},
        ),
        "ng_switch": _device(
            hub_entry,
            (DOMAIN, f"{SYSAP_UUID}_ABB700DA1DDF"),
            name="Bad Doppeltaster (ABB700DA1DDF)",
            labels={"ng"},
        ),
        "leg_rt": _device(
            legacy_entry, (LEGACY_DOMAIN, "ABB700DB3F2C"), name="Bad RTRegler", area_id="bad"
        ),
        "ng_rt": _device(
            hub_entry, (DOMAIN, f"{SYSAP_UUID}_ABB700DB3F2C"), name="Bad RTRegler (ABB700DB3F2C)"
        ),
    }

    # Legacy entities (switch, dimmer status, thermostat temperature, scene, multi-sensor)
    _entity(
        ent_reg,
        entity_id="switch.bad_deckenlicht",
        unique_id="ABB700DA1DDF/ch0006",
        platform=LEGACY_DOMAIN,
        config_entry=legacy_entry,
        device_id=devices["leg_switch"],
        name="Deckenlicht Custom",
        icon="mdi:ceiling-light",
        area_id="bad",
        aliases=["Bad Licht", COMPUTED_NAME],
        labels={"wichtig"},
        options={
            "conversation": {"should_expose": True},
            "cloud.google_assistant": {"should_expose": False},
            LEGACY_DOMAIN: {"ignored": True},
        },
    )
    _entity(
        ent_reg,
        entity_id="sensor.bad_dimming_status",
        unique_id="ABB700DA1DDF/ch0000/dimming_status",
        platform=LEGACY_DOMAIN,
        config_entry=legacy_entry,
        device_id=devices["leg_switch"],
        disabled_by=RegistryEntryDisabler.USER,
        hidden_by=RegistryEntryHider.USER,
        aliases=[COMPUTED_NAME],
    )
    _entity(
        ent_reg,
        entity_id="sensor.bad_rt_temp",
        unique_id="ABB700DB3F2C/ch0000/current_temperature",
        platform=LEGACY_DOMAIN,
        config_entry=legacy_entry,
        device_id=devices["leg_rt"],
        disabled_by=RegistryEntryDisabler.INTEGRATION,
        hidden_by=RegistryEntryHider.INTEGRATION,
        options={
            "sensor": {"suggested_display_precision": 1, "display_precision": 2},
            "conversation": {"should_expose": True},
        },
    )
    _entity(
        ent_reg,
        entity_id="scene.abdunkeln",
        unique_id=f"{LEGACY_SERIAL}/FFFF48000002/ch0000",
        platform=LEGACY_DOMAIN,
        config_entry=legacy_entry,
        options={"conversation": {"should_expose": True}},
    )
    _entity(
        ent_reg,
        entity_id="sensor.living_co2",
        unique_id="ABB700D10007/ch0000/odp0001",
        platform=LEGACY_DOMAIN,
        config_entry=legacy_entry,
        options={"sensor": {"suggested_display_precision": 0}},
    )

    # Matching NG entities
    ng_switch_domain = "switch" if ng_switch_as_x else "light"
    _entity(
        ent_reg,
        entity_id=f"{ng_switch_domain}.ng_bad_deckenlicht",
        unique_id=f"{SYSAP_UUID}/ABB700DA1DDF/ch0006",
        platform=DOMAIN,
        config_entry=hub_entry,
        device_id=devices["ng_switch"],
        labels={"existing_ng"},
    )
    _entity(
        ent_reg,
        entity_id="sensor.ng_bad_dimming_status",
        unique_id=f"{SYSAP_UUID}/ABB700DA1DDF/ch0000/dimming_status",
        platform=DOMAIN,
        config_entry=hub_entry,
        device_id=devices["ng_switch"],
    )
    _entity(
        ent_reg,
        entity_id="sensor.ng_bad_rt_temp",
        unique_id=f"{SYSAP_UUID}/ABB700DB3F2C/ch0000/current_temperature",
        platform=DOMAIN,
        config_entry=hub_entry,
        device_id=devices["ng_rt"],
    )
    _entity(
        ent_reg,
        entity_id="scene.ng_abdunkeln",
        unique_id=f"{SYSAP_UUID}/FFFF48000002/ch0000",
        platform=DOMAIN,
        config_entry=hub_entry,
    )
    _entity(
        ent_reg,
        entity_id="sensor.ng_living_co2",
        unique_id=f"{SYSAP_UUID}/ABB700D10007/ch0000/odp0001",
        platform=DOMAIN,
        config_entry=hub_entry,
    )

    # Helper entities that must remain completely untouched
    _entity(
        ent_reg,
        entity_id="light.bad_deckenlicht",
        unique_id="helper_switch_as_x_1",
        platform="switch_as_x",
        device_id=devices["leg_switch"],
    )
    _entity(
        ent_reg,
        entity_id="sensor.bad_heizbedarf_heute",
        unique_id="helper_utility_1",
        platform="utility_meter",
        device_id=devices["leg_rt"],
    )

    return Env(hub_entry, legacy_entry, dev_reg, ent_reg, devices)


def _legacy_entries(hass: HomeAssistant) -> list[str]:
    return [e.entry_id for e in hass.config_entries.async_entries(LEGACY_DOMAIN)]


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


async def test_dry_run_preview_non_destructive(hass: HomeAssistant) -> None:
    """dry_run=True performs zero writes and surfaces mismatch/prefix warnings."""
    env = _build_env(hass, ng_switch_as_x=False, legacy_switch_as_x=True, name_prefix="NG ")
    _entity(
        env.ent_reg,
        entity_id="sensor.bad_unparsed",
        unique_id="corrupt_uid",
        platform=LEGACY_DOMAIN,
        config_entry=env.legacy_entry,
    )
    devices_before = {d.id: d for d in env.dev_reg.devices}
    entities_before = {e.entity_id: e for e in env.ent_reg.entities.values()}

    result = await async_migrate_from_legacy(hass, env.hub_entry, dry_run=True, cutover=True)

    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["cutover"] is True
    assert _legacy_entries(hass) == [env.legacy_entry.entry_id]
    assert {d.id: d for d in env.dev_reg.devices} == devices_before
    assert {e.entity_id: e for e in env.ent_reg.entities.values()} == entities_before

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


async def test_side_by_side_metadata_sync(hass: HomeAssistant) -> None:
    """cutover=False transfers metadata and Assist options while preserving legacy."""
    env = _build_env(hass)

    result = await async_migrate_from_legacy(hass, env.hub_entry, dry_run=False, cutover=False)

    assert result["success"] is True
    assert _legacy_entries(hass) == [env.legacy_entry.entry_id]

    ng_dev = env.dev_reg.async_get(env.devices["ng_switch"])
    assert ng_dev is not None
    assert ng_dev.name_by_user == "Mein Bad Doppeltaster"
    assert ng_dev.area_id == "bad"
    assert ng_dev.labels == {"ng", "licht", "bad"}

    ng_sw = env.ent_reg.async_get("switch.ng_bad_deckenlicht")
    assert ng_sw is not None
    assert ng_sw.name == "Deckenlicht Custom"
    assert ng_sw.icon == "mdi:ceiling-light"
    assert ng_sw.area_id == "bad"
    assert set(ng_sw.aliases) == {"Bad Licht", COMPUTED_NAME}
    assert ng_sw.labels == {"existing_ng", "wichtig"}
    assert ng_sw.options.get("conversation") == {"should_expose": True}
    assert ng_sw.options.get("cloud.google_assistant") == {"should_expose": False}
    assert LEGACY_DOMAIN not in ng_sw.options

    # User-only disablers/hiders are copied, integration ones are not; computed-only aliases skipped.
    ng_dim = env.ent_reg.async_get("sensor.ng_bad_dimming_status")
    assert ng_dim is not None
    assert ng_dim.disabled_by == RegistryEntryDisabler.USER
    assert ng_dim.hidden_by == RegistryEntryHider.USER
    assert ng_dim.aliases in ([], [COMPUTED_NAME])

    ng_temp = env.ent_reg.async_get("sensor.ng_bad_rt_temp")
    assert ng_temp is not None
    assert ng_temp.disabled_by is None
    assert ng_temp.hidden_by is None
    assert ng_temp.options.get("sensor") == {"display_precision": 2}
    assert ng_temp.options.get("conversation") == {"should_expose": True}


async def test_full_cutover_preserves_entity_ids_and_helpers(hass: HomeAssistant) -> None:
    """cutover=True removes legacy, renames same-domain IDs, and handles conflicts."""
    env = _build_env(hass)
    _entity(
        env.ent_reg,
        entity_id="sensor.orphaned_co2",
        unique_id="orphan/ch0000/odp0001",
        platform=LEGACY_DOMAIN,
    )
    other_entry = MockConfigEntry(domain="other_integration")
    other_entry.add_to_hass(hass)

    orig_remove = hass.config_entries.async_remove

    async def _remove_with_reclaim(entry_id: str) -> Any:
        """Simulate a third-party entity reclaiming sensor.bad_rt_temp right after removal."""
        result = await orig_remove(entry_id)
        _entity(
            env.ent_reg,
            entity_id="sensor.bad_rt_temp",
            unique_id="other_rt_temp",
            platform="other_integration",
            config_entry=other_entry,
        )
        return result

    options_calls: list[str] = []
    orig_update_options = env.ent_reg.async_update_entity_options

    def _spy_update_options(entity_id: str, *args: Any, **kwargs: Any) -> Any:
        options_calls.append(entity_id)
        return orig_update_options(entity_id, *args, **kwargs)

    with (
        patch.object(hass.config_entries, "async_remove", _remove_with_reclaim),
        patch.object(env.ent_reg, "async_update_entity_options", _spy_update_options),
    ):
        result = await async_migrate_from_legacy(hass, env.hub_entry, dry_run=False, cutover=True)

    assert result["success"] is True
    assert _legacy_entries(hass) == []
    assert env.hub_entry.runtime_data.suppress_reload is False

    # Same-domain NG entities now occupy the original legacy entity_ids.
    switch = env.ent_reg.async_get("switch.bad_deckenlicht")
    assert switch is not None and switch.platform == DOMAIN
    assert env.ent_reg.async_get("switch.ng_bad_deckenlicht") is None

    scene = env.ent_reg.async_get("scene.abdunkeln")
    assert scene is not None and scene.platform == DOMAIN
    assert scene.options.get("conversation") == {"should_expose": True}

    # The reclaimed entity_id is a conflict: NG keeps its id but still receives options.
    assert result["summary"]["conflicts"] == 1
    assert result["conflicts"][0]["entity_id"] == "sensor.bad_rt_temp"
    ng_temp = env.ent_reg.async_get("sensor.ng_bad_rt_temp")
    assert ng_temp is not None
    assert ng_temp.options.get("sensor") == {"display_precision": 2}

    # Options were written to the final entity_id, i.e. after the rename.
    assert "switch.bad_deckenlicht" in options_calls
    assert "switch.ng_bad_deckenlicht" not in options_calls

    # Orphaned legacy entity removed; downstream helpers untouched.
    assert env.ent_reg.async_get("sensor.orphaned_co2") is None
    helper_light = env.ent_reg.async_get("light.bad_deckenlicht")
    assert helper_light is not None and helper_light.platform == "switch_as_x"
    helper_meter = env.ent_reg.async_get("sensor.bad_heizbedarf_heute")
    assert helper_meter is not None and helper_meter.platform == "utility_meter"


async def test_cutover_aborts_safely_when_no_matching_ng_entities(hass: HomeAssistant) -> None:
    """The legacy entry is never removed if zero NG entities matched."""
    env = _build_env(hass)
    for entity in list(env.ent_reg.entities.values()):
        if entity.platform == DOMAIN:
            env.ent_reg.async_remove(entity.entity_id)

    result = await async_migrate_from_legacy(hass, env.hub_entry, dry_run=False, cutover=True)

    assert result["success"] is False
    assert _legacy_entries(hass) == [env.legacy_entry.entry_id]
    assert any("zero matching freeathome_ng entities" in w for w in result["warnings"])


async def test_selective_serialnumbers_filter_and_partial_cutover_guard(
    hass: HomeAssistant,
) -> None:
    """The serialnumbers filter scopes dry_run/sync and rejects cutover=True."""
    env = _build_env(hass)

    preview = await async_migrate_from_legacy(
        hass,
        env.hub_entry,
        dry_run=True,
        cutover=False,
        serialnumbers_filter={"abb700da1ddf", "MISSING01"},
    )
    assert preview["summary"]["discovered_legacy_devices"] == 1
    assert preview["summary"]["discovered_legacy_entities"] == 2
    assert any("MISSING01" in w for w in preview["warnings"])

    synced = await async_migrate_from_legacy(
        hass,
        env.hub_entry,
        dry_run=False,
        cutover=False,
        serialnumbers_filter={"ABB700DA1DDF"},
    )
    assert synced["summary"]["same_domain_entities_migrated"] == 2
    assert env.dev_reg.async_get(env.devices["ng_switch"]).area_id == "bad"
    assert env.dev_reg.async_get(env.devices["ng_rt"]).area_id is None
    assert "sensor" not in env.ent_reg.async_get("sensor.ng_bad_rt_temp").options

    with pytest.raises(ServiceValidationError) as exc:
        await async_migrate_from_legacy(
            hass,
            env.hub_entry,
            dry_run=False,
            cutover=True,
            serialnumbers_filter={"ABB700DA1DDF"},
        )
    assert exc.value.translation_domain == DOMAIN
    assert exc.value.translation_key == "partial_cutover_not_supported"
    assert _legacy_entries(hass) == [env.legacy_entry.entry_id]


async def test_migration_validation_errors_are_translated(hass: HomeAssistant) -> None:
    """Unloaded hubs and ambiguous legacy entries raise translated errors without writes."""
    unloaded = MockConfigEntry(domain=DOMAIN, unique_id="ABB700000009")
    unloaded.add_to_hass(hass)
    with pytest.raises(ServiceValidationError) as exc:
        await async_migrate_from_legacy(hass, unloaded, dry_run=True)
    assert exc.value.translation_key == "entry_not_loaded"
    assert exc.value.translation_placeholders == {"entry_id": unloaded.entry_id}

    env = _build_env(hass)
    hass.config_entries.async_update_entry(
        env.legacy_entry, unique_id="ABB700111111", data={CONF_HOST: "10.0.0.1"}
    )
    MockConfigEntry(
        domain=LEGACY_DOMAIN, unique_id="ABB700222222", data={CONF_HOST: "10.0.0.2"}
    ).add_to_hass(hass)
    with pytest.raises(ServiceValidationError) as exc:
        await async_migrate_from_legacy(hass, env.hub_entry, dry_run=False, cutover=True)
    assert exc.value.translation_key == "legacy_entry_ambiguous"
    assert len(_legacy_entries(hass)) == 2


async def test_device_metadata_updates_use_current_registry_api(hass: HomeAssistant) -> None:
    """Device metadata is transferred through the non-deprecated registry API.

    Calling the deprecated `async_get_device` from integration code raises in tests,
    so a successful run proves the modern lookup path is used.
    """
    env = _build_env(hass)
    result = await async_migrate_from_legacy(hass, env.hub_entry, dry_run=False, cutover=False)
    assert result["summary"]["device_metadata_updates"] == 2


async def test_migrate_service_multi_hub_and_legacy_flow_defaults(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_sysap: MockSysApServer
) -> None:
    """The service is registered with response support and disambiguates multiple hubs."""
    legacy_entry = MockConfigEntry(
        domain=LEGACY_DOMAIN,
        unique_id="ABB700999999",
        data={CONF_HOST: "192.168.8.23", CONF_USE_ROOM_NAMES: True, CONF_SWITCH_AS_X: False},
    )
    legacy_entry.add_to_hass(hass)
    assert get_legacy_setup_defaults(hass) == {
        CONF_HOST: "192.168.8.23",
        CONF_USE_ROOM_NAMES: True,
        CONF_SWITCH_AS_X: False,
    }
    assert hass.services.supports_response(DOMAIN, SERVICE_MIGRATE_FROM_LEGACY) == (
        SupportsResponse.ONLY
    )

    # A second loaded hub (another SysAP) makes an untargeted call ambiguous.
    other_config = {
        "11111111-1111-1111-1111-111111111111": next(iter(mock_sysap.configuration.values()))
    }
    other_sysap = MockSysApServer(port=0, serial_number="ABB700000002", configuration=other_config)
    await other_sysap.start()
    second = MockConfigEntry(
        domain=DOMAIN,
        unique_id="ABB700000002",
        data=entry_data(other_sysap, **{CONF_USERNAME: "apiuser", CONF_PASSWORD: "secret"}),
    )
    second.add_to_hass(hass)
    assert await hass.config_entries.async_setup(second.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_MIGRATE_FROM_LEGACY,
            {"dry_run": True},
            blocking=True,
            return_response=True,
        )

    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_MIGRATE_FROM_LEGACY,
        {"entry_id": init_integration.entry_id, "dry_run": True},
        blocking=True,
        return_response=True,
    )
    assert response["success"] is True
    assert response["hub_entry_id"] == init_integration.entry_id

    assert await hass.config_entries.async_unload(second.entry_id)
    await other_sysap.stop()
