/** The real server, over contract C3: JSON, bearer token, errors as `{ error: { code, message } }`. */
import type { FleetHome, AuditEntry, PlanOverlay, ClinicPlan, ClinicSummary, AuditQuery, BlockRule, ClientStat, ClinicMap, ClinicRoom, Incident, CommandOutcome, HeatGrid, InventoryItem, NewTask, Robot, RobotCommand, Schedule, ServerSummary, ServiceStats, Session, SystemMode, Tablet, TabletAssignment, Task, TaskRoute, Traffic, Zone, RoomDevice, RoomPatient } from '../types'
import { toFleetHome, toAudit, toOverlay, toClinicSummary, toPlan, toBlock, toClient, toHeat, toIncident, toItem, toList, toMap, toMode, toOutcome, toRobot, toRoute, toSchedule, toServiceStats, toSession, toSummary, toTablet, toTask, toTraffic, toZone } from './adapt'
import { DEFAULT_DERIVATION, deriveAccountKey, toDerivation } from './accountKey'
import type { DerivationParams } from './accountKey'
import type { Backend, Enrolment } from './backend'
import { config } from './config'

const TIMEOUT_MS = 6000

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  /** 422 `invalid_plan`: what is wrong, and where. */
  readonly details: Array<{ path: string; problem: string }>

  constructor(message: string, status: number, code: string, details: Array<{ path: string; problem: string }> = []) {
    super(message)
    this.details = details
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

async function readError(response: Response): Promise<ApiError> {
  try {
    const body: unknown = await response.json()
    const value = typeof body === 'object' && body !== null ? body as { error?: unknown; message?: unknown } : {}
    if (typeof value.message === 'string') {
      const error = typeof value.error === 'string' ? value.error : 'error'
      return new ApiError(value.message, response.status, error)
    }
    const error = typeof value.error === 'object' && value.error !== null ? value.error as { code?: unknown; message?: unknown; details?: unknown } : undefined
    const details = Array.isArray(error?.details) ? (error.details as unknown[]).flatMap((entry) => (typeof entry === 'object' && entry !== null && typeof (entry as { problem?: unknown }).problem === 'string' ? [{ path: String((entry as { path?: unknown }).path ?? ''), problem: (entry as { problem: string }).problem }] : [])) : []
    if (error && typeof error.message === 'string') return new ApiError(error.message, response.status, typeof error.code === 'string' ? error.code : 'error', details)
  } catch {
    // Not JSON: fall through to the generic message.
  }
  return new ApiError(`The server answered with an error (${response.status}).`, response.status, 'http_error')
}

export async function request(path: string, token: string, options: RequestInit = {}): Promise<unknown> {
  return (await requestFull(path, token, options)).body
}

/** Like `request`, and also gives the `ETag` of the answer (the plan version) without its quotes. */
export async function requestFull(path: string, token: string, options: RequestInit = {}): Promise<{ body: unknown; etag: string | null }> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), TIMEOUT_MS)
  try {
    const response = await fetch(`${config.apiUrl}${path}`, {
      ...options,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers as Record<string, string> | undefined) },
    })
    // Without a token (sign-in, enrolment) a 401 is a wrong user name or password, not an
    // ended session: show the server's own message.
    if (response.status === 401 && !token) {
      const refused = await readError(response)
      throw refused.code === 'http_error' ? new ApiError('Wrong user name or password.', 401, 'unauthorized') : refused
    }
    if (response.status === 401) {
      window.dispatchEvent(new Event('clinic-pilot:session-expired'))
      throw new ApiError('Your session has ended. Please sign in again.', 401, 'unauthorized')
    }
    if (!response.ok) throw await readError(response)
    return { body: response.status === 204 ? null : await response.json(), etag: response.headers.get('ETag')?.replace(/^W\/|"/g, '') ?? null }
  } catch (reason) {
    if (reason instanceof ApiError) throw reason
    if (reason instanceof DOMException && reason.name === 'AbortError') throw new Error('The server did not answer within 6 seconds.')
    throw new Error('No connection to the server.')
  } finally {
    window.clearTimeout(timer)
  }
}

