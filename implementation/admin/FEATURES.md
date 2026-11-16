# Clinic Pilot admin console: features and how it works

This is a reference for the admin website in `implementation/admin/`: what each screen does, how the code is laid out, how data moves between the console and the clinic server (`implementation/server/`), and what the server provides behind each feature.

For a quick start, read `README.md`. For the exact JSON the console expects from the server, read `requirements/`.

---

## 1. What it is

**Clinic Pilot** is the fleet console used by the clinic administrator. From one browser page the admin can:

- watch every robot, staff tablet and bedside tablet on a 3D model of the clinic, live;
- give robots tasks, pause, resume, dock or stop them;
- draw *deaf* zones (where robots switch their microphone off) and *restricted* zones;
- manage stock, the automatic night restock round, clinic floor plans and the building layout;
- follow incidents, patient alarms (read only), server health, attacks and IP blocks;
- read the audit log, which cannot be changed;
- **stop every robot with one click** and switch the whole clinic into **emergency mode**.

The console only displays and asks. The server decides, and each robot has the final say. When a robot or the server refuses, the console shows the reason it was given.

Data rules that apply on every page:
- No patient data. Tasks keep an item and a place, staff appear as pseudonyms, bedside tablets as bed labels.
- No outside network. Fonts, icons, 3D code and the label font are all bundled. There is no analytics and no CDN.
- The session token is kept in memory only, never in the URL or browser storage.

### Tech stack

| Concern | Choice |
|---|---|
| UI | React 19, TypeScript, Vite 8 |
| Routing | react-router-dom 7 (`BrowserRouter`) |
| State | zustand (one store) |
| 3D | three.js through `@react-three/fiber` and `@react-three/drei` |
| Icons, fonts | lucide-react, Space Grotesk, JetBrains Mono (bundled with fontsource) |
| Tests | Vitest (unit), Playwright (end-to-end), oxlint |

---

## 2. Two ways to run it: demo and real server

The console always calls one interface, `Backend` (`src/lib/backend.ts`). At startup one of two implementations is loaded, never both:

| Mode | How to turn it on | What answers |
|---|---|---|
| **Demo** (default) | `VITE_USE_MOCK` unset or `true` | `src/mock/server.ts`: a whole simulated clinic that runs in the browser. It has 4 robots, staff requests, stock, tablets, incidents, attack traffic and an emergency mode. All data is invented. |
| **Real server** | `VITE_USE_MOCK=false` in `.env.local` | `src/lib/http.ts`: REST calls to `VITE_API_URL` plus a WebSocket to `VITE_WS_URL` |

Environment variables (`src/lib/config.ts`, set in `.env.local`):

```dotenv
VITE_USE_MOCK=false
VITE_API_URL=http://localhost:8080          # clinic server (contract C3)
VITE_WS_URL=ws://localhost:8080/ws          # live stream (default: derived from API URL)
VITE_JURY_URL=http://localhost:8000/jury    # existing jury screen (b13_ecran), linked only
VITE_ROBOT_SCREEN_URL=http://localhost:8000 # robot-side screen; hosts the backup stop
```

Constants: a robot is shown as **"No signal"** after `STALE_AFTER_MS = 5000`. The backup stop path is `/api/arret_urgence`.

On the server side:
- `cargo run -- --mock` serves canned, invented data for every service. The demo accounts are `admin`, `nurse`, and so on, with the password `mock`.
- `cargo run -- --demo` runs the real server with simulated robots on the active plan.
- `cargo run` with no flag wires the real login, accounts, clinic plans and map. Every other service is `Unbuilt` and answers **501 `not_implemented_yet`** (`server/src/services/unbuilt.rs`).
- The server's CORS and WS origins default to `http://localhost:5173`, `127.0.0.1:5173` and `localhost:4173`. Set them with `CORS_ORIGINS` and `WS_ORIGINS`.

In demo mode, any non-empty username and password signs in.

---

## 3. Folder layout

```
admin/
  index.html            static login screen + #estop-root + #root (login shows before any JS runs)
  .env.example          the five VITE_* variables
  README.md             short guide
  FEATURES.md           this file
  requirements/         what the console needs from the server, per feature (JSON, errors, WS messages)
  e2e/admin.spec.ts     Playwright end-to-end scenarios
  scripts/              shots.mjs / crop.mjs: screenshots for the pitch
  src/
    main.tsx            boot order: emergency controls → backend → panel
    start.tsx           mounts <App/> in BrowserRouter, takes over the static login
    App.tsx             routes (each page lazy-loaded), theme, session expiry
    types.ts            every data shape the console uses (Robot, Task, Zone, Incident, ...)
    estop/              emergency stop + emergency mode switch: own React root, own network code
    lib/                config, Backend interface, HTTP client, JSON readers, live socket, helpers
    state/              zustand store, activity feed, map polling hooks
    pages/              one file per page (+ sub-folders for page parts)
    scene/              the 3D clinic (floors, furniture, robots, tablets, zones, routes, heat, incidents)
    mock/               the in-browser demo clinic and fake server
    ui/                 shell (sidebar, top bar, banners, toasts), login, confirm dialog, small kit
    styles/             design tokens (dark/light) and base CSS
```

