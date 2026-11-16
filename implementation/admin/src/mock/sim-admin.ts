/** What the admin can do in the demo: robot commands, zones, stock, schedule. */
import type { CommandOutcome, InventoryItem, RobotCommand, Schedule, SystemMode, Task, Zone } from '../types'
import { driveTo, stopDriving } from './sim-motion'
import type { SimRobot, SimState } from './sim-state'
import { alert, audit, copySchedule, copyZone, emit, emitItem, iso, simRobot, touchTask } from './sim-state'
import { raiseForRobot } from './sim-incidents'
import { closeTask, finishRound, isOpen, releaseRobot } from './sim-tasks'

const ESTOP_LATCHED = 'Emergency stop is latched. Release the red button on the robot first.'

function refuse(state: SimState, actor: string, entry: SimRobot, name: RobotCommand, reason: string): CommandOutcome {
  audit(state, actor, `Command ${name}`, entry.robot.id, 'refused', reason)
  return { accepted: false, reason }
}

function accept(state: SimState, actor: string, entry: SimRobot, name: RobotCommand): CommandOutcome {
  audit(state, actor, `Command ${name}`, entry.robot.id, 'ok', null)
  return { accepted: true, reason: null }
}

function openTaskOf(state: SimState, entry: SimRobot): Task | undefined {
  return state.tasks.find((task) => task.id === entry.robot.taskId && isOpen(task))
}

/**
 * Takes a task away from its robot. A delivery goes back to the queue for another robot; a night
 * round cannot be handed over, so it ends as failed and the schedule says so.
 */
function releaseTask(state: SimState, entry: SimRobot, task: Task, actor: string, why: string): void {
  if (task.kind === 'restock_round') {
    closeTask(state, task, 'failed', actor, why)
    const schedule = state.schedules.find((candidate) => candidate.robotId === entry.robot.id)
    if (schedule) finishRound(state, schedule, 'failed', schedule.lastCounts)
    entry.roundQueue = []
    return
  }
  task.state = 'requested'
  task.robotId = null
  touchTask(state, task, actor, `Released: ${why}`)
}

/** An item the robot carried goes back on its shelf (a person puts it back). */
function returnHeldItem(state: SimState, entry: SimRobot): void {
  const item = entry.robot.holding ? state.inventory.find((candidate) => candidate.label === entry.robot.holding) : undefined
  if (item) { item.count += 1; emitItem(state, item) }
  entry.robot.holding = null
}

/** The panel asks, the robot decides. Throws when the robot cannot be reached at all. */
export function command(state: SimState, robotId: string, name: RobotCommand, actor: string): CommandOutcome {
  const entry = simRobot(state, robotId)
  if (!entry) throw new Error(`Robot ${robotId} is not known to the server.`)
  if (state.clock < entry.linkDownUntil) {
    audit(state, actor, `Command ${name}`, robotId, 'failed', 'No link to the robot')
    throw new Error(`${robotId} did not answer: no link to the robot.`)
  }
  const { robot } = entry

  if (name === 'estop') {
    const task = openTaskOf(state, entry)
    if (task?.kind === 'restock_round') releaseTask(state, entry, task, actor, 'Emergency stop.')
    else if (task) closeTask(state, task, 'failed', actor, 'Emergency stop.')
    stopDriving(entry)
    entry.phase = 'idle'
    entry.wait = 0
    robot.state = 'estop'
    robot.micOpen = false
    alert(state, 'critical', `${robotId} stopped by emergency stop.`)
    raiseForRobot(state, robotId, 'robot_estop', 'critical')
    return accept(state, actor, entry, name)
  }
  if (robot.state === 'estop') return refuse(state, actor, entry, name, ESTOP_LATCHED)
  if (robot.state === 'fault') return refuse(state, actor, entry, name, 'A fault is active. A person must check the robot.')

  if (name === 'pause') {
    if (robot.state === 'paused') return refuse(state, actor, entry, name, 'The robot is already paused.')
    if (robot.state !== 'busy') return refuse(state, actor, entry, name, 'Nothing to pause: the robot is idle.')
    robot.state = 'paused'
    entry.speed = 0
    return accept(state, actor, entry, name)
  }
  if (name === 'resume') {
    if (robot.state !== 'paused') return refuse(state, actor, entry, name, 'The robot is not paused.')
    robot.state = 'busy'
    return accept(state, actor, entry, name)
  }
  // dock
  if (robot.holding) return refuse(state, actor, entry, name, `It carries a ${robot.holding.toLowerCase()}. It must deliver it or hand it to a staff member first.`)
  if (entry.phase === 'charging') return refuse(state, actor, entry, name, 'The robot is already on its dock.')
  const task = openTaskOf(state, entry)
  if (task) releaseTask(state, entry, task, actor, `${robotId} was sent to its dock`)
  releaseRobot(entry)
  if (!driveTo(state, entry, entry.home)) return refuse(state, actor, entry, name, 'No free way to the dock.')
  robot.state = 'busy'
  entry.phase = 'to_dock'
  return accept(state, actor, entry, name)
}

