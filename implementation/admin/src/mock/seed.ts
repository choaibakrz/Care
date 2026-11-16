/** INVENTED DATA, for the demo only: the four robots of `flotte.yaml`, a small stock, two zones. */
import type { InventoryItem, Robot, Schedule, Zone } from '../types'
import type { SimRobot, SimState } from './sim-state'
import { placeById } from './sim-state'

interface RobotSeed {
  id: string
  role: string
  home: string
  battery: number
  heading: number
  simulated: boolean
}

const ROBOT_SEEDS: RobotSeed[] = [
  { id: 'R1', role: 'Reception', home: 'dock-a', battery: 88, heading: 0, simulated: false },
  { id: 'R2', role: 'Ward', home: 'dock-w', battery: 71, heading: 0, simulated: true },
  { id: 'R3', role: 'Therapy', home: 'dock-b', battery: 64, heading: Math.PI, simulated: true },
  { id: 'R4', role: 'Night', home: 'dock-n', battery: 93, heading: 0, simulated: true },
]

export function seedRobots(state: SimState): SimRobot[] {
  return ROBOT_SEEDS.map((seed) => {
    const home = placeById(state, seed.home)
    if (!home) throw new Error(`Unknown home place for ${seed.id}: ${seed.home}`)
    const robot: Robot = {
      id: seed.id,
      name: `${seed.id} · ${seed.role}`,
      role: seed.role,
      simulated: seed.simulated,
      position: { x: home.x, y: home.y, heading: seed.heading, floor: home.floor },
      battery: seed.battery,
      state: 'idle',
      holding: null,
      micOpen: true,
      taskId: null,
      lastSeen: new Date(state.clock).toISOString(),
      inDeafZone: false,
      goingHome: false,
      mood: 'happy',
    }
    return { robot, home: seed.home, phase: 'idle', path: [], pathIndex: 0, speed: 0, wait: 0, blockedFor: 0, idleFor: 0, linkDownUntil: 0, faultUntil: 0, roundQueue: [], roundMismatches: 0, stuck: false }
  })
}

type ItemSeed = [id: string, label: string, place: string, count: number, lowAt: number]

const ITEM_SEEDS: ItemSeed[] = [
  ['blanket', 'Blanket', 'supply-a', 9, 4],
  ['neck-pillow', 'Neck pillow', 'supply-a', 6, 3],
  ['large-pillow', 'Large pillow', 'supply-a', 3, 3],
  ['water-bottle', 'Water bottle', 'supply-b', 16, 6],
  ['exercise-sheet', 'Exercise sheet', 'supply-b', 24, 10],
  ['gloves', 'Nitrile gloves (box)', 'nurse-cabinet', 7, 4],
  ['masks', 'Surgical masks (box)', 'nurse-cabinet', 3, 4],
  ['towel', 'Towel', 'linen-shelf', 14, 6],
  ['therapy-band', 'Therapy band', 'linen-shelf', 6, 4],
  ['welcome-folder', 'Welcome folder', 'reception', 9, 5],
]

export function seedInventory(state: SimState): InventoryItem[] {
  const at = new Date(state.clock).toISOString()
  return ITEM_SEEDS.map(([id, label, place, count, lowAt]) => ({ id, label, place, count, lowAt, lastRobotCount: null, lastRobotCountAt: null, updatedAt: at }))
}

/** Where a fetched item can be asked for, by shelf. Always on the shelf's own floor. */
export const DESTINATIONS: Record<string, string[]> = {
  'supply-a': ['room-11', 'room-12', 'room-13', 'room-14', 'lounge'],
  'supply-b': ['room-11', 'room-12', 'room-13', 'room-14', 'lounge', 'nurse-station'],
  'nurse-cabinet': ['room-11', 'room-12', 'room-13', 'room-14'],
  'linen-shelf': ['therapy-1', 'therapy-2', 'pool'],
  reception: ['hall', 'therapy-1', 'therapy-2'],
}

export const REQUESTERS = ['nurse', 'nurse', 'therapist', 'doctor', 'reception']

export function seedZones(robotIds: string[]): Zone[] {
  const received = robotIds.map((robotId) => ({ robotId, status: 'received' as const }))
  return [
    { id: 'zone-therapy-2', name: 'Therapy 2 · confidential talks', floor: 0, kind: 'deaf', polygon: [[17, 0], [24, 0], [24, 5.5], [17, 5.5]], deliveries: received.map((entry) => ({ ...entry })) },
    { id: 'zone-room-12', name: 'Room 12 · rest', floor: 2, kind: 'deaf', polygon: [[17, 0], [24, 0], [24, 5.5], [17, 5.5]], deliveries: received.map((entry) => ({ ...entry })) },
    { id: 'zone-pool-edge', name: 'Pool edge', floor: 0, kind: 'restricted', polygon: [[11.4, 9.9], [21.6, 9.9], [21.6, 13.9], [11.4, 13.9]], deliveries: received.map((entry) => ({ ...entry })) },
  ]
}

export function seedSchedules(): Schedule[] {
  return [{ id: 'night-restock', label: 'Night restock round', enabled: true, time: '02:30', robotId: 'R4', lastRun: null, lastResult: 'never', lastCounts: [] }]
}

export function fullCount(itemId: string): number {
  return ITEM_SEEDS.find((seed) => seed[0] === itemId)?.[3] ?? 5
}
