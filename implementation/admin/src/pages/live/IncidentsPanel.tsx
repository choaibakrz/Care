/** Open incidents next to the map, most serious first. Only there when something is open. */
import { Link } from 'react-router-dom'
import { byUrgency } from '../../lib/incidents'
import { useStore } from '../../state/store'
import { Panel } from '../../ui/kit'
import { IncidentRow } from '../incidents/IncidentRow'

const SHOWN = 4

export function IncidentsPanel({ now }: { now: number }) {
  const incidents = useStore((state) => state.incidents)
  if (!incidents.length) return null
  const sorted = [...incidents].sort(byUrgency)
  const critical = incidents.filter((incident) => incident.severity === 'critical').length
  return (
    <Panel title="Incidents" eyebrow={`${incidents.length} open${critical ? ` · ${critical} critical` : ''}`} className="incidents-panel" actions={<Link className="button is-small" to="/incidents">All incidents</Link>}>
      <div className="card-pad">
        <ul className="incident-list">{sorted.slice(0, SHOWN).map((incident) => <IncidentRow key={incident.id} incident={incident} now={now} compact />)}</ul>
        {sorted.length > SHOWN && <p className="incidents-more">{sorted.length - SHOWN} more on the Incidents page.</p>}
      </div>
    </Panel>
  )
}
