/**
 * The demo clinic: four fake robots that drive around walls and furniture, staff requests
 * that appear by themselves, a stock that goes down, zones the robots obey.
 *
 * It stands in for the server (job 3) and the robots (job 2) until they are ready.
 * Nothing here is sent anywhere: it all runs in the browser tab.
 */
import type { AuditEntry, AuditQuery, ClinicMap, CommandOutcome, InventoryItem, LiveMessage, Robot, RobotCommand, Incident, Schedule, SystemMode, Tablet, TabletAssignment, Task, Zone } from '../types'
import { fullCount, seedInventory, seedRobots, seedSchedules, seedZones } from './seed'
import * as admin from './sim-admin'
import { advance, driveTo, teleport, updateBattery, updateMicrophone } from './sim-motion'
import type { SimRobot, SimState } from './sim-state'
import { alert, buildGrids, copyRobot, copySchedule, copyTask, copyZone, defaultMap, emit, iso, mulberry32, placeById } from './sim-state'
import { acknowledge, close, listIncidents, playPatientAlarm, stepIncidents } from './sim-incidents'
import { assignTablet, copyTablet, disconnectTablet, seedTablets, stepTablets } from './sim-tablets'
import { createTask, dispatch, giveUp, onArrive, onWaitDone, spawnRequest, staffRefill, startRound } from './sim-tasks'

export interface SimOptions {
  seed?: number
  /** Simulated seconds played before the first real tick, so the demo does not start empty. */
  warmupSeconds?: number
  autoTasks?: boolean
  /** Called once per simulated second during warm-up, with each robot's position. */
  onWarmupSample?: (robot: Robot) => void
}

const WARMUP_STEP = 0.2
const REQUEST_MIN_SECONDS = 9
const REQUEST_SPREAD_SECONDS = 12
const LOW_BATTERY = 25
const FULL_BATTERY = 97
const IDLE_BEFORE_HOME_SECONDS = 6
const HOME_DISTANCE = 0.6

export class ClinicSim {
  private readonly state: SimState

  constructor(options: SimOptions = {}) {
    const warmup = options.warmupSeconds ?? 0
    const map = defaultMap()
    const state: SimState = {
      map,
      grids: buildGrids(map),
      clock: Date.now() - warmup * 1000,
      random: mulberry32(options.seed ?? 20261114),
      robots: [],
      tasks: [],
      inventory: [],
      zones: [],
      schedules: seedSchedules(),
      audit: [],
      outbox: [],
      deliveries: [],
      nextTaskIn: 2,
      taskCount: 100,
      auditCount: 0,
      lastScheduleKey: '',
      autoTasks: options.autoTasks ?? true,
      mode: { mode: 'normal', since: null, by: null, reason: null },
      pausedByEmergency: [],
      tablets: [],
      tabletReportIn: 10,
      incidents: [],
      incidentCount: 0,
      alarmEnds: [],
    }
    state.robots = seedRobots(state)
    state.inventory = seedInventory(state)
    state.zones = seedZones(state.robots.map((entry) => entry.robot.id))
    seedTablets(state)
    this.state = state
    this.warmUp(warmup, options.onWarmupSample)
  }

  private warmUp(seconds: number, onSample?: (robot: Robot) => void): void {
    const steps = Math.round(seconds / WARMUP_STEP)
    const stepsPerSecond = Math.round(1 / WARMUP_STEP)
    for (let index = 0; index < steps; index++) {
      this.step(WARMUP_STEP)
      if (onSample && index % stepsPerSecond === 0) this.state.robots.forEach((entry) => onSample(entry.robot))
    }
    this.state.clock = Date.now()
    this.state.outbox = []
  }

  /** Advances the world by `dt` seconds. */
  step(dt: number): void {
    const { state } = this
    state.clock += dt * 1000
    for (const entry of state.robots) this.stepRobot(entry, dt)
    stepTablets(state, dt)
    stepIncidents(state)
    // In emergency mode the server takes no new request and hands out no task.
    const emergency = state.mode.mode === 'emergency'
    if (state.autoTasks && !emergency) {
      state.nextTaskIn -= dt
      if (state.nextTaskIn <= 0) {
        spawnRequest(state)
        staffRefill(state, fullCount)
        state.nextTaskIn = REQUEST_MIN_SECONDS + state.random() * REQUEST_SPREAD_SECONDS
      }
    }
    if (!emergency) dispatch(state)
    admin.deliverZones(state)
    if (!emergency) this.checkSchedules()
  }

  private stepRobot(entry: SimRobot, dt: number): void {
    const { state } = this
    const { robot } = entry
    if (robot.state === 'fault' && state.clock >= entry.faultUntil) {
      robot.state = 'idle'
      alert(state, 'info', `${robot.id}: fault cleared, the robot is available again.`)
    }
    if (robot.state === 'busy' && entry.wait > 0) {
      entry.wait -= dt
      if (entry.wait <= 0) { entry.wait = 0; onWaitDone(state, entry) }
    }
    if (advance(state, entry, dt)) onArrive(entry)
    if (entry.stuck) { entry.stuck = false; giveUp(state, entry) }
    this.stepIdle(entry, dt)
    updateBattery(entry, dt)
    updateMicrophone(state, entry)
  }

  private stepIdle(entry: SimRobot, dt: number): void {
    const { state } = this
    const { robot } = entry
    if (entry.phase === 'charging' && robot.battery >= FULL_BATTERY) entry.phase = 'idle'
    if (entry.phase !== 'idle' || robot.state !== 'idle') return
    entry.idleFor += dt
    const home = placeById(state, entry.home)
    const awayFromHome = home ? Math.hypot(robot.position.x - home.x, robot.position.y - home.y) > HOME_DISTANCE : false
    const lowBattery = robot.battery < LOW_BATTERY
    if (!awayFromHome) { if (robot.battery < 90) entry.phase = 'charging'; return }
    if (!lowBattery && entry.idleFor < IDLE_BEFORE_HOME_SECONDS) return
    if (!driveTo(state, entry, entry.home)) return
    robot.state = 'busy'
    entry.phase = lowBattery ? 'to_dock' : 'to_home'
    if (lowBattery) alert(state, 'info', `${robot.id}: battery at ${Math.round(robot.battery)}%, going to its dock.`)
  }