export function cancelTask(state: SimState, taskId: string, actor: string): Task {
  const task = state.tasks.find((candidate) => candidate.id === taskId)
  if (!task) throw new Error(`Task ${taskId} does not exist.`)
  if (!isOpen(task)) throw new Error(`Task ${taskId} is already closed.`)
  const entry = task.robotId ? simRobot(state, task.robotId) : undefined
  closeTask(state, task, 'cancelled', actor, 'Cancelled from the admin panel.')
  if (!entry) return task
  const carriesItem = Boolean(entry.robot.holding) && Boolean(task.fromPlace)
  if (carriesItem && task.fromPlace && driveTo(state, entry, task.fromPlace)) {
    entry.phase = 'to_return'
    entry.wait = 0
    if (entry.robot.state === 'paused') entry.robot.state = 'busy'
    return task
  }
  entry.robot.holding = null
  releaseRobot(entry)
  return task
}

export function adjustInventory(state: SimState, itemId: string, delta: number, actor: string): InventoryItem {
  const item = state.inventory.find((candidate) => candidate.id === itemId)
  if (!item) throw new Error(`Item ${itemId} does not exist.`)
  if (!Number.isInteger(delta) || delta === 0) throw new Error('The change must be a whole number other than zero.')
  const before = item.count
  item.count = Math.max(0, item.count + delta)
  emitItem(state, item)
  audit(state, actor, 'Stock adjusted', item.label, 'ok', `${before} to ${item.count}`)
  return item
}

const DELIVERY_MIN_SECONDS = 0.8
const DELIVERY_SPREAD_SECONDS = 1.8

export function putZone(state: SimState, zone: Zone, actor: string): Zone {
  if (zone.polygon.length < 3) throw new Error('A zone needs at least three points.')
  if (!zone.name.trim()) throw new Error('A zone needs a name.')
  if (!state.map.floors.some((floor) => floor.id === zone.floor)) throw new Error('Unknown floor.')
  const saved: Zone = { ...copyZone(zone), name: zone.name.trim(), deliveries: state.robots.map((entry) => ({ robotId: entry.robot.id, status: 'pending' })) }
  const exists = state.zones.some((candidate) => candidate.id === saved.id)
  state.zones = exists ? state.zones.map((candidate) => candidate.id === saved.id ? saved : candidate) : [...state.zones, saved]
  state.deliveries = [
    ...state.deliveries.filter((delivery) => delivery.zoneId !== saved.id),
    ...state.robots.map((entry) => ({ zoneId: saved.id, robotId: entry.robot.id, at: state.clock + (DELIVERY_MIN_SECONDS + state.random() * DELIVERY_SPREAD_SECONDS) * 1000 })),
  ]
  audit(state, actor, exists ? 'Zone changed' : 'Zone created', saved.name, 'ok', saved.kind === 'deaf' ? 'Deaf zone' : 'Restricted zone (advisory only)')
  emit(state, { type: 'zone.updated', zone: copyZone(saved) })
  return saved
}

export function deleteZone(state: SimState, zoneId: string, actor: string): void {
  const zone = state.zones.find((candidate) => candidate.id === zoneId)
  if (!zone) throw new Error('This zone does not exist any more.')
  state.zones = state.zones.filter((candidate) => candidate.id !== zoneId)
  state.deliveries = state.deliveries.filter((delivery) => delivery.zoneId !== zoneId)
  audit(state, actor, 'Zone deleted', zone.name, 'ok', null)
  emit(state, { type: 'zone.deleted', zoneId })
}

/** A robot confirms a zone a moment after it was saved, unless its link is down. */
export function deliverZones(state: SimState): void {
  const due = state.deliveries.filter((delivery) => delivery.at <= state.clock)
  if (!due.length) return
  const kept = state.deliveries.filter((delivery) => delivery.at > state.clock)
  for (const delivery of due) {
    const entry = simRobot(state, delivery.robotId)
    const zone = state.zones.find((candidate) => candidate.id === delivery.zoneId)
    if (!entry || !zone) continue
    if (state.clock < entry.linkDownUntil) { kept.push({ ...delivery, at: entry.linkDownUntil + 500 }); continue }
    zone.deliveries = zone.deliveries.map((candidate) => candidate.robotId === delivery.robotId ? { ...candidate, status: 'received' } : candidate)
    emit(state, { type: 'zone.updated', zone: copyZone(zone) })
  }
  state.deliveries = kept
}

