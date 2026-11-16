import { describe, expect, test } from 'vitest'
import { problemShapes } from './plan'
import { toClinicSummary, toFleetHome, toPlan, toHeat, toLiveMessage, toMap, toRobot, toRoute, toTask } from './adapt'
import { taskTitle } from './format'
import { heatCells } from './heat'

// Copied from the server's docs/ws_messages.md and from what `clinic-server --mock` answers.
const MAP_UPDATED = { type: 'map.updated', id: '00000000-0000-4000-8000-000000000001', ts: '2026-11-14T08:00:00Z', active: true, clinic_id: 'seed', version: 2 }
const RESYNC = { type: 'resync', id: '00000000-0000-4000-8000-000000000001', ts: '2026-11-14T08:00:00Z' }

describe('map messages', () => {
  test('map.updated is read with its clinic, version and active flag', () => {
    expect(toLiveMessage(MAP_UPDATED)).toEqual({ type: 'map.updated', clinicId: 'seed', version: 2, active: true })
  })

  test('map.updated about an inactive plan says so', () => {
    expect(toLiveMessage({ ...MAP_UPDATED, active: false })).toMatchObject({ active: false })
  })

  test('map.updated without a clinic is dropped', () => {
    expect(toLiveMessage({ type: 'map.updated', version: 2, active: true })).toBeNull()
  })

  test('resync is read', () => {
    expect(toLiveMessage(RESYNC)).toEqual({ type: 'resync' })
  })

  test('the map keeps the plan identity of GET /map', () => {
    const map = toMap({ clinic_id: 'seed', version: 1, name: 'Demo clinic', floors: [{ id: 0, label: 'Ground floor', outline: [[0, 0], [24, 0], [24, 14], [0, 14]] }], rooms: [], walls: [], places: [], props: [] })
    expect(map.clinicId).toBe('seed')
    expect(map.version).toBe(1)
  })
})

describe('heat grid', () => {
  test('GET /stats/heat is read', () => {
    const grid = toHeat({ floor: 2, cell_m: 1.0, origin: [3.0, 4.0], columns: 3, rows: 2, counts: [0, 4, 0, 1, 0, 0] })
    expect(grid).toEqual({ floor: 2, cellM: 1, origin: [3, 4], columns: 3, rows: 2, counts: [0, 4, 0, 1, 0, 0] })
  })

  test('counts that do not fill the grid are refused', () => {
    expect(toHeat({ floor: 0, cell_m: 1, origin: [0, 0], columns: 3, rows: 2, counts: [1, 2] })).toBeNull()
  })

  test('cells are placed from the origin, row 0 on the north edge, weighted by the busiest cell', () => {
    const cells = heatCells({ floor: 0, cellM: 1, origin: [3, 4], columns: 3, rows: 2, counts: [0, 4, 0, 1, 0, 0] })
    expect(cells).toEqual([
      { x: 4.5, y: 4.5, size: 1, weight: 1 },
      { x: 3.5, y: 5.5, size: 1, weight: 0.5 },
    ])
  })

  test('an empty floor draws nothing', () => {
    expect(heatCells({ floor: 0, cellM: 1, origin: [0, 0], columns: 2, rows: 1, counts: [0, 0] })).toEqual([])
  })
})

describe('task route', () => {
  test('GET /tasks/{id}/route is read', () => {
    expect(toRoute({ floor: 2, points: [[2.0, 7.0], [12.0, 7.0], [12.0, 3.0]], length_m: 14.0, estimate: true })).toEqual({ floor: 2, points: [[2, 7], [12, 7], [12, 3]], lengthM: 14, estimate: true })
  })

  test('a route with fewer than two points is not drawn', () => {
    expect(toRoute({ floor: 0, points: [[1, 1]], length_m: 0, estimate: true })).toBeNull()
  })
})

describe('follow tasks', () => {
  test('a follow task shows the pseudonym of the tablet it follows', () => {
    const task = toTask({ id: 't-9', kind: 'follow', to_place: 'room-12', state: 'en_route', robot_id: 'r2', requested_by: 'Admin (mock)', target_device: 'tab-dr-a', target_label: 'Dr. A', history: [] })
    expect(task).toMatchObject({ kind: 'follow', targetLabel: 'Dr. A' })
    expect(task && taskTitle(task)).toBe('Following Dr. A')
  })
})

describe('clinic plans', () => {
  test('GET /clinics rows and plans are read, unknown plan fields kept', () => {
    expect(toClinicSummary({ id: 'seed', name: 'Demo clinic', version: 3, active: true, updated_at: '2026-11-15T10:00:00Z' })).toEqual({ id: 'seed', name: 'Demo clinic', version: 3, active: true, updatedAt: '2026-11-15T10:00:00Z' })
    const plan = toPlan({ name: 'X', floors: [], rooms: [], walls: [], places: [], props: [], marque: 'm' })
    expect(plan?.marque).toBe('m')
    expect(toPlan({ floors: [] })).toBeNull()
  })

  test('422 paths point at shapes', () => {
    expect([...problemShapes([{ path: 'rooms[2].polygon' }, { path: 'walls.0.points' }, { path: 'name' }])]).toEqual(['rooms:2', 'walls:0'])
  })
})

describe('robot mood', () => {
  const ROBOT = { id: 'S1', name: 'S1', role: 'Ward', simulated: true, pos: { x: 3, y: 4, heading: 0, floor: 0 }, battery: 80, state: 'idle', holding: null, mic_open: true, task_id: null, last_seen: '2026-11-16T08:00:00Z' }

  test('the server mood and flags are read', () => {
    expect(toRobot({ ...ROBOT, mood: 'charging', in_deaf_zone: false, going_home: true })).toMatchObject({ mood: 'charging', inDeafZone: false, goingHome: true })
  })

  test('an older server without mood gets one from the state and the microphone', () => {
    expect(toRobot(ROBOT)).toMatchObject({ mood: 'happy', inDeafZone: false, goingHome: false })
    expect(toRobot({ ...ROBOT, mic_open: false })).toMatchObject({ mood: 'deaf', inDeafZone: true })
    expect(toRobot({ ...ROBOT, state: 'busy' })?.mood).toBe('busy')
    expect(toRobot({ ...ROBOT, state: 'estop', mic_open: false })).toMatchObject({ mood: 'stopped', inDeafZone: false })
    expect(toRobot({ ...ROBOT, mood: 'grumpy', state: 'fault' })?.mood).toBe('alarm')
  })

  test('the fleet home is read, the floor as a string too', () => {
    expect(toFleetHome({ place_id: 'dock-a', label: 'Dock A', floor: '0' })).toEqual({ placeId: 'dock-a', label: 'Dock A', floor: 0 })
    expect(toFleetHome({ place_id: null, label: null, floor: null })).toEqual({ placeId: null, label: null, floor: null })
  })
})
