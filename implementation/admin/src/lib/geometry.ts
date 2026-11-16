import type { ClinicMap, Point } from '../types'

export interface Bounds {
  minX: number
  minY: number
  maxX: number
  maxY: number
  width: number
  depth: number
  centerX: number
  centerY: number
}

export function boundsOf(points: Point[]): Bounds {
  const xs = points.map((point) => point[0])
  const ys = points.map((point) => point[1])
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  return { minX, minY, maxX, maxY, width: maxX - minX, depth: maxY - minY, centerX: (minX + maxX) / 2, centerY: (minY + maxY) / 2 }
}

const EMPTY_BOUNDS: Bounds = { minX: 0, minY: 0, maxX: 24, maxY: 14, width: 24, depth: 14, centerX: 12, centerY: 7 }

export function mapBounds(map: ClinicMap): Bounds {
  const points = map.floors.flatMap((floor) => floor.outline)
  return points.length ? boundsOf(points) : EMPTY_BOUNDS
}

/** Ray casting. Points exactly on an edge count as inside or outside, either is fine for zones. */
export function pointInPolygon(x: number, y: number, polygon: Point[]): boolean {
  let inside = false
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i]
    const [xj, yj] = polygon[j]
    const crosses = yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi
    if (crosses) inside = !inside
  }
  return inside
}

export function centroid(polygon: Point[]): Point {
  let area = 0
  let cx = 0
  let cy = 0
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const cross = polygon[j][0] * polygon[i][1] - polygon[i][0] * polygon[j][1]
    area += cross
    cx += (polygon[j][0] + polygon[i][0]) * cross
    cy += (polygon[j][1] + polygon[i][1]) * cross
  }
  if (Math.abs(area) < 1e-9) {
    const bounds = boundsOf(polygon)
    return [bounds.centerX, bounds.centerY]
  }
  return [cx / (3 * area), cy / (3 * area)]
}

export function polygonArea(polygon: Point[]): number {
  let area = 0
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    area += polygon[j][0] * polygon[i][1] - polygon[i][0] * polygon[j][1]
  }
  return Math.abs(area) / 2
}

export function distanceToSegment(px: number, py: number, a: Point, b: Point): number {
  const dx = b[0] - a[0]
  const dy = b[1] - a[1]
  const lengthSquared = dx * dx + dy * dy
  const t = lengthSquared === 0 ? 0 : Math.max(0, Math.min(1, ((px - a[0]) * dx + (py - a[1]) * dy) / lengthSquared))
  return Math.hypot(px - (a[0] + t * dx), py - (a[1] + t * dy))
}

export function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}

/** Smallest signed difference between two angles, in [-π, π]. */
export function angleDelta(from: number, to: number): number {
  let delta = (to - from) % (Math.PI * 2)
  if (delta > Math.PI) delta -= Math.PI * 2
  if (delta < -Math.PI) delta += Math.PI * 2
  return delta
}

export function pathLength(path: Point[]): number {
  let total = 0
  for (let i = 1; i < path.length; i++) total += Math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1])
  return total
}

export function roundTo(value: number, step: number): number {
  return Math.round(value / step) * step
}
