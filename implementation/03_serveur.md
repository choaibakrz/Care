# Job 3: Backend engineer

**Mission:** the central server is the single source of truth: users, task queue, inventory, map, zones, robot status, audit log. Three other jobs wait on you, so ship the **spec and a mock in the first hour**, then the real thing.

You own `implementation/server/`. Stack: Rust, axum, tokio, PostgreSQL (your earlier choice).

Read first: [architecture.md](architecture.md) (contracts C2, C3), `briques/clinique/taches.py` (task states), `briques/clinique/repartiteur.py` (how a robot is chosen), `briques/clinique/cartes.py` and `cartes_de_role/*.yaml` (role cards), `briques/clinique/badges.yaml` (roles), `briques/clinique/faux_dossier/{lieux,reserve}.yaml` and `flotte.yaml` (seed data), `briques/clinique/carnet.py` (the audit log), `commun/monde.yaml` (places with coordinates).

## The existing Python is your reference

`briques/clinique/` already implements the behaviour you need, in Python, with tests. Do not guess at the rules: **port them**, and use the Python tests as the specification.

| Behaviour | Python reference | You |
| --- | --- | --- |
| Task states and transitions | `taches.py` | Same six states, same legal transitions |
| Choose a robot: nearest free, right role card, enough battery, relay between two robots | `repartiteur.py` | Same decision, same "hand to a human if none can" fallback |
| Role cards: allowed places, max speed, allowed actions | `cartes_de_role/*.yaml`, `cartes.py` | Load the YAML as seed data, serve it |
| Reserve and stock | `faux_dossier/reserve.yaml` | Seed the inventory table |
| Audit trail | `carnet.py`, `b12_boite_noire` | Append-only table |
| Roles | `badges.yaml` | `nurse`, `doctor`, `therapist`, `reception`, `admin`, `robot` |

## What you build

### P0. Spec and fakes (first hour, unblocks everyone)
- [ ] `openapi.yaml` for contract C3 and `ws_messages.md` for contract C2. Every request, response, error and WebSocket message with an example. Get jobs 1, 2, 4, 5 to read it and sign off. **This is milestone M0.**
- [ ] A **mock server** that answers every call with fixed data (a tool such as Prism on `openapi.yaml`, or a tiny axum stub). Jobs 4 and 5 build against it right away.
- [ ] A **fake robot script** that connects to `/ws/robot/{id}`, sends `hello` and `robot.state` moving along a path, and acknowledges tasks. Jobs 4 and 5 need a moving robot to test against.

### P0. The real server
- [ ] **Schema and migrations** (sqlx): `users`, `robots`, `tasks` (state, requester, item, from/to place, timestamps, failure reason), `inventory` (item, count, low-stock threshold), `places` (name, floor, coordinates), `zones` (kind, floor, polygon), `schedules`, `audit_log`.
- [ ] **Seed importer:** load the existing YAML files above into the database on first start. The data is invented and the seed must say so.
- [ ] **Auth:** login returns a token and a role. Start simple (the existing badge pick is not real authentication; a username and PIN per demo user is enough), but design for real hashing (argon2) so it can be upgraded. Check roles on every route.
- [ ] **REST routes** from C3: auth, position, tasks, inventory, map, zones, robots, schedules, audit.
- [ ] **WebSocket hub:** one endpoint for the apps (`/ws`), one per robot (`/ws/robot/{id}`). Push `task.updated`, `robot.updated`, `inventory.updated`, `zone.updated`, `alert` to every connected app.
- [ ] **Dispatcher:** on a new task, choose a robot with the same rules as `repartiteur.py` and send `task.assign`. If none fits, mark the task as handed to a human with the reason.
- [ ] **Robot disconnect:** if a robot goes silent for 5 s, mark it `offline`, reassign its running task if safe, raise an `alert`. When it reconnects, take its state as the truth for what it was doing.
- [ ] **Stock rules:** `delivered` fetch tasks decrement the inventory. `inventory.seen` from the robot overwrites a count when confident, and flags a mismatch otherwise. Never let a count go negative.
- [ ] **Audit log:** every state change, login and admin action, with who and when. Append-only: no update or delete route exists.

### P1. Night restock schedule
- [ ] A scheduler (tokio) that creates `restock_round` tasks at the configured time. The schedule is editable by an admin through `PUT /schedules/{id}`.
- [ ] Low-stock report after a round: items below threshold, listed for the admin.

### P1. Map and zones
- [ ] Places need **coordinates and floors**. `lieux.yaml` has names and floors only; `commun/monde.yaml` has x, y positions for a different hall. Agree one map format with jobs 2 and 5 (places with x, y in metres and a floor, plus walls as polygons for the 3D view).
- [ ] When an admin changes a zone, save it, broadcast `zone.updated` to apps, and send `zones.update` to every robot. If a robot is offline, send on reconnect.

### P2. Extras
- [ ] OpenAPI-generated client stubs for Dart and TypeScript (spares jobs 4 and 5 hand-writing models).
- [ ] Hash-chained audit entries so tampering is detectable.
- [ ] Export the audit log as CSV.

## Rules for you

- **The server never stores images, audio or health content.** A task has an item, two places and a state. Not a diagnosis, not a photo.
- **The server cannot move a robot.** It creates tasks. The robot decides, through the gardien. Do not add any "drive to x, y" endpoint.
- **`estop` is the only command to pass straight through**, and it needs the admin role. It must work when the dispatcher is stuck (separate code path, tested).
- Every error returns `{ "error": { "code", "message" } }` with a message safe to show.
- Time zone: store UTC, send ISO-8601.
- The demo runs offline on a laptop. A single `docker`-free way to start (`cargo run` plus a local PostgreSQL via `brew`) beats anything elaborate. If PostgreSQL setup eats time on Saturday, an SQLite fallback is acceptable. Say so to the team, don't switch quietly.

## Interfaces

| You give | To | When |
| --- | --- | --- |
| `openapi.yaml`, `ws_messages.md`, mock server, fake robot | Everyone | M0 |
| Real server | Jobs 2, 4, 5 | M1 |
| Class list and item names (from job 1) as inventory seed | — | M0 |

| You need | From | When |
| --- | --- | --- |
| Class list (`classes.yaml`) | Job 1 | M0 |
| Robot message shapes confirmed | Job 2 | M0 |
| Map format agreed | Jobs 2 and 5 | M1 |

## Tests

Unit tests for the dispatcher against the same scenarios as `repartiteur.py`'s Python tests. Integration test: start the server, connect the fake robot, create a task over REST, assert the full state sequence arrives on the app WebSocket.

## Done when

- A task made over REST reaches the fake robot, the state changes come back, and the app WebSocket shows each one.
- Stock goes down on delivery and a mismatch is flagged when the robot counts differently.
- Killing the robot mid-task produces an `offline` alert within 5 s.
- Role checks hold: a nurse cannot change zones or send `estop`.
