import { AlertTriangle, Bot, ClipboardList, MicOff } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { ago } from '../../lib/format'
import { useStore } from '../../state/store'
import type { EventKind } from '../../state/events'
import { Empty, Panel } from '../../ui/kit'

const ICON: Record<EventKind, typeof Bot> = { task: ClipboardList, robot: Bot, mic: MicOff, alert: AlertTriangle }

export function ActivityFeed({ now }: { now: number }) {
  const events = useStore((state) => state.events)
  return (
    <Panel title="Live activity" eyebrow="Newest first" className="activity" actions={<NavLink className="text-link" to="/audit">Audit log</NavLink>}>
      {events.length ? (
        <ol className="activity-list">
          {events.slice(0, 7).map((event) => {
            const Icon = ICON[event.kind]
            return (
              <li key={event.id} className={`tone-${event.tone}`}>
                <span className="activity-icon"><Icon size={14} /></span>
                <div><strong>{event.title}</strong><small>{event.detail}</small></div>
                <time className="mono">{ago(event.at, now)}</time>
              </li>
            )
          })}
        </ol>
      ) : <Empty title="Nothing yet">Events appear here as robots work.</Empty>}
    </Panel>
  )
}
