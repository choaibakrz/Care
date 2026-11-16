/**
 * The emergency stop's own tiny state. The rest of the panel may tell it who is signed in and
 * which robots exist; it never reads anything back from the panel.
 *
 * Each robot has its own run number: pressing "stop R2" after "stop all" only replaces R2's
 * report, the others keep being confirmed and keep their warnings.
 */
import type { SystemMode } from '../types'
import { setModeToken, showMode } from './mode'
import { readRobots, sendFallbackStop, sendRearm, sendStop } from './send'

export type StopPhase = 'sending' | 'sent' | 'confirmed' | 'unconfirmed' | 'failed' | 'rearmed' | 'rearm_refused'

export interface RobotStop {
  robotId: string
  phase: StopPhase
  detail: string
}

export type FallbackPhase = 'idle' | 'sending' | 'sent' | 'failed'

export interface EstopSnapshot {
  token: string | null
  robotIds: string[]
  stops: RobotStop[]
  /** Set while the robots are looked up, or when the stop could not even start. */
  problem: string | null
  looking: boolean
  fallback: FallbackPhase
  fallbackDetail: string
}

const CONFIRM_EVERY_MS = 400
const CONFIRM_FOR_MS = 5000
const LOOKUP_TRIES = 3

let snapshot: EstopSnapshot = { token: null, robotIds: [], stops: [], problem: null, looking: false, fallback: 'idle', fallbackDetail: '' }
const runs = new Map<string, number>()
let generation = 0
let runCount = 0
const listeners = new Set<() => void>()

function update(next: Partial<EstopSnapshot>): void {
  snapshot = { ...snapshot, ...next }
  listeners.forEach((listener) => listener())
}

function isCurrent(robotId: string, run: number, gen: number): boolean {
  return runs.get(robotId) === run && generation === gen
}

function setStop(robotId: string, phase: StopPhase, detail: string): void {
  const others = snapshot.stops.filter((stop) => stop.robotId !== robotId)
  update({ stops: [...others, { robotId, phase, detail }].sort((a, b) => a.robotId.localeCompare(b.robotId)) })
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

export function getSnapshot(): EstopSnapshot {
  return snapshot
}

/** True while an order is on its way or waiting for the robot to confirm. */
export function isResolving(state: EstopSnapshot = snapshot): boolean {
  return state.looking || state.stops.some((stop) => stop.phase === 'sending' || stop.phase === 'sent')
}

export function setEstopContext(context: { token?: string | null; robotIds?: string[]; mode?: SystemMode }): void {
  if (context.mode) showMode(context.mode)
  if (context.token !== undefined && context.token !== snapshot.token) setModeToken(context.token)
  if (context.token === null) {
    // Signing out ends every pending check: they would keep polling with a dead token.
    generation += 1
    runs.clear()
    update({ token: null, robotIds: [], stops: [], problem: null, looking: false, fallback: 'idle', fallbackDetail: '' })
    return
  }
  const { mode: _mode, ...rest } = context
  update(rest)
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => { window.setTimeout(resolve, ms) })
}

async function confirm(token: string, robotId: string, run: number, gen: number): Promise<void> {
  const deadline = Date.now() + CONFIRM_FOR_MS
  while (Date.now() < deadline && isCurrent(robotId, run, gen)) {
    await wait(CONFIRM_EVERY_MS)
    try {
      const robots = await readRobots(token)
      if (robots.find((robot) => robot.id === robotId)?.state === 'estop') {
        if (isCurrent(robotId, run, gen)) setStop(robotId, 'confirmed', 'The robot reports it has stopped.')
        return
      }
    } catch {
      // Keep asking until the deadline.
    }
  }
  if (isCurrent(robotId, run, gen)) setStop(robotId, 'unconfirmed', 'Order sent, but the robot has not confirmed. Check the robot.')
}

async function stopOne(token: string, robotId: string, gen: number): Promise<void> {
  runCount += 1
  const run = runCount
  runs.set(robotId, run)
  setStop(robotId, 'sending', 'Sending the stop order.')
  try {
    await sendStop(token, robotId)
  } catch (reason) {
    if (isCurrent(robotId, run, gen)) setStop(robotId, 'failed', reason instanceof Error ? reason.message : 'The order did not go through.')
    return
  }
  if (!isCurrent(robotId, run, gen)) return
  setStop(robotId, 'sent', 'Order sent. Waiting for the robot to confirm.')
  await confirm(token, robotId, run, gen)
}

async function lookUpRobots(token: string, gen: number): Promise<string[]> {
  for (let attempt = 1; attempt <= LOOKUP_TRIES && generation === gen; attempt++) {
    try {
      const ids = (await readRobots(token)).map((robot) => robot.id)
      if (ids.length) return ids
    } catch {
      // Try again below.
    }
    if (generation === gen) update({ problem: `Looking for the robots… (try ${attempt} of ${LOOKUP_TRIES})` })
  }
  return []
}

/** Stops the given robots, or every known robot when none is given. Nothing asks "are you sure". */
export async function requestStop(only?: string[]): Promise<void> {
  const { token } = snapshot
  if (!token) return
  const gen = generation
  update({ fallback: 'idle', fallbackDetail: '' })
  let targets = only?.length ? only : snapshot.robotIds
  if (!targets.length) {
    update({ looking: true, problem: 'Looking for the robots…' })
    targets = await lookUpRobots(token, gen)
    if (generation !== gen) return
    update({ looking: false })
    if (!targets.length) { update({ problem: 'The panel cannot reach any robot.' }); return }
    update({ robotIds: targets })
  }
  update({ problem: null })
  await Promise.all(targets.map((robotId) => stopOne(token, robotId, gen)))
}

/** Re-arms the robots this report shows as stopped, once a person confirmed the area is safe. */
export async function requestRearm(): Promise<void> {
  const { token } = snapshot
  if (!token) return
  const gen = generation
  const targets = snapshot.stops.filter((stop) => stop.phase === 'confirmed' || stop.phase === 'unconfirmed' || stop.phase === 'rearm_refused').map((stop) => stop.robotId)
  await Promise.all(targets.map(async (robotId) => {
    runCount += 1
    runs.set(robotId, runCount)
    setStop(robotId, 'sending', 'Re-arming…')
    try {
      await sendRearm(token, robotId)
      if (generation === gen) setStop(robotId, 'rearmed', 'The robot can move again.')
    } catch (reason) {
      if (generation === gen) setStop(robotId, 'rearm_refused', reason instanceof Error ? reason.message : 'The robot was not re-armed.')
    }
  }))
}

export async function requestFallback(): Promise<void> {
  update({ fallback: 'sending', fallbackDetail: '' })
  try {
    await sendFallbackStop()
    update({ fallback: 'sent', fallbackDetail: 'The robot-side screen took the backup stop.' })
  } catch (reason) {
    update({ fallback: 'failed', fallbackDetail: reason instanceof Error ? reason.message : 'The backup did not answer.' })
  }
}

/** Closes the report. Refused while an order is still being confirmed. */
export function dismissStops(): void {
  if (isResolving()) return
  update({ stops: [], problem: null, fallback: 'idle', fallbackDetail: '' })
}
