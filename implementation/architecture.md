# Clinic Helper Robot: Architecture and Team Plan

Updated Nov 14, 2026, after reading the existing code in `briques/`, `commun/` and `briques/clinique/`.

Five people build five parts in parallel. They talk through three written contracts, so any part can run against a fake of the others. **The robot-side Python code already exists and is kept.** This plan adds what is missing around it.

Per-person guides: [01 AI vision](01_ia_vision.md) · [02 Robot](02_robot.md) · [03 Server](03_serveur.md) · [04 Staff app](04_app_personnel.md) · [05 Admin panel](05_admin.md)

## Rules inherited from the existing project (not up for debate)

These come from `AGENTS.md`, `DECISIONS.md` and `docs/projet/REGLES_DES_AGENTS.md`. Every new part must respect them.

1. **Every robot order takes one path:** brain proposes → **gardien** signs a ticket → **prise** checks it → **adaptateur** moves the robot. Nothing new may skip a step. The server and the apps only ever create *tasks*, never motor commands.
2. **Offline.** Everything runs on the team's own computers over the local Wi-Fi. No cloud API, no model downloaded at demo time.
3. **Privacy.** Camera images and audio travel only between the robot and the model service (same machine or LAN). The server stores task type, place, item name and counts, never images, audio or health content. **Texts sent to the server-side brain** (translate, simplify, summarise, report; Task A6) **pass through the server in memory only**: never written to the database, the journal, a log or a temporary file; the journal records only "brain call, kind, latency, ok/failed" (`BrainCall`). Details: `server/docs/brain.md`. **The server never learns who a user is** (Task A7): the user name and the password never leave the device; the client derives an account key (PBKDF2-HMAC-SHA256, 600 000 rounds, salt `clinic:<clinic_id>:<lowercase username>`) and the server keeps only `HMAC-SHA256(pepper, key)` with a pseudonym ("Nurse 7"), a role and a disabled flag; the pepper is a key file outside the database. No user name, e-mail, real name, password or key is stored, logged or journaled; people see an account as `"<pseudonym> #<6-hex tag>"`. A forgotten password cannot be recovered (disable, re-enrol). Details and test vectors: `server/docs/accounts.md`.
4. **No medicine.** The prototype gives no diagnosis or health advice. Data is invented and labelled so.
5. **Say what is tested.** Mark anything not run on a real robot or real camera as "not tested" (see `NON_TESTE.md`). A model's numbers go in a `MESURES.md` with the machine they were measured on.
6. **Do not touch** `briques/b01_prise/prise.py`, `ticket.py` or `briques/b07_gardien/` without the security reviewer (`AGENTS.md`).
7. **Licences.** MIT, Apache and BSD are fine. GPL or AGPL means telling Hiba first (`LICENCES.md`).
8. **Memory budget.** The brain computers are an iMac M4 and a MacBook M2, 16 GB each, also running Apertus 8B and speech. The vision models must stay small (see job 1).

## What already exists and what is new

| Part | Existing code (reuse) | New work |
| --- | --- | --- |
| Speech, translation | `b04_oreilles_voix` (faster-whisper, whisper.cpp, Silero VAD, Piper voices), `clinique/interprete.py` (interpreter mode) | HTTP wrapper only if time allows |
| Brain | `b06_cerveau` (Apertus 8B → 4B → rules cascade, forced form, measured bench) | Nothing required |
| Vision | `b05_yeux`: plug-in `Branchement` interface, MediaPipe EfficientDet-Lite0 (80 generic COCO classes), ArUco, RapidOCR, calibration, camera geometry | **A trained detector and classifier for the clinic's tools** (the main gap) |
| Safety | `b01_prise`, `b07_gardien`, `b08_doute` ("I'm not sure"), `b11_main_humaine` | Nothing. Frozen |
| Robots | `b02_faux_robot` (fake humanoid, dog, arm, wheels), `b03_adaptateurs` (Go2 and ROS 2 drafts) | Optional Webots 3D world |
| Tasks and fleet | `clinique/`: task states, dispatcher (`repartiteur`), role cards, fleet board, `coursier` (runs a fetch under the gardien), badges, reserve, places, black box | **Becomes the robot-side executor.** The server owns the data |
| Screens | `b13_ecran` (FastAPI, jury screen, WebSocket event stream), `clinique/ecrans*.py` (patient, nurse, reception pages) | Flutter staff app and React admin panel replace them for real use. The old pages stay as the offline fallback |
| Event stream | `commun/bus.py`, `commun/evenements.py`, `b12_boite_noire` | One new event family for the server link |

