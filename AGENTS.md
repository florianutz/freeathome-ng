# free@home NG — Agent Instructions

## 1. Instruction Structure & Maintenance Rules

This file (`AGENTS.md`) is the canonical repository handbook. More specific scoped `AGENTS.md` files (if added under subdirectories) supplement this root document; in any conflict, this root file governs.

Meta-rules for editing `AGENTS.md`:

- Keep this file concise: **<= 200 lines** and **<= 16,000 Unicode characters**.
- Offload deep architectural specs, compatibility tables, and reference guides into dedicated documents under `docs/` rather than duplicating prose here.
- Use ordinary Markdown links with explicit scope descriptions; never use `@`-imports or bare `"see also"` references.
- Verify no drift between `AGENTS.md`, `custom_components/freeathome_ng/`, `tests/`, and `docs/` after code or metadata changes.

---

## 2. Project Overview

**free@home NG (`freeathome_ng`)** is a Home Assistant (`>= 2025.2.0`) custom integration for **ABB / Busch-Jaeger free@home** built cleanly on the official **SysAP Local REST & WebSocket API** (`/fhapi/v1/api`), packaged for **Home Assistant Marketplace** (`2026.11+`, formerly HACS).

It is designed for **zero-collision side-by-side operation** alongside the classic XMPP-based `freeathome` integration plus guided `freeathome_ng.migrate_from_legacy` takeover (preserving device metadata, Assist exposure, and Recorder history).

---

## 3. Repository Layout

- `custom_components/freeathome_ng/api/` — Pure-Python Local REST & WebSocket client (`client.py`), discovery/event controller (`controller.py`), and device models (`devices/*.py`). Zero `homeassistant` imports permitted.
- `custom_components/freeathome_ng/` — Hub setup & services (`__init__.py`), Config/Discovery/Reauth/Reconfigure/Options flows (`config_flow.py`), migration engine (`migration.py`), entity base (`entity.py`), platforms (`binary_sensor.py`, `button.py`, `climate.py`, `cover.py`, `fan.py`, `light.py`, `lock.py`, `scene.py`, `sensor.py`, `switch.py`), `const.py`, `fah_event.py`, `diagnostics.py`, `manifest.json`, `services.yaml`, `strings.json`, `translations/` (7 locales), and `brand/` PNG assets.
- `docs/` — Engineering standards ([HA Integration Engineering Standards](docs/HA_INTEGRATION_STANDARDS.md)) and user migration guide ([Migration Guide](docs/MIGRATION.md)).
- `tests/` — Lightweight HA stubs (`conftest.py`), standalone mock SysAP server (`mock_sysap_server.py`), configuration fixture (`fixtures/configuration.json`), and test modules (`test_*.py`).
- `.github/workflows/validate.yml` — GitHub Actions CI (`ruff`, `pytest`, `hassfest`, `hacs/action`).

---

## 4. Non-Negotiable Architectural & HA Core Invariants

1. **Pure-Python `api/` Layer:** Never import `homeassistant` inside `custom_components/freeathome_ng/api/**` (enforced by AST tests). Inject HA's managed `aiohttp.ClientSession` via `async_get_clientsession(hass, verify_ssl=verify_ssl)`.
2. **Hub Architecture & `entry.runtime_data`:** Keep `"integration_type": "hub"` and one `ConfigEntry` per SysAP (`FreeAtHomeNgConfigEntry = ConfigEntry[FreeAtHomeNgRuntime]`). Register a `DeviceEntryType.SERVICE` Hub device at setup and implement `async_remove_config_entry_device`. Store only `"loaded_entries"` in `hass.data[DOMAIN]` for service routing. Do **not** replace WebSocket auto-discovery with manual Config Subentries.
3. **Home Assistant 2026.11+ / 2027.x Deprecation Compliance:**
   - Link child devices via `via_device_id` (from `runtime.hub_device_id`, with guarded `via_device=(DOMAIN, f"hub_{entry_id}")` fallback only for older HA/stubs) — required before `2027.8.0`.
   - Look up devices with `async_get_device_by_identifier` / `async_get_devices` / `async_get` (guarded fallback to `async_get_device` only on HA `< 2026.8`) — required before `2027.8.0`.
   - Use `hass.config_entries.async_schedule_reload` in `_async_reload_entry` / reauth triggers and `self.async_update_and_abort` in reauth/reconfigure flows (never mix `add_update_listener` with `async_update_reload_and_abort`) — required before `2026.12.0`.
   - Use zero-arg `OptionsFlow` reading `self.config_entry`, guarded `UnitOfDensity` / `UnitOfRatio` imports (`2027.8.0`), `native_*_temperature` on climate (`2027.11.0`), `AddConfigEntryEntitiesCallback`, and `PARALLEL_UPDATES = 0` on all 10 platforms.
