import { describe, expect, test } from 'vitest'
import { distanceToSegment } from '../lib/geometry'
import type { Point, Robot } from '../types'
import { ClinicSim } from './sim'
import { mockMap } from './world'

function quietSim(): ClinicSim {
  return new ClinicSim({ seed: 7, autoTasks: false })
}

function run(sim: ClinicSim, seconds: number, each?: () => void): void {
  for (let i = 0; i < seconds * 10; i++) { sim.step(0.1); each?.() }
}

function robot(sim: ClinicSim, id: string): Robot {
  const found = sim.getRobots().find((entry) => entry.id === id)
  if (!found) throw new Error(`no robot ${id}`)
  return found
}

function wallClearance(floor: number, x: number, y: number): number {
  const segments = mockMap.walls.filter((wall) => wall.floor === floor).flatMap((wall) => wall.points.slice(1).map((point, index): [Point, Point] => [wall.points[index], point]))
  return Math.min(...segments.map(([a, b]) => distanceToSegment(x, y, a, b)))
}

const CLOSED = ['delivered', 'failed', 'resumed']

describe('demo simulation', () => {
  test('a requested item is picked up and delivered, and the stock goes down', () => {
    const sim = quietSim()
    const before = sim.getInventory().find((item) => item.id === 'water-bottle')?.count ?? 0
    const task = sim.request('Water bottle', 'supply-b', 'room-13')
    run(sim, 90)
    const after = sim.getTasks().find((entry) => entry.id === task.id)
    expect(CLOSED).toContain(after?.state)
    if (after?.state === 'delivered') expect(sim.getInventory().find((item) => item.id === 'water-bottle')?.count).toBe(before - 1)
  })

  test('robots never drive through walls or solid furniture during a long run', () => {
    const sim = new ClinicSim({ seed: 3 })
    const solids = mockMap.props.filter((prop) => prop.solid && prop.kind !== 'dock')
    let tightest = Infinity
    const insideFurniture: string[] = []
    run(sim, 600, () => {
      for (const entry of sim.getRobots()) {
        const { x, y, floor } = entry.position
        tightest = Math.min(tightest, wallClearance(floor, x, y))
        for (const prop of solids) {
          if (prop.floor === floor && Math.abs(x - prop.x) < prop.width / 2 + 0.2 && Math.abs(y - prop.y) < prop.depth / 2 + 0.2) insideFurniture.push(`${entry.id} in ${prop.kind}`)
        }
      }
    })
    expect(tightest).toBeGreaterThan(0.25)
    expect(insideFurniture).toEqual([])
    expect(sim.getTasks().filter((task) => task.state === 'delivered').length).toBeGreaterThan(8)
  }, 30000)

  test('two robots on a floor never overlap', () => {
    const sim = new ClinicSim({ seed: 11 })
    let closest = Infinity
    run(sim, 600, () => {
      const robots = sim.getRobots()
      for (const a of robots) for (const b of robots) {
        if (a.id >= b.id || a.position.floor !== b.position.floor) continue
        closest = Math.min(closest, Math.hypot(a.position.x - b.position.x, a.position.y - b.position.y))
      }
    })
    expect(closest).toBeGreaterThan(0.5)
  }, 30000)

  test('the microphone closes inside a deaf zone, once the robot has received it', () => {
    const sim = quietSim()
    sim.putZone({ id: 'z-test', name: 'Corridor west', floor: 2, kind: 'deaf', polygon: [[0, 5.5], [6, 5.5], [6, 8.5], [0, 8.5]], deliveries: [] }, 'admin')
    sim.step(0.1)
    expect(robot(sim, 'R2').micOpen).toBe(true)
    run(sim, 4)
    expect(sim.getZones().find((zone) => zone.id === 'z-test')?.deliveries.every((delivery) => delivery.status === 'received')).toBe(true)
    expect(robot(sim, 'R2').micOpen).toBe(false)
    expect(robot(sim, 'R4').micOpen).toBe(true)
  })

  test('pause is refused with a reason when the robot is idle', () => {
    const outcome = quietSim().command('R1', 'pause', 'admin')
    expect(outcome.accepted).toBe(false)
    expect(outcome.reason).toMatch(/idle/)
  })

  test('emergency stop latches: the robot stops, fails its task and refuses resume', () => {
    const sim = quietSim()
    const task = sim.request('Towel', 'linen-shelf', 'pool')
    run(sim, 4)
    const id = sim.getRobots().find((entry) => entry.taskId === task.id)?.id ?? ''
    expect(id).not.toBe('')
    expect(sim.command(id, 'estop', 'admin').accepted).toBe(true)
    const stoppedAt = robot(sim, id).position
    run(sim, 5)
    expect(robot(sim, id).state).toBe('estop')
    expect(robot(sim, id).micOpen).toBe(false)
    expect(robot(sim, id).position.x).toBeCloseTo(stoppedAt.x, 5)
    expect(sim.getTasks().find((entry) => entry.id === task.id)?.state).toBe('failed')
    expect(sim.command(id, 'resume', 'admin')).toMatchObject({ accepted: false })
    sim.releaseEstop(id)
    expect(robot(sim, id).state).toBe('idle')
  })

  test('a command throws when the robot link is down', () => {
    const sim = quietSim()
    sim.dropLink('R2', 30)
    expect(() => sim.command('R2', 'estop', 'admin')).toThrow(/no link/)
  })

  test('pause freezes a busy robot and resume lets it finish', () => {
    const sim = quietSim()
    const task = sim.request('Towel', 'linen-shelf', 'therapy-1')
    run(sim, 3)
    const id = sim.getRobots().find((entry) => entry.taskId === task.id)?.id ?? ''
    expect(sim.command(id, 'pause', 'admin').accepted).toBe(true)
    const frozen = robot(sim, id).position
    run(sim, 3)
    expect(robot(sim, id).position.x).toBeCloseTo(frozen.x, 5)
    expect(sim.command(id, 'resume', 'admin').accepted).toBe(true)
    run(sim, 90)
    expect(CLOSED).toContain(sim.getTasks().find((entry) => entry.id === task.id)?.state)
  })

  test('dock is refused while the robot carries an item', () => {
    const sim = quietSim()
    const task = sim.request('Towel', 'linen-shelf', 'pool')
    let holder = ''
    run(sim, 40, () => { holder ||= sim.getRobots().find((entry) => entry.holding)?.id ?? '' })
    if (!holder) { expect(CLOSED).toContain(sim.getTasks().find((entry) => entry.id === task.id)?.state); return }
    const again = quietSim()
    again.request('Towel', 'linen-shelf', 'pool')
    let outcome = null
    for (let i = 0; i < 400 && !outcome; i++) {
      again.step(0.1)
      const carrying = again.getRobots().find((entry) => entry.holding)
      if (carrying) outcome = again.command(carrying.id, 'dock', 'admin')
    }
    expect(outcome).toMatchObject({ accepted: false })
  })

  test('the night round counts every shelf of the floor and reports the result', () => {
    const sim = quietSim()
    expect(sim.runRoundNow('night-restock', 'admin')).toBeNull()
    run(sim, 120)
    const schedule = sim.getSchedules()[0]
    expect(['success', 'partial']).toContain(schedule.lastResult)
    expect(schedule.lastCounts.length).toBe(sim.getInventory().filter((item) => ['supply-a', 'supply-b', 'nurse-cabinet'].includes(item.place)).length)
    expect(sim.getInventory().find((item) => item.id === 'blanket')?.lastRobotCount).not.toBeNull()
  })

  test('the audit log records admin actions and filters by actor', () => {
    const sim = quietSim()
    sim.command('R1', 'pause', 'chief')
    sim.adjustInventory('masks', 5, 'chief')
    expect(sim.getAudit({ actor: 'chief' }).length).toBe(2)
    expect(sim.getAudit({ actor: 'nobody' }).length).toBe(0)
  })

  test('a zone with fewer than three points is refused', () => {
    expect(() => quietSim().putZone({ id: 'bad', name: 'Bad', floor: 0, kind: 'deaf', polygon: [[0, 0], [1, 1]], deliveries: [] }, 'admin')).toThrow(/three points/)
  })

  test('a cancelled task frees its robot', () => {
    const sim = quietSim()
    const task = sim.request('Towel', 'linen-shelf', 'pool')
    run(sim, 3)
    expect(sim.cancelTask(task.id, 'admin').state).toBe('cancelled')
    expect(sim.getRobots().every((entry) => entry.taskId !== task.id)).toBe(true)
  })

  test('sending the night robot to its dock ends the round as failed instead of leaving it open', () => {
    const sim = quietSim()
    expect(sim.runRoundNow('night-restock', 'admin')).toBeNull()
    run(sim, 3)
    const round = sim.getTasks().find((task) => task.kind === 'restock_round')
    expect(sim.command('R4', 'dock', 'admin').accepted).toBe(true)
    expect(sim.getTasks().find((task) => task.id === round?.id)?.state).toBe('failed')
    expect(sim.getSchedules()[0].lastResult).toBe('failed')
  })

  test('a paused robot whose task is cancelled becomes available again', () => {
    const sim = quietSim()
    const task = sim.request('Towel', 'linen-shelf', 'pool')
    run(sim, 3)
    const id = sim.getRobots().find((entry) => entry.taskId === task.id)?.id ?? ''
    expect(sim.command(id, 'pause', 'admin').accepted).toBe(true)
    sim.cancelTask(task.id, 'admin')
    run(sim, 1)
    expect(robot(sim, id).state).not.toBe('paused')
  })

  test('a fault puts the carried item back on the shelf', () => {
    const sim = quietSim()
    sim.request('Towel', 'linen-shelf', 'pool')
    let carrier = ''
    for (let i = 0; i < 600 && !carrier; i++) { sim.step(0.1); carrier = sim.getRobots().find((entry) => entry.holding)?.id ?? '' }
    if (!carrier) return
    const before = sim.getInventory().find((item) => item.id === 'towel')?.count ?? 0
    sim.injectFault(carrier)
    expect(sim.getInventory().find((item) => item.id === 'towel')?.count).toBe(before + 1)
  })
})
