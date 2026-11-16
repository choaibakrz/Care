/** The audit log. Read only: the panel offers no way to edit or delete an entry. */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Lock, RefreshCw, ScrollText, Search } from 'lucide-react'
import { backend } from '../lib/backend'
import { dayTime, errorMessage } from '../lib/format'
import { useStore } from '../state/store'
import type { AuditEntry, AuditResult } from '../types'
import { Chip, Empty, Panel } from '../ui/kit'
import './pages.css'

const RESULT: Record<AuditResult, { label: string; tone: 'mint' | 'amber' | 'coral' }> = { ok: { label: 'OK', tone: 'mint' }, refused: { label: 'Refused', tone: 'amber' }, failed: { label: 'Failed', tone: 'coral' } }
const PERIODS = [['all', 'Any time'], ['15', 'Last 15 min'], ['60', 'Last hour'], ['1440', 'Last 24 h']] as const

export function Audit() {
  const token = useStore((state) => state.session?.token)
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [query, setQuery] = useState('')
  const [actor, setActor] = useState('')
  const [period, setPeriod] = useState<string>('all')

  const load = useCallback(async (): Promise<void> => {
    if (!token) return
    setLoading(true)
    try {
      const from = period === 'all' ? undefined : new Date(Date.now() - Number(period) * 60000).toISOString()
      setEntries(await backend.getAudit(token, { actor: actor || undefined, from }))
      setError('')
    } catch (reason) { setError(errorMessage(reason)) } finally { setLoading(false) }
  }, [token, actor, period])

  useEffect(() => { void load() }, [load])
  useEffect(() => {
    const timer = window.setInterval(() => { void load() }, 10000)
    return () => window.clearInterval(timer)
  }, [load])

  const actors = useMemo(() => [...new Set(entries.map((entry) => entry.actor))].sort(), [entries])
  const shown = entries.filter((entry) => !query.trim() || `${entry.action} ${entry.target} ${entry.detail ?? ''} ${entry.actor}`.toLowerCase().includes(query.trim().toLowerCase()))

  return (
    <Panel flush>
      <div className="filters">
        <div className="filter-tools">
          <label className="search"><Search size={15} /><input placeholder="Action, robot, zone…" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
          <select className="select is-compact" value={actor} onChange={(event) => setActor(event.target.value)} aria-label="Actor">
            <option value="">Everyone</option>
            {[...new Set([...actors, actor].filter(Boolean))].map((name) => <option key={name} value={name}>{name}</option>)}
          </select>
          <select className="select is-compact" value={period} onChange={(event) => setPeriod(event.target.value)} aria-label="Time">
            {PERIODS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </div>
        <button type="button" className="button is-small" onClick={() => { void load() }} disabled={loading}><RefreshCw size={14} />Refresh</button>
      </div>
      {error ? <Empty title="The log did not load">{error}</Empty> : shown.length ? (
        <table className="table is-static">
          <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Target</th><th>Result</th></tr></thead>
          <tbody>
            {shown.map((entry) => (
              <tr key={entry.id}>
                <td className="mono muted">{dayTime(entry.at)}</td>
                <td>{entry.actor}</td>
                <td><strong>{entry.action}</strong>{entry.detail && <small>{entry.detail}</small>}</td>
                <td className="mono">{entry.target}</td>
                <td><Chip tone={RESULT[entry.result].tone}>{RESULT[entry.result].label}</Chip></td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : <Empty icon={<ScrollText size={20} />} title={loading ? 'Loading…' : 'No entry matches'} />}
      <p className="read-only" style={{ padding: '0 16px 16px' }}><Lock size={13} />Read only. Entries cannot be edited or deleted from this panel.</p>
    </Panel>
  )
}