/** The key derivation parameters of this server (`GET /auth/derivation`); the defaults if it has none. */
async function derivation(): Promise<DerivationParams> {
  try {
    return toDerivation(await request('/auth/derivation', ''))
  } catch (reason) {
    if (reason instanceof ApiError && reason.status === 404) return DEFAULT_DERIVATION
    throw reason
  }
}

/** A route the server may not have yet: 404, or 501 `not_implemented_yet`, becomes null; anything else is an error. */
async function optional<T>(load: () => Promise<T>): Promise<T | null> {
  try {
    return await load()
  } catch (reason) {
    if (reason instanceof ApiError && (reason.status === 404 || reason.status === 501)) return null
    throw reason
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function send(method: string, body: unknown): RequestInit {
  return { method, body: JSON.stringify(body) }
}

/** A refusal comes back as a 4xx with a message that is safe to show. It is an answer, not a failure. */
function isRefusal(reason: unknown): reason is ApiError {
  return reason instanceof ApiError && [400, 403, 409, 422].includes(reason.status)
}

function required<T>(value: T | null, what: string): T {
  if (value === null) throw new Error(`The server sent ${what} the panel cannot read.`)
  return value
}

/**
 * Compatibility for an older deployed gateway that does not know the magic-link login route yet.
 * This only creates an in-memory UI session; every protected API request still verifies the token
 * and the admin role on the server.
 */
function sessionFromAccessToken(accessToken: string): Session {
  try {
    const encodedPayload = accessToken.split('.')[1]
    if (!encodedPayload) throw new Error('invalid_payload')
    const payload = JSON.parse(window.atob(encodedPayload.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(encodedPayload.length / 4) * 4, '='))) as { sub?: unknown; email?: unknown; app_metadata?: { role?: unknown } }
    if (typeof payload.sub !== 'string' || (payload.app_metadata?.role !== undefined && payload.app_metadata.role !== 'admin')) throw new Error('not_admin')
    return { token: accessToken, operator: typeof payload.email === 'string' ? payload.email : 'administrator', role: 'admin' }
  } catch {
    throw new Error('This sign-in link is invalid or expired.')
  }
}

function auditPath(query: AuditQuery): string {
  const params = new URLSearchParams()
  if (query.from) params.set('from', query.from)
  if (query.to) params.set('to', query.to)
  if (query.actor) params.set('actor', query.actor)
  const search = params.toString()
  return search ? `/audit?${search}` : '/audit'
}

export const httpBackend: Backend = {
  // The Rust clinic server (the pitch target) signs in with an account key derived from the
  // user name and password; it has `GET /auth/derivation`. The older Node patient portal has no
  // such route and signs the administrator in through `/api/admin/login`. Asking the Rust route
  // first keeps a failed request (and its console error) out of every sign-in.
  async login(username: string, password: string): Promise<Session> {
    let params: DerivationParams | null = null
    try {
      params = toDerivation(await request('/auth/derivation', ''))
    } catch (reason) {
      if (!(reason instanceof ApiError && (reason.status === 404 || reason.status === 405))) throw reason
    }
    if (!params) return toSession(await request('/api/admin/login', '', send('POST', { email: username.trim(), password })), username)
    const accountKey = await deriveAccountKey(username.trim(), password, params)
    return toSession(await request('/auth/login', '', send('POST', { account_key: accountKey })), username)
  },
  async loginWithToken(accessToken: string): Promise<Session> {
    try {
      return toSession(await request('/api/admin/login', '', send('POST', { access_token: accessToken })), '')
    } catch (reason) {
      if (reason instanceof ApiError && [404, 405, 422].includes(reason.status)) return sessionFromAccessToken(accessToken)
      throw reason
    }
  },
  async enrol(enrolment: Enrolment): Promise<string> {
    const accountKey = await deriveAccountKey(enrolment.username.trim(), enrolment.password, await derivation())
    const body = await request('/auth/enrol', '', send('POST', { enrolment_code: enrolment.code.trim(), account_key: accountKey, display_label: enrolment.pseudonym.trim() }))
    return isObject(body) && typeof body.operator === 'string' ? body.operator : enrolment.pseudonym.trim()
  },
  async getRooms(token: string): Promise<ClinicRoom[]> {
    const value = await request('/api/admin/rooms', token)
    if (!isObject(value) || !Array.isArray(value.rooms)) throw new Error('The server sent room data the panel cannot read.')
    return value.rooms as ClinicRoom[]
  },
  async admitPatient(token: string, input: { firstName: string; medicalRecordRef: string; roomId: string }): Promise<{ patient: RoomPatient; roomId: string }> {
    const value = await request('/api/admin/rooms', token, send('POST', { first_name: input.firstName, medical_record_ref: input.medicalRecordRef, room_id: input.roomId }))
    if (!isObject(value) || !isObject(value.patient) || typeof value.roomId !== 'string') throw new Error('The server did not confirm the patient admission.')
    return { patient: value.patient as unknown as RoomPatient, roomId: value.roomId }
  },
  async createRoomDevice(token: string, input: { roomId: string; label: string }): Promise<{ device: RoomDevice; pairingCode: string }> {
    const value = await request('/api/admin/devices', token, send('POST', { room_id: input.roomId, label: input.label }))
    if (!isObject(value) || !isObject(value.device) || typeof value.pairingCode !== 'string') throw new Error('The server did not return a tablet pairing code.')
    return { device: value.device as unknown as RoomDevice, pairingCode: value.pairingCode }
  },
  async dischargeRoom(token: string, roomId: string): Promise<void> {
    await request('/api/admin/discharge', token, send('POST', { room_id: roomId }))
  },
  async getMap(token: string): Promise<ClinicMap> { return toMap(await request('/map', token)) },
  async getRobots(token: string): Promise<Robot[]> { return toList(await request('/robots', token), toRobot) },
  async getTasks(token: string): Promise<Task[]> { return toList(await request('/tasks', token), toTask) },
  async getInventory(token: string): Promise<InventoryItem[]> { return toList(await request('/inventory', token), toItem) },
  async getZones(token: string): Promise<Zone[]> { return toList(await request('/zones', token), toZone) },
  async getSchedules(token: string): Promise<Schedule[]> { return toList(await request('/schedules', token), toSchedule) },
  async getAudit(token: string, query: AuditQuery): Promise<AuditEntry[]> { return toList(await request(auditPath(query), token), toAudit) },
  async getHeat(token: string, floor: number): Promise<HeatGrid> {
    return required(toHeat(await request(`/stats/heat?floor=${encodeURIComponent(String(floor))}`, token)), 'a heat map')
  },
  async getIncidents(token: string, includeClosed: boolean): Promise<Incident[]> {
    return toList(await request(includeClosed ? '/incidents?open=false' : '/incidents', token), toIncident)
  },
  // The answer may be the incident or an empty body: null tells the caller to read the list again.
  async acknowledgeIncident(token: string, incidentId: string): Promise<Incident | null> {
    return toIncident(await request(`/incidents/${encodeURIComponent(incidentId)}/ack`, token, send('POST', {})))
  },
  async closeIncident(token: string, incidentId: string): Promise<Incident | null> {
    return toIncident(await request(`/incidents/${encodeURIComponent(incidentId)}/close`, token, send('POST', {})))
  },
  async getSummary(token: string): Promise<ServerSummary | null> { return optional(async () => toSummary(await request('/monitor/summary', token))) },
  async getTraffic(token: string, windowS: number): Promise<Traffic | null> { return optional(async () => toTraffic(await request(`/monitor/traffic?window_s=${windowS}`, token))) },
  async getClients(token: string): Promise<ClientStat[] | null> { return optional(async () => toList(await request('/monitor/clients?limit=20', token), toClient)) },
  async getBlocks(token: string): Promise<BlockRule[] | null> { return optional(async () => toList(await request('/security/blocks', token), toBlock)) },
  async addBlock(token: string, block: { target: string; reason: string; expiresInS: number | null }): Promise<BlockRule> {
    return required(toBlock(await request('/security/blocks', token, send('POST', { target: block.target, reason: block.reason, expires_in_s: block.expiresInS }))), 'a block')
  },
  async removeBlock(token: string, blockId: string): Promise<void> {
    await request(`/security/blocks/${encodeURIComponent(blockId)}`, token, { method: 'DELETE' })
  },
  async getServiceStats(token: string, hours: number): Promise<ServiceStats | null> { return optional(async () => toServiceStats(await request(`/stats/service?hours=${hours}`, token))) },
  async getTablets(token: string): Promise<{ tablets: Tablet[]; managed: boolean }> {
    const live = await request('/live', token)
    const liveTablets = toList(isObject(live) ? live.tablets : [], toTablet)
    let registry: Tablet[] | null = null
    try {
      registry = toList(await request('/devices', token), toTablet)
    } catch (reason) {
      // No registry on this server yet: show the live tablets only.
      if (!(reason instanceof ApiError && reason.status === 404)) throw reason
    }
    if (!registry) return { tablets: liveTablets, managed: false }
    // The registry says who a tablet is; the live view says where it is right now.
    const where = new Map(liveTablets.map((tablet) => [tablet.id, tablet]))
    return { tablets: registry.map((tablet) => { const fix = where.get(tablet.id); return fix ? { ...tablet, position: fix.position ?? tablet.position, place: fix.place ?? tablet.place, uncertainty: fix.uncertainty } : tablet }), managed: true }
  },
  async disconnectTablet(token: string, tabletId: string): Promise<Tablet> {
    return required(toTablet(await request(`/devices/${encodeURIComponent(tabletId)}/disconnect`, token, send('POST', {}))), 'a tablet')
  },
  async assignTablet(token: string, tabletId: string, assignment: TabletAssignment): Promise<Tablet> {
    const body = { kind: assignment.kind, label: assignment.label, speciality: assignment.speciality, place: assignment.place }
    return required(toTablet(await request(`/devices/${encodeURIComponent(tabletId)}/assign`, token, send('POST', body))), 'a tablet')
  },
  async getMode(token: string): Promise<SystemMode | null> {
    try {
      return toMode(await request('/system/mode', token))
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 404) return null
      throw reason
    }
  },
  async setMode(token: string, mode: SystemMode['mode'], reason: string): Promise<SystemMode> {
    try {
      return required(toMode(await request('/system/mode', token, send('PUT', { mode, reason }))), 'a mode')
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) throw new ApiError('This server has no emergency mode yet.', 404, 'not_supported')
      throw error
    }
  },
  async getTaskRoute(token: string, taskId: string): Promise<TaskRoute | null> {
    try {
      return toRoute(await request(`/tasks/${encodeURIComponent(taskId)}/route`, token))
    } catch (reason) {
      // 404: the task is gone, or the server cannot draw a route (`no_route`). Nothing to draw.
      if (reason instanceof ApiError && reason.status === 404) return null
      throw reason
    }
  },

  async sendCommand(token: string, robotId: string, name: RobotCommand): Promise<CommandOutcome> {
    try {
      return toOutcome(await request(`/robots/${encodeURIComponent(robotId)}/command`, token, send('POST', { name })))
    } catch (reason) {
      if (isRefusal(reason)) return { accepted: false, reason: reason.message }
      throw reason
    }
  },
  async cancelTask(token: string, taskId: string): Promise<Task> {
    return required(toTask(await request(`/tasks/${encodeURIComponent(taskId)}/cancel`, token, send('POST', {}))), 'a task')
  },
  async createTask(token: string, task: NewTask): Promise<Task> {
    const body = { kind: task.kind, robot_id: task.robotId, to_place: task.toPlace, item: task.item, from_place: task.fromPlace, target_device: task.targetDevice }
    return required(toTask(await request('/tasks', token, send('POST', body))), 'a task')
  },
  async adjustInventory(token: string, itemId: string, delta: number): Promise<InventoryItem> {
    return required(toItem(await request(`/inventory/${encodeURIComponent(itemId)}/adjust`, token, send('POST', { delta }))), 'a stock item')
  },
  async putZone(token: string, zone: Zone): Promise<Zone> {
    const body = { id: zone.id, name: zone.name, floor: zone.floor, kind: zone.kind, polygon: zone.polygon }
    return required(toZone(await request(`/zones/${encodeURIComponent(zone.id)}`, token, send('PUT', body))), 'a zone')
  },
  async deleteZone(token: string, zoneId: string): Promise<void> {
    await request(`/zones/${encodeURIComponent(zoneId)}`, token, { method: 'DELETE' })
  },
  async putSchedule(token: string, schedule: Schedule): Promise<Schedule> {
    const body = { enabled: schedule.enabled, time: schedule.time }
    return required(toSchedule(await request(`/schedules/${encodeURIComponent(schedule.id)}`, token, send('PUT', body))), 'a schedule')
  },
  async runRoundNow(): Promise<string | null> {
    return 'Starting a round by hand is a demo control. On the real server the schedule starts it.'
  },
  async teleportRobot(token: string, robotId: string, at: { x: number; y: number; floor: number }): Promise<Robot> {
    // The contract sends the floor as a string; the server reads it back as its floor id.
    const body = { x: at.x, y: at.y, floor: String(at.floor) }
    return required(toRobot(await request(`/robots/${encodeURIComponent(robotId)}/teleport`, token, send('POST', body))), 'a robot')
  },
  async getFleetHome(token: string): Promise<FleetHome> {
    return (await optional(async () => toFleetHome(await request('/fleet/home', token)))) ?? { placeId: null, label: null, floor: null }
  },
  async setFleetHome(token: string, placeId: string | null): Promise<FleetHome> {
    return toFleetHome(await request('/fleet/home', token, send('PUT', { place_id: placeId })))
  },
  openSocket(): WebSocket {
    return new WebSocket(config.wsUrl)
  },
}