The old Python screens are good UX references: `clinique/ecrans_*.py` and `traductions_ecrans.yaml` show which screens and words the app needs, in five languages.

## How it fits together

```mermaid
flowchart LR
    subgraph Apps
      A[Staff app<br/>Flutter]
      D[Admin panel<br/>React + Three.js]
    end
    S[(Central server<br/>Rust + PostgreSQL)]
    subgraph Brain computer: Python, already built
      L[b16 server link<br/>NEW]
      C[clinique: coursier,<br/>task executor]
      B[b06 brain]
      G[b07 gardien]
      P[b01 prise]
      R[Robot or fake robot<br/>b02 / b03]
      Y[b05 yeux]
      E[b04 ears and voice]
    end
    M[Model service<br/>NEW: tool detector,<br/>classifier]
    A <-->|C3 REST + WS| S
    D <-->|C3 REST + WS| S
    S <-->|C2 WebSocket| L
    L --> C --> G --> P --> R
    E --> B --> G
    Y -->|C1 HTTP| M
    Y --> B
    Y --> G
```

The apps and the robot never talk directly. The server passes tasks down and status up. The robot is the only one that talks to the model service.

## How a task runs

1. A nurse taps "bring a blanket to room 12" in the app. **C3:** `POST /tasks`.
2. The server stores it as `requested`, picks the best free robot (nearest, right role card, enough battery) and sends it down. **C2:** `task.assign`.
3. `b16_lien_serveur` hands the task to the existing `Coursier`. Each move goes brain → gardien → prise → robot as usual.
4. The robot looks at the shelf. The vision model confirms the item is there. The robot grabs it, drives to room 12, drops it, and reports each state change up. **C2:** `task.event`.
5. The server updates stock, writes the audit log and pushes the new state to the app and the admin panel. **C3:** WebSocket `task.updated`.

The **night restocking run** is the same loop, started by a schedule on the server. Its only addition: at each shelf the robot sends what it counted (`inventory.seen`).

## The five parts and who owns them

| # | Job | Owns | Guide | Needs from others |
| --- | --- | --- | --- | --- |
| 1 | AI vision engineer | `implementation/model_service/`, new plug-in in `briques/b05_yeux/branchements/` | [01](01_ia_vision.md) | Camera images from job 2, class list agreed with jobs 2 and 3 |
| 2 | Robot engineer | `briques/b16_lien_serveur/` (new), glue in `b04`/`b05`/`clinique`, optional `implementation/sim/` | [02](02_robot.md) | C1 mock from job 1, C2 spec from job 3 |
| 3 | Backend engineer | `implementation/server/` | [03](03_serveur.md) | Nothing. Unblocks jobs 2, 4 and 5 |
| 4 | Staff app developer | `implementation/app/` | [04](04_app_personnel.md) | C3 mock from job 3 |
| 5 | Admin developer | `implementation/admin/` | [05](05_admin.md) | C3 mock from job 3, map data from job 3 |

**Why this split.** The tool-recognition network is the biggest unknown and needs a full-time owner, so job 1 does nothing else. Speech, translation and the brain already work and are measured, so they do not need a new owner. They sit with the robot engineer for integration only. The backend is its own job because three other parts wait on it.

## Contracts (agree on day one, freeze after M0)

