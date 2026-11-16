/** A point on a floor plan, in metres: [x, y]. x grows east, y grows south (top-down view). */
export type Point = [number, number]

export type RobotState = 'idle' | 'busy' | 'paused' | 'fault' | 'estop'
/** What the panel shows. `offline` is never sent by the server: it is derived from a stale `lastSeen`. */
export type DisplayState = RobotState | 'offline'
export type RobotCommand = 'pause' | 'resume' | 'dock' | 'estop'

export interface RobotPosition {
  x: number
  y: number
  /** Radians. 0 points east (+x), positive turns towards south (+y). */
  heading: number
  floor: number
}

export interface Robot {
  id: string
  name: string
  role: string
  simulated: boolean
  position: RobotPosition
  battery: number
  state: RobotState
  holding: string | null
  micOpen: boolean
  taskId: string | null
  lastSeen: string
  /** Inside a deaf zone it has received: the microphone stays closed there. */
  inDeafZone: boolean
  /** On its way to the fleet's home place (emergency, dock command or low battery). */
  goingHome: boolean
  /** One word for the robot's state of mind, shown as an emoji on the map. */
  mood: RobotMood
}

export type RobotMood = 'happy' | 'busy' | 'deaf' | 'charging' | 'home' | 'alarm' | 'stopped' | 'offline'

/** `GET /fleet/home`: where robots go in an emergency, on "dock" and to recharge. */
export interface FleetHome {
  placeId: string | null
  label: string | null
  floor: number | null
}

export interface MapFloor {
  id: number
  label: string
  outline: Point[]
}

export type RoomKind = 'room' | 'corridor' | 'elevator' | 'care' | 'storage' | 'therapy' | 'pool' | 'lounge'

export interface MapRoom {
  id: string
  floor: number
  label: string
  kind: RoomKind
  polygon: Point[]
  labelAt?: Point
}

/** An open polyline. A door is simply a gap between two walls. */
export interface MapWall {
  floor: number
  points: Point[]
}

export type PlaceKind = 'room' | 'shelf' | 'dock' | 'point'

export interface MapPlace {
  id: string
  label: string
  floor: number
  x: number
  y: number
  kind: PlaceKind
}

export type PropKind = 'bed' | 'counter' | 'desk' | 'shelf' | 'cabinet' | 'sofa' | 'armchair' | 'table' | 'plant' | 'dock' | 'pool' | 'bench' | 'crate' | 'mat' | 'bars' | 'nightstand' | 'door'

/** Optional furniture. Anything with `solid` blocks the route planner. */
export interface MapProp {
  id: string
  floor: number
  kind: PropKind
  x: number
  y: number
  width: number
  depth: number
  solid: boolean
}

export interface ClinicMap {
  /** Which stored plan this is, and its version. Absent from the in-browser demo. */
  clinicId?: string
  version?: number
  floors: MapFloor[]
  rooms: MapRoom[]
  walls: MapWall[]
  places: MapPlace[]
  props: MapProp[]
}

export type TaskState = 'requested' | 'assigned' | 'en_route' | 'delivered' | 'failed' | 'resumed' | 'cancelled'
export type TaskKind = 'fetch' | 'restock_round' | 'go_to' | 'follow'

export interface TaskHistoryEntry {
  at: string
  actor: string
  label: string
}

export interface Task {
  id: string
  kind: TaskKind
  item: string | null
  fromPlace: string | null
  toPlace: string
  state: TaskState
  robotId: string | null
  requestedBy: string
  createdAt: string
  updatedAt: string
  reason: string | null
  history: TaskHistoryEntry[]
  /** Follow tasks: the pseudonym of the staff tablet being followed ("Dr. A"). */
  targetLabel?: string | null
}

/** What the console asks the server to give one robot. */
export interface NewTask {
  /** Absent: the server's optimizer picks the robot (go_to, fetch). */
  robotId?: string
  kind: 'go_to' | 'fetch' | 'follow'
  toPlace?: string
  item?: string
  fromPlace?: string
  /** Follow: the staff tablet's id. */
  targetDevice?: string
}

export interface InventoryItem {
  id: string
  label: string
  place: string
  count: number
  lowAt: number
  lastRobotCount: number | null
  lastRobotCountAt: string | null
  updatedAt: string
}

export type DeliveryStatus = 'received' | 'pending' | 'failed'

export interface ZoneDelivery {
  robotId: string
  status: DeliveryStatus
}

export type ZoneKind = 'deaf' | 'restricted'

export interface Zone {
  id: string
  name: string
  floor: number
  kind: ZoneKind
  polygon: Point[]
  deliveries: ZoneDelivery[]
}

export type RoundResult = 'success' | 'partial' | 'failed' | 'never'

export interface RoundShelfCount {
  place: string
  item: string
  expected: number
  counted: number
}

export interface Schedule {
  id: string
  label: string
  enabled: boolean
  /** Local time, HH:MM. */
  time: string
  robotId: string | null
  lastRun: string | null
  lastResult: RoundResult
  lastCounts: RoundShelfCount[]
}

