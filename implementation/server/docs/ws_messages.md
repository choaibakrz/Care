# WebSocket messages

Two sockets. Every server message is `{ "type", "id": "uuid", "ts": "ISO-8601", ...payload }`.
Unknown types are ignored on both sides, never fatal. Coordinates: metres, x east, y south.
Rust types: `crates/realtime/src/protocol.rs` and `views.rs`.

## `WS /ws` (applications: admin console, tablets)

1. The `Origin` header is checked before the upgrade (403 `origin_not_allowed`).
2. The client's **first message** must be, within 5 s:
   `{"type": "auth", "token": "<token from POST /auth/login>"}`.
   The token never travels in the URL; a `?token=` or `?ticket=` is ignored.
   Missing, late, malformed or refused: the server closes with code **4401** and a reason
   that says which. Robot tokens are refused here (they use `/ws/robot/{id}`).
3. Then the server sends a `snapshot`, then events. Anything else the client sends is ignored.
4. An open `/ws` is **not** rechecked when its token expires or is revoked: the token is
   checked once, at the auth message. Closing sockets on expiry or revocation is left to
   Task 8.

| `type` | Payload | Read by the console |
| --- | --- | --- |
| `snapshot` | `tasks` (unfinished, `TaskView`), `positions` | no |
| `robot.updated` | `robot`: as in `GET /robots`. Sent on change and **at least once per second per connected robot** | yes |
| `task.updated` | `task`: as in `GET /tasks/{id}` | yes |
| `inventory.updated` | `item`: as in `GET /inventory` | yes |
| `zone.updated` | `zone`: as in `GET /zones` | yes |
| `zone.deleted` | `zone_id` | yes |
| `schedule.updated` | `schedule`: as in `GET /schedules` | yes |
| `map.updated` | `clinic_id`, `version` (after the change; the last one for a deleted plan), `active`. Sent after every clinic plan change (create, save, activate, delete). When `active` is `true`, the map changed: fetch `GET /map` again (Task A4) | yes (task F3) |
| `alert` | `level` (`info`, `warning`, `critical`), `kind`, `message` (safe to show); `command` only on `staff_command` alerts (Task A7, see below) | yes (`command`: task F9) |
| `positions.delta` | `robots`, `tablets` (owner label and room only), `removed_tablets`; every 200 ms | no |
| `incident.updated` | `incident`, `colour` | no |
| `resync` | none; a fresh `snapshot` follows (the client fell behind) | no |

`in_deaf_zone`, `going_home` and `mood` (`happy`, `busy`, `deaf`, `charging`, `home`, `alarm`,
`stopped`, `offline`) are derived by the server; the console shows the mood as an emoji.

`state` in `robot.updated` is never `offline`: it is the last reported state; the console
greys a robot whose `last_seen` is older than 5 s, and the server sends an `alert`.

`staff_command` alert (Task A7): when a non-admin (a nurse) sends `pause`, `resume` or
`dock` (`shutdown` is admin only, ruling R24), the server sends a `warning` alert of kind
`staff_command` with the command, so the admin can undo it with
`POST /robots/{robot_id}/commands/{command_id}/revert` (`revertible` says the command has an
inverse; the revert is still refused once another command was sent to the robot, 409
`superseded`, and while the robot is in emergency stop, 409 `estop_latched`). Every other alert has no `command` key. Example (the
canonical `alert` example below is the one the protocol test compares):

```json
{"type": "alert", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "kind": "staff_command", "level": "warning", "message": "Ward 2 nurse #3fa9c1 sent pause to robot r1 (command 6f1c0b9e-1d2a-4c3b-9e8f-0a1b2c3d4e5f). You can revert it.", "command": {"command_id": "6f1c0b9e-1d2a-4c3b-9e8f-0a1b2c3d4e5f", "robot_id": "r1", "command": "pause", "by": "Ward 2 nurse #3fa9c1", "revertible": true}}
```

