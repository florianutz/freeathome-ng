# Migration Guide: Legacy `freeathome` → free@home NG (`freeathome_ng`)

This step-by-step guide helps you migrate safely from the classic XMPP-based `freeathome` custom integration to **free@home NG (`freeathome_ng`)**—preserving your **device names, areas, labels, entity custom names, icons, aliases, Voice/Assist exposure, dashboards, automations, helpers (`switch_as_x`, `integration`, `utility_meter`), and historical Recorder / Long-Term Statistics data**.

---

## 1. Before You Start (Prerequisites & Backup)

1. **Home Assistant version:** `2025.2.0` or newer (fully compliant with `HA 2026.11+` / `2027.x`).
2. **Create a Backup first:**
   - Go to **Settings → System → Backups → Create Backup** before running a cutover migration.
3. **Install and set up `freeathome_ng` side by side:**
   - Install **Busch-Jaeger / ABB free@home NG (Local API)** via **Settings → Marketplace** (`HA 2026.11+`) or **HACS** (`HA 2025.2–2026.10`) and restart Home Assistant.
   - Add your SysAP under **Settings → Devices & Services → Add Integration → free@home NG**.
   - **Important:** When legacy `freeathome` is installed, `freeathome_ng` automatically pre-fills `host`, `use_room_names`, and `switch_as_x` from your legacy entry so platform domains (`light` vs. `switch`) match cleanly. Verify `switch_as_x` matches your legacy setting before running a cutover.
4. **Recommendation for initial testing:** Set **Optional entity name prefix** (`name_prefix`) to e.g. `NG ` during parallel testing, then clear it in integration options right after cutover.

> [!IMPORTANT]
> **Keep legacy `freeathome` installed until the migration finishes!**
> `freeathome_ng` reads your legacy config entry, device metadata, and entity registry entries directly from Home Assistant. Do **not** remove the legacy integration beforehand.

---

## 2. What Gets Migrated Automatically vs. What Needs Manual Updates

| Item | Side-by-Side Mode (`cutover: false`) | Full Cutover Mode (`cutover: true`) |
|---|---|---|
| **Device Name (`name_by_user`), Area & Labels** | Copied to `freeathome_ng` devices | Copied to `freeathome_ng` devices |
| **Entity Custom Name, Icon, Area, Aliases, Labels** | Copied to `freeathome_ng` entities | Copied to `freeathome_ng` entities |
| **User Disabled / Hidden State** | Copied (user-only; system defaults untouched) | Copied (user-only; system defaults untouched) |
| **Assist / Google / Alexa Exposure & Explicit Display Precision** | Copied to `freeathome_ng` entities | Copied to `freeathome_ng` entities |
| **`entity_id` + Recorder History & Long-Term Statistics** | Legacy keeps old `entity_id`s (parallel testing) | **Legacy entry removed & `freeathome_ng` reuses exact old `entity_id`s** |
| **Downstream Helpers (`switch_as_x`, `integration`, `utility_meter`)** | Remain linked to legacy `entity_id`s | **Continue seamlessly** once `freeathome_ng` takes over the original `entity_id`s |

### Why Recorder History & Helpers Stay Intact
In Home Assistant, Recorder history, Long-Term Statistics, dashboards, automations, and helpers (`switch_as_x`, `integration`, `utility_meter`) bind to **`entity_id`**. Because `freeathome_ng` maps every legacy `unique_id` deterministically (including hardware channels `<serial>/chXXXX`, multi-sensor datapoints `<serial>/chXXXX/odpXXXX`, dimming status `<serial>/chXXXX/dimming_status`, thermostat temperatures `<serial>/chXXXX/current_temperature`, and SysAP-prefixed scenes/virtual devices `<sysap_id>/FFFF.../chXXXX`), renaming same-domain `freeathome_ng` entities back to your original `entity_id`s keeps your entire history continuous with zero gaps.

- **Note on `switch_as_x`:** If your legacy integration used `switch_as_x: true` (creating `switch.*`) while `freeathome_ng` used `switch_as_x: false` (creating `light.*`), or vice versa, those entities changed domain (`domain_changed_entities`). Home Assistant does not allow renaming `switch.*` to `light.*`; metadata and Assist exposure are still copied, while `entity_id` renaming is skipped for those cross-domain entities.

---

## 3. Step-by-Step Migration (`freeathome_ng.migrate_from_legacy`)

Open **Developer Tools → Actions** (*Entwicklerwerkzeuge → Aktionen*) and run `freeathome_ng.migrate_from_legacy` in up to three stages:

### Step 1: Mandatory Dry-Run Preview (`dry_run: true`)

Nothing is modified during a dry run—inspect the exact plan first:

```yaml
action: freeathome_ng.migrate_from_legacy
data:
  dry_run: true
  cutover: true
```

*(If you run multiple SysAP hubs, also pass `entry_id: "<your_hub_entry_id>"` or `host: "<sysap_ip>"`.)*

