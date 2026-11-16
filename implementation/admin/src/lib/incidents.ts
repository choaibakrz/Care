/** What an incident means in plain words, its colour on the map, and which one matters most. */
import type { ClinicMap, Incident, IncidentSeverity, MapRoom } from '../types'
import { pointInPolygon } from './geometry'

/** The server's map colours: critical red, warning orange, info yellow. */
export const SEVERITY_COLOR: Record<IncidentSeverity, string> = { critical: '#ff5468', warning: '#ff9440', info: '#f6c453' }
export const SEVERITY_LABEL: Record<IncidentSeverity, string> = { critical: 'Critical', warning: 'Warning', info: 'Info' }
const SEVERITY_RANK: Record<IncidentSeverity, number> = { critical: 3, warning: 2, info: 1 }

const FAULT: Record<string, string> = { motor: 'motor', battery: 'battery', sensor: 'sensor', navigation: 'navigation', gripper: 'gripper', software: 'software' }
const APP_ERROR: Record<string, string> = { crash: 'the app crashed', network_lost: 'network lost', bluetooth_off: 'Bluetooth is off', camera_unavailable: 'camera unavailable', storage_full: 'storage full' }
const ALARM_LEVEL: Record<string, string> = { call: 'Patient call', urgent: 'Urgent patient call', emergency: 'Patient emergency' }

export function incidentTitle(incident: Incident): string {
  switch (incident.code) {
    case 'robot_fault': return incident.detail ? `Robot fault: ${FAULT[incident.detail] ?? incident.detail}` : 'Robot fault'
    case 'robot_offline': return 'Robot not answering'
    case 'robot_estop': return 'Robot in emergency stop'
    case 'tablet_offline': return 'Tablet offline'
    case 'tablet_battery_low': return 'Tablet battery low'
    case 'tablet_app_error': return incident.detail ? `Tablet: ${APP_ERROR[incident.detail] ?? incident.detail}` : 'Tablet app error'
    case 'zone_not_delivered': return 'Zone not received by a robot'
    case 'journal_degraded': return 'Audit journal cannot write'
    case 'emergency_alarm': return ALARM_LEVEL[incident.detail ?? ''] ?? 'Patient alarm'
    case 'emergency_link_down': return 'Link to the emergency service lost'
    default: return incident.rawCode.replace(/_/g, ' ')
  }
}

/** What the admin can do about it, in one sentence. */
export function incidentAdvice(incident: Incident): string {
  switch (incident.code) {
    case 'emergency_alarm': return 'The emergency service is paging staff. It is acknowledged there, not here.'
    case 'emergency_link_down': return 'Patient alarms may not show on this map. The emergency service itself keeps working.'
    case 'robot_estop': return 'A person must check the robot and release its red button.'
    case 'robot_fault': return 'A person must check the robot.'
    case 'robot_offline': return 'Check the robot is on and in Wi-Fi range.'
    case 'tablet_battery_low': return 'Put the tablet on charge.'
    case 'tablet_offline': return 'Check the tablet is on and in Wi-Fi range.'
    case 'journal_degraded': return 'Changes may not be recorded. Check the server disk.'
    case 'zone_not_delivered': return 'The robot keeps its old zones until it receives the new ones.'
    default: return ''
  }
}

/** Patient alarms are mirrored from the emergency service: never acknowledged here (the server answers 409). */
export function canAcknowledge(incident: Incident): boolean {
  return incident.code !== 'emergency_alarm' && !incident.acknowledgedBy && !incident.closedAt
}

export function worse(a: Incident, b: Incident): Incident {
  if (SEVERITY_RANK[a.severity] !== SEVERITY_RANK[b.severity]) return SEVERITY_RANK[a.severity] > SEVERITY_RANK[b.severity] ? a : b
  // Same severity: a patient alarm first, then the most recent.
  if ((a.code === 'emergency_alarm') !== (b.code === 'emergency_alarm')) return a.code === 'emergency_alarm' ? a : b
  return Date.parse(a.lastSeenAt) >= Date.parse(b.lastSeenAt) ? a : b
}

/** Most serious first, then the newest. */
export function byUrgency(a: Incident, b: Incident): number {
  return worse(a, b) === a ? -1 : 1
}

/** The room of an incident: the room with the place's id, or the room around the place's point. */
export function incidentRoom(map: ClinicMap, incident: Incident): MapRoom | null {
  if (!incident.place) return null
  const direct = map.rooms.find((room) => room.id === incident.place)
  if (direct) return direct
  const place = map.places.find((entry) => entry.id === incident.place)
  if (!place) return null
  return map.rooms.find((room) => room.floor === place.floor && pointInPolygon(place.x, place.y, room.polygon)) ?? null
}