Slow clients (Task 5): the hub never waits for a client. Events go through one bounded
broadcast queue (`APP_QUEUE_CAPACITY`, 256 events); a client that falls more than 256 events
behind receives `resync` and a fresh `snapshot`, then the live stream again. A client whose
socket does not take an event for 10 s (`APP_SEND_TIMEOUT`, it stopped reading) is
disconnected; the console reconnects and gets a new `snapshot`.

## `WS /ws/robot/{id}` (robots, contract C2)

Native client: the robot token goes in the `Authorization: Bearer` header. Closes with 4403
(token mismatch or not a robot token), 4404 (unknown robot), 4409 (already connected).
Messages: see architecture.md C2 (`hello`, `robot.state`, `task.event`, `inventory.seen`,
`zone.ack` up; `task.assign`, `task.cancel`, `zones.update`, `map.update`, `command` down).
`map.update` carries `version`, the active clinic plan's tag `<clinic id>-v<version>` (the
`ETag` of `GET /map`); it is sent when the active plan changes (saved or another one
activated), never for an inactive plan.

Hub (Task 5): each connected robot has a bounded outbound queue (64 messages) and a separate
priority queue for the emergency stop, always written to the socket first. A full queue is an
error for the sender (`QueueFull`), never a wait. A second connection for a robot already
connected is closed with 4409.

### With `--mock` and the `fake_robot` binary

- Robot tokens of the mock verifier only: `mock-robot` (robot `robot-r2`) and
  `mock-robot-<id>` (robot `<id>`). The live server's verifier never accepts them. The mock
  accepts any robot id (an unknown one is added to `GET /robots`), so there is no 4404 in mock
  mode.
- On connect the server sends `zones.update`; the robot answers `zone.ack`.
- `POST /tasks` sends `task.assign` to a free connected robot (a WebSocket robot such as
  `fake_robot` first, then a demo robot of the destination's floor; ruling R21: never a demo
  robot of another floor, and a demo robot that cannot reach a place answers `failed`
  `path_blocked`); the robot's `task.event`s
  become `task.updated` (a `delivered` also takes one item out of the reserve:
  `inventory.updated`). `POST /tasks/{id}/cancel` sends `task.cancel`.
- `POST /robots/{id}/command` sends `command` (the emergency stop on the priority queue);
  the robot confirms in its next `robot.state` (`paused`, `estop`, ...).
  A robot with no live session gets 409 `robot_offline` (never an accepted receipt), and
  the view changes only after the command was queued.
- A robot that disconnects (or says `hello` without a running task) leaves no hanging task:
  a started one becomes `failed` (`robot_lost`), one only sent to it is queued again.
- The four demo robots of `--mock` are the same simulated driver as `fake_robot`, run
  in-process over the hub instead of a socket; they report `robot.state` every 200 ms.

`fake_robot --server ws://127.0.0.1:8080 --id robot-r2 --simulated` (token from `--token` or
`ROBOT_TOKEN`, default `mock-robot-<id>`): `hello`, then `robot.state` every second
(`--state-interval-ms`) while looping along `--round` (default `dock-a,reception,therapy-1`
of the seed plan); on `task.assign`: `task.event` `assigned` at once, `en_route` 2 s later,
`delivered` 2 s after that, or once it reaches a destination on its floor if that takes
longer (a destination off its floor or off the plan keeps the 2 s timeline without moving and
logs a warning on stderr); on `shutdown` a running task is answered `failed` (`robot_lost`); a second task while busy is answered `failed` (`handed_to_human`). It obeys `pause`,
`resume`, `estop`, `dock` and `shutdown` (it exits) and answers `zones.update` with
`zone.ack`. Its motion is simplistic (see `docs/dev-setup.md`); everything is simulated and
`hello` says `simulated: true`.

## Task A8: emergency mode, tablets, security alerts

