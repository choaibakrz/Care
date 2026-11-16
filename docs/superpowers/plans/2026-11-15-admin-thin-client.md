# Admin Console Thin Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the admin console (`implementation/admin/`) into a pure frontend: it loads every clinic from the server, edits clinic plans and zones through the server, and holds no simulation, routing or statistics logic of its own.

**Architecture:** The console keeps rendering (3D scene, plan editor, pages), view state (`state/store.ts`), formatting and its emergency-stop module. Everything that decides or computes moves to the server (server plan, Tasks A3, A4, 5b, 10b, 11d, 13b). The in-browser demo is removed; demos run against `clinic-server --demo`.

**Tech Stack:** React, TypeScript, Vite, Three.js (react-three-fiber), Vitest, Playwright (already in the console).

**Spec:** `implementation/BACKEND_A_FAIRE.md` §2, server plan `docs/superpowers/plans/2026-11-14-clinic-server.md` Tasks A3 and A4 (the wire contract), and the lead's instruction of Nov 15: "make the frontend only a frontend; the logic lives on the backend; load custom clinics from the backend; edit deaf and blocked zones and the buildings from the frontend".

## Global Constraints

- The console never computes a robot route, a stock rule, a dispatch decision or a simulation. It shows what the server says.
- Offline: no CDN, no external font or script at run time.
- The emergency stop module (`src/estop/`) stays independent of the rest of the page and keeps its fallback to the robot's `/api/arret_urgence`.
- Field names follow the server contract (snake_case on the wire). Unknown message types are ignored, never fatal.
- Data is invented and says so.
- No patient data is shown; tasks show an item and rooms only.
- Existing unit and end-to-end tests keep passing, rewritten against a stub of the server contract where they used the in-browser demo.

## Review Focus

1. A server that refuses an edit (422 `invalid_plan` with a problem list, 412 version conflict, 409 place in use) must show each problem next to the thing it concerns, and never lose the operator's unsaved edits.
2. The live connection drops while editing: the editor keeps the draft, and on reconnect warns if the server's plan version changed.
3. A clinic plan with an unknown room or prop kind still renders (fallback shape), so a plan made elsewhere never blanks the scene.
4. A server with no plan (fresh install) shows an empty state with "import a clinic", not a crash.
5. The emergency stop still works with the rest of the page broken (its own tests unchanged).

---

### Task F1: Strict client from the server contract

**Files:** Modify `src/lib/adapt.ts`, `src/lib/http.ts`, `src/lib/live.ts`, `src/types.ts`. Test: `src/lib/adapt.test.ts` (new).

- [ ] Replace the "accept both spellings" readers with readers of the contract in server Task A3 (still tolerant of missing optional fields, still dropping unreadable messages). Add `cancelled` handling, the `interpreter_session` task kind, `zone.deleted`, `schedule.updated`, `map.updated`, `{items, next}` pages.
- [ ] Tests: one per message type and per list endpoint, fed with the exact JSON examples from the server's `docs/ws_messages.md` and `docs/openapi.yaml`.
- [ ] `npm test` green. Commit `refactor(admin): strict client for the server contract`.

### Task F2: Remove the in-browser demo, route planner and heat map

**Files:** Delete `src/mock/` (`world.ts`, `seed.ts`, `sim*.ts`, `server.ts`), `src/lib/nav.ts`, `src/lib/nav.test.ts`, `src/lib/heat.ts`. Modify `src/lib/backend.ts`, `src/scene/ClinicScene.tsx`, `src/scene/Overlays.tsx`, `src/pages/System.tsx`, `src/state/store.ts`, `src/estop/send.ts` (only the import).

- [ ] Only after the server serves the replacements: `GET /tasks/{id}/route` (server Task 13b), `GET /stats/heat` (11d), `--demo` mode (5b), and the seed clinic exported from `world.ts` (A4 Step 3).
- [ ] The route overlay draws the server's polyline and labels it "estimate"; the heat layer draws the server's grid.
- [ ] `VITE_USE_MOCK` is removed; development runs against `clinic-server --demo`. Unit tests that used the demo get a small fixed fake of the server contract (`src/test/fakeServer.ts`), not a simulation.
- [ ] `npm test` and the Playwright tests green against the fake (unit) and against `clinic-server --demo` (end to end). Commit `refactor(admin): the console is only a frontend`.

### Task F3: Load and switch clinics

**Files:** Create `src/pages/Clinics.tsx`. Modify `src/ui/Shell.tsx` (navigation), `src/state/store.ts`, `src/lib/http.ts`.

