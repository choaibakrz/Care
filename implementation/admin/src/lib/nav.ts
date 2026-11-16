/**
 * Route planner on a floor plan.
 *
 * The floor is cut into small cells. A cell is blocked when a wall, a solid piece of
 * furniture or the outside of the building is closer than the robot's body. A* finds the
 * cell path, then the path is straightened and its corners are rounded.
 *
 * Used twice: by the demo simulation to drive the fake robots, and by the map to draw the
 * planned route of a task. The real robot plans its own way: the drawn route is an estimate.
 */
import type { ClinicMap, Point } from '../types'
import { boundsOf, distanceToSegment, pointInPolygon } from './geometry'

const CELL = 0.2
const WALL_HALF_THICKNESS = 0.08
const ROBOT_CLEARANCE = 0.42
const CORNER_RADIUS = 0.55
const SQRT2 = Math.SQRT2

export interface NavGrid {
  floor: number
  cols: number
  rows: number
  originX: number
  originY: number
  blocked: Uint8Array
  /** 1 when a blocked cell is right next to this one: A* avoids hugging obstacles. */
  near: Uint8Array
}

export interface Disc {
  x: number
  y: number
  radius: number
}

function cellIndex(grid: NavGrid, col: number, row: number): number {
  return row * grid.cols + col
}

function toCell(grid: NavGrid, x: number, y: number): [number, number] {
  return [Math.floor((x - grid.originX) / CELL), Math.floor((y - grid.originY) / CELL)]
}

function cellCenter(grid: NavGrid, col: number, row: number): Point {
  return [grid.originX + (col + 0.5) * CELL, grid.originY + (row + 0.5) * CELL]
}

function inGrid(grid: NavGrid, col: number, row: number): boolean {
  return col >= 0 && row >= 0 && col < grid.cols && row < grid.rows
}

export function buildNavGrid(map: ClinicMap, floorId: number): NavGrid | null {
  const floor = map.floors.find((entry) => entry.id === floorId)
  if (!floor) return null
  const bounds = boundsOf(floor.outline)
  const cols = Math.ceil(bounds.width / CELL)
  const rows = Math.ceil(bounds.depth / CELL)
  const grid: NavGrid = { floor: floorId, cols, rows, originX: bounds.minX, originY: bounds.minY, blocked: new Uint8Array(cols * rows), near: new Uint8Array(cols * rows) }

  const segments: Array<[Point, Point]> = map.walls
    .filter((wall) => wall.floor === floorId)
    .flatMap((wall) => wall.points.slice(1).map((point, index): [Point, Point] => [wall.points[index], point]))
  const solids = map.props.filter((prop) => prop.floor === floorId && prop.solid)
  const closedRooms = map.rooms.filter((room) => room.floor === floorId && room.kind === 'elevator')
  const wallReach = WALL_HALF_THICKNESS + ROBOT_CLEARANCE

  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      const [x, y] = cellCenter(grid, col, row)
      const outside = !pointInPolygon(x, y, floor.outline)
      const inClosedRoom = closedRooms.some((room) => pointInPolygon(x, y, room.polygon))
      const nearWall = segments.some(([a, b]) => distanceToSegment(x, y, a, b) < wallReach)
      const nearProp = solids.some((prop) => Math.abs(x - prop.x) < prop.width / 2 + ROBOT_CLEARANCE && Math.abs(y - prop.y) < prop.depth / 2 + ROBOT_CLEARANCE)
      if (outside || inClosedRoom || nearWall || nearProp) grid.blocked[cellIndex(grid, col, row)] = 1
    }
  }
  markNear(grid)
  return grid
}

function markNear(grid: NavGrid): void {
  for (let row = 0; row < grid.rows; row++) {
    for (let col = 0; col < grid.cols; col++) {
      if (grid.blocked[cellIndex(grid, col, row)]) continue
      for (let dr = -1; dr <= 1; dr++) {
        for (let dc = -1; dc <= 1; dc++) {
          if (inGrid(grid, col + dc, row + dr) && grid.blocked[cellIndex(grid, col + dc, row + dr)]) grid.near[cellIndex(grid, col, row)] = 1
        }
      }
    }
  }
}

