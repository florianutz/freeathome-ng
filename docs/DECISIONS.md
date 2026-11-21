# Architecture Decision Records

Binding design decisions for `freeathome_ng`. Each record states the decision, why it was made, and what it implies. A new decision that overrides an old one gets a new record; the old one is marked *Superseded*.

---

## ADR-001: Entity naming via `has_entity_name` and per-channel sub-devices

**Status:** Accepted (2026-11-21) · **Implemented in:** work package AP4

**Context.** free@home models user-facing *channels*, not physical devices: every channel has its own name and its own room in the free@home app. Multi-gang actuators (for example an 8-gang MDRC switch actuator `B008`) carry channels that live in different rooms under one serial number. Home Assistant requires `has_entity_name = True` (Quality Scale Bronze: has-entity-name), and HA areas are assigned per device. The previous rule ("never set `has_entity_name` globally") avoided the problem by giving up the HA naming model.

**Decision.**
1. Every entity sets `_attr_has_entity_name = True`.
2. Each free@home channel that produces at least one entity becomes its own HA device ("channel device"):
   - identifier `(DOMAIN, f"{sysap_uuid}_{serialnumber}_{channel_id}")`
   - `name` = channel `displayName`, `suggested_area` = channel room
   - `via_device_id` = the physical device
3. The physical device keeps `(DOMAIN, f"{sysap_uuid}_{serialnumber}")`, carries manufacturer, model, firmware and serial, links to the SysAP hub via `via_device_id`, and hosts device-wide diagnostic entities.
4. The primary entity of a channel uses `name = None` (it is named after the channel device). Secondary entities use a `translation_key` (for example "Valve opening", "Temperature").
5. Scenes, groups and SysAP-wide functions (day/night switchover, timer profiles) attach to the SysAP hub device and use their free@home name as entity name.
6. Entity `unique_id` formats do **not** change. Existing `entity_id`s stay in the entity registry; only friendly names of existing installs may change, which is announced in the CHANGELOG.

**Consequences.** Areas work per channel; entity pickers and voice assistants see the same names as the free@home app. `migration.py` must map legacy device metadata (`area_id`, `name_by_user`) onto channel devices; this needs dedicated tests in `test_migration.py` before AP4 merges.

---

## ADR-002: Minimum Home Assistant version 2026.8.0

**Status:** Accepted (2026-11-21) · **Implemented in:** work package AP3

**Context.** v1.0.0 supports HA 2025.2.0 and carries capability guards and fallbacks for old APIs (`via_device`, `async_get_device`, `AddEntitiesCallback`, unit constants, `async_schedule_reload`). Each guard doubles code paths that need testing. `pytest-homeassistant-custom-component` tests against one concrete HA release.

**Decision.** Raise the minimum to **2026.8.0** (`hacs.json`). `async_get_device_by_identifier` and the other registry APIs the code relies on exist in 2026.10 but not in 2026.2; confirm the exact first release before setting the version in AP3. Note that HA 2026.3+ requires Python 3.14. Remove all compatibility guards for older releases. CI tests against the current stable release and HA beta.

**Consequences.** Less code, a single test target, zero deprecation warnings by construction. Users on HA older than 2026.8 stay on v1.0.x.

---

## ADR-003: Test against real Home Assistant, not stubs

**Status:** Implemented (2026-11-21, work package AP2)

**Decision.** Tests use `pytest-homeassistant-custom-component` (real HA core, `hass` fixture, `MockConfigEntry`) and `syrupy` snapshots for entity and device registries per platform. `tests/mock_sysap_server.py` remains the SysAP double. The hand-written HA stubs are retired. Home Assistant 2026.3+ requires Python 3.14, so the test stack and CI use Python 3.14; `requirements_test.txt` pins the HA version under test. Coverage target: > 95 % for the integration package.

---

## ADR-004: Native `event` entities in addition to the bus event

**Status:** Accepted (2026-11-21) · **Implemented in:** work package AP5

**Decision.** Rockers and push buttons get `event` platform entities (with `event_types` and translations), so automations can use the UI. `freeathome_ng_event` on the event bus stays unchanged for backwards compatibility.
