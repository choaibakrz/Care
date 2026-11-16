import { describe, expect, test } from 'vitest'
import { mockMap } from '../mock/world'
import type { Point } from '../types'
import { distanceToSegment, pointInPolygon } from './geometry'
import { buildNavGrid, findPath, isFree } from './nav'
import type { NavGrid } from './nav'

const grids = new Map<number, NavGrid>()

function grid(floor: number): NavGrid {
  const built = grids.get(floor) ?? buildNavGrid(mockMap, floor)
  if (!built) throw new Error('no grid')
  grids.set(floor, built)
  return built
}

function clearanceToWalls(floor: number, path: Point[]): number {
  const segments = mockMap.walls.filter((wall) => wall.floor === floor).flatMap((wall) => wall.points.slice(1).map((point, index): [Point, Point] => [wall.points[index], point]))
  let smallest = Infinity
  for (let i = 1; i < path.length; i++) {
    for (let step = 0; step <= 10; step++) {
      const x = path[i - 1][0] + ((path[i][0] - path[i - 1][0]) * step) / 10
      const y = path[i - 1][1] + ((path[i][1] - path[i - 1][1]) * step) / 10
      for (const [a, b] of segments) smallest = Math.min(smallest, distanceToSegment(x, y, a, b))
    }
  }
  return smallest
}

describe('route planner', () => {
  test('every named place stands on free ground', () => {
    for (const place of mockMap.places) expect(isFree(grid(place.floor), place.x, place.y), place.id).toBe(true)
  })

  test('every place can be reached from every other place of its floor', () => {
    for (const floor of mockMap.floors) {
      const places = mockMap.places.filter((place) => place.floor === floor.id)
      for (const from of places) for (const to of places) {
        if (from === to) continue
        expect(findPath(grid(floor.id), [from.x, from.y], [to.x, to.y]), `${from.id} to ${to.id}`).not.toBeNull()
      }
    }
  })

  test('a path never comes closer to a wall than the robot body', () => {
    for (const floor of mockMap.floors) {
      const places = mockMap.places.filter((place) => place.floor === floor.id)
      for (const from of places) for (const to of places) {
        if (from === to) continue
        const path = findPath(grid(floor.id), [from.x, from.y], [to.x, to.y]) as Point[]
        expect(clearanceToWalls(floor.id, path), `${from.id} to ${to.id}`).toBeGreaterThan(0.3)
      }
    }
  })

  test('a path never crosses solid furniture', () => {
    const solids = mockMap.props.filter((prop) => prop.floor === 2 && prop.solid)
    const path = findPath(grid(2), [1.5, 11.0], [20.4, 10.4]) as Point[]
    for (const [x, y] of path) for (const prop of solids) {
      expect(Math.abs(x - prop.x) < prop.width / 2 && Math.abs(y - prop.y) < prop.depth / 2, `${prop.kind} at ${prop.x},${prop.y}`).toBe(false)
    }
  })

  test('a goal inside the elevator is moved outside: robots never enter it', () => {
    const path = findPath(grid(0), [4, 7], [8.5, 2.5]) as Point[]
    const end = path[path.length - 1]
    const elevator = mockMap.rooms.find((room) => room.id === 'elevator-0')
    expect(pointInPolygon(end[0], end[1], elevator?.polygon ?? [])).toBe(false)
  })

  test('drives around a robot standing in the corridor', () => {
    const path = findPath(grid(2), [2, 7], [22, 7], [{ x: 12, y: 7, radius: 0.85 }]) as Point[]
    expect(path.every(([x, y]) => Math.hypot(x - 12, y - 7) >= 0.75)).toBe(true)
  })
})