### Key files in `src/lib/`

| File | Role |
|---|---|
| `config.ts` | Reads `VITE_*` variables |
| `backend.ts` | The `Backend` interface (every call the pages can make) and the proxy that sends each call to the backend loaded at startup |
| `http.ts` | Real server client. Bearer token, 6 s timeout. A 401 fires `clinic-pilot:session-expired`, which signs the user out. Errors come back as `{error:{code,message,details}}`, wrapped in `ApiError`. `optional()` turns a 404 into "not on this server yet". Also holds the clinic-plan functions (`listClinics`, `getClinic`, `saveOverlay`, ...) |
| `adapt.ts` | Tolerant readers. They accept the server's snake_case and camelCase. A message that cannot be read is dropped, never shown wrongly |
| `live.ts` | The one WebSocket. It reconnects with backoff (1 s → 8 s). After opening it sends `{"type":"auth","token":…}` as the first message |
| `format.ts` | Shared words and formats: state labels, `ago()`, place names, `displayState()` (stale → offline) |
| `incidents.ts` | Incident titles, advice text, severity colours, ranking (`worse`, `byUrgency`), the room of an incident |
| `nav.ts` | Grid route planner on a floor plan. Used by the demo for robot motion and route estimates |
| `heat.ts`, `geometry.ts`, `plan.ts` | Heat grid helpers. Point-in-polygon and areas. Building editor helpers (diff into an overlay, read 422 problem paths) |
| `service.ts` | Computes service stats from tasks when the server has no `/stats/service` |
| `prefetch.ts` | Downloads the next code while the browser is idle (see §8) |

---

## 4. Application frame (on every page)

Code: `src/ui/Shell.tsx`.

- **Sidebar** with 11 entries. Badges show counts: open tasks, low-stock items, and open incidents (red if any is critical). The footer shows "Demo clinic · invented data" in demo mode, plus the operator's name and a sign-out button.
- **Top bar**: page title and subtitle, a **connection pill** (Live, Connecting… or Offline), a **Presenter** toggle (live map only), and a dark/light theme switch. The theme is saved in `localStorage`.
- **Banners**, shown in order of importance:
  1. **Patient alarm**, one per alarm from the emergency service. It shows the room, how long ago, and who is on the way. It is read only.
  2. **No link to the emergency service**, when an `emergency_link_down` incident is open.
  3. **Emergency mode** (red stripes), with since when and by whom.
  4. **No connection to the server**. Positions are greyed and old. The console keeps retrying.
  5. **Some data did not load**, with the first error.
- **Toasts** (up to 4, auto-dismiss after 6.5 s; danger toasts stay 13 s) for command results, critical incidents, security blocks and reconnection.
- **Page error boundary**: if a page crashes it shows a message and a "Try again" button. The navigation and the stop button keep working.
- **Confirm dialog** (`ui/confirm.tsx`): one shared `askConfirm()` for destructive actions such as cancelling a task, deleting a zone, freeing a tablet or deleting a clinic.
- **Footer**: "Invented data, demonstration only · no patient data is shown · this panel asks, each robot decides".

### Login

`index.html` contains a plain HTML login form, so it appears before any script loads. `ui/boot.ts` keeps whatever was typed, including an early Enter, when React takes over (`ui/Login.tsx`). Login calls `POST /auth/login {username,password}` and returns a `Session {token, operator, role:'admin'}`.

---

## 5. Pages

### 5.1 Live map (`/`), `pages/LiveMap.tsx`

This is the main screen.

**KPI strip**: robots working out of the total, robots needing attention (fault, stop or no signal), open tasks, tasks delivered (as a share of closed fetch tasks), and low-stock items. Numbers roll from old to new values (`Ticker`). Skeleton placeholders show while the first data loads, so the strip never shows a misleading 0.

