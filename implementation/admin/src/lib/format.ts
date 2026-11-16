/** Words and small formats shared by every page. One place, so a state is named the same everywhere. */
import type { ClinicMap, DisplayState, Robot, RobotMood, RobotState, Task, TaskState } from '../types'
import { STALE_AFTER_MS } from './config'

export const STATE_LABEL: Record<DisplayState, string> = {
  idle: 'Available',
  busy: 'On a task',
  paused: 'Paused',
  fault: 'Fault',
  estop: 'Emergency stop',
  offline: 'No signal',
}

export const STATE_ORDER: DisplayState[] = ['idle', 'busy', 'paused', 'fault', 'estop', 'offline']

export const TASK_LABEL: Record<TaskState, string> = {
  requested: 'Requested',
  assigned: 'Assigned',
  en_route: 'On the way',
  delivered: 'Delivered',
  failed: 'Failed',
  resumed: 'Handed to staff',
  cancelled: 'Cancelled',
}

export const OPEN_TASK_STATES: TaskState[] = ['requested', 'assigned', 'en_route']

export function isOpenTask(task: Task): boolean {
  return OPEN_TASK_STATES.includes(task.state)
}

/** A robot not heard from for five seconds is shown as "no signal", whatever it last said. */
export function isStale(robot: Robot, now: number): boolean {
  const seen = Date.parse(robot.lastSeen)
  return Number.isNaN(seen) || now - seen > STALE_AFTER_MS
}

export function displayState(robot: Robot, now: number): DisplayState {
  return isStale(robot, now) ? 'offline' : robot.state
}

export const MOOD_EMOJI: Record<RobotMood, string> = {
  happy: '😊',
  busy: '🚚',
  deaf: '🙉',
  charging: '🔋',
  home: '🏠',
  alarm: '🚨',
  stopped: '🛑',
  offline: '💤',
}

export const MOOD_LABEL: Record<RobotMood, string> = {
  happy: 'Happy, wandering',
  busy: 'Busy',
  deaf: 'Deaf zone, not listening',
  charging: 'Charging',
  home: 'Going home',
  alarm: 'Needs a person',
  stopped: 'Stopped',
  offline: 'No signal',
}

/** For servers that do not send `mood` yet: a best guess from the state and the microphone. */
export function deriveMood(state: RobotState, micOpen: boolean, goingHome = false): RobotMood {
  if (state === 'estop') return 'stopped'
  if (state === 'fault') return 'alarm'
  if (goingHome) return 'home'
  if (!micOpen) return 'deaf'
  if (state === 'busy') return 'busy'
  return state === 'paused' ? 'stopped' : 'happy'
}

/** The mood to show: a robot not heard from is asleep, whatever it last said. */
export function displayMood(robot: Robot, now: number): RobotMood {
  return isStale(robot, now) ? 'offline' : robot.mood
}

export function placeName(map: ClinicMap | null, placeId: string | null): string {
  if (!placeId) return '—'
  return map?.places.find((place) => place.id === placeId)?.label ?? placeId
}

export function floorName(map: ClinicMap | null, floorId: number): string {
  return map?.floors.find((floor) => floor.id === floorId)?.label ?? (floorId === 0 ? 'Ground floor' : `Floor ${floorId}`)
}

export function taskTitle(task: Task): string {
  if (task.kind === 'restock_round') return 'Night restock round'
  if (task.kind === 'go_to') return 'Go to a place'
  if (task.kind === 'follow') return `Following ${task.targetLabel ?? 'a staff tablet'}`
  return task.item ?? 'Item'
}

export function taskRoute(task: Task, map: ClinicMap | null): string {
  if (task.kind === 'restock_round') return 'Every shelf of the floor'
  if (task.kind === 'follow') return `Now in ${placeName(map, task.toPlace)}`
  if (!task.fromPlace) return `To ${placeName(map, task.toPlace)}`
  return `${placeName(map, task.fromPlace)} → ${placeName(map, task.toPlace)}`
}

const TIME = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
const SHORT_TIME = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit' })
const DAY_TIME = new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })

function parse(value: string | null): Date | null {
  if (!value) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

export function clockTime(value: string | null): string {
  const date = parse(value)
  return date ? TIME.format(date) : '—'
}

export function shortTime(value: string | null): string {
  const date = parse(value)
  return date ? SHORT_TIME.format(date) : '—'
}

export function dayTime(value: string | null): string {
  const date = parse(value)
  return date ? DAY_TIME.format(date) : '—'
}

export function ago(value: string | null, now: number): string {
  const date = parse(value)
  if (!date) return '—'
  const seconds = Math.max(0, Math.round((now - date.getTime()) / 1000))
  if (seconds < 5) return 'just now'
  if (seconds < 60) return `${seconds} s ago`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  return hours < 24 ? `${hours} h ago` : `${Math.round(hours / 24)} d ago`
}

export function errorMessage(reason: unknown): string {
  return reason instanceof Error && reason.message ? reason.message : 'Something went wrong.'
}

export function capitalize(value: string): string {
  return value ? value[0].toUpperCase() + value.slice(1) : value
}
