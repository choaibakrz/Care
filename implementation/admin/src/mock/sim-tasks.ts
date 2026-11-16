/** The life of a task in the demo: request, assignment, pick-up, delivery, and the night round. */
import type { InventoryItem, RoundShelfCount, Schedule, Task, TaskKind, TaskState } from '../types'
import { DESTINATIONS, REQUESTERS } from './seed'
import { driveTo, stopDriving } from './sim-motion'
import type { SimRobot, SimState } from './sim-state'
import { alert, audit, copySchedule, emit, emitItem, iso, pick, placeById, placeLabel, simRobot, touchTask } from './sim-state'

const OPEN_STATES: TaskState[] = ['requested', 'assigned', 'en_route']
const MAX_OPEN_TASKS = 4
const PICK_SECONDS = 2.6
const DROP_SECONDS = 2.2
const COUNT_SECONDS = 3
const START_SECONDS = 1
const FAIL_CHANCE = 0.06
const HANDOVER_CHANCE = 0.05
const MISCOUNT_CHANCE = 0.2
const MIN_BATTERY_FOR_TASK = 22

export function isOpen(task: Task): boolean {
  return OPEN_STATES.includes(task.state)
}

export function createTask(state: SimState, kind: TaskKind, item: string | null, fromPlace: string | null, toPlace: string, requestedBy: string): Task {
  state.taskCount += 1
  const at = iso(state)
  const task: Task = { id: `T-${state.taskCount}`, kind, item, fromPlace, toPlace, state: 'requested', robotId: null, requestedBy, createdAt: at, updatedAt: at, reason: null, history: [{ at, actor: requestedBy, label: 'Task requested' }] }
  state.tasks = [task, ...state.tasks].slice(0, 120)
  audit(state, requestedBy, 'Task created', task.id, 'ok', describe(state, task))
  emit(state, { type: 'task.updated', task: { ...task, history: [...task.history] } })
  return task
}

function describe(state: SimState, task: Task): string {
  if (task.kind === 'restock_round') return 'Night restock round'
  if (task.kind === 'go_to') return `Go to ${placeLabel(state, task.toPlace)}`
  return `${task.item ?? 'Item'}: ${placeLabel(state, task.fromPlace)} to ${placeLabel(state, task.toPlace)}`
}

/** A staff member asks for something, as the staff app would. */
export function spawnRequest(state: SimState): void {
  if (state.tasks.filter(isOpen).length >= MAX_OPEN_TASKS) return
  const available = state.inventory.filter((item) => item.count > 0 && DESTINATIONS[item.place])
  if (!available.length) return
  const item = pick(state, available)
  createTask(state, 'fetch', item.label, item.place, pick(state, DESTINATIONS[item.place]), pick(state, REQUESTERS))
}

function canTakeTask(entry: SimRobot, floor: number, clock: number): boolean {
  const { robot } = entry
  if (robot.position.floor !== floor || robot.battery < MIN_BATTERY_FOR_TASK || robot.taskId || clock < entry.linkDownUntil) return false
  if (entry.phase === 'idle' || entry.phase === 'to_home') return robot.state === 'idle' || robot.state === 'busy'
  return entry.phase === 'charging' && robot.battery > 40 && robot.state === 'idle'
}

/** The server gives each waiting task to the nearest free robot on the right floor. */
export function dispatch(state: SimState): void {
  const waiting = state.tasks.filter((task) => task.state === 'requested' && task.kind !== 'restock_round').reverse()
  for (const task of waiting) {
    const start = placeById(state, task.fromPlace ?? task.toPlace)
    if (!start) { closeTask(state, task, 'failed', 'server', 'Unknown place.'); continue }
    const candidates = state.robots.filter((entry) => canTakeTask(entry, start.floor, state.clock))
    if (!candidates.length) continue
    const nearest = candidates.reduce((best, entry) => distanceTo(entry, start.x, start.y) < distanceTo(best, start.x, start.y) ? entry : best)
    assign(state, task, nearest)
  }
}

function distanceTo(entry: SimRobot, x: number, y: number): number {
  return Math.hypot(entry.robot.position.x - x, entry.robot.position.y - y)
}

function assign(state: SimState, task: Task, entry: SimRobot): void {
  const firstStop = task.fromPlace ?? task.toPlace
  if (!driveTo(state, entry, firstStop)) { closeTask(state, task, 'failed', 'server', `No free way to ${placeLabel(state, firstStop)}.`); return }
  task.state = 'assigned'
  task.robotId = entry.robot.id
  entry.robot.taskId = task.id
  entry.robot.state = 'busy'
  entry.phase = task.fromPlace ? 'to_source' : 'to_dest'
  entry.wait = START_SECONDS
  entry.idleFor = 0
  touchTask(state, task, 'server', `Assigned to ${entry.robot.id}`)
}

function taskOf(state: SimState, entry: SimRobot): Task | undefined {
  return state.tasks.find((task) => task.id === entry.robot.taskId)
}

