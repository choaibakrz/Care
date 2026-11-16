# Pitch buttons: every control against the live server

Checked on 2026-11-16 against the live Rust server (`clinic-server`, no `--mock`, 2 simulated robots
`sim-pip` / `sim-sunny`), through the Vite dev server and through the console the server serves at
`/admin/`. Script: `e2e/pitch-live.spec.ts` (7 tests, all pass on both).

```
# server on :8080 (fresh data dir: note the enrolment code printed on stderr)
VITE_USE_MOCK=false VITE_API_URL=http://localhost:8080 pnpm exec vite --port 5199
ENROL_CODE=XXXX-XXXX-XXXX PITCH_USER=admin PITCH_PASS=pitch-pass-123 API_URL=http://localhost:8080 pnpm exec playwright test pitch-live
# or the console served by the server itself
BASE_URL=http://localhost:8080/admin/ API_URL=http://localhost:8080 pnpm exec playwright test pitch-live
```

Status: **works** (did what it says on the first try), **fixed** (was broken, now works),
**friendly message** (cannot work live; the page says why, no error).

## Sign-in

| Control | Status | Note |
|---|---|---|
| "I have an enrolment code" → Create my account | works | |
| Username / Password → Open the console | fixed | Field was `type=email`: a Rust user name like `admin` was refused by the browser. Now "Username", text. |
| Sign-in request | fixed | Asked the Node `/api/admin/login` first: a 404 in the console on every sign-in. Now asks `/auth/derivation` first. |
| Wrong password | fixed | Said "Your session has ended". Now the server's "User name or password is incorrect." |
| Typing before the page has loaded | fixed | The password typed into the static login screen while the bundle loaded was sometimes lost. It is now read again when the screen is replaced. |
| Sign out | works | |
| Theme switch | works | |

## Live map

| Control | Status | Note |
|---|---|---|
| "Live map" link and `/` | fixed | `/` sent you to Patients in live mode, so the 3D map could not be reached. |
| Page itself after selecting a robot | fixed | Crashed with "Maximum update depth exceeded" (GiveTask built a new array in a store selector). |
| Floor tabs, All floors, 3D / Plan, Zones / Tablets / Heat toggles, Presenter | works | |
| Fleet row / robot tag click (select) | works | Mood emoji shown in both. |
| Give task: Go to | works | |
| Give task while the robot drives another task | fixed | The server dropped the robot's instant "failed" answer (task was stored after the order left), leaving tasks `assigned` forever, which also blocked switching clinic plans. Now refused: 409 "Robot sim-pip is busy with task …". |
| Give task: Fetch | works | |
| Give task: Follow | friendly message | No staff tablet online in the pitch: the list says "No staff tablet online" and the button stays disabled. |
| Give task: Go charge, Send to dock | works | Robot drives to the home place. |
| Pause / Resume | works | |
| Stop {robot} now, Re-arm robot | works | |
| Drag a simulated robot | fixed | Only the 3D body could be grabbed; the emoji tag (what people grab) did nothing. The tag now starts the drag too. Server answers 200; a wall / restricted zone answers 422 and a toast says why. |
| Home / charging place selector | works | "None" and any place; 🏠 marker on the map. |
| Tablets tab | works | Empty list (no tablet online). |
| EMERGENCY MODE on → Back to normal | works | Banner shows and clears. |
| EMERGENCY STOP (all) → Re-arm all | works / friendly message | Both simulated robots confirm stopped and re-arm. The seed robots r1–r4 are registered but never connect, so their rows say "offline: the stop was not delivered. Use the physical button." (safety wording kept on purpose). |

## Other pages

| Control | Status | Note |
|---|---|---|
| Tasks: filter tabs, robot filter, search, row select | works | |
| Tasks: Cancel this task | fixed / friendly message | The server only cancels before the robot sets off; the button failed for every running task. Shown only for requested/assigned; otherwise "already on the way… pause the robot or send it to its dock". |
| Stock: + / −, "only problems" toggle | works | Count changes on screen. |
| Night round: switch, Save, Run now | friendly message | The live server has no schedule: "No schedule. The server has no night round set." |
| Incidents: Open / With closed, severity filter, Acknowledge, Close | works | Tested on the incident an emergency stop opens. |
| Audit log: actor, time, search, Refresh | works | |
| Monitor: block an address, Remove | works | |
| Zones: New zone, draw, Name, Deaf / Restricted, Create, Save changes, Delete, Discard | works | |
| Zones: "Received by" list | fixed | Stayed "waiting…" forever: the server did not publish `zone.updated` after a robot's ack, and the save answer overwrote an ack that came first. Now turns "received" for both robots. |
| Clinics: New from the active one, Export, Activate, Delete | works / friendly message | Activate is refused while a robot still drives a task: "Tasks are still open; finish or cancel them before switching plans." |
| Building: Add furniture, Save, Reset modifications, Add floor, Discard | works | |
| Patients: Admit, Register tablet (pairing code), Copy code, Refresh, Discharge and reset | works | Copy on plain http over the LAN: "Copy was blocked. Read the code directly from this screen." |
| Patients: room labels | fixed | "Floor 2 · Floor 2" said once. |
| System page | works | Demo controls only exist in the mock; the "Open the jury screen" link needs `b13_ecran` running on :8000. |
| Console served at `/admin/` on another port | fixed | Talked to `localhost:8080` (from `.env.local`) instead of the server that served it. |

## Not covered by the script

- Importing a clinic plan file and "Import modifications" (file pickers): not exercised.
- Zone corner dragging in the plan editor: only drawing, renaming and deleting are scripted.
- Robots r1–r4 come from `seed/demo_fleet.json`: they show "No signal" and count in "Need attention". For a cleaner pitch, keep them out of the database the pitch uses.
