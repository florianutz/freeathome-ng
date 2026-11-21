---
name: add-entity
description: Add a new free@home device type, entity or HA platform to freeathome_ng end to end (api device model, EntityDescription, translations, icons, tests, quality gate).
argument-hint: "<device, functionID or platform>"
allowed-tools: Bash, Read, Edit, Write, Grep, Glob
---

# /add-entity

Input: `$ARGUMENTS` (device, functionID or platform). Ask for, or derive from the request: the free@home `functionID`(s), the relevant pairing IDs (input/output datapoints) and parameter IDs, and the HA platform. Read AGENTS.md sections 3–5 and docs/DECISIONS.md (ADR-001) first.

## 1. API layer (`custom_components/freeathome_ng/api/`)

1. Add or extend the device model in `api/devices/<platform>.py` (subclass of `FahBaseDevice` in `base.py`): `pairing_ids(function_id)`, optional `parameter_ids(function_id)`, state properties and async command methods that write datapoints through the client.
2. Export it from `api/devices/__init__.py` and add it to `DEVICE_CLASSES` in `api/controller.py`; new Function, Pairing or parameter IDs go into `api/const.py`, never into the HA-layer `const.py`.
3. No `homeassistant` imports. Run `mypy` (strict) on the change.
4. Add the channel to `tests/fixtures/configuration.json` (anonymised serial, realistic datapoints) if no existing channel covers it.

## 2. HA platform (`custom_components/freeathome_ng/<platform>.py`)

1. New platform only: add it to `PLATFORMS` in `__init__.py`, set `PARALLEL_UPDATES = 0`, use `AddConfigEntryEntitiesCallback`, and register an adder for devices found at runtime with `register_platform_adder(hass, entry_id, "<platform>", adder)`. If the entities are built from device models of another kind (for example a `number` from thermostats), map the platform to those kinds in `PLATFORM_DEVICE_KINDS` (`__init__.py`).
2. Describe the entity with a frozen `EntityDescription` subclass: `key`, `translation_key`, `device_class`, `state_class`, `entity_category`, `entity_registry_enabled_default`, value accessor. Set `self.entity_description` **before** `super().__init__()`: the base class reads `translation_key`, which HA caches, so a description set afterwards leaves the entity without its translated name.
3. The entity subclasses `FreeAtHomeNgEntity` (`entity.py`), which already sets `has_entity_name` and attaches it to the channel device (ADR-001). The channel's primary entity has no `translation_key` (named after the device); an additional entity of the same channel sets a `translation_key` and a unique ID suffix: `{sysap_uuid}/{serial}/{channel_id}/<suffix>`. A suffix, once released, never changes (AGENTS.md section 5).
4. Commands: decorate every action method with `@api_action` (`entity.py`); it turns `api/` errors into a translated `HomeAssistantError`.
5. No raw configuration in `extra_state_attributes`. A value users want to see in history, automate on or change is an entity (sensor, number, select, switch), not an attribute.
6. Replacing an existing attribute or entity action: keep the old one working, mark it deprecated in code, `strings.json` (service description) and README, call `self.async_report_deprecated_action(action, platform, key)` from the old action so users get a repair issue naming the new entity, and list it in `CHANGELOG.md`. Removal happens only in a major release.

## 3. Strings, translations, icons

1. Add `entity.<platform>.<translation_key>.name` (and `state`/`state_attributes` where relevant) plus any new `exceptions` to `strings.json`.
2. Run `/sync-translations` so all 7 locales get the keys.
3. Add the icon to `icons.json` under `entity.<platform>.<translation_key>` (default and per state where it changes). No `_attr_icon`.

## 4. Tests

1. Device model test: functionID/pairing matching and datapoint updates (`tests/test_controller_and_devices.py`), edge cases without a SysAP in `tests/test_device_models.py`.
2. Platform test: setup from the fixture via the mock SysAP, state change via a WebSocket frame (`_broadcast_dp` and `_wait_for_state` from `tests/test_platforms.py`), unavailability. Add each command to the parametrised `test_entity_action_writes_to_sysap` in `tests/test_platform_actions.py`.
3. Look entities up by unique ID with `entity_id_for(hass, platform, "<serial>/<channel>[/suffix]")` from `tests/conftest.py`, never by a hard-coded entity ID: HA releases generate entity IDs for child devices differently.
4. Snapshots (syrupy): `test_platform_snapshot` covers every platform in `PLATFORMS` automatically. Update only the affected platform, for example `pytest "tests/test_platforms.py::test_platform_snapshot[number]" --snapshot-update`, and review the `.ambr` diff: existing entries must not change unless intended.
5. If the device could also exist in the legacy integration, extend `tests/test_migration.py` with the unique ID mapping.
6. `tests/test_coexistence.py` checks that every `icons.json` key, including state icons, has a matching entry in `strings.json`.

## 5. Finish

1. Update README "Supported Platforms & Devices", `CHANGELOG.md` `[Unreleased]`, and `quality_scale.yaml` if a rule's status changed.
2. Run `/check-quality`; everything must be green, including the minimum-HA run when the change uses a Home Assistant API for the first time.
3. If the same check still fails after 3 fix attempts, stop and report the blocker with the failing output instead of trying further variations.
