/**
 * The one door to the outside. The pages call `backend`, and never know whether the answer
 * comes from the real server (contract C3) or from the demo clinic that runs in the browser.
 */
import type { FleetHome, AuditEntry, AuditQuery, BlockRule, ClientStat, ClinicMap, ClinicRoom, Incident, CommandOutcome, HeatGrid, InventoryItem, NewTask, Robot, RobotCommand, Schedule, ServerSummary, ServiceStats, Session, SystemMode, Tablet, TabletAssignment, Task, TaskRoute, Traffic, Zone, RoomDevice, RoomPatient } from '../types'
import { config } from './config'

/** The small part of a WebSocket the live layer needs. The demo provides a fake one. */
export interface LiveSocket {
  onopen: ((event: Event) => void) | null
  onmessage: ((event: MessageEvent) => void) | null
  onclose: ((event: CloseEvent) => void) | null
  onerror: ((event: Event) => void) | null
  send(data: string): void
  close(): void
}

/** What a new user types with the one-time code an admin gave them (docs/accounts.md). */
export interface Enrolment {
  code: string
  username: string
  password: string
  /** Shown to others with the account tag ("Nurse 7 #3fa9c1"); never a real name. */
  pseudonym: string
}

export interface Backend {
  login(username: string, password: string): Promise<Session>
  /** Exchanges a Supabase access token received from a magic link for an admin session. */
  loginWithToken(accessToken: string): Promise<Session>
  /** Creates the account of an enrolment code. Resolves with the operator label (pseudonym and tag). */
  enrol(enrolment: Enrolment): Promise<string>
  getRooms(token: string): Promise<ClinicRoom[]>
  admitPatient(token: string, input: { firstName: string; medicalRecordRef: string; roomId: string }): Promise<{ patient: RoomPatient; roomId: string }>
  createRoomDevice(token: string, input: { roomId: string; label: string }): Promise<{ device: RoomDevice; pairingCode: string }>
  dischargeRoom(token: string, roomId: string): Promise<void>
  getMap(token: string): Promise<ClinicMap>
  getRobots(token: string): Promise<Robot[]>
  getTasks(token: string): Promise<Task[]>
  getInventory(token: string): Promise<InventoryItem[]>
  getZones(token: string): Promise<Zone[]>
  getSchedules(token: string): Promise<Schedule[]>
  getAudit(token: string, query: AuditQuery): Promise<AuditEntry[]>
  /** Where robots spent their time on one floor. */
  getHeat(token: string, floor: number): Promise<HeatGrid>
  /** The estimated rest of a task's path. Resolves with null when no route can be drawn. */
  getTaskRoute(token: string, taskId: string): Promise<TaskRoute | null>
  /**
   * Every tablet. `managed` is false when the server has no tablet registry yet: then only the live
   * ones are known, and they cannot be freed or assigned from here.
   */
  getTablets(token: string): Promise<{ tablets: Tablet[]; managed: boolean }>
  /** Ends the tablet's session and makes it free. */
  disconnectTablet(token: string, tabletId: string): Promise<Tablet>
  /** Gives a free tablet to a person (staff) or a bed (bedside). */
  assignTablet(token: string, tabletId: string, assignment: TabletAssignment): Promise<Tablet>
  /** Open incidents, or all of them (closed included). */
  getIncidents(token: string, includeClosed: boolean): Promise<Incident[]>
  /** Records that someone is on it. Refused for patient alarms (acknowledged in the emergency service). */
  acknowledgeIncident(token: string, incidentId: string): Promise<Incident | null>
  closeIncident(token: string, incidentId: string): Promise<Incident | null>
  // Monitor page. Each resolves with null when the server does not have that route yet.
  getSummary(token: string): Promise<ServerSummary | null>
  getTraffic(token: string, windowS: number): Promise<Traffic | null>
  getClients(token: string): Promise<ClientStat[] | null>
  getBlocks(token: string): Promise<BlockRule[] | null>
  /** Blocks an address or a range. `expiresInS` null: until removed by hand. */
  addBlock(token: string, block: { target: string; reason: string; expiresInS: number | null }): Promise<BlockRule>
  removeBlock(token: string, blockId: string): Promise<void>
  getServiceStats(token: string, hours: number): Promise<ServiceStats | null>
  /** How the server runs now. Resolves with null when the server has no emergency mode. */
  getMode(token: string): Promise<SystemMode | null>
  /** Switches between normal and emergency operation. */
  setMode(token: string, mode: SystemMode['mode'], reason: string): Promise<SystemMode>
  /** Resolves with the robot's answer (it may refuse). Rejects when nobody answered. */
  sendCommand(token: string, robotId: string, name: RobotCommand): Promise<CommandOutcome>
  cancelTask(token: string, taskId: string): Promise<Task>
  /** Gives one robot a task. Rejects with the server's message when it refuses. */
  createTask(token: string, task: NewTask): Promise<Task>
  adjustInventory(token: string, itemId: string, delta: number): Promise<InventoryItem>
  putZone(token: string, zone: Zone): Promise<Zone>
  deleteZone(token: string, zoneId: string): Promise<void>
  putSchedule(token: string, schedule: Schedule): Promise<Schedule>
  /** Resolves with null when the round started, or with the reason it did not. */
  runRoundNow(token: string, scheduleId: string): Promise<string | null>
  /** Moves a simulated robot by hand (drag on the map). Rejects with the server's reason when refused. */
  teleportRobot(token: string, robotId: string, at: { x: number; y: number; floor: number }): Promise<Robot>
  /** Where robots go in an emergency, on "dock" and to recharge. */
  getFleetHome(token: string): Promise<FleetHome>
  setFleetHome(token: string, placeId: string | null): Promise<FleetHome>
  openSocket(): LiveSocket
}

let loaded: Backend | null = null
let loading: Promise<Backend> | null = null

/**
 * Loads the real server client, or the demo clinic, and nothing else. Called once before the app
 * starts: in server mode the demo simulation is never downloaded.
 */
export function initBackend(): Promise<Backend> {
  loading ??= (config.useMock ? import('../mock/server').then((module) => module.mockBackend) : import('./http').then((module) => module.httpBackend))
    .then((chosen) => { loaded = chosen; return chosen })
  return loading
}

function current(): Backend {
  if (!loaded) throw new Error('The panel is still starting. Try again in a moment.')
  return loaded
}

/** The pages call this. Every call goes to the backend chosen by `initBackend`. */
export const backend: Backend = new Proxy({} as Backend, {
  get: (_target, name: string | symbol) => {
    const chosen = current() as unknown as Record<string | symbol, unknown>
    const value = chosen[name]
    return typeof value === 'function' ? (value as (...args: unknown[]) => unknown).bind(chosen) : value
  },
})
