/**
 * Server health, traffic, attacks and blocks, and how the service is doing.
 *
 * Everything comes from the server (`requirements/monitoring-security.md`). A part the server does
 * not have yet says so, and the rest of the page keeps working. The patient part is counts only.
 */
import { useState } from 'react'
import type { FormEvent } from 'react'
import { Ban, CheckCircle2, Gauge, ShieldAlert, ShieldCheck, Siren, Swords } from 'lucide-react'
import { config } from '../lib/config'
import { backend } from '../lib/backend'
import { ago, errorMessage, placeName } from '../lib/format'
import { serviceFromTasks } from '../lib/service'
import { useStore } from '../state/store'
import type { BlockRule, ClientStat, ClientStatus, RejectReason, SecurityAlert } from '../types'
import { askConfirm } from '../ui/confirm'
import { useNow } from '../ui/Shell'
import { Chip, Empty, Panel, Ticker } from '../ui/kit'
import { BarList, LineChart } from './monitor/charts'
import { SERVICE_HOURS, WINDOW_S, useMonitor } from './monitor/useMonitor'
import './pages.css'
import './monitor/monitor.css'

const REASON_LABEL: Record<RejectReason, string> = {
  rate_limited: 'Rate-limited (429)',
  blocked: 'Blocked address',
  unauthorized: 'Not signed in / bad login (401)',
  forbidden: 'Not allowed (403)',
  emergency_mode: 'Emergency mode (503)',
  invalid: 'Invalid request (4xx)',
}

const STATUS: Record<ClientStatus, { tone: 'mint' | 'amber' | 'coral'; label: string; icon: typeof CheckCircle2 }> = {
  ok: { tone: 'mint', label: 'OK', icon: CheckCircle2 },
  limited: { tone: 'amber', label: 'Limited', icon: Gauge },
  blocked: { tone: 'coral', label: 'Blocked', icon: Ban },
}

const DURATIONS: Array<{ label: string; seconds: number | null }> = [
  { label: '15 minutes', seconds: 900 },
  { label: '1 hour', seconds: 3600 },
  { label: '24 hours', seconds: 86400 },
  { label: 'Until removed', seconds: null },
]

const QUICK_BLOCK_S = 3600

function uptime(seconds: number): string {
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return days ? `${days} d ${hours} h` : hours ? `${hours} h ${minutes} min` : `${minutes} min`
}

function duration(seconds: number | null): string {
  if (seconds === null) return '—'
  return seconds < 90 ? `${Math.round(seconds)} s` : `${(seconds / 60).toFixed(1)} min`
}

function remaining(expiresAt: string | null, now: number): string {
  if (!expiresAt) return 'Until removed'
  const minutes = Math.max(0, Math.round((Date.parse(expiresAt) - now) / 60000))
  return minutes >= 120 ? `${Math.round(minutes / 60)} h left` : minutes >= 1 ? `${minutes} min left` : 'Under a minute'
}

function NotOnServer({ what }: { what: string }) {
  return <p className="viz-empty">The server does not report {what} yet. See <code>requirements/monitoring-security.md</code>.</p>
}

function Tile({ label, value, note, tone }: { label: string; value: React.ReactNode; note: string; tone?: 'alarm' | 'warn' }) {
  return (
    <div className={`kpi-tile ${tone ? `is-${tone}` : ''}`}>
      <span>{label}</span>
      <strong className="mono">{value}</strong>
      <small>{note}</small>
    </div>
  )
}

function useToken(): string {
  return useStore((state) => state.session?.token ?? '')
}