function isBlocked(grid: NavGrid, col: number, row: number, discs: Disc[]): boolean {
  if (!inGrid(grid, col, row)) return true
  if (grid.blocked[cellIndex(grid, col, row)]) return true
  if (!discs.length) return false
  const [x, y] = cellCenter(grid, col, row)
  return discs.some((disc) => Math.hypot(x - disc.x, y - disc.y) < disc.radius)
}

/** Nearest free cell, searched in growing squares. Lets a goal sit a little inside an obstacle. */
function nearestFree(grid: NavGrid, col: number, row: number, discs: Disc[]): [number, number] | null {
  if (!isBlocked(grid, col, row, discs)) return [col, row]
  for (let radius = 1; radius <= 12; radius++) {
    let best: [number, number] | null = null
    let bestDistance = Infinity
    for (let dr = -radius; dr <= radius; dr++) {
      for (let dc = -radius; dc <= radius; dc++) {
        if (Math.max(Math.abs(dr), Math.abs(dc)) !== radius) continue
        if (isBlocked(grid, col + dc, row + dr, discs)) continue
        const distance = Math.hypot(dc, dr)
        if (distance < bestDistance) { best = [col + dc, row + dr]; bestDistance = distance }
      }
    }
    if (best) return best
  }
  return null
}

class MinHeap {
  private readonly nodes: number[] = []
  private readonly scores: number[] = []

  get size(): number { return this.nodes.length }

  push(node: number, score: number): void {
    this.nodes.push(node)
    this.scores.push(score)
    let index = this.nodes.length - 1
    while (index > 0) {
      const parent = (index - 1) >> 1
      if (this.scores[parent] <= this.scores[index]) break
      this.swap(parent, index)
      index = parent
    }
  }

  pop(): number {
    const top = this.nodes[0]
    const lastNode = this.nodes.pop() as number
    const lastScore = this.scores.pop() as number
    if (this.nodes.length) {
      this.nodes[0] = lastNode
      this.scores[0] = lastScore
      this.sink(0)
    }
    return top
  }

  private sink(start: number): void {
    let index = start
    for (;;) {
      const left = index * 2 + 1
      const right = left + 1
      let smallest = index
      if (left < this.nodes.length && this.scores[left] < this.scores[smallest]) smallest = left
      if (right < this.nodes.length && this.scores[right] < this.scores[smallest]) smallest = right
      if (smallest === index) return
      this.swap(smallest, index)
      index = smallest
    }
  }

  private swap(a: number, b: number): void {
    const node = this.nodes[a]; this.nodes[a] = this.nodes[b]; this.nodes[b] = node
    const score = this.scores[a]; this.scores[a] = this.scores[b]; this.scores[b] = score
  }
}

const NEIGHBOURS: Array<[number, number, number]> = [[1, 0, 1], [-1, 0, 1], [0, 1, 1], [0, -1, 1], [1, 1, SQRT2], [1, -1, SQRT2], [-1, 1, SQRT2], [-1, -1, SQRT2]]

function searchCells(grid: NavGrid, start: [number, number], goal: [number, number], discs: Disc[]): Array<[number, number]> | null {
  const total = grid.cols * grid.rows
  const cost = new Float32Array(total).fill(Infinity)
  const parent = new Int32Array(total).fill(-1)
  const closed = new Uint8Array(total)
  const startIndex = cellIndex(grid, start[0], start[1])
  const goalIndex = cellIndex(grid, goal[0], goal[1])
  const heap = new MinHeap()
  cost[startIndex] = 0
  heap.push(startIndex, 0)

  while (heap.size) {
    const current = heap.pop()
    if (current === goalIndex) break
    if (closed[current]) continue
    closed[current] = 1
    const col = current % grid.cols
    const row = (current - col) / grid.cols
    for (const [dc, dr, step] of NEIGHBOURS) {
      const nextCol = col + dc
      const nextRow = row + dr
      if (isBlocked(grid, nextCol, nextRow, discs)) continue
      // No squeezing diagonally between two obstacles.
      if (dc !== 0 && dr !== 0 && (isBlocked(grid, col + dc, row, discs) || isBlocked(grid, col, row + dr, discs))) continue
      const next = cellIndex(grid, nextCol, nextRow)
      const nextCost = cost[current] + step * (grid.near[next] ? 2.6 : 1)
      if (nextCost >= cost[next]) continue
      cost[next] = nextCost
      parent[next] = current
      const dx = Math.abs(goal[0] - nextCol)
      const dy = Math.abs(goal[1] - nextRow)
      heap.push(next, nextCost + Math.max(dx, dy) + (SQRT2 - 1) * Math.min(dx, dy))
    }
  }

  if (parent[goalIndex] === -1 && goalIndex !== startIndex) return null
  const cells: Array<[number, number]> = []
  for (let index = goalIndex; index !== -1; index = parent[index]) {
    const col = index % grid.cols
    cells.push([col, (index - col) / grid.cols])
  }
  return cells.reverse()
}

