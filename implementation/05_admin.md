# Job 5: Admin panel developer

**Mission:** a web console where the clinic manager sees the whole clinic in 3D, watches the robots live, edits the zones, checks the stock, and can stop a robot at once.

You own `implementation/admin/`. Stack: React, TypeScript, Three.js (use react-three-fiber). You talk only to the server (contract C3). The panel runs offline, from the local Wi-Fi.

Read first: [architecture.md](architecture.md) (contract C3), `briques/clinique/tableau_flotte.py` and `flotte.yaml` (the existing fleet board), `briques/clinique/faux_dossier/lieux.yaml` (places and floors), `commun/monde.yaml` (places with x, y coordinates), `briques/b13_ecran/jury.py` and `static/jury.*` (the jury screen), `briques/b12_boite_noire/` (what the audit log holds).

## What you build

### P0. Skeleton against the mock (first hours)
- [ ] Vite + React + TypeScript project, router, theme, API client and WebSocket hook, pointed at the mock server from job 3.
- [ ] **Login** (admin role only). Keep the token safe in memory, not in a URL.
- [ ] **Live data layer:** one WebSocket, a store holding robots, tasks, inventory, zones. Handle disconnects and reconnects without a page reload, and show a clear "no connection to the server" banner.

### P0. The 3D clinic map
This is the hard part, so start it early.
- [ ] Render the floors from `GET /map`: floor slabs, walls from polygons, place labels. Use **simple extruded shapes**, not heavy 3D models: it must run fast on a laptop and load offline.
- [ ] **Floor switcher.** The robots never take the elevator (see `lieux.yaml`), so floors are separate views and one floor-exploded view.
- [ ] **Robots as markers** with live position and heading from `robot.updated`. Smooth movement between updates (interpolate, don't jump). Colour by state: idle, busy, paused, fault, estop, offline.
- [ ] **Click a robot** to get a side panel: battery, state, current task, holding, microphone open or closed, last update time.
- [ ] **Task overlay:** the route from source to destination of the selected task.
- [ ] Stale data must look stale (grey out a robot not heard from in 5 s). Never show an old position as live.
- [ ] Until job 3 delivers real coordinates, use the fake data from the mock. A robot's `pos` is in metres in the map's frame.

### P0. Robot controls
- [ ] **Emergency stop**, big and always visible, on every screen. Sends `POST /robots/{id}/command {name: "estop"}`. Show the result clearly (sent / confirmed stopped / **failed: use the physical button**).
- [ ] `pause`, `resume`, `dock` per robot, each with a confirmation for anything that interrupts a running task.
- [ ] Say on screen that the panel **requests**, the robot decides. A refused command shows the robot's reason.
- [ ] Fallback for the demo: the existing robot-side `POST /api/arret_urgence` on `b13_ecran` is open to everyone on the local network. Do not hide this route, and do not wire it as the primary path. It is a documented backup.

### P1. Zones editor
- [ ] Draw, move and delete polygons on the 3D map's floor plane (top-down edit mode is fine). Two kinds: **deaf** (robot closes its microphone) and **restricted**.
- [ ] Save with `PUT /zones/{id}`. Show for each robot whether it has received the zone (the server tells you).
- [ ] Show what a zone does in plain words ("In this zone the robot does not listen").
- [ ] **Restricted zones do not reach the gardien yet** (see architecture.md, open question 5). Label them "advisory only" in the UI until that is decided. Do not imply a guarantee that does not exist.

### P1. Tasks, stock, schedules, audit
- [ ] **Task queue:** all tasks with filters, state, robot, who asked, time. Open a task to see its full history.
- [ ] **Inventory table:** current count per item, low-stock highlight, adjust (admin). Show the last robot count and a **mismatch** flag when the robot's count differs.
- [ ] **Night restock:** edit the schedule, see the last round's result and the low-stock list.
- [ ] **Audit log:** searchable, filtered by actor and time, read only. Never offer edit or delete.

### P2. Polish
- [ ] Link to the existing jury screen (`b13_ecran`) rather than rebuilding it.
- [ ] A **demo mode toggle** that makes the map presentable on the big screen: hide the debug panels, enlarge the labels.
- [ ] Heat map of where robots spend time, or of failed tasks.
- [ ] Screenshots and a short screen recording for the pitch.
- [ ] Component and end-to-end tests (Playwright) for login, estop, zone edit.

## Rules for you

- **No external assets at run time.** Bundle all fonts, textures and libraries. The demo is offline.
- **No third-party analytics or tracking.** Check the dependencies.
- **Do not show patient data.** Tasks show an item and a room only.
- **The emergency stop must keep working if everything else in the page is broken.** Keep its code independent of the 3D scene and the data store, so a rendering bug cannot hide it.
- **Data is invented.** Say so in the footer, as the existing screens do.

## Interfaces

| You give | To | When |
| --- | --- | --- |
| The map format you need (walls, floors, label positions) | Job 3 | M0 |
| Screenshots and a recording for the pitch | Hiba | M2 |

| You need | From | When |
| --- | --- | --- |
| `openapi.yaml`, mock server, fake robot sending positions | Job 3 | M0 |
| Real coordinates and walls for the map | Jobs 3 and 2 | M1 |
| Zone delivery status per robot | Job 3 | M2 |

## Done when

- The 3D map shows both floors and the fake robot moving smoothly, with its state colour.
- Pressing the stop button sends the command, and the panel shows the confirmed result or the "use the physical button" warning.
- An admin draws a deaf zone and the robot's `mic_open` goes false when it enters. The panel shows this.
- With the server killed, the panel shows the lost connection and recovers without a reload.
