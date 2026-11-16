import { describe, expect, test } from 'vitest'
import { toIncident, toLiveMessage } from '../lib/adapt'
import { canAcknowledge, incidentRoom, incidentTitle, worse } from '../lib/incidents'
import { ClinicSim } from './sim'
import { ALARM_REFUSAL, DEMO_ALARM_SECONDS } from './sim-incidents'
import { mockMap } from './world'

function run(sim: ClinicSim, seconds: number): void {
  for (let i = 0; i < seconds * 10; i++) sim.step(0.1)
}

describe('incident readers', () => {
  test('GET /incidents entry, as clinic-server --mock answers it', () => {
    const incident = toIncident({ id: 1, code: { code: 'tablet_battery_low' }, severity: 'warning', subject: { kind: 'tablet', id: 'tab-mock-1' }, place: 'nurse-station', floor: 2, opened_at: '2026-11-15T12:04:34.626016400Z', last_seen_at: '2026-11-15T12:21:34.626016400Z', repeats: 2, acknowledged_by: null, closed_at: null })
    expect(incident).toEqual({ id: '1', code: 'tablet_battery_low', rawCode: 'tablet_battery_low', detail: null, severity: 'warning', subject: { kind: 'tablet', id: 'tab-mock-1' }, place: 'nurse-station', floor: 2, openedAt: '2026-11-15T12:04:34.626016400Z', lastSeenAt: '2026-11-15T12:21:34.626016400Z', repeats: 2, acknowledgedBy: null, closedAt: null })
  })

  test("incident.updated (server's docs/ws_messages.md example)", () => {
    const message = { type: 'incident.updated', id: '00000000-0000-4000-8000-000000000001', ts: '2026-11-14T08:00:00Z', colour: 'orange', incident: { acknowledged_by: null, closed_at: null, code: { code: 'robot_offline' }, floor: 1, id: 4, last_seen_at: '2026-11-14T08:00:00Z', opened_at: '2026-11-14T08:00:00Z', place: 'room-101', repeats: 0, severity: 'warning', subject: null } }
    expect(toLiveMessage(message)).toMatchObject({ type: 'incident.updated', incident: { id: '4', code: 'robot_offline', place: 'room-101', floor: 1, severity: 'warning' } })
  })

  test('the detail of a coded incident is kept, and an unknown code is still shown', () => {
    expect(toIncident({ id: 7, code: { code: 'robot_fault', fault: 'motor' }, severity: 'warning', opened_at: 'x', last_seen_at: 'x', repeats: 0 })?.detail).toBe('motor')
    expect(toIncident({ id: 8, code: { code: 'emergency_alarm', level: 'urgent' }, severity: 'critical', opened_at: 'x', last_seen_at: 'x', repeats: 0 })?.detail).toBe('urgent')
    const unknown = toIncident({ id: 9, code: { code: 'door_jammed' }, severity: 'info', opened_at: 'x', last_seen_at: 'x', repeats: 0 })
    expect(unknown?.code).toBe('other')
    expect(unknown && incidentTitle(unknown)).toBe('door jammed')
  })
})

describe('incident rules', () => {
  const base = { rawCode: '', detail: null, subject: null, place: null, floor: null, openedAt: '2026-11-15T09:00:00Z', lastSeenAt: '2026-11-15T09:00:00Z', repeats: 0, acknowledgedBy: null, closedAt: null }

  test('a patient alarm wins over anything of the same severity, and is never acknowledged here', () => {
    const alarm = { ...base, id: '1', code: 'emergency_alarm' as const, severity: 'critical' as const }
    const estop = { ...base, id: '2', code: 'robot_estop' as const, severity: 'critical' as const, lastSeenAt: '2026-11-15T09:05:00Z' }
    expect(worse(estop, alarm)).toBe(alarm)
    expect(canAcknowledge(alarm)).toBe(false)
    expect(canAcknowledge(estop)).toBe(true)
  })

  test('an incident is placed in the room of its place', () => {
    const incident = { ...base, id: '3', code: 'tablet_battery_low' as const, severity: 'warning' as const, place: 'nurse-station' }
    expect(incidentRoom(mockMap, incident)?.floor).toBe(2)
  })
})

describe('demo incident board', () => {
  test('an emergency stop opens a critical incident in the robot room; doing it again merges', () => {
    const sim = new ClinicSim({ seed: 7, autoTasks: false })
    const robot = sim.getRobots()[0]
    sim.command(robot.id, 'estop', 'admin')
    sim.command(robot.id, 'estop', 'admin')
    const stops = sim.getIncidents(false).filter((incident) => incident.code === 'robot_estop')
    expect(stops).toHaveLength(1)
    expect(stops[0]).toMatchObject({ severity: 'critical', subject: { kind: 'robot', id: robot.id }, repeats: 1 })
    expect(stops[0].place).not.toBeNull()
  })

  test('a low tablet battery is raised once, not on every tick', () => {
    const sim = new ClinicSim({ seed: 7, autoTasks: false })
    run(sim, 5)
    const low = sim.getIncidents(false).filter((incident) => incident.code === 'tablet_battery_low' && incident.subject?.id === 'tab-bed-13')
    expect(low).toHaveLength(1)
    expect(low[0].repeats).toBe(0)
  })

  test('a patient alarm cannot be acknowledged or closed here, and the emergency service resolves it', () => {
    const sim = new ClinicSim({ seed: 7, autoTasks: false })
    const alarm = sim.playPatientAlarm('room-13', 'urgent')
    expect(alarm).toMatchObject({ code: 'emergency_alarm', severity: 'critical', detail: 'urgent', place: 'room-13' })
    expect(() => sim.acknowledgeIncident(alarm.id, 'admin')).toThrow(ALARM_REFUSAL)
    expect(() => sim.closeIncident(alarm.id, 'admin')).toThrow(/emergency service/)
    run(sim, DEMO_ALARM_SECONDS + 1)
    expect(sim.getIncidents(false).some((incident) => incident.id === alarm.id)).toBe(false)
    expect(sim.getIncidents(true).find((incident) => incident.id === alarm.id)).toMatchObject({ acknowledgedBy: 'Nurse (emergency service)' })
  })

  test('an admin acknowledges then closes a robot incident', () => {
    const sim = new ClinicSim({ seed: 7, autoTasks: false })
    sim.injectFault(sim.getRobots()[1].id)
    const fault = sim.getIncidents(false).find((incident) => incident.code === 'robot_fault')
    expect(fault?.detail).toBe('motor')
    if (!fault) return
    expect(sim.acknowledgeIncident(fault.id, 'admin').acknowledgedBy).toBe('admin')
    expect(sim.closeIncident(fault.id, 'admin').closedAt).not.toBeNull()
    expect(sim.getIncidents(false).some((incident) => incident.id === fault.id)).toBe(false)
  })
})

describe('incidents on the demo live stream', () => {
  test('an incident sent by the demo server reads back the same', () => {
    const sim = new ClinicSim({ seed: 7, autoTasks: false })
    sim.drain(false)
    const alarm = sim.playPatientAlarm('room-13', 'urgent')
    const sent = sim.drain(false).find((message) => message.type === 'incident.updated')
    const read = toLiveMessage(JSON.parse(JSON.stringify(sent)))
    expect(read).toEqual({ type: 'incident.updated', incident: alarm })
    expect(read?.type === 'incident.updated' && incidentTitle(read.incident)).toBe('Urgent patient call')
  })
})