Inspect the YAML response carefully:
- **`summary`:** Counts of legacy devices/entities discovered, device metadata updates, same-domain entities (`history_preserved: true`), `domain_changed_entities`, `missing_ng_entities`, `conflicts`, and legacy entries to remove.
- **`entity_migrations`:** Lists every legacy `entity_id` alongside its matched `freeathome_ng` entity and confirms `will_rename_entity_id` / `history_preserved`.
- **`conflicts`:** Any `entity_id` currently held by a third integration (neither `freeathome` nor `freeathome_ng`). Metadata is still copied without forcing an ID collision.
- **`warnings`:** Highlights `switch_as_x` mismatches, active `name_prefix`, and event/service renames to apply after cutover.

### Step 2 (Optional): Copy Metadata Side by Side (`cutover: false`)

To copy device names, areas, labels, entity names, icons, aliases, and Voice/Assist settings while keeping both integrations running in parallel:

```yaml
action: freeathome_ng.migrate_from_legacy
data:
  dry_run: false
  cutover: false
```

### Step 3: Execute Full Cutover (`dry_run: false`, `cutover: true`)

When you are ready to switch over permanently and transfer all `entity_id`s and Recorder history:

```yaml
action: freeathome_ng.migrate_from_legacy
data:
  dry_run: false
  cutover: true
```

**What happens atomically under the hood:**
1. Verifies matching `freeathome_ng` entities are present (aborts safely without removing legacy `freeathome` if zero NG matches exist).
2. Enables `suppress_reload` during registry updates to prevent reload storms.
3. Removes the legacy `freeathome` config entry (and any orphaned legacy entity registry records), freeing up the original `entity_id`s while preserving all Recorder history.
4. Copies device `name_by_user`, `area_id`, and merged `labels` onto `freeathome_ng` devices.
5. Copies entity metadata (`name`, `icon`, `area_id`, `aliases`, `labels`, user-only `disabled_by`/`hidden_by`), renames same-domain entities onto their exact legacy `entity_id`s, and applies entity registry options (Assist/Google/Alexa exposure, explicit `display_precision`) **after** renaming onto the final `entity_id`.

---

## 4. Post-Cutover Cleanup (Automations, Options & Restart)

1. **Clear `name_prefix` (if used during testing):**
   - Go to **Settings → Devices & Services → free@home NG → Configure (Options)** and clear **Optional entity name prefix**.
2. **Update event triggers and legacy service calls in automations/scripts:**
   - Replace bus event `freeathome_event` with **`freeathome_ng_event`** (note: `unique_id` inside event data now carries the `{sysap_uuid}/...` prefix if your automation filters on `event_data.unique_id`).
   - Replace legacy actions with the `freeathome_ng.*` equivalents:
     - `freeathome.cover_force_position` → `freeathome_ng.cover_force_position`
     - `freeathome.thermostat_temperature_correction` → `freeathome_ng.thermostat_temperature_correction`
     - `freeathome.dump` → `freeathome_ng.dump_config`
     - `freeathome.monitor` → `freeathome_ng.monitor`
3. **Restart Home Assistant & verify:**
   - Restart Home Assistant (**Settings → System → Restart**).
   - Open history graphs for key thermostats, power/valve sensors, or utility meters and confirm continuity across the cutover timestamp.
   - Check **Settings → System → Logs** for zero errors or orphaned-entity warnings.
4. **Remove legacy `freeathome` files:**
   - Once satisfied, uninstall the old `freeathome` repository via **Settings → Marketplace** (or **HACS**) and restart Home Assistant once more (also remove any `freeathome:` YAML block from `configuration.yaml` if present).

---

## 5. Selective Metadata Sync & Troubleshooting

### Selective Metadata Sync (`serialnumbers`)
Because legacy `freeathome` uses a **single ConfigEntry for the entire SysAP**, Home Assistant cannot remove only one device from the legacy ConfigEntry during cutover. However, you can test a **dry-run preview** or **side-by-side metadata sync (`cutover: false`)** on specific serial numbers first:

```yaml
action: freeathome_ng.migrate_from_legacy
data:
  dry_run: false
  cutover: false
  serialnumbers: "ABB700DA1DDF, ABB700DB3F2C"
```

### Common Questions
- **Why does `cutover: true` reject `serialnumbers`?**
  Removing a legacy `freeathome` ConfigEntry removes all legacy entities on that SysAP at once. Partial cutover would leave the remaining legacy entities deleted or unmigrated, so `freeathome_ng` explicitly guards against this.
- **I see a `switch_as_x mismatch detected` warning.**
  Check **Configure (Options)** on `freeathome_ng` and align **Expose switch actuators as switches (instead of lights)** with your legacy setup before running `cutover: true` if you want switching entities to keep their exact `switch.*` or `light.*` `entity_id`s and history.
- **One of my `entity_id`s appears under `conflicts`.**
  Another integration (for example a helper or unrelated integration) currently holds that exact `entity_id`. Rename or remove the conflicting entity if you want `freeathome_ng` to take over that exact ID.
