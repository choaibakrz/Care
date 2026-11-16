/**
 * What the 3D map asks the server for on its own, outside the live stream: the estimated route of
 * the selected robot's task and the heat map. Both are polled while they are on screen and kept
 * when a poll fails, so a short drop never blanks the map.
 */
import { useEffect, useState } from 'react'
import { backend } from '../lib/backend'
import type { HeatGrid, Robot, Task, TaskRoute } from '../types'

/** The server plans from where the robot is now: ask again while it moves. */
export const ROUTE_REFRESH_MS = 3000
export const HEAT_REFRESH_MS = 5000

export function useTaskRoute(token: string | null, robot: Robot | undefined, task: Task | undefined): TaskRoute | null {
  const [route, setRoute] = useState<{ taskId: string; route: TaskRoute | null } | null>(null)
  const taskId = task && task.kind !== 'restock_round' ? task.id : null
  // A new state or a picked-up item changes the path at once: ask without waiting for the timer.
  const changeKey = `${task?.state}|${robot?.holding}|${robot?.position.floor}`

  useEffect(() => {
    if (!token || !taskId) return undefined
    let stopped = false
    const ask = (): void => {
      backend.getTaskRoute(token, taskId).then(
        (next) => { if (!stopped) setRoute({ taskId, route: next }) },
        () => { /* Keep the last route: the next poll tries again. */ },
      )
    }
    ask()
    const timer = window.setInterval(ask, ROUTE_REFRESH_MS)
    return () => { stopped = true; window.clearInterval(timer) }
  }, [token, taskId, changeKey])

  // An answer for another task is never shown, even for the moment before the new one arrives.
  return route && route.taskId === taskId ? route.route : null
}

export function useHeat(token: string | null, floors: number[], enabled: boolean): Map<number, HeatGrid> {
  const [grids, setGrids] = useState<Map<number, HeatGrid>>(() => new Map())
  const floorKey = floors.join(',')

  useEffect(() => {
    if (!token || !enabled || !floorKey) return undefined
    let stopped = false
    const wanted = floorKey.split(',').map(Number)
    const ask = (): void => {
      for (const floor of wanted) {
        backend.getHeat(token, floor).then(
          (grid) => { if (!stopped) setGrids((previous) => new Map(previous).set(floor, grid)) },
          () => { /* Keep the last grid of this floor. */ },
        )
      }
    }
    ask()
    const timer = window.setInterval(ask, HEAT_REFRESH_MS)
    return () => { stopped = true; window.clearInterval(timer) }
  }, [token, floorKey, enabled])

  return grids
}
