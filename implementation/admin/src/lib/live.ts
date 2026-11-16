/**
 * The one live connection. It reconnects by itself, with a growing delay, and tells the
 * panel each time it is back so the panel can reload what it missed.
 */
import type { ConnectionState, LiveMessage } from '../types'
import { toLiveMessage } from './adapt'
import { backend } from './backend'
import type { LiveSocket } from './backend'

export interface LiveHandlers {
  onMessage: (message: LiveMessage) => void
  onStatus: (status: ConnectionState) => void
}

const FIRST_RETRY_MS = 1000
const MAX_RETRY_MS = 8000
const STABLE_MS = 10000

/** Opens the connection and keeps it open. Returns the function that closes it for good. */
export function connectLive(token: string, handlers: LiveHandlers): () => void {
  let socket: LiveSocket | null = null
  let retryTimer: number | undefined
  let retryDelay = FIRST_RETRY_MS
  let stopped = false
  let openedAt = 0

  const scheduleRetry = (): void => {
    if (stopped || retryTimer !== undefined) return
    handlers.onStatus('offline')
    retryTimer = window.setTimeout(() => { retryTimer = undefined; open() }, retryDelay)
    retryDelay = Math.min(MAX_RETRY_MS, retryDelay * 2)
  }

  const open = (): void => {
    if (stopped) return
    let current: LiveSocket
    try {
      current = backend.openSocket()
    } catch {
      scheduleRetry()
      return
    }
    socket = current
    current.onopen = () => {
      if (stopped || socket !== current) return
      // The token travels inside the connection, never in its address.
      current.send(JSON.stringify({ type: 'auth', token }))
      openedAt = Date.now()
      handlers.onStatus('live')
    }
    current.onmessage = (event) => {
      if (stopped || socket !== current) return
      // The server spoke: the token was accepted, the next drop starts again from a short delay.
      retryDelay = FIRST_RETRY_MS
      let parsed: unknown
      try { parsed = JSON.parse(String(event.data)) } catch { return }
      const message = toLiveMessage(parsed)
      if (message) handlers.onMessage(message)
    }
    current.onerror = () => { /* A close always follows: the retry starts there. */ }
    current.onclose = () => {
      if (stopped || socket !== current) return
      socket = null
      // A socket closed right after opening (rejected token, broken server) must not loop fast.
      if (Date.now() - openedAt > STABLE_MS) retryDelay = FIRST_RETRY_MS
      scheduleRetry()
    }
  }

  handlers.onStatus('connecting')
  open()

  return () => {
    stopped = true
    if (retryTimer !== undefined) window.clearTimeout(retryTimer)
    socket?.close()
    socket = null
  }
}
