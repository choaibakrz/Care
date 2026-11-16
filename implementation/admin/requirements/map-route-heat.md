# The 3D map: plan, route estimate, heat map

Status: **mostly on the server.** `GET /map`, `GET /tasks/{id}/route` and `GET /stats/heat` answer in `--mock` mode. Three things are missing or need care.

## 1. Publish `map.updated` (missing)

`server/src/services/clinics.rs` still has `todo!("T10b: … publish AppEvent::MapUpdated …")`, so saving or activating a plan sends nothing and the console keeps drawing the old building until a reload. The console is ready (tested with the exact documented message):

```json
{"type": "map.updated", "id": "00000000-0000-4000-8000-000000000001", "ts": "2026-11-15T08:00:00Z", "active": true, "clinic_id": "seed", "version": 2}
```

On `active: true` with a `(clinic_id, version)` different from the one drawn, the console fetches `GET /map` once and redraws. The same version twice does nothing, and `active: false` does nothing. `GET /map` must carry `clinic_id` and `version` (it does), or the console cannot skip duplicates.

`MapView::of` (`crates/locations/src/view.rs`) is also still `todo!` (T10b): outside `--mock`, `GET /map` fails, and the console shows "Some data did not load".

## 2. `resync`

On `resync` the console reloads everything (`/map`, `/robots`, `/tasks`, `/inventory`, `/zones`, `/schedules`, `/system/mode`, tablets) instead of reading the following `snapshot`. No change needed; documented so nobody removes `resync`.

## 3. `GET /tasks/{id}/route` (works; one request)

The console asks for the selected robot's task every 3 s, and again at once when the task state, the robot's load or its floor changes. It draws `points` only on `floor`, labelled "ESTIMATE", with a marker at the pick-up place while the robot does not hold the item yet. 404 (`not_found` or `no_route`) draws nothing.

Request: while Task 13b is not done, the mock answers a task **without a start place** with a fixed route on floor 2, whatever the robot's floor. Please answer 404 `no_route` instead (or plan from the robot's position): a route on the wrong floor is never drawn, but it costs a request every 3 s for nothing.

Semantics the console assumes, please keep: `points[0]` is the robot's current position when a robot has the task (the start place otherwise), the last point is the goal, `estimate` is always `true`.

## 4. `GET /stats/heat?floor=` (works)

Polled every 5 s for each floor on screen while the heat layer is on. The console uses `origin`, `cell_m`, `columns`, `rows` as sent (row 0 on the north edge); a grid whose `counts` length is not `columns × rows` is ignored. An unknown floor (422) is ignored.

## Where the console does this

| What | File |
| --- | --- |
| `map.updated`, `resync` | `src/state/store.ts` (`reloadMap`, `applyLive`) |
| Route and heat polling | `src/state/useMapData.ts` |
| Readers | `src/lib/adapt.ts` (`toMap`, `toRoute`, `toHeat`) |
| Tests | `src/lib/adapt.test.ts` |
