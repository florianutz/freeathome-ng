# free@home NG — Engineering Handbook

Binding rules for everyone (humans and AI agents) changing this repository. This file is the single source of truth; `CLAUDE.md` imports it. Keep it under 200 lines: detail belongs in `docs/`, linked from here.

## 1. Project & quality target

`freeathome_ng` is a Home Assistant custom integration for ABB / Busch-Jaeger free@home, built only on the official SysAP Local REST & WebSocket API (`/fhapi/v1/api`). It runs side by side with the legacy XMPP `freeathome` integration and can take over from it (`freeathome_ng.migrate_from_legacy`).

- **Target:** Integration Quality Scale **Gold**, architecturally ready for **Platinum**. The status of every rule lives in `custom_components/freeathome_ng/quality_scale.yaml`; update it in the same PR that changes a rule's status.
- **Minimum Home Assistant:** 2026.8.0 ([ADR-002](docs/DECISIONS.md)). Do not add compatibility guards for older releases.
- **Binding design decisions:** [docs/DECISIONS.md](docs/DECISIONS.md). Patterns and details: [docs/HA_INTEGRATION_STANDARDS.md](docs/HA_INTEGRATION_STANDARDS.md).

## 2. Repository layout

- `custom_components/freeathome_ng/api/` — HA-free library: REST/WebSocket client (`client.py`), configuration and event controller (`controller.py`), device models (`devices/*.py`).
- `custom_components/freeathome_ng/` — HA layer: setup and services (`__init__.py`), flows (`config_flow.py`), legacy takeover (`migration.py`), entity base (`entity.py`), one module per platform, `diagnostics.py`, `const.py`, `manifest.json`, `services.yaml`, `strings.json`, `translations/` (7 locales), `quality_scale.yaml`, `brand/`.
- `tests/` — test suite, `mock_sysap_server.py` (SysAP double), `fixtures/configuration.json`.
- `scripts/` — developer tooling (`check_translations.py`).
- `docs/` — decisions, standards, user migration guide.
- `.claude/skills/` — Claude Code workflows (section 9).

## 3. Architecture

1. **Two layers, one direction.** `api/` is written as if it were its own PyPI package: stdlib + `aiohttp` only, never `homeassistant` (an AST test enforces this), fully typed, raises its own exceptions (`FreeAtHomeAuthError`, connection errors). The HA layer depends on `api/`, never the reverse.
2. **Data flow.** `client` (REST + WebSocket) → `controller` (configuration model, datapoint routing, `devicesAdded`/`devicesRemoved`) → device models → callbacks → HA entities. Entities never call REST directly; they call device-model methods.
3. **One config entry per SysAP** (`integration_type: hub`), typed `entry.runtime_data` (`FreeAtHomeNgConfigEntry = ConfigEntry[FreeAtHomeNgRuntime]`). No state in `hass.data`.
4. **Device model** ([ADR-001](docs/DECISIONS.md)): SysAP hub device → physical device → one channel device per free@home channel. Devices are discovered from the SysAP; never add manual subentries for bus devices.
5. **Services** are registered once in `async_setup` and target an entry via `config_entry_id`. They never fall back silently to another SysAP.
6. **WebSocket lifecycle:** reconnect with capped exponential backoff and jitter, full configuration resync after every reconnect, one `WARNING` on loss, `DEBUG` for retries, one `INFO` on recovery. Every background task is cancelled in `async_unload_entry`.

## 4. Coding standards

- **Python 3.14 (required by Home Assistant), typed.** `mypy --strict` must pass (today for `api/`; the HA layer joins in AP6). No new `Any` in public signatures, no bare `# type: ignore` (always with error code).
- **Async:** no blocking I/O in the event loop (no `requests`, `time.sleep`, sync file I/O; use `hass.async_add_executor_job` if unavoidable). Use HA's shared `aiohttp` session via `async_get_clientsession`. Never create unmanaged tasks; use `entry.async_create_background_task`.
- **Entities:**
  - `_attr_has_entity_name = True` on every entity; names come from the device (primary entity, `name=None`) or from `translation_key`. No hard-coded English names.
  - Describe entities with frozen `EntityDescription` dataclasses (`key`, `translation_key`, `device_class`, `entity_category`, `entity_registry_enabled_default`, value functions).
  - Icons come from `icons.json` (including state icons), never `_attr_icon`.
  - Diagnostic/config entities set `entity_category`; noisy or rarely used entities are disabled by default.
  - `PARALLEL_UPDATES = 0` on every platform (push-only).
  - `extra_state_attributes` only for small user-relevant values; never raw SysAP configuration or frames (use diagnostics).
  - Availability follows both the WebSocket connection and the device's own reachability.
- **Errors:** user-facing exceptions (`HomeAssistantError`, `ServiceValidationError`, `ConfigEntryNotReady`, `ConfigEntryAuthFailed`) use `translation_domain=DOMAIN` + `translation_key`; texts live in `strings.json` → `exceptions`. Catch `api/` exceptions at the HA boundary and re-raise as HA exceptions.
- **Config flow:** unique ID = SysAP serial; every field has `data_description`; specific errors (`cannot_connect`, `invalid_auth`, `unknown`); reauth and reconfigure use `async_update_reload_and_abort` / `async_update_and_abort`.
- **Repairs:** use `issue_registry` for actionable problems the user must fix (not for transient errors).
- **Diagnostics:** everything through `async_redact_data`; redact credentials, serials, JIDs, UUIDs, host and geo data.
- **Style:** `ruff check` and `ruff format` (config in `pyproject.toml`). Docstrings on public functions. Log with `%s` formatting, never f-strings.
- **Names from the SysAP:** `.strip()` all room, device and channel names. Keep the 840 s keep-alive filter for binary sensors; never suppress `PID_FIRE_ALARM_ACTIVE` / `PID_CO_ALARM_ACTIVE`.