**3D stage** (`scene/ClinicScene.tsx`, lazy-loaded because it is the heaviest code):
- **Floor selector** shows each floor, how many robots are on it, and a coloured dot when the floor has an open incident. **All floors** gives an exploded view with the floors stacked.
- **Camera**: 3D (isometric orbit) or Plan (top-down). Drag to turn, scroll to zoom.
- **Toggles**: Zones, Tablets, Heat.
- **Robots** (`RobotMarker.tsx`) are coloured by state: available, on a task, paused, fault, stopped, or no signal (grey after 5 s of silence). Between updates they glide to the new position instead of jumping. Click a robot to select it.
- **Route estimate** for the selected robot's open task. It comes from `GET /tasks/{id}/route`, is polled every 3 s, and is labelled "estimate".
- **Heat map** shows where robots spent their time. It comes from `GET /stats/heat?floor=`, polled every 5 s for each visible floor. If a poll fails, the last grid stays on screen.
- **Zones**: deaf zones are drawn solid, restricted zones dashed.
- **Tablets** (`TabletMarker.tsx`): staff tablets are violet, bedside tablets sand-coloured, free or offline tablets grey. Free tablets wait on a shelf. When a staff tablet's position is an estimate, it shows an uncertainty radius.
- **Incident layer** (`IncidentLayer.tsx`): a room is tinted with the colour of its worst open incident (critical red and pulsing, warning orange, info yellow). Clicking it selects the incident.
- Furniture is drawn from simple boxes (`Furniture.tsx`). The physical scale is in metres (`scene/scale.ts`) and the stage shows a metric scale note.

