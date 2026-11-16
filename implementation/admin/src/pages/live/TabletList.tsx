/** The tablets, as rows like the robots: in use first, then free, then offline. */
import type { CSSProperties } from 'react'
import { BedDouble, Stethoscope, WifiOff } from 'lucide-react'
import { placeName } from '../../lib/format'
import { tabletColor, tabletTitle } from '../../scene/tablet'
import { useStore } from '../../state/store'
import type { Tablet } from '../../types'
import { Battery } from '../../ui/kit'

function rank(tablet: Tablet): number {
  if (!tablet.online) return 2
  return tablet.assigned ? 0 : 1
}

export function TabletList() {
  const tablets = useStore((state) => state.tablets)
  const map = useStore((state) => state.map)
  const selectedTabletId = useStore((state) => state.selectedTabletId)
  const selectTablet = useStore((state) => state.selectTablet)
  const sorted = [...tablets].sort((a, b) => rank(a) - rank(b) || a.kind.localeCompare(b.kind) || a.label.localeCompare(b.label))
  if (!sorted.length) return <p className="fleet-empty">No tablet is known to the server right now.</p>
  return (
    <ul className="fleet-list">
      {sorted.map((tablet) => {
        const Icon = tablet.kind === 'bedside' ? BedDouble : Stethoscope
        const status = !tablet.online ? 'Offline' : tablet.assigned ? (tablet.kind === 'bedside' ? 'Bedside' : tablet.speciality ?? 'Staff') : 'Free'
        return (
          <li key={tablet.id}>
            <button type="button" className={`fleet-row ${tablet.id === selectedTabletId ? 'is-selected' : ''} ${tablet.online ? '' : 'is-offline'}`} style={{ '--state': tabletColor(tablet) } as CSSProperties} onClick={() => selectTablet(tablet.id)} data-testid={`tablet-${tablet.id}`}>
              <span className="fleet-id"><Icon size={15} aria-label={tablet.kind === 'bedside' ? 'Bedside tablet' : 'Staff tablet'} /></span>
              <span className="fleet-main">
                <strong>{tabletTitle(tablet)}</strong>
                <small>{status} · {placeName(map, tablet.place)}</small>
              </span>
              {!tablet.online && <WifiOff size={13} className="fleet-mic" aria-label="Offline" />}
              {tablet.battery !== null ? <Battery value={tablet.battery} compact /> : <span className="mono is-muted" title="The server does not report this tablet's battery">—</span>}
            </button>
          </li>
        )
      })}
    </ul>
  )
}
