# Clinic Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Rust central server (job 3): REST + WebSocket API, security layers, audit trail, 3D clinic model with live robot and tablet positions, robot dispatch and inventory optimisation, scheduler, and an optional Python bridge.

**Architecture:** A Cargo workspace in `implementation/server/`. The binary (`src/`) is the axum API and wiring only. Each concern lives in its own crate behind traits, so the API can run on mock services (milestone M0) and on real ones later. Crates depend downwards only: `domain` ← everything; the other crates never depend on each other except where the dependency table says so.

**Tech Stack:** Rust (stable, edition 2024 or later as installed: cargo 1.97 is present), axum, tokio, tower, tower-http, utoipa + utoipa-axum + utoipa-scalar, sqlx + SQLite (WAL mode), thiserror, tracing, serde, governor, ipnet, chrono + chrono-tz, argon2, sha2, uuid, pyo3 (feature-gated). **Exact versions:** add each with `cargo add`, record the resolved version in `[workspace.dependencies]`, and read that version's docs before use. Do not rely on version numbers written from memory, in this plan or elsewhere.

**Spec:** `implementation/architecture.md` (contracts C2 and C3, rules), `implementation/03_serveur.md` (job description), and the requirements the project lead gave in conversation, restated in Global Constraints below. Python reference behaviour: `briques/clinique/{repartiteur,monde_robots,taches,cartes,carnet}.py`.

## Method: top-down build-out (lead's instruction)

The code is written from the top down, not from the leaves up:

1. **Phase A (Tasks A1, A2).** Write `main.rs`, the router, the handlers and the WebSocket handlers first, calling types and methods as they *should* exist, with the names and signatures given in the Interfaces blocks of Tasks 2–20. Then declare every missing item in the crate this plan assigns it to, with its real signature and a body of `todo!("T<n>: <what it must do>")`, until `cargo check --workspace --all-targets` has zero errors. Then write the tests for everything, against those signatures.
2. **Phase B (Tasks 2–21).** Replace the `todo!` bodies slice by slice. Inside each slice, go top-down again: the handler first, then the service it calls, then the crate functions the service calls, which may themselves call functions that are still `todo!`. A task is done when its slice has no `todo!` left and its tests are un-ignored and pass.
3. **Tests for stubbed code** carry `#[ignore = "todo(T12): TaskService::create"]` so the suite stays green while the remaining work stays visible. When a body is filled, its tests are un-ignored in the same commit.
4. **Every step is documented.** Each commit appends an entry to `docs/progress.md`: date, task, stubs added, bodies filled, tests added or un-ignored, and the `todo!` and ignored-test counts before and after (printed by `scripts/todo_report.sh`). Every public item gets a rustdoc comment saying what it does, its errors, and its invariants.

**How to read Tasks 2–21 under this method:** their Files already exist as stubs after Phase A, and their tests already exist as ignored. "Write the failing tests" means un-ignore this task's tests and add any the stub phase missed. "Implement" means replace this slice's `todo!` bodies, starting from the handler. The task order stays the same.

## Global Constraints

Requirements from the lead, verbatim in intent:

- **No `unwrap()`, no `expect()`, no `panic!`, no `unsafe`** anywhere in server code, tests included. Tests return `Result<(), Box<dyn std::error::Error>>` and use `?`. Enforced by the lint wall (Task 1), not by discipline.
- **One temporary exception: `todo!()`**, and only during build-out (see Method). `clippy::todo` is `warn` until Task 21, which turns it to `deny` and requires zero `todo!` left. `unimplemented!` stays forbidden; use `todo!` with a task id so every stub is traceable.
- **Object-oriented style:** structs with private fields and validating constructors, behaviour in `impl` blocks, traits as interfaces, dependency injection through `Arc<dyn Trait>`. No inheritance emulation, no global state.
- **Errors:** every crate has one `thiserror` enum. Each variant's message says what happened, to what, and what to do. API errors always have the shape `{ "error": { "code", "message" } }` (architecture.md C3), where `message` is safe to show to a user and never leaks SQL, paths or internals.
- **API stack:** axum, utoipa for OpenAPI, utoipa-scalar for the docs page at `/docs`. (Scalar is an interactive API reference, not a log viewer. Logs are `tracing` output plus the audit trail.)
- **Security crate:** tower and tower-http layers: CORS, request limits (rate), a known-network check with an identity header, and the other layers listed in Task 7.
- **Crates required:** `python-bindings` (pyo3), `security`, `optimization`, `scheduler`, `audit`, `locations`. Added by this plan to avoid circular dependencies: `domain`, `storage`, `realtime`.
- **`locations` holds a 3D plan of the building**, joined with live positions of robots and tablets, so a 3D UI can show robot ids and what each robot is doing, and the owner of each tablet.
- **Privacy:** for a human, the server holds only a tablet's owner label and its room. Nothing else about a person is stored, shown or logged. Tablet positions live in memory only.

Inherited from the project:

- The server **creates tasks, never motor commands.** No "drive to x, y" endpoint. The emergency stop is the only command that bypasses the dispatcher, needs the admin role, and has its own tested code path.
- The server never stores images, audio or health content.
- Everything works offline on a laptop. No external service, no CDN, no GeoIP database, no cloud.
- Licences: MIT, Apache, BSD only. `cargo deny` fails the build on GPL or AGPL (rule from `LICENCES.md`).
- Data is invented and says so (`"marque": "inventé"` in every seed file).
- Say what is tested. Anything not run against a real robot is labelled "not tested".
- Time: store UTC, send ISO-8601. Scheduler time zone defaults to `Europe/Zurich`.

## Review Focus

Failure modes the spec implies but nobody would think to test. Each has an owning task with a test.

1. **Replayed robot events.** A robot that reconnects resends events. The same event id twice must not decrement stock twice or write two audit rows. (Task 12)
2. **Two requests for the last unit.** Exactly one is reserved, the other gets an explicit "out of stock" refusal, and stock never goes negative. (Task 15)
3. **Forged network headers.** A client that sends `X-Forwarded-For` or `X-Client-Id` from an unknown or a known address must not gain access or change identity. (Task 7)
4. **Malformed input.** Invalid JSON, oversize body, NaN or infinite coordinates, a self-intersecting zone polygon, a room that is not on the map, a floor that does not exist: each returns an explicit 4xx, never a panic or a 500. (Tasks 4, 10, 11, 16)
5. **Stale data shown as live.** A robot silent for over 5 s must show `stale`; a tablet position expires after its TTL and never reaches the database or the logs. (Task 11)

Also covered by tests in their own tasks: browser WebSocket cannot send an `Authorization` header (Task 8), WebSocket ignores CORS (Task 7), slow WebSocket consumer (Task 14), DST in cron (Task 17).

## Where each piece lives

```
implementation/server/
  Cargo.toml                 workspace, shared lints, shared dependency versions; also the `clinic-server` package
  rust-toolchain.toml, rustfmt.toml, clippy.toml, deny.toml, .gitignore, .env.example
  src/
    main.rs                  startup only
    lib.rs                   builds the Router from AppState
    config.rs, state.rs, error.rs (ApiError), openapi.rs
    routes/                  one file per area: health, auth, tasks, inventory, map, zones, robots, schedules, audit
    services/                traits + mock.rs + one real impl per trait
    ws/                      apps.rs, robots.rs (upgrade handlers)
    bin/fake_robot.rs        stand-in robot for jobs 4 and 5
  crates/
    domain/                  ids, roles, task state machine, Clock, ports (repository traits), ErrorBody
    storage/                 sqlx repositories implementing the ports
    realtime/                WS protocol types (C2), Hub, robot sessions, liveness
    security/                CORS, limits, rate limit, known networks, identity, origin check
    locations/               3D model of the building, validation, live positions, privacy filter, Bluetooth positioning
    optimization/            routing graph, dispatcher, stock ledger, tour planner, leases, reservations
    scheduler/               cron schedules, restock rounds
    audit/                   sealed append-only journal, flight recorder, verifier
    python-bindings/         pyo3 bridge, off by default (cargo feature `python`)
  migrations/                numbered SQL files, one set per crate that owns tables
  seed/                      JSON seed data (invented): clinic_map.json, reserve.json, robots.json, role_cards.json, users.json
  scripts/                   check.sh, check.ps1, lint_canary.sh, export_seeds.py, export_openapi.sh, gen_dispatch_golden.py
  tests/                     integration and end-to-end tests
  docs/                      dev-setup.md, ws_messages.md, map-format.md, task-states.md, openapi.yaml, pyo3-decision.md, runbook.md
```

**Dependency rule:** `domain` depends on nothing in the workspace. `locations`, `audit`, `scheduler`, `optimization`, `security`, `realtime` depend on `domain`. `optimization` also depends on `locations` (the routing graph is built from the map). `storage` depends on `domain`, `audit`, `locations`, `scheduler`. The binary depends on all. `python-bindings` depends on `domain` and `optimization`.

## Milestones and priority

| Tier | Tasks | Gate |
| --- | --- | --- |
| **M0** contracts and fakes | 0, 1, A1, A2, 2–5 | Jobs 4 and 5 can read `openapi.yaml`, call the mock server and watch the fake robot move |
| **M1** first end-to-end | 6–14 | App tap → real server → dispatcher → fake robot → live 3D positions |
| **M2** MVP jobs | 11c, 15, 17, 18, 11b | Stock-safe fetches, night restock round with leases |
| **M3** full | 16, 19, 20, 21 | Deaf-zone delivery, reservations, Python bridge, hardening gate |

If time runs short, cut from the end: 19 first, then 20, then 18, then 11b (rooms are still picked by hand or QR code). Tasks 0–14 are the product.

## Technical risks (known now)

| Risk | Consequence | Handling |
| --- | --- | --- |
| **SQLite** (decided). sqlx compiles SQLite into the binary: no server to install, but a C compiler is needed at build time (MSVC Build Tools on Windows, Xcode tools on the Macs). SQLite allows one writer at a time | Write contention under load; locking errors if misconfigured | WAL mode, `busy_timeout` 5 s, short write transactions, `BEGIN IMMEDIATE` for reservations (Task 15). The repository traits keep a later move to PostgreSQL a swap, not a rewrite |
| `todo!()` stubs panic if reached at run time | A half-built server can crash on a route that is not finished | Stubs only during build-out; ignored tests mark every unfinished path; Task 21 denies `todo` |
| Bluetooth RSSI is noisy (several metres) and phone platforms limit scanning | Wrong room shown | Map matching, room fingerprints, hysteresis; manual room pick overrides; synthetic tests before any hardware (Task 11b) |
| Browsers cannot set headers on a WebSocket | The admin panel cannot authenticate `/ws` with `Authorization` | First-message auth `{type:"auth", token}` within 5 s (Task A3; the earlier ticket design was removed) |
| Browsers do not apply CORS to WebSockets | Any web page on the LAN could open `/ws` | Explicit `Origin` check (Task 7) |
| IP geolocation is meaningless on a LAN | "Locate the caller" cannot mean GeoIP | It means a table of known networks (CIDR → label and area), Task 7 |
| `X-Forwarded-For` and custom identity headers are forgeable | IP and identity spoofing | Use the socket's peer address; trust forwarded headers only from configured proxies; identity comes from the token, the header is only cross-checked |
| pyo3 macros generate `unsafe` code | `forbid(unsafe_code)` cannot hold in that one crate | Task 20: `deny` instead, our own code stays unsafe-free, documented exception |
| pyo3 needs a matching Python at build and run time. This machine has Python 3.14 and no project venv | Build failure or import errors (pydantic wheels) | Task 0 creates a venv with a supported Python; Task 20 is behind a feature flag so nothing else depends on it |
| sqlx compile-time query checking needs a database at build time | CI and teammates without a DB cannot compile | Commit the offline query cache (`cargo sqlx prepare`) and check it in `scripts/check.sh` |
| axum 0.8 changed path syntax to `/{id}` | Routes silently never match | Task 4 has a test that hits every parameterised route |
| Plain HTTP on hospital Wi-Fi | Tokens readable on the network | Out of scope for M0–M2. Task 21 documents TLS with rustls and a local CA as the upgrade path. Flag to Hiba |
| Staff location is personal data | Legal exposure (Swiss nFADP, GDPR) | Room-level only, in memory, short TTL, no history. Needs the clinic's sign-off before any real deployment |
| Rust learning curve and compile times | Slow iteration | Small crates compile fast. `cargo check` in the loop, full lint wall before each commit |

---

### Task 0: Development environment

**Files:**
- Create: `implementation/server/docs/dev-setup.md`, `implementation/server/.env.example`

**Interfaces:**
- Produces: the environment variables `DATABASE_URL` (for example `sqlite://data/clinic.db?mode=rwc`, used by the server and by `cargo sqlx prepare`), `JOURNAL_DIR`, and the commands later tasks call: `sqlx`, `cargo deny`, `cargo audit`, `python`. Tests use in-memory SQLite through `#[sqlx::test]`, so they need no file.

- [ ] **Step 1: Install and record.** Check a C compiler is available (`cl` from MSVC Build Tools on Windows; `cc` on Mac). Run `cargo install sqlx-cli --no-default-features --features rustls,sqlite`, `cargo install cargo-deny cargo-audit`. Create a Python venv with a Python version the repo supports (3.11–3.13, check `requirements.txt` wheels first) at the repo root `.venv`, install `requirements.txt`. Write the exact commands that worked into `dev-setup.md`.
- [ ] **Step 2: Database.** SQLite: nothing to install. `data/` and `journal/` go in `.gitignore`. The authoritative audit trail is the sealed journal (Task 9), not the database.
- [ ] **Step 3: Verify.** Run `sqlx --version`, `cargo deny --version`, `cargo audit --version`, `.venv/Scripts/python -c "import yaml, pydantic"`. Expected: all print a version, no errors.
- [ ] **Step 4: Commit** `docs: server dev setup`.

---

### Task 1: Workspace and the lint wall

**Files:**
- Create: `Cargo.toml`, `rust-toolchain.toml`, `rustfmt.toml`, `clippy.toml`, `deny.toml`, `.gitignore`, `src/main.rs`, `src/lib.rs`, `crates/*/Cargo.toml`, `crates/*/src/lib.rs`, `scripts/check.sh`, `scripts/check.ps1`, `scripts/lint_canary.sh` (all under `implementation/server/`)

**Interfaces:**
- Produces: `scripts/check.sh` (and `.ps1`), the one command every later task runs before committing. It runs, in order: `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test`, `cargo deny check`, and (once Task 6 exists) `cargo sqlx prepare --check`.
- Produces: workspace-wide lints inherited by every crate through `[lints] workspace = true`.

- [ ] **Step 1: Write the canary test.** `scripts/lint_canary.sh` copies a file containing `unwrap()`, `expect()`, `panic!`, array indexing and an `unsafe` block into `crates/domain/src/bin/canary.rs`, runs clippy, asserts the output names every one of those lints and the exit code is non-zero, then deletes the file (with a trap, so it is removed on failure too).
- [ ] **Step 2: Run it to see it fail.** `bash scripts/lint_canary.sh`. Expected: fails, because no lint wall exists yet.
- [ ] **Step 3: Create the workspace.** Root `Cargo.toml` is both `[workspace]` and the `clinic-server` package. `[workspace.lints.rust]`: `unsafe_code = "forbid"`. `[workspace.lints.clippy]` at `deny`: `unwrap_used`, `expect_used`, `panic`, `unimplemented`, `unreachable`, `indexing_slicing`, `dbg_macro`, `print_stdout`, `print_stderr`; at `warn`: `todo` (build-out only, see Method) and `pedantic`. `[workspace.lints.rust]` also sets `missing_docs = "warn"`. `check.sh` passes `-D warnings` but `-A clippy::todo` until Task 21. Also create `scripts/todo_report.sh` (counts `todo!(` per crate and `#[ignore = "todo(` per test file, prints a table) and `docs/progress.md` (the step journal, first entry: this task). `[workspace.dependencies]` holds every shared dependency version. Each crate gets an empty `lib.rs` with one passing test. `deny.toml` allows only MIT, Apache-2.0, BSD-2/3-Clause, ISC, Unicode-3.0, Zlib and fails on any GPL/AGPL.
- [ ] **Step 4: Run the canary and the full check.** Canary expected: passes (clippy fails as intended). `bash scripts/check.sh` expected: green on the empty workspace.
- [ ] **Step 5: Commit** `chore: workspace with strict lint wall`.

---

### Task A1: Top-down skeleton that compiles

**Files:**
- Create: every file listed under "Where each piece lives", as stubs. Real code only in `main.rs`, `lib.rs` (router), route and WebSocket handlers, and the service wiring in `state.rs`.
- Modify: `docs/progress.md`

**Interfaces:**
- Consumes: the Interfaces blocks of Tasks 2–20. They are the single source of names and signatures. A name the top layer wants that no block defines is added to the owning task's Interfaces block in the same commit, so the plan stays the map.
- Produces: a workspace where every type, trait, and function of the plan exists with its final signature. Structs and enums are complete (fields and variants are real, they cannot be `todo!`). Function and method bodies are `todo!("T<n>: …")`. Error enums are complete with their messages, since messages are part of the contract.

- [ ] **Step 1: Write the top layer.** `main.rs` (config, tracing and journal start, database, services, router, serve, graceful shutdown with a final journal seal), the router with the security stack, every handler from C3, both WebSocket handlers. Write it as the finished program would read.
- [ ] **Step 2: Run `cargo check --workspace --all-targets`.** Expected: many unresolved-name errors. Record the count in `docs/progress.md`.
- [ ] **Step 3: Declare what is missing**, crate by crate, following each compiler error to the crate the plan assigns it to: real signature, rustdoc comment, `todo!` body. Repeat Step 2 after each crate.
- [ ] **Step 4: Verify.** `cargo check --workspace --all-targets`: zero errors. `bash scripts/check.sh`: green apart from the allowed `todo` warnings. `cargo run -- --print-openapi` works already (it uses only derives). `bash scripts/todo_report.sh` prints the stub count.
- [ ] **Step 5: Commit** `feat(skeleton): top-down workspace skeleton with todo stubs`, with the progress entry.