## 5. Protection rules (never break these)

1. **Stable identifiers.** Never change the format of entity `unique_id`s (`{sysap_uuid}/{serialnumber}/{channel_id}[/...]`), device identifiers (`{sysap_uuid}_{serialnumber}`, `hub_{entry_id}`) or config entry unique IDs without a registry migration (`async_migrate_entry` / `er.async_migrate_entries`) and a test proving the migration.
2. **Domain isolation.** Never use the legacy domain `freeathome`, its identifiers, `freeathome_event` or its services in normal operation. Event names `freeathome_ng_event`, `freeathome_ng_scene_triggered`, `freeathome_ng_virtual_device_command` are public API.
3. **`migration.py`** changes only with green `tests/test_migration.py` and `tests/test_coexistence.py`, and with a new test for the changed behaviour. Keep its safety invariants (see [standards §6](docs/HA_INTEGRATION_STANDARDS.md)).
4. **Translations:** `strings.json` is the source; all 7 locales (`en`, `de`, `es`, `fr`, `it`, `nl`, `pl`) stay key-identical and placeholder-identical (`scripts/check_translations.py`).
5. **Public service schemas and event payloads** change only in a backwards-compatible way, or with a CHANGELOG entry under "Breaking changes".
6. **README** contains no third-party attribution/credit sections or links to legacy forks. Call HACS on HA 2026.11+ "Home Assistant Marketplace".
7. **Secrets:** never commit credentials, real SysAP dumps or host names; fixtures are anonymised.

## 6. Testing

```bash
pip install -r requirements_test.txt   # Python 3.14; pins HA core, pytest, syrupy
pytest                                   # whole suite
pytest tests/test_migration.py tests/test_coexistence.py   # guard suites
pytest --cov --cov-report=term-missing   # coverage
```

- Every feature or bug fix comes with a test. Config flow: every step and every error path. Platforms: setup, state updates via WebSocket frames, actions, unavailability.
- Tests run against real Home Assistant (`pytest-homeassistant-custom-component`). Fixtures in `tests/conftest.py`: `mock_sysap` (mock SysAP on a free localhost port), `mock_config_entry`, `init_integration` (entry set up end to end), `mock_setup_entry`, `entity_registry_enabled_by_default`. Import the integration as `custom_components.freeathome_ng`, never as `freeathome_ng`.
- Use `tests/mock_sysap_server.py` and `tests/fixtures/configuration.json` for SysAP behaviour; extend the fixture rather than mocking internals.
- **Snapshots (syrupy):** `tests/snapshots/` holds entity and device registry snapshots per platform. Regenerate only intentionally with `pytest --snapshot-update`, and review the `.ambr` diff in the PR like code. Bumping `pytest-homeassistant-custom-component` (and with it HA core) may change snapshots; regenerate and review them in the same PR.
- Target: > 95 % coverage for the integration package ([ADR-003](docs/DECISIONS.md)).

## 7. Quality gate

A change is done only when all of these pass (the `/check-quality` skill runs them and summarises):

```bash
ruff check custom_components tests scripts
ruff format --check custom_components tests scripts
mypy
pytest --cov --cov-report=term
python3 scripts/check_translations.py
```

CI (`.github/workflows/validate.yml`) additionally runs Hassfest and HACS validation.

## 8. Workflow

- Small, single-purpose PRs on a feature branch; never push to `main` directly.
- Add user-visible changes to `CHANGELOG.md` under `[Unreleased]`.
- Keep this file, `docs/`, `quality_scale.yaml` and the code consistent in the same PR.
- Releases follow the `/release` skill; versions stay in sync across `manifest.json`, `pyproject.toml`, `CHANGELOG.md` and the `vX.Y.Z` tag.

## 9. Claude Code skills

- `/check-quality` — run the full quality gate and report.
- `/add-entity` — add a new entity type or platform end to end.
- `/sync-translations` — reconcile `strings.json` with all 7 locales.
- `/release` — prepare a release.

## 10. Current gaps

The code does not yet meet every rule above; open items are tracked as `todo` in `quality_scale.yaml` with their work package (AP2–AP7). When touching code in a `todo` area, move it toward the rule; never add new code that violates it.

## 11. References

- Integration Quality Scale: https://developers.home-assistant.io/docs/core/integration-quality-scale/
- Architecture: https://developers.home-assistant.io/docs/architecture_index
- Config flow, reauth, reconfigure: https://developers.home-assistant.io/docs/config_entries_config_flow_handler
- Entities (`has_entity_name`, `EntityDescription`): https://developers.home-assistant.io/docs/core/entity
- Diagnostics: https://developers.home-assistant.io/docs/core/integration-diagnostics
- Repairs: https://developers.home-assistant.io/docs/core/platform/repairs
- Translations and icons: https://developers.home-assistant.io/docs/internationalization/core
- Testing: https://developers.home-assistant.io/docs/development_testing
- HACS publishing: https://hacs.xyz/docs/publish/integration/
- Ruff: https://docs.astral.sh/ruff/
