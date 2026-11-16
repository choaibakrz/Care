/** Stock per shelf: current count, threshold, what the robot last counted, and admin adjustment. */
import { useState } from 'react'
import { AlertTriangle, Minus, Plus } from 'lucide-react'
import { backend } from '../lib/backend'
import { ago, errorMessage, placeName } from '../lib/format'
import { EMERGENCY_LOCKED, useEmergency, useStore } from '../state/store'
import type { InventoryItem } from '../types'
import { Chip, Panel } from '../ui/kit'
import { useNow } from '../ui/Shell'
import './pages.css'

function Level({ item }: { item: InventoryItem }) {
  const scale = Math.max(item.count, item.lowAt * 2.5, 1)
  const low = item.count <= item.lowAt
  return (
    <span className={`level ${low ? 'is-low' : ''}`} title={`Threshold ${item.lowAt}`}>
      <b className="mono">{item.count}</b>
      <span className="level-track"><span style={{ width: `${(item.count / scale) * 100}%` }} /><em style={{ left: `${(item.lowAt / scale) * 100}%` }} /></span>
    </span>
  )
}

export function Stock() {
  const emergency = useEmergency()
  const inventory = useStore((state) => state.inventory)
  const map = useStore((state) => state.map)
  const token = useStore((state) => state.session?.token)
  const toast = useStore((state) => state.toast)
  const upsertItem = useStore((state) => state.upsertItem)
  const [busy, setBusy] = useState<string | null>(null)
  const [onlyProblems, setOnlyProblems] = useState(false)
  const now = useNow()

  const mismatch = (item: InventoryItem): boolean => item.lastRobotCount !== null && item.lastRobotCount !== item.count
  const low = inventory.filter((item) => item.count <= item.lowAt)
  const mismatches = inventory.filter(mismatch)
  const shown = onlyProblems ? inventory.filter((item) => item.count <= item.lowAt || mismatch(item)) : inventory
  const places = [...new Set(shown.map((item) => item.place))]

  const adjust = async (item: InventoryItem, delta: number): Promise<void> => {
    if (!token) return
    setBusy(item.id)
    try { upsertItem(await backend.adjustInventory(token, item.id, delta)) } catch (reason) { toast('danger', `${item.label} not changed: ${errorMessage(reason)}`) } finally { setBusy(null) }
  }

  return (
    <>
      <div className="summary-row">
        <div className="stat"><span>Item types</span><strong className="mono">{inventory.length}</strong></div>
        <div className="stat"><span>Units on shelves</span><strong className="mono">{inventory.reduce((sum, item) => sum + item.count, 0)}</strong></div>
        <div className={`stat ${low.length ? 'is-alarm' : ''}`}><span>Low stock</span><strong className="mono">{low.length}</strong></div>
        <div className={`stat ${mismatches.length ? 'is-warn' : ''}`}><span>Robot count differs</span><strong className="mono">{mismatches.length}</strong></div>
      </div>
      <Panel flush title="Stock by shelf" eyebrow="Counts" actions={<button type="button" className={`toggle ${onlyProblems ? 'is-on' : ''}`} onClick={() => setOnlyProblems(!onlyProblems)}><AlertTriangle size={14} />Only problems</button>}>
        <table className="table is-static">
          <thead><tr><th>Item</th><th>Count</th><th>Threshold</th><th>Last robot count</th><th>Adjust</th></tr></thead>
          {places.map((place) => (
            <tbody key={place}>
              <tr className="group-row"><td colSpan={5}><span className="eyebrow">{placeName(map, place)}</span></td></tr>
              {shown.filter((item) => item.place === place).map((item) => (
                <tr key={item.id}>
                  <td><strong>{item.label}</strong>{item.count <= item.lowAt && <small className="is-coral">Below threshold</small>}</td>
                  <td><Level item={item} /></td>
                  <td className="mono muted">{item.lowAt}</td>
                  <td>
                    {item.lastRobotCount === null ? <span className="muted">Not counted yet</span> : (
                      <>
                        <span className={mismatch(item) ? 'mismatch' : 'mono'}>{mismatch(item) && <AlertTriangle size={13} />}<span className="mono">{item.lastRobotCount}</span>{mismatch(item) && ' · differs'}</span>
                        <small className="muted">{ago(item.lastRobotCountAt, now)}</small>
                      </>
                    )}
                  </td>
                  <td>
                    <span className="stepper">
                      <button type="button" disabled={busy === item.id || item.count === 0 || emergency} title={emergency ? EMERGENCY_LOCKED : undefined} onClick={() => { void adjust(item, -1) }} aria-label={`One less ${item.label}`}><Minus size={14} /></button>
                      <button type="button" disabled={busy === item.id || emergency} title={emergency ? EMERGENCY_LOCKED : undefined} onClick={() => { void adjust(item, 1) }} aria-label={`One more ${item.label}`}><Plus size={14} /></button>
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          ))}
        </table>
        {!places.length && <p className="read-only" style={{ padding: 16 }}><Chip tone="mint">All good</Chip>No low stock and no count difference.</p>}
      </Panel>
    </>
  )
}
