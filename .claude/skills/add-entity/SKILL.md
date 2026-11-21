---
name: add-entity
description: Add a new free@home device type, entity or HA platform to freeathome_ng end to end (api device model, EntityDescription, translations, icons, tests, quality gate).
---

# /add-entity

Ask for, or derive from the request: the free@home `functionID`(s), the relevant pairing IDs (input/output datapoints) and parameter IDs, and the HA platform. Read AGENTS.md sections 3–5 and docs/DECISIONS.md (ADR-001) first.

## 1. API layer (`custom_components/freeathome_ng/api/`)

1. Add or extend the device model in `api/devices/<platform>.py` (subclass of `FahBaseDevice` in `base.py`): `pairing_ids(function_id)`, optional `parameter_ids(function_id)`, state properties and async command methods that write datapoints through the client.
2. Export it from `api/devices/__init__.py` and add it to `DEVICE_CLASSES` in `api/controller.py`; new Function, Pairing or parameter IDs go into `api/const.py`, never into the HA-layer `const.py`.
3. No `homeassistant` imports. Run `mypy` (strict) on the change.
4. Add the channel to `tests/fixtures/configuration.json` (anonymised serial, realistic datapoints) if no existing channel covers it.

## 2. HA platform (`custom_components/freeathome_ng/<platform>.py`)

1. New platform only: add it to `PLATFORMS` in `__init__.py`, set `PARALLEL_UPDATES = 0`, use `AddConfigEntryEntitiesCallback`, subscribe to `devicesAdded` for dynamic devices.
2. Describe the entity with a frozen `EntityDescription` subclass: `key`, `translation_key`, `device_class`, `state_class`, `entity_category`, `entity_registry_enabled_default`, value accessor.
3. The entity subclasses `FreeAtHomeNgEntity` (`entity.py`), sets `_attr_has_entity_name = True`, attaches to the channel device (ADR-001), uses `name=None` for the channel's primary entity, and keeps the `unique_id` scheme `{sysap_uuid}/{serial}/{channel_id}[/suffix]`.
4. Commands: catch `api/` exceptions and raise `HomeAssistantError(translation_domain=DOMAIN, translation_key=...)`.
5. No raw configuration in `extra_state_attributes`.

## 3. Strings, translations, icons

1. Add `entity.<platform>.<translation_key>.name` (and `state`/`state_attributes` where relevant) plus any new `exceptions` to `strings.json`.
2. Run `/sync-translations` so all 7 locales get the keys.
3. Add the icon to `icons.json` under `entity.<platform>.<translation_key>` (default and per state where it changes). No `_attr_icon`.

## 4. Tests

1. Device model test: functionID/pairing matching and datapoint updates (`tests/test_controller_and_devices.py`).
2. Platform test: setup from the fixture via the mock SysAP, state change via a WebSocket `datapoints` frame, each command, unavailability.
3. Snapshot test (syrupy) of entity and device registry entries for the new entities; generate with `pytest --snapshot-update` and review the `.ambr` diff.
4. If the device could also exist in the legacy integration, extend `tests/test_migration.py` with the unique ID mapping.

## 5. Finish

1. Update README "Supported Platforms & Devices", `CHANGELOG.md` `[Unreleased]`, and `quality_scale.yaml` if a rule's status changed.
2. Run `/check-quality`; everything must be green.