export function putSchedule(state: SimState, next: Schedule, actor: string): Schedule {
  const schedule = state.schedules.find((candidate) => candidate.id === next.id)
  if (!schedule) throw new Error('This schedule does not exist.')
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(next.time)) throw new Error('The time must look like 02:30.')
  schedule.enabled = next.enabled
  schedule.time = next.time
  audit(state, actor, 'Schedule changed', schedule.label, 'ok', `${schedule.enabled ? 'On' : 'Off'} at ${schedule.time}`)
  emit(state, { type: 'schedule.updated', schedule: copySchedule(schedule) })
  return schedule
}

/** Demo only: someone releases the red button on the robot. */
export function releaseEstop(state: SimState, robotId: string): void {
  const entry = simRobot(state, robotId)
  if (!entry || entry.robot.state !== 'estop') return
  entry.robot.state = 'idle'
  entry.robot.holding = null
  releaseRobot(entry)
  audit(state, 'staff', 'Emergency stop released on the robot', robotId, 'ok', null)
  alert(state, 'info', `${robotId}: emergency stop released on the robot.`)
}

const FAULT_SECONDS = 25

/** Demo only: a wheel gets stuck for a while. */
export function injectFault(state: SimState, robotId: string): void {
  const entry = simRobot(state, robotId)
  if (!entry || entry.robot.state === 'estop') return
  const task = openTaskOf(state, entry)
  if (task) releaseTask(state, entry, task, robotId, 'the robot reported a fault')
  returnHeldItem(state, entry)
  releaseRobot(entry)
  entry.robot.state = 'fault'
  entry.faultUntil = state.clock + FAULT_SECONDS * 1000
  audit(state, robotId, 'Fault reported', robotId, 'failed', 'Wheel blocked')
  alert(state, 'critical', `${robotId} reports a fault: wheel blocked.`)
  raiseForRobot(state, robotId, 'robot_fault', 'warning', 'motor')
}

/** Demo only: one robot loses its Wi-Fi for a while. It keeps working, the panel stops hearing it. */
export function dropLink(state: SimState, robotId: string, seconds: number): void {
  const entry = simRobot(state, robotId)
  if (!entry) return
  entry.linkDownUntil = state.clock + seconds * 1000
  raiseForRobot(state, robotId, 'robot_offline', 'warning')
}

export const EMERGENCY_REFUSAL = 'The clinic is in emergency mode: only emergency actions are accepted. Leave emergency mode first.'

/** The server's 503 `emergency_mode`, as the demo throws it. */
export function requireNormal(state: SimState, what: string): void {
  if (state.mode.mode !== 'emergency') return
  audit(state, 'server', what, '', 'refused', 'Emergency mode')
  throw new Error(EMERGENCY_REFUSAL)
}

/**
 * Emergency mode on: every robot clears the way. A free robot drives to its dock (its task goes
 * back to the queue); a robot that cannot (it carries an item, or has no way) pauses where it is.
 * Stopped and faulty robots are left alone. Off: the robots it paused resume.
 */
export function setMode(state: SimState, mode: SystemMode['mode'], reason: string, actor: string): SystemMode {
  if (state.mode.mode === mode) return { ...state.mode }
  state.mode = { mode, since: iso(state), by: actor, reason: reason || null }
  audit(state, actor, mode === 'emergency' ? 'Emergency mode on' : 'Emergency mode off', 'server', 'ok', reason || null)
  if (mode === 'emergency') {
    state.pausedByEmergency = []
    for (const entry of state.robots) {
      const { robot } = entry
      if (robot.state === 'estop' || robot.state === 'fault' || entry.phase === 'charging') continue
      if (entry.phase === 'to_dock' || (robot.state === 'idle' && entry.phase === 'idle' && !robot.taskId)) {
        if (entry.phase === 'idle' && driveTo(state, entry, entry.home)) { robot.state = 'busy'; entry.phase = 'to_dock' }
        continue
      }
      const docked = command(state, robot.id, 'dock', 'emergency mode')
      if (docked.accepted) continue
      if (robot.state === 'busy' && command(state, robot.id, 'pause', 'emergency mode').accepted) state.pausedByEmergency.push(robot.id)
    }
    alert(state, 'critical', 'Emergency mode is on: only emergency actions are accepted. Robots are going to their docks.')
  } else {
    for (const robotId of state.pausedByEmergency) command(state, robotId, 'resume', 'emergency mode')
    state.pausedByEmergency = []
    alert(state, 'info', 'Emergency mode is off: the clinic is back to normal operation.')
  }
  emit(state, { type: 'mode.updated', mode: { ...state.mode } })
  return { ...state.mode }
}
