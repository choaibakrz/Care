/**
 * The emergency mode switch: its own small state and its own network code, like the stop button.
 *
 * The server's mode is read every few seconds while someone is signed in, so the switch shows the
 * truth even when the rest of the panel is broken. The panel may also hand it a fresher value
 * (from the live stream); it never reads anything back from the panel.
 */
import { config } from '../lib/config'
import type { SystemMode } from '../types'
import { CallError, call, demoBackend } from './send'

export type ModeAction = 'idle' | 'switching'

export interface ModeSnapshot {
  /** Null until the server answered once. */
  mode: SystemMode | null
  /** False when the server has no emergency mode at all (it answered 404). */
  supported: boolean
  action: ModeAction
  /** The last refusal or failure, shown under the switch. */
  error: string | null
  /** True while the operator is asked to confirm leaving emergency mode. */
  confirmingExit: boolean
}

const REFRESH_MS = 5000
/** A server without emergency mode is asked again only once a minute (12 × 5 s). */
const UNSUPPORTED_SKIPS = 11
const ENTER_REASON = 'Switched on from the admin console.'
const EXIT_REASON = 'Switched off from the admin console.'

let snapshot: ModeSnapshot = { mode: null, supported: true, action: 'idle', error: null, confirmingExit: false }
let token: string | null = null
let timer: number | undefined
let skips = 0
const listeners = new Set<() => void>()

function update(next: Partial<ModeSnapshot>): void {
  snapshot = { ...snapshot, ...next }
  listeners.forEach((listener) => listener())
}

export function subscribeMode(listener: () => void): () => void {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

export function getModeSnapshot(): ModeSnapshot {
  return snapshot
}

function readMode(value: unknown): SystemMode | null {
  if (typeof value !== 'object' || value === null) return null
  const raw = value as Record<string, unknown>
  if (raw.mode !== 'normal' && raw.mode !== 'emergency') return null
  const text = (key: string): string | null => (typeof raw[key] === 'string' && raw[key] ? (raw[key] as string) : null)
  return { mode: raw.mode, since: text('since'), by: text('by'), reason: text('reason') }
}

async function fetchMode(current: string): Promise<SystemMode | null> {
  if (config.useMock) return (await demoBackend()).getMode(current)
  try {
    return readMode(await call(`${config.apiUrl}/system/mode`, current, 'GET'))
  } catch (reason) {
    if (reason instanceof CallError && reason.status === 404) return null
    throw reason
  }
}

async function refresh(): Promise<void> {
  const current = token
  if (!current) return
  if (skips > 0) { skips -= 1; return }
  try {
    const mode = await fetchMode(current)
    if (token !== current) return
    // While a switch is on its way, its own answer wins.
    if (snapshot.action === 'switching') return
    if (!mode) skips = UNSUPPORTED_SKIPS
    update(mode ? { mode, supported: true } : { mode: null, supported: false })
  } catch {
    // Keep the last known mode: the next refresh tries again.
  }
}

/** Called by the stop's bridge when someone signs in or out. */
export function setModeToken(next: string | null): void {
  token = next
  skips = 0
  if (timer !== undefined) { window.clearInterval(timer); timer = undefined }
  if (!next) { update({ mode: null, supported: true, action: 'idle', error: null, confirmingExit: false }); return }
  void refresh()
  timer = window.setInterval(() => { void refresh() }, REFRESH_MS)
}

/** The panel heard `mode.updated` on the live stream: show it at once. */
export function showMode(mode: SystemMode): void {
  if (snapshot.action === 'switching') return
  update({ mode, supported: true })
}

async function send(next: SystemMode['mode']): Promise<void> {
  const current = token
  if (!current || snapshot.action === 'switching') return
  update({ action: 'switching', error: null, confirmingExit: false })
  const reason = next === 'emergency' ? ENTER_REASON : EXIT_REASON
  try {
    const mode = config.useMock
      ? await (await demoBackend()).setMode(current, next, reason)
      : readMode(await call(`${config.apiUrl}/system/mode`, current, 'PUT', JSON.stringify({ mode: next, reason })))
    if (token !== current) return
    if (!mode) throw new Error('The server answered something the panel cannot read.')
    update({ mode, action: 'idle' })
  } catch (reason) {
    if (token !== current) return
    const unsupported = reason instanceof CallError && reason.status === 404
    update({ action: 'idle', supported: !unsupported, error: unsupported ? 'This server has no emergency mode yet.' : reason instanceof Error ? reason.message : 'The switch did not go through.' })
  }
}

/** One click, no question: in an emergency every second counts. */
export function enterEmergency(): Promise<void> {
  return send('emergency')
}

/** Leaving takes a second click: the clinic goes back to normal operation. */
export function askExit(): void {
  update({ confirmingExit: true, error: null })
}

export function cancelExit(): void {
  update({ confirmingExit: false })
}

export function confirmExit(): Promise<void> {
  return send('normal')
}