---

### Task A2: Tests for everything, against the skeleton

**Files:**
- Create: every test file named in Tasks 2–21, and `tests/support/` (server-on-port-0 helper, fake clock wiring, WebSocket test client).
- Modify: `docs/progress.md`

**Interfaces:**
- Consumes: the stubbed signatures from A1.
- Produces: every test named in this plan, compiling. Each test whose code path reaches a `todo!` is marked `#[ignore = "todo(T<n>): <function>"]`. Tests that already pass (serde shapes, derives, error messages, OpenAPI paths) are not ignored.

- [ ] **Step 1: Write the tests** with the assertions given in each task.
- [ ] **Step 2: Run `cargo test --workspace`.** Expected: PASS (ignored tests do not run).
- [ ] **Step 3: Run `cargo test --workspace -- --ignored`.** Expected: every ignored test fails with a `todo` panic naming its task, and no other kind of failure. Any other failure means the test or the signature is wrong: fix it now.
- [ ] **Step 4: Commit** `test: full test suite against skeleton`, with the passing and ignored counts in the progress entry.

---

### Task A3: Align the contract with the admin console (inserted Nov 15)

The admin console (job 5, `implementation/admin/`, merged from `feat/admin-console-v2`) is finished and tested against its own in-browser mock. `implementation/BACKEND_A_FAIRE.md` §2 lists what it expects from the server. The skeleton's DTOs differ in several places. Since Phase B fills bodies against these DTOs, the contract is fixed **now**, before Task 2 resumes. The console's readers (`admin/src/lib/adapt.ts`) are the authority on field names; they accept snake_case and ignore unknown fields.

**Rulings (the lead may override):**
- **Map axes follow the console:** metres, x grows east, **y grows south** (top-down screen view); heading 0 = east, positive turns toward south. This replaces "y north" in `docs/map-format.md` and Task 10. All 2D maths is unchanged; only the documented frame and the seed data follow it.
- **`TaskState::Cancelled`** is added as a terminal state (the console shows it). Cancelling no longer maps to `Failed` + reason `Cancelled`. Not in the Python states; documented in `docs/task-states.md` under "Intentional differences".
- **WebSocket auth:** `/ws` accepts the console's first message `{"type":"auth","token":"…"}` within 5 s, else closes (code 4401, explicit reason). The token never travels in the URL. The single-use ticket (`POST /auth/ws-ticket`, `?ticket=`) is **removed**: the console does not use it, and the first-message auth solves the same browser problem. The `Origin` check stays.
- **Login:** `POST /auth/login {username, password}` → `{token, role, operator, expires_at}`. `username` is the user id, `password` the secret (argon2, as the PIN before). `device_id` becomes optional: a browser has none. `operator` = the user's pseudonymous label.
- **Schedules are daily at a time:** the API exposes `time: "HH:MM"` (Europe/Zurich) and keeps cron internally (`"MM HH * * *"`). `PUT /schedules/{id}` accepts a partial body `{enabled?, time?, robot_id?}`.
- **Lists are arrays**, or `{items, next}` where paging matters (`/tasks`, `/audit`): the console reads `items`.
- **Robot `state` is never `offline`.** It carries the last reported state; staleness is shown by `last_seen` (the console greys a robot silent for 5 s) and by an `alert`. Otherwise the console would show `offline` as `fault`.
- **`robot.updated` is pushed at least once per second per connected robot**, even when nothing changed (the coalescing broadcaster of Task 11 sends a per-robot heartbeat).
- **`interpreter_session`** is added as a `TaskKind` (BACKEND_A_FAIRE decision 1). The console does not know it yet (it shows unknown kinds as `fetch`): noted for job 5.

**Files:**
- Modify: `src/dto.rs`, `src/routes/{auth,tasks,inventory,zones,robots,schedules,audit,map}.rs`, `src/ws/apps.rs`, `crates/realtime/src/protocol.rs` (`AppEvent` wire format), `crates/domain/src/task.rs` (`Cancelled`, `InterpreterSession`), `crates/locations/` docs and seed conventions, the A2 tests that assert the old shapes, `docs/openapi.yaml` after regeneration, `implementation/architecture.md` (C3 section), `docs/map-format.md`, `docs/ws_messages.md`
- Test: `tests/console_contract.rs` (new)

**Interfaces (the wire contract, exactly as the console reads it):**
- `POST /auth/login` body `{username, password}`; response `{token, role, operator, expires_at}`.
- `GET /map` → `{floors:[{id, label, outline}], rooms:[{id, floor, label, kind, polygon, label_at?}], walls:[{floor, points}], places:[{id, label, floor, x, y, kind}], props:[…]?}`. Room kinds: `room|corridor|elevator|care|storage|therapy|pool|lounge`; place kinds: `room|shelf|dock|point`. Points are `[x, y]`.
- `GET /robots` → `[{id, name, role, simulated, pos:{x, y, heading, floor}, battery, state: idle|busy|paused|fault|estop, holding, mic_open, task_id, last_seen}]`. A robot never heard from is listed with its seeded start position and `last_seen: null`.
- `POST /robots/{id}/command {name: pause|resume|dock|estop}` → 200 `{accepted, reason, sent_at}`; a refusal is 409 with a readable `error.message`. The estop to an offline robot is 409, message "Robot X is offline: the stop was not delivered. Use the physical button."
- `GET /tasks` → `{items:[Task], next}`; `GET /tasks/{id}`, `POST /tasks/{id}/cancel` (admin or requester) → Task. Task = `{id, kind, item, from_place, to_place, state, robot_id, requested_by, created_at, updated_at, reason, history:[{at, actor, label}]}`. `requested_by` is the owner label (never a real name).
- `GET /inventory` → `[{id, label, place, count, low_at, last_robot_count, last_robot_count_at, updated_at}]`; `POST /inventory/{item}/adjust {delta}` (non-zero integer; `reason` optional, default `admin_correction`) → the item.
- `GET /zones` → `[{id, name, floor, kind: deaf|restricted, polygon, deliveries:[{robot_id, status: received|pending|failed}], enforced_by_gardien}]`; `PUT /zones/{id}` body `{id, name, floor, kind, polygon}` (body `id` must equal the path id, else 422); `DELETE /zones/{id}` → 204.
- `GET /schedules` → `[{id, label, enabled, time, robot_id, last_run, last_result: success|partial|failed|never, last_counts:[{place, item, expected, counted}]}]`; `PUT /schedules/{id}` partial `{enabled?, time?, robot_id?}`.
- `GET /audit?from=&to=&actor=` → `{items:[{id, at, actor, action, target, result: ok|refused|failed, detail}], next}`, derived from journal records by a fixed mapping per `RecordBody` variant (`detail` built from typed fields only, never free text from a client).
- `WS /ws`: first client message `{type:"auth", token}`; server messages `{type:"robot.updated", robot}`, `{type:"task.updated", task}`, `{type:"inventory.updated", item}`, `{type:"zone.updated", zone}`, `{type:"zone.deleted", zone_id}`, `{type:"schedule.updated", schedule}`, `{type:"alert", level: info|warning|critical, message}`. Incident and position events keep their own types (`incident.updated`, `positions.delta`), which the console ignores today.

- [ ] **Step 1: Write the failing contract tests** in `tests/console_contract.rs`, one per row above, asserting the exact key sets and enum spellings on the mock server (`--mock` wiring). Also `ws_auth_first_message_accepts_valid_token`, `ws_without_auth_message_closes_after_5s_with_4401`, `ws_token_in_query_is_ignored`, `robot_updated_sent_every_second_while_connected`, `zone_put_with_mismatched_body_id_is_422`, `schedule_put_partial_body_changes_only_given_fields`, `adjust_without_reason_uses_admin_correction`, `robot_state_never_serialises_as_offline`. Mark them ignored with the task that fills the slice (most: T4/T5 for the mock).
- [ ] **Step 2: Change the DTOs, wire types, routes and domain enums** to the contract above. Update the A2 tests that assert the old shapes (list each one in the report), regenerate `docs/openapi.yaml`, update `docs/ws_messages.md`, `docs/map-format.md` and the C3 section of `architecture.md`.
- [ ] **Step 3: Remove the WebSocket ticket** (route, DTO, service method, tests) and record it in `docs/progress.md`.
- [ ] **Step 4: Verify.** `cargo test --workspace` green, `CARGO_BUILD_JOBS=2 bash scripts/check.sh` OK, `--print-openapi` lists every console path including `DELETE /zones/{id}`.
- [ ] **Step 5: Commit** `feat(contract): align the API with the admin console`.

---

### Task A4: Contract for editable clinics, routes, heat and demo mode (inserted Nov 15)

The lead's direction (Nov 15): **the console becomes only a frontend.** The logic it holds today moves to the server: the demo clinic simulation (`admin/src/mock/`), the route planner (`admin/src/lib/nav.ts`), the heat map (`admin/src/lib/heat.ts`). And clinics become **data on the server**: the console loads any clinic plan from the server and edits it (floors, rooms, walls, places, furniture), plus deaf and blocked zones. This task declares that contract (stubs and tests, as A1/A2 did); Tasks 5b, 10b, 11d and 13b fill it. The console side has its own plan: `docs/superpowers/plans/2026-11-15-admin-thin-client.md`.

