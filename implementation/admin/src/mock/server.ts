/**
 * The demo server: it wraps the simulated clinic so the panel can use it exactly like the
 * real one (same calls, same live messages, a short answer delay, and a way to cut the line).
 */
import type { Backend, Enrolment, LiveSocket } from '../lib/backend'
import { localHeatGrid, recordHeat } from '../lib/heat'
import { serviceFromTasks } from '../lib/service'
import type { FleetHome, AuditEntry, AuditQuery, BlockRule, ClientStat, ClinicMap, ClinicRoom, Incident, CommandOutcome, HeatGrid, InventoryItem, LiveMessage, Robot, RobotCommand, Schedule, ServerSummary, ServiceStats, Session, SystemMode, Tablet, TabletAssignment, Task, TaskRoute, Traffic, Zone, RoomDevice, RoomPatient } from '../types'
import { estimateRoute } from './route'
import { ClinicSim } from './sim'
import { TrafficSim } from './traffic'
import { admitDemoPatient, createDemoDevice, dischargeDemoRoom, getRoomControl } from './room-control'

const TICK_MS = 100
const ROBOT_PERIOD_MS = 500
const MAX_STEP_SECONDS = 0.5
const WARMUP_SECONDS = 420
const LATENCY_MS = 140

let sim: ClinicSim | null = null
let traffic: TrafficSim | null = null
let operator = 'admin'
let outage = false
let ticker: number | undefined
const sockets = new Set<MockSocket>()
/** Demo of `/fleet/home`: undefined until read, then the first dock of the map. */
let homePlace: string | null | undefined

function fleetHome(): FleetHome {
  const places = world().getMap().places
  if (homePlace === undefined) homePlace = places.find((place) => place.kind === 'dock')?.id ?? null
  const place = places.find((entry) => entry.id === homePlace)
  return place ? { placeId: place.id, label: place.label, floor: place.floor } : { placeId: null, label: null, floor: null }
}

function world(): ClinicSim {
  if (!sim) {
    sim = new ClinicSim({ warmupSeconds: WARMUP_SECONDS, onWarmupSample: (robot) => recordHeat(robot.position.floor, robot.position.x, robot.position.y) })
    startTicking()
  }
  return sim
}

function network(): TrafficSim {
  traffic ??= new TrafficSim(Date.now())
  return traffic
}

function startTicking(): void {
  if (ticker !== undefined) return
  let last = performance.now()
  let sinceRobots = 0
  ticker = window.setInterval(() => {
    const now = performance.now()
    const elapsed = now - last
    last = now
    if (!sim) return
    sim.step(Math.min(MAX_STEP_SECONDS, elapsed / 1000))
    sinceRobots += elapsed
    const withRobots = sinceRobots >= ROBOT_PERIOD_MS
    if (withRobots) sinceRobots = 0
    const messages = sim.drain(withRobots)
    messages.push(...network().step(elapsed / 1000, Date.now(), sim.getMode().mode === 'emergency'))
    // The demo's own heat count: the robots keep moving even while the line is cut.
    for (const message of messages) if (message.type === 'robot.updated') recordHeat(message.robot.position.floor, message.robot.position.x, message.robot.position.y)
    // While the line is cut the messages are lost, as they would be: the panel resyncs on reconnect.
    if (outage) return
    for (const socket of sockets) socket.deliver(messages)
  }, TICK_MS)
}

class MockSocket implements LiveSocket {
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  private open = false
  private readonly timer: number

  constructor() {
    world()
    this.timer = window.setTimeout(() => {
      if (outage) { this.onclose?.(new CloseEvent('close')); return }
      this.open = true
      sockets.add(this)
      this.onopen?.(new Event('open'))
    }, 250)
  }

  send(): void {
    // The demo server needs no token.
  }

  deliver(messages: LiveMessage[]): void {
    if (!this.open) return
    for (const message of messages) this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(message) }))
  }

  drop(): void {
    if (!this.open) return
    this.open = false
    sockets.delete(this)
    this.onclose?.(new CloseEvent('close'))
  }

  close(): void {
    window.clearTimeout(this.timer)
    this.open = false
    sockets.delete(this)
  }
}