function lineIsFree(grid: NavGrid, a: Point, b: Point, discs: Disc[]): boolean {
  const steps = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) / (CELL / 2)))
  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    const [col, row] = toCell(grid, a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
    if (isBlocked(grid, col, row, discs)) return false
  }
  return true
}

/** Drops every point the robot can skip by driving straight. */
function straighten(grid: NavGrid, points: Point[], discs: Disc[]): Point[] {
  const result: Point[] = [points[0]]
  let anchor = 0
  while (anchor < points.length - 1) {
    let reach = points.length - 1
    while (reach > anchor + 1 && !lineIsFree(grid, points[anchor], points[reach], discs)) reach--
    result.push(points[reach])
    anchor = reach
  }
  return result
}

/** Replaces each sharp corner with a short curve, when the curve stays clear of obstacles. */
function roundCorners(grid: NavGrid, points: Point[], discs: Disc[]): Point[] {
  if (points.length < 3) return points
  const result: Point[] = [points[0]]
  for (let i = 1; i < points.length - 1; i++) {
    const previous = points[i - 1]
    const corner = points[i]
    const next = points[i + 1]
    const inLength = Math.hypot(corner[0] - previous[0], corner[1] - previous[1])
    const outLength = Math.hypot(next[0] - corner[0], next[1] - corner[1])
    const radius = Math.min(CORNER_RADIUS, inLength / 2, outLength / 2)
    if (radius < 0.08) { result.push(corner); continue }
    const enter: Point = [corner[0] + ((previous[0] - corner[0]) / inLength) * radius, corner[1] + ((previous[1] - corner[1]) / inLength) * radius]
    const leave: Point = [corner[0] + ((next[0] - corner[0]) / outLength) * radius, corner[1] + ((next[1] - corner[1]) / outLength) * radius]
    const curve: Point[] = []
    for (let step = 0; step <= 6; step++) {
      const t = step / 6
      const u = 1 - t
      curve.push([u * u * enter[0] + 2 * u * t * corner[0] + t * t * leave[0], u * u * enter[1] + 2 * u * t * corner[1] + t * t * leave[1]])
    }
    const clear = curve.every((point) => { const [col, row] = toCell(grid, point[0], point[1]); return !isBlocked(grid, col, row, discs) })
    if (clear) result.push(...curve)
    else result.push(corner)
  }
  result.push(points[points.length - 1])
  return result
}

/**
 * Plans a way from one point to another on one floor.
 * `discs` are temporary obstacles, used to drive around another robot.
 * Returns null when there is no way.
 */
export function findPath(grid: NavGrid, from: Point, to: Point, discs: Disc[] = []): Point[] | null {
  const [fromCol, fromRow] = toCell(grid, from[0], from[1])
  const [toCol, toRow] = toCell(grid, to[0], to[1])
  // A robot standing next to an obstacle must still be able to leave: ignore discs at the start.
  const start = nearestFree(grid, fromCol, fromRow, [])
  const goal = nearestFree(grid, toCol, toRow, discs)
  if (!start || !goal) return null
  const cells = searchCells(grid, start, goal, discs)
  if (!cells) return null
  const end: Point = isBlocked(grid, toCol, toRow, discs) ? cellCenter(grid, goal[0], goal[1]) : to
  const raw: Point[] = [from, ...cells.slice(1, -1).map(([col, row]) => cellCenter(grid, col, row)), end]
  return roundCorners(grid, straighten(grid, raw, discs), discs)
}

export function isFree(grid: NavGrid, x: number, y: number): boolean {
  const [col, row] = toCell(grid, x, y)
  return !isBlocked(grid, col, row, [])
}
