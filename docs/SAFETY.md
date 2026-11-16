# Safety model

This is a prototype built during a hackathon. **It is not certified for anything**, and it has been driven on exactly
one real device (a robot hand, with only objects in reach). This document explains what the code enforces, what it
does not, and how to check both.

## Three locks

1. **The guardian** (`briques/b07_gardien`) checks every proposed action against the rules and issues a ticket:
   signed (HMAC-SHA-256 with a key that exists only in the running process), bound to **one** robot,
   **single-use**, valid for **5 seconds**.
2. **The socket** (`briques/b01_prise`) refuses any action without a valid ticket. It works on a **copy** of the action,
   so changing the request after the guardian approved it has no effect. It re-checks the robot's card and the global
   ceilings, whatever the card says.
3. **The robot adapter** stops on its own if it stops receiving a sign of life (watchdog).

## Limits applied by default

| Limit | Default | Where |
|---|---|---|
| Speed | 0.3 m/s | `reglages.exemple.yaml` → `securite` |
| Force | 15 N | same |
| Longest relative move in one order | 5 m | same |
| Robot answer time-out | 2 s | same |
| Watchdog | 0.6 s | same |

The smaller of the robot card's limit and the global ceiling wins. A card value of `0` means "not read in the
manufacturer's documentation": the action is refused. Numbers are never guessed.

## Rules of the guardian

Rules are data (`briques/b07_gardien/regles.yaml`), each with the sentence a person can read. Among them:

- **Distance to people.** The robot stays one metre from people when it moves, grasps, puts down or replays a gesture.
  **If the guardian does not know where people are, a human decides.**
- **Fragile objects and pouring** always go through a human first.
- **Named places can be closed** (stairs, a kitchen during service), and the robot stays inside the hall.
- **Maximum speed, force and load** per robot.

Possible outcomes: allowed (ticket), a human is asked (`b11_main_humaine`: the robot "raises its hand" and waits),
or refused with a reason given in the person's language.

## Stop

- `arreter` (stop) is never refused. Its parameters are ignored and everything stops.
- The **emergency stop needs no ticket**. The socket then verifies that the robot has stopped, retries every 0.1 s for
  3 s, and tells the operator to use the **physical** button if the stop is not confirmed.
- After an emergency stop, a human must re-arm. A new stop during re-arming cancels the re-arming.
- If the socket loses track of a running action for more than one second, it triggers the emergency stop.
- Only one long action runs at a time; a second one is refused, a stop always passes.

Software stops are not a substitute for a physical one. The procedure for a real robot starts with "the physical stop
button has been found and tried" ([`BRANCHER_UN_ROBOT.md`](../BRANCHER_UN_ROBOT.md)).

## Driving a real robot is a deliberate act

- A real robot is refused unless its two-stage conformity test passed on **this** version of its files.
- Both stages are started by a human typing a random phrase shown on screen. An agent or a script must not do it.
- During the test suite, settings are forced to the fake robot and the hand's vendor kit path points to an empty
  folder (`conftest.py`), so running the tests cannot reach a device even on a computer configured for one.
- Demonstrations of care use a mannequin or an object only. The system gives no diagnosis and no health advice: health
  questions are passed to the care team.

## What the tests enforce

`tests_bout_en_bout/test_aucun_contournement.py` reads the source code and fails if:

- any robot command is called outside the socket;
- an adapter is constructed anywhere but in `commun/systeme.py`;
- anyone touches the private parts of the socket or the guardian;
- `getattr` is used with a computed name (a way to hide a call);
- anything but the guardian creates tickets;
- the system keeps a reference to the adapter after handing it to the socket;
- the brain knows about the socket or the guardian.

`tests_bout_en_bout/test_jamais_un_vrai_robot_pendant_les_essais.py` checks that tests always load the fake robot.

These are static checks plus behaviour tests on fake robots. **They prove that the rules hold in the code and on
simulated robots. They prove nothing about a physical robot.**

## Review practice

"The one who writes is not the one who verifies": the adapters of the robot head and of the robot hand were each read by a reviewer who had not written them, and who
tried to break it on the stand-in before any real test. The findings that were **not** fixed are written down in
[`NON_TESTE.md`](../NON_TESTE.md), for example: on the robot hand, a finger blocked before its target can be reported as
"arrived", so a "done" on screen does not prove the shape of the hand.

## What this does not cover

- No person detection is wired to the guardian: it cannot see whether someone is near. That is why it asks a human.
- Force is not measured on the robot hand (only a motor current): free "grip harder" requests are refused.
- Voice commands were not measured in a noisy room.
- The identity of a person at reception is not verified.
- Nothing has been reviewed by a safety engineer, a clinician or a lawyer.
