/** The night restock round: when it runs, which robot, and what the last round counted. */
import { useEffect, useState } from 'react'
import { CalendarClock, CheckCircle2, MoonStar, Play, TriangleAlert } from 'lucide-react'
import { backend } from '../lib/backend'
import { config } from '../lib/config'
import { dayTime, errorMessage, placeName } from '../lib/format'
import { EMERGENCY_LOCKED, useEmergency, useStore } from '../state/store'
import type { Schedule } from '../types'
import { Empty, Panel } from '../ui/kit'
import './pages.css'

const RESULT_LABEL: Record<Schedule['lastResult'], string> = { success: 'Every count matched', partial: 'Done, some counts differ', failed: 'Did not run', never: 'Not run yet' }

export function Night() {
  const emergency = useEmergency()
  const schedule = useStore((state) => state.schedules[0])
  const inventory = useStore((state) => state.inventory)
  const map = useStore((state) => state.map)
  const token = useStore((state) => state.session?.token)
  const toast = useStore((state) => state.toast)
  const upsertSchedule = useStore((state) => state.upsertSchedule)
  const [draft, setDraft] = useState<Schedule | undefined>(schedule)
  const [busy, setBusy] = useState(false)

  useEffect(() => { setDraft((current) => current && schedule && current.id === schedule.id ? { ...schedule, enabled: current.enabled, time: current.time } : schedule) }, [schedule])
  if (!schedule || !draft) return <Panel><Empty icon={<CalendarClock size={20} />} title="No schedule">The server has no night round set.</Empty></Panel>

  const changed = draft.enabled !== schedule.enabled || draft.time !== schedule.time
  const low = inventory.filter((item) => item.count <= item.lowAt)

  const save = async (): Promise<void> => {
    if (!token) return
    setBusy(true)
    try { upsertSchedule(await backend.putSchedule(token, draft)); toast('success', 'Night round saved.') } catch (reason) { toast('danger', `Not saved: ${errorMessage(reason)}`) } finally { setBusy(false) }
  }
  const runNow = async (): Promise<void> => {
    if (!token) return
    setBusy(true)
    try {
      const refusal = await backend.runRoundNow(token, schedule.id)
      if (refusal) toast('warning', refusal); else toast('success', `Round started with ${schedule.robotId}. Follow it on the live map.`)
    } catch (reason) { toast('danger', errorMessage(reason)) } finally { setBusy(false) }
  }

  return (
    <div className="cards">
      <Panel title={schedule.label} eyebrow="Schedule" actions={<button type="button" className={`switch ${draft.enabled ? 'is-on' : ''}`} aria-pressed={draft.enabled} aria-label="Round on or off" onClick={() => setDraft({ ...draft, enabled: !draft.enabled })} />}>
        <div className="card-pad">
          <p>Each night, {schedule.robotId ?? 'the night robot'} visits every shelf of its floor, counts what it sees, and sends the counts to the server. Every move still goes through the robot's safety checks.</p>
          <label className="field">Departure time<input className="input mono" type="time" value={draft.time} onChange={(event) => setDraft({ ...draft, time: event.target.value })} disabled={!draft.enabled} /></label>
          <dl className="kv">
            <div><dt>State</dt><dd>{draft.enabled ? <span className="is-mint">On · next at {draft.time}</span> : <span className="muted">Off</span>}</dd></div>
            <div><dt>Robot</dt><dd className="mono">{schedule.robotId ?? '—'}</dd></div>
          </dl>
          <div className="inline-actions">
            <button type="button" className="button is-primary" disabled={!changed || busy || emergency} title={emergency ? EMERGENCY_LOCKED : undefined} onClick={() => { void save() }}>Save</button>
            {config.useMock && <button type="button" className="button" disabled={busy || emergency} title={emergency ? EMERGENCY_LOCKED : undefined} onClick={() => { void runNow() }}><Play size={14} />Run a round now (demo)</button>}
          </div>
        </div>
      </Panel>

      <Panel title="Last round" eyebrow={schedule.lastRun ? dayTime(schedule.lastRun) : 'Never'}>
        <div className="card-pad">
          <span className={`result-badge result-${schedule.lastResult}`}>{schedule.lastResult === 'success' ? <CheckCircle2 size={17} /> : schedule.lastResult === 'never' ? <MoonStar size={17} /> : <TriangleAlert size={17} />}{RESULT_LABEL[schedule.lastResult]}</span>
          {schedule.lastCounts.length ? (
            <table className="table is-static">
              <thead><tr><th>Item</th><th>Shelf</th><th>List</th><th>Counted</th></tr></thead>
              <tbody>
                {schedule.lastCounts.map((count) => (
                  <tr key={`${count.place}-${count.item}`}>
                    <td>{count.item}</td>
                    <td className="muted">{placeName(map, count.place)}</td>
                    <td className="mono">{count.expected}</td>
                    <td className={`mono ${count.counted !== count.expected ? 'mismatch' : ''}`}>{count.counted}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p>No count yet.</p>}
        </div>
      </Panel>

      <Panel title="Low stock for the next round" eyebrow={`${low.length} item(s)`}>
        <div className="card-pad">
          {low.length ? (
            <table className="table is-static">
              <thead><tr><th>Item</th><th>Shelf</th><th>Left</th><th>Threshold</th></tr></thead>
              <tbody>{low.map((item) => <tr key={item.id}><td>{item.label}</td><td className="muted">{placeName(map, item.place)}</td><td className="mono is-coral">{item.count}</td><td className="mono muted">{item.lowAt}</td></tr>)}</tbody>
            </table>
          ) : <p>Every item is above its threshold.</p>}
        </div>
      </Panel>
    </div>
  )
}
