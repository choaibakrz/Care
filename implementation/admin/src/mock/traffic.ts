/**
 * The demo server's traffic and its attack detection: invented clients (consoles, tablets, robots)
 * send requests every second; an attack can be started from the Monitor page. The detection
 * follows `requirements/monitoring-security.md`: a per-address rate limit, an automatic block
 * when an address keeps going over it or keeps failing to log in, and manual blocks.
 *
 * Addresses are invented. 203.0.113.0/24 and 198.51.100.0/24 are documentation ranges (RFC 5737).
 */
import type { BlockRule, ClientStat, ClientStatus, LiveMessage, RejectReason, SecurityAlertKind, ServerSummary, Traffic, TrafficPoint } from '../types'

export const RATE_PER_S = 20
export const BURST = 40
/** Seconds over the limit in a row before an automatic block. */
export const LIMITED_SECONDS_BEFORE_BLOCK = 5
export const LOGIN_FAILURES_BEFORE_BLOCK = 10
export const AUTO_BLOCK_S = 600
const HISTORY_S = 300
const CLIENT_WINDOW_S = 300
const ATTACK_S = 75
const RECENT_RATE_S = 10

/** The address of this console in the demo: it can never be blocked. */
export const CONSOLE_IP = '10.0.1.5'

interface ClientModel {
  ip: string
  label: string | null
  /** Requests per second it sends. */
  rate: number
  /** Failed logins per second (credential stuffing). */
  loginFailRate: number
  robot: boolean
  /** Simulated seconds after which an attacker stops. */
  until: number | null
}

interface Second {
  accepted: number
  rejected: number
  loginFailures: number
}

interface ClientState extends ClientModel {
  seconds: Second[]
  overLimitFor: number
  status: ClientStatus
  reason: string | null
}

interface ReasonSecond {
  at: number
  reasons: Partial<Record<RejectReason, number>>
}

const BASE_CLIENTS: ClientModel[] = [
  { ip: CONSOLE_IP, label: 'Admin console', rate: 1.6, loginFailRate: 0, robot: false, until: null },
  { ip: '10.0.2.21', label: 'Ward Wi-Fi · staff tablet', rate: 0.9, loginFailRate: 0, robot: false, until: null },
  { ip: '10.0.2.22', label: 'Ward Wi-Fi · staff tablet', rate: 0.7, loginFailRate: 0, robot: false, until: null },
  { ip: '10.0.2.31', label: 'Ward Wi-Fi · bedside tablet', rate: 0.4, loginFailRate: 0, robot: false, until: null },
  { ip: '10.0.2.32', label: 'Ward Wi-Fi · bedside tablet', rate: 0.35, loginFailRate: 0, robot: false, until: null },
  { ip: '10.0.2.40', label: 'Reception Wi-Fi', rate: 0.6, loginFailRate: 0, robot: false, until: null },
  { ip: '10.0.3.11', label: 'Robot R1', rate: 1.2, loginFailRate: 0, robot: true, until: null },
  { ip: '10.0.3.12', label: 'Robot R2', rate: 1.2, loginFailRate: 0, robot: true, until: null },
  { ip: '10.0.3.13', label: 'Robot R3', rate: 1.2, loginFailRate: 0, robot: true, until: null },
  { ip: '10.0.3.14', label: 'Robot R4', rate: 1.2, loginFailRate: 0, robot: true, until: null },
]

function ipToNumber(ip: string): number | null {
  const parts = ip.split('.')
  if (parts.length !== 4) return null
  let value = 0
  for (const part of parts) {
    if (!/^\d{1,3}$/.test(part)) return null
    const byte = Number(part)
    if (byte > 255) return null
    value = value * 256 + byte
  }
  return value
}

/** `10.0.2.21` or `203.0.113.0/24`. Returns null when it is neither. */
export function parseTarget(target: string): { base: number; prefix: number } | null {
  const [address, prefixText] = target.trim().split('/')
  const base = ipToNumber(address)
  if (base === null) return null
  if (prefixText === undefined) return { base, prefix: 32 }
  if (!/^\d{1,2}$/.test(prefixText)) return null
  const prefix = Number(prefixText)
  return prefix <= 32 ? { base, prefix } : null
}