**Side panels** (`pages/live/`):
- `IncidentsPanel`: open incidents. Selecting one highlights it on the map and moves to its floor.
- `FleetList` / `TabletList`: Robots and Tablets tabs.
- `RobotDetail` for the selected robot. It shows the simulated or real badge, state, current task (title, route, state), battery, what it carries, microphone open or closed, position (floor, x and y in metres), last update, and pick-up place.
  - **Give a task** (`GiveTask.tsx`) has four kinds: *Go to* a place, *Fetch* an item to a place (the pick-up is the item's shelf), *Follow* an online staff tablet, or *Go charge* (sends a dock command). It calls `POST /tasks`.
  - **Controls**: Pause or Resume, Send to dock, **Stop Rx now** (single-robot e-stop), and **Re-arm robot** when the robot is in estop. These call `POST /robots/{id}/command {name}`, where name is `pause`, `resume`, `dock` or `estop`.
  - The controls are disabled when the robot is offline, in fault, or stopped.
- `TabletDetail`: kind, in-use, free or offline, battery, speciality (staff), place, floor, uncertainty, and device id. For a bedside tablet it lists the open requests going to its room.
  - **Free this tablet** signs the user out and returns the tablet to the shelf (`POST /devices/{id}/disconnect`).
  - **Hand out** assigns it to a staff member (pseudonym and speciality) or to a bed (bed label and room), through `POST /devices/{id}/assign`.
  - If the server has no tablet registry (`managed=false`), tablets are shown but cannot be changed.
- `ActivityFeed` (`state/events.ts`): the last 40 events, newest first: task steps, robot state changes, microphone opened or closed (entering or leaving a deaf zone), and alerts. When the page opens, it is filled from task history.

**Presenter mode** hides the KPIs, side panels and tablet labels and enlarges labels for a big screen.

### 5.2 Tasks (`/tasks`), `pages/Tasks.tsx`

- A table of every task, newest first, with filter tabs and counts (All, Open, Delivered, Failed, Resumed, Cancelled), a text search (id, item, place, requester) and a robot filter.
- Selecting a row opens the **task detail**: From → To route card, who asked, robot, created time, failure reason, and a full **history timeline** with time and actor for each step.
- **Cancel this task** is shown for open tasks and asks for confirmation (`POST /tasks/{id}/cancel`). If the task is en route, the robot takes back what it carries.
- Task states: `requested → assigned → en_route → delivered | failed | resumed | cancelled`. Task kinds: `fetch`, `go_to`, `follow`, `restock_round`.

### 5.3 Zones (`/zones`), `pages/Zones.tsx` + `zones/PlanEditor.tsx`

Three columns: the zone list, a top-down SVG plan editor, and the zone form.
- **Draw** a new zone by clicking corners and clicking the first corner to close it. **Edit** by dragging corners or the whole shape. A "+" handle adds a corner and a double-click removes one. You can **delete** a zone.
- **Kinds**:
  - *Deaf*: the robot closes its own microphone inside the zone, even with no connection.
  - *Restricted*: robots should stay out. This is **advisory only**: the zone is not sent to the robot's safety guard.
- The form shows the number of corners, the area in m², and the robots inside right now with their microphone state.
- **Delivery status per robot** shows whether each robot has received, is waiting for, or failed to get the latest zone. The list shows `received/total`.
- Save calls `PUT /zones/{id}`. Delete calls `DELETE /zones/{id}`. Both are disabled in emergency mode.

### 5.4 Clinics (`/clinics`), `pages/Clinics.tsx` (real server only)

This page manages the stored clinic floor plans. In demo mode it shows "needs the server".
- A table with name, id, version, update time and an **Active** badge.
- Actions:
  - **Activate** (`POST /clinics/{id}/activate`).
  - **Export** the effective plan, **Export base**, **Export modifications** (the overlay). These download JSON files.
  - **Import modifications** (`PUT /clinics/{id}/overlay` with `If-Match`).
  - **Delete** (inactive plans only, after confirmation).
- **Import** a plan file (`POST /clinics`) and **New from the active one** (copy under a new name).
- Server validation errors (422 `invalid_plan`) are listed by path (`Problems` component).

### 5.5 Building (`/building`), `pages/Building.tsx` + `building/BuildingPlan.tsx` (real server only)

This page edits the active plan as a local draft, floor by floor, on an SVG plan with a 0.1 m snap.
- **Tools**:
  - Select: drag corners, add corners with "+", double-click to remove a corner.
  - Add room: click corners, then click the first corner to close.
  - Add wall: click points, then *Finish wall*.
  - Add place: one click. Kinds are room, shelf, dock and point.
  - Add furniture: 17 kinds, from bed and shelf to door, with width and depth in metres. A **solid** flag means robots go around it.
  - Add floor: draw its outline.
- The side panel edits the selection's name and kind and has **Delete**. A floor can only be deleted once it is empty.
- **Saving** sends only the *differences from the base plan* as an overlay: `PUT /clinics/{id}/overlay` with `If-Match: "<version>"`.
  - On **412** (someone saved meanwhile) you can choose *Reload server version* or *Keep editing (my save will overwrite)*.
  - On **422** the shapes the server refused are outlined in red.
- **Reset modifications** goes back to the base plan (`DELETE …/overlay`). **Discard** drops the local draft.
- After a save the server publishes `map.updated`, and the live map redraws itself without a page reload.

### 5.6 Stock (`/stock`), `pages/Stock.tsx`

- Summary: number of item types, units on shelves, low-stock count, and the count of items where the robot's count differs.
- A table grouped by shelf: count with a level bar and threshold marker, threshold, **last robot count** (flagged when it differs from the count), and how long ago it was counted.
- A **± stepper** adjusts the count (`POST /inventory/{id}/adjust {delta}`). It is disabled in emergency mode. An **Only problems** filter is available.

### 5.7 Night round (`/night`), `pages/Night.tsx`

- The automatic restock round: on/off switch, departure time, and assigned robot. Save calls `PUT /schedules/{id}`.
- **Last round**: result (every count matched, some counts differ, did not run, or not run yet), and for each shelf the expected count against the counted one.
- **Low stock for the next round** lists items below their threshold.
- In demo mode there is also *Run a round now (demo)*.

### 5.8 Incidents (`/incidents`), `pages/Incidents.tsx`

- Open incidents arrive live. *With closed* fetches the closed ones on request (`GET /incidents?open=false`). There is a severity filter (All, Critical, Warning, Info).
- Incident codes:
  - Robots: `robot_fault` (motor, battery, sensor, ...), `robot_offline`, `robot_estop`.
  - Tablets: `tablet_offline`, `tablet_battery_low`, `tablet_app_error`.
  - `zone_not_delivered`, `journal_degraded`.
  - `emergency_alarm` (patient call, urgent call or emergency, mirrored from the emergency service).
  - `emergency_link_down`.
- Each row (`IncidentRow.tsx`) shows a title, a line of advice, place, age, number of repeats, and who acknowledged it. **On it** acknowledges (`POST /incidents/{id}/ack`). **Close** closes it (`POST /incidents/{id}/close`).
- **Patient alarms cannot be acknowledged here.** The emergency service handles them, and the server answers 409.
- In demo mode, *Patient alarm (demo)* raises an alarm in Room 13, which the demo resolves after 45 s.

### 5.9 Audit log (`/audit`), `pages/Audit.tsx`

- Read only. The page has no edit or delete control.
- The table shows when, who, action (with detail), target, and result (OK, Refused or Failed).
- You can filter by actor and time window (15 min, 1 h, 24 h or any time) and search the text. It refreshes every 10 s or on demand. It uses `GET /audit?from&to&actor`.
- On the server, the log is a signed and sealed append-only journal (`crates/audit`: segments, seals, anchors, verification). See `GET /audit/integrity`.

### 5.10 Monitor (`/monitor`), `pages/Monitor.tsx` + `monitor/`

Server health and security. Fast data is polled often and service statistics every 10 s (`useMonitor.ts`).
- **Summary**: uptime, requests per second, refused per second, answer time, robots connected out of the total, app clients, journal and database status, blocked clients (`GET /monitor/summary`).
- **Traffic**: a line chart over 5 minutes of accepted and refused requests (`GET /monitor/traffic?window_s=300`).
- **Why requests were refused**: unauthorized, forbidden, rate-limited, blocked, emergency mode, or invalid.
- **Who is calling the server**: the busiest client addresses (`GET /monitor/clients?limit=20`) with label, request rate, refusals, login failures and status (ok, limited or blocked). There is a quick block button.
- **Security alerts**: a live feed from the `security.alert` WS message (rate limited, auto blocked, login burst, blocked, unblocked).
- **Blocked addresses**:
  - Automatic and manual rules, with target, reason, source, expiry and hits.
  - Block an address or range by hand with a reason and duration (`POST /security/blocks`).
  - Unblock (`DELETE /security/blocks/{id}`).
- **How the service is doing** over the last N hours, as counts only: requests, delivered, failed, median and p90 wait, most-asked items, busiest places, and bedside tablets online (`GET /stats/service?hours=`). If the server has no such route, the numbers are computed from the tasks already loaded (`lib/service.ts`), and the page says so.
- In demo mode, **Simulate an attack** sends a flood from `203.0.113.42`, which is rate-limited and then blocked, and a credential-stuffing run from `198.51.100.7`, which is blocked after 10 failed logins.

### 5.11 System (`/system`), `pages/System.tsx`

- **Connections**: mode (demo or real), live stream state, API and WS addresses, and the signed-in operator.
- **Jury screen**: a link to the existing `b13_ecran` jury screen, which opens in a new tab.
- **If the stop button fails**: the documented backup. First, press the physical red button on the robot. Second, use `POST {robotScreenUrl}/api/arret_urgence` on the robot-side screen.
- **Demo controls** (demo mode only, `system/DemoControls.tsx`):
  - Cut the server line for 15 s.
  - Drop one robot's Wi-Fi for 20 s.
  - Block a wheel (fault).
  - Release a robot's red button.
  - Reset the demo clinic.

---

## 6. Safety features

### 6.1 Emergency stop (`src/estop/`)

- The stop is **always visible at the top right, on every page**. **One click stops all robots, with no confirmation.**
- It runs in **its own React root** (`#estop-root`) with its own CSS and its own network code (`send.ts`). It does not use the store, the API client, the readers or the 3D scene. A crash anywhere else cannot hide it or break it. It is the first code the browser downloads (`main.tsx`).
- `bridge.ts` holds its small state. The panel only *pushes* the token, the robot ids and the mode into it, and never reads anything back.
- **Per-robot report**: *Sending → Sent → Confirmed stopped*. Confirmation comes from reading `GET /robots` until the robot's state is `estop`. Otherwise the report shows *FAILED* or *Not confirmed*. Each robot has its own run number, so "stop R2" after "stop all" replaces only R2's line.
- When a stop fails, the panel says **"Use the physical red button on the robot now"** and offers the backup `POST /api/arret_urgence` on the robot-side screen. The backup is never the first path, and it is never called in demo mode.
- **Re-arm** sends `resume` to the stopped robots once a person confirms the area is safe.
- Requests time out after 4 s, separately from the panel's 6 s.
- On the server, the stop is never refused, not in emergency mode, not when the journal is degraded, and not by IP blocks.

### 6.2 Emergency mode (`estop/mode.ts`, `ModeSwitch.tsx`)

- A switch next to the stop button. **One click turns it on. Turning it off takes a second, confirming click.** It calls `PUT /system/mode {mode, reason}`.
- While it is on:
  - The server refuses every request that is not on its allow-list with **503 `emergency_mode`** (`server/src/emergency_mode.rs`).
  - Robots leave the corridors for their docks. A robot carrying something pauses where it is.
  - The console shows a red banner on every page and disables changes to stock, zones and the night round. The disabled buttons explain why in a tooltip.
- **Patient alarms are not affected.** They go through the separate emergency service.
- The switch has its own network code. It reads `GET /system/mode` every 5 s and also takes `mode.updated` from the live stream. If the server answers 404, the switch shows "Not on this server" and asks again only once a minute.

### 6.3 Other guarantees

- One WebSocket with automatic reconnection. After reconnecting, the console reloads all its data and shows "Connection restored". A `resync` message also triggers a full reload.
- A robot silent for 5 s turns grey ("No signal"). Its last position is shown as old, not live.
- Every command shows the robot's answer. A refusal (HTTP 400, 403, 409 or 422) is treated as an answer, not a failure.

---

## 7. Data flow

### 7.1 Store (`src/state/store.ts`)

One zustand store holds: the session, connection state, map, mode, robots, tablets, tasks, incidents, security alerts, inventory, zones, schedules, activity events, toasts, and UI choices (selected robot, tablet or incident, floor, theme, presenter mode, the zones/heat/tablets toggles, exploded view, camera view).

- **`signIn`** stores the token, gives it to the e-stop bridge, calls `loadAll()` and opens the live socket.
- **`loadAll`** fetches robots, map, tasks, inventory, zones, schedules and open incidents in parallel. Each part is shown as soon as it arrives. Tablets and mode are fetched separately, so a server without them does not block the rest. When everything has arrived, it picks a robot to select (the first busy one) and its floor, and fills the activity feed.
- **`signOut`** closes the socket and clears everything, including the e-stop's token.

### 7.2 Live messages (WebSocket `/ws`)

The first message the client sends is `{"type":"auth","token":"…"}`, within 5 s. Otherwise the server closes the socket with code 4401. Messages the console handles:

| Message | Effect |
|---|---|
| `robot.updated` | Insert or update the robot, add activity events (state change, microphone), refresh the e-stop's robot list |
| `task.updated`, `inventory.updated`, `zone.updated`, `zone.deleted`, `schedule.updated` | Insert or update, or remove, in the store |
| `alert` | Activity event. A warning or critical alert also shows a toast, unless it is about a stop, which already has its own report |
| `map.updated` | If the active plan's version changed, re-fetch `GET /map` and redraw in place |
| `mode.updated` | Update the banner and the switch |
| `device.updated` | Insert or update a tablet |
| `positions.delta` | Move tablets. A tablet that is no longer seen becomes offline. Robot positions in this message are not read yet |
| `incident.updated` | Insert or update, or remove when closed. A new critical incident shows a toast |
| `security.alert` | Add to the Monitor feed. Auto-blocks and login bursts show a toast |
| `resync` | Reload everything |

### 7.3 REST endpoints the console calls

| Area | Calls |
|---|---|
| Auth | `POST /auth/login` |
| Fleet | `GET /robots`, `POST /robots/{id}/command` |
| Tasks | `GET /tasks`, `POST /tasks`, `POST /tasks/{id}/cancel`, `GET /tasks/{id}/route` |
| Map | `GET /map`, `GET /stats/heat?floor=` |
| Clinic plans | `GET/POST /clinics`, `GET/PUT/DELETE /clinics/{id}`, `POST /clinics/{id}/activate`, `GET /clinics/{id}/base`, `GET/PUT/DELETE /clinics/{id}/overlay` (version through `ETag` / `If-Match`) |
| Zones | `GET /zones`, `PUT/DELETE /zones/{id}` |
| Stock | `GET /inventory`, `POST /inventory/{id}/adjust` |
| Night round | `GET /schedules`, `PUT /schedules/{id}` |
| Audit | `GET /audit?from&to&actor` |
| Incidents | `GET /incidents[?open=false]`, `POST /incidents/{id}/ack`, `POST /incidents/{id}/close` |
| Tablets | `GET /live`, `GET /devices`, `POST /devices/{id}/disconnect`, `POST /devices/{id}/assign` |
| Mode | `GET/PUT /system/mode` |
| Monitor | `GET /monitor/summary`, `GET /monitor/traffic?window_s=`, `GET /monitor/clients?limit=`, `GET/POST /security/blocks`, `DELETE /security/blocks/{id}`, `GET /stats/service?hours=` |
| Backup stop | `POST {VITE_ROBOT_SCREEN_URL}/api/arret_urgence` (robot-side screen, not the server) |

All of these routes exist in the server router (`server/src/lib.rs`, plus `console_routes()` for mode, monitor, blocks, devices and service stats). The server's full API is at `/docs` (Scalar, offline) and `/openapi.json`. There is also a copy in `server/docs/openapi.yaml`. The WS message reference is in `server/docs/ws_messages.md`.

Errors always look like `{"error":{"code","message"}}`. The console shows `message` as it is.

---

## 8. Load order and performance (`main.tsx`, `lib/prefetch.ts`)

1. The static HTML login appears before any script runs.
2. The emergency stop and the mode switch load next, with React only (about 74 KB gzipped).
3. Then either the server client or the demo clinic, never both.
4. While the operator types, the live map and the 3D scene are fetched in advance, and in demo mode the demo clinic warms up.
5. After sign-in, each part appears as soon as its data arrives, with skeletons until then. All other pages download in the background.

Measured on a slow 3G-like network with a 4× slower CPU: first paint went from 2.8 s to about 1 s, the 3D map after sign-in from 4.7 s to 1.9 s, and the stop button after sign-in from 1.7 s to 0.6–0.8 s.

---

## 9. The demo clinic (`src/mock/`)

| File | What it simulates |
|---|---|
| `world.ts` | Invented clinic plan (follows `faux_dossier/lieux.yaml`): floors, rooms, walls, places, furniture |
| `seed.ts` | 4 robots, stock, 2 zones, the night schedule |
| `sim.ts`, `sim-state.ts` | The simulation loop and its shared state |
| `sim-motion.ts` | Robots follow planned paths, turn smoothly, give way to each other |
| `sim-tasks.ts` | Staff requests appear on their own. Each one goes to the nearest free robot on the right floor. Pick-up, delivery, night round |
| `sim-admin.ts` | Admin commands, zones (with per-robot delivery), stock adjustments, schedule, emergency mode |
| `sim-tablets.ts` | Staff tablets follow their owner, bedside tablets stay with a bed, free tablets sit on the nurse-station shelf |
| `sim-incidents.ts` | Incidents raised by what happens (stops, faults, silences, low tablet batteries) and patient alarms |
| `traffic.ts` | Invented client traffic, rate limiting and auto-block detection, the attack scenario |
| `route.ts` | Route estimates for `GET /tasks/{id}/route`, using `lib/nav.ts` |
| `server.ts` | Wraps it all as a `Backend`: same calls, same live messages, a short answer delay, a "cut the line" switch, and `demoControls` |

---

## 10. Server side (`implementation/server/`)

The server is a Rust (axum) workspace on SQLite.

| Crate | Role behind the console |
|---|---|
| `domain` | Core types: robots, tasks and their states, incidents, system mode, roles and permissions, ports (traits) |
| `security` | Accounts, identity, CORS and origin checks, rate limits, known networks, monitoring and blocks |
| `realtime` | WebSocket hub, robot sessions, liveness, incidents, zone delivery to robots, wire protocol |
| `locations` | Clinic plan model, loader, validation, overlays, live positions, tablet positioning, privacy |
| `optimization` | Dispatcher (who gets a task), routing graph, route preview (the route estimate), stock reservations, tours (night round) |
| `scheduler` | Cron-style schedules (night round) |
| `audit` | Signed, sealed append-only journal, flight recorder, verification |
| `storage` | SQLite repositories (clinics, accounts, devices, events, audit index), migrations in `migrations/` |
| `python-bindings` | Bridge to the Python "brain" (translate, simplify, summarise, report) |

How the server supports the console:
- **Roles**: the console routes are admin only, except `GET /system/mode`. Non-admin robot commands (from a nurse, for example) raise a `staff_command` alert, and the admin can revert them.
- **Emergency filter and journal guard** sit at the router level. In degraded journal mode, mutating routes answer 503, but the e-stop still goes through.
- **Clinic plans** are stored as a base plus an overlay, with versioning. Every change publishes `map.updated`.
- Server docs: `docs/accounts.md` (login and enrolment), `docs/map-format.md`, `docs/task-states.md`, `docs/ws_messages.md`, `docs/progress.md` (build log).

---

## 11. Tests

```bash
pnpm run lint      # oxlint
pnpm test          # Vitest
pnpm test:e2e      # Playwright, demo mode
pnpm run build     # tsc + vite build
```

- **Vitest** covers the server readers (`adapt.test.ts`), the route planner (`nav.test.ts`), building-editor helpers (`plan.test.ts`), and the demo simulation, emergency mode, tablets, attack detection, incidents and routes (`mock/*.test.ts`).
- **Playwright** (`e2e/admin.spec.ts`) covers:
  - login, and typing before the scripts load;
  - the stop on every page with per-robot confirmation;
  - a failed stop showing "use the physical button";
  - automatic reconnection;
  - drawing a deaf zone that every robot receives;
  - a stale robot turning grey;
  - entering and leaving emergency mode;
  - freeing and handing out a tablet;
  - an attack being blocked automatically, and blocking by hand;
  - a patient alarm banner that cannot be acknowledged.

On Windows, run Vitest from a path that starts with an upper-case `C:`.

---

## 12. Planned: medical object recognition (fine-tuned YOLO)

> **Status: planned.** Nothing in this section is built yet, and the console does not show any of it today.
> The vision work happens in `briques/b05_yeux/` (the robot's "eyes"). The current training notebook is `briques/b05_yeux/entrainement/yolo_medical_kaggle.ipynb`. It trains a small YOLO, starting from `best.pt`, on a unified detection set of 68 classes.

### 12.1 Goal

Each robot will get one camera model that does two jobs:

1. **Recognise medical utilities**: find them in the image (bounding box) and say which item they are, for example gauze, syringe, glove box, saline bag, thermometer or blood-pressure cuff.
2. **Still recognise ordinary objects**: the original classes (person, chair, bed, bottle, cup, laptop, …).

The second job matters as much as the first:
- **Avoiding obstacles**: a chair, a person or a trolley in the way is something the robot must go around.
- **"Not a medical utility"**: when an object is detected as something ordinary, the robot knows it is not a medical item. It will not put it in stock, count it, or take it to a doctor.

With this model, robots can **organise the clinic's storage**: check that each item is on the right shelf, count it, and spot an item that does not belong there. They can also **help doctors retrieve objects**: find the asked-for item and bring it.

### 12.2 Model

- **Base**: YOLO **medium** (`yolo11m`) by default, or **large** (`yolo11l`) if the robot's computer can run it fast enough. Both start from the pretrained weights, which already know the 80 COCO classes.
- **New head**: the detection head is replaced by a custom one whose class list is **the original classes + the medical classes**. For example, 80 COCO classes followed by N medical ones.
  - The backbone and neck are kept. They already extract good general visual features.
  - The new head's outputs for the original classes are **initialised from the old head's weights**, so the model recognises ordinary objects from day one. Only the new medical outputs start from scratch.
- **Two-level answer**: each class has a **group**.
  - The groups are `medical/consumable`, `medical/instrument`, `medical/device`, `medical/linen`, … for medical items, and `general/obstacle` or `general/other` for everything else.
  - The robot reads both the exact item ("gauze 10×10") and the kind of object ("medical consumable" or "not medical").
  - The group comes from a fixed class → group table shipped with the model. It is not a second network.

### 12.3 Keeping the old classes (avoiding "forgetting")

If we fine-tune only on medical photos, the model forgets the old classes. Worse, every chair or person in those photos is unlabelled, so the model learns that they are "background". To prevent this:

- **Pseudo-labels for old classes**: before training, run the original pretrained model on every medical image. Its confident detections (person, chair, bed, …) are added as labels. Every training image is then labelled for **both** class sets.
- **Replay**: mix a slice of the original COCO data (for example 20–30% of each batch) into training, so the old classes keep being seen.
- **Gentle schedule**:
  - Freeze the backbone for the first epochs, so only the new head learns.
  - Then unfreeze everything with a low learning rate (cosine schedule, as in the current notebook).
- **Two scores to check after each run**:
  - mAP on the medical validation set: is it learning the new classes?
  - mAP on a COCO validation subset: did it forget the old ones?

  A run is accepted only if the COCO score drops by no more than a small agreed margin.

### 12.4 Data

- The starting dataset is the existing unified detection set (68 classes, `unified_detection.zip`), with its classes mapped onto the medical class list and groups.
- It is completed with photos taken **in the clinic**: shelves, trolleys, the nurse station, with the robot camera's own angle and lighting.
- The augmentations already used in the notebook (scale, rotation, colour, mixup, copy-paste) help with cluttered shelves and partly hidden items.
- Training happens on Kaggle or Colab GPUs, as today. Only the final weights are copied to the robot. **Inference runs on the robot, offline**, and no image leaves the clinic.
- No patient appears in the training data: shelves and objects only.

### 12.5 How it plugs into the rest

- **Robot (`b05_yeux`)**: the model runs on the camera stream. Its detections go two ways:
  - The obstacle avoidance uses ordinary objects plus anything unknown.
  - The item logic uses medical classes only.
- **Server**: the robot already reports what it sees through the existing `SeenItem` type (`item`, `count`, `uncertain`, in `server/crates/domain/src/robot.rs`). The stock ledger reconciles those reports (`reconcile` in `optimization/src/stock.rs`). The model's class id becomes the `ItemId`, and a low-confidence detection sets `uncertain: true`.
- **Admin console**, using screens that already exist:
  - **Stock** page: the *Last robot count* column and the *differs* flag are filled by what the robots counted with the camera.
  - **Night round**: the robot visits each shelf, counts with the model, and the *Last round* table shows expected against counted.
  - **Live map → Give a task → Fetch**: a doctor's request for an item. The robot uses the model to find the right item on the shelf before bringing it.
  - **Incidents** (possible addition): a medical item seen on the wrong shelf, or a non-medical object found in storage.

### 12.6 Steps

1. Fix the medical class list and the class → group table.
2. Build the combined dataset: unified set + clinic photos + pseudo-labels for the old classes + COCO replay slice.
3. Train `yolo11m` with the extended head (old weights copied), then compare with `yolo11l`.
4. Validate on both sets (medical and COCO), and measure frames per second on the robot's hardware. Pick medium or large.
5. Export the model (for example ONNX), load it in `b05_yeux`, and send `SeenItem` reports.
6. Check the result end to end on the Stock and Night round pages.

---

## 13. Known gaps and notes

- `README.md`'s page table does not list the **Clinics** and **Building** pages yet.
- `requirements/README.md`'s "server status" column (2026-11-15) says several features are not started. The server router now has every route listed there. Whether each one actually works depends on how the server is run: `--mock` and `--demo` serve them, while the plain `cargo run` still answers 501 for services listed in `services/unbuilt.rs`.
- The client treats only **404** as "this route is not on the server" (`optional()` in `http.ts`). A **501** from an unbuilt service shows as an error message instead of a quiet "not available".
- The robot positions in `positions.delta` are not read yet. Robots move through `robot.updated` only.
- Restricted zones are advisory only. They are not enforced on the robot.
- The console has not been tested with real robots, real coordinates, or browsers other than Chrome.
