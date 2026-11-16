# Server development setup

The server is a Rust Cargo workspace in `implementation/server/`. The database is SQLite (nothing to install). Tests use in-memory SQLite through `#[sqlx::test]`.

## Tested on Windows 11 (stable-x86_64-pc-windows-msvc)

Prerequisites: Rust via rustup, Python 3.13 (`py` launcher), a C compiler (MSVC Build Tools). `cl.exe` does not need to be on PATH: the `cc` crate finds MSVC through the registry. Proof it works: installing `sqlx-cli` below compiles the bundled SQLite C code (`libsqlite3-sys`) without error.

Run from the repo root (Git Bash shown; PowerShell equivalents are the same except the venv path uses backslashes):

```
cargo install sqlx-cli --no-default-features --features rustls,sqlite
cargo install cargo-deny cargo-audit --locked
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
```

Do not use Python 3.14 for the venv; `requirements.txt` was tested on 3.13.

Versions installed and verified:

```
$ sqlx --version
sqlx-cli 0.9.0
$ cargo deny --version
cargo-deny 0.20.2
$ cargo audit --version
cargo-audit-audit 0.23.0
$ .venv/Scripts/python --version
Python 3.13.14
$ .venv/Scripts/python -c "import yaml, pydantic"     # no error; PyYAML 6.0.3, pydantic 2.14.3
$ cargo --version
cargo 1.97.1 (c980f4866 2026-06-30)
```

Install times: sqlx-cli about 1.5 min, cargo-deny + cargo-audit about 5.5 min.

## macOS (not tested here)

```
xcode-select --install                     # provides cc
cargo install sqlx-cli --no-default-features --features rustls,sqlite
cargo install cargo-deny cargo-audit --locked
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt    # or requirements-mac.txt if the repo says so
```

The venv Python is `.venv/bin/python` instead of `.venv/Scripts/python`.

## Environment

Run these from `implementation/server/`. SQLite's `mode=rwc` creates the database file but not a missing directory, so create `data/` first or the first run fails with "unable to open database".

```
cd implementation/server
mkdir data
cp .env.example .env
```

`.env` lives at `implementation/server/.env`. Never commit it (the root `.gitignore` already ignores it; check with `git check-ignore -v implementation/server/.env`).

- `DATABASE_URL=sqlite://data/clinic.db?mode=rwc` (used by the server and by `cargo sqlx prepare`)
- `JOURNAL_DIR=journal`

`data/` and `journal/` are git-ignored by `implementation/server/.gitignore` and must not be committed. The authoritative audit trail is the sealed journal (Task 9), not the database.

## Run the real server (step R1)

`cargo run` without `--mock` starts the live server: SQLite database, sealed journal, the full security stack, real login and accounts. Run it from `implementation/server/` (the seed files are read relative to it):

```
cd implementation/server
cargo run
```

Defaults (each can be set in `.env` or the environment, see `.env.example`): `CLINIC_BIND=127.0.0.1:8080`, `DATABASE_URL=sqlite://data/clinic.db?mode=rwc` (the `data/` directory is created if missing), `JOURNAL_DIR=journal`, `JOURNAL_KEY=keys/journal.key` (created on first start, with `keys/journal.key.pub` next to it), `ACCOUNT_PEPPER=keys/account.pepper` (created on first start), `JOURNAL_ANCHORS=anchor/anchor.log`, `LOG_DIR=logs`. **Back up `keys/`**: without the pepper nobody can log in, without the journal key no new seal can be checked against the old ones. `data/`, `journal/`, `keys/`, `anchor/` and `logs/` are local state; never commit them.

Known networks: without `seed/known_networks.json` (and no `KNOWN_NETWORKS_FILE`), the server accepts this computer (127.0.0.0/8, ::1) and the private LAN ranges (10/8, 172.16/12, 192.168/16, fc00::/7, fe80::/10); the startup log says so. Any other address gets 403 `network_not_allowed`.

**First start.** With no account in the database the server issues a one-time **admin enrolment code** and prints it on the terminal (stderr only: never in the log file or the journal), for example:

```
FIRST START: no account exists. One-time ADMIN enrolment code: 18FQ-JYQZ-32RC
  valid until 2026-11-16T18:20:30+00:00, single use. ...
```

It is valid 24 hours and single use. Later starts print nothing once an account exists. A restart before anyone enrolled retires the earlier code and prints a new one.

**Back up `keys/account.pepper` and `keys/journal.key` (with `.pub`).** Losing them is unrecoverable: without the pepper no account can log in, without the journal key the existing seals cannot be continued. The server never silently replaces them: it creates the pepper only on a fresh installation (no account, no enrolment code) and the journal key only for an empty journal; otherwise a missing or replaced key file stops the start with "restore it from the backup".

