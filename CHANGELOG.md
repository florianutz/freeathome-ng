# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Breaking changes
- Minimum Home Assistant version is now **2026.9.0**, which brings the child devices used for free@home channels. Users on older releases stay on v1.0.x.
- With more than one SysAP set up, the writing actions `set_datapoint`, `register_virtual_device`, `unregister_virtual_device`, `trigger_proxy_device` and `send_notification` no longer run against every SysAP when no target is given. Choose the SysAP with the new `config_entry_id` field (or `host`); otherwise the action fails with a clear error. Setups with a single SysAP are not affected.
- Thermostats now use the HVAC mode `heat` instead of `heat_cool`, because free@home room temperature controllers heat towards one target temperature. Automations that set or check `heat_cool` need to use `heat`.

### Added
- Thermostats report their current action (heating, idle or off), based on the valve demand.
- Event entities for wall rockers and push buttons (`press_up`, `press_down`, and for dimming rockers `hold_up`, `hold_down`, `release`), usable as triggers in the automation editor. The `freeathome_ng_event` bus event is unchanged.
- All actions accept a `config_entry_id` field with a SysAP picker in the UI.
- Every setup and options field now has a help text, in all 7 languages.

### Changed
- Binary sensors are described with entity descriptions like in Home Assistant core; the doorbell icon comes from icon translations, and doorbells get the translated name "Doorbell" as fallback.
- The README documents every setup field and option, how data is updated, use cases, known limitations, troubleshooting and removal. The help text of "Include room names" now says correctly that the room is added in brackets after the channel name.
- Every free@home channel is now its own device below its physical device, named like the channel. A channel in another room than its actuator (for example one gang of a multi-gang switch actuator) gets that room as its area; channels in the same room keep using the area of the physical device, including areas you assigned yourself. Scenes, groups and timer programs stay single devices.
- Entities use Home Assistant's entity naming: the main entity of a channel is named after the channel device, other entities add a translated suffix (for example "Temperature"). Entity IDs of existing installations stay the same, and so do the names of main entities. The dimmer status sensor drops the channel number from its name ("Wall Rocker LT Dimmer status" instead of "Dimmer status ch0000").
- Device names no longer contain the serial number; it is shown as the device's serial number instead.
- Icons come from icon translations (`icons.json`), including icons for every action and for each dimmer status state. Sensors with a device class now show Home Assistant's own icon for it (for example the battery level icon follows the charge).
- Timer program switches are shown as configuration entities.
- Devices deleted on the SysAP are removed from Home Assistant, together with their channel devices and entities, both at runtime and on startup. Devices that are only hidden by an option (for example channels without a room) are kept.
- New installations start with the Beaufort wind force sensor disabled, as it duplicates the wind speed. Existing installations are unchanged.
- Actions are registered when Home Assistant starts, not when a SysAP loads, so automations that use them validate even while the SysAP is offline.
- Error messages from setup, actions and the legacy migration are translated, and a command the SysAP rejects now shows a clear error instead of a raw exception.
- WebSocket reconnects use randomised backoff, and unloading the integration now stops every background task cleanly.
- Development: new engineering handbook (`AGENTS.md`), `CLAUDE.md`, architecture decision records (`docs/DECISIONS.md`), Integration Quality Scale tracking (`quality_scale.yaml`), Claude Code skills, `ruff format`, strict `mypy` for the `api/` layer, coverage reporting and a translation parity script in CI. Test coverage is above 95 % (line and branch) and CI fails below that. free@home protocol constants moved into the `api/` library (`api/const.py`), which no longer imports anything from the Home Assistant layer. `mypy --strict` now covers the whole integration, and action and option schemas use `probatio`, Home Assistant's schema library. CI also tests on the minimum Home Assistant (2026.9.0) and weekly on the newest beta; a pre-commit configuration runs the quality checks locally.
- Development: the test suite now runs against real Home Assistant (`pytest-homeassistant-custom-component`, Python 3.14) instead of hand-written stubs, with syrupy snapshots of all entities and devices.

### Fixed
- Climate: thermostats failed to load on current Home Assistant (`AttributeError` while adding the entity) and never reported current or target temperature, because the entity used a non-existent `native_*` temperature API.

## [1.0.0] - 2026-11-21

