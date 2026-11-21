# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