- `mode.updated {mode: {mode, since, by, reason}}`: sent to every app on each switch of emergency mode (`PUT /system/mode`), with an `alert` (`emergency_mode_on`, critical, on entry; `emergency_mode_off`, info, on exit). The `snapshot` carries the same `mode` object. While the mode is on, every REST call off the allow-list is 503 `emergency_mode` (`architecture.md` C3).
- `device.updated {device}`: the full tablet object of `GET /devices` on every assign, free, online or offline change, and at most every 10 s per tablet for a battery change. No patient name, no health field.
- `security.alert {alert: {at, kind, ip, message}}`: **admin sockets only**. `kind` is `rate_limited` (at most once per address per minute), `auto_blocked`, `login_burst`, `blocked` (manual) or `unblocked`. A socket whose address gets blocked is closed with code 1008 and the reason "Access from this address is blocked.".
- New `alert` kinds: `emergency_mode_on` (critical), `emergency_mode_off` (info), `command_refused` (warning: a robot did not take a command the server sent on its own; not retried).

## Examples (checked by the tests)

Every block below is parsed by `crates/realtime/src/protocol.rs` tests: robot messages must decode and re-encode identically, application events must equal what the server encodes (with `id` `00000000-0000-4000-8000-000000000001` and `ts` `2026-11-14T08:00:00Z` fixed). Ids, names and numbers are invented.

### Application to server

```json auth
{"type": "auth", "token": "3f9c0d5e-invented-token"}
```

### Server to applications (`WS /ws`)

```json app
{"type": "snapshot", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "positions": {"at": "2026-11-14T08:00:00Z", "map_version": "seed-v2", "robots": [{"battery_pct": 81.0, "floor": 1, "heading_rad": 0.0, "id": "robot-r2", "mic_open": false, "name": "R2", "stale": false, "status": "busy", "task": {"id": "t-17", "kind": "fetch"}, "x": 12.0, "y": 4.0}], "tablets": [{"device_id": "tablet-1", "floor": 1, "owner": "Nurse A", "place": "room-101", "uncertainty_m": 2.5, "x": 20.0, "y": 8.0}]}, "mode": {"mode": "normal", "since": null, "by": null, "reason": null}, "tasks": [{"created_at": "2026-11-14T08:00:00Z", "from_place": "reserve", "history": [{"actor": "server", "at": "2026-11-14T08:00:00Z", "label": "requested"}], "id": "t-17", "item": "blanket", "kind": "fetch", "reason": null, "requested_by": "Nurse A", "robot_id": "robot-r2", "state": "en_route", "to_place": "room-101", "updated_at": "2026-11-14T08:00:00Z"}]}
```

```json app
{"type": "task.updated", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "task": {"created_at": "2026-11-14T08:00:00Z", "from_place": "reserve", "history": [{"actor": "server", "at": "2026-11-14T08:00:00Z", "label": "requested"}], "id": "t-17", "item": "blanket", "kind": "fetch", "reason": null, "requested_by": "Nurse A", "robot_id": "robot-r2", "state": "en_route", "to_place": "room-101", "updated_at": "2026-11-14T08:00:00Z"}}
```

```json app
{"type": "robot.updated", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "robot": {"battery": 81.0, "connected": true, "going_home": false, "holding": "blanket", "id": "robot-r2", "in_deaf_zone": false, "last_seen": "2026-11-14T08:00:00Z", "mic_open": false, "mood": "busy", "name": "R2", "pos": {"floor": 1, "heading": 0.0, "x": 12.0, "y": 4.0}, "role": "porteur", "simulated": true, "state": "busy", "task_id": "t-17"}}
```

```json app
{"type": "positions.delta", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "removed_tablets": ["tablet-2"], "robots": [{"battery_pct": 81.0, "floor": 1, "heading_rad": 0.0, "id": "robot-r2", "mic_open": false, "name": "R2", "stale": false, "status": "busy", "task": {"id": "t-17", "kind": "fetch"}, "x": 12.0, "y": 4.0}], "tablets": [{"device_id": "tablet-1", "floor": 1, "owner": "Nurse A", "place": "room-101", "uncertainty_m": 2.5, "x": 20.0, "y": 8.0}]}
```

```json app
{"type": "inventory.updated", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "item": {"count": 7, "id": "blanket", "label": "Blanket", "last_robot_count": 7, "last_robot_count_at": "2026-11-14T08:00:00Z", "low_at": 3, "place": "reserve", "updated_at": "2026-11-14T08:00:00Z"}}
```

