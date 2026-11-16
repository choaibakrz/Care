# Job 2: Robot engineer

**Mission:** make the existing Python robot program take tasks from the server, do them safely, and report back. Most of the robot already exists. Your job is the connection, the missions, and the microphone rule.

You own `briques/b16_lien_serveur/` (new) and glue code in `b04_oreilles_voix`, `b05_yeux` and `clinique`. Optionally `implementation/sim/`. Add a `b16` row to the roles table in `AGENTS.md`.

**Never edit** `b01_prise/prise.py`, `b01_prise/ticket.py` or `b07_gardien/` without the security reviewer. Your whole job is to stay on the safe side of that line.

Read first: [architecture.md](architecture.md) (contracts C1, C2), `AGENTS.md`, `docs/projet/REGLES_DES_AGENTS.md`, `briques/b01_prise/PRISE.md`, `briques/clinique/GUIDE.md`, `briques/clinique/coursier.py`, `briques/clinique/taches.py`, `briques/clinique/repartiteur.py`, `briques/b04_oreilles_voix/GUIDE.md`, `NON_TESTE.md`.

## What exists and works (do not rebuild)

- `python3 lancer.py` runs the whole chain on the fake robot. `python3 lancer.py repetition` plays a seven-scene rehearsal.
- `Coursier` already runs a fetch: reserve → room, under the gardien, with a safe stop. `TableauDesTaches` already holds task states. `Repartiteur` already picks a robot.
- The event bus and black box (`commun/bus.py`, `b12_boite_noire`) record everything.
- Voice in, voice out, interpreter mode, "I'm not sure" (b08), human help (b11) all exist.

## What you build

### P0. The server link: `briques/b16_lien_serveur/`
- [ ] WebSocket client for `/ws/robot/{robot_id}` (contract C2). Send `hello`, then `robot.state` every second.
- [ ] Turn `task.assign` into a task in the existing `TableauDesTaches`, then let `Coursier.faire()` run it. Map states both ways (`delivered` ↔ `livrée`, and so on, table in architecture.md).
- [ ] Forward bus events as `task.event`. A failure or a handover to a human carries a `reason`.
- [ ] **Survive a dropped connection.** Finish or safely stop the task, buffer events, resync on reconnect. The robot must not move *more* because the link is down.
- [ ] Reject malformed or unknown messages without crashing. Log them to the black box.
- [ ] New event types go in `commun/evenements.py` (`TYPES` is a closed list). Add tests: `python3 lancer.py tests briques/b16_lien_serveur`.
- [ ] A **mock server** (small FastAPI script) so you can test before job 3 is ready. Replace it with the real one at M1.

### P0. Commands from the server
- [ ] `estop` → the prise's existing emergency stop (needs no ticket, by design). Check it still requires a human to re-arm.
- [ ] `pause`, `resume`, `dock`, `shutdown` → ordinary actions that go through brain/gardien/prise like any other. Never a shortcut to the adapter.
- [ ] Add a test: a server command can never produce a robot movement that did not pass the gardien.

### P1. Use the detector (with job 1)
- [ ] Turn on the `service_http` plug-in in `reglages.yaml` once job 1 ships it. Start with job 1's mock.
- [ ] **Confirm before grabbing:** the existing `Coursier._constater` checks the world. Make it use "item seen at the shelf" from the vision result. If the item is not seen, report `failed` with reason `item_not_found` and offer a human handover. Do not guess.
- [ ] Map detector labels to the world's object names and to `classes.yaml`. A new tool must not need a code change.

### P1. Night restocking round
- [ ] A `restock_round` task: a list of shelves. At each, look, count what the detector sees, send `inventory.seen {place, [{item, count}]}`. The server decides what to reorder.
- [ ] Handle: shelf not reachable, battery too low (go dock, resume later), item "unknown" (record the count as uncertain, never as zero).
- [ ] Reuse `clinique/etageres.py` and `docs/projet/EPREUVE_ETAGERES.md` as the starting point for how shelves are described.

### P1. Deaf zones (microphone closed)
- [ ] Keep the latest `zones.update` list locally. On every position update, check if the robot is inside a `deaf` zone. If so, close the mic and stop listening (hook into `b04_oreilles_voix/conversation.py` and `ecoute.py`).
- [ ] **Unknown position counts as deaf.** The mic stays closed until the robot knows where it is.
- [ ] Report `mic_open` in `robot.state`. Add `micro_ferme` / `micro_ouvert` events to the black box.
- [ ] Works with no connection, from the last zones received.
- [ ] Say so in the UI: a visible "microphone off" indicator on the robot's screen (`b13_ecran`).
- [ ] A test with the fake robot walking in and out of a zone. Because it changes what the robot hears, ask the security reviewer to read it.

### P2. Extras
- [ ] **Staff-approved summaries and comfort mode** (full version): reuse `clinique/resume.py` and its source checks. The summary only goes out after a nurse approves it in the app.
- [ ] **Webots world** (`implementation/sim/`): a small ward with a wheeled robot, a camera, shelves with the clinic tools. Value: realistic frames for job 1 and a nicer demo. Cost: a new simulator to learn. Do it only after M2. Write a small `b03_adaptateurs` adapter if it drives the robot, and run the conformance test (`b01_prise/conformite.py`).
- [ ] Real robot: `briques/b03_adaptateurs/` already has Go2 and ROS 2 drafts (`docs/projet/PREMIERE_HEURE.md`). Anything on a real robot goes through `docs/projet/PROTOCOLE_ESSAIS_REELS.md` and stays marked **not tested** until it is.

## Interfaces

| You give | To | When |
| --- | --- | --- |
| Robot position, battery, state, `mic_open` (C2 up) | Job 3, then jobs 4 and 5 | M1 |
| Camera frames from the simulation | Job 1 | as early as possible |
| Real robot's place names with coordinates | Jobs 3 and 5 (for the map) | M1 |

| You need | From | When |
| --- | --- | --- |
| `ws_messages.md` and a server to connect to | Job 3 | M0 |
| C1 mock, then the real detector | Job 1 | M0, M2 |

## Don't

- Don't give the server, the apps or the model service a path to the adapters.
- Don't send images or audio to the server. Counts and names only.
- Don't mark anything "tested" that you did not run. The existing docs are strict about this; keep to it.

## Done when

- A task created through the server runs on the fake robot with the gardien in the loop, and every state change reaches the server.
- Unplugging the connection mid-task leaves the robot safe, and plugging it back resyncs.
- In a deaf zone, no audio is captured (checked by a test), and the black box shows it.
- `python3 lancer.py tests` passes (the whole suite, as before), with internet cut for the program.