  private checkSchedules(): void {
    const { state } = this
    const now = new Date(state.clock)
    const time = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
    const key = `${now.toDateString()} ${time}`
    if (key === state.lastScheduleKey) return
    state.lastScheduleKey = key
    for (const schedule of state.schedules) {
      if (schedule.enabled && schedule.time === time) startRound(state, schedule, 'schedule')
    }
  }

  /** Live messages produced since the last call, robot positions included. */
  drain(includeRobots: boolean): LiveMessage[] {
    const { state } = this
    if (includeRobots) {
      const at = iso(state)
      for (const entry of state.robots) {
        if (state.clock < entry.linkDownUntil) continue
        entry.robot.lastSeen = at
        emit(state, { type: 'robot.updated', robot: copyRobot(entry.robot) })
      }
    }
    const messages = state.outbox
    state.outbox = []
    return messages
  }

  getMap(): ClinicMap { return this.state.map }
  getRobots(): Robot[] { return this.state.robots.map((entry) => copyRobot(entry.robot)) }
  getTasks(): Task[] { return this.state.tasks.map(copyTask) }
  getInventory(): InventoryItem[] { return this.state.inventory.map((item) => ({ ...item })) }
  getZones(): Zone[] { return this.state.zones.map(copyZone) }
  getSchedules(): Schedule[] { return this.state.schedules.map(copySchedule) }

  getAudit(query: AuditQuery = {}): AuditEntry[] {
    const from = query.from ? Date.parse(query.from) : -Infinity
    const to = query.to ? Date.parse(query.to) : Infinity
    return this.state.audit
      .filter((entry) => !query.actor || entry.actor === query.actor)
      .filter((entry) => { const at = Date.parse(entry.at); return at >= from && at <= to })
      .map((entry) => ({ ...entry }))
  }

  command(robotId: string, name: RobotCommand, actor: string): CommandOutcome { return admin.command(this.state, robotId, name, actor) }
  cancelTask(taskId: string, actor: string): Task { return copyTask(admin.cancelTask(this.state, taskId, actor)) }
  adjustInventory(itemId: string, delta: number, actor: string): InventoryItem { return { ...admin.adjustInventory(this.state, itemId, delta, actor) } }
  putZone(zone: Zone, actor: string): Zone { return copyZone(admin.putZone(this.state, zone, actor)) }
  deleteZone(zoneId: string, actor: string): void { admin.deleteZone(this.state, zoneId, actor) }
  putSchedule(schedule: Schedule, actor: string): Schedule { return copySchedule(admin.putSchedule(this.state, schedule, actor)) }

  runRoundNow(scheduleId: string, actor: string): string | null {
    const schedule = this.state.schedules.find((candidate) => candidate.id === scheduleId)
    return schedule ? startRound(this.state, schedule, actor) : 'This schedule does not exist.'
  }

  getTablets(): Tablet[] { return this.state.tablets.map((entry) => copyTablet(entry.tablet)) }
  disconnectTablet(tabletId: string, actor: string): Tablet { return disconnectTablet(this.state, tabletId, actor) }
  assignTablet(tabletId: string, assignment: TabletAssignment, actor: string): Tablet { return assignTablet(this.state, tabletId, assignment, actor) }

  getIncidents(includeClosed: boolean): Incident[] { return listIncidents(this.state, includeClosed) }
  acknowledgeIncident(incidentId: string, actor: string): Incident { return acknowledge(this.state, incidentId, actor) }
  closeIncident(incidentId: string, actor: string): Incident { return close(this.state, incidentId, actor) }
  /** Demo control: a patient alarm, mirrored from the emergency service and resolved there. */
  playPatientAlarm(placeId: string, level: 'call' | 'urgent' | 'emergency'): Incident { return playPatientAlarm(this.state, placeId, level) }

  getMode(): SystemMode { return { ...this.state.mode } }
  setMode(mode: SystemMode['mode'], reason: string, actor: string): SystemMode { return admin.setMode(this.state, mode, reason, actor) }
  /** Throws the server's emergency-mode refusal when the clinic is in emergency mode. */
  requireNormal(what: string): void { admin.requireNormal(this.state, what) }

  /** Demo of the teleport route: throws the refusal, as the server answers 409 or 422. */
  teleport(robotId: string, x: number, y: number, floor: number): Robot {
    const entry = this.state.robots.find((candidate) => candidate.robot.id === robotId)
    if (!entry) throw new Error(`Robot ${robotId} is not known to the server.`)
    const refusal = teleport(this.state, entry, x, y, floor)
    if (refusal) throw new Error(refusal)
    const robot = copyRobot(entry.robot)
    emit(this.state, { type: 'robot.updated', robot })
    return robot
  }

  releaseEstop(robotId: string): void { admin.releaseEstop(this.state, robotId) }
  injectFault(robotId: string): void { admin.injectFault(this.state, robotId) }
  dropLink(robotId: string, seconds: number): void { admin.dropLink(this.state, robotId, seconds) }

  /** Test helper: a staff request, as the staff app would send it. */
  request(item: string, fromPlace: string, toPlace: string, requestedBy = 'nurse'): Task {
    return copyTask(createTask(this.state, 'fetch', item, fromPlace, toPlace, requestedBy))
  }
}
