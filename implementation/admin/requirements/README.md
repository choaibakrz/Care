# What the console needs from the server

The admin console (`implementation/admin/`) is a thin client of the clinic server. These files say exactly what it calls, what JSON it reads, and what it does when a route is missing, so the server can be built to match. The console is written against these files; its readers are tolerant (unknown fields are dropped, a 404 means "not on this server yet"), so nothing breaks while the server catches up.

Each file has: endpoints with exact JSON examples, error codes, WebSocket messages, behaviour rules, and the console files that read them. The JSON examples are also the console's test fixtures.

| File | What | Server status (2026-11-15) |
| --- | --- | --- |
| [`emergency-mode.md`](emergency-mode.md) | One switch: the server refuses non-emergency requests, robots clear the corridors. Patient alarms are never touched. | Not started |
| [`tablets.md`](tablets.md) | Tablets on the 3D map: kind, label, speciality, battery, free or in use; free a tablet, hand one out | `/live` positions exist; registry, battery, free/assign missing |
| [`monitoring-security.md`](monitoring-security.md) | Health, traffic, per-address activity, automatic and manual blocks, service counts | Rate limiter exists (T7, todo); the rest missing |
| [`incidents.md`](incidents.md) | Rooms coloured by incident, patient alarms mirrored from the emergency service | Routes exist; emergency mirror and colours are `todo!` (T11c) |
| [`map-route-heat.md`](map-route-heat.md) | Live plan reload, route estimate, heat map | `map.updated` not published (T10b); route and heat work |

## Rules that hold for all of them

- **No patient data.** No patient name, no diagnosis, no "issue kind", anywhere. Staff appear only by pseudonym. Service statistics are counts.
- **The emergency stop is never in the way.** No rule, block, mode or limit may refuse `POST /robots/{id}/command` from an authenticated admin, or cut a robot off.
- **Admin only** for everything here, except `GET /system/mode` (any signed-in user).
- **Errors** as today: `{"error": {"code": "...", "message": "..."}}`. The console shows `message` as is, so it must be safe to show and in plain words.
- **Audit**: every change made through these routes is journaled with who, what and why.

## Order that gives the most for the least

1. `map.updated` (a few lines: the event type and the hub exist), and the emergency mirror (T11c): without it, patient alarms never reach the map.
2. `GET/PUT /system/mode` + the 503 filter (one middleware with an allow-list).
3. `GET /monitor/summary` and `/monitor/traffic` (counters around the existing stack).
4. Block rules + `/monitor/clients` + `security.alert`.
5. Tablet registry, `battery_pct`, free and assign.
6. `GET /stats/service`.

To see what the console does with each, run it in demo mode (`pnpm dev`): the in-browser demo server implements all of the above with the same rules, under `src/mock/`.