function answer<T>(produce: () => T): Promise<T> {
  return new Promise((resolve, reject) => {
    window.setTimeout(() => {
      if (outage) { reject(new Error('No connection to the server.')); return }
      try { resolve(produce()) } catch (reason) { reject(reason instanceof Error ? reason : new Error('The demo server failed.')) }
    }, LATENCY_MS)
  })
}

export const mockBackend: Backend = {
  login(username: string, password: string): Promise<Session> {
    return answer(() => {
      if (!username.trim() || !password.trim()) throw new Error('Enter a username and a password.')
      operator = username.trim()
      world()
      return { token: 'demo-token', operator, role: 'admin' }
    })
  },
  loginWithToken(accessToken: string): Promise<Session> {
    return answer(() => {
      if (!accessToken.trim()) throw new Error('The sign-in link is invalid.')
      operator = 'demo admin'
      world()
      return { token: 'demo-token', operator, role: 'admin' }
    })
  },
  enrol(enrolment: Enrolment): Promise<string> {
    return answer(() => {
      if (!enrolment.code.trim() || !enrolment.username.trim() || !enrolment.password || !enrolment.pseudonym.trim()) throw new Error('Fill in every field.')
      return `${enrolment.pseudonym.trim()} #demo00`
    })
  },
  getRooms: (): Promise<ClinicRoom[]> => answer(() => getRoomControl()),
  admitPatient: (_token: string, input: { firstName: string; medicalRecordRef: string; roomId: string }): Promise<{ patient: RoomPatient; roomId: string }> => answer(() => admitDemoPatient(input)),
  createRoomDevice: (_token: string, input: { roomId: string; label: string }): Promise<{ device: RoomDevice; pairingCode: string }> => answer(() => createDemoDevice(input)),
  dischargeRoom: (_token: string, roomId: string): Promise<void> => answer(() => dischargeDemoRoom(roomId)),
  getMap: (): Promise<ClinicMap> => answer(() => world().getMap()),
  getRobots: (): Promise<Robot[]> => answer(() => world().getRobots()),
  getTasks: (): Promise<Task[]> => answer(() => world().getTasks()),
  getInventory: (): Promise<InventoryItem[]> => answer(() => world().getInventory()),
  getZones: (): Promise<Zone[]> => answer(() => world().getZones()),
  getSchedules: (): Promise<Schedule[]> => answer(() => world().getSchedules()),
  getAudit: (_token: string, query: AuditQuery): Promise<AuditEntry[]> => answer(() => world().getAudit(query)),
  getHeat: (_token: string, floor: number): Promise<HeatGrid> => answer(() => localHeatGrid(floor)),
  getTaskRoute: (_token: string, taskId: string): Promise<TaskRoute | null> => answer(() => {
    const clinic = world()
    const task = clinic.getTasks().find((entry) => entry.id === taskId)
    if (!task) return null
    return estimateRoute(clinic.getMap(), task, clinic.getRobots().find((robot) => robot.id === task.robotId))
  }),
  sendCommand: (_token: string, robotId: string, name: RobotCommand): Promise<CommandOutcome> => answer(() => world().command(robotId, name, operator)),
  cancelTask: (_token: string, taskId: string): Promise<Task> => answer(() => world().cancelTask(taskId, operator)),
  createTask: (): Promise<Task> => answer(() => { throw new Error('Giving a robot a task is not available in demo mode. Connect the console to the server.') }),
  adjustInventory: (_token: string, itemId: string, delta: number): Promise<InventoryItem> => answer(() => { world().requireNormal('Adjust stock'); return world().adjustInventory(itemId, delta, operator) }),
  putZone: (_token: string, zone: Zone): Promise<Zone> => answer(() => { world().requireNormal('Save zone'); return world().putZone(zone, operator) }),
  deleteZone: (_token: string, zoneId: string): Promise<void> => answer(() => { world().requireNormal('Delete zone'); world().deleteZone(zoneId, operator) }),
  putSchedule: (_token: string, schedule: Schedule): Promise<Schedule> => answer(() => { world().requireNormal('Change schedule'); return world().putSchedule(schedule, operator) }),
  runRoundNow: (_token: string, scheduleId: string): Promise<string | null> => answer(() => { world().requireNormal('Start round'); return world().runRoundNow(scheduleId, operator) }),
  getMode: (): Promise<SystemMode | null> => answer(() => world().getMode()),
  getIncidents: (_token: string, includeClosed: boolean): Promise<Incident[]> => answer(() => world().getIncidents(includeClosed)),
  acknowledgeIncident: (_token: string, incidentId: string): Promise<Incident | null> => answer(() => world().acknowledgeIncident(incidentId, operator)),
  closeIncident: (_token: string, incidentId: string): Promise<Incident | null> => answer(() => world().closeIncident(incidentId, operator)),
  getSummary: (): Promise<ServerSummary | null> => answer(() => {
    const robots = world().getRobots()
    const fresh = robots.filter((robot) => Date.now() - Date.parse(robot.lastSeen) < 5000).length
    return network().getSummary(fresh, robots.length)
  }),
  getTraffic: (_token: string, windowS: number): Promise<Traffic | null> => answer(() => network().getTraffic(windowS)),
  getClients: (): Promise<ClientStat[] | null> => answer(() => network().getClients()),
  getBlocks: (): Promise<BlockRule[] | null> => answer(() => network().getBlocks()),
  addBlock: (_token: string, block: { target: string; reason: string; expiresInS: number | null }): Promise<BlockRule> => answer(() => network().addBlock(block.target, block.reason, block.expiresInS, operator)),
  removeBlock: (_token: string, blockId: string): Promise<void> => answer(() => network().removeBlock(blockId)),
  getServiceStats: (_token: string, hours: number): Promise<ServiceStats | null> => answer(() => serviceFromTasks(world().getTasks(), world().getTablets(), Date.now(), hours)),
  getTablets: (): Promise<{ tablets: Tablet[]; managed: boolean }> => answer(() => ({ tablets: world().getTablets(), managed: true })),
  disconnectTablet: (_token: string, tabletId: string): Promise<Tablet> => answer(() => world().disconnectTablet(tabletId, operator)),
  assignTablet: (_token: string, tabletId: string, assignment: TabletAssignment): Promise<Tablet> => answer(() => world().assignTablet(tabletId, assignment, operator)),
  setMode: (_token: string, mode: SystemMode['mode'], reason: string): Promise<SystemMode> => answer(() => world().setMode(mode, reason, operator)),
  teleportRobot: (_token: string, robotId: string, at: { x: number; y: number; floor: number }): Promise<Robot> => answer(() => world().teleport(robotId, at.x, at.y, at.floor)),
  getFleetHome: (): Promise<FleetHome> => answer(() => fleetHome()),
  setFleetHome: (_token: string, placeId: string | null): Promise<FleetHome> => answer(() => {
    if (placeId !== null && !world().getMap().places.some((place) => place.id === placeId)) throw new Error('This place is not on the map.')
    homePlace = placeId
    return fleetHome()
  }),
  openSocket: (): LiveSocket => new MockSocket(),
}

/** Builds the demo clinic (its warm-up takes a moment): called while the login screen waits. */
export function warmUpDemo(): void {
  world()
}

/** Controls that exist only in the demo, to show what the panel does when things go wrong. */
export const demoControls = {
  isOutage: (): boolean => outage,
  /** Cuts or restores the line between the panel and the server. The robots keep working. */
  setOutage(next: boolean): void {
    outage = next
    if (next) for (const socket of [...sockets]) socket.drop()
  },
  releaseEstop: (robotId: string): void => world().releaseEstop(robotId),
  injectFault: (robotId: string): void => world().injectFault(robotId),
  dropLink: (robotId: string, seconds: number): void => world().dropLink(robotId, seconds),
  /** A flood from one address and a credential-stuffing run from another (documentation addresses). */
  simulateAttack: (): void => network().simulateAttack(),
  /** A patient alarm from the emergency service, mirrored on the map; it resolves by itself after 45 s. */
  patientAlarm: (placeId: string, level: 'call' | 'urgent' | 'emergency'): void => { world().playPatientAlarm(placeId, level) },
  reset(): void {
    sim = null
    traffic = null
    homePlace = undefined
    outage = false
    world()
  },
}