**Console login.** Start the console against the server (`VITE_USE_MOCK=false pnpm dev`, see below), click **"I have an enrolment code"**, type the code, choose a user name, a password and a pseudonym (shown to others as `"<pseudonym> #<tag>"`, never your real name). The console derives the account key in the browser (WebCrypto, `docs/accounts.md`) and sends only the key: the server never sees the name or the password, and cannot recover them. The console then signs in; next time, sign in with the same user name and password. More accounts: `POST /admin/enrolment-codes {"role": "nurse", "label": "Nurse 7"}` as an admin, then the same enrolment screen (the console accepts the admin role only; other roles use the staff app). WebCrypto needs a secure context: open the console at `http://localhost:5173` (or over https), not at a LAN address over plain http.

What works on the live server today: `/health`, `/auth/*`, `/admin/enrolment-codes`, `/admin/accounts`, `/me`, `/map`, `/live` (empty), `/clinics` (list, read, create, edit; activating another plan is 501 until the task store exists), `/system/mode` (read: `normal`), `/docs`, `/ws` (snapshot with no task and no position). Everything else answers **501 `not_implemented_yet`** with the build-out task in the message (robots, tasks, inventory, zones, schedules, audit view, incidents, tablets, monitoring, statistics, brain); the console shows those panels as not available. No robot can connect yet (Task 14).

Stop with Ctrl+C (Ctrl+Break on Windows also works): the server seals the journal before it exits. Check the journal any time:

```
cargo run -- journal verify --dir journal --public-key keys/journal.key.pub --anchor anchor/anchor.log
```

It prints a JSON report and exits 0 when the chain, the seals and the anchors are intact (a half-written last line after a crash is reported as `torn_tail`, not as tampering).

## Run with the admin console (`--mock`)

The mock server answers every route of the contract with invented data: the admin console's own demo clinic (`seed/clinic_map.json`, the four robots, stock, zones and schedule of `seed/demo_fleet.json`), plus a few invented tasks, audit rows and one incident. It needs no `.env`, no database, no journal, and writes nothing to disk.

```
cd implementation/server
cargo run -- --mock
```

It listens on `127.0.0.1:8080`, this computer only (ruling R20). To reach it from another computer, set `CLINIC_BIND=0.0.0.0:8080` explicitly; the startup log then warns that mock mode has no network check (since Task A8 it does rate-limit and block other addresses, as the live server will; loopback is never limited). CORS allows the console's `http://localhost:5173`, `http://127.0.0.1:5173` and `http://localhost:4173` (change with `CORS_ORIGINS`, a comma-separated list; `*` is refused). The startup log says what mock mode leaves out.

Then, in another terminal, start the console against it:

```
cd implementation/admin
pnpm install                                    # first time only
VITE_USE_MOCK=false pnpm dev                    # Git Bash, macOS, Linux
$env:VITE_USE_MOCK="false"; pnpm dev            # Windows PowerShell
```

Demo credentials (all invented, password `mock`):

| User | Role | Use |
|---|---|---|
| `admin` | admin | the console (it accepts the admin role only) |
| `nurse` | nurse | to see role refusals with curl (for example an emergency stop is 403) |
| `doctor`, `therapist`, `reception` | their role | same |

Login (Task A7, `docs/accounts.md`): a client sends `{"account_key": "<64 hex>"}`, the key it derives from the user name, the password and the account clinic id `demo-clinic` (`GET /auth/derivation`); the server never receives the name or the password. Since step R1 (frontend F9) the console derives the key itself (WebCrypto) and sends `{account_key}` to both servers; `--mock` still also accepts a `{username, password}` body (it derives the key itself); the live server answers that body with 422 `key_derivation_required`. `POST /admin/enrolment-codes`, `POST /auth/enrol`, `GET /admin/accounts` and `DELETE /admin/accounts/{tag}` work in memory. A nurse's `pause`/`resume`/`dock` raises a `staff_command` alert for the admin, who can revert it with `POST /robots/{id}/commands/{command_id}/revert`.

The token returned is `mock-<role>` (`mock-account-<id>` for an account enrolled in the mock). Robot tokens (mock verifier only, the live server never accepts them): `mock-robot` (robot `robot-r2`) and `mock-robot-<id>` (any robot id).

What works:

- login, `GET /map`, `/robots`, `/tasks`, `/inventory`, `/zones`, `/schedules`, `/audit`, `/clinics`, `/health` (`mode: "mock"`), `/docs` (Scalar, served from this server, works offline);
- **robots move**: `r1`..`r4` are simulated in-process by the same driver as the `fake_robot` binary (`src/sim/`), each as a real hub session handled like a WebSocket robot. They loop between the places of their floor (docks left out), going through doors and along corridors, and send `robot.state` every 200 ms, so the console's 3D map shows them moving;
- `WS /ws` with the first-message authentication, a `snapshot`, then `robot.updated` at least once per second for every connected robot (about 5 per second for the moving ones);
- `POST /tasks` sends the task to a free connected robot (`fake_robot` first, then a demo robot **of the destination's floor**: ruling R21, a demo robot never gets a task whose destination is on another floor or not on the plan): `assigned`, then `en_route` 2 s later, then `delivered` 2 s after that (or when it reached the destination); a delivery takes one item out of the reserve. While no robot fits the task waits in `requested` (a `task_needs_human` alert says so) and goes out when one frees up. A demo robot that still cannot reach a place on its floor answers `failed` (`path_blocked`) without ever showing `holding`. The seed's four invented tasks are never sent to a robot;
- robot commands reach the robot: `pause` stops it (`paused`), `estop` stops it (`estop`), `resume` moves it again, `dock` sends it to its dock, `shutdown` disconnects it (`robot_offline` alert; an in-process robot comes back 10 s later at its dock). A command, including the emergency stop, to a robot with no live session is 409 `robot_offline` (the stop: "Robot X is offline: the stop was not delivered. Use the physical button."), never accepted; the robot's state on the map changes only once the command was queued to it;
- a robot that goes away with a task (shutdown, closed socket, or a reconnect whose `hello` has no running task) does not leave it hanging: a started task (`assigned`, `en_route`) becomes `failed` (`robot_lost`), a task only sent to it goes back to the queue;
- task create and cancel, stock adjust, zone put and delete, schedule put and robot commands publish their events (`task.updated`, `inventory.updated`, `zone.updated`/`zone.deleted`, `schedule.updated`, `robot.updated`, `alert`): a second console sees them live. Everything changes the server's memory only; a restart starts again from the seed;
- refusals as on the real server: unknown ids are 404, a cancelled or en-route task cannot be cancelled (409), an emergency stop needs the admin role (403), and a command to `robot-r2` while no `fake_robot` is connected is 409 `robot_offline` (the emergency stop with the "Use the physical button" message). `robot-r2` is listed with `connected: false` and `last_seen` = the time the mock started.

### `fake_robot` against the mock

With `cargo run -- --mock` running, in another terminal:

```
cd implementation/server
cargo run --bin fake_robot -- --server ws://127.0.0.1:8080 --id robot-r2 --simulated
```

It connects to `/ws/robot/robot-r2` with the token `mock-robot-robot-r2` (default; `--token` or `ROBOT_TOKEN` to change it), says `hello`, then sends `robot.state` every second (`--state-interval-ms`) while looping along `--round` (default `dock-a,reception,therapy-1`, ground floor of the seed plan; `--plan` for another plan file). `robot-r2` turns connected in the console and new tasks go to it first. Ctrl+C stops it; the console then shows it offline with an alert. Any other `--id` also works (the mock adds it to the robot list).

What does not work yet:

- motion is simplistic: straight lines between points of a visibility graph over the walls (doors, corridors); it ignores furniture, zones, other robots and lifts, and robots never change floor. `fake_robot` given a task whose places are on another floor or not on the plan still "delivers" it on the 2 s timeline without moving (gate M0) and prints a warning on stderr. Real routing is Task 13b, the demo's motion Task 5b;
- the in-process robots keep the plan that was active at start (a newly activated clinic plan is not followed), and clinic plan changes publish no `map.updated` in mock mode;
- no journal, database or real bootstrap (ruling R18); the real server's robot sessions (real robot tokens, liveness, de-duplication across reconnects) are Task 14;
- plans, places and items are checked lightly (the full plan validation comes with Task 10b), and the route preview and heat map are canned;
- mock mode has no known-network check (it rate-limits and blocks other addresses since Task A8; loopback, connected robots and an admin's robot commands are never refused): if you set `CLINIC_BIND` beyond localhost, do so on a trusted network only. Mock tablet sessions use the token `mock-tablet-<device id>` while the tablet is assigned (`GET /devices`); freeing the tablet revokes it. The live server keeps the full security stack (its default bind is also `127.0.0.1:8080`; a deployment sets `CLINIC_BIND`).

Checked by `tests/api_shell.rs`, `tests/console_contract.rs` and `tests/m0_fake_robot.rs` (the same wiring and transport as `cargo run -- --mock`; the last one runs the `fake_robot` binary and checks moving robots, pause/resume/estop and live mutation events). Task 5 also ran `cargo run -- --mock` by hand with a WebSocket client and the `fake_robot` binary. Not tested against the running console in a browser, and not against a real robot.

## Hackathon open mode

For the pitch the server accepts devices on any network and any origin. Every relaxed
check is marked `HACKATHON:` in the code: the restrictive line is commented out, not
deleted, and the open replacement sits right below it. Restore them after the pitch
(`grep -rn HACKATHON src crates ../admin/src`).

| Where | What is disabled |
|---|---|
| `crates/security/src/cors.rs` `CorsPolicy::layer` / `open_layer` | CORS origin list: any origin is mirrored, credentials allowed; methods GET POST PUT PATCH DELETE OPTIONS; headers `Authorization`, `Content-Type`, `X-Client-Id`, `If-Match`; `ETag`, `Retry-After`, `Content-Disposition` exposed |
| `crates/security/src/stack.rs` `known_network` | known-network (IP allow-list) refusal: an unknown address is served with the label `any network (hackathon open mode)` |
| `crates/security/src/origin.rs` `HACKATHON_OPEN` | WebSocket `Origin` check: every origin (or none) passes |
| `src/patient/mod.rs` `check_origin` | same-origin refusal on mutating `/api/*` patient routes |
| `src/lib.rs` `patient_routes` | the patient routes get the open CORS layer too |
| `src/config.rs` `CLINIC_BIND` | default bind `0.0.0.0:8080` (every interface) instead of `127.0.0.1:8080` |
| `src/config.rs` `RATE_PER_SECOND` / `RATE_BURST` | per-address rate raised from 20/s burst 40 to 100/s burst 400 (the traffic monitor stays on) |
| `crates/security/tests/stack.rs`, `origin.rs` tests | refusal tests `#[ignore = "HACKATHON: open network"]` |
| `../admin/src/lib/config.ts` | a console served by the server talks to its own origin |
| `src/tls.rs`, `src/main.rs` `start_https` | HTTPS listener with a self-signed certificate (phones show a warning once) |

Reach the server from a phone or a laptop:

1. Same Wi-Fi as the server computer. Find its LAN address: `ipconfig` (Windows,
   "IPv4 Address") or `ip addr` / `ifconfig`, for example `192.168.1.20`.
2. Start the live server: `cargo run` (or `cargo run -- --mock`). It listens on
   `0.0.0.0:8080`; set `CLINIC_BIND=127.0.0.1:8080` to keep it on this computer only.
   Allow the program through the Windows firewall (private networks) when asked.
3. Patient app: `http://192.168.1.20:8080/patient/` (folder `PATIENT_WEB_DIR`,
   default `../patient-web`). Phones only give the microphone ("Listen & translate") to
   https pages: use `https://192.168.1.20:8443/patient/` and accept the certificate warning
   once (see "HTTPS listener" below).
4. Admin console: `http://192.168.1.20:8080/admin/` (folder `ADMIN_WEB_DIR`, default
   `../admin/dist`). Build it first in `implementation/admin`: `npx pnpm build`
   (`VITE_USE_MOCK=false`). Served from the server, the console uses the page's own origin for
   the API and `ws://<same host>/ws`, even when `.env.local` names `localhost`.
   The console dev server (`pnpm dev`, port 5173) keeps working from any origin too.

## HTTPS listener (phones, microphone)

HACKATHON: self-signed certificate. Phone browsers give the microphone only to https pages
(or `localhost`), so the server (live and `--mock`) also serves the same router over https.

| Variable | Default | Meaning |
|---|---|---|
| `HTTPS_PORT` | `8443` | https port on the `CLINIC_BIND` address; `0` turns https off |
| `TLS_CERT`, `TLS_KEY` | unset | PEM certificate and key; both or neither |
| `TLS_DIR` | `data/tls` | where the generated self-signed certificate is kept |

Without `TLS_CERT`/`TLS_KEY` the first start generates a self-signed certificate (rcgen, ring)
naming `localhost`, `127.0.0.1`, the computer name and every non-loopback IPv4 address, and
reuses it on later starts (a new one when an address is new or it is within 30 days of expiry).
The start log prints the URLs: `Phones: https://<lan-ip>:8443/patient/ - accept the certificate
warning once`. A certificate problem or a taken port is logged and the server stays on http.
Ctrl+C stops both listeners, then seals the journal as before.

Check: `curl -k https://<lan-ip>:8443/health` and `curl -k https://<lan-ip>:8443/patient/`.
Each host name gets its own cookie: a patient signed in over http signs in again over https.
