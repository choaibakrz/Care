# Map format

The clinic map is a **clinic plan** (Task A4): one versioned document per clinic, in the admin
console's map shape. The seed plan is `seed/clinic_map.json`, exported from the console's demo
clinic by `scripts/export_console_clinic.mjs`; admins store, edit and activate plans through
`/clinics`. All data is invented (`"marque": "inventé"`).

## Coordinate frame

- Metres. **x grows east, y grows south** (a top-down screen view: the admin console draws
  `[x, y]` as screen coordinates). z grows up; floor `n` is at `n × 3.5` m.
- Heading: radians, 0 = east, positive turns toward south (clockwise on screen).
- Points are `[x, y]` pairs everywhere (seed file, API, WebSocket).
- The 2D geometry (polygons, distances, containment, positioning) does not depend on the
  orientation; only this documented frame and the seed data follow it.
- Three.js (y up): `three.x = x`, `three.y = elevation_m (+ height)`, `three.z = y`.

Before Task A3 the frame was "y north"; no geometry code changed.

## Clinic plan (`locations::ClinicPlan`)

`seed/clinic_map.json`, the body of `POST /clinics` and `PUT /clinics/{id}`, the answer of
`GET /clinics/{id}`. Unknown keys are refused.

| Key | Content |
| --- | --- |
| `marque` | optional, `"inventé"` for invented data |
| `name` | display name, 1 to 80 characters |
| `floors[]` | `{id: level (0 ground), label, outline}` |
| `rooms[]` | `{id, floor, label, kind, polygon, label_at?}`; kinds `room`, `corridor`, `elevator`, `care`, `storage`, `therapy`, `pool`, `lounge` |
| `walls[]` | `{id, floor, points}`: open polylines; a door is a gap between two walls |
| `places[]` | `{id, label, floor, x, y, kind}`: the points robots go to; kinds `room`, `shelf`, `dock`, `point` |
| `props[]` | `{id, floor, kind, x, y, width, depth, solid}`: furniture centred on `(x, y)`; `solid` props block the route planner |
| `connections[]` | optional, `{from, to, metres}`: walkable links the drawing cannot show, chiefly a lift between two floors (the only links between floors). Absent means none; the console does not send it today |

`ClinicPlan::validate` checks the whole plan and lists **every** problem with a path
(`rooms[3].polygon: edges 1–2 and 3–4 cross`); the API answers 422 `invalid_plan` with
`error.details`. The checks are in its rustdoc. A valid plan becomes the model
(`locations::ClinicMap`): floors with wall segments, one place per plan place (footprint = the
smallest room containing it), links between the places of each floor, one link per
`connections` entry, and obstacles (solid props, lifts). Without a connection there is no
link between floors.

There is **one description of a clinic** (ruling R14): the model is always derived from a
plan, in production and in tests (`tests/support/map.rs` is a plan with a lift connection).
There is no second file format.

## `GET /map`

The active plan with its identity: `{clinic_id, version, name, floors, rooms, walls, places,
props}` (`locations::MapView`). The `ETag` is `<clinic id>-v<version>`; `If-None-Match` gives
304. On `map.updated` with `active: true` the console fetches it again.
