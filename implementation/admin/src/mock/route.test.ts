import { describe, expect, test } from 'vitest'
import type { Robot, Task } from '../types'
import { estimateRoute } from './route'
import { mockMap } from './world'

const shelf = mockMap.places.find((place) => place.kind === 'shelf')
const room = mockMap.places.find((place) => place.kind === 'room' && place.floor === shelf?.floor && place.id !== shelf?.id)

function task(overrides: Partial<Task> = {}): Task {
  if (!shelf || !room) throw new Error('the demo clinic needs a shelf and a room on one floor')
  return { id: 't-1', kind: 'fetch', item: 'blanket', fromPlace: shelf.id, toPlace: room.id, state: 'en_route', robotId: 'r1', requestedBy: 'nurse', createdAt: '', updatedAt: '', reason: null, history: [], ...overrides }
}

function robotAt(x: number, y: number, floor: number, holding: string | null): Robot {
  return { id: 'r1', name: 'r1', role: '', simulated: true, position: { x, y, heading: 0, floor }, battery: 90, state: 'busy', holding, micOpen: true, taskId: 't-1', lastSeen: '', inDeafZone: false, goingHome: false, mood: 'busy' }
}

describe('demo route estimate', () => {
  test('without a robot it goes from the shelf to the room', () => {
    const route = estimateRoute(mockMap, task({ robotId: null }), undefined)
    expect(route?.points[0]).toEqual([shelf?.x, shelf?.y])
    expect(route?.points.at(-1)).toEqual([room?.x, room?.y])
    expect(route?.estimate).toBe(true)
    expect(route?.lengthM).toBeGreaterThan(0)
  })

  test('a robot still to pick the item up goes through the shelf', () => {
    if (!shelf || !room) throw new Error('missing places')
    const route = estimateRoute(mockMap, task(), robotAt(room.x, room.y, room.floor, null))
    expect(route?.points[0]).toEqual([room.x, room.y])
    expect(route?.points).toContainEqual([shelf.x, shelf.y])
  })

  test('a robot that carries the item goes straight to the room', () => {
    if (!shelf || !room) throw new Error('missing places')
    const route = estimateRoute(mockMap, task(), robotAt(shelf.x, shelf.y, shelf.floor, 'blanket'))
    expect(route?.points[0]).toEqual([shelf.x, shelf.y])
    expect(route?.points.at(-1)).toEqual([room.x, room.y])
  })

  test('a night round has no single route', () => {
    expect(estimateRoute(mockMap, task({ kind: 'restock_round' }), undefined)).toBeNull()
  })
})