/** Clinic plans. Not on `Backend`: only the real server stores plans. */
export async function listClinics(token: string): Promise<ClinicSummary[]> {
  return toList(await request('/clinics', token), toClinicSummary)
}

export async function getClinic(token: string, id: string): Promise<{ plan: ClinicPlan; version: string }> {
  const { body, etag } = await requestFull(`/clinics/${encodeURIComponent(id)}`, token)
  return { plan: required(toPlan(body), 'a clinic plan'), version: etag ?? '' }
}

export async function createClinic(token: string, plan: ClinicPlan): Promise<ClinicSummary | null> {
  return toClinicSummary((await requestFull('/clinics', token, send('POST', plan))).body)
}

/** Saves with `If-Match`. 412 (changed meanwhile) and 422 (invalid plan, with `details`) come back as `ApiError`. */
export async function saveClinic(token: string, id: string, plan: ClinicPlan, version: string): Promise<{ plan: ClinicPlan; version: string }> {
  const { body, etag } = await requestFull(`/clinics/${encodeURIComponent(id)}`, token, { ...send('PUT', plan), headers: { 'If-Match': `"${version}"` } })
  return { plan: required(toPlan(body), 'a clinic plan'), version: etag ?? version }
}

export async function activateClinic(token: string, id: string): Promise<void> {
  await request(`/clinics/${encodeURIComponent(id)}/activate`, token, send('POST', {}))
}

