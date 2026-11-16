/**
 * The demo server's incident board. Incidents are raised by what happens in the demo clinic (a
 * robot stops, faults or goes silent; a tablet runs low or goes offline) and by the demo control
 * that plays a patient alarm from the emergency service. Rules as the server's:
 *
 * - the same thing raised again while open is merged (`repeats`, `last_seen_at`), and its
 *   severity can rise, never fall;
 * - patient alarms are read-only here: they are acknowledged and resolved in the emergency
 *   service (acknowledging one here is refused, like the server's 409).
 */
import { pointInPolygon } from '../lib/geometry'
import type { Incident, IncidentCode, IncidentSeverity } from '../types'
import type { SimState } from './sim-state'
import { audit, emit, iso } from './sim-state'

const RANK: Record<IncidentSeverity, number> = { info: 1, warning: 2, critical: 3 }
/** How long the emergency service takes to resolve a demo patient alarm. */
export const DEMO_ALARM_SECONDS = 45

export const ALARM_REFUSAL = 'Emergency alarms are acknowledged in the emergency service, not here.'

export interface RaiseOptions {
  code: IncidentCode
  severity: IncidentSeverity
  detail?: string | null
  subject?: Incident['subject']
  place?: string | null
  floor?: number | null
}

function copy(incident: Incident): Incident {
  return { ...incident, subject: incident.subject ? { ...incident.subject } : null }
}

function announce(state: SimState, incident: Incident): void {
  emit(state, { type: 'incident.updated', incident: copy(incident) })
}

/** The room a point is in, as a place id the map can colour. */
export function roomAt(state: SimState, floor: number, x: number, y: number): string | null {
  return state.map.rooms.find((room) => room.floor === floor && room.kind !== 'corridor' && pointInPolygon(x, y, room.polygon))?.id
    ?? state.map.rooms.find((room) => room.floor === floor && pointInPolygon(x, y, room.polygon))?.id
    ?? null
}

function sameThing(incident: Incident, options: RaiseOptions): boolean {
  return !incident.closedAt && incident.code === options.code && (incident.detail ?? null) === (options.detail ?? null)
    && incident.subject?.id === options.subject?.id && (options.code !== 'emergency_alarm' || incident.place === options.place)
}

export function raise(state: SimState, options: RaiseOptions): Incident {
  const at = iso(state)
  const open = state.incidents.find((incident) => sameThing(incident, options))
  if (open) {
    open.repeats += 1
    open.lastSeenAt = at
    if (RANK[options.severity] > RANK[open.severity]) open.severity = options.severity
    announce(state, open)
    return copy(open)
  }
  state.incidentCount += 1
  const incident: Incident = {
    id: String(state.incidentCount),
    code: options.code,
    rawCode: options.code,
    detail: options.detail ?? null,
    severity: options.severity,
    subject: options.subject ?? null,
    place: options.place ?? null,
    floor: options.floor ?? null,
    openedAt: at,
    lastSeenAt: at,
    repeats: 0,
    acknowledgedBy: null,
    closedAt: null,
  }
  state.incidents.push(incident)
  announce(state, incident)
  return copy(incident)
}

/** Raised by a robot: placed in the room the robot is in. */
export function raiseForRobot(state: SimState, robotId: string, code: IncidentCode, severity: IncidentSeverity, detail: string | null = null): void {
  const robot = state.robots.find((entry) => entry.robot.id === robotId)?.robot
  if (!robot) return
  const { floor, x, y } = robot.position
  raise(state, { code, severity, detail, subject: { kind: 'robot', id: robotId }, place: roomAt(state, floor, x, y), floor })
}

function find(state: SimState, incidentId: string): Incident {
  const incident = state.incidents.find((entry) => entry.id === incidentId)
  if (!incident) throw new Error(`Incident ${incidentId} does not exist.`)
  return incident
}

export function acknowledge(state: SimState, incidentId: string, actor: string): Incident {
  const incident = find(state, incidentId)
  if (incident.code === 'emergency_alarm') throw new Error(ALARM_REFUSAL)
  if (incident.closedAt) throw new Error('This incident is already closed.')
  incident.acknowledgedBy = actor
  audit(state, actor, 'Incident acknowledged', `incident ${incidentId}`)
  announce(state, incident)
  return copy(incident)
}

export function close(state: SimState, incidentId: string, actor: string): Incident {
  const incident = find(state, incidentId)
  if (incident.closedAt) return copy(incident)
  if (incident.code === 'emergency_alarm' && actor !== 'emergency service') throw new Error('Patient alarms are resolved in the emergency service, not here.')
  incident.closedAt = iso(state)
  audit(state, actor, 'Incident closed', `incident ${incidentId}`)
  announce(state, incident)
  return copy(incident)
}

export function listIncidents(state: SimState, includeClosed: boolean): Incident[] {
  return state.incidents.filter((incident) => includeClosed || !incident.closedAt).map(copy)
}

/** Demo control: a patient presses the bedside button; the emergency service resolves it later. */
export function playPatientAlarm(state: SimState, placeId: string, level: 'call' | 'urgent' | 'emergency'): Incident {
  const place = state.map.places.find((entry) => entry.id === placeId)
  const incident = raise(state, { code: 'emergency_alarm', severity: level === 'call' ? 'warning' : 'critical', detail: level, place: placeId, floor: place?.floor ?? null })
  state.alarmEnds.push({ incidentId: incident.id, at: state.clock + DEMO_ALARM_SECONDS * 1000 })
  return incident
}

/** Closes the demo patient alarms the emergency service has resolved. */
export function stepIncidents(state: SimState): void {
  const due = state.alarmEnds.filter((entry) => entry.at <= state.clock)
  if (!due.length) return
  state.alarmEnds = state.alarmEnds.filter((entry) => entry.at > state.clock)
  for (const entry of due) {
    const incident = state.incidents.find((candidate) => candidate.id === entry.incidentId)
    if (!incident || incident.closedAt) continue
    incident.acknowledgedBy = 'Nurse (emergency service)'
    close(state, incident.id, 'emergency service')
  }
}
