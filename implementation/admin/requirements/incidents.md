# Incidents on the map

Status: **on the server**, with gaps. `GET /incidents`, `POST /incidents/{id}/ack`, `POST /incidents/{id}/close` and `incident.updated` exist and the console uses them as documented in `docs/openapi.yaml` and `docs/ws_messages.md`. What the console needs on top:

## 1. The emergency mirror (Task 11c, still `todo!`)

`src/emergency_mirror.rs` is a stub, and `IncidentSeverity::colour` too. Until the mirror runs, **patient alarms never reach the map**, and nothing says so. The console is ready for both incidents it raises:

- `emergency_alarm` (`code: {"code": "emergency_alarm", "level": "call" | "urgent" | "emergency"}`): a red room with a ringing tag on the map, a banner on every page, the alarm first in every list. No acknowledge or close button (the server answers 409; the console never sends it).
- `emergency_link_down`: a banner on every page, "Patient alarms may not show on this map. The emergency service itself keeps paging the staff."

Please also close the `emergency_alarm` incident when the emergency service resolves the alarm, and fill `acknowledged_by` with the label of whoever accepted it there: the banner then says who is on the way.

## 2. Answers of ack and close

The console accepts either the updated incident as the body (preferred) or an empty 200/204; on an empty body it reads `GET /incidents` again. Either way, also send `incident.updated` so the other consoles see it.

## 3. `place` is a place or room of the active plan

The console colours the room whose id is `place`, or the room around the place's point. A `place` that is on neither draws no room (the incident still shows in the lists). `floor` lets the console jump to the right floor when the incident is clicked.

## 4. Merge and severity

As the server already does: the same incident raised again while open increments `repeats` and moves `last_seen_at`; its severity can rise, never fall. The console shows "raised N times".

## Where the console does this

| What | File |
| --- | --- |
| Reader (code object, unknown codes kept as "other") | `src/lib/adapt.ts` (`toIncident`) |
| Words, advice, colours, "most serious" | `src/lib/incidents.ts` |
| Rooms tinted on the 3D map, critical ones pulse | `src/scene/IncidentLayer.tsx` |
| Panel next to the map, full page, banners, nav badge | `src/pages/live/IncidentsPanel.tsx`, `src/pages/Incidents.tsx`, `src/ui/Shell.tsx` |
| Demo board (same rules, alarms resolved by the "emergency service" after 45 s) | `src/mock/sim-incidents.ts` |
| Tests | `src/mock/incidents.test.ts` |