export function matches(target: string, ip: string): boolean {
  const range = parseTarget(target)
  const address = ipToNumber(ip)
  if (!range || address === null) return false
  if (range.prefix === 0) return true
  const shift = 32 - range.prefix
  return Math.floor(range.base / 2 ** shift) === Math.floor(address / 2 ** shift)
}

/** Small integer noise around a rate: the same rate never gives a flat line. */
function countFor(rate: number, random: () => number): number {
  const whole = Math.floor(rate)
  return whole + (random() < rate - whole ? 1 : 0) + (rate >= 3 ? Math.round((random() - 0.5) * rate * 0.3) : 0)
}

export class TrafficSim {
  private clients = new Map<string, ClientState>()
  private history: TrafficPoint[] = []
  private reasonSeconds: ReasonSecond[] = []
  private latencies: number[] = []
  private blocks: BlockRule[] = []
  private blockCount = 0
  private carry = 0
  private clock: number
  private readonly startedAt: number
  private readonly random: () => number

  constructor(now: number, random: () => number = Math.random) {
    this.clock = now
    this.startedAt = now - 3 * 3600 * 1000
    this.random = random
    for (const model of BASE_CLIENTS) this.addClient(model)
    // Start with five minutes of history, so the charts are not empty.
    for (let second = 0; second < HISTORY_S; second++) this.tick(this.clock - (HISTORY_S - second) * 1000, false)
  }

  private addClient(model: ClientModel): void {
    this.clients.set(model.ip, { ...model, seconds: [], overLimitFor: 0, status: 'ok', reason: null })
  }

  /** Advances by `dt` seconds. Returns the alerts to send on the live stream. */
  step(dt: number, now: number, emergency: boolean): LiveMessage[] {
    this.carry += dt
    const alerts: LiveMessage[] = []
    while (this.carry >= 1) {
      this.carry -= 1
      this.clock = now
      alerts.push(...this.tick(now, emergency))
    }
    return alerts
  }

  private blockFor(ip: string): BlockRule | undefined {
    return this.blocks.find((block) => matches(block.target, ip))
  }

  private alert(at: number, kind: SecurityAlertKind, ip: string, message: string): LiveMessage {
    return { type: 'security.alert', alert: { at: new Date(at).toISOString(), kind, ip, message } }
  }

