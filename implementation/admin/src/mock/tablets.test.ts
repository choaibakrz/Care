import { describe, expect, test } from 'vitest'
import { toLiveMessage, toTablet } from '../lib/adapt'
import { ClinicSim } from './sim'

function sim(): ClinicSim {
  return new ClinicSim({ seed: 7, autoTasks: false })
}

describe('tablet readers', () => {
  test("today's GET /live tablet (clinic-server --mock) is read with safe defaults", () => {
    const tablet = toTablet({ device_id: 'tab-mock-1', owner: 'Ward 2 nurse (mock)', place: 'nurse-station', floor: 2, point: { x: 3.2, y: 7.8 }, uncertainty_m: null })
    expect(tablet).toEqual({ id: 'tab-mock-1', kind: 'staff', label: 'Ward 2 nurse (mock)', speciality: null, battery: null, online: true, assigned: true, place: 'nurse-station', position: { x: 3.2, y: 7.8, floor: 2 }, uncertainty: null, lastSeen: null })
  })

  test('GET /devices entry (requirements/tablets.md) is read in full', () => {
    const tablet = toTablet({ device_id: 'tab-bed-12', kind: 'bedside', label: 'Bed 12', speciality: null, battery_pct: 64, online: true, assigned: true, place: 'room-12', floor: 2, x: 20.9, y: 4.1, uncertainty_m: null, last_seen: '2026-11-15T09:12:00Z' })
    expect(tablet).toMatchObject({ id: 'tab-bed-12', kind: 'bedside', label: 'Bed 12', battery: 64, place: 'room-12', position: { x: 20.9, y: 4.1, floor: 2 } })
  })

  test('fields that are not in the contract are dropped, and long labels are cut', () => {
    const tablet = toTablet({ device_id: 'tab-1', label: 'A'.repeat(60), patient_name: 'Jane Doe', diagnosis: 'x', floor: 0, x: 1, y: 1 })
    expect(tablet).not.toHaveProperty('patient_name')
    expect(tablet).not.toHaveProperty('diagnosis')
    expect(tablet?.label.length).toBe(40)
  })

  test("positions.delta tablets (server's docs/ws_messages.md example) are read", () => {
    const message = { type: 'positions.delta', id: '00000000-0000-4000-8000-000000000001', ts: '2026-11-14T08:00:00Z', removed_tablets: ['tablet-2'], robots: [], tablets: [{ device_id: 'tablet-1', floor: 1, owner: 'Nurse A', place: 'room-101', uncertainty_m: 2.5, x: 20.0, y: 8.0 }] }
    expect(toLiveMessage(message)).toEqual({ type: 'positions.delta', tablets: [{ id: 'tablet-1', label: 'Nurse A', place: 'room-101', position: { x: 20, y: 8, floor: 1 }, uncertainty: 2.5 }], removedTablets: ['tablet-2'] })
  })

  test('device.updated is read', () => {
    const message = { type: 'device.updated', id: '00000000-0000-4000-8000-000000000001', ts: '2026-11-15T09:12:00Z', device: { device_id: 'tab-spare-1', kind: 'staff', label: '', online: true, assigned: false, battery_pct: 100, place: 'nurse-station', floor: 2, x: 3.7, y: 8.2 } }
    expect(toLiveMessage(message)).toMatchObject({ type: 'device.updated', tablet: { id: 'tab-spare-1', assigned: false, label: '' } })
  })
})

describe('demo tablets', () => {
  test('the clinic has staff, bedside and free tablets, and no patient name', () => {
    const tablets = sim().getTablets()
    expect(tablets.some((tablet) => tablet.kind === 'staff' && tablet.assigned)).toBe(true)
    expect(tablets.some((tablet) => tablet.kind === 'bedside' && tablet.assigned)).toBe(true)
    expect(tablets.some((tablet) => !tablet.assigned)).toBe(true)
    for (const tablet of tablets.filter((entry) => entry.kind === 'bedside' && entry.assigned)) expect(tablet.label).toMatch(/^Bed \d+$/)
  })

  test('freeing a tablet clears its label and sends it to the shelf; it can then be handed out', () => {
    const clinic = sim()
    const freed = clinic.disconnectTablet('tab-dr-a', 'admin')
    expect(freed).toMatchObject({ assigned: false, label: '', speciality: null, place: 'nurse-station' })
    expect(() => clinic.disconnectTablet('tab-dr-a', 'admin')).toThrow(/already free/)
    const given = clinic.assignTablet('tab-dr-a', { kind: 'staff', label: 'Dr. C', speciality: 'Neurology', place: null }, 'admin')
    expect(given).toMatchObject({ assigned: true, label: 'Dr. C', speciality: 'Neurology' })
  })

  test('a tablet in use cannot be handed out twice, and labels follow the server rules', () => {
    const clinic = sim()
    expect(() => clinic.assignTablet('tab-dr-a', { kind: 'staff', label: 'Dr. X', speciality: null, place: null }, 'admin')).toThrow(/in use/)
    expect(() => clinic.assignTablet('tab-spare-1', { kind: 'staff', label: '1234', speciality: null, place: null }, 'admin')).toThrow(/digits only/)
    expect(() => clinic.assignTablet('tab-spare-1', { kind: 'bedside', label: 'Bed 9', speciality: null, place: 'nurse-cabinet' }, 'admin')).toThrow(/patient room/)
  })

  test('batteries drain in use and charge when free', () => {
    const clinic = sim()
    const before = new Map(clinic.getTablets().map((tablet) => [tablet.id, tablet.battery ?? 0]))
    for (let i = 0; i < 600; i++) clinic.step(0.1)
    const after = new Map(clinic.getTablets().map((tablet) => [tablet.id, tablet.battery ?? 0]))
    expect(after.get('tab-dr-a')).toBeLessThan(before.get('tab-dr-a') ?? 0)
    expect(after.get('tab-spare-2')).toBeGreaterThan(before.get('tab-spare-2') ?? 0)
  })
})

describe('tablets on the demo live stream', () => {
  test('a tablet sent by the demo server reads back the same, position included', () => {
    const clinic = sim()
    clinic.drain(false)
    const freed = clinic.disconnectTablet('tab-dr-a', 'admin')
    const sent = clinic.drain(false).find((message) => message.type === 'device.updated')
    expect(toLiveMessage(JSON.parse(JSON.stringify(sent)))).toEqual({ type: 'device.updated', tablet: freed })
  })
})
