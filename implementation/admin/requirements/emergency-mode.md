# Emergency mode

Status: **the console is ready, the server has none of it yet.** Until the server has it, `GET /system/mode` answers 404, the switch shows "Not on this server" and stays disabled. Nothing else breaks.

## What it is

One switch for the admin. When the clinic has a real emergency (fire, evacuation, mass casualty), the main server stops doing anything that is not needed for it:

- it refuses every request that is not on the allow-list below, with **503 `emergency_mode`**;
- it sends every robot out of the corridors, to its dock;
- it starts no new task and no night round.

**It never touches patient alarms.** Patient calls and staff emergency calls go through the separate emergency service (`implementation/emergency.md`), not through this server. Emergency mode must not depend on that service, and must not slow it down or block it. If anything, the main server's load drops, which helps everyone on the same network.

## Endpoints

### `GET /system/mode` (any signed-in user)

```json
{"mode": "emergency", "since": "2026-11-15T09:12:00Z", "by": "Admin A", "reason": "Fire alarm, wing B"}
```

```json
{"mode": "normal", "since": "2026-11-15T09:40:00Z", "by": "Admin A", "reason": null}
```

- `mode`: `"normal"` or `"emergency"`. Any other value is ignored by the console.
- `since`: when the current mode started (ISO-8601). `null` if never switched since start.
- `by`: the pseudonymous operator label of whoever switched it. `null` before the first switch.
- `reason`: free text given with the switch (max 200 characters), or `null`.

The server keeps the mode in its database, so a restart keeps an emergency on.

### `PUT /system/mode` (admin only)

Body:

```json
{"mode": "emergency", "reason": "Switched on from the admin console."}
```

Answer: 200 with the same shape as `GET`. Switching to the mode it is already in is 200 with no change (idempotent: two admins pressing at once is fine).

Errors (the usual `{error: {code, message}}`):

| Status | Code | When |
| --- | --- | --- |
| 403 | `forbidden` | not an admin |
| 422 | `invalid_field` | `mode` not `normal`/`emergency`, or `reason` too long |

The switch is **always** allowed, in both modes, and is never rate-limited for an authenticated admin.

Each switch is written to the audit journal (`system_mode_changed`: from, to, by, reason).

### WebSocket `/ws`: `mode.updated`

Sent to every app on each switch, and nothing else:

```json
{"type": "mode.updated", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-15T09:12:00Z", "mode": {"mode": "emergency", "since": "2026-11-15T09:12:00Z", "by": "Admin A", "reason": "Fire alarm, wing B"}}
```

Also send an `alert` (`level: critical` on entry, `info` on exit) so tablets that only show alerts see it.

The `snapshot` sent on connect should carry `mode` too (same object). The console also reads `GET /system/mode` at start and every 5 s from the switch itself.

## What is still allowed in emergency mode

Everything not in this table answers **503**, code `emergency_mode`, message `"The clinic is in emergency mode: only emergency actions are accepted."` (the console shows the message as is).

| Allowed | Why |
| --- | --- |
| `POST /auth/login`, `GET /me` | People must still sign in |
| `GET/PUT /system/mode` | To see it, and to leave it |
| `POST /robots/{id}/command` (all commands, estop first) | Robots must stay controllable |
| `GET /robots`, `GET /map`, `GET /live`, `GET /zones`, `GET /tasks`, `GET /tasks/{id}` | The map and lists the admin needs to see what happens |
| `POST /tasks/{id}/cancel` | Cancelling reduces work, it never adds any |
| `PUT /me/location`, `POST /me/scans` | Knowing where staff are matters most now |
| `POST /devices/me/events` | Device faults must still be reported |
| `GET /incidents`, `POST /incidents/{id}/ack`, `POST /incidents/{id}/close` | Incident handling |
| The monitor and security routes (`monitoring-security.md`) | An attack can be the cause of the emergency |
| `/ws`, `/ws/robot/{id}` | Live view and robot links stay open |

Refused, for example: `POST /tasks` (new requests), `POST /inventory/{item}/adjust`, `PUT/DELETE /zones/{id}`, `PUT /schedules/{id}`, every `/clinics` write, `/brain/*`, `/stats/*`.

## What happens to robots and tasks

On entry:

1. A robot with no task, or driving home: send `dock`.
2. A robot with a task and nothing in its hands: `task.cancel`, the task goes back to `requested` (history entry `"held: emergency mode"`), then `dock`.
3. A robot carrying an item (it refuses `dock`): `pause` where it is. Remember that the server paused it.
4. Robots in `estop` or `fault`, or already charging: leave them alone.
5. No task is handed out and no night round starts while the mode is on.

On exit:

1. `resume` only the robots the server paused in step 3.
2. Hand out the queued tasks again as usual.

The robot keeps the last word: if it refuses a command, the server keeps the refusal in the audit journal and shows it in an `alert`. It does not retry in a loop.

## Where the console does this

| What | File |
| --- | --- |
| The switch (own network code, polls every 5 s, works if the rest of the page crashed) | `src/estop/mode.ts`, `src/estop/EmergencyStop.tsx` |
| Readers | `src/lib/adapt.ts` (`toMode`, `mode.updated`) |
| Client | `src/lib/http.ts` (`getMode`, `setMode`: 404 means "not on this server") |
| Banner on every page, buttons disabled | `src/ui/Shell.tsx` (`EmergencyBanner`), `src/state/store.ts` (`useEmergency`) |
| Demo behaviour (same rules) | `src/mock/sim-admin.ts` (`setMode`, `requireNormal`) |
| Tests | `src/mock/emergency.test.ts` |

Leaving the mode takes a second click ("Back to normal"). Entering it takes one.
