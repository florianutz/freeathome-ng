# Home Assistant Custom Integration Engineering Standards (`HA 2025.2–2026.11+`)

This engineering playbook captures the architectural patterns, Home Assistant Core compatibility rules, multi-channel naming standards, Recorder hygiene rules, and Home Assistant Marketplace release requirements for **`freeathome_ng`**.

---

## 1. Hub Architecture & Local-Push Lifecycle (`HA >= 2025.2`)

1. **One Hub Entry per SysAP (`"integration_type": "hub"`):**
   - Each free@home System Access Point (SysAP) corresponds to one `ConfigEntry` driven by Local REST discovery (`/fhapi/v1/api/rest/configuration`) and persistent WebSocket push updates (`/fhapi/v1/api/ws`).
   - Because physical devices, channels, and runtime additions/removals (`devicesAdded` / `devicesRemoved`) are discovered automatically from the SysAP configuration model, **do not** introduce manual `ConfigSubentryFlow` entries for SysAP bus devices.
2. **Typed Runtime Data (`entry.runtime_data`):**
   - Declare `FreeAtHomeNgRuntime` and `type FreeAtHomeNgConfigEntry = ConfigEntry[FreeAtHomeNgRuntime]` in `__init__.py` rather than storing runtime state directly in `hass.data[DOMAIN][entry.entry_id]`.
   - Keep only `"loaded_entries"` in `hass.data[DOMAIN]` so domain services can target loaded SysAP instances safely across multiple hubs.
3. **SysAP Hub Device & Lifecycle Hygiene:**
   - Register a `DeviceEntryType.SERVICE` Hub device (`identifiers={(DOMAIN, f"hub_{entry.entry_id}")}`) at setup and store its `hub_device.id` on `entry.runtime_data.hub_device_id` so every bus device links cleanly via `via_device_id`.
   - Implement `async_remove_config_entry_device` so Home Assistant prevents deleting the active SysAP Hub or currently configured free@home devices from the UI while permitting cleanup of stale or removed devices.
   - Ignore `CONF_VIRTUAL_DEVICES` in `_connection_snapshot` and honor `runtime.suppress_reload` inside `_async_reload_entry` so registering/updating virtual devices never triggers redundant entry reloads.

---

## 2. Strict API Layer Separation & WebSocket Resilience

1. **Zero `homeassistant` Imports Inside `api/`:**
   - Keep REST/WebSocket clients (`api/client.py`), configuration/event routing (`api/controller.py`), and all device models (`api/devices/*.py`) pure Python (`aiohttp` / stdlib only). Enforce this automatically via AST tests in CI.
   - Inject Home Assistant's managed `aiohttp.ClientSession` (`async_get_clientsession(hass, verify_ssl=verify_ssl)`).
2. **Typed Exception Hierarchy & Auth Fallback:**
   - Distinguish connection/API errors (`ConfigEntryNotReady` at startup) from authentication failures (`FreeAtHomeAuthError` → `ConfigEntryAuthFailed` / automatic `async_start_reauth`).
   - Support automatic `/settings.json` username resolution (`resolve_username_candidates`) when the user enters a SysAP display name instead of the JID localpart.
3. **WebSocket Reconnect Discipline & Resync:**
   - Follow the `log-when-unavailable` pattern in `FreeAtHomeLocalApiClient._websocket_loop`: emit a single `WARNING` when the WebSocket drops, log retry attempts at `DEBUG`, and emit a single `INFO` recovery message upon reconnection.
   - Trigger `resync_configuration()` automatically after every reconnect so state transitions missed during a network or SysAP restart are reconciled immediately.
   - Track `ws_connected` availability on `FreeAtHomeNgEntity.available` and keep virtual device TTL heartbeat tasks isolated from `entry` reloads.

---

## 3. Home Assistant Core 2025–2027 Deprecation & Compatibility Tracker

Watch `homeassistant.helpers.frame` log warnings on live HAOS instances after every integration update and eliminate deprecations proactively:

| Deprecated Pattern | Required Replacement | Breaks in HA Core | Reference Implementation |
|---|---|---|---|
| `DeviceInfo(..., via_device=(DOMAIN, id))` | Look up Hub `DeviceEntry.id` via `device_registry.async_get_or_create(...)` stored on `runtime.hub_device_id` and pass `via_device_id=hub_device_id` (guarded fallback only for old HA/stubs) | **`2027.8.0`** | [`__init__.py`](../custom_components/freeathome_ng/__init__.py), [`entity.py`](../custom_components/freeathome_ng/entity.py) |
| `device_registry.async_get_device(identifiers=...)` | Use `async_get_device_by_identifier((domain, id), config_entry_id)`, `async_get(device_id)`, or `async_get_devices(identifiers=...)` (guarded fallback only on HA `< 2026.8`) | **`2027.8.0`** | Migration & registry helpers |
| Combining `entry.add_update_listener(...)` with `async_update_reload_and_abort(...)` or calling `async_reload()` inside listener | Keep one reload owner: `entry.add_update_listener` schedules reload via `hass.config_entries.async_schedule_reload(entry.entry_id)` and reauth/reconfigure flows call `self.async_update_and_abort(...)` | **`2026.12.0`** | [`__init__.py`](../custom_components/freeathome_ng/__init__.py), [`config_flow.py`](../custom_components/freeathome_ng/config_flow.py) |
| Passing `config_entry` to `OptionsFlow.__init__` | Return `FreeAtHomeNgOptionsFlow()` with zero arguments and read `self.config_entry` | **`2025.12.0`** | [`config_flow.py`](../custom_components/freeathome_ng/config_flow.py) |
| `CONCENTRATION_MICROGRAMS_PER_CUBIC_METER` / `CONCENTRATION_PARTS_PER_MILLION` | Import `UnitOfDensity.MICROGRAMS_PER_CUBIC_METER` and `UnitOfRatio.PARTS_PER_MILLION` with guarded fallback for older HA | **`2027.8.0`** | [`sensor.py`](../custom_components/freeathome_ng/sensor.py) |
| Legacy `ClimateEntity` `temperature_unit` / `current_temperature` / `target_temperature` | Use `_attr_native_temperature_unit`, `native_current_temperature`, `native_target_temperature` | **`2027.11.0`** | [`climate.py`](../custom_components/freeathome_ng/climate.py) |
| Legacy `AddEntitiesCallback` platform typing & missing concurrency guard | Use `AddConfigEntryEntitiesCallback` (with guarded fallback) and define `PARALLEL_UPDATES = 0` on all push-driven platforms | Current standard | All 10 platform modules |

### Compatibility Guard Pattern

When supporting HA `2025.2+` through `2026.11+` simultaneously:

```python
_SUPPORTS_VIA_DEVICE_ID = (
    "via_device_id" in getattr(DeviceInfo, "__annotations__", {})
    or "via_device_id" in getattr(DeviceInfo, "__optional_keys__", set())
    or DeviceInfo is dict
)
```

Use capability checks (`hasattr(hass.config_entries, "async_schedule_reload")`, `hasattr(self, "async_update_and_abort")`, `hasattr(self, "_get_reconfigure_entry")`) so modern HA Core releases emit zero frame warnings while standalone test stubs stay clean.

---

## 4. Platform Semantics, Multi-Channel Naming & Recorder Discipline

1. **Multi-Channel Actuator Naming vs. Typed Sensor Entities:**
   - Multi-gang free@home MDRC actuators (such as `B008` 8/8-gang or `1010` 2/2-gang) group independent channels located in different rooms under one physical SysAP device.
   - Therefore, **do not** set `_attr_has_entity_name = True` globally on `FreeAtHomeNgEntity`: actuators, covers, climate, fans, switches, locks, buttons, scenes, and binary sensors intentionally use their resolved channel display name (`self._attr_name = device.name`).
   - Dedicated multi-entity/derived sensors in `sensor.py` (`FreeAtHomeNgSensor`, `FreeAtHomeNgThermostatTemperatureSensor`, `FreeAtHomeNgDimmingStatusSensor`) use `_attr_has_entity_name = True` with `_attr_translation_key` and `{channel_name}` / `{channel_id}` placeholders so localized type labels compose cleanly.
2. **Whitespace & Cyclic Repeat Discipline:**
   - Normalize `.strip()` on all SysAP room, device, and channel names during `load_configuration()` to prevent double spaces in generated entity names.
   - Keep the 840 s cyclic repeat filter active on `FahBinarySensor` rockers/motion sensors while never suppressing safety alarms (`PID_FIRE_ALARM_ACTIVE`, `PID_CO_ALARM_ACTIVE`).
3. **Zero Recorder Bloat & Diagnostic Redaction:**
   - Keep `extra_state_attributes` strictly minimal (`window_position` on window contacts, `forced_position` on covers, `valve`/`temperature_correction` on thermostats). **Never** store raw SysAP configuration blobs or WebSocket JSON frames on entity attributes.
   - Expose redacted SysAP and single-device configuration snapshots through `diagnostics.py` (`async_get_config_entry_diagnostics` + `async_get_device_diagnostics`) using `async_redact_data`.
   - Validate domain service targets (`_resolve_target_runtimes`) and raise `ServiceValidationError` rather than falling back silently to another SysAP when `host` does not match or no entry is loaded.

---

