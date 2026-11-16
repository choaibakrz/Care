/**
 * One incident: what, where, since when, who is on it, and the two actions (acknowledge, close).
 * Patient alarms show neither action: they are handled in the emergency service.
 */
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { BellRing, Check, CheckCheck, TriangleAlert } from 'lucide-react'
import { backend } from '../../lib/backend'
import { ago, errorMessage, floorName, placeName } from '../../lib/format'
import { SEVERITY_COLOR, SEVERITY_LABEL, canAcknowledge, incidentAdvice, incidentTitle } from '../../lib/incidents'
import { useStore } from '../../state/store'
import type { Incident } from '../../types'
import './incidents.css'

export function IncidentRow({ incident, now, compact = false }: { incident: Incident; now: number; compact?: boolean }) {
  const map = useStore((state) => state.map)
  const token = useStore((state) => state.session?.token ?? '')
  const selected = useStore((state) => state.selectedIncidentId === incident.id)
  const selectIncident = useStore((state) => state.selectIncident)
  const applyIncident = useStore((state) => state.applyIncident)
  const toast = useStore((state) => state.toast)
  const [busy, setBusy] = useState(false)
  const alarm = incident.code === 'emergency_alarm'
  const Icon = alarm ? BellRing : TriangleAlert
  const where = [incident.place ? placeName(map, incident.place) : null, incident.floor !== null ? floorName(map, incident.floor) : null].filter(Boolean).join(' · ')
  const what = incident.subject ? `${incident.subject.kind === 'robot' ? 'Robot' : 'Tablet'} ${incident.subject.id}` : null

  const act = async (name: 'acknowledge' | 'close'): Promise<void> => {
    setBusy(true)
    try {
      applyIncident(name === 'acknowledge' ? await backend.acknowledgeIncident(token, incident.id) : await backend.closeIncident(token, incident.id))
      toast('success', name === 'acknowledge' ? `${incidentTitle(incident)}: you are on it.` : `${incidentTitle(incident)}: closed.`)
    } catch (reason) {
      toast('danger', `Not ${name === 'acknowledge' ? 'acknowledged' : 'closed'}: ${errorMessage(reason)}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className={`incident ${compact ? 'is-compact' : ''} ${selected ? 'is-selected' : ''} ${incident.closedAt ? 'is-closed' : ''}`} style={{ '--incident': SEVERITY_COLOR[incident.severity] } as CSSProperties} data-testid={`incident-${incident.id}`}>
      <button type="button" className="incident-main" onClick={() => selectIncident(incident.id)} title="Show on the map">
        <span className="incident-badge"><Icon size={14} aria-hidden="true" />{SEVERITY_LABEL[incident.severity]}</span>
        <strong>{incidentTitle(incident)}</strong>
        <small>{[where, what].filter(Boolean).join(' · ') || 'Whole system'}</small>
        <small className="incident-time">{incident.closedAt ? `Closed ${ago(incident.closedAt, now)}` : `Since ${ago(incident.openedAt, now).replace(' ago', '')}`}{incident.repeats ? ` · raised ${incident.repeats + 1} times` : ''}{incident.acknowledgedBy ? ` · ${incident.acknowledgedBy} is on it` : ''}</small>
        {!compact && incidentAdvice(incident) && <small className="incident-advice">{incidentAdvice(incident)}</small>}
      </button>
      {!incident.closedAt && (alarm ? (
        <span className="incident-note">In the emergency service</span>
      ) : (
        <span className="incident-actions">
          {canAcknowledge(incident) && <button type="button" className="button is-small" disabled={busy} onClick={() => { void act('acknowledge') }} title="Say you are on it" data-testid={`incident-ack-${incident.id}`}><Check size={13} />{compact ? '' : 'On it'}</button>}
          <button type="button" className="button is-small" disabled={busy} onClick={() => { void act('close') }} title="Close: it is solved" data-testid={`incident-close-${incident.id}`}><CheckCheck size={13} />{compact ? '' : 'Close'}</button>
        </span>
      ))}
    </li>
  )
}
