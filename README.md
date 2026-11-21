# ABB / Busch-Jaeger free@home NG (`freeathome_ng`)

[![HA Marketplace](https://img.shields.io/badge/Home%20Assistant-Marketplace-41BDF5.svg?style=for-the-badge)](https://contributors.home-assistant.io/marketplace/)
[![Validate & Test](https://github.com/florianutz/freeathome-ng/actions/workflows/validate.yml/badge.svg?style=for-the-badge)](https://github.com/florianutz/freeathome-ng/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

**free@home NG** is a modern, next-generation Home Assistant custom integration for **ABB / Busch-Jaeger free@home** built 100% on the official **Local REST & WebSocket API** (`/fhapi/v1/api`).

> **Designed for Safe Side-by-Side Testing:**  
> `freeathome_ng` uses a completely separate Home Assistant domain, device identifiers, entity unique IDs, event names, and service namespace. You can install and run it **simultaneously** alongside the classic XMPP-based `freeathome` integration without conflicts, duplicate entity collisions, or unintended automation triggers.

---

## Why `freeathome_ng`?

| Feature | Classic `freeathome` (XMPP) | `freeathome_ng` (Local API) |
|---|---|---|
| **Protocol** | Unofficial XMPP + custom SCRAM/NaCl crypto | Official HTTP/HTTPS REST + WebSocket JSON API |
| **Dependencies** | `slixmpp`, `pynacl` | None (uses Home Assistant's built-in `aiohttp`) |
| **Real-time Events** | PubSub XML updates | Instant WebSocket JSON (`datapoints`, `parameters`, `scenesTriggered`, `devicesAdded`, `devicesRemoved`) |
| **Device Types** | Classic lights, switches, covers, climate, sensors, locks, buttons, scenes | Classic types **plus** Ceiling Fans (`0x00A8`), Shutter Groups (`0x4001`), Timer Profiles (`0x4A00`), Thermostat Fan Stages, Energy Management (PV, Battery, Grid, Home Consumption) |
| **Home Assistant → free@home** | Not supported | **Bidirectional Virtual Devices** (`register_virtual_device`, `set_datapoint`, `EnergyMeterv2`) & **Proxy Actions** |
| **System Notifications** | Not supported | Push notifications to free@home App / Panels via `freeathome_ng.send_notification` |
| **Runtime Configuration** | Reconfigure / reload required | UI **Options Flow** (`name_prefix`, `use_room_names`, `switch_as_x`, HTTPS/SSL, orphan channels) |
| **Migration from Legacy** | Manual YAML / re-setup | Built-in `freeathome_ng.migrate_from_legacy` (**dry-run preview, names, areas, Assist exposure & Recorder history**) |
| **Localization** | Partial (`en`/`de`/`nl` config dialogs only; German-only `names.json`) | Full UI, entity, and service translations across **7 languages** (`en`, `de`, `nl`, `fr`, `it`, `es`, `pl`) |

---

## Side-by-Side Coexistence Guarantees

If you already run the classic `freeathome` integration in Home Assistant, installing `freeathome_ng` will **not** interfere with your existing setup:

1. **Isolated Domain & Directory:** Installed in `custom_components/freeathome_ng/` under domain `freeathome_ng`.
2. **Isolated Device Registry:** Device identifiers use `("freeathome_ng", "{sysap_uuid}_{serialnumber}")` instead of `("freeathome", ...)`, linked under a dedicated SysAP Hub device (`("freeathome_ng", "hub_{entry_id}")`).
3. **Isolated Entity Unique IDs:** All entity unique IDs are scoped to the `freeathome_ng` domain and include `{sysap_uuid}/{serialnumber}/{channel_id}`.
4. **Optional Name Prefix:** Set `name_prefix` (e.g. `NG `) during setup or in the integration options to easily distinguish test entities in dashboards and entity pickers.
5. **Isolated Event Bus Names:** Fires `freeathome_ng_event` (never `freeathome_event`), `freeathome_ng_scene_triggered`, and `freeathome_ng_virtual_device_command`.
6. **Isolated Transport:** Uses HTTP(S) REST & WebSocket (`/fhapi/v1/api`) rather than XMPP port `5222`.

---

## Prerequisites

1. **Home Assistant `2026.9.0` or newer.** Users on older Home Assistant releases stay on `freeathome_ng` 1.0.x.
2. **System Access Point 2.0 (SysAP)** running **firmware ≥ 2.6.0**.
3. **Enable Local API** on your SysAP:
   - In the **free@home Next App** or SysAP Web UI, navigate to *More → free@home Settings → Local API*.
   - Note the **Local API Username** (typically the user's UUID or API login shown there) and password. *(Tip: `freeathome_ng` also automatically resolves normal SysAP usernames via `/settings.json` if needed.)*
4. Local network reachability between Home Assistant and your SysAP (`http://<SysAP-IP>` or `https://<SysAP-IP>`).

---

## Side-by-Side Quickstart

To safely test `freeathome_ng` alongside an existing `freeathome` installation:

1. Install **Busch-Jaeger / ABB free@home NG (Local API)** via Home Assistant Marketplace / HACS (or copy `custom_components/freeathome_ng` into `<config>/custom_components/freeathome_ng`) and restart Home Assistant.
2. Go to **Settings → Devices & Services → Add Integration → free@home NG** (or confirm the automatically discovered SysAP via Zeroconf).
3. **Recommendation for side-by-side testing:** Enter e.g. **`NG `** under `name_prefix` in the setup dialog. Every new entity will be clearly identifiable (for example `light.ng_ceiling_lamp`), leaving all your existing entities and automations completely untouched.
4. Thanks to `suggested_area`, Home Assistant automatically pre-populates your free@home rooms as area suggestions.

---

## Installation

### Via Home Assistant Marketplace (HA 2026.11+, formerly HACS)

Starting with **Home Assistant 2026.11**, HACS is integrated directly into Home Assistant Core under **Settings → Marketplace**. Adding custom repositories requires a connected GitHub account in Marketplace settings.

1. Open **Settings → Marketplace** and connect your GitHub account if not already linked.
2. Open the menu (**⋮**) → **Custom repositories**.
3. Add `https://github.com/florianutz/freeathome-ng` with category **Integration**.
4. Install **Busch-Jaeger / ABB free@home NG (Local API)** and restart Home Assistant.
5. Go to **Settings → Devices & Services → Add Integration** (or accept the discovered SysAP notification) and search for **free@home NG**.

### Via HACS (Home Assistant 2026.9–2026.10)

1. Open **HACS → Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/florianutz/freeathome-ng` with category **Integration**.
3. Install **Busch-Jaeger / ABB free@home NG (Local API)** and restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration** (or accept the discovered SysAP notification) and search for **free@home NG**.

### Manual Installation
Copy `custom_components/freeathome_ng` into your Home Assistant `<config>/custom_components/freeathome_ng` directory and restart Home Assistant.

---

## Migrating from Legacy `freeathome` (History, Names & Areas)

You can migrate cleanly from the classic `freeathome` integration—preserving **device names, rooms/areas, labels, custom entity names, icons, aliases, Voice/Assist/Google/Alexa exposure, downstream helpers (`switch_as_x`, `integration`, `utility_meter`), and full Recorder history / Long-Term Statistics**—using the built-in **`freeathome_ng.migrate_from_legacy`** action:

1. **Preview first (read-only):** Run `freeathome_ng.migrate_from_legacy` with `dry_run: true` and `cutover: true` to inspect every device/entity mapping, `switch_as_x` parity, and potential conflicts.
2. **Optional side-by-side sync:** Run with `dry_run: false, cutover: false` to copy names, areas, and Assist options without removing legacy `freeathome`.
3. **Full cutover with history preservation:** Run with `dry_run: false, cutover: true` to remove the legacy `freeathome` entry and rename same-domain `freeathome_ng` entities back to their original `entity_id`s so graphs, dashboards, automations, and helpers continue seamlessly.

> **Step-by-Step Instructions:** See **[docs/MIGRATION.md](docs/MIGRATION.md)** for the complete migration walkthrough, post-cutover automation event/service updates (`freeathome_event` → `freeathome_ng_event`), and troubleshooting.

---

## Supported Platforms & Devices

- **Light (`light`):** Switching lights (when `switch_as_x` is `false`), Dimmers, Color Temperature lights (Kelvin), RGB lights, Light & Dimming Groups (`0x4000`, `0x4002`).
- **Switch (`switch`):** Switching Actuators (`0x0007`, when `switch_as_x` is `true`), Timer Program Switches (`0x4A00`), SysAP Day/Night Switchover (`0x0025`), and Door Entry / Touch-Panel switches (`0x001D` Call Level, `0x0020` Automatic Door Opener, `0x0021` Corridor Light).
- **Cover (`cover`):** Roller Blinds, Shutters (with slat tilt position), Attic Windows, Awnings, Shutter Groups (`0x4001`), and Forced Position (`freeathome_ng.cover_force_position`).
- **Climate (`climate`):** Room Temperature Controllers (with and without fan speed), Eco Mode preset, Heating/Cooling demand valve attribute, and Temperature Correction (`freeathome_ng.thermostat_temperature_correction`).
- **Fan (`fan`):** Ceiling Fan Actuators (`0x00A8`) with percentage speed control.
- **Sensor (`sensor`):**
  - Weather station (Outdoor Temperature, Brightness/Lux, Wind Speed, Wind Force, Rain)
  - Air Quality (Humidity, CO₂, VOC)
  - Heating/Cooling valve flow & Thermostat current temperature
  - Energy Management (PV Power, Battery Power, Battery SoC, Grid Power, Home Power Consumption, Consumed/Injected Energy, Self-Consumption, Self-Sufficiency)
  - Dimmer rocker status enum sensor (`not_pressed`, `pressed_up`, `pressed_down`, `held_up`, `held_down`)
- **Binary Sensor (`binary_sensor`):** Wall switches/rockers, pushbuttons, motion/presence detectors (with 840 s cyclic keep-alive filter), window/door contacts (with `window_position` attribute `closed`/`tilted`/`open`), smoke/CO detectors, door call sensors (with momentary auto-reset), weather alarms.
- **Button (`button`):** Momentary timed triggers (`0x0045`).
- **Lock (`lock`):** Door opener actuators (`0x001A`, `0x0020`).
- **Scene (`scene`):** Custom and system scenes (`0x4800`–`0x4804`).

---

## Events & Automations

### `freeathome_ng_event`
Fired by binary sensors (wall switches, dimmers, etc.):
```yaml
trigger:
  - platform: event
    event_type: freeathome_ng_event
    event_data:
      unique_id: 00000000-0000-0000-0000-000000000000/ABB700CE9999/ch0000
      command: dim_start # pressed | dim_start | dim_stop
      direction: up      # up | down (for relative dimming)
```

### `freeathome_ng_scene_triggered`
Fired when the SysAP reports a `scenesTriggered` frame over the WebSocket:
```yaml
event_type: freeathome_ng_scene_triggered
```

### `freeathome_ng_virtual_device_command`
Fired when free@home writes to an input datapoint (`idp*`) of a virtual device registered by your integration, enabling bidirectional control of third-party Home Assistant entities from free@home wall switches and scenes!

```yaml
trigger:
  - platform: event
    event_type: freeathome_ng_virtual_device_command
    event_data:
      serialnumber: "6000A1B2C3D4"
      channel_id: "ch0000"
      datapoint_id: "idp0000"
      value: "1"
```

---

## Services (`freeathome_ng.*`)

| Service | Description |
|---|---|
| `freeathome_ng.register_virtual_device` | Register or refresh a virtual/proxy device (`SwitchingActuator`, `DimActuator`, `EnergyMeterv2`, `BinarySensor`, etc.) on the SysAP. Persisted across HA restarts with automatic TTL heartbeat renewal. |
| `freeathome_ng.unregister_virtual_device` | Stop TTL renewal and remove a persisted virtual device (`ttl=0`). |
| `freeathome_ng.set_datapoint` | Write any datapoint value (`idp*` or `odp*` feedback for virtual devices) directly to the SysAP. |
| `freeathome_ng.trigger_proxy_device` | Trigger a proxy device action (`shortpress`, `longpress`, `release`) via `/fhapi/v1/api/rest/proxydevice/...`. |
| `freeathome_ng.send_notification` | Push a notification message to the SysAP (`POST /fhapi/v1/api/rest/notifications`). |
| `freeathome_ng.dump_config` | Export the full JSON configuration model (`freeathome_ng_dump_<host>_<timestamp>.json`) to `<config>/`. |
| `freeathome_ng.monitor` | Record raw WebSocket JSON frames (`freeathome_ng_monitor_<host>_<timestamp>.jsonl`) for debugging. |
| `freeathome_ng.cover_force_position` | Entity service to force a cover `open`, `closed`, or `none`. |
| `freeathome_ng.thermostat_temperature_correction` | Entity service to update a thermostat's temperature offset. |
| `freeathome_ng.migrate_from_legacy` | Preview (`dry_run: true`) or migrate device names, areas, entity metadata, Assist options, and Recorder history (`cutover: true`) from legacy `freeathome`. |

> **Diagnostics:** Download redacted Hub or per-device diagnostic snapshots directly from the Home Assistant UI via **Settings → Devices & Services → free@home NG → ⋮ → Download diagnostics** (or from any individual device page).

---

## Practical YAML Examples

### 1. Create a Virtual Switch & Control Third-Party Entities from a Wall Rocker
Register a virtual switch once via **Developer Tools → Actions** (it remains active automatically across Home Assistant restarts):
```yaml
action: freeathome_ng.register_virtual_device
data:
  native_id: ha_zigbee_desk_lamp
  device_type: SwitchingActuator
  display_name: "Desk Lamp (HA)"
  ttl: 180
```
Link this virtual device to a physical wall switch in the free@home app. Then use this automation to toggle your Home Assistant light (`odp0000` state feedback back to the SysAP is handled automatically or explicitly via `set_datapoint`):
```yaml
alias: "free@home Rocker toggles HA Lamp"
trigger:
  - platform: event
    event_type: freeathome_ng_virtual_device_command
    event_data:
      channel_id: ch0000
      datapoint_id: idp0000
action:
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ trigger.event.data.value == '1' }}"
        sequence:
          - action: light.turn_on
            target:
              entity_id: light.zigbee_desk_lamp
      - conditions:
          - condition: template
            value_template: "{{ trigger.event.data.value == '0' }}"
        sequence:
          - action: light.turn_off
            target:
              entity_id: light.zigbee_desk_lamp
```

### 2. Feed PV Inverter & Battery Telemetry from HA into free@home (`EnergyMeterv2`)
```yaml
action: freeathome_ng.register_virtual_device
data:
  native_id: ha_solar_ems
  device_type: EnergyMeterv2
  display_name: "HA Solar & Battery"
  flavor: "0C"
  ttl: 180
```
Afterward, periodically send your live wattage readings (for example every 10 s or on sensor state change) via `freeathome_ng.set_datapoint` to the generated `6000...` output datapoints (`odp*`) listed in your diagnostics dump.

---

## Documentation

- [Migration Guide](docs/MIGRATION.md) — Step-by-step walkthrough for migrating names, areas, Assist exposure, and Recorder history from legacy `freeathome`.
- [Changelog](CHANGELOG.md) — Release history and implemented features.
- [Contributing](CONTRIBUTING.md) — Local development setup, translation parity, and architecture guidelines.
- [HA Integration Engineering Standards](docs/HA_INTEGRATION_STANDARDS.md) — Architectural patterns, HA Core compatibility tracker, and Marketplace checklist.

---

## Development & Testing

```bash
pytest
ruff check custom_components tests
```

A standalone mock SysAP REST & WebSocket server backed by [tests/fixtures/configuration.json](tests/fixtures/configuration.json) is included at [tests/mock_sysap_server.py](tests/mock_sysap_server.py):

```bash
python3 tests/mock_sysap_server.py --port 8080
```
