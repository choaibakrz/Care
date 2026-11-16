# Emergency service: design

Nov 14, 2026. Status: **design for review.** The implementation plan follows once the lead approves it.

## What it is

A separate, small, independent program whose only job is getting a person to a patient who pressed the alarm. Robot management, inventory, maps and statistics are all secondary to it. It keeps working when the main server, the database, the robots and the admin panel are all down. It is the last part of the system to fail.

**Not a replacement for a certified nurse-call system.** Real clinics have nurse-call systems built and certified for this (in German-speaking countries, the DIN VDE 0834 standard for call systems in hospitals). This service is a prototype. In any real clinic it runs **alongside** the certified system, never instead of it. The pitch and the UI must say so.

## What it handles (and nothing else)

| Alarm | Source | Level |
| --- | --- | --- |
| Patient call ("mayday") | Bedside button or patient tablet | High |
| Staff emergency call ("I need help here now") | Staff app, one long press | Critical |
| Device-detected fault of the alarm path itself | Self-test, a silent button | Fault (goes to the nurse station, never to a patient) |

No robot management, no inventory, no positioning maths, no medical content. Every extra feature is a way to fail.

## Independence: what "fully independent" means here

| Layer | Rule |
| --- | --- |
| **Code** | Its own Cargo workspace at `implementation/emergency/`. It depends on no crate of the main server. A few types are duplicated on purpose. Minimal dependencies (tokio, axum, rusqlite or sqlx-sqlite, serde, ed25519/hmac, tracing). No pyo3, no optimisation, no 3D. |
| **Process** | Its own binary, its own port, its own data file, its own journal directory. Restarted automatically by the operating system's service manager (launchd on Mac, systemd on Linux), with a watchdog heartbeat. |
| **Hardware** | Recommended: its own small machine (a Raspberry Pi or a spare laptop) on a UPS, not the main server's computer. For the hackathon demo it may share the laptop but runs as a separate process. |
| **Data** | Holds its own copy of everything it needs: the staff roster (id, role, owner label, on duty), the room list with walking distances, and the alarm devices' keys. The main server pushes updates when it is up; the emergency service keeps the last good copy when it is not. |
| **Staff positions** | Staff tablets send a small heartbeat with their current room **directly** to the emergency service every 10 s, as well as to the main server. It never asks the main server where people are. |
| **Network** | Same Wi-Fi, separate addresses. Two instances (below). |

## Redundancy: two instances, both active

Two instances, **A** and **B**, on two machines. Every alarm device sends every alarm to **both**. Both run the escalation. Staff apps connect to both and **deduplicate by alarm id**. A duplicate page is acceptable; a lost alarm is not.

There is no leader election or consensus between A and B: that machinery is itself a common cause of failure. A and B share only acknowledgements: when a staff member accepts an alarm, the app sends the acceptance to both, and each instance also forwards acknowledgements it receives to the other.

## The alarm, end to end

1. **Press.** The device creates an alarm id (device id plus a monotonic counter), signs it with its own key (HMAC, so a forged or replayed alarm is rejected), and sends it to A and B. It retries every 2 s until at least one instance confirms. Its light shows "received" only after a confirmation.
2. **Room lights up.** The instance marks the room as in alarm. Its own status page (plain HTML, no external files, works with the main server down) shows the room in red at the top. The main server's 3D map mirrors it in red when the main server is up (task 11c of the server plan).
3. **First call: the nearest person.** Among staff on duty, online (heartbeat under 30 s) and not already handling a Critical alarm, sort the nurses and doctors by walking distance from their last room to the alarm room. Page the nearest one at once.
4. **Second call: the most needed role.** For each alarm type a table says which role matters most (patient call: nurse; staff emergency call: doctor). If the first person paged is not that role, page the nearest person of that role at the same time.
5. **Acknowledge or escalate.** Each paged person must tap "I'm going" within **30 s**. Otherwise the next nearest candidate of that role is paged. After **90 s** with nobody accepting, everyone on duty on that floor is paged and the nurse station sounds a continuous alarm. This continues until someone accepts.
6. **Arrive and resolve.** "Arrived" and "Resolved" are two more taps. An accepted alarm with no "Arrived" after 3 minutes is escalated again. Only "Resolved" turns the room back to normal.
7. **Clear the way (optional, best effort).** If the main server is up, the emergency service asks it to pause robots in the corridors leading to that room. It never waits for an answer.

Every step is written to its own journal (the same sealed design as the main server's, with its own key). The journal records who was paged, when, and when they responded. It holds no patient health content.

## Failing loudly

- **Self-test every minute:** a test alarm from a virtual device, through the whole pipeline, to a virtual pager. If it fails, the nurse station shows **"ALARM SYSTEM FAULT"**. A silent failure of the alarm path is the worst outcome, so it must never be silent.
- **Silent devices:** every alarm button sends a heartbeat every 60 s. A button silent for 3 minutes shows "button offline" on its room.
- **Instance down:** each instance watches the other. If B is down, A shows "backup alarm server down" at the nurse station, and the reverse.
- **Overload:** the service sheds everything that is not an alarm or an acknowledgement. Per-device rate limits stop a stuck button from drowning the others.

## Interfaces

| Who | Talks to | How |
| --- | --- | --- |
| Alarm button / patient tablet | A and B | HTTP POST of a signed alarm, retried until confirmed; heartbeat every 60 s |
| Staff app | A and B | WebSocket for pages; HTTP for accept, arrived, resolved; room heartbeat every 10 s |
| Nurse station display | A and B | Its own status page, loud sound |
| Main server | A and B | Pushes roster and room-distance updates; reads the status stream (read-only mirror for the 3D map); receives "pause robots near room X" (best effort) |

## How we will test it

- **Chaos tests:** kill the main server → alarm still paged. Kill instance A → B pages. Drop 30 % of network packets → alarm paged within 10 s. Unplug the database file → paging still works from memory, and a fault is raised.
- **Correctness:** duplicate press gives one alarm; forged signature is rejected; replayed alarm is rejected; nearest-person order is correct on the seed map; escalation timings with a fake clock.
- **Measure, don't guess:** time from press to first page on the demo hardware, written down with the machine used.

## Open questions for the lead

1. **Who owns it.** The backend engineer already has a large job. Options: the backend engineer owns both and the server plan is cut (drop tasks 19 and 20 of the server plan), or the robot engineer takes it.
2. **The bedside device.** A button on the patient tablet (no new hardware), or a physical button (an ESP32 board with a button and a light, a few francs, more reliable than an app). Recommendation: a physical button for the demo, as it shows the "independent" idea.
3. **Second machine.** Is there a second computer for instance B during the demo?
4. **Role table.** Confirm "patient call → nurse first; staff emergency call → doctor".