  private tick(at: number, emergency: boolean): LiveMessage[] {
    const alerts: LiveMessage[] = []
    this.blocks = this.blocks.filter((block) => !block.expiresAt || Date.parse(block.expiresAt) > at)
    const reasons: Partial<Record<RejectReason, number>> = {}
    const reject = (reason: RejectReason, count: number): void => { if (count > 0) reasons[reason] = (reasons[reason] ?? 0) + count }
    let accepted = 0
    let rejected = 0
    let attackLoad = 0

    for (const client of [...this.clients.values()]) {
      if (client.until !== null && at > client.until) {
        // The attacker gave up: keep it in the table while it still has recent seconds.
        if (client.seconds.every((second) => second.accepted + second.rejected === 0)) { this.clients.delete(client.ip); continue }
        client.rate = 0
        client.loginFailRate = 0
      }
      const sent = countFor(client.rate, this.random)
      const failedLogins = countFor(client.loginFailRate, this.random)
      const second: Second = { accepted: 0, rejected: 0, loginFailures: 0 }
      const block = this.blockFor(client.ip)
      if (client.rate >= RATE_PER_S || client.loginFailRate > 0) attackLoad += sent + failedLogins

      if (block) {
        block.hits += sent + failedLogins
        second.rejected = sent + failedLogins
        reject('blocked', second.rejected)
        client.status = 'blocked'
        client.reason = block.reason
      } else {
        const allowed = Math.min(sent, client.overLimitFor > 0 ? RATE_PER_S : BURST)
        const limited = sent - allowed
        client.overLimitFor = limited > 0 ? client.overLimitFor + 1 : 0
        // In emergency mode the server refuses most of what tablets ask (see emergency-mode.md).
        const refusedByMode = emergency && !client.robot && client.ip !== CONSOLE_IP ? Math.round(allowed * 0.6) : 0
        const noise = this.random() < 0.04 ? 1 : 0
        second.accepted = Math.max(0, allowed - refusedByMode - noise)
        second.rejected = limited + refusedByMode + noise + failedLogins
        second.loginFailures = failedLogins
        reject('rate_limited', limited)
        reject('emergency_mode', refusedByMode)
        reject(this.random() < 0.5 ? 'invalid' : 'forbidden', noise)
        reject('unauthorized', failedLogins)
        if (limited > 0 && client.status === 'ok') {
          client.status = 'limited'
          client.reason = `Over ${RATE_PER_S} requests/s`
          alerts.push(this.alert(at, 'rate_limited', client.ip, `${client.ip} is sending ${sent} requests/s: rate-limited.`))
        }
        if (limited === 0 && client.status === 'limited') { client.status = 'ok'; client.reason = null }
        const recentFailures = client.seconds.slice(-59).reduce((sum, entry) => sum + entry.loginFailures, 0) + failedLogins
        if (client.overLimitFor >= LIMITED_SECONDS_BEFORE_BLOCK) {
          alerts.push(...this.autoBlock(at, client, `Over ${RATE_PER_S} requests/s for ${LIMITED_SECONDS_BEFORE_BLOCK} s`, 'auto_blocked'))
        } else if (recentFailures >= LOGIN_FAILURES_BEFORE_BLOCK) {
          alerts.push(...this.autoBlock(at, client, `${recentFailures} failed logins in a minute`, 'login_burst'))
        }
      }
      accepted += second.accepted
      rejected += second.rejected
      client.seconds = [...client.seconds, second].slice(-CLIENT_WINDOW_S)
    }

    this.history = [...this.history, { at: new Date(at).toISOString(), accepted, rejected }].slice(-HISTORY_S)
    this.reasonSeconds = [...this.reasonSeconds, { at, reasons }].slice(-HISTORY_S)
    // Answer time: steady, and slower while an attack gets through the limiter.
    const latency = 18 + this.random() * 14 + Math.min(260, attackLoad * 1.4)
    this.latencies = [...this.latencies, latency].slice(-RECENT_RATE_S * 3)
    return alerts
  }

  private autoBlock(at: number, client: ClientState, reason: string, kind: SecurityAlertKind): LiveMessage[] {
    this.blockCount += 1
    this.blocks.push({ id: `blk-${this.blockCount}`, target: client.ip, reason, source: 'auto', createdAt: new Date(at).toISOString(), expiresAt: new Date(at + AUTO_BLOCK_S * 1000).toISOString(), by: null, hits: 0 })
    client.status = 'blocked'
    client.reason = reason
    client.overLimitFor = 0
    return [this.alert(at, kind, client.ip, `${client.ip} blocked automatically for ${AUTO_BLOCK_S / 60} min: ${reason.toLowerCase()}.`)]
  }

  /** A flood from one address and a credential-stuffing run from another. */
  simulateAttack(): void {
    const until = this.clock + ATTACK_S * 1000
    this.addClient({ ip: '203.0.113.42', label: null, rate: 85, loginFailRate: 0, robot: false, until })
    this.addClient({ ip: '198.51.100.7', label: null, rate: 0, loginFailRate: 0.6, robot: false, until })
  }

