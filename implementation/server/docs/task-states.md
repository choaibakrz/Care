# Task states

Source: `briques/clinique/taches.py` (`ETATS`, `changer_etat`), checked 2026-11-15.

## What the Python does

`ETATS = ("demandée", "attribuée", "en route", "livrée", "échouée", "reprise")`.
`changer_etat` only checks that the new state is in `ETATS` and who may change it (a robot or
staff; a simulated robot may not deliver). **It has no table of legal transitions**: every state
may follow every other, because each change is a new line in the ledger. So there is no
Python transition the plan failed to anticipate; the table below is the server's own, built on
the Python's order of states, and it is stricter on purpose (a delivered task cannot go back).

| English | Python |
|---|---|
| requested | demandée |
| assigned | attribuée |
| en_route | en route |
| delivered | livrée |
| failed | échouée |
| resumed | reprise |
| cancelled | (none, server only) |

## Allowed transitions (`TaskState::can_go_to`)

| From | To |
|---|---|
| requested | assigned, failed, cancelled |
| assigned | en_route, failed, cancelled |
| en_route | delivered, failed |
| failed | resumed |
| resumed | assigned, en_route, delivered, failed |
| delivered | nothing |
| cancelled | nothing |

Everything else is refused with `IllegalTransition`: "Task 't-1': going from 'delivered' to
'en_route' is not allowed." A move to `failed` needs a `FailureReason`
(`item_missing, path_blocked, robot_fault, robot_lost, handed_to_human, deadline_passed`),
otherwise `MissingFailureReason`. The reason is kept while the task is `failed` and cleared on
the next transition.

`is_terminal` is true for delivered, failed and cancelled (finished for the dispatcher and the
schedulers). `failed -> resumed` is the one exit from a terminal state: a human or the
dispatcher takes the task up again.

## Intentional differences from the Python

- `cancelled` exists only on the server. It is terminal and reachable only from `requested` and
  `assigned`: a task already `en_route` cannot be cancelled (the robot is carrying it; stop it
  with a command). Rule from `docs/progress.md`, Task A3.
- The Python lets any state follow any state; the server refuses the transitions above. The
  Python's checks on who may change a state (`changer_etat`) belong to the permission table
  (`Role::allows`) and the gardien, not to the state machine.
- `resumed` may go straight to `en_route` or `delivered` (a human or a robot that picks the
  task up mid-way), as the Python's free ordering permits.

## `is_terminal` versus `is_closed`

- `TaskState::is_terminal`: delivered, failed, cancelled. A failed task is "finished for now" but can be resumed, so do not use it to skip tasks a dispatcher must still look at.
- `TaskState::is_closed`: only delivered and cancelled. These can never change again; use this for "can never change again" checks.

## `constater`

The Python's `constater` (delivered -> delivered with `constate="oui"`) is modelled on the server as a separate confirmation flag or record, never as a state transition (ruling R19: the stricter table stands).
