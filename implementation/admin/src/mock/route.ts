/**
 * The demo's answer to `GET /tasks/{id}/route`: the rest of a task's path, planned in the browser
 * on the demo clinic. Like the server's answer it is an estimate, from the robot (or the start
 * place when no robot has it yet) to the goal, on one floor.
 */
import { buildNavGrid, findPath } from '../lib/nav'
import type { NavGrid } from '../lib/nav'
import type { ClinicMap, Point, Robot, Task, TaskRoute } from '../types'

const grids = new WeakMap<ClinicMap, Map<number, NavGrid | null>>()

function gridFor(map: ClinicMap, floor: number): NavGrid | null {
  let byFloor = grids.get(map)
  if (!byFloor) { byFloor = new Map(); grids.set(map, byFloor) }
  if (!byFloor.has(floor)) byFloor.set(floor, buildNavGrid(map, floor))
  return byFloor.get(floor) ?? null
}

function leg(grid: NavGrid, from: Point, to: Point): Point[] {
  return findPath(grid, from, to) ?? [from, to]
}

function lengthOf(points: Point[]): number {
  let total = 0
  for (let index = 1; index < points.length; index++) total += Math.hypot(points[index][0] - points[index - 1][0], points[index][1] - points[index - 1][1])
  return total
}

export function estimateRoute(map: ClinicMap, task: Task, robot: Robot | undefined): TaskRoute | null {
  if (task.kind === 'restock_round') return null
  const target = map.places.find((place) => place.id === task.toPlace)
  if (!target) return null
  const source = map.places.find((place) => place.id === task.fromPlace)
  const grid = gridFor(map, target.floor)
  if (!grid) return null
  const goal: Point = [target.x, target.y]
  const sourcePoint: Point | null = source && source.floor === target.floor ? [source.x, source.y] : null
  const robotHere = robot && robot.position.floor === target.floor ? robot : undefined
  const points: Point[] = []
  if (robotHere) {
    const start: Point = [robotHere.position.x, robotHere.position.y]
    // Still on its way to pick the item up: through the shelf first.
    if (sourcePoint && !robotHere.holding) points.push(...leg(grid, start, sourcePoint), ...leg(grid, sourcePoint, goal).slice(1))
    else points.push(...leg(grid, start, goal))
  } else if (sourcePoint) {
    points.push(...leg(grid, sourcePoint, goal))
  } else {
    return null
  }
  return points.length >= 2 ? { floor: target.floor, points, lengthM: lengthOf(points), estimate: true } : null
}
