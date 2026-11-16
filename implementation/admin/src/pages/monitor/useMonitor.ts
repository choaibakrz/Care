/**
 * The Monitor page's data, polled only while the page is open. Each part may be missing on the
 * server (it answers 404): that part is `unsupported` and the page says so, the others still work.
 */
import { useCallback, useEffect, useState } from 'react'
import { backend } from '../../lib/backend'
import { errorMessage } from '../../lib/format'
import type { BlockRule, ClientStat, ServerSummary, ServiceStats, Traffic } from '../../types'

export const FAST_MS = 2000
/** When the server has none of the monitor routes, ask again only this often. */
export const UNSUPPORTED_MS = 30000
export const SLOW_MS = 10000
export const WINDOW_S = 300
export const SERVICE_HOURS = 24

/** `undefined`: not loaded yet. `null`: the server does not have it. */
export interface MonitorData {
  summary: ServerSummary | null | undefined
  traffic: Traffic | null | undefined
  clients: ClientStat[] | null | undefined
  blocks: BlockRule[] | null | undefined
  service: ServiceStats | null | undefined
  error: string | null
}

export function useMonitor(token: string | null): MonitorData & { refresh: () => void } {
  const [data, setData] = useState<MonitorData>({ summary: undefined, traffic: undefined, clients: undefined, blocks: undefined, service: undefined, error: null })
  const [tick, setTick] = useState(0)
  const refresh = useCallback(() => setTick((value) => value + 1), [])

  useEffect(() => {
    if (!token) return undefined
    let stopped = false
    let timer: number | undefined
    const fast = async (): Promise<void> => {
      let wait = FAST_MS
      try {
        const [summary, traffic, clients, blocks] = await Promise.all([backend.getSummary(token), backend.getTraffic(token, WINDOW_S), backend.getClients(token), backend.getBlocks(token)])
        if (!stopped) setData((previous) => ({ ...previous, summary, traffic, clients, blocks, error: null }))
        // A server without any of these routes is not asked every 2 s for nothing.
        if ([summary, traffic, clients, blocks].every((part) => part === null)) wait = UNSUPPORTED_MS
      } catch (reason) {
        // Keep the last numbers on screen and say why they stopped moving.
        if (!stopped) setData((previous) => ({ ...previous, error: errorMessage(reason) }))
      }
      if (!stopped) timer = window.setTimeout(() => { void fast() }, wait)
    }
    void fast()
    return () => { stopped = true; window.clearTimeout(timer) }
  }, [token, tick])

  useEffect(() => {
    if (!token) return undefined
    let stopped = false
    const slow = (): void => {
      backend.getServiceStats(token, SERVICE_HOURS).then((service) => { if (!stopped) setData((previous) => ({ ...previous, service })) }, () => { /* Next try in 10 s. */ })
    }
    slow()
    const timer = window.setInterval(slow, SLOW_MS)
    return () => { stopped = true; window.clearInterval(timer) }
  }, [token])

  return { ...data, refresh }
}