export type AuditResult = 'ok' | 'refused' | 'failed'

export interface AuditEntry {
  id: string
  at: string
  actor: string
  action: string
  target: string
  result: AuditResult
  detail: string | null
}

export interface Session {
  token: string
  operator: string
  role: 'admin'
}

export type AlertLevel = 'info' | 'warning' | 'critical'

export type LiveMessage =
  | { type: 'robot.updated'; robot: Robot }
  | { type: 'task.updated'; task: Task }
  | { type: 'inventory.updated'; item: InventoryItem }
  | { type: 'zone.updated'; zone: Zone }
  | { type: 'zone.deleted'; zoneId: string }
  | { type: 'schedule.updated'; schedule: Schedule }
  | { type: 'alert'; level: AlertLevel; message: string }
  /** A clinic plan changed. When `active`, the building on screen is out of date: fetch the map again. */
  | { type: 'map.updated'; clinicId: string; version: number; active: boolean }
  /** The panel fell behind the server's live stream: reload everything. */
  | { type: 'resync' }
  /** The server switched between normal and emergency operation. */
  | { type: 'mode.updated'; mode: SystemMode }
  /** A tablet was registered, assigned, freed, or changed battery or link. */
  | { type: 'device.updated'; tablet: Tablet }
  /** An incident was opened, raised again, acknowledged or closed. */
  | { type: 'incident.updated'; incident: Incident }
  /** The server's attack detection did something (or an admin blocked someone). */
  | { type: 'security.alert'; alert: SecurityAlert }
  /** Tablet positions (the robots part of `positions.delta` is not read yet). */
  | { type: 'positions.delta'; tablets: TabletFix[]; removedTablets: string[] }

/**
 * Where robots spent their time on one floor (`GET /stats/heat`): `columns × rows` counts, row-major,
 * row 0 on the north edge, cell (0, 0) with its north-west corner at `origin`.
 */
export interface HeatGrid {
  floor: number
  cellM: number
  origin: Point
  columns: number
  rows: number
  counts: number[]
}

/** The server's estimate of what is left of a task's path (`GET /tasks/{id}/route`). The robot plans its own way. */
export interface TaskRoute {
  floor: number
  points: Point[]
  lengthM: number
  estimate: boolean
}

/**
 * How the main server runs. In `emergency`, it refuses every request that is not needed in an
 * emergency (503 `emergency_mode`) and sends the robots out of the way. Patient alarms never go
 * through this server (separate emergency service), so this mode never touches them.
 */
export interface SystemMode {
  mode: 'normal' | 'emergency'
  /** When the current mode started. */
  since: string | null
  /** Who switched it (pseudonymous operator label). */
  by: string | null
  reason: string | null
}

/** Staff tablets go with a person; bedside tablets stay with a bed. */
export type TabletKind = 'staff' | 'bedside'

/**
 * One tablet. What it says about a person is limited on purpose (`requirements/tablets.md`): the
 * label is a pseudonym ("Dr. A", "Ward 2 nurse") or a bed ("Bed 12"), never a patient name, and
 * there is no health field at all.
 */
export interface Tablet {
  id: string
  kind: TabletKind
  /** Owner label (staff) or bed label (bedside). Empty when the tablet is free. */
  label: string
  /** Staff only: the person's speciality or role ("cardiology", "physio"). */
  speciality: string | null
  /** 0 to 100, or null when the server does not say. */
  battery: number | null
  online: boolean
  /** False: nobody uses it, it is free to hand out. */
  assigned: boolean
  /** The room it is in (staff), its bed's room (bedside), or its dock (free). */
  place: string | null
  /** Where to draw it. Null: drawn at its place. */
  position: { x: number; y: number; floor: number } | null
  /** Metres; null when the position is exact or the room anchor. */
  uncertainty: number | null
  lastSeen: string | null
}

/** One tablet's position from the live stream. */
export interface TabletFix {
  id: string
  label: string | null
  place: string | null
  position: { x: number; y: number; floor: number } | null
  uncertainty: number | null
}

/** What `POST /devices/{id}/assign` sends: a person for a staff tablet, a bed for a bedside one. */
export interface TabletAssignment {
  kind: TabletKind
  label: string
  speciality: string | null
  place: string | null
}

export type RoomPatientStatus = 'admitted' | 'discharged'

export interface RoomPatient {
  id: string
  firstName: string
  medicalRecordRef: string
  status: RoomPatientStatus
  admittedAt: string
}

export interface RoomDevice {
  id: string
  label: string
  roomId: string
  online: boolean
  paired: boolean
  pairingCode: string | null
}

export interface ClinicRoom {
  id: string
  label: string
  wing: string
  floor: number
  patient: RoomPatient | null
  device: RoomDevice | null
}

/** `GET /monitor/summary`: the server's health in one look. Null fields: the server does not say. */
export interface ServerSummary {
  startedAt: string | null
  uptimeS: number
  version: string | null
  robotsConnected: number
  robotsTotal: number
  /** Open `/ws` connections of apps (consoles, tablets). */
  appClients: number
  journalOk: boolean | null
  databaseOk: boolean | null
  /** Over the last 10 s. */
  requestsPerS: number
  rejectedPerS: number
  p95Ms: number | null
  blockedClients: number
}

