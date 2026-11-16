/** How a fake robot drives: follow the planned path, turn smoothly, give way to another robot. */
import { angleDelta, pointInPolygon } from '../lib/geometry'
import { findPath } from '../lib/nav'
import type { Disc } from '../lib/nav'
import type { Point } from '../types'
import type { SimRobot, SimState } from './sim-state'
import { placeById } from './sim-state'
import { deriveMood } from '../lib/format'

const MAX_SPEED = 0.95
const ACCELERATION = 1.4
const TURN_RATE = 3.2
const ARRIVE_DISTANCE = 0.08
const BODY_GAP = 0.66
const AVOID_RADIUS = 0.85
const LOOK_AHEAD = 1.1
const PATIENCE_MOVING = 1.6
const PATIENCE_STILL = 0.5
const GIVE_UP_SECONDS = 12

export function isMoving(entry: SimRobot): boolean {
  return entry.robot.state === 'busy' && entry.path.length > 0 && entry.wait <= 0
}

/** Plans a path to a named place. Returns false when the place cannot be reached. */
export function driveTo(state: SimState, entry: SimRobot, placeId: string, avoid: Disc[] = []): boolean {
  const target = placeById(state, placeId)
  const grid = state.grids.get(entry.robot.position.floor)
  if (!target || !grid || target.floor !== entry.robot.position.floor) return false
  const path = findPath(grid, [entry.robot.position.x, entry.robot.position.y], [target.x, target.y], avoid)
  if (!path) return false
  entry.path = path
  entry.pathIndex = 1
  entry.blockedFor = 0
  return true
}

export function stopDriving(entry: SimRobot): void {
  entry.path = []
  entry.pathIndex = 0
  entry.speed = 0
  entry.blockedFor = 0
}

/** The other robot standing in the way within the next metre of the path, if any. */
function findBlocker(state: SimState, entry: SimRobot): SimRobot | undefined {
  const { position } = entry.robot
  const samples: Point[] = []
  let travelled = 0
  let previous: Point = [position.x, position.y]
  for (let index = entry.pathIndex; index < entry.path.length && travelled < LOOK_AHEAD; index++) {
    const next = entry.path[index]
    const length = Math.hypot(next[0] - previous[0], next[1] - previous[1])
    const steps = Math.max(1, Math.ceil(length / 0.2))
    for (let step = 1; step <= steps && travelled < LOOK_AHEAD; step++) {
      samples.push([previous[0] + ((next[0] - previous[0]) * step) / steps, previous[1] + ((next[1] - previous[1]) * step) / steps])
      travelled += length / steps
    }
    previous = next
  }
  return state.robots.find((other) => {
    if (other === entry || other.robot.position.floor !== position.floor) return false
    const here = Math.hypot(other.robot.position.x - position.x, other.robot.position.y - position.y)
    // Already overlapping (for example two robots released at the same spot): let them separate.
    if (here < 0.3) return false
    return samples.some((sample) => Math.hypot(other.robot.position.x - sample[0], other.robot.position.y - sample[1]) < BODY_GAP)
  })
}

function replanAround(state: SimState, entry: SimRobot, blocker: SimRobot): boolean {
  const grid = state.grids.get(entry.robot.position.floor)
  const goal = entry.path[entry.path.length - 1]
  if (!grid || !goal) return false
  const disc: Disc = { x: blocker.robot.position.x, y: blocker.robot.position.y, radius: AVOID_RADIUS }
  const path = findPath(grid, [entry.robot.position.x, entry.robot.position.y], goal, [disc])
  if (!path) return false
  entry.path = path
  entry.pathIndex = 1
  entry.blockedFor = 0
  return true
}

function remainingDistance(entry: SimRobot): number {
  let total = 0
  let previous: Point = [entry.robot.position.x, entry.robot.position.y]
  for (let index = entry.pathIndex; index < entry.path.length; index++) {
    total += Math.hypot(entry.path[index][0] - previous[0], entry.path[index][1] - previous[1])
    previous = entry.path[index]
  }
  return total
}