function ClientsTable({ clients, blocks, onChange }: { clients: ClientStat[]; blocks: BlockRule[]; onChange: () => void }) {
  const token = useToken()
  const toast = useStore((state) => state.toast)
  const [busy, setBusy] = useState<string | null>(null)

  const block = async (client: ClientStat): Promise<void> => {
    const sure = await askConfirm({ title: `Block ${client.ip}?`, body: `Every request from this address is refused for 1 hour. ${client.label ? `The server knows it as “${client.label}”.` : 'The server does not know this address.'}`, confirmLabel: 'Block for 1 hour', danger: true })
    if (!sure) return
    setBusy(client.ip)
    try {
      await backend.addBlock(token, { target: client.ip, reason: 'Blocked by hand from the Monitor page', expiresInS: QUICK_BLOCK_S })
      toast('success', `${client.ip} is blocked for 1 hour.`)
      onChange()
    } catch (reason) {
      toast('danger', `Not blocked: ${errorMessage(reason)}`)
    } finally {
      setBusy(null)
    }
  }

  const unblock = async (client: ClientStat): Promise<void> => {
    const rule = blocks.find((entry) => entry.target === client.ip)
    if (!rule) { toast('warning', `${client.ip} is blocked by a range. Remove the range in the block list below.`); return }
    setBusy(client.ip)
    try {
      await backend.removeBlock(token, rule.id)
      toast('success', `${client.ip} is no longer blocked.`)
      onChange()
    } catch (reason) {
      toast('danger', `Not unblocked: ${errorMessage(reason)}`)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="table-wrap">
      <table className="monitor-table" data-testid="clients-table">
        <thead><tr><th>Address</th><th>Known as</th><th className="num">Req/s</th><th className="num">Refused (5 min)</th><th className="num">Failed logins</th><th>Status</th><th /></tr></thead>
        <tbody>
          {clients.map((client) => {
            const status = STATUS[client.status]
            const Icon = status.icon
            return (
              <tr key={client.ip} className={client.status !== 'ok' ? `is-${client.status}` : ''}>
                <td className="mono">{client.ip}</td>
                <td>{client.label ?? <span className="is-unknown">Unknown</span>}</td>
                <td className="num mono">{client.requestsPerS}</td>
                <td className="num mono">{client.rejected}</td>
                <td className="num mono">{client.loginFailures}</td>
                <td><Chip tone={status.tone} title={client.reason ?? undefined}><Icon size={12} />{status.label}</Chip>{client.reason && <small className="row-reason">{client.reason}</small>}</td>
                <td className="row-action">
                  {client.status === 'blocked'
                    ? <button type="button" className="button is-small" disabled={busy === client.ip} onClick={() => { void unblock(client) }}>Unblock</button>
                    : <button type="button" className="button is-small is-danger" disabled={busy === client.ip} onClick={() => { void block(client) }} data-testid={`block-${client.ip}`}>Block</button>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function BlockList({ blocks, now, onChange }: { blocks: BlockRule[]; now: number; onChange: () => void }) {
  const token = useToken()
  const toast = useStore((state) => state.toast)
  const [target, setTarget] = useState('')
  const [reason, setReason] = useState('')
  const [seconds, setSeconds] = useState<number | null>(3600)
  const [busy, setBusy] = useState(false)

  const add = async (event: FormEvent): Promise<void> => {
    event.preventDefault()
    setBusy(true)
    try {
      const rule = await backend.addBlock(token, { target: target.trim(), reason: reason.trim(), expiresInS: seconds })
      toast('success', `${rule.target} is blocked.`)
      setTarget('')
      setReason('')
      onChange()
    } catch (error) {
      toast('danger', `Not blocked: ${errorMessage(error)}`)
    } finally {
      setBusy(false)
    }
  }

  const remove = async (rule: BlockRule): Promise<void> => {
    try {
      await backend.removeBlock(token, rule.id)
      toast('success', `${rule.target} is no longer blocked.`)
      onChange()
    } catch (error) {
      toast('danger', `Not removed: ${errorMessage(error)}`)
    }
  }

  return (
    <div className="block-list">
      <form className="block-form" onSubmit={(event) => { void add(event) }}>
        <label className="field">Address or range<input className="input mono" value={target} onChange={(event) => setTarget(event.target.value)} placeholder="203.0.113.42 or 203.0.113.0/24" required data-testid="block-target" /></label>
        <label className="field">Reason (kept in the audit log)<input className="input" value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Flooding the login page" required maxLength={200} /></label>
        <label className="field">For<select className="select" value={seconds ?? ''} onChange={(event) => setSeconds(event.target.value ? Number(event.target.value) : null)}>{DURATIONS.map((entry) => <option key={entry.label} value={entry.seconds ?? ''}>{entry.label}</option>)}</select></label>
        <button type="submit" className="button is-danger" disabled={busy || !target.trim() || !reason.trim()} data-testid="block-add"><Ban size={15} />Block</button>
      </form>
      <p className="monitor-hint">The server refuses to block this console, loopback, or a robot's address: robots must stay reachable for the emergency stop.</p>
      {blocks.length ? (
        <div className="table-wrap">
          <table className="monitor-table">
            <thead><tr><th>Address or range</th><th>Why</th><th>By</th><th>Until</th><th className="num">Refused</th><th /></tr></thead>
            <tbody>
              {blocks.map((rule) => (
                <tr key={rule.id}>
                  <td className="mono">{rule.target}</td>
                  <td>{rule.reason}</td>
                  <td>{rule.source === 'auto' ? <Chip tone="amber"><ShieldAlert size={12} />Automatic</Chip> : rule.by ?? 'Admin'}</td>
                  <td>{remaining(rule.expiresAt, now)}</td>
                  <td className="num mono">{rule.hits}</td>
                  <td className="row-action"><button type="button" className="button is-small" onClick={() => { void remove(rule) }}>Remove</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p className="viz-empty">No address is blocked.</p>}
    </div>
  )
}

function AlertsFeed({ alerts, now }: { alerts: SecurityAlert[]; now: number }) {
  if (!alerts.length) return <Empty icon={<ShieldCheck size={20} />} title="Nothing detected">Rate limits and automatic blocks show up here as they happen.</Empty>
  return (
    <ul className="alert-feed">
      {alerts.map((alert) => (
        <li key={`${alert.at}-${alert.ip}-${alert.kind}`} className={`is-${alert.kind}`}>
          {alert.kind === 'rate_limited' ? <Gauge size={14} /> : alert.kind === 'unblocked' ? <ShieldCheck size={14} /> : <Ban size={14} />}
          <div><p>{alert.message}</p><small>{ago(alert.at, now)}</small></div>
        </li>
      ))}
    </ul>
  )
}

async function startDemoAttack(): Promise<void> {
  const { demoControls } = await import('../mock/server')
  demoControls.simulateAttack()
}

export function Monitor() {
  const now = useNow()
  const token = useToken()
  const data = useMonitor(token || null)
  const alerts = useStore((state) => state.securityAlerts)
  const robots = useStore((state) => state.robots)
  const tasks = useStore((state) => state.tasks)
  const tablets = useStore((state) => state.tablets)
  const map = useStore((state) => state.map)
  const mode = useStore((state) => state.mode)
  const toast = useStore((state) => state.toast)
  const { summary, traffic, clients, blocks, service: serverService } = data

  // Until the server has `/stats/service`, the same numbers come from the tasks this console knows.
  const service = serverService ?? (serverService === null ? serviceFromTasks(tasks, tablets, now, SERVICE_HOURS) : undefined)
  const rejectedTotal = traffic ? Object.values(traffic.rejectedBy).reduce((sum, value) => sum + value, 0) : 0
  const deliveredShare = service && service.delivered + service.failed ? Math.round((service.delivered / (service.delivered + service.failed)) * 100) : null

  return (
    <div className="monitor">
      {data.error && <div className="banner is-warning" role="alert"><ShieldAlert size={17} /><div><strong>The monitor stopped updating.</strong> {data.error}</div></div>}

      <section className="kpi-row" aria-label="Server health">
        {summary ? (
          <>
            <Tile label="Up for" value={uptime(summary.uptimeS)} note={summary.version ? `Version ${summary.version}` : 'Version not reported'} />
            <Tile label="Requests" value={<><Ticker value={summary.requestsPerS} format={(value) => value.toFixed(1)} />/s</>} note="Last 10 seconds" />
            <Tile label="Refused" value={<><Ticker value={summary.rejectedPerS} format={(value) => value.toFixed(1)} />/s</>} note={summary.requestsPerS ? `${Math.round((summary.rejectedPerS / summary.requestsPerS) * 100)}% of requests` : 'No traffic'} tone={summary.requestsPerS && summary.rejectedPerS / summary.requestsPerS > 0.3 ? 'alarm' : undefined} />
            <Tile label="Answer time (p95)" value={summary.p95Ms !== null ? `${summary.p95Ms} ms` : '—'} note="95% of answers are faster" tone={summary.p95Ms !== null && summary.p95Ms > 150 ? 'warn' : undefined} />
            <Tile label="Robots connected" value={`${summary.robotsConnected}/${summary.robotsTotal}`} note={`${summary.appClients} apps on the live stream`} tone={summary.robotsConnected < summary.robotsTotal ? 'warn' : undefined} />
            <Tile label="Blocked addresses" value={summary.blockedClients} note={`Journal ${summary.journalOk === false ? 'FAILING' : summary.journalOk ? 'OK' : '—'} · database ${summary.databaseOk === false ? 'FAILING' : summary.databaseOk ? 'OK' : '—'}`} tone={summary.journalOk === false || summary.databaseOk === false ? 'alarm' : summary.blockedClients ? 'warn' : undefined} />
          </>
        ) : summary === null ? (
          <>
            <Tile label="Robots connected" value={`${robots.filter((robot) => now - Date.parse(robot.lastSeen) < 5000).length}/${robots.length}`} note="From the live stream" />
            <Tile label="Server mode" value={mode?.mode === 'emergency' ? 'Emergency' : 'Normal'} note="The rest is not reported yet" tone={mode?.mode === 'emergency' ? 'alarm' : undefined} />
          </>
        ) : <p className="viz-empty">Loading…</p>}
      </section>

      <div className="monitor-grid">
        <Panel title="Traffic" eyebrow={`Last ${WINDOW_S / 60} minutes · requests per second`} className="span-2">
          <div className="card-pad">
            {traffic ? (
              <LineChart title="Requests per second" unit="req/s" times={traffic.points.map((point) => point.at)} series={[
                { key: 'accepted', label: 'Accepted', color: 'var(--series-1)', values: traffic.points.map((point) => point.accepted) },
                { key: 'rejected', label: 'Refused', color: 'var(--series-2)', values: traffic.points.map((point) => point.rejected) },
              ]} />
            ) : traffic === null ? <NotOnServer what="its traffic" /> : <p className="viz-empty">Loading…</p>}
          </div>
        </Panel>

        <Panel title="Why requests were refused" eyebrow={`${rejectedTotal} in ${WINDOW_S / 60} minutes`}>
          <div className="card-pad">
            {traffic ? <BarList empty="Nothing was refused." rows={(Object.keys(REASON_LABEL) as RejectReason[]).map((reason) => ({ key: reason, label: REASON_LABEL[reason], value: traffic.rejectedBy[reason] })).sort((a, b) => b.value - a.value)} /> : traffic === null ? <NotOnServer what="refusals" /> : null}
          </div>
        </Panel>

        <Panel title="Who is calling the server" eyebrow="Busiest addresses, last 5 minutes" className="span-2" actions={config.useMock ? <button type="button" className="button is-small is-danger" onClick={() => { void startDemoAttack().then(() => toast('info', 'Demo attack started: a flood from 203.0.113.42 and failed logins from 198.51.100.7.')) }} data-testid="demo-attack"><Swords size={14} />Simulate an attack (demo)</button> : undefined}>
          {clients ? (clients.length ? <ClientsTable clients={clients} blocks={blocks ?? []} onChange={data.refresh} /> : <p className="viz-empty card-pad">No traffic.</p>) : clients === null ? <div className="card-pad"><NotOnServer what="per-address traffic" /></div> : null}
        </Panel>

        <Panel title="Security alerts" eyebrow="Live, newest first">
          <div className="card-pad"><AlertsFeed alerts={alerts} now={now} /></div>
        </Panel>

        <Panel title="Blocked addresses" eyebrow="Automatic and by hand" className="span-3">
          <div className="card-pad">
            {blocks ? <BlockList blocks={blocks} now={now} onChange={data.refresh} /> : blocks === null ? <NotOnServer what="its block list" /> : null}
          </div>
        </Panel>

        <Panel title="How the service is doing" eyebrow={`Last ${SERVICE_HOURS} hours · counts only, never a person${serverService === null ? ' · from the tasks this console knows' : ''}`} className="span-3">
          {service ? (
            <div className="service">
              <div className="kpi-row is-compact">
                <Tile label="Requests" value={service.requests} note={`${service.delivered} delivered · ${service.failed} failed`} />
                <Tile label="Delivered" value={deliveredShare !== null ? `${deliveredShare}%` : '—'} note="Of finished requests" tone={deliveredShare !== null && deliveredShare < 80 ? 'warn' : undefined} />
                <Tile label="Wait (median)" value={duration(service.medianWaitS)} note={`90% within ${duration(service.p90WaitS)}`} />
                <Tile label="Bedside tablets online" value={`${service.bedsideOnline}/${service.bedsideTotal}`} note="Tablets assigned to a bed" tone={service.bedsideOnline < service.bedsideTotal ? 'warn' : undefined} />
              </div>
              <div className="service-bars">
                <div><h3>Most asked for</h3><BarList empty="No request yet." rows={service.byItem.map((entry) => ({ key: entry.label, label: entry.label, value: entry.count }))} /></div>
                <div><h3>Busiest places</h3><BarList empty="No request yet." rows={service.byPlace.map((entry) => ({ key: entry.place, label: placeName(map, entry.place), value: entry.count }))} /></div>
              </div>
            </div>
          ) : <p className="viz-empty card-pad">Loading…</p>}
        </Panel>
      </div>

      {mode?.mode === 'emergency' && <p className="monitor-note"><Siren size={14} />Emergency mode is on: refusals with reason “Emergency mode” are expected.</p>}
    </div>
  )
}