Backend writes the full spec as `implementation/server/openapi.yaml` and `implementation/server/ws_messages.md`. This section is the summary everyone reviews first.

### C1. Robot to model service (HTTP, local network)

The robot names an endpoint, never a model. The service decides which model answers (`models.yaml`), so models are swappable.

| Call | In | Out |
| --- | --- | --- |
| `GET /v1/health` | none | loaded models, versions, memory used |
| `POST /v1/detect` | one JPEG (multipart) | boxes with labels, below |
| `POST /v1/classify` | one cropped JPEG | top-k labels with confidence, or `unknown` |
| `GET /v1/classes` | none | the class list and its version |

```json
POST /v1/detect

{
  "model": "tools-det-v1",
  "latency_ms": 74,
  "objects": [
    { "label": "blanket", "confidence": 0.91, "box": [312, 80, 140, 220] },
    { "label": "water_bottle", "confidence": 0.78, "box": [40, 150, 60, 180] }
  ]
}
```

- `box` is `[x, y, width, height]` in pixels, the same shape as `Boite` in `briques/b05_yeux/prise_yeux.py`.
- **No `distance_m` from the service.** The model does not know the camera. The robot computes ground position with its calibration (`b05_yeux/geometrie.py`). This replaces the earlier draft of the contract.
- A label is a key from `classes.yaml` (see job 1), mapped to the world's object name in five languages by the robot side.
- Speech and translation stay in-process (`b04`, `b06`) unless time allows `POST /v1/transcribe` and `POST /v1/translate` wrappers.

### C2. Robot to server (one WebSocket per robot: `/ws/robot/{robot_id}`)

Every message: `{ "type": "...", "id": "uuid", "ts": "ISO-8601", ... }`. Unknown types are ignored and logged, never fatal. Messages over 64 KiB are refused. Exact JSON for every message: `server/docs/ws_messages.md`. On `WS /ws` the server also sends `resync` when an application fell behind (a fresh `snapshot` follows; added to C3).

| Direction | `type` | Payload |
| --- | --- | --- |
| down | `task.assign` | `task_id`, `kind` (`fetch`, `restock_round`, `go_to`, `interpreter_session`), `item`, `from_place`, `to_place`, `deadline` |
| down | `task.cancel` | `task_id` |
| down | `zones.update` | `zones`: every zone (`id`, `kind` (`deaf`, `restricted`), `floor`, `polygon` in metres, `version`), `version`: the zone-set version; an empty list removes every zone |
| down | `map.update` | `version`: the active clinic plan's tag `<clinic id>-v<version>`; the robot fetches `GET /map` (sent when an admin saves the active plan or activates another one) |
| down | `command` | `name`: `pause`, `resume`, `dock`, `estop`, `shutdown` |
| up | `robot.state` | `pos {x, y, heading, floor}`, `battery`, `state` (`idle`, `busy`, `paused`, `fault`, `estop`), `holding`, `mic_open`, every 1 s |
| up | `task.event` | `task_id`, `state`, `reason` (set on failure or handover to a human) |
| up | `inventory.seen` | `place`, `items`: list of `{item, count, uncertain}` (`count` may be `null`) |
| up | `zone.ack` | `zone_version_by_id`: the zone versions the robot has applied (added to C2; the server shows delivery per robot in `GET /zones`) |
| up | `hello` | on connect: `robot_id`, `role_card`, `capabilities`, `simulated`, `running_task`, optional `ble_id` |

Task states: `requested`, `assigned`, `en_route`, `delivered`, `failed`, `resumed`. They match the existing French states in `clinique/taches.py` (`demandée`, `attribuée`, `en route`, `livrée`, `échouée`, `reprise`).

**Server commands are requests, not orders.** `pause`, `dock` and `shutdown` become ordinary actions that go through the gardien. `estop` is the only one that calls the prise's emergency stop directly, because that path needs no ticket by design (`PRISE.md`). The robot must keep working if the WebSocket drops: it finishes or safely stops the current task, buffers events, and resyncs on reconnect.