/** Why a request was refused. */
export type RejectReason = 'unauthorized' | 'forbidden' | 'rate_limited' | 'blocked' | 'emergency_mode' | 'invalid'

/** One second of traffic. */
export interface TrafficPoint {
  at: string
  accepted: number
  rejected: number
}

/** `GET /monitor/traffic?window_s=300`. */
export interface Traffic {
  stepS: number
  points: TrafficPoint[]
  /** Refusals over the whole window, by reason. */
  rejectedBy: Record<RejectReason, number>
  p95Ms: number | null
}

export type ClientStatus = 'ok' | 'limited' | 'blocked'

/** `GET /monitor/clients`: one client address and what it did over the last 5 minutes. */
export interface ClientStat {
  ip: string
  /** What the server knows it is: a known network ("Ward Wi-Fi"), a robot, the console. Never a person. */
  label: string | null
  requestsPerS: number
  requests: number
  rejected: number
  loginFailures: number
  status: ClientStatus
  /** Why it is limited or blocked. */
  reason: string | null
}

/** `GET /security/blocks`: one blocked address or range. */
export interface BlockRule {
  id: string
  /** An IP address or a CIDR range. */
  target: string
  reason: string
  source: 'manual' | 'auto'
  createdAt: string
  /** Null: until removed by hand. */
  expiresAt: string | null
  by: string | null
  /** Requests refused because of it. */
  hits: number
}

export type SecurityAlertKind = 'rate_limited' | 'auto_blocked' | 'login_burst' | 'blocked' | 'unblocked'

export interface SecurityAlert {
  at: string
  kind: SecurityAlertKind
  ip: string
  message: string
}

/** `GET /stats/service?hours=24`: how the service is doing, in counts only, never a person. */
export interface ServiceStats {
  hours: number
  requests: number
  delivered: number
  failed: number
  /** Request to delivery, seconds. */
  medianWaitS: number | null
  p90WaitS: number | null
  byItem: Array<{ label: string; count: number }>
  byPlace: Array<{ place: string; count: number }>
  bedsideOnline: number
  bedsideTotal: number
}

export type IncidentSeverity = 'info' | 'warning' | 'critical'

export type IncidentCode =
  | 'robot_fault' | 'robot_offline' | 'robot_estop'
  | 'tablet_offline' | 'tablet_battery_low' | 'tablet_app_error'
  | 'zone_not_delivered' | 'journal_degraded'
  | 'emergency_alarm' | 'emergency_link_down'
  /** A code this console does not know yet: shown with its raw name. */
  | 'other'

/**
 * Something wrong on the map (`GET /incidents`, `incident.updated`). It names a room and a robot
 * or tablet, never a person. Patient alarms (`emergency_alarm`) are mirrored from the separate
 * emergency service: they are acknowledged there, never here.
 */
export interface Incident {
  id: string
  code: IncidentCode
  /** The server's code when it is one this console does not know. */
  rawCode: string
  /** The fault (robot), the app error (tablet) or the alarm level (`call`, `urgent`, `emergency`). */
  detail: string | null
  severity: IncidentSeverity
  subject: { kind: 'robot' | 'tablet'; id: string } | null
  place: string | null
  floor: number | null
  openedAt: string
  lastSeenAt: string
  /** Times raised again while open. */
  repeats: number
  acknowledgedBy: string | null
  closedAt: string | null
}

export type ConnectionState = 'live' | 'connecting' | 'offline'

/** The robot answers a request. It may refuse, and then it says why. */
export interface CommandOutcome {
  accepted: boolean
  reason: string | null
}

export interface AuditQuery {
  from?: string
  to?: string
  actor?: string
}

/** One stored clinic plan in `GET /clinics`. */
export interface ClinicSummary {
  id: string
  name: string
  version: number
  active: boolean
  updatedAt: string
}

/** A clinic plan as the server stores it. Unknown fields are kept so a save sends them back. */
export interface ClinicPlan {
  name: string
  floors: Array<{ id: number; label: string; outline: Point[] }>
  rooms: Array<{ id: string; floor: number; label: string; kind: RoomKind; polygon: Point[]; label_at?: Point | null }>
  walls: Array<{ id: string; floor: number; points: Point[] }>
  places: Array<{ id: string; label: string; floor: number; x: number; y: number; kind: PlaceKind }>
  props: MapProp[]
  [extra: string]: unknown
}

/** The modifications of a base plan (`/clinics/{id}/overlay`): items added or replaced, and ids removed. */
export interface PlanOverlay {
  base_version: number
  upsert: { floors: ClinicPlan['floors']; rooms: ClinicPlan['rooms']; walls: ClinicPlan['walls']; places: ClinicPlan['places']; props: MapProp[] }
  remove: { floors: number[]; rooms: string[]; walls: string[]; places: string[]; props: string[] }
}