/** Ends a task and frees its robot. */
export function closeTask(state: SimState, task: Task, next: TaskState, actor: string, reason: string | null): void {
  task.state = next
  task.reason = reason
  const done = task.kind === 'restock_round' ? 'Round finished' : `Delivered at ${placeLabel(state, task.toPlace)}`
  const label = next === 'delivered' ? done : next === 'cancelled' ? 'Cancelled' : next === 'resumed' ? 'Handed over to a staff member' : 'Failed'
  touchTask(state, task, actor, reason && next !== 'delivered' ? `${label}: ${reason}` : label)
  audit(state, actor, `Task ${next}`, task.id, next === 'failed' ? 'failed' : 'ok', reason)
  const entry = task.robotId ? simRobot(state, task.robotId) : undefined
  if (entry && entry.robot.taskId === task.id) entry.robot.taskId = null
}

export function releaseRobot(entry: SimRobot): void {
  stopDriving(entry)
  entry.phase = 'idle'
  entry.wait = 0
  entry.idleFor = 0
  entry.robot.taskId = null
  if (entry.robot.state === 'busy' || entry.robot.state === 'paused') entry.robot.state = 'idle'
}

/** The robot reached the end of its path. */
export function onArrive(entry: SimRobot): void {
  if (entry.phase === 'to_source') { entry.phase = 'picking'; entry.wait = PICK_SECONDS; return }
  if (entry.phase === 'to_dest') { entry.phase = 'dropping'; entry.wait = DROP_SECONDS; return }
  if (entry.phase === 'to_return') { entry.phase = 'returning'; entry.wait = DROP_SECONDS; return }
  if (entry.phase === 'round_travel') { entry.phase = 'round_count'; entry.wait = COUNT_SECONDS; return }
  if (entry.phase === 'to_home' || entry.phase === 'to_dock') {
    entry.phase = entry.robot.battery < 90 ? 'charging' : 'idle'
    entry.robot.state = 'idle'
    entry.idleFor = 0
  }
}

/** The robot has finished standing still. */
export function onWaitDone(state: SimState, entry: SimRobot): void {
  const task = taskOf(state, entry)
  if (entry.phase === 'to_source' || entry.phase === 'to_dest') {
    if (task && task.state === 'assigned') { task.state = 'en_route'; touchTask(state, task, entry.robot.id, `On the way to ${placeLabel(state, task.fromPlace ?? task.toPlace)}`) }
    return
  }
  if (entry.phase === 'picking' && task) { pickUp(state, entry, task); return }
  if (entry.phase === 'dropping' && task) {
    entry.robot.holding = null
    closeTask(state, task, 'delivered', entry.robot.id, null)
    releaseRobot(entry)
    return
  }
  if (entry.phase === 'returning') {
    const item = state.inventory.find((candidate) => candidate.label === entry.robot.holding)
    if (item) { item.count += 1; emitItem(state, item) }
    entry.robot.holding = null
    releaseRobot(entry)
    return
  }
  if (entry.phase === 'round_count') countShelf(state, entry)
}

function pickUp(state: SimState, entry: SimRobot, task: Task): void {
  const item = state.inventory.find((candidate) => candidate.label === task.item && candidate.place === task.fromPlace)
  const draw = state.random()
  if (!item || item.count <= 0 || draw < FAIL_CHANCE) {
    closeTask(state, task, 'failed', entry.robot.id, `${task.item ?? 'Item'} not seen on ${placeLabel(state, task.fromPlace)} by the camera.`)
    alert(state, 'warning', `${task.id} failed: ${task.item ?? 'item'} not found on ${placeLabel(state, task.fromPlace)}.`)
    releaseRobot(entry)
    return
  }
  if (draw < FAIL_CHANCE + HANDOVER_CHANCE) {
    closeTask(state, task, 'resumed', entry.robot.id, 'The robot was not sure which item to take.')
    alert(state, 'info', `${task.id}: ${entry.robot.id} asked a staff member to take over.`)
    releaseRobot(entry)
    return
  }
  item.count -= 1
  emitItem(state, item)
  if (item.count === item.lowAt) alert(state, 'warning', `Low stock: ${item.label} (${item.count} left on ${placeLabel(state, item.place)}).`)
  entry.robot.holding = item.label
  if (!driveTo(state, entry, task.toPlace)) {
    closeTask(state, task, 'failed', entry.robot.id, `No free way to ${placeLabel(state, task.toPlace)}.`)
    entry.robot.holding = null
    item.count += 1
    emitItem(state, item)
    releaseRobot(entry)
    return
  }
  entry.phase = 'to_dest'
  touchTask(state, task, entry.robot.id, `Picked up at ${placeLabel(state, task.fromPlace)}`)
}

