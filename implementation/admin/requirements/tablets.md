# Tablets on the map

Status: **partly on the server.** `GET /live` already lists the live tablets (`device_id`, `owner`, `place`, `floor`, `point`, `uncertainty_m`) and `positions.delta` carries them: the console draws those today. Everything below marked **new** is missing; until it exists the console shows "battery not reported", treats every live tablet as an in-use staff tablet, and says "This server has no tablet registry yet" instead of the free / hand-out buttons.

## Privacy rules (unchanged, and stricter for bedside tablets)

- A staff tablet's `label` is the owner label: a **pseudonym** ("Dr. A", "Ward 2 nurse"), 1 to 40 characters, not digits only. Never a full name. Same rule as `OwnerLabel` today.
- A bedside tablet's `label` is the **bed**, never the patient: "Bed 12". The server must refuse anything that is not a bed label for a bedside tablet if it can tell (it cannot fully, so the console says it next to the field).
- **No health field at all.** No diagnosis, no condition, no "issue kind". What a bed needs is visible only through the open tasks to its room (item and state), which the console already shows.
- `speciality` exists for **staff** tablets only (work information: "Cardiology", "Nursing"). Always `null` for bedside tablets.
- The console drops any field not listed here (`src/lib/adapt.ts`, `toTablet`). In Presenter mode (the big screen) it shows only "Staff" or "Bed", never the label.
- The tablet positions are never persisted (ruling R1 stays).

## Tablet object (new fields in **bold**)

```json
{
  "device_id": "tab-bed-12",
  "kind": "bedside",
  "label": "Bed 12",
  "speciality": null,
  "battery_pct": 64,
  "online": true,
  "assigned": true,
  "place": "room-12",
  "floor": 2,
  "x": 20.9,
  "y": 4.1,
  "uncertainty_m": null,
  "last_seen": "2026-11-15T09:12:00Z"
}
```

| Field | | Meaning |
| --- | --- | --- |
| `device_id` | exists | Device id |
| **`kind`** | new | `"staff"` (goes with a person) or `"bedside"` (stays with a bed) |
| **`label`** | new (today: `owner`) | Owner pseudonym or bed label; `""` when free. The console also reads `owner` |
| **`speciality`** | new | Staff only, or `null` |
| **`battery_pct`** | new | 0 to 100, reported by the tablet with its location heartbeat; `null` if unknown |
| **`online`** | new | Heard within the last 120 s (the existing tablet expiry) |
| **`assigned`** | new | `false`: nobody uses it, it is free to hand out |
| `place` | exists | Room it is in (staff), its bed's room (bedside), its shelf (free) |
| `floor`, `x`, `y` | exists | As `positions.delta` (`/live` nests them in `point: {x, y}`, both are read) |
| `uncertainty_m` | exists | As today |
| **`last_seen`** | new | Last heartbeat |

## Endpoints (all admin only)

### `GET /devices` (new): the registry

Every registered tablet, **including free and offline ones**, as a JSON array of tablet objects (or `{items: [...]}`). The console merges it with `GET /live` by `device_id` (the registry says who, `/live` says where). If this answers 404 the console falls back to `/live` only.

### `POST /devices/{id}/disconnect` (new): free a tablet

Body `{}`. Revokes the tablet's session token at once (the person is signed out), clears `label` and `speciality`, sets `assigned: false`, puts it back on its shelf `place`. Answers the updated tablet object.

| Status | Code | When |
| --- | --- | --- |
| 404 | `not_found` | unknown device |
| 409 | `already_free` | it is already free |

Audit: `device_freed` with the device id (no label for staff tablets).

### `POST /devices/{id}/assign` (new): hand out a free tablet

```json
{"kind": "staff", "label": "Dr. C", "speciality": "Neurology", "place": null}
```

```json
{"kind": "bedside", "label": "Bed 12", "speciality": null, "place": "room-12"}
```

Answers the updated tablet object. The tablet's next login is bound to this assignment.

| Status | Code | When |
| --- | --- | --- |
| 404 | `not_found` | unknown device |
| 409 | `in_use` | it is assigned: free it first |
| 409 | `offline` | it is not connected |
| 422 | `invalid_field` | label empty, longer than 40, digits only; bedside without a patient-room `place`; `speciality` on a bedside tablet |

Audit: `device_assigned` with the device id, the kind, and the label for bedside tablets only.

Both actions are allowed in emergency mode (handing a tablet to a doctor may be part of the emergency).

### WebSocket `/ws`

- **`device.updated`** (new): the full tablet object, on every assign, free, online/offline change, and at most every 10 s for battery changes.

```json
{"type": "device.updated", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-15T09:12:00Z", "device": {"device_id": "tab-spare-1", "kind": "staff", "label": "", "speciality": null, "battery_pct": 100, "online": true, "assigned": false, "place": "nurse-station", "floor": 2, "x": 4.6, "y": 9.5, "uncertainty_m": null, "last_seen": "2026-11-15T09:12:00Z"}}
```

- `positions.delta` (exists): the console reads its `tablets` and `removed_tablets`. A removed tablet that the registry knows turns **offline** on the map; without a registry it disappears.

## Where the console does this

| What | File |
| --- | --- |
| Readers (drop unknown fields, cut long labels) | `src/lib/adapt.ts` (`toTablet`, `device.updated`, `positions.delta`) |
| Client (`/devices` with fallback to `/live`) | `src/lib/http.ts` (`getTablets`, `disconnectTablet`, `assignTablet`) |
| Store (positions, offline on removal) | `src/state/store.ts` (`moveTablets`) |
| 3D marker (label hidden in Presenter mode) | `src/scene/TabletMarker.tsx` |
| Side panel (list, detail, free, hand out) | `src/pages/live/TabletList.tsx`, `src/pages/live/TabletDetail.tsx` |
| Demo tablets (same rules) | `src/mock/sim-tablets.ts` |
| Tests | `src/mock/tablets.test.ts` |
