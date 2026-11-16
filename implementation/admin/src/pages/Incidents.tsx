/**
 * Every incident: open ones live from the store, closed ones on request. Filter by severity.
 * Patient alarms are listed (mirrored from the emergency service) but never acknowledged here.
 */
import { useEffect, useState } from 'react'
import { BellRing, ShieldCheck } from 'lucide-react'
import { config } from '../lib/config'
import { backend } from '../lib/backend'
import { errorMessage } from '../lib/format'
import { byUrgency } from '../lib/incidents'
import { useStore } from '../state/store'
import type { Incident, IncidentSeverity } from '../types'
import { Empty, Panel, Segmented } from '../ui/kit'
import { useNow } from '../ui/Shell'
import { IncidentRow } from './incidents/IncidentRow'
import './pages.css'

type Show = 'open' | 'all'
type Level = 'any' | IncidentSeverity

/** Demo only: a patient presses the button in a room of the demo clinic. */
async function playDemoAlarm(): Promise<void> {
  const { demoControls } = await import('../mock/server')
  demoControls.patientAlarm('room-13', 'urgent')
}

export function Incidents() {
  const now = useNow()
  const open = useStore((state) => state.incidents)
  const token = useStore((state) => state.session?.token ?? '')
  const toast = useStore((state) => state.toast)
  const [show, setShow] = useState<Show>('open')
  const [level, setLevel] = useState<Level>('any')
  const [closed, setClosed] = useState<Incident[]>([])
  const [error, setError] = useState<string | null>(null)

  // Closed incidents are not kept in memory: read them when asked, and again when one closes.
  useEffect(() => {
    if (show !== 'all' || !token) return undefined
    let stopped = false
    backend.getIncidents(token, true).then((all) => { if (!stopped) { setClosed(all.filter((incident) => incident.closedAt)); setError(null) } }, (reason: unknown) => { if (!stopped) setError(errorMessage(reason)) })
    return () => { stopped = true }
  }, [show, token, open.length])

  const shown = [...open, ...(show === 'all' ? closed.filter((incident) => !open.some((entry) => entry.id === incident.id)) : [])]
    .filter((incident) => level === 'any' || incident.severity === level)
    .sort((a, b) => (a.closedAt ? 1 : 0) - (b.closedAt ? 1 : 0) || byUrgency(a, b))

  return (
    <div className="cards is-wide">
      <Panel
        title="Incidents"
        eyebrow={`${open.length} open`}
        actions={(
          <div className="inline-actions">
            <Segmented label="Show" value={show} onChange={setShow} options={[{ value: 'open', label: 'Open' }, { value: 'all', label: 'With closed' }]} />
            <Segmented label="Severity" value={level} onChange={setLevel} options={[{ value: 'any', label: 'All' }, { value: 'critical', label: 'Critical' }, { value: 'warning', label: 'Warning' }, { value: 'info', label: 'Info' }]} />
            {config.useMock && <button type="button" className="button is-small is-danger" onClick={() => { void playDemoAlarm().then(() => toast('info', 'Demo: a patient alarm from Room 13. The emergency service resolves it in 45 s.')) }} data-testid="demo-alarm"><BellRing size={14} />Patient alarm (demo)</button>}
          </div>
        )}
      >
        <div className="card-pad">
          {error && <p className="incidents-error" role="alert">Closed incidents could not be read: {error}</p>}
          {shown.length ? <ul className="incident-list">{shown.map((incident) => <IncidentRow key={incident.id} incident={incident} now={now} />)}</ul> : <Empty icon={<ShieldCheck size={20} />} title={show === 'open' ? 'Nothing open' : 'No incident'}>Robots, tablets and the emergency link are fine.</Empty>}
          <p className="incidents-note">Patient alarms come from the emergency service, which pages the staff. They show here and on the map, and are acknowledged there. This list never names a patient.</p>
        </div>
      </Panel>
    </div>
  )
}
