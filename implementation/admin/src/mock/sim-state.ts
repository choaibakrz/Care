/**
 * The state of the demo simulation, and the small helpers every part of it shares.
 *
 * The simulation is a little world that runs in the browser when no server is there.
 * Its inner state is changed in place, tick after tick, like a physics loop. Everything
 * that leaves it (`snapshot…` functions, live messages) is a fresh copy.
 */
import type { NavGrid } from '../lib/nav'
import { buildNavGrid } from '../lib/nav'
import type { AlertLevel, AuditEntry, AuditResult, ClinicMap, InventoryItem, LiveMessage, MapPlace, Incident, Point, Robot, Schedule, SystemMode, Task, Zone } from '../types'
import type { SimTablet } from './sim-tablets'
import { mockMap } from './world'

export type Phase = 'idle' | 'to_source' | 'picking' | 'to_dest' | 'dropping' | 'to_return' | 'returning' | 'to_home' | 'to_dock' | 'charging' | 'round_travel' | 'round_count'

export interface SimRobot {
  robot: Robot
  home: string
  phase: Phase
  path: Point[]
  pathIndex: number
  speed: number
  /** Seconds left to stand still (picking up, handing over, counting). */
  wait: number
  blockedFor: number
  idleFor: number
  linkDownUntil: number
  faultUntil: number
  roundQueue: string[]
  roundMismatches: number
  /** Set when the robot gave up waiting behind another robot. */
  stuck: boolean
}

export interface PendingDelivery {
  zoneId: string
  robotId: string
  at: number
}

export interface SimState {
  map: ClinicMap
  grids: Map<number, NavGrid>
  /** Simulated time, in milliseconds since the epoch. */
  clock: number
  random: () => number
  robots: SimRobot[]
  tasks: Task[]
  inventory: InventoryItem[]
  zones: Zone[]
  schedules: Schedule[]
  audit: AuditEntry[]
  outbox: LiveMessage[]
  deliveries: PendingDelivery[]
  nextTaskIn: number
  taskCount: number
  auditCount: number
  lastScheduleKey: string
  /** When false, no new request appears by itself. Tests use this. */
  autoTasks: boolean
  /** Normal or emergency operation (see `requirements/emergency-mode.md`). */
  mode: SystemMode
  /** Robots the emergency mode paused because they could not go to their dock; resumed when it ends. */
  pausedByEmergency: string[]
  tablets: SimTablet[]
  /** Seconds until the next battery report of every online tablet. */
  tabletReportIn: number
  incidents: Incident[]
  incidentCount: number
  /** Demo patient alarms and when the emergency service resolves them. */
  alarmEnds: Array<{ incidentId: string; at: number }>
}

export function mulberry32(seed: number): () => number {
  let state = seed >>> 0
  return () => {
    state = (state + 0x6d2b79f5) >>> 0
    let value = Math.imul(state ^ (state >>> 15), 1 | state)
    value = (value + Math.imul(value ^ (value >>> 7), 61 | value)) ^ value
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296
  }
}

export function buildGrids(map: ClinicMap): Map<number, NavGrid> {
  const grids = new Map<number, NavGrid>()
  for (const floor of map.floors) {
    const grid = buildNavGrid(map, floor.id)
    if (grid) grids.set(floor.id, grid)
  }
  return grids
}

export function iso(state: SimState): string {
  return new Date(state.clock).toISOString()
}

export function pick<T>(state: SimState, items: T[]): T {
  return items[Math.floor(state.random() * items.length)]
}

export function placeById(state: SimState, id: string | null): MapPlace | undefined {
  return id ? state.map.places.find((place) => place.id === id) : undefined
}

export function placeLabel(state: SimState, id: string | null): string {
  return placeById(state, id)?.label ?? id ?? 'unknown place'
}

export function emit(state: SimState, message: LiveMessage): void {
  state.outbox.push(message)
}

export function alert(state: SimState, level: AlertLevel, message: string): void {
  emit(state, { type: 'alert', level, message })
}

const AUDIT_LIMIT = 400

export function audit(state: SimState, actor: string, action: string, target: string, result: AuditResult = 'ok', detail: string | null = null): void {
  state.auditCount += 1
  const entry: AuditEntry = { id: `A-${String(state.auditCount).padStart(4, '0')}`, at: iso(state), actor, action, target, result, detail }
  state.audit = [entry, ...state.audit].slice(0, AUDIT_LIMIT)
}

export function copyRobot(robot: Robot): Robot {
  return { ...robot, position: { ...robot.position } }
}

export function copyTask(task: Task): Task {
  return { ...task, history: task.history.map((entry) => ({ ...entry })) }
}

export function copyZone(zone: Zone): Zone {
  return { ...zone, polygon: zone.polygon.map((point): Point => [point[0], point[1]]), deliveries: zone.deliveries.map((delivery) => ({ ...delivery })) }
}

export function copySchedule(schedule: Schedule): Schedule {
  return { ...schedule, lastCounts: schedule.lastCounts.map((count) => ({ ...count })) }
}

export function touchTask(state: SimState, task: Task, actor: string, label: string): void {
  task.updatedAt = iso(state)
  task.history.push({ at: task.updatedAt, actor, label })
  emit(state, { type: 'task.updated', task: copyTask(task) })
}

export function emitItem(state: SimState, item: InventoryItem): void {
  item.updatedAt = iso(state)
  emit(state, { type: 'inventory.updated', item: { ...item } })
}

export function simRobot(state: SimState, robotId: string): SimRobot | undefined {
  return state.robots.find((entry) => entry.robot.id === robotId)
}

export function defaultMap(): ClinicMap {
  return mockMap
}
