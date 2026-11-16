/** The "live activity" feed: one short line for each thing worth knowing, newest first. */
import { STATE_LABEL, taskRoute, taskTitle } from '../lib/format'
import type { ClinicMap, LiveMessage, Robot, Task } from '../types'

export type Tone = 'info' | 'success' | 'warning' | 'danger'
export type EventKind = 'task' | 'robot' | 'mic' | 'alert'

export interface ActivityEvent {
  id: string
  at: string
  kind: EventKind
  tone: Tone
  title: string
  detail: string
}

let eventCount = 0

function event(kind: EventKind, tone: Tone, title: string, detail: string, at = new Date().toISOString()): ActivityEvent {
  eventCount += 1
  return { id: `event-${eventCount}`, at, kind, tone, title, detail }
}

function taskTone(task: Task): Tone {
  if (task.state === 'delivered') return 'success'
  if (task.state === 'failed') return 'danger'
  if (task.state === 'resumed' || task.state === 'cancelled') return 'warning'
  return 'info'
}

function taskEvent(task: Task, map: ClinicMap | null, entry = task.history[task.history.length - 1]): ActivityEvent {
  const label = entry?.label ?? task.state
  return event('task', taskTone(task), `${task.id} · ${label}`, `${taskTitle(task)} · ${taskRoute(task, map)}`, entry?.at || task.updatedAt)
}

export function eventsFromMessage(message: LiveMessage, robots: Robot[], map: ClinicMap | null): ActivityEvent[] {
  if (message.type === 'task.updated') return [taskEvent(message.task, map)]
  if (message.type === 'alert') return [event('alert', message.level === 'critical' ? 'danger' : message.level === 'warning' ? 'warning' : 'info', 'Alert', message.message)]
  if (message.type !== 'robot.updated') return []

  const next = message.robot
  const previous = robots.find((robot) => robot.id === next.id)
  if (!previous) return []
  const events: ActivityEvent[] = []
  if (previous.state !== next.state) {
    const tone: Tone = next.state === 'estop' || next.state === 'fault' ? 'danger' : next.state === 'paused' ? 'warning' : 'info'
    events.push(event('robot', tone, `${next.id} · ${STATE_LABEL[next.state]}`, `Was: ${STATE_LABEL[previous.state].toLowerCase()}`, next.lastSeen))
  }
  if (previous.micOpen !== next.micOpen && next.state !== 'estop') {
    events.push(event('mic', 'info', `${next.id} · microphone ${next.micOpen ? 'open' : 'closed'}`, next.micOpen ? 'Left a deaf zone' : 'Entered a deaf zone', next.lastSeen))
  }
  return events
}

const HISTORY_EVENTS = 8

/** Fills the feed when the page opens, from the last steps of the tasks the server already knows. */
export function eventsFromHistory(tasks: Task[], map: ClinicMap | null): ActivityEvent[] {
  return tasks
    .flatMap((task) => task.history.slice(-2).map((entry) => taskEvent({ ...task, state: entry === task.history[task.history.length - 1] ? task.state : 'en_route' }, map, entry)))
    .sort((a, b) => Date.parse(b.at) - Date.parse(a.at))
    .slice(0, HISTORY_EVENTS)
}