### Added
- **Official Local REST & WebSocket API Architecture:** Built 100% on the official ABB / Busch-Jaeger SysAP Local REST & WebSocket API (`/fhapi/v1/api`, SysAP 2.0 firmware ≥ 2.6.0) with a pure-Python `api/` layer and zero external runtime dependencies (reuses Home Assistant's managed `aiohttp` session).
- **Real-Time WebSocket Resilience:** Instant push updates over `/fhapi/v1/api/ws` (`datapoints`, `parameters`, `scenesTriggered`, `devicesAdded`, `devicesRemoved`), automatic full configuration resync on reconnect, `log-when-unavailable` reconnect log deduplication, automatic `/settings.json` username resolution, and leading/trailing whitespace normalization on SysAP room, device, and channel names.
- **Full 10-Platform Device Coverage:**
  - **Lights (`light`):** Switching lights (when `switch_as_x` is `false`), Dimmers, Color Temperature (Kelvin), RGB lights, and Light & Dimming Groups (`0x4000`, `0x4002`).
  - **Switches (`switch`):** Switching Actuators (`0x0007`, when `switch_as_x` is `true`), Timer Program Switches (`0x4A00`), central SysAP Day/Night Switchover (`0x0025`), and Door Entry / Touch-Panel switches (`0x001D` Call Level, `0x0020` Automatic Door Opener, `0x0021` Corridor Light).
  - **Covers (`cover`):** Roller Blinds, Shutters (with slat tilt position), Attic Windows, Awnings, Shutter Groups (`0x4001`), and Forced Position (`freeathome_ng.cover_force_position`).
  - **Climate (`climate`):** Room Temperature Controllers (with and without fan speed), Eco mode preset, heating/cooling valve demand attribute, and Temperature Correction (`freeathome_ng.thermostat_temperature_correction`).
  - **Fans (`fan`):** Ceiling Fan Actuators (`0x00A8`) with percentage speed control.
  - **Sensors (`sensor`):** Localized typed sensors covering Weather Station (outdoor temperature, brightness/lux, wind speed, wind force, rain), Air Quality (humidity, CO₂, VOC), heating/cooling valve opening, dedicated thermostat current temperature, Energy Management (PV, battery power & SoC, grid, home consumption, consumed/injected energy, self-consumption, self-sufficiency), and dimmer rocker status enum.
  - **Binary Sensors (`binary_sensor`):** Wall switches/rockers (with KNX DPT 3.007 relative dimming events), pushbuttons, motion/presence detectors (with 840 s cyclic keep-alive filter that never suppresses fire/CO safety alarms), window/door contacts (`closed`/`tilted`/`open`), smoke/CO detectors, door call sensors, and weather alarms.
  - **Buttons (`button`), Locks (`lock`) & Scenes (`scene`):** Momentary triggers (`0x0045`), door opener actuators (`0x001A`, `0x0020`), and custom/system scenes (`0x4800`–`0x4804`).
- **Bidirectional Virtual Devices, Proxy Actions & System Notifications:**
  - Persistent virtual/proxy device registration (`freeathome_ng.register_virtual_device`, `freeathome_ng.unregister_virtual_device`) with automatic TTL heartbeat renewal across restarts and `freeathome_ng_virtual_device_command` events (`SwitchingActuator`, `DimActuator`, `EnergyMeterv2`, `BinarySensor`, etc.).
  - Direct datapoint writes (`freeathome_ng.set_datapoint`), proxy actions (`freeathome_ng.trigger_proxy_device`), SysAP push notifications (`freeathome_ng.send_notification`), configuration export (`freeathome_ng.dump_config`), and raw WebSocket frame monitor (`freeathome_ng.monitor`).
- **Zero-Collision Side-by-Side Coexistence & Guided Legacy Migration:**
  - Completely isolated domain (`freeathome_ng`), device identifiers, entity unique IDs, event bus names (`freeathome_ng_event`, `freeathome_ng_scene_triggered`, `freeathome_ng_virtual_device_command`), services, and optional `name_prefix` for safe side-by-side operation alongside the classic XMPP `freeathome` integration.
  - Non-destructive setup pre-fill (`host`, `use_room_names`, `switch_as_x`) when a legacy `freeathome` entry is detected.
  - Built-in 3-stage migration engine (`freeathome_ng.migrate_from_legacy` with `SupportsResponse.ONLY`): read-only `dry_run` preview, non-destructive side-by-side metadata sync (`cutover: false`), and atomic cutover (`cutover: true`) preserving device names, areas, labels, entity metadata, Assist/Google/Alexa exposure, explicit display precision, downstream helpers, and Recorder / Long-Term Statistics history (see [`docs/MIGRATION.md`](docs/MIGRATION.md)).
- **Modern Home Assistant Core Architecture, Diagnostics & Marketplace Packaging:**
  - Fully compatible with Home Assistant `2025.2.0` through `2026.11+` / `2027.x` Core APIs (`entry.runtime_data`, `DeviceEntryType.SERVICE` Hub device linked via `via_device_id`, `async_remove_config_entry_device`, `async_schedule_reload`, `async_update_and_abort`, zero-arg `OptionsFlow`, `UnitOfDensity`/`UnitOfRatio`, `native_*_temperature`, `AddConfigEntryEntitiesCallback`, `PARALLEL_UPDATES = 0`, `async_get_device_by_identifier`).
  - Redacted Hub and per-device diagnostics (`diagnostics.py`) with minimal entity attributes for zero Recorder bloat.
  - Home Assistant Marketplace (`2026.11+`) and HACS ready (`"integration_type": "hub"`, `"categories": ["hubs_protocols"]`, brand PNG assets, Hassfest & HACS CI validation).
- **7-Language Localization & Comprehensive Verification:**
  - Complete UI, config/options flow, entity, and service translations across English (`en`), German (`de`), Dutch (`nl`), French (`fr`), Italian (`it`), Spanish (`es`), and Polish (`pl`).
  - Full unit test suite, AST `api/` isolation guard, recursive translation parity checks, engineering handbook (`AGENTS.md`, `docs/HA_INTEGRATION_STANDARDS.md`), and standalone mock SysAP REST & WebSocket server (`tests/mock_sysap_server.py`).
