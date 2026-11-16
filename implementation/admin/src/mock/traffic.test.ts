import { describe, expect, test } from 'vitest'
import { toBlock, toClient, toLiveMessage, toSummary, toTraffic } from '../lib/adapt'
import type { LiveMessage } from '../types'
import { CONSOLE_IP, LIMITED_SECONDS_BEFORE_BLOCK, TrafficSim, matches } from './traffic'
import { mulberry32 } from './sim-state'

const START = Date.parse('2026-11-15T09:00:00Z')

function network(): { sim: TrafficSim; run: (seconds: number, emergency?: boolean) => LiveMessage[] } {
  const sim = new TrafficSim(START, mulberry32(5))
  let clock = START
  return {
    sim,
    run: (seconds, emergency = false) => {
      const alerts: LiveMessage[] = []
      for (let second = 0; second < seconds; second++) { clock += 1000; alerts.push(...sim.step(1, clock, emergency)) }
      return alerts
    },
  }
}

function status(sim: TrafficSim, ip: string): string | undefined {
  return sim.getClients().find((client) => client.ip === ip)?.status
}

describe('attack detection in the demo server', () => {
  test('a flood is rate-limited at once, then blocked automatically', () => {
    const { sim, run } = network()
    sim.simulateAttack()
    const first = run(1)
    expect(status(sim, '203.0.113.42')).toBe('limited')
    expect(first).toContainEqual(expect.objectContaining({ type: 'security.alert', alert: expect.objectContaining({ kind: 'rate_limited', ip: '203.0.113.42' }) }))
    const later = run(LIMITED_SECONDS_BEFORE_BLOCK)
    expect(status(sim, '203.0.113.42')).toBe('blocked')
    expect(later).toContainEqual(expect.objectContaining({ alert: expect.objectContaining({ kind: 'auto_blocked', ip: '203.0.113.42' }) }))
    expect(sim.getBlocks().some((block) => block.target === '203.0.113.42' && block.source === 'auto')).toBe(true)
  })

  test('repeated failed logins get an address blocked', () => {
    const { sim, run } = network()
    sim.simulateAttack()
    const alerts = run(40)
    expect(alerts).toContainEqual(expect.objectContaining({ alert: expect.objectContaining({ kind: 'login_burst', ip: '198.51.100.7' }) }))
    expect(status(sim, '198.51.100.7')).toBe('blocked')
  })

  test('normal clinic traffic is never limited', () => {
    const { sim, run } = network()
    run(60)
    expect(sim.getClients().every((client) => client.status === 'ok')).toBe(true)
  })

  test('a manual block refuses everything from that range, and removing it lets it through', () => {
    const { sim, run } = network()
    const rule = sim.addBlock('10.0.2.0/24', 'Test', 3600, 'admin')
    run(3)
    expect(status(sim, '10.0.2.21')).toBe('blocked')
    expect(sim.getTraffic(3).rejectedBy.blocked).toBeGreaterThan(0)
    sim.removeBlock(rule.id)
    run(1)
    expect(status(sim, '10.0.2.21')).toBe('ok')
  })

  test('the console, loopback, robots and huge ranges cannot be blocked', () => {
    const { sim } = network()
    expect(() => sim.addBlock(CONSOLE_IP, 'x', null, 'admin')).toThrow(/console/)
    expect(() => sim.addBlock('127.0.0.1', 'x', null, 'admin')).toThrow(/Loopback/)
    expect(() => sim.addBlock('10.0.3.12', 'x', null, 'admin')).toThrow(/Robot R2/)
    expect(() => sim.addBlock('10.0.0.0/8', 'x', null, 'admin')).toThrow(/too broad/)
    expect(() => sim.addBlock('not-an-ip', 'x', null, 'admin')).toThrow(/IPv4/)
    expect(() => sim.addBlock('203.0.113.9', '  ', null, 'admin')).toThrow(/why/)
  })

  test('emergency mode refusals are counted with their own reason', () => {
    const { sim, run } = network()
    run(20, true)
    expect(sim.getTraffic(20).rejectedBy.emergency_mode).toBeGreaterThan(0)
  })

  test('ranges match the right addresses', () => {
    expect(matches('203.0.113.0/24', '203.0.113.42')).toBe(true)
    expect(matches('203.0.113.0/24', '203.0.114.1')).toBe(false)
    expect(matches('10.0.2.21', '10.0.2.21')).toBe(true)
  })
})

describe('monitor readers (requirements/monitoring-security.md examples)', () => {
  test('GET /monitor/summary', () => {
    expect(toSummary({ started_at: '2026-11-15T06:00:00Z', uptime_s: 10800, version: '0.4.0', robots_connected: 3, robots_total: 4, app_clients: 6, journal_ok: true, database_ok: true, requests_per_s: 12.4, rejected_per_s: 0.3, p95_ms: 28, blocked_clients: 1 })).toEqual({ startedAt: '2026-11-15T06:00:00Z', uptimeS: 10800, version: '0.4.0', robotsConnected: 3, robotsTotal: 4, appClients: 6, journalOk: true, databaseOk: true, requestsPerS: 12.4, rejectedPerS: 0.3, p95Ms: 28, blockedClients: 1 })
  })

  test('GET /monitor/traffic', () => {
    const traffic = toTraffic({ step_s: 1, p95_ms: 31, points: [{ at: '2026-11-15T09:00:00Z', accepted: 11, rejected: 0 }, { at: '2026-11-15T09:00:01Z', accepted: 12, rejected: 45 }], rejected_by: { rate_limited: 45, unauthorized: 2 } })
    expect(traffic?.points).toHaveLength(2)
    expect(traffic?.rejectedBy).toEqual({ unauthorized: 2, forbidden: 0, rate_limited: 45, blocked: 0, emergency_mode: 0, invalid: 0 })
  })

  test('GET /monitor/clients and /security/blocks entries', () => {
    expect(toClient({ ip: '203.0.113.42', label: null, requests_per_s: 84.2, requests: 2410, rejected: 2300, login_failures: 0, status: 'blocked', reason: 'Over 20 requests/s for 5 s' })).toMatchObject({ ip: '203.0.113.42', status: 'blocked', requestsPerS: 84.2 })
    expect(toBlock({ id: 'blk-3', target: '203.0.113.0/24', reason: 'Flooding the login page', source: 'manual', created_at: '2026-11-15T09:02:00Z', expires_at: null, by: 'Admin A', hits: 120 })).toMatchObject({ id: 'blk-3', target: '203.0.113.0/24', source: 'manual', expiresAt: null, hits: 120 })
  })

  test('security.alert', () => {
    const message = { type: 'security.alert', id: '00000000-0000-4000-8000-000000000001', ts: '2026-11-15T09:01:05Z', alert: { at: '2026-11-15T09:01:05Z', kind: 'auto_blocked', ip: '203.0.113.42', message: '203.0.113.42 blocked automatically for 10 min: over 20 requests/s for 5 s.' } }
    expect(toLiveMessage(message)).toEqual({ type: 'security.alert', alert: message.alert })
  })
})
