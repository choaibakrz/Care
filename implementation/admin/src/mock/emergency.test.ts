import { describe, expect, test } from 'vitest'
import { toLiveMessage, toMode } from '../lib/adapt'
import type { Robot } from '../types'
import { ClinicSim } from './sim'
import { EMERGENCY_REFUSAL } from './sim-admin'

function run(sim: ClinicSim, seconds: number): void {
  for (let i = 0; i < seconds * 10; i++) sim.step(0.1)
}

function busyRobot(sim: ClinicSim): Robot {
  const found = sim.getRobots().find((robot) => robot.taskId)
  if (!found) throw new Error('no robot on a task')
  return found
}

describe('emergency mode in the demo clinic', () => {
  test('switching it on clears the way: the task goes back to the queue and nobody takes it', () => {
    const sim = new ClinicSim({ seed: 7, autoTasks: false })
    const task = sim.request('Water bottle', 'supply-b', 'room-13')
    run(sim, 2)
    const robot = busyRobot(sim)

    const mode = sim.setMode('emergency', 'fire drill', 'admin')
    expect(mode).toMatchObject({ mode: 'emergency', by: 'admin', reason: 'fire drill' })
    run(sim, 20)

    expect(sim.getTasks().find((entry) => entry.id === task.id)?.state).toBe('requested')
    expect(sim.getRobots().find((entry) => entry.id === robot.id)?.taskId).toBeNull()
  })

  test('changes that are not about the emergency are refused, and accepted again after', () => {
    const sim = new ClinicSim({ seed: 7, autoTasks: false })
    sim.setMode('emergency', '', 'admin')
    expect(() => sim.requireNormal('Adjust stock')).toThrow(EMERGENCY_REFUSAL)
    sim.setMode('normal', '', 'admin')
    expect(() => sim.requireNormal('Adjust stock')).not.toThrow()
  })

  test('the emergency stop still works in emergency mode', () => {
    const sim = new ClinicSim({ seed: 7, autoTasks: false })
    sim.setMode('emergency', '', 'admin')
    const target = sim.getRobots()[0]
    expect(sim.command(target.id, 'estop', 'admin').accepted).toBe(true)
    expect(sim.getRobots()[0].state).toBe('estop')
  })

  test('the queued task is handed out again once the mode is off', () => {
    const sim = new ClinicSim({ seed: 7, autoTasks: false })
    const task = sim.request('Water bottle', 'supply-b', 'room-13')
    sim.setMode('emergency', '', 'admin')
    run(sim, 10)
    expect(sim.getTasks().find((entry) => entry.id === task.id)?.state).toBe('requested')
    sim.setMode('normal', '', 'admin')
    run(sim, 2)
    expect(sim.getTasks().find((entry) => entry.id === task.id)?.state).not.toBe('requested')
  })

  test('every switch is announced on the live stream', () => {
    const sim = new ClinicSim({ seed: 7, autoTasks: false })
    sim.drain(false)
    sim.setMode('emergency', 'drill', 'admin')
    const messages = sim.drain(false)
    expect(messages).toContainEqual(expect.objectContaining({ type: 'mode.updated', mode: expect.objectContaining({ mode: 'emergency' }) }))
  })
})

describe('mode readers (requirements/emergency-mode.md examples)', () => {
  test('GET /system/mode', () => {
    expect(toMode({ mode: 'emergency', since: '2026-11-15T09:12:00Z', by: 'Admin A', reason: 'Fire alarm, wing B' })).toEqual({ mode: 'emergency', since: '2026-11-15T09:12:00Z', by: 'Admin A', reason: 'Fire alarm, wing B' })
  })

  test('an unknown mode is not read', () => {
    expect(toMode({ mode: 'lockdown' })).toBeNull()
  })

  test('mode.updated', () => {
    const message = { type: 'mode.updated', id: '00000000-0000-4000-8000-000000000001', ts: '2026-11-15T09:12:00Z', mode: { mode: 'normal', since: '2026-11-15T09:40:00Z', by: 'Admin A', reason: null } }
    expect(toLiveMessage(message)).toEqual({ type: 'mode.updated', mode: { mode: 'normal', since: '2026-11-15T09:40:00Z', by: 'Admin A', reason: null } })
  })
})