**Rulings:**
- **A clinic plan is one versioned document**: `ClinicPlan { name, floors, rooms, walls, places, props }` in the console's map shape (y south). Several plans can be stored; **one is active** and is what `GET /map` returns. Editing replaces the whole plan with optimistic concurrency (`If-Match: <version>`, 412 on conflict). This is simpler and safer than many granular endpoints: the server validates the whole plan at once.
- **Walls get ids** (the console's walls have none today: console plan, task F3).
- **Validation is all server-side** (`locations::ClinicMap::new` and new checks), and a refusal lists every problem: `{error:{code:"invalid_plan", message, details:[{path, problem}]}}`, for example `{path:"rooms[3].polygon", problem:"edges 1–2 and 3–4 cross"}`.
- **Referential safety:** deleting or renaming a place that an open task, a stock item, a schedule or a robot's start uses is refused (409) with the list of users. Activating another plan while tasks are open is refused (409).
- **Blocked zones = the `restricted` kind.** The server's planners (route preview, dispatcher path cost, tour planner) treat them as impassable. This is **planning only**: the gardien still does not enforce them (open question 5), and the UI keeps saying so.
- **The route preview is a server estimate**: grid A* on the active plan (walls, solid props, outside of the building, blocked zones), straightened and rounded, a port of `nav.ts`. The real robot plans its own way.
- **Heat map counts robots only**, never tablets (privacy rule), in memory, reset on restart, like the console's version.
- **Demo mode is the server's job**: `clinic-server --demo` runs simulated robots that drive the routes, take auto-generated tasks, count stock and obey zones, a port of `admin/src/mock/sim*.ts`, and labels everything "SIMULATED". It replaces the console's in-browser demo.
- **Seed clinic**: the console's demo clinic (`admin/src/mock/world.ts` plus `seed.ts`) becomes the server's seed plan `seed/clinic_map.json` (exported once by a script), so the demo looks the same.

**Files:**
- Modify: `src/dto.rs`, `src/routes/` (add `clinics.rs`, `stats.rs`; extend `map.rs`, `tasks.rs`), `src/services/` (add `clinics.rs`, `routing.rs`, `stats.rs`, `demo.rs`), `crates/locations/src/` (add `plan.rs`, `grid.rs` for the planning grid), `crates/optimization/src/` (add `route_preview.rs`), `crates/realtime/src/protocol.rs` (`map.updated`), `crates/storage/src/clinics.rs` + migration
- Create: `scripts/export_console_clinic.mjs` (runs `world.ts`/`seed.ts` through Node and writes `seed/clinic_map.json` and `seed/demo_fleet.json`)
- Test: `tests/clinics.rs`, `tests/route_preview.rs`, `tests/demo_mode.rs`, `crates/locations/tests/plan_validation.rs`

**Interfaces:**
- `GET /clinics` → `[{id, name, version, active, updated_at}]`; `GET /clinics/{id}` → `ClinicPlan` with `ETag: <version>`; `POST /clinics` body `ClinicPlan` → 201 created (validated); `PUT /clinics/{id}` with `If-Match` → the plan (validated, `version+1`); `POST /clinics/{id}/activate` → 200; `DELETE /clinics/{id}` (never the active one) → 204. Admin only. `GET /map` stays the active plan, everyone. Each change is journaled, sends `{type:"map.updated", version}` on `/ws` and `map.update` to robots.
- `ClinicPlan` types in `locations::plan`: `PlanFloor {id, label, outline}`, `PlanRoom {id, floor, label, kind, polygon, label_at?}`, `PlanWall {id, floor, points}`, `PlanPlace {id, label, floor, x, y, kind}`, `PlanProp {id, floor, kind, x, y, width, depth, solid}`. `ClinicPlan::validate(&self) -> Result<ClinicMap, PlanErrors>` with `PlanErrors(Vec<PlanProblem { path, problem }>)`.
- `GET /tasks/{id}/route` → `{floor, points:[[x,y]], length_m, estimate: true}` or 404 `no_route` with the reason. `RoutePreview::plan(&self, plan: &ClinicMap, zones: &[Zone], from: Point2, to: Point2, floor: i32) -> Result<PreviewPath, RouteError>`; grid cell 0.2 m, robot clearance radius 0.42 m, near-obstacle step cost ×2.6, free-ground search 2.4 m — the values of `nav.ts` (ruling R13; constants in one place, documented).
- `GET /stats/heat?floor=` → `{floor, cell_m: 1, origin:[x,y], columns, rows, counts:[u32]}` (row-major), admin only.
- Demo: `DemoClinic::start(plan, fleet, hub, clock, seed) -> DemoHandle` behind `--demo`; `GET /health` reports `mode: "demo" | "live" | "mock"`.

- [ ] **Step 1: Declare** the routes, DTOs, services and crate types above with `todo!("T<n>: …")` bodies (5b demo, 10b clinics, 11d heat, 13b route preview), real signatures and rustdoc.
- [ ] **Step 2: Write the tests** (ignored with their task id), including: `plan_with_crossing_room_edges_lists_the_problem_path`, `plan_with_place_outside_every_floor_is_refused`, `put_with_stale_if_match_is_412`, `deleting_a_place_used_by_an_open_task_is_409_listing_the_task`, `activating_another_plan_with_open_tasks_is_409`, `map_updated_is_broadcast_after_put`, `route_avoids_walls_and_solid_props`, `route_avoids_restricted_zone_but_crosses_deaf_zone`, `route_between_floors_is_404_no_route`, `heat_counts_robots_only_never_tablets`, `demo_mode_robots_move_and_send_robot_updated_every_second`, `demo_mode_labels_every_robot_simulated`, `seed_plan_matches_console_demo_clinic` (room and place counts from the exported JSON).
- [ ] **Step 3: Export the console clinic** with the script, commit `seed/clinic_map.json` and `seed/demo_fleet.json` (marked invented).
- [ ] **Step 4: Verify** `cargo test --workspace` green, `CARGO_BUILD_JOBS=2 bash scripts/check.sh` OK, `--print-openapi` lists the new paths. **Commit** `feat(contract): editable clinics, route preview, heat, demo mode`.

**Phase B tasks added for this contract** (execution order in the ledger: after Task 5 comes 5b, after Task 10 comes 10b, after 11c comes 11d, after 13 comes 13b):
- **Task 5b — Demo mode** (fills `services/demo.rs`): port `admin/src/mock/sim.ts`, `sim-motion.ts`, `sim-tasks.ts`, `sim-admin.ts` behaviour into the server, using Task 13b's route preview for motion and the real task/stock services. Its tests are the demo-mode tests plus a port of `admin/src/mock/sim.test.ts`.
- **Task 10b — Editable clinic plans** (fills `locations::plan`, `services/clinics.rs`, `routes/clinics.rs`, storage): validation with problem lists, versions, If-Match, referential checks, activation, broadcast.
- **Task 11d — Heat map** (fills `services/stats.rs`): robot positions only, 1 m cells, per floor, in memory.
- **Task 13b — Route preview** (fills `locations::grid`, `optimization::route_preview`): port of `nav.ts` (its test file `admin/src/lib/nav.test.ts` is ported as the Rust tests' reference cases), blocked zones impassable.

---

### Task A5: Contract for tablets, person-linked tasks, and live robot routes (inserted Nov 15)

The lead's direction (Nov 15): the map shows **tablets** as well as robots; robots **interact with tablets** ("follow Dr X", "attend the patient in room 12"); the console shows **the route each robot will take in the next seconds** and lets the admin **change it on the fly** from the 3D map. Contract task like A3/A4 (declarations, `todo!` bodies, ignored tests); Tasks 8b, 12b and 14b fill it. The console side is in the thin-client plan (Tasks F7, F8).

**Rulings:**
- **Two kinds of tablet**, one registry: `DeviceKind::Bedside` (fixed: registered to one place, its position is that place, never positioned by radio) and `DeviceKind::Staff` (mobile: carried by a staff member, positioned by room pick, QR, or Task 11b). A device has `{id, kind, label, place (bedside only), owner (staff: the logged-in user's owner label)}`. Admin registers and edits devices.
- **Privacy rule for patients (lead, Nov 15):** a patient **may be referred to by name**, but the name is **never linked to their data** and **never shown on the admin panel**. A bedside device has a `label` (room/bed, shown everywhere) and an optional `patient_name` that only staff tablets (nurse, doctor, therapist) receive; it is excluded from admin-panel responses, tasks, summaries, reports, the audit log, the journal and logs, and never joined to any clinical record. The server stores no health data. The owner of a staff tablet is the pseudonymous owner label. The 3D map (admin) shows: tablet kind, label/owner label, room, and nothing else.
- **Tablets receive data** over the same `/ws` with their device-bound token: events about tasks they asked for or that target them (`task.updated`), "a robot is coming" notices, and messages from the robot (`robot.message`, typed, from a closed catalogue: arriving, waiting, done, cannot reach). No free text from robots to tablets in this version.
- **Person-linked tasks:** new `TaskKind::Follow { target: DeviceId, until: FollowEnd }` (follow a staff tablet; ends at a place, a time limit (default 10 minutes, configurable), or on cancel) and `TaskKind::Attend { at: DeviceId }` (go to a bedside tablet's place and stay available there until released). The console and tablets show them as "following <owner label>" and "attending <bedside label>". A follow task uses the target tablet's live position: if that position is unknown or stale for more than the stale limit (default 10 s, configurable), the robot stops and waits (never guesses). Both limits are server settings (`FOLLOW_MAX_MINUTES`, `FOLLOW_STALE_S`), validated at start-up. **Safety:** following a person is a sequence of ordinary moves through brain → gardien → prise on the robot; the server only updates the target position.
- **Live route (next seconds):** every robot reports its own plan with a new C2 message `robot.plan { points: [[x,y]], horizon_s, floor, at }` (at least once per second while moving; the simulator sends it; real robots via b16). The server forwards it to the console as `robot.route { robot_id, points, horizon_s, floor, source: "robot" }`. The server's route preview (13b) is the fallback when a robot sends no plan, labelled `source: "server_estimate"`.
- **Changing a route from the console is a request, never a command:** `PUT /robots/{id}/route { waypoints: [[x,y]], floor }` (admin) → the server validates it (waypoints inside the floor, not through walls or blocked zones, within the robot's role-card places; 422 with the problem list otherwise) → sends C2 `route.suggest { suggestion_id, waypoints }` → the robot answers `route.answer { suggestion_id, accepted, reason }` (the robot's planner and the gardien decide; a real robot may refuse) → the console gets `route.answered`. `DELETE /robots/{id}/route` withdraws the suggestion. Audit-logged. The emergency stop is unaffected and still bypasses everything.

**Files:** `crates/domain/src/{device.rs, task.rs (kinds)}`, `crates/realtime/src/protocol.rs` (`robot.plan`, `route.suggest`, `route.answer`, `robot.message`, app events `robot.route`, `route.answered`, `device.updated`), `src/dto.rs`, `src/routes/{devices.rs, robots.rs}`, `src/services/{devices.rs, routes_live.rs}`, `crates/storage/src/devices.rs` + migration, `crates/locations` (bedside device anchors on the plan), the mock and the simulator (follow, attend, plan reporting, suggestion handling — declared now, filled by 14b), docs (`ws_messages.md`, C2/C3 in `architecture.md`, `openapi.yaml`).

**Interfaces:**
- `GET /devices` (admin; staff see only their own) → `[{id, kind: bedside|staff, label, place, owner, online, last_seen}]`; `PUT /devices/{id}` (admin) body `{kind, label, place?}`; `DELETE /devices/{id}` (admin). `GET /live` already lists tablets (Task 11): bedside tablets appear at their place with `kind`.
- `POST /tasks` accepts `{kind: "follow", target_device, until: {place?|minutes?}}` and `{kind: "attend", at_device}`. Task wire adds `target_device`, `target_label` (owner or bedside label).
- `GET /robots/{id}/route` → `{robot_id, points, horizon_s, floor, source, at}`; `PUT /robots/{id}/route` → 202 `{suggestion_id}`; `DELETE /robots/{id}/route` → 204.
- C2 up: `robot.plan`, `route.answer`; C2 down: `route.suggest`, `route.withdraw`, `follow.target { device, pos|null }` (1 Hz while following).
- App events: `robot.route`, `route.answered`, `device.updated`; tablet-only events: `task.updated` (filtered), `robot.message`.

- [ ] **Step 1: Declare** all of the above with `todo!("T8b|T12b|T14b: …")` bodies (8b devices, 12b follow/attend tasks, 14b live routes and suggestions incl. simulator support).
- [ ] **Step 2: Tests** (ignored with their ids), including: `bedside_tablet_position_is_its_place`, `patient_is_never_named_on_any_wire` (every DTO and event with a patient link carries only the bedside label), `follow_task_stops_when_target_position_is_stale_10s`, `follow_task_ends_after_10_minutes`, `attend_task_goes_to_the_bedside_place`, `robot_plan_is_forwarded_as_robot_route`, `server_estimate_is_used_when_robot_sends_no_plan`, `route_put_through_a_wall_is_422_with_problem`, `route_put_into_blocked_zone_is_422`, `route_suggestion_refused_by_robot_reaches_console_with_reason`, `nurse_cannot_put_a_route`, `estop_still_works_during_a_route_suggestion`, `tablet_receives_only_its_own_task_updates`.
- [ ] **Step 3: Verify** `cargo test --workspace` green, `CARGO_BUILD_JOBS=2 bash scripts/check.sh` OK, `docs/openapi.yaml` regenerated. (No commit: the lead commits.)

**Phase B tasks added for this contract (A5):** see the list after Task A6.

---

### Task A6: The brain on the server; robots as peripherals (inserted Nov 15)

> **Scope narrowed by the lead (Nov 15, later):** the robot keeps a basic brain of its own with its filtering system (gardien, prise, the existing b06 rules), so the robot speech round trip (C2 `utterance` / `brain.reply`, Task 20c) is **postponed**. **Now only: endpoints for clients** (staff app, console) to use the brain: **translate, simplify, summarise, report**. The separate `clinic-brain` process, the python-bindings bridge and the privacy rule below stay as written. Client endpoints, all authenticated, all results drafts that a staff member reads before anything is sent anywhere:
> - `POST /brain/translate {text, from?, to}` → `{text, from, to, checks: {fixed_terms_ok, numbers_ok}}` (existing `interprete.py` two-step path, fixed medical terms).
> - `POST /brain/simplify {text, lang, level: "plain"|"easy"}` → `{text, lang}` (plain-language rewrite for a patient; never adds medical advice; the brain's output is checked against its source like `resume.py` does, and falls back to "could not simplify safely").
> - `POST /brain/summarise {sources:[{kind, text}], lang}` → `{draft, lines:[{text, source}]}` (every line points to its source; reuses `resume.py` and its checks).
> - `POST /brain/report {kind: "shift"|"incident"|"robot_activity", from, to, lang}` → `{draft, lines:[…]}` built from server data the caller may see (tasks, incidents, robot activity — no audio, no free text from patients).
> - `GET /brain/health` → `{status: up|degraded|down, models, queue}`.
> Texts sent to these endpoints are processed in memory only (never stored, logged or journaled; the journal records only "brain call, kind, latency, ok/failed"). Phase B for this narrowed scope: **20** (bridge core), **20b** (clinic-brain binary with translate/simplify/summarise/report), **20d** (main-server client endpoints, auth, degradation). **20c is postponed.**

The lead's direction (Nov 15): **the central server is the main server.** It serves every request that needs intelligence: understanding a spoken request, translation, summaries, interpreter sessions. **Robots become simple peripherals**: they capture (microphone, camera), act, and report. The brain stays **written in Python** (the existing `b04_oreilles_voix`, `b06_cerveau`, `clinique/interprete.py`, `clinique/resume.py`), and is **executed from Rust through the `python-bindings` crate** (pyo3), with results passed over HTTP. This replaces Task 20's "parity oracle only" scope: the bridge becomes a core component.

**Rulings (the lead may override):**
- **A separate brain process, in the same workspace:** a second binary `clinic-brain` embeds Python through `python-bindings` and serves a small local HTTP API; the main server calls it. Reason: Apertus 8B, whisper and Python run in one process; an out-of-memory or a crash in a model must not take down task dispatch, the alarm mirror or the emergency-stop routing of the main server. Same code, two processes; the main server reports `brain: down` and degrades (rules-only answers, "interpreter unavailable") instead of dying.
- **The safety chain does not move:** the brain on the server *proposes* an action; the robot's own **gardien → prise → adapter** still check and execute it on the robot computer, exactly as today. The emergency stop, the watchdog and the deaf-zone microphone cut stay on the robot. (Touching `prise.py`, `ticket.py` or `b07_gardien/` still needs the security reviewer.)
- **Speech out stays on the robot:** the server returns text and language; the robot speaks it with its local voice (Piper / system voice). Lower latency, no audio download.
- **Privacy rule updated:** audio and text now pass through the server, **in memory only**: never written to disk, the database, logs or the journal. The journal records only "utterance processed, language, decision kind, latency". The deaf-zone rule is unchanged: a robot in a deaf zone captures nothing, so it sends nothing.
- **Offline, as before:** the brain uses the local models already chosen (whisper, Apertus via the existing cascade with the rules-only fallback). No cloud API.
- **Python environment:** the brain process runs with the repo's `.venv` (Python 3.13) and imports the existing bricks unchanged; the bridge has one interpreter thread and a bounded queue with per-call timeouts (no GIL contention in the async runtime).

**Files:** `src/bin/clinic_brain.rs` (new binary), `crates/python-bindings/src/{bridge.rs, brain.rs, speech.rs, translate.rs, summary.rs}`, `src/services/brain.rs` (main server's HTTP client to the brain, health, degradation), `src/routes/{brain.rs, translate.rs, summaries.rs, interpreter.rs}`, `crates/realtime/src/protocol.rs` (C2: `utterance` up, `brain.reply` down), `crates/domain/src/brain.rs` (decision, reply, language types), docs (`architecture.md` C1/C2/C3 and the privacy rules, `ws_messages.md`, `openapi.yaml`, `docs/brain.md`).

**Interfaces:**
- Brain process API (localhost only, token from config): `POST /v1/understand {text?, audio?, lang_hint?, robot_id, role_card}` → `{transcript, lang, decision: {kind: action|question|out_of_card|unknown|chat, action?, question?, text?}, confidence, brain}`; `POST /v1/translate {text, from?, to, fixed_terms: true}` → `{text, from, to, checks: {fixed_terms_ok, numbers_ok}}`; `POST /v1/summarise {sources:[…]}` → `{draft, lines:[{text, source}]}`; `GET /v1/health` → models loaded, memory, queue length.
- Main server, for apps: `POST /translate` (staff), `POST /interpreter/sessions` → an `interpreter_session` task, `GET /summaries`, `POST /summaries/{id}/decision {approve|reject}` (doctor/therapist only; nothing leaves before approval).
- C2: robot → server `utterance {id, audio (base64 PCM 16 kHz mono, ≤ 15 s) | text, lang_hint}`; server → robot `brain.reply {utterance_id, say: {text, lang}, propose: action | null, ask: question | null}`. The robot passes `propose` to its own brain-side gardien chain.
- `GET /health` adds `brain: up|degraded|down`.

- [ ] **Step 1: Declare** the binary, bridge, services, routes, protocol messages and types with `todo!("T20|T20b|T20c|T20d: …")` bodies.
- [ ] **Step 2: Tests** (ignored), including: `brain_down_main_server_keeps_dispatching_and_answers_degraded`, `utterance_audio_is_never_written_anywhere` (DB, journal, logs, temp files), `deaf_zone_robot_utterance_is_refused`, `proposed_action_is_not_executed_by_the_server` (only sent to the robot), `translate_keeps_fixed_terms_and_numbers`, `summary_needs_approval_before_leaving`, `brain_call_timeout_returns_explicit_error`, `brain_api_refuses_non_localhost`.
- [ ] **Step 3: Verify** green and check OK; regenerate `openapi.yaml`.

**Phase B tasks for A5 and A6:**
- **8b — Devices**, **12b — Follow and attend tasks**, **14b — Live routes** (A5, described above).
- **20 — Python bridge (core):** interpreter thread, queue, timeouts, error mapping, `.venv` discovery; the unsafe-lint exception for pyo3 (ruling R7).
- **20b — Brain process:** `clinic-brain` binary serving `/v1/understand`, `/v1/translate`, `/v1/summarise`, `/v1/health` over the existing Python bricks; measured latency and memory in `docs/brain.md`.
- **20c — Robot speech round trip:** `utterance` → brain → `brain.reply`; the simulator sends canned utterances in `--mock`/`--demo`; deaf-zone refusal.
- **20d — Translation, interpreter sessions and summaries for apps**, with staff approval for summaries.
- **Robot side (job 2, Python, outside this plan):** `b16_lien_serveur` sends `utterance` and handles `brain.reply`, instead of running `b06` locally; the robot keeps gardien, prise, voice out and the deaf-zone cut. Needs the security reviewer.

---

### Task A7: Pseudonymous accounts — the server does not know who a user is (inserted Nov 15)

The lead's direction (Nov 15): **the server must not know who the user is.** Credentials are hashed **on the client**; the result is the index to that user's data. If the database leaks, no record says whose it is. (Data a user wrote that contains names stays readable: this is an extra layer, not end-to-end encryption.)

**Design (rulings, the lead may override):**
- **Client side:** the client never sends the username or the password. It derives `account_key = PBKDF2-HMAC-SHA256(password, salt = "clinic:" + clinic_id + ":" + lowercase(username), 600 000 iterations, 32 bytes)` with the browser's WebCrypto (no extra library, works offline) or the equivalent in Flutter. `account_key` is sent at login.
- **Server side:** the server never stores `account_key` either (it is password-equivalent: storing it would let a leaked database log in). It stores `account_id = HMAC-SHA256(pepper, account_key)`, where `pepper` is a secret key file outside the database (like the journal key). Login: recompute, look up, compare in constant time. A leaked database alone cannot be used to log in, nor to test password guesses without the pepper.
- **What a record holds:** `account_id`, `role`, `display_label` (a pseudonym the user or the admin chooses, e.g. "Nurse 7", never a real name), `created_at`, `disabled`. No username, no email, no real name, anywhere on the server.
- **Enrolment without the server learning names:** an admin creates a one-time **enrolment code** for a role (and a suggested pseudonym). The new user types the code, chooses username + password on their own device, the client derives `account_key` and sends `{enrolment_code, account_key, display_label}`. The code is single use, expires (24 h), and is journaled by code id only.
- **Audit and owner labels** show the pseudonym and a short account tag (first 6 hex of `account_id`), never anything else. Tasks' `requested_by`, tablet owners and audit actors follow this.
- **Consequences to accept:** a forgotten password cannot be recovered (the admin disables the account and issues a new enrolment code; data tied to the old account stays under the old id); the 600 000-iteration derivation takes ~0.3–1 s on a tablet (once per login); usernames can no longer be listed or searched by the admin.
- **Mock mode** follows the same flow with the demo credentials (the console computes the key; the mock knows only the derived ids).
- This changes the A3 login contract: `POST /auth/login {account_key}` → `{token, role, operator, expires_at}`; `POST /auth/enrol {enrolment_code, account_key, display_label}`; `POST /admin/enrolment-codes {role, label?}` (admin) → `{code, expires_at}`; `DELETE /admin/accounts/{account_tag}` disables. The console (thin-client plan, new task F9) and the staff app compute the key.

**Files:** `crates/domain/src/account.rs`, `crates/security/src/accounts.rs` (pepper, HMAC, constant-time compare), `crates/storage/src/accounts.rs` + migration (replaces the `users` table's username/PIN columns), `src/routes/auth.rs`, `src/services/auth.rs`, `src/services/mock.rs`, `src/dto.rs`, docs (`architecture.md` C3 and privacy rules, `docs/accounts.md` with the exact derivation so every client implements it identically, a test vector).

- [ ] **Step 1: Declare** the types, routes and services with `todo!("T8: …")` bodies (Task 8 fills them); remove username/PIN from the contract.
- [ ] **Step 2: Tests** (ignored where they reach stubs): `server_never_receives_username_or_password` (request DTOs have no such fields), `database_dump_contains_no_account_key_and_no_username`, `login_with_derived_key_works_and_wrong_key_fails_identically`, `enrolment_code_is_single_use_and_expires`, `leaked_db_without_pepper_cannot_log_in` (copy the DB, swap the pepper, login fails), `audit_shows_pseudonym_and_account_tag_only`, `derivation_test_vector_matches_docs` (a fixed username/password/clinic → known key, shared with the clients).
- [ ] **Step 3: Verify** green, check OK, `openapi.yaml` regenerated.

---

### Task A8: What the updated console needs (inserted Nov 15)

Source of truth: `implementation/admin/requirements/` (`README.md`, `emergency-mode.md`, `tablets.md`, `monitoring-security.md`, `map-route-heat.md`), written against the console's readers; its JSON examples are the console's test fixtures. **Those files govern field names, codes and behaviour**; this task only adds the server-side decisions. Contract task (declarations, `todo!` bodies, ignored tests) **plus real `--mock` implementations**, because the lead tests the console against `--mock`.

**Rulings:**
- **Emergency mode** (`emergency-mode.md`): `GET/PUT /system/mode`, persisted, `mode.updated` + `alert`, the 503 `emergency_mode` filter as one middleware with the documented allow-list, robots cleared to docks (cancel+requeue tasks without a load, pause robots holding an item, leave estop/fault/charging alone), no dispatch or night round while on, resume only what the server paused on exit. It never touches the emergency service. The estop and `POST /robots/{id}/command` are always allowed.
- **Tablets** (`tablets.md`) merge into A5's device registry: the tablet object adds `kind`, `label`, `speciality` (staff only), `battery_pct`, `online`, `assigned`, `last_seen`; `GET /devices`, `POST /devices/{id}/disconnect`, `POST /devices/{id}/assign`, `device.updated`. The A5 `patient_name` (staff-tablet-only) never appears in any of these admin responses. Positions stay unpersisted (R1).
- **Monitoring and blocking** (`monitoring-security.md`) extend the security crate (Task 7): per-address counters in memory (5 min), rate limit 20/s burst 40, auto-block after 5 s over the limit or 10 failed logins in 60 s, manual blocks with protected targets (caller, loopback, connected robots, emergency service, ranges broader than /16 or /48), `GET /monitor/summary`, `/monitor/traffic`, `/monitor/clients`, `GET/POST/DELETE /security/blocks`, `security.alert` to admin sockets only (at most one `rate_limited` per address per minute). All thresholds in `.env`. **An authenticated admin's robot command is never refused by any rule.**
- **Service stats** (`GET /stats/service`): counts only, top 6 items/places, optional k-anonymity fold below 3.
- **Map** (`map-route-heat.md`): `map.updated` is published by 10b; `MapView::of` is 10b; the mock route answers 404 `no_route` for a task without a start place (or plans from the robot's position) instead of a fixed floor-2 route.

**Phase B fills:** **E1 — Emergency mode** (middleware, mode store, robot clearing, mock real); **7b — Monitoring and blocks** (with Task 7); **8b — Devices** (extended per tablets.md); **11e — Service stats**; the map items are in **10b**. Suggested order (README's "most for the least"): 10b's `map.updated`, E1, 7b's summary/traffic, 7b's blocks/clients/alerts, 8b, 11e.

- [ ] **Step 1: Declare** every route, DTO, event and service above (snake_case exactly as the requirement files' JSON), bodies `todo!("E1|T7b|T8b|T11e|T10b: …")`; implement them for real in `--mock` (in-memory), so the console's Monitor, Emergency switch and Tablets panels work against `cargo run -- --mock`.
- [ ] **Step 2: Tests**: one contract test per JSON example in the requirement files (byte-for-byte key sets and codes), the emergency allow-list (every route in the table allowed, a sample of others 503), protected block targets, estop never refused by blocks/limits/mode, no personal data in monitor/stats/devices responses; ignored with their fill ids except the mock ones.
- [ ] **Step 3: Verify** green, check OK, `openapi.yaml` regenerated, `implementation/admin/requirements/README.md` status column left to the console owner (do not edit console files).

---

**Phase B tasks added for the A5 contract:** **8b — Devices** (registry, bedside/staff, owner from login, tablet WS filtering); **12b — Follow and attend tasks** (task rules, target position feed, stale-stop, time limit); **14b — Live routes** (robot.plan forwarding, server-estimate fallback, suggestion validation and round trip, simulator follows suggestions and reports plans, mock support so the console can use it in `--mock`).

---

### Task 2: `domain` crate

**Files:**
- Create: `crates/domain/src/{lib.rs, ids.rs, role.rs, task.rs, robot.rs, actor.rs, clock.rs, wire.rs, error.rs, ports.rs}`, `docs/task-states.md`
- Test: tests inside each module

**Interfaces:**
- Produces (used by every crate):
  - Ids: `TaskId, RobotId, DeviceId, UserId, PlaceId, ZoneId, ItemId` as newtypes. `FromStr`/`TryFrom<String>` validate 1–64 chars of `[a-z0-9_-]`, else `DomainError::InvalidId { kind: &'static str, value: String, reason: &'static str }`. Serde as plain strings.
  - `OwnerLabel` newtype: 1–40 visible characters, no digits-only strings, trimmed. A pseudonymous display label, never a full name by convention (documented).
  - `Role { Nurse, Doctor, Therapist, Reception, Admin, Robot }` and `Permission` enum with `Role::allows(&self, Permission) -> bool`. `Permission::Estop` and zone editing are `Admin` only.
  - `TaskState { Requested, Assigned, EnRoute, Delivered, Failed, Resumed }` and `Task::transition(&mut self, next: TaskState, reason: Option<FailureReason>, at: DateTime<Utc>) -> Result<(), DomainError>`.
  - `RobotStatus { Idle, Busy, Paused, Fault, Estop, Offline }`.
  - `Actor { User(UserId), Device(DeviceId), Robot(RobotId), System(&'static str) }`.
  - `trait Clock: Send + Sync { fn now(&self) -> DateTime<Utc>; }`, `SystemClock`, and `FakeClock` (settable, for tests, behind a `testing` feature).
  - `ErrorBody { error: ErrorDetail { code: String, message: String, request_id: Option<String> } }` in `wire.rs`, shared by `security` and the API crate.
  - Repository ports in `ports.rs` (`#[async_trait]`): `TaskRepository, InventoryRepository, UserRepository, DeviceRepository, RobotRepository, ZoneRepository, ScheduleRepository`. Method lists are fixed by Tasks 6, 12, 16 and 17 when they implement them.
  - `DomainError` (thiserror).
  - Added by Task A1 (names the skeleton needed): `ScheduleId`; `TaskDraft`, `TaskParts`, `Task::{new, restore, assign_to, mark_needs_human, summary}` and getters; `TaskSummary`; `TaskKind`; closed `FailureReason` list; `TaskFilter`; `Page::new` (1-500); `TaskState::{can_go_to, is_terminal}`; `Permission` variant list and `name()`; `ErrorBody::new`; `Actor::KNOWN_SYSTEM_NAMES` and a manual `Deserialize` for `Actor`. Moved here by the ports pattern (lower crates need them): `SubjectRef`, `CommandName`, `SeenItem`, `ZoneKind`, `ZoneVersions`, `StockLedger`, `Reservation`, `ReconcileOutcome`, `StockError`, `ApplyOutcome`, `StockLevel`, `StockAdjustReason`. Records `UserRecord, DeviceRecord, RobotRecord, RobotFix, ZoneRecord, ScheduleRecord`; port method lists as declared in `ports.rs`; `DomainError` variants `MissingFailureReason, InvalidOwnerLabel, MissingTaskField, InvalidPage, InsufficientStock, StoreUnavailable, Conflict, NotFound, Corrupt`.

- [ ] **Step 1: Extract the real transition table.** Read `briques/clinique/taches.py` (`changer_etat` and the state list) and write the legal transitions into `docs/task-states.md`. This table is the source for the tests below. If the Python allows transitions this plan did not anticipate, the Python wins.
- [ ] **Step 2: Write the failing tests.** `task_requested_to_assigned_ok`, one test per illegal transition asserting the message contains both state names and the words "not allowed" (for example `delivered_to_en_route_is_rejected_with_explicit_message`), `failed_requires_a_reason`, `id_rejects_uppercase_and_spaces`, `id_rejects_65_chars`, `owner_label_rejects_empty_and_whitespace_only`, `nurse_cannot_estop`, `admin_can_estop`, `every_error_variant_has_nonempty_message` (iterates a `DomainError::samples()` test helper).
- [ ] **Step 3: Run `cargo test -p domain`.** Expected: fails to compile (types missing).
- [ ] **Step 4: Implement** the signatures above. State transitions live in one `match` on `(from, to)` inside `TaskState::can_transition_to`, and `Task::transition` is the only mutator (fields private).
- [ ] **Step 5: Run `bash scripts/check.sh`.** Expected: green.
- [ ] **Step 6: Commit** `feat(domain): ids, roles, task state machine, ports`.

---

### Task 3: `realtime` protocol types (contract C2)

**Files:**
- Create: `crates/realtime/src/{lib.rs, protocol.rs, error.rs}`, `docs/ws_messages.md`

**Interfaces:**
- Consumes: `domain` ids, `TaskState`, `RobotStatus`.
- Produces:
  - `Envelope<T> { id: Uuid, ts: DateTime<Utc>, body: T }`, serialised flat with a `"type"` tag from `T`.
  - `RobotUp { Hello{robot_id, role_card, capabilities, simulated, running_task: Option<TaskId>}, State{pos, battery_pct, status, holding, mic_open}, TaskEvent{task_id, state, reason}, InventorySeen{place, items: Vec<SeenItem{item, count: Option<u32>, uncertain: bool}>}, ZoneAck{zone_version_by_id} }`.
  - `RobotDown { TaskAssign{..}, TaskCancel{task_id}, ZonesUpdate{zones, version}, MapUpdate{version}, Command{name: CommandName} }`, `CommandName { Pause, Resume, Dock, Estop, Shutdown }`.
  - `AppEvent { Snapshot, TaskUpdated, RobotUpdated, PositionsDelta, InventoryUpdated, ZoneUpdated, Alert{kind: AlertKind, message}, Resync }`.
  - `const MAX_MESSAGE_BYTES: usize = 64 * 1024;`
  - `fn decode_robot_up(bytes: &[u8]) -> Result<Envelope<RobotUp>, ProtocolError>`; `ProtocolError { TooLarge{size, max}, UnknownType{type_name}, Malformed{reason}, MissingField{field} }`.
  - Added by Task A1 (names the skeleton needed): `Envelope::new`, `encode`, `decode_robot_down`; `RobotPose`, `WireZone`, `Positions`, `RobotPosition`, `TabletPosition`; `AlertKind` list; `AppEvent::IncidentUpdated`; `RobotUp::Hello.ble_id`; wire names `battery` and `state` (fields `battery_pct`, `status`).

- [ ] **Step 1: Write the failing tests.** `hello_roundtrips_json`, `decode_rejects_message_over_64kib_with_sizes_in_message`, `decode_unknown_type_returns_unknown_type_not_malformed`, `decode_missing_task_id_names_the_field`, `state_with_nan_battery_is_rejected`.
- [ ] **Step 2: Run `cargo test -p realtime`.** Expected: FAIL (module missing).
- [ ] **Step 3: Implement** the types and `decode_robot_up`. Unknown types must be distinguishable so callers can log and ignore them (architecture.md C2: unknown types are never fatal).
- [ ] **Step 4: Write `docs/ws_messages.md`** from the types, one example per message. Note two additions to C2 and update `implementation/architecture.md` in this same commit: `zones.ack` (robot to server) and `Resync` (server to apps).
- [ ] **Step 5: Run `bash scripts/check.sh`.** Expected: green. **Commit** `feat(realtime): websocket protocol types`.

---

### Task 4: API shell, mock services, OpenAPI, Scalar docs

**Files:**
- Create: `src/{main.rs, lib.rs, config.rs, state.rs, error.rs, openapi.rs}`, `src/routes/{mod,health,auth,tasks,inventory,map,zones,robots,schedules,audit}.rs`, `src/services/{mod.rs, mock.rs}`, `scripts/export_openapi.sh`, `docs/openapi.yaml`
- Test: `tests/api_shell.rs`

**Interfaces:**
- Consumes: `domain::{ErrorBody, ids, Role, TaskState}`.
- Produces:
  - `ApiError { status: StatusCode, code: &'static str, message: String }` implementing `IntoResponse` with `ErrorBody`; `From<DomainError>`. Variants are constructed through named constructors (`ApiError::not_found(what, id)`, `::invalid_input(field, reason)`, `::conflict(code, message)`), never struct literals in handlers.
  - `ApiJson<T>`: an extractor wrapping `axum::Json` that turns every rejection into an `ApiError` with code `invalid_json` or `invalid_field` and a message quoting the parser's position. A fallback handler for 404 (`not_found`) and 405 (`method_not_allowed`).
  - Service traits (`#[async_trait]`, in `services/mod.rs`): `AuthService, TaskService, InventoryService, MapService, ZoneService, RobotService, ScheduleService, AuditQueryService`, each returning `Result<_, ApiError>`. `AppState { auth: Arc<dyn AuthService>, tasks: Arc<dyn TaskService>, … }`.
  - `MockServices` implementing all traits with canned, clearly invented data.
  - `pub fn build_router(state: AppState) -> Router`.
  - Every route annotated with `#[utoipa::path]`; DTOs derive `ToSchema`; `ApiDoc` derives `OpenApi`. Scalar served at `/docs`, JSON at `/openapi.json`. Routes: every path in architecture.md C3 (`/auth/login`, `/me`, `/me/location`, `/tasks`, `/tasks/{id}`, `/tasks/{id}/cancel`, `/inventory`, `/inventory/{item}/adjust`, `/map`, `/zones`, `/zones/{id}`, `/robots`, `/robots/{id}/command`, `/schedules`, `/schedules/{id}`, `/audit`) plus `/health`.
  - CLI: `clinic-server [--mock] [--print-openapi]` (clap).
  - Added by Task A1 (names the skeleton needed): `ApiQuery`, `ApiPath`; `ApiError::{unauthorized, forbidden, journal_unavailable, unavailable, internal, route_not_found, method_not_allowed, code, status, message}`; `fallback_not_found`, `fallback_method_not_allowed`; `StartupError`, `ConfigError`, `Config::load`, `Cli`/`Command`/`JournalCommand`/`VerifyArgs`; DTOs in `src/dto.rs`; `AppState` fields (adds `locations`, `incidents`, `journal: Arc<dyn JournalStatus>`, `verifier`, `hub`, `ws_origins`, `clock`); `Wiring::{mock, real}`, `RealDeps`, `AppState::snapshot_event`; traits `LocationService`, `IncidentService`, `JournalStatus`; `TaskService::active`; `default-run = "clinic-server"`.

- [ ] **Step 1: Write the failing tests** with `tower::ServiceExt::oneshot`, no network: `health_returns_200`, `docs_page_is_served`, `openapi_lists_every_c3_path` (compares against the list above), `unknown_path_returns_error_body_with_code_not_found`, `wrong_method_returns_405_error_body`, `invalid_json_returns_400_with_position_in_message`, `missing_field_names_the_field`, `every_parameterised_route_matches_a_real_id` (hits `/tasks/t-1`, `/zones/z-1`, and the rest, guarding the axum 0.8 `{id}` syntax), `mock_task_creation_returns_requested_state`.
- [ ] **Step 2: Run `cargo test --test api_shell`.** Expected: FAIL.
- [ ] **Step 3: Implement** the shell and mock mode. The DTO field names are the C3 contract; copy them from architecture.md and `03_serveur.md`, and add the fields they leave open (pagination: `limit` 1–200 default 50 and `cursor`, on every list route).
- [ ] **Step 4: Export the spec.** `bash scripts/export_openapi.sh` writes `docs/openapi.yaml`. Add a test that the committed file equals the freshly generated one, so it cannot drift.
- [ ] **Step 5: Run `bash scripts/check.sh`.** Expected: green. **Commit** `feat(api): shell, mock services, openapi and scalar docs`.

---

### Task 5: Hub, fake robot, M0 gate

**Files:**
- Create: `crates/realtime/src/hub.rs`, `src/ws/{mod,apps,robots}.rs`, `src/bin/fake_robot.rs`
- Test: `tests/m0_fake_robot.rs`
- Modify: `docs/ws_messages.md`

**Interfaces:**
- Consumes: Task 3 protocol, Task 4 `AppState`.
- Produces:
  - `Hub::new() -> Hub`, `Hub::subscribe_apps(&self) -> broadcast::Receiver<AppEvent>`, `Hub::publish(&self, AppEvent)`, `Hub::register_robot(&self, RobotId) -> Result<RobotSession, RealtimeError>` where `RobotSession::send(&self, RobotDown) -> Result<(), RealtimeError>` and `RobotSession::recv(&mut self) -> Option<Envelope<RobotUp>>`.
  - WS routes `GET /ws` and `GET /ws/robot/{id}` (no auth yet; mock mode only until Task 14).
  - `fake_robot --server ws://… --id robot-r2 --simulated`: sends `hello`, then `State` every 1 s along a polyline between three places, and on `TaskAssign` replies with `TaskEvent` `assigned` → `en_route` → `delivered` with 2 s gaps.
  - Added by Task A1 (names the skeleton needed): `Hub::{with_clock, unregister_robot, send_to_robot, connected_robots, is_connected}`; `RobotSession::{robot, take_link}` and the socket side `RobotLink::{next_down, push_up}`; `RobotService::{is_known, run_session, on_disconnect}`.

- [ ] **Step 1: Write the failing test** `fake_robot_position_reaches_app_websocket_within_3s`: start the mock server on port 0, connect an app WS client, spawn the fake robot, assert a `RobotUpdated` arrives within 3 s with the robot id. Add `task_created_over_rest_reaches_fake_robot_and_delivers`.
- [ ] **Step 2: Run it.** Expected: FAIL.
- [ ] **Step 3: Implement** `Hub` and the two handlers. In mock mode the REST `POST /tasks` forwards `TaskAssign` to the fake robot's session.
- [ ] **Step 4: Run `bash scripts/check.sh`, then hand over.** Send jobs 4 and 5 the URLs of `/docs` and `/openapi.json` and the fake robot command line. **M0 gate:** each of the two confirms it can build against them. Do not start Task 6 before this.
- [ ] **Step 5: Commit** `feat: websocket hub and fake robot (M0)`.

---

### Task 6: `storage` crate: identity tables

**Files:**
- Create: `crates/storage/src/{lib.rs, pool.rs, users.rs, devices.rs, robots.rs, tokens.rs, error.rs}`, `migrations/0001_identity.sql`, `scripts/export_seeds.py`, `seed/{users.json, robots.json, role_cards.json}`
- Modify: `scripts/check.sh` (add `cargo sqlx prepare --check`)

**Interfaces:**
- Consumes: `domain::ports::{UserRepository, DeviceRepository, RobotRepository}`.
- Produces:
  - `Database::connect(url: &str) -> Result<Database, StorageError>`, `Database::migrate(&self)`.
  - `SqliteUserRepository, SqliteDeviceRepository, SqliteRobotRepository, SqliteTokenStore`, each `::new(Database)`.
  - Token store: `issue(&self, subject: TokenSubject, ttl: Duration) -> Result<RawToken, StorageError>` stores only the SHA-256 of a 32-byte random value; `resolve(&self, raw: &str) -> Result<Option<TokenSubject>, StorageError>`; `revoke`. `TokenSubject { User{user_id, role, device_id}, Robot{robot_id} }`.
  - `StorageError` (thiserror) with `Unavailable`, `Conflict{what}`, `NotFound{what}`, `Corrupt{table, reason}`; no sqlx text in `Display`.
  - Tables: `users(id, role, display_label, pin_hash)`, `devices(id, user_id nullable, registered_at)`, `robots(id, name, role_card, simulated, key_hash)`, `tokens(hash, subject_json, expires_at, revoked_at)`.
  - Added by Task A1 (names the skeleton needed): `Database::{in_memory, pool}`; `StorageError::Migration`; `RawToken::expose` (redacted `Debug`); `From<StorageError> for DomainError`; `SqliteRobotRepository::{save_last_fix, last_fix}` (robot types only, ruling R1).

- [ ] **Step 1: Write `export_seeds.py`.** Reads `briques/clinique/{badges.yaml, flotte.yaml, cartes_de_role/*.yaml}` and writes the JSON seeds, each with `"marque": "inventé"`. PINs are generated randomly at seed time and printed once, never committed.
- [ ] **Step 2: Write the failing tests** with `#[sqlx::test]`: `token_roundtrip_returns_subject`, `raw_token_is_not_stored` (query the table, assert the raw string appears nowhere), `expired_token_resolves_to_none`, `revoked_token_resolves_to_none`, `duplicate_user_id_returns_conflict_with_id_in_message`, `seed_is_idempotent_when_run_twice`.
- [ ] **Step 3: Run `cargo test -p storage`.** Expected: FAIL.
- [ ] **Step 4: Implement** the migration and repositories using the `query!` family so the offline cache covers them. `cargo sqlx prepare` and commit `.sqlx/`.
- [ ] **Step 5: Run `bash scripts/check.sh`.** Expected: green. **Commit** `feat(storage): identity tables, token store, seeds`.

---

### Task 7: `security` crate

**Files:**
- Create: `crates/security/src/{lib.rs, cors.rs, limits.rs, rate_limit.rs, known_networks.rs, identity.rs, origin.rs, stack.rs, error.rs}`, `seed/known_networks.json`

**Interfaces:**
- Consumes: `domain::{ErrorBody, DeviceId, OwnerLabel, PlaceId, Role}`.
- Produces:
  - `CorsPolicy::new(allowed_origins: Vec<String>) -> Result<CorsPolicy, SecurityError>` (rejects `"*"`, rejects non-URL origins), `CorsPolicy::layer(&self) -> tower_http::cors::CorsLayer`. Allows methods GET, POST, PUT, DELETE, OPTIONS; headers `authorization`, `content-type`, `x-client-id`; max-age 600 s.
  - `RequestLimits { max_body_bytes: usize, timeout: Duration, max_in_flight: usize }`.
  - `RateLimiter::new(RateLimitConfig { per_second: NonZeroU32, burst: NonZeroU32 }) -> RateLimiter`, a keyed limiter per client IP using `governor`. tower-http has no rate limiter, so this is our own middleware: on excess it returns 429, code `rate_limited`, header `Retry-After`, and a message with the wait in seconds.
  - `KnownNetworks::new(entries: Vec<NetworkEntry { cidr: IpNet, label: String, area: Option<PlaceId> }>, trusted_proxies: Vec<IpNet>) -> Result<KnownNetworks, SecurityError>`, `KnownNetworks::resolve(&self, peer: SocketAddr, forwarded_for: Option<&str>) -> Option<ClientNetwork { ip, label, area }>`. The forwarded header is read only when `peer` is in `trusted_proxies`.
  - `trait TokenVerifier: Send + Sync { async fn verify(&self, raw: &str) -> Result<Option<VerifiedIdentity>, SecurityError>; }` and `VerifiedIdentity { subject_id, role, device_id: Option<DeviceId>, owner: Option<OwnerLabel> }`.
  - `ClientIdentity { verified: VerifiedIdentity, network: ClientNetwork }` inserted as a request extension. The `X-Client-Id` header, when present, must equal `device_id`, else 403 `identity_mismatch`.
  - `OriginCheck::new(allowed: Vec<String>)`, used on WebSocket upgrades: a missing or unlisted `Origin` is rejected 403 `origin_not_allowed`. (Native app clients send no `Origin`; allowed only on routes configured `allow_missing_origin`.)
  - `SecurityStack::new(config: SecurityConfig, verifier: Arc<dyn TokenVerifier>) -> Result<SecurityStack, SecurityError>`, `SecurityStack::apply(&self, Router) -> Router`. Layer order, outermost first: trace, catch-panic, timeout, body limit, concurrency limit, CORS, known network, rate limit, identity. A comment in `stack.rs` explains why (CORS preflight must pass before identity; unknown IPs must be rejected cheaply before any token lookup; rate limit before identity so password guessing is throttled).
  - Added by Task A1 (names the skeleton needed): `SecurityConfig` fields (`cors_origins, limits, rate, networks, trusted_proxies, ws_origins, ws_allow_missing_origin, public_paths`); `OriginCheck::{allow_missing_origin(bool), check}`; `RateLimiter::check`; `NetworkEntry::load_file`; `SecurityError` variants (`UnknownNetwork { ip }`, code `network_not_allowed`) and `code()`/`status()`; `CLIENT_ID_HEADER`; `VerifiedIdentity.subject_id: Actor`.

- [ ] **Step 1: Write the failing tests** using `tower::ServiceExt` with `ConnectInfo<SocketAddr>` set by hand: `cors_preflight_from_allowed_origin_passes_without_token`, `cors_disallowed_origin_gets_no_allow_origin_header`, `cors_rejects_wildcard_config`, `unknown_ip_gets_403_network_not_allowed_naming_the_ip`, `forwarded_for_from_untrusted_peer_is_ignored` and `forwarded_for_cannot_turn_unknown_ip_into_known` (Review Focus 3), `known_network_attaches_label_and_area`, `burst_plus_one_returns_429_with_retry_after`, `different_ips_have_separate_budgets`, `body_over_limit_returns_413_error_body`, `slow_handler_returns_408_error_body` (timeout), `identity_header_mismatch_returns_403`, `missing_token_returns_401_with_explicit_message`, `websocket_upgrade_from_foreign_origin_is_rejected`, `handler_error_returns_500_error_body_without_internal_detail`. The catch-panic layer stays installed as a last-resort safety net and is deliberately **not** tested with a panicking handler, because the project forbids `panic!` even in tests.
- [ ] **Step 2: Run `cargo test -p security`.** Expected: FAIL.
- [ ] **Step 3: Implement** each type. `SecurityRejection` implements `IntoResponse` with `domain::ErrorBody`, so every layer's failure looks like every other API error.
- [ ] **Step 4: Run `bash scripts/check.sh`.** Expected: green. **Commit** `feat(security): cors, limits, known networks, identity`.

---

### Task 8: Auth service and routes

**Files:**
- Create: `src/services/auth.rs`, `src/extractors.rs`
- Modify: `src/routes/auth.rs`, `src/lib.rs` (apply `SecurityStack`), `src/state.rs`
- Test: `tests/auth.rs`

**Interfaces:**
- Consumes: `storage::{SqliteUserRepository, SqliteTokenStore}`, `security::{SecurityStack, TokenVerifier}`.
- Produces:
  - `AuthService::login(&self, user_id: &UserId, pin: &str, device: DeviceId, network: &ClientNetwork) -> Result<LoginResponse { token, role, owner_label, expires_at }, ApiError>`; PIN verified with `argon2`; the same message for unknown user and wrong PIN ("User id or PIN is incorrect."), with a constant-time-ish path (hash a dummy when the user does not exist). A failed login writes no PIN anywhere.
  - WebSocket auth (Task A3): `/ws` reads a first message `{type:"auth", token}` within 5 s, verifies it with the same `TokenVerifier` as REST, refuses robot tokens, closes 4401 with an explicit reason otherwise. No ticket route exists.
  - Extractors `Authenticated(ClientIdentity)` and `RequireRole<const R: ...>`-style guards, or one `Authorized<P: PermissionMarker>`; a role without the permission gets 403 `forbidden` naming the permission.
  - `impl TokenVerifier for SqliteTokenStore`.
  - Added by Task A1 (names the skeleton needed): `AuthService::me` (`redeem_ws_ticket` removed in A3); extractor `Network`; `PermissionMarker`, `perm::*` markers, `Authorized<P> { identity }`; `build_app(state, &SecurityStack)` (`build_router` stays without security for handler tests); `TokenStoreVerifier` newtype in `src/services/auth.rs` (ruling R3, replaces `impl TokenVerifier for SqliteTokenStore`); `RealAuthService`, `AuthDeps`.

- [ ] **Step 1: Write the failing tests.** `login_with_correct_pin_returns_token_and_role`, `wrong_pin_and_unknown_user_have_identical_response_bodies`, `five_failed_logins_from_one_ip_return_429` (uses the rate limiter), `token_is_bound_to_the_device_it_was_issued_for`, `nurse_token_cannot_call_put_zones_gets_403`, `ws_auth_first_message_accepts_valid_token`, `ws_without_auth_message_closes_after_5s_with_4401`, `me_returns_owner_label_and_nothing_else_about_the_person` (asserts the exact key set).
- [ ] **Step 2: Run `cargo test --test auth`.** Expected: FAIL.
- [ ] **Step 3: Implement.** Swap `MockServices.auth` for the real service when `--mock` is absent; keep the others mocked.
- [ ] **Step 4: Run `bash scripts/check.sh`.** Expected: green. **Commit** `feat(api): login, roles, websocket first-message auth`.

---

### Task 9: `audit` crate: sealed journal, flight recorder, verification

The journal is the authority on what happened. It is a set of append-only files, hash-chained record by record, and **sealed** every `seal_interval` (default 60 s, configurable) by a signed record that covers everything before it.

**Why sequence numbers instead of a 1-second overlap.** The lead's concern: a record created just before a seal, but written just after it, must not escape. A time window (seal includes records up to 1 s before itself) only works if lateness is bounded, and it is not: a robot that was offline sends events minutes old. So:
- **One writer task** assigns a gapless sequence number (`seq`) to every record, in arrival order. A seal is a request in the *same* queue as the records, so every record submitted before the seal request is written before the seal and covered by it. A record submitted after the request gets a higher `seq` and goes into the next seal. Nothing can fall between two seals, because seals cover contiguous `seq` ranges and the verifier checks contiguity.
- Every record carries two times: `ingested_at` (server clock, when written) and `event_at` (when it happened, from its source). A record whose `event_at` is older than the previous seal is sealed normally and flagged `late_by_ms`, so a late arrival is visible, never lost and never mistaken for tampering.

**Why a signature and an anchor.** A hash chain alone can be recomputed by anyone who can write the files. Seals are signed with an Ed25519 key kept outside the journal directory, and each seal's hash is also copied to anchors the server cannot rewrite in the same operation: a second append-only file on another disk or USB path, and a live event to the admin panel.

**Files:**
- Create: `crates/audit/src/{lib.rs, record.rs, journal.rs, segment.rs, seal.rs, signer.rs, anchor.rs, flight_recorder.rs, tracing_layer.rs, redact.rs, verify.rs, index.rs, error.rs}`, `migrations/0002_audit_index.sql`, `docs/journal.md`
- Modify: `src/main.rs` (start journal first, seal on shutdown), `src/lib.rs` (degraded mode), CLI subcommand `clinic-server journal verify`
- Test: `crates/audit/tests/{journal.rs, seal.rs, verify.rs, flight_recorder.rs}`

**Interfaces:**
- Consumes: `domain::{Actor, Clock}`.
- Produces:
  - `Severity { Info, Notice, Warning, Error, Critical }`, `Category { Audit, Security, Robot, System, Incident, Seal }`.
  - `JournalRecord { seq: u64, ingested_at, event_at: Option<DateTime<Utc>>, late_by_ms: Option<u64>, severity, category, actor: Actor, body: RecordBody, prev_hash: [u8; 32], hash: [u8; 32] }`. `RecordBody` is a typed enum (`LoginSucceeded{device}`, `LoginFailed{device, network}`, `TaskCreated{..}`, `TaskStateChanged{..}`, `StockAdjusted{..}`, `ZoneChanged{..}`, `RobotCommandSent{..}`, `EstopSent{robot, delivered}`, `ScheduleChanged{..}`, `ScheduleMissed{..}`, `SecurityRejected{code, network}`, `SystemEvent{target, message}`, `Incident{trigger, recent: Vec<FlightEvent>}`, `Seal(Seal)`). No free-text field accepts user input, so nothing personal can be put in by accident. `hash = SHA-256(prev_hash ‖ canonical JSON of the record without hash)`.
  - `JournalConfig { dir: PathBuf, seal_interval: Duration (60 s), segment_max_bytes: u64 (64 MiB), batch_fsync: Duration (1 s), key_path: PathBuf, anchor_paths: Vec<PathBuf>, flight_window: Duration (30 s), flight_capacity: usize (10_000) }`.
  - `Journal::start(config, clock: Arc<dyn Clock>, signer: Box<dyn Signer>) -> Result<(Journal, JoinHandle<()>), JournalError>`: opens the last segment, verifies its tail, resumes `seq`, spawns the single writer.
  - `Journal::append(&self, severity, category, actor, body, event_at: Option<DateTime<Utc>>) -> Result<RecordReceipt { seq, hash }, JournalError>`. `Critical` records are `fsync`ed before `append` returns and trigger an immediate seal. Other records are fsynced in batches every `batch_fsync`, so a power cut can lose at most that much non-critical data (written in `docs/journal.md`).
  - `Journal::seal_now(&self, reason: SealReason { Interval, Critical, Shutdown, Rotation }) -> Result<Seal, JournalError>`.
  - `Seal { first_seq, last_seq, count, chain_head: [u8; 32], prev_seal_hash: [u8; 32], sealed_at, oldest_event_at, latest_event_at, late_records: u32, sealed_files: Vec<FileDigest { name, sha256, bytes }>, key_fingerprint, signature }`. `sealed_files` holds the digests of rotated operational log files (the `tracing-appender` daily files), so those are covered too.
  - `trait Signer { fn sign(&self, msg: &[u8]) -> Result<Signature, JournalError>; fn fingerprint(&self) -> String; }`, `Ed25519FileSigner::load(path)` (key created on first start, file permissions checked, refuses a world-readable key with an explicit message).
  - `AnchorSink::append(&self, seal_hash, last_seq, sealed_at)`. Anchor failures are `Error` records and an admin alert, never silent.
  - `FlightRecorder`: a `tracing` layer that keeps the last `flight_window` of events at DEBUG and above in a bounded ring in memory. On any `Critical` record it is dumped into an `Incident` record, so a grave event comes with everything that led up to it.
  - `JournalLayer`: a `tracing` layer that copies WARN and above into the journal as `SystemEvent`, after `Redactor` has dropped fields named `token`, `pin`, `password`, `key`, `rssi`, `point`, `position`, `place` when attached to a tablet.
  - `verify(dir, public_key, anchors) -> VerifyReport { records, seals, first_bad_record: Option<u64>, gaps: Vec<(u64, u64)>, bad_seals: Vec<u64>, anchor_mismatches: Vec<u64>, torn_tail: bool }`. A half-written last line after a power cut is reported as `torn_tail` (expected after a crash), distinct from tampering.
  - `AuditIndex`: a database table rebuilt from the journal for `GET /audit` queries (filters, pagination, `limit` 1–500 with an explicit error above). It is a convenience copy; the files are the authority. `GET /audit/integrity` returns the last `VerifyReport`.
  - **Degraded mode:** if the journal cannot write, every mutating route returns 503 `journal_unavailable` ("Actions are paused because they cannot be recorded."). The emergency stop is the exception: it is always sent, and its record goes to the emergency fallback file named in `JournalConfig`. Safety before bookkeeping.
  - Critical triggers: estop sent or not delivered, verification failure, an en-route robot lost, ten or more rejected logins in a minute from one network, a journal write failure, a configuration change by an admin.
  - Added by Task A1 (names the skeleton needed): `Journal::{close, is_writable, flight_recorder, subscribe_seals, record_estop_fallback}`; `JournalConfig::{emergency_fallback, log_dir, with_defaults}`; `load_verifying_key`, `Ed25519FileSigner::verifying_key`; `VerifyReport::is_clean`; `AnchorSink` is a trait with `FileAnchor`; `AuditIndex` is a port trait with `AuditQuery`/`AuditPage`, implemented by `SqliteAuditIndex` in `crates/storage/src/audit_index.rs`; `IncidentTrigger`; `RecordBody::IncidentChanged`; `Signature`; `record::hex_bytes`; `Segment`/`TailState`; `JournalRecord::{canonical_bytes, compute_hash}`; `JournalAuditQuery`, `spawn_seal_forwarder`, `impl JournalStatus for Journal`.

- [ ] **Step 1: Write the failing tests.** `seq_is_gapless_and_survives_restart`; `seal_covers_every_record_submitted_before_it` (ten tasks append 1,000 records while another requests seals; every record submitted before a seal request completed has `seq <= that seal's last_seq`, seals are contiguous); `record_submitted_during_a_seal_lands_in_the_next_seal`; `late_robot_event_is_flagged_with_lag_and_still_sealed`; `changing_one_byte_is_reported_with_its_seq`; `deleting_a_record_is_reported_as_a_gap`; `recomputed_chain_without_the_key_fails_the_signature_check`; `anchor_disagreement_is_reported`; `torn_last_line_is_torn_tail_not_tampering`; `critical_record_is_fsynced_before_append_returns` (a `SyncProbe` test double counts fsync calls); `critical_record_triggers_seal_and_incident_with_recent_events`; `flight_recorder_keeps_only_the_window`; `rotated_log_file_digest_appears_in_next_seal`; `redactor_drops_token_pin_and_tablet_location`; `journal_failure_returns_503_on_mutations_but_estop_still_goes_out`; `world_readable_key_is_refused_with_explicit_message`; `audit_query_limit_above_500_is_rejected`.
- [ ] **Step 2: Run `cargo test -p audit`.** Expected: FAIL.
- [ ] **Step 3: Implement.** Start the journal before anything else in `main.rs`; seal with `SealReason::Shutdown` during graceful shutdown. The login service from Task 8 now journals `LoginSucceeded` and `LoginFailed` (device and network, never the PIN).
- [ ] **Step 4: Verify by hand once.** Run the server, make a few requests, stop it, run `clinic-server journal verify --dir journal/`: expected "OK", exit code 0. Edit one byte of a segment and run it again: expected the seq of the broken record and a non-zero exit code. Write both outputs into `docs/journal.md`.
- [ ] **Step 5: Run `bash scripts/check.sh`.** Expected: green. **Commit** `feat(audit): sealed journal, flight recorder, verifier`.

---

### Task 10: `locations` crate: the 3D clinic model

**Files:**
- Create: `crates/locations/src/{lib.rs, geometry.rs, model.rs, validate.rs, loader.rs, error.rs}`, `seed/clinic_map.json`, `docs/map-format.md`
- Modify: `src/services/map.rs`, `src/routes/map.rs`
- Test: `crates/locations/src/*` unit tests, `tests/map_route.rs`

**Interfaces:**
- Consumes: `domain::PlaceId`, `ZoneId`.
- Produces:
  - `Point2::new(x: f64, y: f64) -> Result<Point2, LocationError>` (finite only).
  - `Polygon::new(Vec<Point2>) -> Result<Polygon, LocationError>`: at least 3 vertices, non-zero area, no self-intersection, no repeated consecutive points. `Polygon::contains(&self, &Point2) -> bool`, `Polygon::centroid(&self) -> Point2`.
  - `Floor { level: i32, elevation_m: f64, height_m: f64, outline: Polygon, walls: Vec<Wall { start, end, thickness_m }> }`.
  - `Place { id: PlaceId, name: String, kind: PlaceKind, floor: i32, footprint: Polygon, anchor: Point2 }`, `PlaceLink { from: PlaceId, to: PlaceId, metres: f64 }`.
  - `Zone { id: ZoneId, kind: ZoneKind { Deaf, Restricted }, floor: i32, polygon: Polygon, version: u32 }`.
  - `ClinicMap::new(floors, places, links, zones) -> Result<ClinicMap, LocationError>` rejecting: duplicate ids, a place whose footprint is not inside its floor outline, a link naming an unknown place, a link with `metres <= 0`, a zone outside its floor. Accessors: `place(&PlaceId)`, `floor(i32)`, `places_on(i32)`, `zones_containing(i32, &Point2) -> Vec<&Zone>`, `version() -> MapVersion` (hash of canonical content).
  - Coordinate convention in `docs/map-format.md`: metres, x east, y north, z up, per-floor `elevation_m`. For Three.js (y up): `three.x = x`, `three.y = z`, `three.z = -y`. Job 5 reads this file.
  - `GET /map` returns the map as JSON with `ETag: <version>`; `If-None-Match` equal returns 304.
  - Added by Task A1 (names the skeleton needed): `ClinicMap::{floors, places, links, zones, place_at, unknown_place_error}`; `MapVersion::as_str`; `Polygon::{from_pairs, contains_polygon, vertices, to_pairs}`; `Point2::{x, y, distance}`; `load_map`, `parse_map`, `validate::validate`; `PlaceKind` variants; `RealMapService`.

- [ ] **Step 1: Author the seed.** Take names and floors from `briques/clinique/faux_dossier/lieux.yaml` (floors 0 and 2; read the whole file, only part of it was seen while planning) and the corridor graph from its `voisins` entries as `links`. Invent coordinates and walls. There is no elevator link between floors for robots (the Python world has none). Mark `"marque": "inventé"`.
- [ ] **Step 2: Write the failing tests.** `point_rejects_nan_and_infinity`, `bowtie_polygon_is_rejected_with_the_crossing_edges_named`, `polygon_with_two_points_is_rejected`, `contains_boundary_point_is_deterministic`, `place_outside_floor_outline_is_rejected_naming_the_place`, `link_to_unknown_place_is_rejected`, `duplicate_place_id_is_rejected`, `zones_containing_returns_overlapping_zones`, `version_changes_when_a_wall_moves`, `seed_map_loads_and_has_two_floors`, `get_map_returns_etag_and_304_on_match`.
- [ ] **Step 3: Run `cargo test -p locations`.** Expected: FAIL.
- [ ] **Step 4: Implement.** Geometry is hand-written (no GIS dependency) and small. Run `bash scripts/check.sh`.
- [ ] **Step 5: Commit** `feat(locations): validated 3d clinic model and /map`.

---

### Task 11: Live positions and the privacy filter

**Files:**
- Create: `crates/locations/src/{live.rs, privacy.rs, snapshot.rs}`, `src/services/location.rs`
- Modify: `src/ws/apps.rs`, `src/routes/map.rs` (add `GET /live`, implement `PUT /me/location`)
- Test: `crates/locations/tests/live.rs`, `tests/live_route.rs`

**Interfaces:**
- Consumes: `ClinicMap`, `domain::{Clock, RobotId, DeviceId, OwnerLabel, RobotStatus}`, `realtime::Hub`.
- Produces:
  - `PositionFix { subject: SubjectRef { Robot(RobotId), Tablet(DeviceId) }, floor: i32, point: Point2, heading_rad: Option<f64>, at: DateTime<Utc> }`.
  - `LivePositions::new(map: Arc<ClinicMap>, clock: Arc<dyn Clock>, ttl: PositionTtl { robot_stale: Duration, tablet_expiry: Duration }) -> LivePositions` (defaults 5 s and 120 s).
  - `LivePositions::update_robot(&self, fix: PositionFix, info: RobotInfo { status, task: Option<TaskSummary { id, kind }>, battery_pct: f32, mic_open: bool }) -> Result<(), LocationError>` rejects a floor not on the map and a point outside the floor outline (`PositionOutOfMap`).
  - `LivePositions::set_tablet(&self, device: DeviceId, owner: OwnerLabel, place: &PlaceId) -> Result<(), LocationError>`: the position is the place's anchor (honest: a tablet is only known to the room).
  - `LivePositions::snapshot(&self) -> LiveSnapshot { robots: Vec<RobotLive>, tablets: Vec<TabletLive>, map_version, at }`, pruning expired tablets. `RobotLive { id, name, status, task, battery_pct, mic_open, floor, point, heading_rad, stale: bool }`. `TabletLive { device_id, owner, place, floor, point, uncertainty_m: Option<f64> }` (`None` when the room was chosen by hand). **`TabletLive` has no other field, so privacy holds by construction.**
  - `PositionBroadcaster::spawn(live, hub, interval: Duration)` publishes `AppEvent::PositionsDelta` every 200 ms containing only subjects that changed, coalesced to the latest fix. A new `/ws` client first receives `Snapshot`.
  - `PUT /me/location { place }`: unknown place returns 422 `unknown_place` with message "Place 'X' is not on the map. Places on floor 2 include: …" (list capped at 10).
  - Added by Task A1 (names the skeleton needed): `RobotInfo.name`; `LivePositions::{update_robot_info, remove_robot, robot_fix, tablet_place, set_tablet_estimate(device, owner, &PositionEstimate), map}`; `PositionBroadcaster` lives in `src/services/location.rs` (joins `locations` and `realtime`); `to_wire_positions`; `privacy::public_point`; `LiveLocationService`.

- [ ] **Step 1: Write the failing tests** with `FakeClock`: `robot_silent_over_5s_is_marked_stale` and `stale_robot_keeps_last_position_but_flag_is_true` (Review Focus 5), `tablet_disappears_after_expiry`, `tablet_json_has_exactly_the_six_allowed_keys` (golden key set: `device_id, owner, place, floor, point, uncertainty_m`), `no_tablet_position_is_ever_passed_to_a_repository` (the type that persists robots cannot accept a tablet fix: a compile-level guarantee asserted by the test existing at all, plus a runtime check that no `Tablet` variant reaches `storage`), `position_with_nan_is_rejected`, `position_on_floor_9_is_rejected_naming_the_floor`, `position_outside_floor_outline_is_rejected`, `broadcaster_coalesces_ten_updates_into_one_delta`, `new_ws_client_gets_snapshot_first`, `put_location_unknown_place_lists_valid_places`.
- [ ] **Step 2: Run `cargo test -p locations`.** Expected: FAIL.
- [ ] **Step 3: Implement.** Log output must never include tablet positions: add a test that captures `tracing` output while a tablet moves and asserts the room name does not appear.
- [ ] **Step 4: Run `bash scripts/check.sh`.** Expected: green. **Commit** `feat(locations): live positions with privacy by construction`.

---

### Task 11b: Indoor positioning without beacons (P1, M2)

GPS does not work indoors. Without this task, a tablet's room comes from a hand pick or a QR code (Task 11). This task estimates positions from what the clinic already has: **the robots, the tablets, and the 3D plan**. No beacons are required; they are an optional add-on that plugs into the same code. It is solved on the server in one Rust implementation, so the Flutter app only scans and reports.

**What each device knows:**
- **A robot knows its own position** (its own localisation, or odometry from its past angles and distances moved, corrected against the map). It advertises a BLE identifier, so it is a **moving anchor**.
- **A fixed device is a free anchor:** a tablet mounted at the nurse station, a robot's charging dock. Registered once with its place.
- **A tablet measures** the BLE signal strength (RSSI) of robots and of other tablets nearby, and its own motion between scans: steps and heading from its motion sensors (pedestrian dead reckoning, PDR), and air pressure for the floor.

**Why that is enough, and its limits (to be written up as a proof in `docs/positioning-proof.md`, Step 4):**
- *Key reduction.* Suppose a tablet's displacement since time 0 is known from PDR: `p_k = p_0 + d_k`. A robot at known `q_k` measures `r_k = ‖p_k − q_k‖ = ‖p_0 − (q_k − d_k)‖`. So the moving tablet is equivalent to a **static** unknown `p_0` seen from **virtual anchors** `v_k = q_k − d_k`. In 2D, `p_0` is uniquely determined if there are at least 3 virtual anchors that are **not collinear**. One robot moving over time is enough.
- *Degenerate cases.* A robot that does not move, or a robot and tablet moving in parallel straight lines, gives collinear virtual anchors. The solution is then known only up to a **mirror image** across that line. The clinic plan often removes the ambiguity: the mirror point lies inside a wall or outside the floor.
- *Two tablets, one robot.* Tablet-to-tablet ranges couple the two. If one tablet is identifiable as above, it becomes an extra (uncertain) anchor for the second, which is then identifiable if its combined virtual anchors are not collinear. With no robot in range at all, ranges between devices fix their shape only up to rotation, translation and reflection: **at least one device of known position must be in range**, sometimes.
- *Precision: metres, not centimetres.* The geometry is fine, the radio is not. RSSI noise is about σ = 4–8 dB, which makes the range error about a third of the distance (≈ 1.5 m at 5 m). Averaging over many scans helps less than hoped because indoor errors are correlated (walls, bodies). PDR drifts by a few percent of the distance walked, so the virtual-anchor window must stay short. Expected result: **the right room most of the time, 1–3 m within it**. Centimetres need ranging radios (UWB or Bluetooth Channel Sounding), which this design accepts as a drop-in observation type.
- *Coverage.* With 4 robots in a clinic, a tablet can go minutes without a robot in range. Its uncertainty then grows with PDR drift until the next contact, and the UI shows the room only, or "last seen in …".

**The method, in four layers:**
1. **Anchors.** Robots (moving, only while their fix is under 1 s old and not stale), fixed devices, and optionally BLE beacons. Other tablets enter as uncertain anchors with their current estimate's spread.
2. **Distance from signal strength.** RSSI is smoothed per anchor (median of the last 5 readings, then exponential smoothing), then turned into a distance with the log-distance path-loss model `d = 10^((P_1m − RSSI) / (10·n))`, with `n` between 2 and 4 calibrated per site. Indoors this distance is noisy: several metres of error. That is why layers 3 and 4 exist.
3. **Trilateration and filtering.** With 3 or more anchors on the same floor, weighted least squares (Gauss-Newton, starting at the weighted centroid of the anchors) gives a first point. A particle filter then tracks the tablet over time: 500 particles, walking speed up to 1.5 m/s, **any particle whose move crosses a wall of the clinic plan is discarded**, and particles outside the floor outline weigh zero. This "map matching" is what makes the clinic plan improve accuracy: a person cannot walk through walls.
4. **Room decision.** A fingerprint classifier (k nearest neighbours over RSSI vectors recorded once per room during a short survey walk) is usually more reliable than geometry for "which room". The room comes from the fingerprint when its confidence is ≥ 0.6, otherwise from the room containing the particle-filter estimate. A room change needs 3 s of agreement, so a tablet at a doorway does not flicker. The floor comes from the floor of the strongest anchors, with the same 3 s hysteresis.

A manual room pick or QR scan overrides Bluetooth for 5 minutes: the person knows better.

The particle filter's motion step uses the tablet's PDR displacement when it is reported (a random walk when it is not), which is exactly the virtual-anchor reasoning above, done over time.

**Deferred options, for the record.** Bluetooth direction finding (5.1 AoA/AoD) and Bluetooth Channel Sounding (6.0) give better accuracy, but need specific hardware support, to be checked on the actual devices. UWB gives 10–30 cm but most tablets lack it. The design accepts these later without change: an observation is either `Rssi` or `Range { metres, sigma }`, so a better radio only adds a new observation source.

**Privacy.** Raw scans are processed in memory and dropped. They are never stored, journaled or logged. Outward, the estimate follows Task 11's rules: the exact point only when `uncertainty_m ≤ 3`, otherwise the room's anchor point. This makes staff tracking more precise than a room pick, so it needs the clinic's consent before any real use (see open decisions).

**Files:**
- Create: `crates/locations/src/positioning/{mod.rs, observation.rs, smoothing.rs, path_loss.rs, virtual_anchors.rs, trilateration.rs, particle_filter.rs, fingerprint.rs, room_tracker.rs, positioner.rs, simulate.rs}`, `seed/fixed_devices.json`, `seed/beacons.json` (empty: beacons are optional), `seed/fingerprints.json` (empty until a survey), `docs/positioning.md`, `docs/positioning-proof.md`
- Modify: `src/routes/map.rs` (add `POST /me/scans`), `crates/realtime/src/protocol.rs` (robots report the BLE id they advertise in `hello`)
- Test: `crates/locations/tests/positioning.rs`

**Interfaces:**
- Consumes: `ClinicMap` (walls, floors, places), `LivePositions` (robot fixes as anchors, tablet output).
- Produces:
  - `Anchor { id: AnchorId, kind: AnchorKind { Robot(RobotId), FixedDevice(DeviceId), Beacon, Tablet(DeviceId) }, floor: i32, point: Point2, spread_m: f64 (0 for known positions), tx_power_dbm_1m: f64 }`.
  - `Observation { Rssi { anchor: AnchorId, dbm: i16 }, Range { anchor: AnchorId, metres: f64, sigma_m: f64 } }`.
  - `MotionDelta { steps: u32, heading_rad: f64, heading_sigma_rad: f64, stride_m: f64 }` and `pressure_hpa: Option<f64>`.
  - `ScanReport { device: DeviceId, at: DateTime<Utc>, observations: Vec<Observation>, motion: Option<MotionDelta>, pressure_hpa: Option<f64> }`, validated: RSSI between −110 and 0 dBm, at most 64 observations, `at` no more than 2 s in the future, at most 10 steps per second. `POST /me/scans` takes it at about 1 Hz.
  - `VirtualAnchors::identifiability(&self) -> Identifiability { Unique, Mirror { line }, Underdetermined { have, need: 3 } }`: the test of the reduction above, used to set the estimate's confidence.
  - `PathLossModel { exponent_n: f64 (default 2.7), sigma_db: f64 (default 4.0) }`, `distance_m(&self, dbm, tx_power) -> f64`, `likelihood(&self, dbm, tx_power, distance_m) -> f64`.
  - `Trilaterator::solve(&self, ranges: &[WeightedRange]) -> Result<Estimate { point, residual_m }, PositioningError>`; fewer than 3 anchors gives `TooFewAnchors { have, need: 3 }`.
  - `ParticleFilter::new(floor: &Floor, particles: usize, seed: u64)`, `predict(&mut self, dt: Duration)`, `update(&mut self, observations, anchors, model)`, `estimate(&self) -> Estimate { point, uncertainty_m }` (2σ radius).
  - `FingerprintIndex::from_survey(&[SurveySample]) -> FingerprintIndex`, `classify(&self, observations) -> Option<(PlaceId, f64)>` (k = 5).
  - `Positioner::ingest(&mut self, scan: ScanReport) -> Result<PositionEstimate { floor, place, point, uncertainty_m, method: Method { Fingerprint, ParticleFilter, Trilateration, Manual } }, PositioningError>`, which then calls `LivePositions::set_tablet_estimate`.
  - `SyntheticScanner` in `simulate.rs`: generates RSSI along a true path through the seed map, with log-normal noise (σ = 4 dB) and 5 dB per wall crossed, so everything is testable without hardware.
  - Added by Task A1 (names the skeleton needed): `FilterEstimate { point, uncertainty_m }` for the particle filter (`Estimate { point, residual_m }` stays trilateration's); `ParticleFilter::set_motion`; `PositionerConfig` and `from_seed_dir`; `Positioner::{new, set_manual}`; `ScanReport::validate(now, previous_at)`; `SmootherBank`; `Line2`; DTO `ScanBody` (device from the identity, never the body); `PositioningError::{BadRange, UnknownAnchor, Diverged, Seed, Map}`. The caller (location service) calls `set_tablet_estimate` with the owner label.

- [ ] **Step 1: Write the failing tests.** `trilateration_is_exact_with_noiseless_ranges`, `too_few_anchors_error_gives_both_counts`, `one_moving_robot_localises_a_static_tablet` (noiseless: within 1 cm, so the maths is right), `one_robot_and_pdr_localise_a_walking_tablet_noiseless`, `collinear_virtual_anchors_report_mirror_ambiguity`, `map_wall_resolves_the_mirror_case`, `second_tablet_localised_through_the_first`, `no_known_anchor_in_range_reports_underdetermined`, `uncertainty_grows_while_no_robot_is_in_range`, `synthetic_beaconless_clinic_round_room_accuracy_is_recorded` (4 robots, 3 tablets, σ = 6 dB, PDR drift 3 %; asserts above 70 % and writes the measured figure to `docs/positioning.md`), `no_particle_ever_crosses_a_wall`, `synthetic_walk_finds_the_right_room_at_least_90_percent_of_the_time` (σ = 4 dB), `synthetic_walk_median_error_is_recorded` (asserts below 3 m and writes the measured value to `docs/positioning.md`), `doorway_does_not_flicker_between_rooms`, `floor_change_needs_3s_of_agreement`, `manual_room_overrides_bluetooth_for_5_minutes`, `stale_robot_is_not_used_as_an_anchor`, `rssi_outside_range_is_rejected`, `scan_from_the_future_is_rejected`, `point_hidden_when_uncertainty_above_3m`, `raw_scans_never_reach_logs_or_journal`.
- [ ] **Step 2: Run `cargo test -p locations --test positioning`.** Expected: FAIL.
- [ ] **Step 3: Implement.** Use a seeded random number generator so tests are repeatable.
- [ ] **Step 4: Write the proof** in `docs/positioning-proof.md`: the virtual-anchor reduction, the non-collinearity condition (uniqueness of the intersection of three circles with non-collinear centres), the mirror case, the two-tablet chaining argument, and the Cramér-Rao bound for the expected precision with RSSI noise. The lead reviews it. Then **document calibration** in `docs/positioning.md`: measure `P_1m` per robot and device model, fit `n` from 10 measured distances, record the survey walk (job 4 adds a "survey mode" screen to the app), and the phone platform limits (Android needs location permission to scan; iOS restricts background scanning, so scans happen while the app is open).
- [ ] **Step 5: Run `bash scripts/check.sh`.** Expected: green. **Commit** `feat(locations): beaconless positioning with robots as moving anchors`.

---

### Task 11c: Incidents on the 3D map (M2)

Device problems and alarms are shown **where they happen**: the room turns orange or red on the admin 3D map. This is a display. The emergency alarm itself is carried by the separate emergency service (`implementation/emergency.md`); the main server only mirrors its alarms, read-only, so a patient alarm is still painted red when everything works, and still delivered when the main server is down.

**Files:**
- Create: `src/services/incidents.rs`, `crates/realtime/src/incidents.rs` (wire types), `crates/locations/src/attribution.rs`, `src/emergency_mirror.rs`
- Modify: `src/routes/` (add `incidents.rs`, `devices.rs`), `crates/realtime/src/protocol.rs`
- Test: `tests/incidents.rs`

**Interfaces:**
- Produces:
  - `IncidentCode` (closed catalogue, **no free text from any device**): `RobotFault { fault: RobotFaultCode }`, `RobotOffline`, `RobotEstop`, `TabletOffline`, `TabletBatteryLow`, `TabletAppError { error: AppErrorCode }`, `ZoneNotDelivered`, `JournalDegraded`, `EmergencyAlarm { level: AlarmLevel }` (mirrored), `EmergencyLinkDown`. Each code has a fixed English and French label table for the UI.
  - `Incident { id, code, severity, subject: Option<SubjectRef>, place: Option<PlaceId>, floor: Option<i32>, opened_at, last_seen_at, repeats: u32, acknowledged_by: Option<OwnerLabel>, closed_at }`.
  - `IncidentBoard::raise(&self, code, subject, at) -> IncidentId`: the same open code for the same subject is merged (`repeats += 1`), not duplicated; severity can rise, never silently fall. `ack(&self, id, by)`, `close(&self, id, by)` (admin). Every change is journaled and published as `AppEvent::IncidentUpdated { incident, colour: Red | Orange | Yellow }`.
  - `Attribution::place_of(&self, subject) -> Option<(PlaceId, i32)>` from `LivePositions` (a robot's current place; a tablet's room).
  - Routes: `GET /incidents?open=true`, `POST /incidents/{id}/ack`, `POST /incidents/{id}/close` (admin), `POST /devices/me/events { code }` (tablets report their own errors from the catalogue; an unknown code is 422).
  - `EmergencyMirror`: a read-only client of the emergency service's status stream. Alarms become `EmergencyAlarm` incidents on their room. If the stream is silent for 10 s it raises `EmergencyLinkDown` (the map must never look calm because the link is broken). It **cannot** acknowledge or create alarms; that happens only in the emergency service.
  - Robot faults and offline/estop states from Task 14 and journal degradation from Task 9 call `raise`.
  - Added by Task A1 (names the skeleton needed): `IncidentId(u64)`, `IncidentSeverity`, `Lang`, `IncidentCode::default_severity` (catalogue types live in `domain::incident`, re-exported by `realtime`); `IncidentChange` and journal `RecordBody::IncidentChanged { id, code, change }`; variant lists of `RobotFaultCode`, `AppErrorCode`, `AlarmLevel`; `IncidentBoardDeps`; `IncidentService::{list_incidents, acknowledge, close_incident, report_device_event}`; `EmergencyMirrorConfig`, `MirrorStatus`, `EmergencyMirror::{new, spawn, status, subscribe}` (read-only, ruling R2).

- [ ] **Step 1: Write the failing tests.** `robot_fault_opens_incident_on_the_robots_current_room`, `repeated_fault_merges_and_counts`, `severity_rises_but_never_silently_falls`, `tablet_event_with_unknown_code_is_422`, `tablet_event_body_with_extra_text_field_is_rejected`, `ack_records_owner_label_and_journals`, `nurse_cannot_close_admin_can`, `mirrored_alarm_paints_room_red`, `silent_emergency_stream_raises_link_down_within_10s`, `mirror_has_no_way_to_ack_or_create_alarms` (the client type exposes no such method; asserted by the public API listing in the test), `incident_json_contains_no_personal_fields`.
- [ ] **Step 2: Run `cargo test --test incidents`.** Expected: FAIL.
- [ ] **Step 3: Implement. Step 4: run `bash scripts/check.sh`.** Expected: green. **Commit** `feat: incidents on the map and emergency mirror`.

---

### Task 12: Tasks and inventory, real services

**Files:**
- Create: `crates/storage/src/{tasks.rs, inventory.rs, events.rs}`, `migrations/0003_tasks_inventory.sql`, `src/services/{tasks.rs, inventory.rs}`, `seed/reserve.json`
- Test: `tests/tasks_inventory.rs`

**Interfaces:**
- Consumes: `domain::{Task, TaskState}`, `AuditLog`, `ClinicMap`.
- Produces:
  - `TaskService::create(&self, actor: &ClientIdentity, new: NewTask { kind: TaskKind { Fetch, RestockRound, GoTo }, item: Option<ItemId>, from: Option<PlaceId>, to: PlaceId, deadline: Option<DateTime<Utc>> }) -> Result<Task, ApiError>`; `get`, `list(TaskFilter, Page)`, `cancel` (allowed only while `Requested` or `Assigned`).
  - `TaskService::apply_robot_event(&self, robot: &RobotId, event_id: Uuid, task: &TaskId, state: TaskState, reason: Option<FailureReason>) -> Result<ApplyOutcome { Applied, Duplicate }, ApiError>`: idempotent through a `processed_events(event_id primary key)` table inside the same transaction as the state change, the stock change and the audit insert.
  - `InventoryService::list`, `adjust(actor, item, delta, reason)` (Admin only; refuses results below zero with message "Cannot remove 5 'blanket': only 3 in stock."), and a delivery hook `on_delivered(task)` decrementing stock.
  - Seed: items from `faux_dossier/reserve.yaml` (big cushion, neck cushion, blanket, water bottle, exercise sheet), class keys matching job 1's `classes.yaml` (agree before seeding).
  - Added by Task A1 (names the skeleton needed): `TaskRepository` methods (`insert, update, get, list, apply_robot_event`); `NewTask::into_draft`; `TaskListQuery::into_parts`; `TaskPage`; `TaskDeps`, `RealTaskService`; `RealInventoryService::new(repo, ledger, journal, hub)`; `InventoryService::on_seen`; `events::mark_processed`.

- [ ] **Step 1: Write the failing tests.** `create_fetch_for_unknown_place_returns_422_naming_the_place`, `create_fetch_for_unknown_item_returns_404`, `create_with_zero_stock_returns_409_out_of_stock`, `duplicate_robot_event_is_applied_once` (Review Focus 1: same event id twice, assert one transition, one stock decrement, one audit entry), `delivered_decrements_stock_exactly_once_even_if_event_replayed`, `illegal_transition_from_robot_returns_409_with_both_states_named`, `cancel_after_en_route_is_rejected`, `adjust_below_zero_is_rejected_with_numbers`, `nurse_cannot_adjust_inventory`, `every_state_change_writes_one_audit_entry`.
- [ ] **Step 2: Run `cargo test --test tasks_inventory`.** Expected: FAIL.
- [ ] **Step 3: Implement** with one database transaction per mutation. Stock is checked here against the current count only. Concurrency-safe reservation arrives in Task 15, and this limitation goes in a comment on `create`.
- [ ] **Step 4: Run `bash scripts/check.sh`.** Expected: green. **Commit** `feat: real task and inventory services`.

---

### Task 13: `optimization` crate: routing graph and dispatcher

**Files:**
- Create: `crates/optimization/src/{lib.rs, graph.rs, fleet.rs, dispatcher.rs, error.rs}`, `scripts/gen_dispatch_golden.py`, `crates/optimization/tests/golden/dispatch/*.json`
- Test: `crates/optimization/tests/dispatch_parity.rs`

**Interfaces:**
- Consumes: `locations::ClinicMap`, `domain::{RobotId, PlaceId, RobotStatus}`.
- Produces:
  - `RoutingGraph::from_map(&ClinicMap) -> RoutingGraph`; `shortest_path(&self, from: &PlaceId, to: &PlaceId, permitted: &PlaceMask) -> Option<Path { places: Vec<PlaceId>, metres: f64 }>`. Dijkstra. Floors are connected only through explicit links, so no link means no path (as in the Python world: "robots do not change floors").
  - `RoleCard { name: String, permitted_places: BTreeSet<PlaceId>, max_speed_m_s: f64 }` loaded from `seed/role_cards.json`.
  - `FleetMember { id: RobotId, name: String, status: RobotStatus, at: PlaceId, battery_pct: f64, card: RoleCard, simulated: bool }`.
  - `DispatchPolicy { consumption_pct_per_m: f64 (0.5), battery_threshold_pct: f64 (15.0) }`.
  - `Dispatcher::new(graph: RoutingGraph, policy: DispatchPolicy) -> Dispatcher`, `Dispatcher::choose(&self, request: &DispatchRequest { from: PlaceId, to: PlaceId, real_delivery: bool }, fleet: &[FleetMember]) -> Decision`.
  - `Decision { chosen: Option<RobotId>, considered: Vec<Consideration { robot: RobotId, fits: bool, reject: Option<RejectReason>, metres: Option<f64> }>, relay: Option<Relay { via: PlaceId, first: RobotId, second: RobotId, metres: f64 }>, explanation: String }`.
  - `RejectReason { Simulated, Faulted{detail}, Busy{status}, CardRefusesPlace{place, card}, NoPath, LowBattery{have_pct, need_pct}, CardRefusesPlaceOnRoute{place, card} }`, each with an explicit English `Display`.
  - `trait DispatchOracle: Send + Sync` (used by Task 20) with `NativeOracle` default.
  - Added by Task A1 (names the skeleton needed): `PlaceMask::{all, only, permits}`; `RoutingGraph::contains`; `RoleCard::{load_all, parse_all, mask}`; `DispatchOracle::choose(&self, &DispatchRequest, &[FleetMember]) -> Result<Decision, OptimizationError>` (synchronous); `NativeOracle::new`; `OptimizationError` variants.

- [ ] **Step 1: Write the golden generator.** `gen_dispatch_golden.py` builds N (≥ 40) scenarios from the real Python `MondeDesRobots` and `Repartiteur.choisir`, varying battery (including exactly at the boundary `battery - need == threshold`, where Python uses `<=`), faulted and busy robots, simulated robots with `real_delivery`, cards refusing the start, the end or a place on the route, floor changes, and relay cases. It writes one JSON per scenario with the inputs (fleet, request) and the Python's outcome, classifying the French reason strings by prefix (`en panne`, `occupé`, `pas de chemin`, `pas assez de batterie`, `simulé`, otherwise card refusal).
- [ ] **Step 2: Write the failing tests.** `golden_scenarios_match_python_choice_and_reject_kinds` (loops every file: same `chosen`, same reject kind per robot, same relay point), `nearest_free_robot_wins`, `equal_distance_ties_break_by_robot_id`, `battery_exactly_at_threshold_is_rejected`, `no_link_between_floors_means_no_path`, `card_refusing_a_traversed_place_rejects_the_robot`, `no_robot_fits_returns_none_with_every_reason_listed`, `explanation_names_each_rejected_robot_and_why`, `real_delivery_excludes_simulated`.
- [ ] **Step 3: Run `cargo test -p optimization`.** Expected: FAIL.
- [ ] **Step 4: Implement.** The Python is the reference: when a golden file disagrees with the Rust, fix the Rust unless the Python is plainly wrong, and then write the difference in `docs/task-states.md` under "Intentional differences".
- [ ] **Step 5: Run `bash scripts/check.sh`.** Expected: green. **Commit** `feat(optimization): routing graph and dispatcher with python parity`.

---

### Task 14: Robot sessions, commands, and assignment

**Files:**
- Create: `crates/realtime/src/{robot_session.rs, liveness.rs, dedupe.rs}`, `src/services/robots.rs`, `src/services/assignment.rs`
- Modify: `src/ws/robots.rs` (real auth), `src/ws/apps.rs`
- Test: `tests/robot_sessions.rs`

**Interfaces:**
- Consumes: Tasks 3, 5, 7, 8, 11, 12, 13.
- Produces:
  - `/ws/robot/{id}` requires a robot token (`TokenSubject::Robot`) whose id equals the path id; a mismatch closes with code 4403 and the text "Token belongs to robot X but the connection asks for robot Y." An unknown robot id closes with 4404 naming it.
  - `Liveness::new(timeout: Duration (5 s), clock)`, `touch(robot)`, `expired() -> Vec<RobotId>`. On expiry the status becomes `Offline`, an `Alert { RobotOffline }` is published, and `TaskService::on_robot_lost` returns a task still `Assigned` to `Requested` for reassignment, while an `EnRoute` task is flagged "robot lost, human needed" and not reassigned (the robot may still be carrying the item).
  - `Deduper::new(capacity: usize = 1024)`, `seen(&mut self, id: Uuid) -> bool`.
  - `AssignmentService::assign(&self, task: &Task) -> Result<AssignOutcome { Sent{robot}, HandedToHuman{explanation} }, ApiError>` builds the fleet from live state and role cards, calls `Dispatcher::choose`, sends `TaskAssign`, and moves the task to `Assigned`. No robot fits means the task stays `Requested` with `needs_human = explanation`.
  - `RobotService::command(&self, actor: &ClientIdentity, robot: &RobotId, name: CommandName) -> Result<CommandReceipt { sent_at, delivered: bool }, ApiError>`; `pause`, `resume`, `dock`, `shutdown` require `Permission::RobotControl`. **`estop` takes a separate function `EstopPath::trigger`** that writes straight to the robot's outbound channel with priority before anything else, then appends the audit entry afterwards, and needs `Permission::Estop`. If the robot is offline the response says so explicitly: "Robot X is offline: the stop was not delivered. Use the physical button."
  - Robot `State` messages feed `LivePositions::update_robot` and `inventory.seen` goes to the stock service (Task 15).
  - Application sessions use a bounded outbound queue (256). On overflow the subscriber receives `Resync` and a fresh `Snapshot`, then continues; it is never allowed to block the hub.
  - Added by Task A1 (names the skeleton needed): `Hub::send_priority`; `CloseReason::{not_a_robot, from_realtime, code, text}`, close code 4409 for a second connection; `Liveness::forget`; `RobotService::{estop, check_liveness}`; `RealRobotService::spawn_liveness_watch`; `RobotDeps`, `AssignmentDeps`; `TaskService::on_robot_lost(&RobotId) -> Result<Vec<TaskId>, ApiError>`.

- [ ] **Step 1: Write the failing tests** over in-memory duplex WebSocket pairs: `robot_with_wrong_token_is_closed_with_4403_and_reason`, `unknown_robot_is_closed_with_4404`, `duplicate_event_id_after_reconnect_changes_nothing`, `robot_silent_for_5s_goes_offline_and_alert_is_published`, `assigned_task_returns_to_requested_when_robot_is_lost`, `en_route_task_is_flagged_for_a_human_not_reassigned`, `no_fitting_robot_leaves_task_requested_with_explanation`, `estop_reaches_robot_even_when_dispatcher_lock_is_held` (hold the assignment mutex in the test), `estop_to_offline_robot_says_use_the_physical_button`, `nurse_cannot_send_estop`, `slow_app_subscriber_gets_resync_and_does_not_block_others`, `reconnecting_robot_with_running_task_in_hello_is_reconciled`.
- [ ] **Step 2: Run `cargo test --test robot_sessions`.** Expected: FAIL.
- [ ] **Step 3: Implement.** Replace the mock WS handlers. Swap `MockServices` out for the real services in `main.rs` unless `--mock`.
- [ ] **Step 4: Run `bash scripts/check.sh`.** Then run the M0 end-to-end test again with real services: `cargo test --test m0_fake_robot`. Expected: green.
- [ ] **Step 5: M1 gate.** Job 2's mock link connects to this server, job 4 creates a task from the app, job 5 sees the robot move. Commit `feat: robot sessions, assignment, commands (M1)`.

---

### Task 15: Stock ledger and reconciliation

**Files:**
- Create: `crates/optimization/src/stock.rs`, `crates/storage/src/ledger.rs`, `migrations/0004_reservations.sql`
- Modify: `src/services/tasks.rs`, `src/services/robots.rs`
- Test: `crates/optimization/tests/stock.rs`, `tests/stock_concurrency.rs`

**Interfaces:**
- Produces:
  - `trait StockLedger: Send + Sync` with `reserve(&self, task: &TaskId, item: &ItemId, qty: u32) -> Result<Reservation, StockError>`, `commit(&self, &Reservation)`, `release(&self, &Reservation)`, `expire_older_than(&self, Duration) -> Result<u32, StockError>` (default reservation lifetime 30 min), `reconcile(&self, place: &PlaceId, seen: &[SeenItem]) -> Result<Vec<ReconcileOutcome>, StockError>`.
  - `StockError::OutOfStock { item, requested, available }` with message "Cannot reserve 1 'blanket': 0 available (2 more are reserved by other tasks)."
  - `ReconcileOutcome { Matched, Mismatch { item, expected, seen }, Uncertain { item } }`. A `SeenItem` with `uncertain: true` or `count: None` never overwrites stock and never reads as zero.
  - `InMemoryLedger` (for fast tests) and `SqliteLedger` (one `BEGIN IMMEDIATE` transaction per reservation, so SQLite serialises competing writers).
  - Added by Task A1 (names the skeleton needed): `StockLedger`, `Reservation`, `ReconcileOutcome`, `StockError` are defined in `domain` (so `storage` need not depend on `optimization`) and re-exported by `optimization::stock`; `InMemoryLedger::new(clock, stock)`; `InventoryRepository::set_count`.

- [ ] **Step 1: Write the failing tests.** `two_tasks_one_unit_exactly_one_wins` (50 repetitions with `tokio::join!`; Review Focus 2), `stock_never_negative_under_random_sequences` (proptest over reserve/commit/release), `release_makes_unit_available_again`, `expired_reservation_is_released`, `uncertain_count_never_overwrites_stock`, `mismatch_is_flagged_and_stock_unchanged_until_admin_confirms`, `delivered_task_commits_reservation`, `cancelled_task_releases_reservation`.
- [ ] **Step 2: Run `cargo test -p optimization --test stock` and `cargo test --test stock_concurrency`.** Expected: FAIL.
- [ ] **Step 3: Implement.** `TaskService::create` now reserves before inserting the task, in one transaction. Remove the limitation comment from Task 12.
- [ ] **Step 4: Run `bash scripts/check.sh`.** Expected: green. **Commit** `feat(optimization): stock ledger with reservations`.

---

### Task 16: Zones: edit, deliver, acknowledge

**Files:**
- Create: `crates/storage/src/zones.rs`, `migrations/0005_zones.sql`, `crates/realtime/src/zone_delivery.rs`, `src/services/zones.rs`
- Modify: `src/routes/zones.rs`
- Test: `tests/zones.rs`

**Interfaces:**
- Consumes: `locations::Zone`, `Hub`, robot sessions.
- Produces:
  - `ZoneService::upsert(&self, actor, id: ZoneId, input: ZoneInput { kind, floor, polygon: Vec<[f64; 2]> }) -> Result<ZoneView, ApiError>`: validates through `locations::Polygon`, bumps `version`, saves, appends audit, publishes `ZoneUpdated`, and sends `ZonesUpdate` (the full list and a global version) to every connected robot.
  - `ZoneDelivery`: records the acknowledged version per robot from `ZoneAck`. `GET /zones` returns each zone plus `delivery: [{ robot, acked_version, state: Delivered | Pending | RobotOffline }]`. A robot that reconnects is sent the current list immediately.
  - `ZoneView.enforced_by_gardien: bool` is `false` for `Restricted` zones for now (architecture.md open question 5).
  - Delete (`DELETE /zones/{id}`) propagates the empty set.
  - Added by Task A1 (names the skeleton needed): `ZoneService::{zones_update, record_ack}`; `ZoneDelivery::{record_ack, entries_for}`; `ZoneDeliveryEntry`, `DeliveryState`; `Hub::broadcast_to_robots`; `ZoneDeps`, `RealZoneService`.

- [ ] **Step 1: Write the failing tests.** `self_intersecting_polygon_returns_422_naming_the_edges` (Review Focus 4), `polygon_outside_floor_returns_422`, `nurse_cannot_edit_zones`, `edit_sends_zones_update_to_all_connected_robots`, `robot_ack_marks_delivered_and_offline_robot_shows_pending`, `reconnecting_robot_receives_current_zones`, `delete_zone_sends_updated_list_without_it`, `restricted_zone_is_labelled_not_enforced`.
- [ ] **Step 2: Run `cargo test --test zones`.** Expected: FAIL.
- [ ] **Step 3: Implement. Step 4: run `bash scripts/check.sh`.** Expected: green. **Commit** `feat: zone editing with delivery tracking`.

---

### Task 17: `scheduler` crate and the night restock round

**Files:**
- Create: `crates/scheduler/src/{lib.rs, cron.rs, schedule.rs, service.rs, error.rs}`, `crates/storage/src/schedules.rs`, `migrations/0006_schedules.sql`, `src/services/schedules.rs`
- Test: `crates/scheduler/tests/scheduler.rs`

**Interfaces:**
- Consumes: `domain::{Clock, PlaceId}`, `trait TaskCreator { async fn create_restock_round(&self, places: &[PlaceId]) -> Result<TaskId, SchedulerError>; }` (implemented by `TaskService`).
- Produces:
  - `CronExpr::parse(&str) -> Result<CronExpr, SchedulerError>` for five-field cron; the error names the failing field ("Field 'hour' has value 25; hours go from 0 to 23.").
  - `Schedule { id, name, cron: CronExpr, timezone: chrono_tz::Tz (default Europe/Zurich), job: ScheduledJob::RestockRound { places: Vec<PlaceId> }, enabled: bool, last_run: Option<DateTime<Utc>>, grace: Duration (default 30 min) }`.
  - `SchedulerService::new(repo: Arc<dyn ScheduleRepository>, clock: Arc<dyn Clock>, creator: Arc<dyn TaskCreator>)`, `run_once(&self) -> Result<Vec<FiredJob>, SchedulerError>`, `spawn(self: Arc<Self>) -> JoinHandle<()>` ticking every second.
  - Claiming a run is one SQL statement (`UPDATE … WHERE last_run < $scheduled RETURNING`), so two ticks or two server instances cannot both fire.
  - Missed runs: on startup, a run missed within `grace` fires once; an older one is skipped and written to the audit log as `ScheduleMissed`.
  - `PUT /schedules/{id}` (Admin) validates and saves; `GET /schedules` lists with `next_run`.
- Pick the cron crate by reading its docs for time-zone and DST handling, and `cargo deny` approval. State the choice in the commit message.
  - Added by Task A1 (names the skeleton needed): `TaskCreator::report_missed(&ScheduleId, DateTime<Utc>)` (the scheduler cannot depend on `audit`); `FiredJob { schedule, scheduled_for, outcome: RunOutcome { Created(TaskId), Missed } }`; `Schedule::{from_record, to_record, next_run}`; `CronExpr::{next_after, as_str}` with private field sets; `ScheduleRepository::claim_run`; `RealScheduleService`.

- [ ] **Step 1: Write the failing tests** with `FakeClock`: `fires_at_0200_zurich_time`, `does_not_fire_twice_on_two_ticks_in_the_same_minute`, `disabled_schedule_never_fires`, `spring_forward_nonexistent_0230_fires_at_next_valid_minute_once`, `fall_back_repeated_0230_fires_once`, `missed_run_within_grace_fires_once_on_startup`, `missed_run_beyond_grace_is_skipped_and_audited`, `invalid_cron_hour_error_names_the_field`, `two_services_sharing_a_database_fire_once`.
- [ ] **Step 2: Run `cargo test -p scheduler`.** Expected: FAIL.
- [ ] **Step 3: Implement. Step 4: run `bash scripts/check.sh`.** Expected: green. **Commit** `feat(scheduler): cron schedules and night restock round`.

---

### Task 18: Tour planner and shelf leases

**Files:**
- Create: `crates/optimization/src/{tour.rs, lease.rs}`
- Modify: `src/services/assignment.rs` (restock rounds use the planner)
- Test: `crates/optimization/tests/tour.rs`, `crates/optimization/tests/lease.rs`

**Interfaces:**
- Produces:
  - `TourPlanner::new(graph: RoutingGraph, policy: DispatchPolicy, dock: PlaceId)`, `plan(&self, robot: &FleetMember, stops: &[PlaceId]) -> Result<Tour { order: Vec<PlaceId>, metres: f64, dock_visits: Vec<usize>, skipped: Vec<SkippedStop { place, reason: RejectReason }> }, OptimizationError>`: nearest neighbour followed by 2-opt. More than 25 stops returns `OptimizationError::TooManyStops { given, max }`. A dock visit is inserted whenever the next leg would take the battery under the threshold. A stop with no path or refused by the role card goes into `skipped`, never silently dropped.
  - `assign_stops(&self, fleet: &[FleetMember], stops: &[PlaceId]) -> Result<Vec<(RobotId, Vec<PlaceId>)>, OptimizationError>`: greedy split by path length so two robots do not cover the same shelf.
  - `ShelfLeases::new(clock: Arc<dyn Clock>)`, `acquire(&self, place: &PlaceId, robot: &RobotId, ttl: Duration) -> Result<Lease, LeaseError::HeldBy { robot, until }>`, `release`, expiry by the clock.
  - Added by Task A1 (names the skeleton needed): `OptimizationError::EmptyFleet` from `assign_stops`.

- [ ] **Step 1: Write the failing tests.** `five_stops_match_brute_force_optimum`, `ten_stops_not_worse_than_nearest_neighbour`, `low_battery_inserts_dock_visit_before_the_unreachable_leg`, `unreachable_stop_is_reported_in_skipped_with_reason`, `thirty_stops_returns_too_many_stops_with_both_numbers`, `two_robots_get_disjoint_stop_sets_covering_all_reachable_stops`, `second_robot_cannot_lease_a_held_shelf_message_names_holder_and_time`, `lease_expires_after_ttl`, `release_by_non_holder_is_rejected`.
- [ ] **Step 2: Run `cargo test -p optimization`.** Expected: FAIL.
- [ ] **Step 3: Implement. Step 4: run `bash scripts/check.sh`.** Expected: green. **Commit** `feat(optimization): restock tour planner and shelf leases`.

---

### Task 19: Space-time reservations (P2)

**Files:**
- Create: `crates/optimization/src/reservation.rs`
- Test: `crates/optimization/tests/reservation.rs`

**Interfaces:**
- Produces: `ReservationTable::new(clock)`, `try_reserve(&self, robot: &RobotId, path: &Path, start: DateTime<Utc>, speed_m_s: f64) -> Result<(), Conflict { with: RobotId, at: PlaceOrEdge, window: (DateTime<Utc>, DateTime<Utc>) }>`, `earliest_start(&self, robot, path, not_before, speed) -> DateTime<Utc>`, `release(&self, &RobotId)`.
- Scope note in the file header: this plans around other robots on the server side. It does **not** replace each robot's own obstacle avoidance or the gardien. Physical safety stays on the robot.
  - Added by Task A1 (names the skeleton needed): `Conflict` is a `thiserror` struct; `PlaceOrEdge::{Place, Edge}`.

- [ ] **Step 1: Write the failing tests.** `same_corridor_overlapping_windows_conflict`, `head_on_swap_through_one_corridor_is_a_conflict`, `adjacent_non_overlapping_windows_are_fine`, `earliest_start_waits_until_corridor_is_free`, `release_frees_all_windows_of_that_robot`.
- [ ] **Step 2: Run `cargo test -p optimization --test reservation`.** Expected: FAIL.
- [ ] **Step 3: Implement. Step 4: run `bash scripts/check.sh`.** Expected: green. **Commit** `feat(optimization): space-time reservations`.

---

### Task 20: `python-bindings` crate (pyo3, feature-gated)

**Files:**
- Create: `crates/python-bindings/src/{lib.rs, bridge.rs, error.rs}`, `crates/optimization/benches/dispatch.rs`, `docs/pyo3-decision.md`
- Test: `crates/python-bindings/tests/oracle.rs` (runs only with `--features python`)

**Interfaces:**
- Consumes: `optimization::{DispatchOracle, DispatchRequest, FleetMember, Decision}`.
- Produces:
  - `PythonBridge::start(config: PythonConfig { repo_root: PathBuf, venv: Option<PathBuf>, call_timeout: Duration }) -> Result<PythonBridge, BridgeError>`: one dedicated OS thread owns the interpreter (so the GIL never blocks the async runtime), requests arrive over a channel.
  - `impl DispatchOracle for PythonBridge`: builds a `MondeDesRobots` from the fleet, calls `briques.clinique.repartiteur.Repartiteur.choisir`, converts the result to `Decision`.
  - `BridgeError { InterpreterUnavailable{detail}, ImportFailed{module, detail}, PythonRaised{exception_type, message}, Timeout{after}, Conversion{field} }`; Python exception text is truncated and contains no file system paths.
  - The workspace builds and tests with **no** Python present: the dependency on pyo3 is optional behind feature `python`, default off.
- **Lint exception:** pyo3's macros expand to `unsafe`. This crate sets `unsafe_code = "deny"` (not `forbid`) and `deny.toml`/`docs/pyo3-decision.md` record why. Our own code in the crate contains no `unsafe`, and a test greps the crate's `src/` for the keyword.
- **Decision to confirm with the lead before starting this task:** which Python code is worth keeping in Python. The dispatcher is already ported, so the bridge's justified uses are the parity oracle and any Python-only logic the lead names (for example localised phrase tables in `commun/phrases.py`). Do not build a bridge for code that is being reimplemented.
  - Added by Task A1 (names the skeleton needed): `PythonBridge` implements the synchronous `DispatchOracle`; `BridgeRequest` is private.

- [ ] **Step 1: Write the failing tests** (feature `python`): `bridge_decision_equals_native_for_every_golden_scenario`, `missing_venv_returns_interpreter_unavailable_naming_the_path_setting`, `python_exception_becomes_python_raised_without_traceback_paths`, `call_exceeding_timeout_returns_timeout`, `bridge_works_from_many_tasks_concurrently`. Plus, without the feature: `workspace_tests_pass_without_python` (the CI script runs the suite on a PATH with no Python).
- [ ] **Step 2: Run `cargo test -p python-bindings --features python`.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Benchmark and write down the numbers.** `cargo bench -p optimization`: native `Dispatcher::choose` vs the pyo3 oracle vs a localhost HTTP call to a stub. Record measured p50 and p99 in `docs/pyo3-decision.md` with the machine used. State plainly whether the bridge is on the request path (expected: no, native is faster) or only a parity and tooling aid.
- [ ] **Step 5: Run `bash scripts/check.sh` with and without `--features python`.** Expected: green. **Commit** `feat(python-bindings): feature-gated pyo3 bridge and measurements`.

---

### Task 21: End-to-end and hardening gate

**Files:**
- Create: `tests/e2e_{task_flow,robot_loss,roles,zones,network,privacy}.rs`, `docs/runbook.md`, `README.md` (all under `implementation/server/`)
- Modify: `implementation/architecture.md` (record anything the implementation changed in C2 or C3)

**Interfaces:** consumes everything.

- [ ] **Step 1: Write the end-to-end tests** (real server on port 0, real database, fake robot binary or in-process):
  - `task_flow`: REST `POST /tasks` → assigned → en_route → delivered; the app WebSocket receives every `TaskUpdated`; stock decreased once; audit chain verifies.
  - `robot_loss`: kill the fake robot; `Alert RobotOffline` within 5.5 s; the task is reassigned or flagged per Task 14.
  - `roles`: a nurse gets 403 on zones, estop, schedules, audit, inventory adjust.
  - `zones`: admin draws a deaf zone; two connected fake robots receive it and ack; `GET /zones` shows delivered for both.
  - `network`: a request from an unknown IP is rejected before any token check; a flood from one IP is throttled while another IP is unaffected.
  - `privacy`: after moving a tablet through three rooms, dump every database table and the captured log output; assert no tablet position, room name or device id appears linked to a coordinate; assert the live snapshot contains only the six allowed tablet keys; assert no raw Bluetooth scan was stored or logged.
- [ ] **Step 2: Run them.** Fix failures in the owning crate, not in the test.
- [ ] **Step 3: Full gate.** First set `clippy::todo` and `missing_docs` to `deny` and remove `-A clippy::todo` from `check.sh`; `bash scripts/todo_report.sh` must print zero stubs and zero ignored tests (anything deliberately cut is deleted, not left as a stub). Then `bash scripts/check.sh`, `clinic-server journal verify` on the test run's journal, `bash scripts/lint_canary.sh`, `cargo deny check`, `cargo audit`, `cargo test --features python` if the venv exists. Expected: all green, canary still fails as designed.
- [ ] **Step 4: Measure, do not guess.** Run a 10 s load of 200 requests/s against `/tasks` on the dev machine and record p50, p99 and memory in `docs/runbook.md`. Note which numbers came from which machine.
- [ ] **Step 5: Write `docs/runbook.md` and `README.md`.** Start order, environment variables, how to seed, how to rotate a robot key, the TLS upgrade path, and a list of everything **not tested** (no real robot, no real Wi-Fi, no real clinic network, plain HTTP).
- [ ] **Step 6: Commit** `test: end-to-end gate and runbook`.

---

## Open decisions for the lead

1. **Tablet owner label.** Plan assumes the owner is the logged-in staff user's pseudonymous `display_label` (set by an admin, for example "Nurse K., floor 2"). The alternative is a label fixed per physical tablet. Say which.
2. **What Python stays in Python** for the pyo3 crate (Task 20 start). Without an answer the crate is built as a parity oracle only.
3. **TLS on the clinic Wi-Fi.** Plain HTTP for the hackathon, or rustls with a local certificate authority from the start (tablets must trust it).
4. ~~PostgreSQL or SQLite~~ **Decided: SQLite** (lead, Nov 14).
5. **Who holds the journal signing key** and where the anchor copy lives (a USB stick, a second laptop). Whoever holds the key can write valid seals.
6. **Bluetooth positioning in a real clinic** tracks staff more precisely than a room pick. It needs the clinic's and the staff's agreement (Task 11b). Beacons are optional.