4. **Local API, WebSocket & Virtual Device Invariants:**
   - Support `/settings.json` username resolution when display name differs from JID localpart.
   - Deduplicate WebSocket reconnect warnings (`log-when-unavailable`: single `WARNING` on disconnect, `DEBUG` retries, single `INFO` on recovery) and resync full configuration on reconnect.
   - Strip leading/trailing whitespace (`.strip()`) on `sysapName`, device `displayName`, channel `displayName`, and room names.
   - Filter 840 s cyclic keep-alive repeats in `FahBinarySensor`, never suppressing safety PIDs (`PID_FIRE_ALARM_ACTIVE`, `PID_CO_ALARM_ACTIVE`).
   - Persist registered virtual devices in `entry.data[CONF_VIRTUAL_DEVICES]` with TTL heartbeats; exclude `CONF_VIRTUAL_DEVICES` from `_connection_snapshot` and honor `runtime.suppress_reload` so virtual device updates never trigger entry reloads.
5. **Naming, Platform Semantics & Zero Recorder Bloat:**
   - Preserve per-channel names on multi-channel actuators and binary sensors (do **not** set `_attr_has_entity_name = True` globally on `FreeAtHomeNgEntity`, as MDRC actuators group channels across rooms under one physical device). Keep `_attr_has_entity_name = True` + `translation_key` on typed `sensor.py` entities.
   - Never dump raw SysAP configuration or frame JSON into `extra_state_attributes`. Expose redacted telemetry via `diagnostics.py` (both Config Entry and single Device diagnostics) and raise `ServiceValidationError` on invalid service targets.
6. **Domain Isolation & Migration Safety:** Never reuse legacy `freeathome` domain names, device identifiers, entity unique IDs, event bus names (`freeathome_event`), or services during normal operation. In `migration.py`, run `dry_run=True` non-destructively, abort cutover before deleting legacy entries if zero matching NG entities exist, block partial cutover with `serialnumbers`, keep `runtime.suppress_reload = True` during cutover, copy user-only `disabled_by`/`hidden_by`, and update `entity_registry` options on `final_entity_id` after renaming.
7. **Documentation Constraint:** Keep `README.md` strictly free of third-party attribution/credit sections or links to external legacy forks. Refer to HACS on `HA 2026.11+` accurately as **Home Assistant Marketplace**.

---

## 5. Testing, Linting & CI Quality Gates

Before finishing any change, verify all checks match CI (`.github/workflows/validate.yml`):

```bash
ruff check custom_components tests
pytest
python3 -m compileall -q custom_components/freeathome_ng tests
```

- Every sensor translation key, dimming state, config/options step, error/abort reason, and service/field requires parity across `services.yaml`, `strings.json`, and all 7 `translations/*.json` files (`test_translations_and_services_yaml_valid`).
- Never break `api/` zero-HA-import AST checks, `manifest.json`, `hacs.json`, or `brand/*.png` invariants verified by tests, Hassfest, or `hacs/action`.

---

## 6. Release & Marketplace Workflow

1. Keep versions synchronized in `custom_components/freeathome_ng/manifest.json`, `pyproject.toml`, `CHANGELOG.md`, and the Git tag/release (`vX.Y.Z`).
2. Maintain strict `manifest.json` key order (`"domain"`, `"name"`, then alphabetical, including `"integration_type": "hub"` and `"categories": ["hubs_protocols"]`).
3. Ensure GitHub repository topics (`home-assistant`, `hacs`, `custom-component`, `freeathome`, `busch-jaeger`, `abb`) stay intact for Marketplace/HACS validation.
4. Confirm GitHub Actions (`Run pytest`, `Home Assistant Hassfest`, `HACS Validation`) pass `success`, and when testing on a live HA instance, inspect `homeassistant.helpers.frame` and `system_log` to verify zero deprecation warnings.

---

## 7. Reference Documents

- [HA Integration Engineering Standards](docs/HA_INTEGRATION_STANDARDS.md) — Complete reusable patterns, HA 2025–2027 deprecation table, multi-channel naming rules, Recorder hygiene, and Marketplace checklist.
- [Legacy Migration Guide](docs/MIGRATION.md) — Step-by-step end-user migration instructions (`dry_run`, side-by-side sync, `cutover`, event/service updates, and troubleshooting).
- [Contributing Guidelines](CONTRIBUTING.md) — Contributor environment setup, localization parity, and PR rules.
- [Changelog](CHANGELOG.md) — Release history and implemented changes.