/** Moves one robot for `dt` seconds. Returns true when it has just reached the end of its path. */
export function advance(state: SimState, entry: SimRobot, dt: number): boolean {
  if (!isMoving(entry)) { entry.speed = 0; return false }
  const { position } = entry.robot

  const blocker = findBlocker(state, entry)
  if (blocker) {
    entry.speed = 0
    entry.blockedFor += dt
    const otherMoves = isMoving(blocker) && blocker.blockedFor === 0
    const hasPriority = entry.robot.id < blocker.robot.id
    const patience = otherMoves && hasPriority ? PATIENCE_MOVING : PATIENCE_STILL
    if (entry.blockedFor > patience) replanAround(state, entry, blocker)
    if (entry.blockedFor > GIVE_UP_SECONDS) { stopDriving(entry); entry.stuck = true }
    return false
  }
  entry.blockedFor = 0

  let budget = dt
  while (budget > 0 && entry.pathIndex < entry.path.length) {
    const target = entry.path[entry.pathIndex]
    const dx = target[0] - position.x
    const dy = target[1] - position.y
    const distance = Math.hypot(dx, dy)
    if (distance < ARRIVE_DISTANCE) { entry.pathIndex += 1; continue }

    const turn = angleDelta(position.heading, Math.atan2(dy, dx))
    const maxTurn = TURN_RATE * budget
    position.heading += Math.max(-maxTurn, Math.min(maxTurn, turn))
    // Turn on the spot when the next point is far off the nose, drive otherwise.
    const cruise = Math.abs(turn) < 0.5 ? MAX_SPEED : Math.abs(turn) < 1.1 ? MAX_SPEED * 0.3 : 0
    const brake = Math.sqrt(2 * ACCELERATION * remainingDistance(entry)) + 0.12
    const wanted = Math.min(cruise, brake)
    entry.speed = wanted > entry.speed ? Math.min(wanted, entry.speed + ACCELERATION * budget) : wanted

    const step = Math.min(distance, entry.speed * budget)
    if (step <= 1e-6) break
    position.x += (dx / distance) * step
    position.y += (dy / distance) * step
    budget -= step / Math.max(entry.speed, 1e-6)
  }

  if (entry.pathIndex >= entry.path.length) {
    stopDriving(entry)
    return true
  }
  return false
}

/**
 * The robot closes its own microphone inside a deaf zone it has received.
 * It is the robot that decides, so this keeps working when the link is down.
 */
export function updateMicrophone(state: SimState, entry: SimRobot): void {
  const { position, id } = entry.robot
  const insideDeafZone = state.zones.some((zone) => zone.kind === 'deaf'
    && zone.floor === position.floor
    && zone.deliveries.some((delivery) => delivery.robotId === id && delivery.status === 'received')
    && pointInPolygon(position.x, position.y, zone.polygon))
  entry.robot.micOpen = entry.robot.state !== 'estop' && !insideDeafZone
  entry.robot.inDeafZone = insideDeafZone
  entry.robot.goingHome = entry.phase === 'to_dock' || entry.phase === 'to_home'
  entry.robot.mood = entry.phase === 'charging' && entry.robot.state === 'idle' ? 'charging' : deriveMood(entry.robot.state, entry.robot.micOpen, entry.robot.goingHome)
}

/**
 * Demo of `POST /robots/{id}/teleport`: puts a simulated robot somewhere else by hand. Returns the
 * reason when refused (outside the floor, inside a restricted zone), or null when moved.
 */
export function teleport(state: SimState, entry: SimRobot, x: number, y: number, floor: number): string | null {
  if (!entry.robot.simulated) return 'Only simulated robots can be moved by hand.'
  const outline = state.map.floors.find((candidate) => candidate.id === floor)?.outline ?? []
  if (outline.length < 3 || !pointInPolygon(x, y, outline)) return 'That point is outside the floor.'
  if (state.zones.some((zone) => zone.kind === 'restricted' && zone.floor === floor && pointInPolygon(x, y, zone.polygon))) return 'That point is inside a restricted zone.'
  const goal = entry.path.length ? entry.path[entry.path.length - 1] : undefined
  const sameFloor = floor === entry.robot.position.floor
  stopDriving(entry)
  entry.robot.position = { ...entry.robot.position, x, y, floor }
  entry.idleFor = 0
  // A robot moved mid-errand plans again from the new spot; with no way there it gives up later.
  const grid = state.grids.get(floor)
  const path = goal && sameFloor && grid ? findPath(grid, [x, y], goal) : null
  if (path) { entry.path = path; entry.pathIndex = 1 } else if (goal) entry.stuck = true
  updateMicrophone(state, entry)
  return null
}

const DRAIN_MOVING = 0.06
const DRAIN_STILL = 0.012
const CHARGE_RATE = 1.6

export function updateBattery(entry: SimRobot, dt: number): void {
  const rate = entry.phase === 'charging' ? CHARGE_RATE : isMoving(entry) ? -DRAIN_MOVING : -DRAIN_STILL
  entry.robot.battery = Math.max(3, Math.min(100, entry.robot.battery + rate * dt))
}
