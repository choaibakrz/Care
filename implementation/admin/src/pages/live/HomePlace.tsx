/** The fleet's home place: where robots go in an emergency, on "dock" and to recharge. */
import { useState } from 'react'
import { backend } from '../../lib/backend'
import { errorMessage, floorName } from '../../lib/format'
import { useStore } from '../../state/store'
import { Panel } from '../../ui/kit'

const NONE = ''

export function HomePlace() {
  const map = useStore((state) => state.map)
  const home = useStore((state) => state.fleetHome)
  const token = useStore((state) => state.session?.token ?? null)
  const [saving, setSaving] = useState(false)
  const places = map ? [...map.places].sort((a, b) => a.floor - b.floor || a.label.localeCompare(b.label)) : []

  const choose = (value: string): void => {
    if (!token || saving) return
    const { setFleetHome, toast } = useStore.getState()
    setSaving(true)
    backend.setFleetHome(token, value === NONE ? null : value).then((next) => {
      setFleetHome(next)
      toast('success', next.placeId ? `Home place set: ${next.label ?? next.placeId}.` : 'No home place: robots stop where they are.')
    }, (reason: unknown) => toast('warning', `The home place was not saved: ${errorMessage(reason)}`)).finally(() => setSaving(false))
  }

  return (
    <Panel title="Home / charging place" eyebrow={home?.placeId ? `🏠 ${home.label ?? home.placeId}` : 'Not set'} className="home-panel">
      <div className="home-place">
        <select className="input" aria-label="Home place" value={home?.placeId ?? NONE} disabled={!token || saving || !map} onChange={(event) => choose(event.target.value)} data-testid="home-place-select">
          <option value={NONE}>None: stop in place</option>
          {places.map((place) => <option key={place.id} value={place.id}>{place.label || place.id} · {floorName(map, place.floor)}{place.kind === 'dock' ? ' · dock' : ''}</option>)}
        </select>
        <small>Robots go here in an emergency, on "Send to dock" and below 20% battery. Simulated robots can be dragged on the map.</small>
      </div>
    </Panel>
  )
}
