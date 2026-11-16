/**
 * Turns what the server sends into the shapes the panel uses.
 *
 * The contract (architecture.md, C2 and C3) writes fields in snake_case: `mic_open`, `pos`,
 * `from_place`. `openapi.yaml` is not written yet, so these readers accept both spellings and
 * never trust a field to be there. A message that cannot be read is dropped, not shown wrong.
 */
import type { FleetHome, RobotMood, ClinicPlan, ClinicSummary, AlertLevel, AuditEntry, AuditResult, BlockRule, ClientStat, ClinicMap, Incident, IncidentCode, CommandOutcome, DeliveryStatus, HeatGrid, InventoryItem, LiveMessage, MapFloor, MapPlace, MapProp, MapRoom, MapWall, PlanOverlay, Point, Robot, RejectReason, RobotState, RoundShelfCount, Schedule, SecurityAlert, ServerSummary, ServiceStats, Session, SystemMode, Tablet, TabletFix, Task, TaskHistoryEntry, TaskKind, TaskRoute, TaskState, Traffic, Zone, ZoneDelivery } from '../types'

import { deriveMood } from './format'

type Raw = Record<string, unknown>

function isRaw(value: unknown): value is Raw {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function field(raw: Raw, ...keys: string[]): unknown {
  for (const key of keys) if (raw[key] !== undefined && raw[key] !== null) return raw[key]
  return undefined
}

function text(raw: Raw, fallback: string, ...keys: string[]): string {
  const value = field(raw, ...keys)
  return typeof value === 'string' ? value : typeof value === 'number' ? String(value) : fallback
}

function textOrNull(raw: Raw, ...keys: string[]): string | null {
  const value = field(raw, ...keys)
  return typeof value === 'string' && value ? value : null
}

function num(raw: Raw, fallback: number, ...keys: string[]): number {
  const value = field(raw, ...keys)
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function flag(raw: Raw, fallback: boolean, ...keys: string[]): boolean {
  const value = field(raw, ...keys)
  return typeof value === 'boolean' ? value : fallback
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback
}

function point(value: unknown): Point | null {
  if (Array.isArray(value) && typeof value[0] === 'number' && typeof value[1] === 'number') return [value[0], value[1]]
  if (isRaw(value) && typeof value.x === 'number' && typeof value.y === 'number') return [value.x, value.y]
  return null
}

function points(value: unknown): Point[] {
  return list(value).map(point).filter((entry): entry is Point => entry !== null)
}

const ROBOT_STATES: readonly RobotState[] = ['idle', 'busy', 'paused', 'fault', 'estop']
const ROBOT_MOODS: readonly RobotMood[] = ['happy', 'busy', 'deaf', 'charging', 'home', 'alarm', 'stopped', 'offline']
const TASK_STATES: readonly TaskState[] = ['requested', 'assigned', 'en_route', 'delivered', 'failed', 'resumed', 'cancelled']
const TASK_KINDS: readonly TaskKind[] = ['fetch', 'restock_round', 'go_to', 'follow']

export function toRobot(value: unknown): Robot | null {
  if (!isRaw(value)) return null
  const id = text(value, '', 'id', 'robot_id')
  const pos = field(value, 'pos', 'position')
  if (!id || !isRaw(pos)) return null
  const role = text(value, '', 'role', 'role_card', 'card')
  const state = oneOf(field(value, 'state'), ROBOT_STATES, 'fault')
  // Unknown microphone state is shown as closed: never claim a robot listens when we do not know.
  const micOpen = flag(value, false, 'mic_open', 'micOpen')
  const goingHome = flag(value, false, 'going_home', 'goingHome')
  const mood = field(value, 'mood')
  return {
    id,
    name: text(value, role ? `${id} · ${role}` : id, 'name'),
    role,
    simulated: flag(value, false, 'simulated'),
    position: { x: num(pos, 0, 'x'), y: num(pos, 0, 'y'), heading: num(pos, 0, 'heading'), floor: num(pos, 0, 'floor') },
    battery: num(value, 0, 'battery'),
    state,
    holding: textOrNull(value, 'holding'),
    micOpen,
    taskId: textOrNull(value, 'task_id', 'taskId'),
    // No time from the server means we cannot claim it is fresh: an empty value counts as stale.
    lastSeen: text(value, '', 'last_seen', 'lastSeen', 'ts'),
    // Older servers send neither: the deaf zone is read from the closed microphone (not when stopped).
    inDeafZone: flag(value, !micOpen && state !== 'estop', 'in_deaf_zone', 'inDeafZone'),
    goingHome,
    mood: ROBOT_MOODS.includes(mood as RobotMood) ? (mood as RobotMood) : deriveMood(state, micOpen, goingHome),
  }
}

/** `GET /fleet/home` and `PUT /fleet/home`. The floor may come as a number or a string. */
export function toFleetHome(value: unknown): FleetHome {
  const raw = isRaw(value) ? value : {}
  const floor = field(raw, 'floor')
  const floorNumber = typeof floor === 'number' ? floor : typeof floor === 'string' && floor.trim() !== '' && Number.isFinite(Number(floor)) ? Number(floor) : null
  return { placeId: textOrNull(raw, 'place_id', 'placeId'), label: textOrNull(raw, 'label'), floor: floorNumber }
}

function toHistory(value: unknown): TaskHistoryEntry[] {
  return list(value).filter(isRaw).map((entry) => ({ at: text(entry, '', 'at', 'ts'), actor: text(entry, 'server', 'actor'), label: text(entry, '', 'label', 'state', 'event') }))
}

export function toTask(value: unknown): Task | null {
  if (!isRaw(value)) return null
  const id = text(value, '', 'id', 'task_id')
  if (!id) return null
  const updatedAt = text(value, new Date().toISOString(), 'updated_at', 'updatedAt', 'ts')
  return {
    id,
    kind: oneOf(field(value, 'kind'), TASK_KINDS, 'fetch'),
    item: textOrNull(value, 'item'),
    fromPlace: textOrNull(value, 'from_place', 'fromPlace'),
    toPlace: text(value, '', 'to_place', 'toPlace'),
    state: oneOf(field(value, 'state'), TASK_STATES, 'requested'),
    robotId: textOrNull(value, 'robot_id', 'robotId'),
    requestedBy: text(value, 'unknown', 'requested_by', 'requestedBy'),
    createdAt: text(value, updatedAt, 'created_at', 'createdAt'),
    updatedAt,
    reason: textOrNull(value, 'reason'),
    history: toHistory(field(value, 'history')),
    targetLabel: textOrNull(value, 'target_label', 'targetLabel'),
  }
}

export function toItem(value: unknown): InventoryItem | null {
  if (!isRaw(value)) return null
  const id = text(value, '', 'id', 'item')
  if (!id) return null
  const robotCount = field(value, 'last_robot_count', 'lastRobotCount')
  return {
    id,
    label: text(value, id, 'label', 'name'),
    place: text(value, '', 'place', 'location'),
    count: num(value, 0, 'count'),
    lowAt: num(value, 0, 'low_at', 'lowAt'),
    lastRobotCount: typeof robotCount === 'number' ? robotCount : null,
    lastRobotCountAt: textOrNull(value, 'last_robot_count_at', 'lastRobotCountAt'),
    updatedAt: text(value, new Date().toISOString(), 'updated_at', 'updatedAt'),
  }
}

const DELIVERY: readonly DeliveryStatus[] = ['received', 'pending', 'failed']

export function toZone(value: unknown): Zone | null {
  if (!isRaw(value)) return null
  const id = text(value, '', 'id')
  const polygon = points(field(value, 'polygon', 'points'))
  if (!id || polygon.length < 3) return null
  const deliveries: ZoneDelivery[] = list(field(value, 'deliveries')).filter(isRaw).map((entry) => ({ robotId: text(entry, '', 'robot_id', 'robotId'), status: oneOf(field(entry, 'status'), DELIVERY, 'pending') }))
  return { id, name: text(value, id, 'name'), floor: num(value, 0, 'floor'), kind: oneOf(field(value, 'kind'), ['deaf', 'restricted'] as const, 'restricted'), polygon, deliveries }
}

export function toSchedule(value: unknown): Schedule | null {
  if (!isRaw(value)) return null
  const id = text(value, '', 'id')
  if (!id) return null
  const counts: RoundShelfCount[] = list(field(value, 'last_counts', 'lastCounts')).filter(isRaw).map((entry) => ({ place: text(entry, '', 'place'), item: text(entry, '', 'item'), expected: num(entry, 0, 'expected'), counted: num(entry, 0, 'counted', 'count') }))
  return {
    id,
    label: text(value, 'Night restock round', 'label', 'name'),
    enabled: flag(value, false, 'enabled'),
    time: text(value, '02:30', 'time'),
    robotId: textOrNull(value, 'robot_id', 'robotId'),
    lastRun: textOrNull(value, 'last_run', 'lastRun'),
    lastResult: oneOf(field(value, 'last_result', 'lastResult'), ['success', 'partial', 'failed', 'never'] as const, 'never'),
    lastCounts: counts,
  }
}

const AUDIT_RESULTS: readonly AuditResult[] = ['ok', 'refused', 'failed']

export function toAudit(value: unknown, index: number): AuditEntry | null {
  if (!isRaw(value)) return null
  return {
    id: text(value, `audit-${index}`, 'id'),
    at: text(value, '', 'at', 'ts'),
    actor: text(value, 'unknown', 'actor'),
    action: text(value, '', 'action', 'type'),
    target: text(value, '', 'target'),
    result: oneOf(field(value, 'result'), AUDIT_RESULTS, 'ok'),
    detail: textOrNull(value, 'detail', 'reason'),
  }
}

export function toMap(value: unknown): ClinicMap {
  const raw = isRaw(value) ? value : {}
  const floors: MapFloor[] = list(raw.floors).map((entry): MapFloor | null => {
    if (typeof entry === 'number') return { id: entry, label: entry === 0 ? 'Ground floor' : `Floor ${entry}`, outline: [] }
    if (!isRaw(entry)) return null
    const id = num(entry, 0, 'id', 'floor')
    return { id, label: text(entry, id === 0 ? 'Ground floor' : `Floor ${id}`, 'label', 'name'), outline: points(entry.outline) }
  }).filter((entry): entry is MapFloor => entry !== null)
  const rooms: MapRoom[] = list(raw.rooms).filter(isRaw).map((entry, index) => ({ id: text(entry, `room-${index}`, 'id'), floor: num(entry, 0, 'floor'), label: text(entry, '', 'label', 'name'), kind: oneOf(entry.kind, ['room', 'corridor', 'elevator', 'care', 'storage', 'therapy', 'pool', 'lounge'] as const, 'room'), polygon: points(entry.polygon), labelAt: point(field(entry, 'label_at', 'labelAt')) ?? undefined })).filter((room) => room.polygon.length >= 3)
  const walls: MapWall[] = list(raw.walls).filter(isRaw).map((entry) => ({ floor: num(entry, 0, 'floor'), points: points(entry.points) })).filter((wall) => wall.points.length >= 2)
  const places: MapPlace[] = list(raw.places).filter(isRaw).map((entry, index) => ({ id: text(entry, `place-${index}`, 'id'), label: text(entry, '', 'label', 'name'), floor: num(entry, 0, 'floor'), x: num(entry, 0, 'x'), y: num(entry, 0, 'y'), kind: oneOf(entry.kind, ['room', 'shelf', 'dock', 'point'] as const, 'room') }))
  const props: MapProp[] = list(raw.props).filter(isRaw).map((entry, index) => ({ id: text(entry, `prop-${index}`, 'id'), floor: num(entry, 0, 'floor'), kind: oneOf(entry.kind, ['bed', 'counter', 'desk', 'shelf', 'cabinet', 'sofa', 'armchair', 'table', 'plant', 'dock', 'pool', 'bench', 'crate', 'mat', 'bars', 'nightstand', 'door'] as const, 'cabinet'), x: num(entry, 0, 'x'), y: num(entry, 0, 'y'), width: num(entry, 0.6, 'width'), depth: num(entry, 0.6, 'depth'), solid: flag(entry, true, 'solid') }))
  const identity = { clinicId: textOrNull(raw, 'clinic_id', 'clinicId') ?? undefined, version: typeof raw.version === 'number' ? raw.version : undefined }
  return { ...identity, floors: floors.map((floor) => floor.outline.length >= 3 ? floor : { ...floor, outline: outlineFromWalls(walls, floor.id) }), rooms, walls, places, props }
}

/** `GET /clinics` rows. */
export function toClinicSummary(value: unknown): ClinicSummary | null {
  if (!isRaw(value)) return null
  const id = textOrNull(value, 'id')
  if (!id) return null
  return { id, name: text(value, id, 'name'), version: num(value, 0, 'version'), active: flag(value, false, 'active'), updatedAt: text(value, '', 'updated_at', 'updatedAt') }
}

/** A stored plan. Fields the console does not edit are kept as they are, so a save sends them back. */
export function toPlan(value: unknown): ClinicPlan | null {
  if (!isRaw(value) || typeof value.name !== 'string') return null
  return { ...value, name: value.name, floors: list(value.floors) as ClinicPlan['floors'], rooms: list(value.rooms) as ClinicPlan['rooms'], walls: list(value.walls) as ClinicPlan['walls'], places: list(value.places) as ClinicPlan['places'], props: list(value.props) as ClinicPlan['props'] }
}

/** `GET /clinics/{id}/overlay`. Missing keys mean nothing changed. */
export function toOverlay(value: unknown): PlanOverlay | null {
  if (!isRaw(value)) return null
  const upsert = isRaw(value.upsert) ? value.upsert : {}
  const remove = isRaw(value.remove) ? value.remove : {}
  const ids = (entries: unknown): string[] => list(entries).filter((entry): entry is string => typeof entry === 'string')
  return {
    base_version: typeof value.base_version === 'number' ? value.base_version : 0,
    upsert: { floors: list(upsert.floors) as ClinicPlan['floors'], rooms: list(upsert.rooms) as ClinicPlan['rooms'], walls: list(upsert.walls) as ClinicPlan['walls'], places: list(upsert.places) as ClinicPlan['places'], props: list(upsert.props) as ClinicPlan['props'] },
    remove: { floors: list(remove.floors).filter((entry): entry is number => typeof entry === 'number'), rooms: ids(remove.rooms), walls: ids(remove.walls), places: ids(remove.places), props: ids(remove.props) },
  }
}

/** `GET /stats/heat`. A grid whose counts do not fill `columns × rows` cannot be drawn right: null. */
export function toHeat(value: unknown): HeatGrid | null {
  if (!isRaw(value)) return null
  const columns = num(value, 0, 'columns')
  const rows = num(value, 0, 'rows')
  const counts = list(value.counts).map((entry) => (typeof entry === 'number' && Number.isFinite(entry) && entry > 0 ? entry : 0))
  if (!Number.isInteger(columns) || !Number.isInteger(rows) || columns < 0 || rows < 0 || counts.length !== columns * rows) return null
  const cellM = num(value, 1, 'cell_m', 'cellM')
  return { floor: num(value, 0, 'floor'), cellM: cellM > 0 ? cellM : 1, origin: point(value.origin) ?? [0, 0], columns, rows, counts }
}

/** `GET /tasks/{id}/route`. Fewer than two points is not a route: null. */
export function toRoute(value: unknown): TaskRoute | null {
  if (!isRaw(value)) return null
  const routePoints = points(value.points)
  if (routePoints.length < 2) return null
  return { floor: num(value, 0, 'floor'), points: routePoints, lengthM: num(value, 0, 'length_m', 'lengthM'), estimate: flag(value, true, 'estimate') }
}

/** `GET /system/mode`, and the `mode` of `mode.updated`. Anything unreadable counts as normal operation. */
export function toMode(value: unknown): SystemMode | null {
  if (!isRaw(value)) return null
  const mode = field(value, 'mode')
  if (mode !== 'normal' && mode !== 'emergency') return null
  return { mode, since: textOrNull(value, 'since'), by: textOrNull(value, 'by', 'actor'), reason: textOrNull(value, 'reason') }
}

const TABLET_KINDS = ['staff', 'bedside'] as const
const MAX_LABEL = 40

/** Owner and bed labels are short pseudonyms: anything longer is cut, never shown in full. */
function shortLabel(value: string): string {
  return value.length > MAX_LABEL ? `${value.slice(0, MAX_LABEL - 1)}…` : value
}

/** `{x, y}`, `point: {x, y}` (both with `floor` beside them), or `position: {x, y, floor}`. */
function tabletPosition(raw: Raw): { x: number; y: number; floor: number } | null {
  const nested = field(raw, 'position')
  if (isRaw(nested)) return tabletPosition(nested)
  const at = point(field(raw, 'point')) ?? point(raw)
  const floor = field(raw, 'floor')
  return at && typeof floor === 'number' ? { x: at[0], y: at[1], floor } : null
}

/**
 * A tablet from `GET /devices`, `GET /live` (`tablets[]`) or `device.updated`. Today's `/live` has
 * only `device_id`, `owner`, `place`, `floor`, `point` and `uncertainty_m`: the rest gets safe
 * defaults (staff, battery unknown, online and assigned since it is live). Only the fields below
 * are kept; anything else the server might send is dropped here.
 */
export function toTablet(value: unknown): Tablet | null {
  if (!isRaw(value)) return null
  const id = text(value, '', 'device_id', 'id')
  if (!id) return null
  const battery = field(value, 'battery_pct', 'battery')
  const uncertainty = field(value, 'uncertainty_m', 'uncertainty')
  return {
    id,
    kind: oneOf(field(value, 'kind'), TABLET_KINDS, 'staff'),
    label: shortLabel(text(value, '', 'label', 'owner')),
    speciality: textOrNull(value, 'speciality'),
    battery: typeof battery === 'number' && Number.isFinite(battery) ? Math.max(0, Math.min(100, battery)) : null,
    online: flag(value, true, 'online'),
    assigned: flag(value, true, 'assigned'),
    place: textOrNull(value, 'place'),
    position: tabletPosition(value),
    uncertainty: typeof uncertainty === 'number' ? uncertainty : null,
    lastSeen: textOrNull(value, 'last_seen', 'lastSeen'),
  }
}

function toTabletFix(value: unknown): TabletFix | null {
  if (!isRaw(value)) return null
  const id = text(value, '', 'device_id', 'id')
  if (!id) return null
  const uncertainty = field(value, 'uncertainty_m')
  const label = textOrNull(value, 'label', 'owner')
  return { id, label: label ? shortLabel(label) : null, place: textOrNull(value, 'place'), position: tabletPosition(value), uncertainty: typeof uncertainty === 'number' ? uncertainty : null }
}

function boolOrNull(raw: Raw, ...keys: string[]): boolean | null {
  const value = field(raw, ...keys)
  return typeof value === 'boolean' ? value : null
}

function numOrNull(raw: Raw, ...keys: string[]): number | null {
  const value = field(raw, ...keys)
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/** `GET /monitor/summary`. */
export function toSummary(value: unknown): ServerSummary | null {
  if (!isRaw(value)) return null
  return {
    startedAt: textOrNull(value, 'started_at'),
    uptimeS: num(value, 0, 'uptime_s'),
    version: textOrNull(value, 'version'),
    robotsConnected: num(value, 0, 'robots_connected'),
    robotsTotal: num(value, 0, 'robots_total'),
    appClients: num(value, 0, 'app_clients'),
    journalOk: boolOrNull(value, 'journal_ok'),
    databaseOk: boolOrNull(value, 'database_ok'),
    requestsPerS: num(value, 0, 'requests_per_s'),
    rejectedPerS: num(value, 0, 'rejected_per_s'),
    p95Ms: numOrNull(value, 'p95_ms'),
    blockedClients: num(value, 0, 'blocked_clients'),
  }
}

const REJECT_REASONS: readonly RejectReason[] = ['unauthorized', 'forbidden', 'rate_limited', 'blocked', 'emergency_mode', 'invalid']

/** `GET /monitor/traffic`. */
export function toTraffic(value: unknown): Traffic | null {
  if (!isRaw(value)) return null
  const by = isRaw(value.rejected_by) ? value.rejected_by : {}
  const rejectedBy = Object.fromEntries(REJECT_REASONS.map((reason) => [reason, num(by, 0, reason)])) as Record<RejectReason, number>
  const pointsRead = list(value.points).filter(isRaw).map((entry) => ({ at: text(entry, '', 'at'), accepted: num(entry, 0, 'accepted', 'ok'), rejected: num(entry, 0, 'rejected') })).filter((entry) => entry.at)
  return { stepS: num(value, 1, 'step_s'), points: pointsRead, rejectedBy, p95Ms: numOrNull(value, 'p95_ms') }
}

const CLIENT_STATUSES = ['ok', 'limited', 'blocked'] as const

/** One entry of `GET /monitor/clients`. */
export function toClient(value: unknown): ClientStat | null {
  if (!isRaw(value)) return null
  const ip = text(value, '', 'ip')
  if (!ip) return null
  return {
    ip,
    label: textOrNull(value, 'label'),
    requestsPerS: num(value, 0, 'requests_per_s'),
    requests: num(value, 0, 'requests'),
    rejected: num(value, 0, 'rejected'),
    loginFailures: num(value, 0, 'login_failures'),
    status: oneOf(field(value, 'status'), CLIENT_STATUSES, 'ok'),
    reason: textOrNull(value, 'reason'),
  }
}

/** One entry of `GET /security/blocks`. */
export function toBlock(value: unknown): BlockRule | null {
  if (!isRaw(value)) return null
  const id = text(value, '', 'id')
  const target = text(value, '', 'target')
  if (!id || !target) return null
  return {
    id,
    target,
    reason: text(value, '', 'reason'),
    source: oneOf(field(value, 'source'), ['manual', 'auto'] as const, 'manual'),
    createdAt: text(value, '', 'created_at'),
    expiresAt: textOrNull(value, 'expires_at'),
    by: textOrNull(value, 'by'),
    hits: num(value, 0, 'hits'),
  }
}

const ALERT_KINDS = ['rate_limited', 'auto_blocked', 'login_burst', 'blocked', 'unblocked'] as const

export function toSecurityAlert(value: unknown): SecurityAlert | null {
  if (!isRaw(value)) return null
  const ip = text(value, '', 'ip')
  if (!ip) return null
  return { at: text(value, new Date().toISOString(), 'at', 'ts'), kind: oneOf(field(value, 'kind'), ALERT_KINDS, 'rate_limited'), ip, message: text(value, '', 'message') }
}

/** `GET /stats/service`. */
export function toServiceStats(value: unknown): ServiceStats | null {
  if (!isRaw(value)) return null
  return {
    hours: num(value, 24, 'hours'),
    requests: num(value, 0, 'requests'),
    delivered: num(value, 0, 'delivered'),
    failed: num(value, 0, 'failed'),
    medianWaitS: numOrNull(value, 'median_wait_s'),
    p90WaitS: numOrNull(value, 'p90_wait_s'),
    byItem: list(value.by_item).filter(isRaw).map((entry) => ({ label: text(entry, '', 'label', 'item'), count: num(entry, 0, 'count') })).filter((entry) => entry.label),
    byPlace: list(value.by_place).filter(isRaw).map((entry) => ({ place: text(entry, '', 'place'), count: num(entry, 0, 'count') })).filter((entry) => entry.place),
    bedsideOnline: num(value, 0, 'bedside_online'),
    bedsideTotal: num(value, 0, 'bedside_total'),
  }
}

const INCIDENT_CODES: readonly IncidentCode[] = ['robot_fault', 'robot_offline', 'robot_estop', 'tablet_offline', 'tablet_battery_low', 'tablet_app_error', 'zone_not_delivered', 'journal_degraded', 'emergency_alarm', 'emergency_link_down']

/**
 * `GET /incidents` entry or the `incident` of `incident.updated`. `code` is an object on the wire
 * (`{"code": "robot_fault", "fault": "motor"}`); a plain string is read too.
 */
export function toIncident(value: unknown): Incident | null {
  if (!isRaw(value)) return null
  const rawId = field(value, 'id')
  const id = typeof rawId === 'number' || typeof rawId === 'string' ? String(rawId) : ''
  const codeField = field(value, 'code')
  const codeRaw = isRaw(codeField) ? codeField : {}
  const rawCode = typeof codeField === 'string' ? codeField : text(codeRaw, '', 'code')
  if (!id || !rawCode) return null
  const subjectRaw = field(value, 'subject')
  const kind = isRaw(subjectRaw) ? oneOf(subjectRaw.kind, ['robot', 'tablet'] as const, 'robot') : 'robot'
  const subject = isRaw(subjectRaw) && (subjectRaw.kind === 'robot' || subjectRaw.kind === 'tablet') && typeof subjectRaw.id === 'string' ? { kind, id: subjectRaw.id } : null
  const floor = field(value, 'floor')
  const openedAt = text(value, '', 'opened_at', 'openedAt')
  return {
    id,
    code: oneOf(rawCode, INCIDENT_CODES, 'other'),
    rawCode,
    detail: textOrNull(codeRaw, 'fault', 'error', 'level') ?? textOrNull(value, 'detail'),
    severity: oneOf(field(value, 'severity'), ['info', 'warning', 'critical'] as const, 'warning'),
    subject,
    place: textOrNull(value, 'place'),
    floor: typeof floor === 'number' ? floor : null,
    openedAt,
    lastSeenAt: text(value, openedAt, 'last_seen_at', 'lastSeenAt'),
    repeats: num(value, 0, 'repeats'),
    acknowledgedBy: textOrNull(value, 'acknowledged_by', 'acknowledgedBy'),
    closedAt: textOrNull(value, 'closed_at', 'closedAt'),
  }
}

/** A server that sends no floor outline still gets a floor slab: the box around its walls. */
function outlineFromWalls(walls: MapWall[], floorId: number): Point[] {
  const all = walls.filter((wall) => wall.floor === floorId).flatMap((wall) => wall.points)
  if (!all.length) return [[0, 0], [24, 0], [24, 14], [0, 14]]
  const xs = all.map((entry) => entry[0])
  const ys = all.map((entry) => entry[1])
  return [[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)], [Math.min(...xs), Math.max(...ys)]]
}

export function toSession(value: unknown, username: string): Session {
  const raw = isRaw(value) ? value : {}
  const token = text(raw, '', 'token', 'access_token')
  if (!token) throw new Error('The server did not return a token.')
  if (text(raw, '', 'role') !== 'admin') throw new Error('This panel is for the admin role only.')
  return { token, operator: text(raw, username, 'operator', 'name', 'username'), role: 'admin' }
}

export function toOutcome(value: unknown): CommandOutcome {
  if (!isRaw(value)) return { accepted: true, reason: null }
  return { accepted: flag(value, true, 'accepted', 'ok'), reason: textOrNull(value, 'reason', 'message') }
}

export function toList<T>(value: unknown, read: (entry: unknown, index: number) => T | null): T[] {
  const entries = Array.isArray(value) ? value : isRaw(value) ? list(field(value, 'items', 'data', 'results')) : []
  return entries.map(read).filter((entry): entry is T => entry !== null)
}

const ALERT_LEVELS: readonly AlertLevel[] = ['info', 'warning', 'critical']

/** Reads one WebSocket message. Unknown types return null: they are ignored, never fatal. */
export function toLiveMessage(value: unknown): LiveMessage | null {
  if (!isRaw(value)) return null
  const type = text(value, '', 'type')
  if (type === 'robot.updated') { const robot = toRobot(field(value, 'robot', 'data') ?? value); return robot ? { type, robot } : null }
  if (type === 'task.updated') { const task = toTask(field(value, 'task', 'data') ?? value); return task ? { type, task } : null }
  if (type === 'inventory.updated') { const item = toItem(field(value, 'item', 'inventory', 'data') ?? value); return item ? { type, item } : null }
  if (type === 'zone.updated') { const zone = toZone(field(value, 'zone', 'data') ?? value); return zone ? { type, zone } : null }
  if (type === 'zone.deleted') { const zoneId = text(value, '', 'zone_id', 'zoneId', 'id'); return zoneId ? { type, zoneId } : null }
  if (type === 'schedule.updated') { const schedule = toSchedule(field(value, 'schedule', 'data') ?? value); return schedule ? { type, schedule } : null }
  if (type === 'map.updated') {
    const clinicId = text(value, '', 'clinic_id', 'clinicId')
    return clinicId ? { type, clinicId, version: num(value, 0, 'version'), active: flag(value, false, 'active') } : null
  }
  if (type === 'resync') return { type }
  if (type === 'incident.updated') { const incident = toIncident(field(value, 'incident') ?? value); return incident ? { type, incident } : null }
  if (type === 'security.alert') { const securityAlert = toSecurityAlert(field(value, 'alert') ?? value); return securityAlert ? { type, alert: securityAlert } : null }
  if (type === 'device.updated') { const tablet = toTablet(field(value, 'device', 'tablet') ?? value); return tablet ? { type, tablet } : null }
  if (type === 'positions.delta') {
    const tablets = list(field(value, 'tablets')).map(toTabletFix).filter((entry): entry is TabletFix => entry !== null)
    const removedTablets = list(field(value, 'removed_tablets')).filter((entry): entry is string => typeof entry === 'string')
    return tablets.length || removedTablets.length ? { type, tablets, removedTablets } : null
  }
  if (type === 'mode.updated') { const nested = field(value, 'mode'); const mode = toMode(isRaw(nested) ? nested : value); return mode ? { type, mode } : null }
  if (type === 'alert') return { type, level: oneOf(field(value, 'level'), ALERT_LEVELS, 'warning'), message: text(value, 'Alert from the server.', 'message') }
  return null
}