```json app
{"type": "zone.updated", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "zone": {"deliveries": [{"acked_version": 3, "robot_id": "robot-r2", "robot_online": true, "status": "received"}], "enforced_by_gardien": true, "floor": 1, "id": "z-deaf-101", "kind": "deaf", "name": "Room 101 (deaf)", "polygon": [[0.0, 0.0], [5.0, 0.0], [5.0, 4.0]], "version": 3}}
```

```json app
{"type": "zone.deleted", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "zone_id": "z-deaf-101"}
```

```json app
{"type": "schedule.updated", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "schedule": {"enabled": true, "id": "night-restock", "label": "Night restock round", "last_counts": [{"counted": 7, "expected": 8, "item": "blanket", "place": "reserve"}], "last_result": "success", "last_run": "2026-11-14T08:00:00Z", "next_run": "2026-11-14T08:00:00Z", "robot_id": null, "time": "02:30", "timezone": "Europe/Zurich"}}
```

```json app
{"type": "alert", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "kind": "robot_offline", "level": "warning", "message": "Robot robot-r2 has been silent for 5 s."}
```

```json app
{"type": "map.updated", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "active": true, "clinic_id": "seed", "version": 2}
```

```json app
{"type": "resync", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z"}
```

```json app
{"type": "mode.updated", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "mode": {"mode": "emergency", "since": "2026-11-14T08:00:00Z", "by": "Admin A", "reason": "Fire alarm, wing B"}}
```

```json app
{"type": "device.updated", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "device": {"device_id": "tab-spare-1", "kind": "staff", "label": "", "speciality": null, "battery_pct": 100, "online": true, "assigned": false, "place": "nurse-station", "floor": 2, "x": 4.6, "y": 9.5, "uncertainty_m": null, "last_seen": "2026-11-14T08:00:00Z"}}
```

```json app
{"type": "security.alert", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "alert": {"at": "2026-11-14T08:00:00Z", "kind": "auto_blocked", "ip": "203.0.113.42", "message": "203.0.113.42 blocked automatically for 10 min: over 20 requests/s for 5 s."}}
```

```json app
{"type": "incident.updated", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "colour": "orange", "incident": {"acknowledged_by": null, "closed_at": null, "code": {"code": "robot_offline"}, "floor": 1, "id": 4, "last_seen_at": "2026-11-14T08:00:00Z", "opened_at": "2026-11-14T08:00:00Z", "place": "room-101", "repeats": 0, "severity": "warning", "subject": null}}
```

### Robot to server (`WS /ws/robot/{id}`)

```json up
{"type": "hello", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "robot_id": "robot-r2", "role_card": "porteur", "capabilities": ["carry", "count_stock"], "simulated": true, "running_task": null, "ble_id": "RB-R2"}
```

```json up
{"type": "robot.state", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "pos": {"x": 12.0, "y": 4.0, "heading": 0.0, "floor": 1}, "battery": 81.0, "state": "busy", "holding": "blanket", "mic_open": false}
```

```json up
{"type": "task.event", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "task_id": "t-17", "state": "failed", "reason": "item_missing"}
```

```json up
{"type": "inventory.seen", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "place": "reserve", "items": [{"item": "blanket", "count": 7, "uncertain": false}, {"item": "gauze", "count": null, "uncertain": true}]}
```

```json up
{"type": "zone.ack", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "zone_version_by_id": {"z-deaf-101": 3}}
```

### Server to robot

```json down
{"type": "task.assign", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "task_id": "t-17", "kind": "fetch", "item": "blanket", "from_place": "reserve", "to_place": "room-101", "deadline": "2026-11-14T09:00:00Z"}
```

```json down
{"type": "task.cancel", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "task_id": "t-17"}
```

```json down
{"type": "zones.update", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "zones": [{"id": "z-deaf-101", "kind": "deaf", "floor": 1, "polygon": [[0.0, 0.0], [5.0, 0.0], [5.0, 4.0]], "version": 3}], "version": 12}
```

```json down
{"type": "map.update", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "version": "seed-v2"}
```

```json down
{"type": "command", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-14T08:00:00Z", "name": "estop"}
```