- [ ] A Clinics page: list (`GET /clinics`), active marker, activate (with the 409 "open tasks" message shown as is), import a plan file (`POST /clinics` with a JSON file), export the active plan (download `GET /clinics/{id}`), delete an inactive plan.
- [ ] On `map.updated`, reload `GET /map` and redraw without a page reload.
- [ ] Tests: list, import refused with problems shown, activate refused with open tasks, live reload on `map.updated`. Commit `feat(admin): load and switch clinic plans from the server`.

### Task F4: Edit the building

**Files:** Extend `src/pages/zones/PlanEditor.tsx` into `src/pages/plan/` (`PlanEditor.tsx` for shapes, `PlanToolbar.tsx`, `PlanInspector.tsx`), create `src/pages/Building.tsx`.

- [ ] Edit the active plan as a draft: floors (outline), rooms (polygon, label, kind), walls (polyline, with ids), places (point, kind), props (position, size, kind, solid). The existing corner-drag, add-corner and remove-corner gestures are reused for every polygon.
- [ ] Save sends the whole draft with `If-Match` (`PUT /clinics/{id}`). A 422 shows each `{path, problem}` on the shape it names; a 412 offers "reload the server's version" or "keep my draft"; a 409 lists the tasks or items using the place.
- [ ] The draft survives a dropped connection; unsaved changes are flagged before leaving the page.
- [ ] Tests: each refusal kind, draft kept after a failed save, gestures on rooms and walls. Commit `feat(admin): edit the clinic building through the server`.

### Task F5: Deaf and blocked zones on the server

**Files:** Modify `src/pages/Zones.tsx`, `src/pages/plan/PlanEditor.tsx`.

- [ ] Zones are created, edited and deleted only through `PUT/DELETE /zones/{id}`; "blocked" is the label for the `restricted` kind, with the text "Robots plan around it. Not enforced by the robot's safety guard yet."
- [ ] Per-robot delivery status from `deliveries`, live through `zone.updated` and `zone.deleted`.
- [ ] Tests: create, edit, delete, refusal shown next to the shape. Commit `feat(admin): zones edited through the server`.

### Task F7: Tablets on the map

**Files:** `src/scene/TabletMarker.tsx` (new), `src/pages/Devices.tsx` (new), `src/scene/ClinicScene.tsx`, `src/state/store.ts`, `src/lib/{http,adapt}.ts`.

- [ ] Bedside tablets drawn at their place, staff tablets at their room/estimate, with kind, label/owner label and online state; nothing else about a person.
- [ ] Devices page: list, register, edit label/place, delete (`/devices`, server Task A5/8b).
- [ ] Tasks show "following <owner>" / "attending <bedside label>" (`target_label`).
- [ ] Tests: markers from `GET /live`, `device.updated` live, no extra personal field rendered. Commit `feat(admin): tablets on the map`.

### Task F8: Live robot routes and on-the-fly changes

**Files:** `src/scene/RouteLine.tsx` (new), `src/pages/live/RouteEditor.tsx` (new), `src/pages/live/RobotDetail.tsx`, `src/lib/{http,adapt}.ts`.

- [ ] Draw each robot's next-seconds route from `robot.route` (solid when `source: "robot"`, dashed and labelled "estimate" when `server_estimate`).
- [ ] Admin edits a route: drag waypoints on the floor plane, send `PUT /robots/{id}/route`; show "suggested → accepted/refused (reason)" from `route.answered`; withdraw with `DELETE`. A 422 shows each problem on the waypoint it names. The UI says plainly: "a suggestion — the robot and its safety guard decide".
- [ ] The emergency stop stays visible and independent while editing.
- [ ] Tests: route drawn and updated, refusal shown with reason, 422 problems placed, estop usable during edit. Commit `feat(admin): live robot routes and route suggestions`.

### Task F6: Gate

- [ ] `npm run build`, `npm test`, Playwright against `clinic-server --demo`, a grep proving no `mock/`, `nav`, `heat` logic remains, and a manual check that the emergency stop page works with the server stopped. Update `implementation/05_admin.md` to describe the thin client.

### Task F9: Client-side account key (server Task A7)

**Files:** `src/lib/accountKey.ts` (new), `src/ui/Login.tsx`, `src/lib/http.ts`, `src/pages/Accounts.tsx` (new: enrolment codes, disable).

- [ ] `deriveAccountKey(username, password, clinicId)` with WebCrypto PBKDF2-HMAC-SHA256, 600 000 iterations, 32 bytes, salt `"clinic:" + clinicId + ":" + lowercase(username)`; test against the server's published test vector (`docs/accounts.md`).
- [ ] Login sends `{account_key}` only; the username and password never leave the page and are not stored (memory only, cleared after derivation).
- [ ] Enrolment screen (code + new credentials + pseudonym) and an admin Accounts page (create enrolment code, disable an account by its tag).
- [ ] Tests: test vector, no request body ever contains `username`/`password`. Commit `feat(admin): client-side account key`.
