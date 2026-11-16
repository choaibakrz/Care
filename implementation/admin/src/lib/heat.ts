/**
 * The heat map: where robots spend their time.
 *
 * The server counts it (`GET /stats/heat`, one grid per floor). The in-browser demo has no server,
 * so it counts the positions of its simulated robots here and answers in the same shape. Drawing
 * only ever reads a `HeatGrid`, whichever side counted it.
 */
import type { HeatGrid } from '../types'

const CELL_METRES = 1
const COLUMNS = 64
const ROWS = 64

const grids = new Map<number, Float32Array>()

function gridFor(floor: number): Float32Array {
  const existing = grids.get(floor)
  if (existing) return existing
  const created = new Float32Array(COLUMNS * ROWS)
  grids.set(floor, created)
  return created
}

/** Demo only: one simulated robot sample. */
export function recordHeat(floor: number, x: number, y: number): void {
  const column = Math.floor(x / CELL_METRES)
  const row = Math.floor(y / CELL_METRES)
  if (column < 0 || row < 0 || column >= COLUMNS || row >= ROWS) return
  gridFor(floor)[row * COLUMNS + column] += 1
}

/** Demo only: the counted samples of one floor, in the server's shape. */
export function localHeatGrid(floor: number): HeatGrid {
  const grid = grids.get(floor)
  return { floor, cellM: CELL_METRES, origin: [0, 0], columns: COLUMNS, rows: ROWS, counts: grid ? Array.from(grid) : new Array<number>(COLUMNS * ROWS).fill(0) }
}

/** Demo only: forget every sample (demo reset). */
export function clearHeat(): void {
  grids.clear()
}

export interface HeatCell {
  /** Centre of the cell, metres. */
  x: number
  y: number
  /** Side of the cell, metres. */
  size: number
  /** 0 to 1, compared with the busiest cell of the floor. */
  weight: number
}

/** The cells worth drawing: every cell with at least one sample. */
export function heatCells(grid: HeatGrid): HeatCell[] {
  const { counts, columns, cellM, origin } = grid
  let peak = 0
  for (const value of counts) if (value > peak) peak = value
  if (peak === 0 || columns <= 0) return []
  const cells: HeatCell[] = []
  for (let index = 0; index < counts.length; index++) {
    if (counts[index] <= 0) continue
    const column = index % columns
    const row = (index - column) / columns
    // Square root: a dock where a robot waits for minutes must not hide every corridor.
    cells.push({ x: origin[0] + (column + 0.5) * cellM, y: origin[1] + (row + 0.5) * cellM, size: cellM, weight: Math.sqrt(counts[index] / peak) })
  }
  return cells
}
