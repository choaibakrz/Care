/** Small helpers of the building editor. */
import type { ClinicPlan, PlanOverlay } from '../types'

/** The shapes a 422 names, as `rooms:2`, from paths like `rooms[2].polygon` or `rooms.2.polygon`. */
export function problemShapes(details: Array<{ path: string }>): Set<string> {
  const shapes = new Set<string>()
  for (const detail of details) {
    const found = /(rooms|walls|places|props|floors)(?:\[|\.)(\d+)/.exec(detail.path)
    if (found) shapes.add(`${found[1]}:${found[2]}`)
  }
  return shapes
}

/** A fresh id for a new room, wall or place. */
export function newId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 7)}`
}

function same(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

/** What the draft changes against the base, by id: items that are new or differ, and base ids that are gone. */
function diffList<T, K extends string | number>(base: T[], draft: T[], key: (item: T) => K): { upsert: T[]; remove: K[] } {
  const before = new Map(base.map((item) => [key(item), item]))
  const kept = new Set(draft.map(key))
  return {
    upsert: draft.filter((item) => !same(before.get(key(item)), item)),
    remove: base.map(key).filter((id) => !kept.has(id)),
  }
}

export function diffOverlay(base: ClinicPlan, draft: ClinicPlan, baseVersion: number): PlanOverlay {
  const floors = diffList(base.floors, draft.floors, (item) => item.id)
  const rooms = diffList(base.rooms, draft.rooms, (item) => item.id)
  const walls = diffList(base.walls, draft.walls, (item) => item.id)
  const places = diffList(base.places, draft.places, (item) => item.id)
  const props = diffList(base.props, draft.props, (item) => item.id)
  return {
    base_version: baseVersion,
    upsert: { floors: floors.upsert, rooms: rooms.upsert, walls: walls.upsert, places: places.upsert, props: props.upsert },
    remove: { floors: floors.remove, rooms: rooms.remove, walls: walls.remove, places: places.remove, props: props.remove },
  }
}

export function countModifications(overlay: PlanOverlay): number {
  return Object.values(overlay.upsert).reduce((sum, items) => sum + items.length, 0) + Object.values(overlay.remove).reduce((sum, ids) => sum + ids.length, 0)
}

/** The next free floor level. */
export function nextFloorId(plan: ClinicPlan): number {
  return plan.floors.reduce((top, floor) => Math.max(top, floor.id), -1) + 1
}
