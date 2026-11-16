/**
 * The network side of the emergency stop.
 *
 * On purpose this file does not use the panel's API client, its store or its adapters: the stop
 * must still work when the rest of the page is broken. It only needs an address and a token.
 */
import { ESTOP_FALLBACK_PATH, config } from '../lib/config'
import type { Backend } from '../lib/backend'

/** Demo mode only: the in-browser clinic, loaded on first use so it never delays this button. */
export async function demoBackend(): Promise<Backend> {
  return (await import('../mock/server')).mockBackend
}

const TIMEOUT_MS = 4000

/** A request with its own timeout, outside the panel's client. `status` is set on an HTTP error. */
export class CallError extends Error {
  readonly status: number | null
  constructor(message: string, status: number | null) {
    super(message)
    this.status = status
  }
}

export async function call(url: string, token: string | null, method: string, body?: string): Promise<unknown> {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), TIMEOUT_MS)
  try {
    const response = await fetch(url, { method, body, signal: controller.signal, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) } })
    const text = await response.text()
    let parsed: unknown = null
    try { parsed = text ? JSON.parse(text) : null } catch { parsed = null }
    if (!response.ok) {
      const message = (parsed as { error?: { message?: unknown } } | null)?.error?.message
      throw new CallError(typeof message === 'string' ? message : `The server answered ${response.status}.`, response.status)
    }
    return parsed
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === 'AbortError') throw new CallError('No answer within 4 seconds.', null)
    if (reason instanceof TypeError) throw new CallError('The server could not be reached.', null)
    throw reason
  } finally {
    window.clearTimeout(timer)
  }
}

/** Asks the server to stop one robot. Resolves when the server took the order, rejects otherwise. */
export async function sendStop(token: string, robotId: string): Promise<void> {
  if (config.useMock) {
    const outcome = await (await demoBackend()).sendCommand(token, robotId, 'estop')
    if (!outcome.accepted) throw new Error(outcome.reason ?? 'The stop was refused.')
    return
  }
  const answer = await call(`${config.apiUrl}/robots/${encodeURIComponent(robotId)}/command`, token, 'POST', JSON.stringify({ name: 'estop' }))
  if (typeof answer === 'object' && answer !== null && (answer as { accepted?: unknown }).accepted === false) throw new Error('The stop was refused.')
}

/** Asks the server to re-arm one stopped robot (an admin's `resume`). Rejects with the server's message when it refuses. */
export async function sendRearm(token: string, robotId: string): Promise<void> {
  if (config.useMock) {
    const outcome = await (await demoBackend()).sendCommand(token, robotId, 'resume')
    if (!outcome.accepted) throw new Error(outcome.reason ?? 'The robot refused.')
    return
  }
  const answer = await call(`${config.apiUrl}/robots/${encodeURIComponent(robotId)}/command`, token, 'POST', JSON.stringify({ name: 'resume' }))
  if (typeof answer === 'object' && answer !== null && (answer as { accepted?: unknown }).accepted === false) throw new Error('The robot refused.')
}

interface KnownRobot {
  id: string
  state: string
}

/** The robots the server knows, with their state. Used to find who to stop and to confirm the stop. */
export async function readRobots(token: string): Promise<KnownRobot[]> {
  if (config.useMock) return (await (await demoBackend()).getRobots(token)).map((robot) => ({ id: robot.id, state: robot.state }))
  const answer = await call(`${config.apiUrl}/robots`, token, 'GET')
  const entries: unknown[] = Array.isArray(answer) ? answer : []
  return entries.flatMap((entry) => {
    if (typeof entry !== 'object' || entry === null) return []
    const raw = entry as { id?: unknown; robot_id?: unknown; state?: unknown }
    const id = typeof raw.id === 'string' ? raw.id : typeof raw.robot_id === 'string' ? raw.robot_id : ''
    return id ? [{ id, state: typeof raw.state === 'string' ? raw.state : '' }] : []
  })
}

export const fallbackUrl = `${config.robotScreenUrl}${ESTOP_FALLBACK_PATH}`

/**
 * The documented backup: the robot-side screen (`b13_ecran`) stops the robot plugged on it.
 * It is open to everyone on the local network. It is a backup, never the first path.
 */
export async function sendFallbackStop(): Promise<void> {
  if (config.useMock) throw new Error('Demo mode: the backup route is not called.')
  await call(fallbackUrl, null, 'POST')
}