### C3. Apps to server (REST + one WebSocket)

JSON over HTTP, `Authorization: Bearer <token>`. Roles follow the existing badges (`clinique/badges.yaml`): `nurse`, `doctor`, `therapist`, `reception`, `admin`.

Field names are snake_case, exactly as the admin console reads them (`admin/src/lib/adapt.ts`); clients ignore unknown fields. Coordinates: metres, x east, **y south**, heading 0 = east. The full schema is `server/docs/openapi.yaml`; the live messages are in `server/docs/ws_messages.md`.

| Area | Calls |
| --- | --- |
| Auth | `POST /auth/login {account_key, device_id?}` → `{token, role, operator, expires_at}` (Task A7: `account_key` is the 64-hex key the client derived from user name and password, see `server/docs/accounts.md`; the server never receives either; `operator` is `"<pseudonym> #<tag>"`; unknown key, wrong password and disabled account are the same 401 `invalid_credentials`; a `{username, password}` body is 422 `key_derivation_required`, except in `--mock` until frontend task F9). `GET /auth/derivation` (public) → `{algorithm, iterations, key_bytes, clinic_id, salt}`. `POST /auth/enrol {enrolment_code, account_key, display_label}` (public) → 201 `{account_tag, role, operator}`; 403 `enrolment_refused` (unknown, used or expired code), 409 `account_exists`. Without `device_id` (a browser) the token is bound to no device: `X-Client-Id` is then refused (403 `identity_mismatch`) and the tablet-only calls (`PUT /me/location`, `POST /me/scans`, `POST /devices/me/events`) answer 403 `device_required`. `GET /me` |
| Accounts | Admin only (`manage_accounts`, Task A7): `POST /admin/enrolment-codes {role, label?}` → 201 `{code, code_id, role, label, expires_at}` (single use, 24 h, journaled by `code_id`); `GET /admin/accounts` → `[{account_tag, display_label, role, created_at, disabled}]` (no user name exists to list); `DELETE /admin/accounts/{account_tag}` → 204, disables and revokes tokens (409 `ambiguous_account_tag`, 409 `cannot_disable_self`). No password recovery |
| Position | `PUT /me/location` (room name or QR payload) |
| Tasks | `POST /tasks {kind, item?, from_place?, to_place, deadline?}`, `GET /tasks` → `{items, next}`, `GET /tasks/{id}`, `POST /tasks/{id}/cancel` (admin or requester). Task: `{id, kind, item, from_place, to_place, state, robot_id, requested_by, created_at, updated_at, reason, history[{at, actor, label}]}`; `requested_by` is an owner label |
| Inventory | `GET /inventory` → `[{id, label, place, count, low_at, last_robot_count, last_robot_count_at, updated_at}]`, `POST /inventory/{item}/adjust {delta, reason?}` (admin) |
| Map and zones | `GET /map` → the active clinic plan `{clinic_id, version, name, floors, rooms, walls, places, props}` (walls have an `id`; `ETag` `<clinic id>-v<version>`); `GET /zones` → `[{id, name, floor, kind, polygon, deliveries[{robot_id, status: received\|pending\|failed}], enforced_by_gardien}]`, `PUT /zones/{id} {id, name, floor, kind, polygon}`, `DELETE /zones/{id}` (admin) |
| Clinics | Admin only. A clinic plan is one versioned document `{name, floors, rooms, walls, places, props}` in the map shape above; several are stored, one is active. `GET /clinics` → `[{id, name, version, active, updated_at}]`; `GET /clinics/{id}` → the plan, `ETag` its version; `POST /clinics` (plan) → 201 summary (409 `clinic_exists` when the id derived from the name is taken); `PUT /clinics/{id}` (plan, `If-Match: <version>`) → the plan at `version+1` (428 without `If-Match`, 412 `version_conflict` when stale); `POST /clinics/{id}/activate` (409 `open_tasks` while tasks are open); `DELETE /clinics/{id}` (never the active one, 409 `clinic_active`). Optional `connections[{from, to, metres}]` add links the drawing cannot show (a lift between floors). A refused plan is 422 `invalid_plan` listing every problem; removing a place still used by an open task, a stock item, a schedule or a dock is 409 `place_in_use` listing the users. Each change is journaled and sends `map.updated` |
| Route | `GET /tasks/{id}/route` → `{floor, points[[x, y]], length_m, estimate: true}`: the server's estimate around walls, solid furniture and restricted zones (planning only: the gardien does not enforce them yet; the dispatcher and the tour planner avoid them too, their graph is rebuilt on every zone or plan change); 404 `no_route` with the reason (for example different floors) |
| Brain | Drafts for staff (Task A6); every result has `draft: true` and the UI shows it as a draft a person reads before anything is sent. `POST /brain/translate {text, from?, to}` → `{draft, text, from, to, checks{fixed_terms_ok, numbers_ok}}` (any staff role; `interprete.py`'s fixed terms; French to English only today, any other pair 422 `unsupported_language`; without `from`, French is assumed, no detection); `POST /brain/simplify {text, lang, level: plain\|easy}` → `{draft, text, lang, level, simplified}` (any staff role; `simplified: false` returns the original: "could not simplify safely"); `POST /brain/summarise {sources[{id, kind, text}], lang}` → `{draft, lang, lines[{text, source}], dropped}` (doctor, therapist, nurse; a line whose numbers are not in its source is dropped); `POST /brain/report {kind: shift\|incident\|robot_activity, from, to, lang}` → `{draft, kind, from, to, lang, lines[{text, source}], dropped}` (admin, doctor; sources are server records `task:<id>`, `incident:<id>`, `robot:<id>`); `GET /brain/health` → `{status: up\|degraded\|down, models, queue, detail?}`. Brain down: 503 `brain_unavailable`, everything else keeps working; too slow: 504 `brain_timeout`. `/brain/*` take bodies up to 1 MiB (413 `body_too_large` above) and have a 30 s request timeout (the brain client waits 25 s, one brain call 20 s, Apertus is cut at 15 s for the rules fallback); every other route keeps 64 KiB and 10 s. Texts: memory only (privacy rule 3) |
| Statistics | `GET /stats/heat?floor=` → `{floor, cell_m: 1, origin[x, y], columns, rows, counts[]}` row-major (admin): robot samples per square metre, robots only, never tablets, memory only |
| Service | `GET /stats/service?hours=24` (admin, Task A8, fill T11e) → `{hours, requests, delivered, failed, median_wait_s, p90_wait_s, by_item[{label, count}], by_place[{place, count}], bedside_online, bedside_total}`: counts only, never a person; wait = `requested` → `delivered`; top 6 items and places; a place under `SERVICE_STATS_MIN_COUNT` requests may be folded into `other` (off by default); `hours` 1 to 720 (422 otherwise) |
| Emergency mode | Task A8, fill E1 (`admin/requirements/emergency-mode.md`). `GET /system/mode` (any signed-in caller) → `{mode: normal\|emergency, since, by, reason}`; `PUT /system/mode {mode, reason?}` (admin, `switch_system_mode`) → the same shape, idempotent; 422 `invalid_field` for another mode or a reason over 200 characters; stored (a restart keeps it on), journaled `system_mode_changed`, sends `mode.updated` and an `alert` (`emergency_mode_on` critical, `emergency_mode_off` info). While on, every request off the allow-list is 503 `emergency_mode` "The clinic is in emergency mode: only emergency actions are accepted." (one route layer, `src/emergency_mode.rs`); the allow-list: login and `/auth/derivation`, `GET /me`, `/system/mode`, every robot command (estop first) and the admin's revert, `GET /robots`, `/map`, `/live`, `/zones`, `/tasks`, `/tasks/{id}`, `POST /tasks/{id}/cancel`, `PUT /me/location`, `POST /me/scans`, `POST /devices/me/events`, incidents (list, ack, close), the monitor and block routes, the tablet registry, `DELETE /admin/accounts/{account_tag}` (R26), `/ws`, `/ws/robot/{id}`, `GET /health`. On entry robots leave the corridors (idle: `dock`; a task and nothing held: `task.cancel`, task back to `requested` with history `held: emergency mode`, then `dock`; carrying an item: `pause`, remembered and stored with the mode; estop, fault, already paused (a staff pause is never resumed by the server), charging (not modelled yet): left alone); no task is handed out and no night round starts; on exit only the robots the server paused are resumed. Never touches the emergency service |
| Tablets | Task A8, fill T8b (`admin/requirements/tablets.md`), admin only (`manage_devices`): `GET /devices` → every tablet, free and offline included, `[{device_id, kind: staff\|bedside, label, speciality, battery_pct, online, assigned, place, floor, x, y, uncertainty_m, last_seen}]` (`label` a staff pseudonym or a bed, `""` when free; `speciality` staff only; no patient name, no health field; A5's `patient_name` never appears here); `POST /devices/{id}/disconnect {}` → the tablet (session revoked at once, back on its shelf; 404 `not_found`, 409 `already_free`; journal `device_freed`); `POST /devices/{id}/assign {kind, label, speciality?, place?}` → the tablet (404, 409 `in_use`, 409 `offline`, 422 `invalid_field`: label empty, over 40 or digits only, a bedside tablet without a patient-room place or with a speciality, or whose label is not a bed label `^(Bed|Lit|Bett|Letto) ?\d{1,4}[A-Za-z]?$` (case-insensitive, ruling R26); journal `device_assigned`, the label only for bedside). `device.updated` on every change, battery at most every 10 s |
| Monitor | Task A8, fill T7b (`admin/requirements/monitoring-security.md`), admin only (`monitor_security`), allowed in emergency mode, no personal data, counters in memory only (5 min): `GET /monitor/summary` → `{started_at, uptime_s, version, robots_connected, robots_total, app_clients, journal_ok, database_ok, requests_per_s, rejected_per_s, p95_ms, blocked_clients}`; `GET /monitor/traffic?window_s=300` → `{step_s, p95_ms, points[{at, accepted, rejected}], rejected_by{unauthorized, forbidden, rate_limited, blocked, emergency_mode, invalid}}`; `GET /monitor/clients?limit=20` → `[{ip, label, requests_per_s, requests, rejected, login_failures, status: ok\|limited\|blocked, reason}]` (`label` a known network or `Robot <id>`, never a user name); `GET /security/blocks` → `[{id, target, reason, source: manual\|auto, created_at, expires_at, by, hits}]`; `POST /security/blocks {target, reason, expires_in_s?}` → 201 the rule (422 `invalid_field`, 422 `protected_target` for the caller, loopback, a connected robot or the emergency service, 422 `range_too_broad` beyond /16 or /48); `DELETE /security/blocks/{id}` → 204 (404 `not_found`). Detection (`security::TrafficMonitor`, thresholds in `.env`): 20 requests/s burst 40 per address (429 `rate_limited`), over the limit 5 s in a row or 10 failed logins in 60 s: blocked 10 min; a blocked address gets 403 `blocked` (no detail) and its open WebSockets are closed (1008). Loopback, the address of a robot's current `/ws/robot/{id}` session and the emergency service are never limited or blocked (a robot may always reconnect to its own socket through a block); **an authenticated admin's robot command (estop included), mode switch, monitoring or block request is never refused** (ruling R26: such a request with a well-formed bearer token is decided after identity; from a blocked or limited address anyone but a verified admin gets the 403/429, also when the token is refused). Refused tokens (401) on those deferred routes only (never tablet routes) count per address like failed logins (10 in 60 s: blocked; the block stays alive while guessing continues); a deferrable request is deferred even from a guessing address, so the token verifier takes those guesses and a verified admin's estop always passes (R27). Robot protection follows each `/ws/robot` session (several robots may share an address). Reasons are stored without control, bidirectional, separator or zero-width characters; IPv4-mapped IPv6 blocks are read as IPv4. Journal `client_blocked`, `client_unblocked`; `security.alert` to admin sockets only (at most one `rate_limited` per address per minute) |
| Robots | `GET /robots` → `[{id, name, role, simulated, pos{x, y, heading, floor}, battery, state, holding, mic_open, task_id, last_seen}]` (`state` is never `offline`); `POST /robots/{id}/command {name}` → `{accepted, reason, sent_at, command, command_id}`, a refusal is 409; `pause`, `resume`, `dock` need `robot_control` (admin, nurse), `shutdown` needs `robot_shutdown` and `estop` needs `estop` (both admin only, ruling R24: a nurse's shutdown is 403 `forbidden`). While a robot is in emergency stop a non-admin `resume` is 409 `estop_latched` ("Only an admin can re-arm a robot after an emergency stop."); only an admin's explicit `resume` re-arms it. A non-admin's command raises the alert `staff_command` (warning, with `command: {command_id, robot_id, command, by, revertible}`); `POST /robots/{id}/commands/{command_id}/revert` (admin only, Task A7) → 202 `{reverted_by_command_id}` sends the inverse (`pause` → `resume`, `resume` → `pause`, `dock` → `resume`) and is journaled; estop, shutdown and an admin's own command are 409 `not_revertible`, a second (or concurrent) revert 409 `already_reverted` (reserved under the lock: one inverse is sent), a command that is no longer the robot's latest 409 `superseded`, any revert on a robot in emergency stop 409 `estop_latched` |
| Schedules | `GET /schedules` → `[{id, label, enabled, time "HH:MM", robot_id, last_run, last_result, last_counts}]`, `PUT /schedules/{id} {enabled?, time?, robot_id?}` (admin; the night restock round) |
| Audit | `GET /audit?from=&to=&actor=` → `{items[{id, at, actor, action, target, result: ok\|refused\|failed, detail}], next}` (admin) |
| Live | `WS /ws`: first client message `{type: "auth", token}` within 5 s, else close 4401 (the token is never in the URL). Then `task.updated`, `robot.updated` (at least every second per connected robot), `inventory.updated`, `zone.updated`, `zone.deleted`, `schedule.updated`, `map.updated {clinic_id, version, active}`, `alert {level, message}`, `mode.updated {mode}`, `device.updated {device}` and `security.alert {alert}` (admin sockets only; Task A8; the `snapshot` also carries `mode`) |
| Health | `GET /health` → `{status, journal_writable, version, mode, brain}`; `mode` is `live`, `demo` (`clinic-server --demo`: simulated robots on the active plan, all labelled "SIMULATED") or `mock`; `brain` is `up`, `degraded` or `down` (the separate `clinic-brain` process; `down` never stops the rest of the server) |

Task states add `cancelled` (terminal, from `requested` or `assigned` only) to the six of C2; the Python states do not have it.

**The brain process.** The models (Apertus through the `b06` cascade, whisper) and Python run in a second binary, `clinic-brain`, which embeds the existing Python bricks through `python-bindings` (pyo3) and serves `POST /v1/translate`, `/v1/simplify`, `/v1/summarise`, `/v1/report` and `GET /v1/health` on loopback only, with a shared `BRAIN_TOKEN`. A crash or an out-of-memory in a model never takes down dispatch, the alarm mirror or the emergency stop. Built without the `python` feature (the default), it answers every call with 503 `brain_unavailable` and the main server reports `brain: down`. The robot keeps its own brain and its filtering chain (gardien, prise, b06 rules); the robot speech round trip through the server (C2 `utterance` / `brain.reply`, Task 20c) is postponed. See `server/docs/brain.md`.

Errors always look like `{ "error": { "code": "...", "message": "..." } }` and `message` is safe to show to a user. When the server checked a whole document (a clinic plan) or refuses because something is in use, the error also has `details: [{path, problem}]`, one entry per problem or per user (`rooms[3].polygon`, `tasks/t-12`).

## Emergency service (separate system)

Patient calls and staff emergency calls do **not** go through the central server. They go to a small, independent emergency service, in two copies on two machines, that pages the nearest nurse or doctor and then the most needed role, and escalates until someone accepts. It keeps working when everything else is down. The central server only mirrors its alarms onto the 3D map (the room turns red). Full design: [emergency.md](emergency.md). It supplements a certified nurse-call system; it never replaces one.

## Deaf zones

Defined in the admin panel (job 5), stored by the server (job 3), **enforced on the robot** (job 2). The robot closes its own microphone, so it still works when the connection drops. If the robot does not know where it is, it treats the place as deaf (microphone closed). The state `mic_open` is reported up so the admin panel can show it. The gardien is not involved, because this is about listening, not moving.

## Where code lives

```
implementation/
  architecture.md, 01_…05_*.md   these docs
  model_service/                 job 1: FastAPI service, training, MESURES.md, classes.yaml
  server/                        job 3: Rust, openapi.yaml, ws_messages.md, migrations/
  app/                           job 4: Flutter
  admin/                         job 5: React + TypeScript + Three.js
  sim/                           job 2, optional: Webots world
briques/b16_lien_serveur/        job 2: new brick (add it to the roles table in AGENTS.md)
briques/b05_yeux/branchements/   job 1 adds one file; job 2 reviews
```

Only the owner edits their folder. A change to a contract needs all affected owners to agree first, and the backend engineer updates the spec file in the same change.

## Milestones

| # | Done when | Who must be ready |
| --- | --- | --- |
| **M0** Contracts frozen and fakes up | `openapi.yaml` and `ws_messages.md` merged. Model service mock returns fixed boxes. Server has a fake-robot script that sends positions. App and admin each show data from the server mock | All, starting together |
| **M1** First end-to-end run | A tap in the app creates a task. The fake robot (`b02`) drives to the room through `b16`, gardien and prise. The admin panel shows it moving | 2, 3, 4, 5 |
| **M2** MVP jobs | Fetch with inventory update. Interpreter session. Night restock round with counting. The real detector replaces the mock | 1 joins the end-to-end loop |
| **M3** Full version | Deaf zones, staff-approved summaries, comfort mode, demo polish, rehearsal with the jury script (`b15_chef_demo`) | All |

## Decisions I made, and the open ones

**Made:**

- **Keep the Rust server and PostgreSQL** you chose earlier, but treat the Python `clinique/` modules (task states, dispatcher, role cards, badges, reserve) as the *behaviour reference*. The server ports their rules and the Python tests are the oracle for them. This costs a port, in return for a real multi-device server.
- **The Python robot stays.** No rewrite, no ROS-first redesign. Real robots plug in through `b03_adaptateurs`.
- **Webots is optional.** The existing fake robot already runs the whole chain. Webots is only worth it if it produces useful camera images for training or a nicer demo.
- **One app, not two.** Same Flutter app for position tracking and the nurse and doctor interface.
- **Vision model licence.** Ultralytics YOLO is AGPL-3.0, which `LICENCES.md` says to raise with Hiba. Job 1 starts with Apache or BSD options (see its guide).

**Open (need an answer, the default is in bold):**

1. Which clinic tools and supplies are in the class list. **Start with the 5 reserve items plus about 7 common tools (job 1 proposes, Hiba confirms).**
2. Indoor position for staff: **room picker or QR code at the door** (the repo already prints QR codes, `clinique/codes_qr.py`). Beacons later.
3. Speech and translation: **stay local** (existing whisper and Apertus). No cloud.
4. Whether the admin panel replaces or embeds the existing jury screen: **link to it, do not rebuild it** (`b13_ecran/jury.py`).
5. Should server-defined "restricted" zones feed the gardien: **no for now.** That needs the security reviewer and is a separate change.
