/**
 * How the service is doing, from a list of tasks: counts and waiting times, never a person.
 * The server answers `GET /stats/service` with the same numbers; until it does, the Monitor page
 * computes them from the tasks this console already knows (and says so).
 */
import type { ServiceStats, Tablet, Task } from '../types'

const TOP = 6

function percentile(sorted: number[], share: number): number | null {
  if (!sorted.length) return null
  return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * share))]
}

/** Seconds from the request to the delivery, read from the task's own history. */
function waitOf(task: Task): number | null {
  if (task.state !== 'delivered') return null
  // The server writes "delivered", the demo "Delivered at Room 12": either marks the moment.
  const done = task.history.find((entry) => /^delivered/i.test(entry.label))?.at ?? task.updatedAt
  const wait = (Date.parse(done) - Date.parse(task.createdAt)) / 1000
  return Number.isFinite(wait) && wait >= 0 ? wait : null
}

function top(counts: Map<string, number>): Array<[string, number]> {
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, TOP)
}

export function serviceFromTasks(tasks: Task[], tablets: Tablet[], now: number, hours: number): ServiceStats {
  const since = now - hours * 3600 * 1000
  const recent = tasks.filter((task) => task.kind !== 'restock_round' && Date.parse(task.createdAt) >= since)
  const byItem = new Map<string, number>()
  const byPlace = new Map<string, number>()
  for (const task of recent) {
    const item = task.item ?? (task.kind === 'go_to' ? 'Go to a place' : 'Other')
    byItem.set(item, (byItem.get(item) ?? 0) + 1)
    byPlace.set(task.toPlace, (byPlace.get(task.toPlace) ?? 0) + 1)
  }
  const waits = recent.map(waitOf).filter((wait): wait is number => wait !== null).sort((a, b) => a - b)
  const bedside = tablets.filter((tablet) => tablet.kind === 'bedside' && tablet.assigned)
  return {
    hours,
    requests: recent.length,
    delivered: recent.filter((task) => task.state === 'delivered').length,
    failed: recent.filter((task) => task.state === 'failed').length,
    medianWaitS: percentile(waits, 0.5),
    p90WaitS: percentile(waits, 0.9),
    byItem: top(byItem).map(([label, count]) => ({ label, count })),
    byPlace: top(byPlace).map(([place, count]) => ({ place, count })),
    bedsideOnline: bedside.filter((tablet) => tablet.online).length,
    bedsideTotal: bedside.length,
  }
}