## 5. Domain Isolation & Migration Readiness

1. **Strict Isolation from Legacy `freeathome`:**
   - Domain: `freeathome_ng` (never `freeathome`).
   - Device identifiers: `("freeathome_ng", "{sysap_uuid}_{serialnumber}")` and Hub `("freeathome_ng", "hub_{entry_id}")`.
   - Entity unique IDs: `{sysap_uuid}/{serialnumber}/{channel_id}` (plus `/{dp_id}`, `/current_temperature`, or `/dimming_status` where applicable).
   - Event bus names: `freeathome_ng_event`, `freeathome_ng_scene_triggered`, `freeathome_ng_virtual_device_command`.
   - Service namespace: `freeathome_ng.*`.
2. **Three-Stage Legacy Migration Workflow (`freeathome_ng.migrate_from_legacy`):**
   - **Stage 1 (`dry_run: true`):** Read-only preview returning deterministic mappings (`("freeathome", serial)` → `("freeathome_ng", "{sysap_uuid}_{serial}")`, legacy `<serial>/<ch>` or `<sysap_id>/FFFF.../<ch>` → `{sysap_uuid}/...`), `switch_as_x` parity checks, third-party conflicts, and warnings.
   - **Stage 2 (`dry_run: false, cutover: false`):** Copies device `name_by_user`/`area_id`/merged `labels` and entity metadata/Assist options without removing legacy `freeathome` (also supports selective `serialnumbers` filtering).
   - **Stage 3 (`dry_run: false, cutover: true`):** Verifies matching NG entities exist before touching the legacy entry, blocks partial `serialnumbers` cutover (single legacy ConfigEntry per SysAP), sets `runtime.suppress_reload = True`, removes the legacy entry + orphaned legacy entities, transfers device metadata via `async_get_device_by_identifier`, copies user-only `disabled_by`/`hidden_by`, renames same-domain entities onto original `entity_id`s, and applies `entity_registry` options **after** renaming onto `final_entity_id`.

---

## 6. Home Assistant Marketplace (`2026.11+`, formerly HACS) & Hassfest Standards

1. **Marketplace Terminology & Setup:**
   - Starting in **Home Assistant `2026.11`**, HACS is integrated into Home Assistant Core as **Marketplace** (**Settings → Marketplace**).
   - Adding **custom repositories** in Marketplace requires a connected GitHub account in Marketplace settings.
   - Document both **Home Assistant Marketplace (`2026.11+`)** and **HACS (`2025.2–2026.10`)** in `README.md`.
2. **`manifest.json` Rules (Hassfest Strict):**
   - Required key order: `"domain"` first, `"name"` second, then all remaining keys sorted **strictly alphabetically**:
     `"categories"`, `"codeowners"`, `"config_flow"`, `"dependencies"`, `"documentation"`, `"integration_type"`, `"iot_class"`, `"issue_tracker"`, `"requirements"`, `"version"`, `"zeroconf"`.
   - `"version"` MUST follow SemVer and match `pyproject.toml` and the Git release tag (`vX.Y.Z`).
   - Declare `"integration_type": "hub"` and valid Core `"categories"` (`["hubs_protocols"]`).
3. **Repository Validation Checklist:**
   - `hacs.json` at repo root (`"name"`, `"render_readme": true`, `"homeassistant": "2025.2.0"`).
   - `custom_components/freeathome_ng/brand/` PNG icons/logos (`icon.png`, `icon@2x.png`, `logo.png`, `logo@2x.png`, verified PNG headers).
   - GitHub repository **Topics** configured (`home-assistant`, `hacs`, `custom-component`, `freeathome`, `busch-jaeger`, `abb`).
   - GitHub Actions workflow running `ruff check custom_components tests`, `pytest`, `home-assistant/actions/hassfest@master`, and `hacs/action@main` (`category: integration`).

---

## 7. Localization, Testing & Live Verification

1. **Translation Parity:** Keep `strings.json`, `services.yaml`, and all 7 `translations/*.json` files (`en`, `de`, `nl`, `fr`, `it`, `es`, `pl`) 100% synchronized recursively, enforced by `tests/test_coexistence.py`.
2. **Standalone Testability + Mock SysAP:** Maintain full lightweight stubs in `tests/conftest.py`, AST import guards for `api/`, config flow tests, entity/platform tests, and a standalone mock SysAP server (`tests/mock_sysap_server.py`) backed by `tests/fixtures/configuration.json`.
3. **Post-Release Live Check:** After tagging a release and updating the live Home Assistant test instance, inspect Hub and device diagnostics, verify options/reconfigure reload cleanly once, and check `homeassistant.helpers.frame` plus `system_log` for zero deprecation warnings or setup errors.
