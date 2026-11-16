# Clinic Pilot · Admin console (job 5)

React, TypeScript and react-three-fiber console for [`05_admin.md`](../05_admin.md). It shows the clinic in 3D, the robots live, the zones, the stock, the night round and the audit log, and it can stop every robot at once.

It talks only to the server (contract C3). Until job 3 delivers the server, a **demo clinic runs in the browser**: four robots drive around walls and furniture, staff requests appear by themselves, the stock goes down, and the robots obey the zones. All data is invented.

## Run it

```bash
cd implementation/admin
pnpm install                 # once per computer
cp .env.example .env.local
# Edit .env.local with the real server URL and keep VITE_USE_MOCK=false.
pnpm dev                     # http://localhost:5173
```

Real server mode is the safe default. The room page uses exactly three rooms:
Room 212, Room 213 and Room 216. Set `VITE_USE_MOCK=true` only when you
explicitly want the invented robot demo.

## Three-room patient setup

1. Run `supabase/room_access.sql` and `supabase/room_patient_data.sql` once in Supabase SQL Editor.
2. On the Mac, open `http://localhost:5173` and sign in with an admin email.
3. Open **Patients & rooms**, assign a patient to Room 212, 213 or 216, then register its tablet.
4. Give the one-time pairing code to the iPhone, the other iPhone or the iPad in that room.
5. On that device, open the deployed patient URL followed by `/login.html` and enter the code once.
6. Add the page to the home screen. The device reconnects to that room automatically; no patient
   email address or phone number is used.

The browser cannot safely detect a room from Wi-Fi or GPS. The one-time code is the explicit physical
handover that binds one device to one room. Discharging a patient revokes that room's tablet session.

## Connect the real server

Copy `.env.example` to `.env.local`:

```dotenv
VITE_USE_MOCK=false
VITE_API_URL=http://127.0.0.1:8080
VITE_WS_URL=ws://127.0.0.1:8080/ws
VITE_JURY_URL=http://localhost:8000/jury
VITE_ROBOT_SCREEN_URL=http://localhost:8000
```

The readers in `src/lib/adapt.ts` accept the snake_case fields of the contract (`mic_open`, `pos`, `from_place`, …) and camelCase. A message the panel cannot read is dropped, never shown wrong. When `openapi.yaml` lands, check it against this file first.

The Vite development server listens on port `3000`. The Rust server accepts that local origin by default. Start both from two terminals:

```bash
# Terminal 1
cd implementation/server
cargo run -- --mock

# Terminal 2
cd implementation/admin
npm run dev
```

Open `http://localhost:3000`. In this local mock server, use `admin` / `mock`. The WebSocket connection is `ws://127.0.0.1:8080/ws`; it changes the header from **Offline** to **Live** and streams robot updates.

## What is on screen

| Page | What it does |
| --- | --- |
| **Live map** | 3D clinic, one floor or all floors stacked, 3D or plan camera. Robots glide between updates (never jump), coloured by state, grey with “No signal” after 5 s of silence. Click a robot: battery, task, load, microphone, last update, pause / resume / dock, stop. The route of its task is drawn as the server estimates it (`GET /tasks/{id}/route`, labelled “estimate”, asked again every 3 s). Zones and the server's heat map (`GET /stats/heat`, every 5 s) can be shown. When the server says the active clinic plan changed (`map.updated`), the building is fetched again and redrawn without a page reload; a `resync` reloads everything. **Tablets**: staff tablets (pseudonym, speciality, battery, room) and bedside tablets (bed label, battery, the open requests to that room) stand in their rooms; free ones wait on the shelf, greyed. A tablet can be freed (its user is signed out) or handed out from the side panel. No patient name, no diagnosis. **Presenter** hides side panels, enlarges labels for the big screen and hides tablet labels. |
| **Tasks** | Every task with filters and search. Open one for its full history; cancel an open task. Item and room only, no patient data. |
| **Zones** | Top-down editor: draw, move corners or the whole shape, add or remove corners, delete. Deaf or restricted, with what it does in plain words. Delivery status per robot. Restricted zones are labelled **advisory only** (open question 5). |
| **Stock** | Counts per shelf with threshold, low-stock highlight, last robot count and a mismatch flag, admin ± adjustment. |
| **Night round** | Turn the round on or off, set its time, see the last round’s counts and the low-stock list. |
| **Audit log** | Search, filter by actor and time. Read only: no edit, no delete. |
| **Incidents** | What is wrong, where, and who is on it: robot faults, stops and silences, tablets offline or low, zones not delivered, the audit journal, and patient alarms mirrored from the emergency service. Open ones live, closed ones on request, filter by severity, acknowledge ("On it") and close. Patient alarms are listed but handled in the emergency service: no button here. On the live map, rooms are tinted in the colour of their worst incident (critical red and pulsing, warning orange, info yellow), floors with one carry a dot, and a panel lists the open ones. A patient alarm also shows as a banner on every page. |
| **Monitor** | Server health (uptime, requests/s, refused/s, answer time, robots connected), traffic over 5 minutes, why requests were refused, the busiest client addresses with their status, live security alerts, the block list (block an address or range by hand, with a reason and a duration; unblock), and how the service is doing in counts only (requests, delivered, median wait, most asked for, busiest places). In demo mode, **Simulate an attack** shows a flood being rate-limited then blocked, and a credential-stuffing run blocked after 10 failed logins. |
| **System** | Connections, link to the existing jury screen (`b13_ecran`), the documented backup stop, and the demo controls. |

