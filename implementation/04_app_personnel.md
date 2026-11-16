# Job 4: Staff app developer

**Mission:** one phone and tablet app for doctors, nurses and the rest of the staff. They tell the robot where they are, ask it for things, and watch the request move.

You own `implementation/app/`. Stack: Flutter (iOS, Android, tablet). You talk only to the server (contract C3). You never connect to the robot or the model service.

Read first: [architecture.md](architecture.md) (contract C3), `briques/clinique/ecrans_*.py` and `traductions_ecrans.yaml` (the existing web screens: which pages and words exist, in five languages), `briques/clinique/badges.yaml` (roles), `briques/clinique/codes_qr.py` (QR codes already generated), `commun/langues.yaml`.

## Who uses it

| Role | Needs |
| --- | --- |
| Nurse | Call the robot, ask for an item, see status |
| Doctor, therapist | Same, plus approve robot-written summaries for their patients |
| Reception | Same, plus see all open requests |
| (Admin has their own web panel, job 5) | |

Patients are **not** a user of this app. The existing patient pages in `clinique/` stay as they are.

## What you build

### P0. Against the mock, no server needed (first hours)
- [ ] Project, navigation, theme, an API client generated from `openapi.yaml` (see job 3's P2) or written by hand with the same models. Point it at the mock server from job 3.
- [ ] **Login** with the token flow from C3. Show the role. Keep the token in secure storage.
- [ ] **Where am I:** pick a room from `GET /map`, or scan the QR code at the door. Send `PUT /me/location`. Show the current room at the top of every screen.
- [ ] **Ask for an item:** list from `GET /inventory` with live stock, tap an item, confirm the destination (default: my room), `POST /tasks`.
- [ ] **Call the robot to me:** a one-tap task, `go_to` my room.
- [ ] **My requests:** list with a live state (`requested`, `assigned`, `en_route`, `delivered`, `failed`, `resumed`, `cancelled`) through `WS /ws`. Cancel while it is still `requested` or `assigned`. Show the failure `reason` in plain words.

### P1. Make it usable and honest
- [ ] **Languages:** French, German, English, Italian, Chinese from day one. Strings in one file per language, no hard-coded text. The existing `traductions_ecrans.yaml` is a ready source of wording.
- [ ] **Offline and weak Wi-Fi:** a visible "connection lost" banner. The app must not pretend an unsent request was sent. Retry with a clear status.
- [ ] **Robot status on the home screen:** which robots exist, which is free, how far from me (`GET /robots`).
- [ ] **Errors:** show the server's `error.message` as is (it is written to be safe to display).
- [ ] **Phone and tablet layouts.** A nurse with one hand on a phone and a charge nurse at a tablet station.
- [ ] **Large touch targets and high contrast.** Used while walking, sometimes wearing gloves.

### P1. Staff-approved summaries (full version)
- [ ] A screen where a doctor or therapist sees a summary the robot drafted and taps **approve** or **reject**. The robot sends nothing onward until approved. The server stores only the approved text and who approved it.
- [ ] Reuse the wording from `clinique/ecrans_resume.py` and its checks. Every summary line shows its source, as the existing screen does.
- [ ] This depends on a route that is not in C3 yet. Ask job 3 to add `GET /summaries` and `POST /summaries/{id}/decision`. No medical advice anywhere in the interface.

### P2. Comfort mode and polish
- [ ] **Comfort mode** toggle: a gentle, low-volume, slow robot behaviour request for a room (maps to an existing role card; ask job 3).
- [ ] **Interpreter session:** a button "start interpreter in this room" that creates a task. The translation itself runs on the robot.
- [ ] Push notifications for "your request is delivered" (local notifications are enough for the demo).
- [ ] Widget and integration tests; a golden-image test for the main screens.

## Rules for you

- **The app creates tasks. It never commands the robot.** There is no "drive" button. The only direct robot control in your app is none; stop and pause belong to the admin panel.
- **No patient health data is shown or sent.** Tasks carry a room and an item. If a screen needs a patient, ask first.
- **No analytics, no cloud SDK.** Nothing may call out to the internet. The server address is a setting (e.g. `192.168.x.x:8080`). Check your dependencies for hidden network calls (crash reporters, font downloads: bundle fonts).
- **Data is invented.** Show "demo data" somewhere visible, like the existing screens do.

## Interfaces

| You give | To | When |
| --- | --- | --- |
| Screenshots and a short screen list for the pitch and motion design | Hiba | M2 |
| Requests for missing routes (summaries, comfort mode) | Job 3 | early |

| You need | From | When |
| --- | --- | --- |
| `openapi.yaml` and a mock server | Job 3 | M0 |
| Map with room names | Job 3 | M0 |
| Item list with names in five languages | Jobs 1 and 3 | M0 |

## Done when

- On a phone, a nurse logs in, picks a room, asks for a blanket, and watches the state change to `delivered` live while the fake robot moves.
- The same flow works in German and in Chinese.
- With Wi-Fi off, the app says so, does not lose the request, and recovers when Wi-Fi returns.
- Nothing in the build opens a connection other than to the server.