  /** The server refuses blocks that would cut the clinic off from itself. */
  addBlock(target: string, reason: string, expiresInS: number | null, by: string): BlockRule {
    const clean = target.trim()
    const range = parseTarget(clean)
    if (!range) throw new Error('Give an IPv4 address (10.0.2.21) or a range (203.0.113.0/24).')
    if (range.prefix < 16) throw new Error('This range is too broad: /16 at most. Block smaller ranges.')
    if (matches(clean, CONSOLE_IP)) throw new Error('This would block this console itself.')
    if (matches(clean, '127.0.0.1')) throw new Error('Loopback cannot be blocked.')
    const robot = [...this.clients.values()].find((client) => client.robot && matches(clean, client.ip))
    if (robot) throw new Error(`This would block ${robot.label ?? robot.ip}: robots must stay reachable for the emergency stop.`)
    if (!reason.trim()) throw new Error('Say why: the reason is kept in the audit log.')
    this.blockCount += 1
    const block: BlockRule = { id: `blk-${this.blockCount}`, target: clean, reason: reason.trim(), source: 'manual', createdAt: new Date(this.clock).toISOString(), expiresAt: expiresInS ? new Date(this.clock + expiresInS * 1000).toISOString() : null, by, hits: 0 }
    this.blocks.push(block)
    return { ...block }
  }

  removeBlock(blockId: string): void {
    const block = this.blocks.find((entry) => entry.id === blockId)
    if (!block) throw new Error('This block no longer exists.')
    this.blocks = this.blocks.filter((entry) => entry.id !== blockId)
    for (const client of this.clients.values()) if (matches(block.target, client.ip) && !this.blockFor(client.ip)) { client.status = 'ok'; client.reason = null }
  }

  getBlocks(): BlockRule[] {
    return this.blocks.map((block) => ({ ...block }))
  }

  getTraffic(windowS: number): Traffic {
    const points = this.history.slice(-windowS)
    const rejectedBy: Record<RejectReason, number> = { unauthorized: 0, forbidden: 0, rate_limited: 0, blocked: 0, emergency_mode: 0, invalid: 0 }
    for (const second of this.reasonSeconds.slice(-windowS)) for (const [reason, count] of Object.entries(second.reasons)) rejectedBy[reason as RejectReason] += count ?? 0
    return { stepS: 1, points: points.map((point) => ({ ...point })), rejectedBy, p95Ms: this.p95() }
  }

  private p95(): number | null {
    if (!this.latencies.length) return null
    const sorted = [...this.latencies].sort((a, b) => a - b)
    return Math.round(sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95))])
  }

  getClients(): ClientStat[] {
    return [...this.clients.values()]
      .map((client) => {
        const total = client.seconds.reduce((sum, second) => ({ accepted: sum.accepted + second.accepted, rejected: sum.rejected + second.rejected, loginFailures: sum.loginFailures + second.loginFailures }), { accepted: 0, rejected: 0, loginFailures: 0 })
        const recent = client.seconds.slice(-RECENT_RATE_S).reduce((sum, second) => sum + second.accepted + second.rejected, 0)
        return { ip: client.ip, label: client.label, requestsPerS: Math.round((recent / RECENT_RATE_S) * 10) / 10, requests: total.accepted + total.rejected, rejected: total.rejected, loginFailures: total.loginFailures, status: client.status, reason: client.reason }
      })
      .sort((a, b) => b.requestsPerS - a.requestsPerS || b.rejected - a.rejected)
  }

  getSummary(robotsConnected: number, robotsTotal: number): ServerSummary {
    const recent = this.history.slice(-RECENT_RATE_S)
    const sum = (key: 'accepted' | 'rejected'): number => recent.reduce((total, point) => total + point[key], 0) / Math.max(1, recent.length)
    return {
      startedAt: new Date(this.startedAt).toISOString(),
      uptimeS: Math.round((this.clock - this.startedAt) / 1000),
      version: 'demo',
      robotsConnected,
      robotsTotal,
      appClients: [...this.clients.values()].filter((client) => !client.robot && client.until === null).length,
      journalOk: true,
      databaseOk: true,
      requestsPerS: Math.round((sum('accepted') + sum('rejected')) * 10) / 10,
      rejectedPerS: Math.round(sum('rejected') * 10) / 10,
      p95Ms: this.p95(),
      blockedClients: [...this.clients.values()].filter((client) => client.status === 'blocked').length,
    }
  }
}