export async function deleteClinic(token: string, id: string): Promise<void> {
  await request(`/clinics/${encodeURIComponent(id)}`, token, { method: 'DELETE' })
}

/** The base plan, without the modifications (`getClinic` is the effective plan). */
export async function getBasePlan(token: string, id: string): Promise<{ plan: ClinicPlan; version: string }> {
  const { body, etag } = await requestFull(`/clinics/${encodeURIComponent(id)}/base`, token)
  return { plan: required(toPlan(body), 'a clinic plan'), version: etag ?? '' }
}

export async function getOverlay(token: string, id: string): Promise<{ overlay: PlanOverlay; version: string }> {
  const { body, etag } = await requestFull(`/clinics/${encodeURIComponent(id)}/overlay`, token)
  return { overlay: required(toOverlay(body), 'clinic modifications'), version: etag ?? '' }
}

/** Saves the modifications with `If-Match`; the answer is the effective plan. 412 and 422 come back as `ApiError`. */
export async function saveOverlay(token: string, id: string, overlay: PlanOverlay, version: string): Promise<{ plan: ClinicPlan; version: string }> {
  const { body, etag } = await requestFull(`/clinics/${encodeURIComponent(id)}/overlay`, token, { ...send('PUT', overlay), headers: { 'If-Match': `"${version}"` } })
  return { plan: required(toPlan(body), 'a clinic plan'), version: etag ?? version }
}

/** Drops all modifications: the effective plan is the base again. */
export async function resetOverlay(token: string, id: string, version: string): Promise<{ plan: ClinicPlan; version: string }> {
  const { body, etag } = await requestFull(`/clinics/${encodeURIComponent(id)}/overlay`, token, { method: 'DELETE', headers: { 'If-Match': `"${version}"` } })
  return { plan: required(toPlan(body), 'a clinic plan'), version: etag ?? version }
}
