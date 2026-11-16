import { describe, expect, it } from 'vitest'
import { countModifications, diffOverlay, nextFloorId } from './plan'
import type { ClinicPlan } from '../types'

const base: ClinicPlan = {
  name: 'X',
  floors: [{ id: 0, label: 'Ground', outline: [[0, 0], [10, 0], [10, 10], [0, 10]] }],
  rooms: [{ id: 'a', floor: 0, label: 'A', kind: 'room', polygon: [[0, 0], [5, 0], [5, 5], [0, 5]] }],
  walls: [],
  places: [],
  props: [{ id: 'p1', floor: 0, kind: 'bed', x: 1, y: 1, width: 1, depth: 2, solid: true }, { id: 'p2', floor: 0, kind: 'plant', x: 3, y: 3, width: 1, depth: 1, solid: false }],
}

describe('diffOverlay', () => {
  it('is empty for an unchanged draft', () => {
    expect(countModifications(diffOverlay(base, structuredClone(base), 1))).toBe(0)
  })
  it('lists changed, added and removed items by id', () => {
    const draft = structuredClone(base)
    draft.props = [{ ...draft.props[0], x: 2 }, { id: 'p3', floor: 0, kind: 'sofa', x: 5, y: 5, width: 2, depth: 1, solid: true }]
    draft.floors.push({ id: nextFloorId(draft), label: 'Floor 1', outline: [] })
    const overlay = diffOverlay(base, draft, 1)
    expect(overlay.upsert.props.map((prop) => prop.id)).toEqual(['p1', 'p3'])
    expect(overlay.remove.props).toEqual(['p2'])
    expect(overlay.upsert.floors.map((floor) => floor.id)).toEqual([1])
    expect(countModifications(overlay)).toBe(4)
  })
})