/** Starts the night round now. Returns the reason when it cannot start. */
export function startRound(state: SimState, schedule: Schedule, actor: string): string | null {
  const entry = schedule.robotId ? simRobot(state, schedule.robotId) : undefined
  const refusal = !entry ? 'No robot is set for the round.'
    : entry.robot.taskId ? `${entry.robot.id} is busy with ${entry.robot.taskId}.`
      : entry.robot.state !== 'idle' ? `${entry.robot.id} is not available (${entry.robot.state}).` : null
  if (!entry || refusal) {
    finishRound(state, schedule, 'failed', [])
    audit(state, actor, 'Night round not started', schedule.id, 'failed', refusal)
    alert(state, 'warning', `Night round not started: ${refusal}`)
    return refusal
  }
  const shelves = [...new Set(state.inventory.map((item) => item.place))].filter((placeId) => placeById(state, placeId)?.floor === entry.robot.position.floor)
  const task = createTask(state, 'restock_round', null, null, entry.home, actor)
  task.state = 'en_route'
  task.robotId = entry.robot.id
  touchTask(state, task, 'server', `Round started with ${entry.robot.id}`)
  entry.robot.taskId = task.id
  entry.robot.state = 'busy'
  entry.roundQueue = shelves
  entry.roundMismatches = 0
  schedule.lastCounts = []
  nextShelf(state, entry)
  return null
}

function nextShelf(state: SimState, entry: SimRobot): void {
  while (entry.roundQueue.length) {
    const shelf = entry.roundQueue[0]
    if (driveTo(state, entry, shelf)) { entry.phase = 'round_travel'; return }
    entry.roundQueue = entry.roundQueue.slice(1)
  }
  const task = taskOf(state, entry)
  const schedule = state.schedules.find((candidate) => candidate.robotId === entry.robot.id)
  if (schedule) finishRound(state, schedule, entry.roundMismatches ? 'partial' : 'success', schedule.lastCounts)
  if (task) closeTask(state, task, 'delivered', entry.robot.id, null)
  alert(state, entry.roundMismatches ? 'warning' : 'info', entry.roundMismatches ? `Night round done: ${entry.roundMismatches} count(s) differ from the stock list.` : 'Night round done: every count matches.')
  releaseRobot(entry)
}

function countShelf(state: SimState, entry: SimRobot): void {
  const shelf = entry.roundQueue[0]
  entry.roundQueue = entry.roundQueue.slice(1)
  const schedule = state.schedules.find((candidate) => candidate.robotId === entry.robot.id)
  const items = state.inventory.filter((item) => item.place === shelf)
  const counts: RoundShelfCount[] = items.map((item) => recordCount(state, entry, item))
  if (schedule) schedule.lastCounts = [...schedule.lastCounts, ...counts]
  const task = taskOf(state, entry)
  if (task) touchTask(state, task, entry.robot.id, `Counted ${placeLabel(state, shelf)}: ${items.length} item type(s)`)
  nextShelf(state, entry)
}

function recordCount(state: SimState, entry: SimRobot, item: InventoryItem): RoundShelfCount {
  const off = state.random() < MISCOUNT_CHANCE ? (state.random() < 0.5 ? -1 : 1) : 0
  const counted = Math.max(0, item.count + off)
  if (counted !== item.count) entry.roundMismatches += 1
  item.lastRobotCount = counted
  item.lastRobotCountAt = iso(state)
  emitItem(state, item)
  return { place: item.place, item: item.label, expected: item.count, counted }
}

export function finishRound(state: SimState, schedule: Schedule, result: Schedule['lastResult'], counts: RoundShelfCount[]): void {
  schedule.lastRun = iso(state)
  schedule.lastResult = result
  schedule.lastCounts = counts
  emit(state, { type: 'schedule.updated', schedule: copySchedule(schedule) })
}

/** A staff member refills the emptiest shelf item, so a long demo never runs dry. */
export function staffRefill(state: SimState, fullCount: (itemId: string) => number): void {
  const low = state.inventory.filter((item) => item.count <= item.lowAt)
  if (low.length < 3) return
  const item = low.reduce((worst, candidate) => candidate.count - candidate.lowAt < worst.count - worst.lowAt ? candidate : worst)
  const before = item.count
  item.count = fullCount(item.id)
  emitItem(state, item)
  audit(state, 'staff', 'Shelf refilled', item.label, 'ok', `${before} to ${item.count}`)
}

/** The robot could not get past another robot. The delivery goes back to the queue; the robot goes home. */
export function giveUp(state: SimState, entry: SimRobot): void {
  const task = taskOf(state, entry)
  alert(state, 'warning', `${entry.robot.id} is blocked by another robot and gives up its way.`)
  if (task && isOpen(task) && task.kind !== 'restock_round') {
    if (entry.robot.holding) {
      const item = state.inventory.find((candidate) => candidate.label === entry.robot.holding)
      if (item) { item.count += 1; emitItem(state, item) }
      entry.robot.holding = null
    }
    task.state = 'requested'
    task.robotId = null
    touchTask(state, task, entry.robot.id, 'Released: the way was blocked by another robot')
  }
  if (task?.kind === 'restock_round') nextShelf(state, entry)
  else releaseRobot(entry)
}