## Emergency mode

- The switch left of the stop button. One click: the server refuses every request that is not about the emergency, the robots leave the corridors for their docks (a robot carrying something pauses where it is). Leaving takes a second click.
- A striped red banner shows on every page while it is on; stock, zones and night-round changes are disabled with the reason.
- **Patient alarms are not affected**: they go through the separate emergency service, never through this server.
- Like the stop, the switch has its own network code and checks the server's mode every 5 s by itself. A server without emergency mode shows it disabled ("Not on this server").

## The emergency stop

- Always visible, top right, on every page. One click stops **all** robots, no confirmation. “Stop R2 now” in the robot panel stops one.
- It lives in its own React root with its own styles and its own network code (`src/estop/`). It does not use the store, the API client or the 3D scene, so a crash elsewhere cannot hide it.
- It reports each robot: *Sending → Sent → Confirmed stopped* (it reads the robot state back), or *FAILED* / *Not confirmed*. Then it says **“Use the physical red button on the robot now”** and offers the documented backup `POST /api/arret_urgence` of the robot-side screen. That backup is never the first path.

## What the server must add

`requirements/` says exactly what the console calls and reads, for each feature the server does not have yet (emergency mode, tablets, monitoring and blocking, map reload). Start with `requirements/README.md`.

## What loads first

1. The login screen is plain HTML in `index.html`: it shows before any script runs. What is typed there, and an early Enter, are kept when the panel takes over (`src/ui/boot.ts`).
2. The emergency stop and the emergency mode switch, with React only (about 74 KB gzipped).
3. The server client or the demo clinic (never both), then the panel.
4. While the operator types: the live map and the 3D scene (the biggest download), and in demo mode the demo clinic's warm-up (`src/lib/prefetch.ts`).
5. After sign-in, each part shows as soon as it arrives (skeletons until then), and every other page downloads in the background, so the menu answers at once.

Measured on the built demo, slow 3G-like network and a 4x slower CPU, with 6 s of typing: first paint 2.8 s → about 1 s; the 3D map 4.7 s → 1.9 s after sign-in; the stop button 1.7 s → 0.6–0.8 s after sign-in. In server mode the demo simulation is never downloaded.

## What the panel guarantees

- One WebSocket, reconnects by itself with a growing delay, reloads everything when it is back, and shows a red banner while it is down. No page reload needed.
- The token stays in memory. It never goes in the address bar or in browser storage; on the WebSocket it is sent inside the connection.
- No request leaves the local network: fonts, icons, 3D code and the label font are bundled; the 3D text library’s CDN fallback is pointed at a local path. No analytics, no tracking.
- The panel asks; each robot decides. A refusal is shown with the robot’s reason.

## Demo controls (System page, demo mode only)

Cut the server line for 15 s · drop one robot’s Wi-Fi for 20 s · block a wheel (fault) · release a robot’s red button after a stop · reset the demo clinic. Use them to show the jury the failure cases.

## Check before handing over

```bash
pnpm run lint
pnpm test          # readers of the server contract, route planner, simulation, emergency mode, tablets, attack detection, incidents (76 tests)
pnpm test:e2e      # Playwright: login, early typing, stop, failed stop, reconnect, deaf zone, stale robot, emergency mode, tablets, attack, patient alarm
pnpm run build
```

On Windows, run `pnpm test` from a path that starts with an upper-case `C:`; Vitest does not start from `c:\`.

## Where things are

```
src/
  estop/        the emergency stop and the emergency mode switch: own root, own network code, loaded first
  lib/          config, server client (http.ts), readers (adapt.ts), live socket, route planner (nav.ts)
  mock/         the demo clinic: plan (world.ts), robots and stock (seed.ts), simulation, fake server, its route estimate (route.ts)
  scene/        the 3D map: floors, furniture, robots, zones, routes, heat map
  state/        the store, the activity feed, and what the map polls from the server (useMapData.ts)
  pages/        one file per page
  ui/           shell, login, small components
e2e/            Playwright tests
scripts/        screenshot helpers for the pitch (shots.mjs, crop.mjs)
```

## Not tested yet

- Against the real server: it does not exist yet. The readers follow `architecture.md`, not a written `openapi.yaml`.
- With real robots or real coordinates. The plan in `src/mock/world.ts` is invented and follows `faux_dossier/lieux.yaml`.
- The backup stop route was not called (demo mode never calls it).
- Browsers other than Chrome.
