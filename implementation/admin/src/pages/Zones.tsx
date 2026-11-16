/** Zones: draw, move, delete. Shows what each zone does and which robots have received it. */
import { useState } from 'react'
import { Check, Clock, EarOff, Hexagon, Mic, MicOff, Plus, ShieldAlert, Trash2, X } from 'lucide-react'
import { backend } from '../lib/backend'
import { displayState, errorMessage, floorName } from '../lib/format'
import { pointInPolygon, polygonArea } from '../lib/geometry'
import { EMERGENCY_LOCKED, useEmergency, useStore } from '../state/store'
import type { Point, Zone, ZoneKind } from '../types'
import { askConfirm } from '../ui/confirm'
import { Chip, Empty, Panel, Segmented } from '../ui/kit'
import { useNow } from '../ui/Shell'
import { PlanEditor } from './zones/PlanEditor'
import './pages.css'
import './zones.css'

const EXPLAIN: Record<ZoneKind, string> = {
  deaf: 'In this zone the robot does not listen. It closes its own microphone when it enters and opens it again when it leaves, even if the connection is lost.',
  restricted: 'Robots should stay out of this zone. Advisory only: today this zone is shown to the staff but it is not sent to the robot’s safety guard, so nothing forces a robot to stay out.',
}

function samePolygon(a: Point[], b: Point[]): boolean {
  return a.length === b.length && a.every((point, index) => point[0] === b[index][0] && point[1] === b[index][1])
}

export function Zones() {
  const emergency = useEmergency()
  const zones = useStore((state) => state.zones)
  const robots = useStore((state) => state.robots)
  const map = useStore((state) => state.map)
  const floor = useStore((state) => state.floor)
  const setFloor = useStore((state) => state.setFloor)
  const token = useStore((state) => state.session?.token)
  const toast = useStore((state) => state.toast)
  const upsertZone = useStore((state) => state.upsertZone)
  const removeZone = useStore((state) => state.removeZone)
  const now = useNow()
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [draft, setDraft] = useState<Zone | null>(null)
  const [drawing, setDrawing] = useState(false)
  const [busy, setBusy] = useState(false)

  if (!map) return <Panel><Empty title="Loading the map…" /></Panel>

  const floorZones = zones.filter((zone) => zone.floor === floor)
  const saved = zones.find((zone) => zone.id === (draft?.id ?? selectedId)) ?? (draft ? undefined : floorZones[0])
  const current = draft ?? saved ?? null
  const isNew = Boolean(draft) && !zones.some((zone) => zone.id === draft?.id)
  const dirty = Boolean(draft) && (isNew || !saved || draft?.name !== saved.name || draft?.kind !== saved.kind || !samePolygon(draft?.polygon ?? [], saved.polygon))
  const edit = (change: Partial<Zone>): void => { if (current) setDraft({ ...current, ...change }) }

  const select = (zone: Zone): void => { setSelectedId(zone.id); setDraft(null); setDrawing(false); if (zone.floor !== floor) setFloor(zone.floor) }
  const startNew = (): void => {
    setDraft({ id: `zone-${Date.now().toString(36)}`, name: 'New zone', floor, kind: 'deaf', polygon: [], deliveries: [] })
    setDrawing(true)
  }
  const discard = (): void => { setDraft(null); setDrawing(false) }

  const save = async (): Promise<void> => {
    if (!token || !draft) return
    if (draft.polygon.length < 3) { toast('warning', 'A zone needs at least three corners.'); return }
    setBusy(true)
    try {
      const answer = await backend.putZone(token, draft)
      // The robots' acks (zone.updated over the socket) can arrive before this answer: keep a
      // "received" they already reported for this same shape instead of going back to "waiting".
      const live = useStore.getState().zones.find((entry) => entry.id === answer.id)
      const sameShape = live && live.name === answer.name && live.kind === answer.kind && samePolygon(live.polygon, answer.polygon)
      const zone = sameShape ? { ...answer, deliveries: answer.deliveries.map((delivery) => live.deliveries.find((known) => known.robotId === delivery.robotId && known.status === 'received') ?? delivery) } : answer
      upsertZone(zone)
      setSelectedId(zone.id)
      setDraft(null)
      setDrawing(false)
      toast('success', `“${zone.name}” saved. Sending it to the robots.`)
    } catch (reason) { toast('danger', `Zone not saved: ${errorMessage(reason)}`) } finally { setBusy(false) }
  }

  const remove = async (): Promise<void> => {
    if (!token || !saved) return
    if (!await askConfirm({ title: `Delete “${saved.name}”?`, body: saved.kind === 'deaf' ? 'Robots will listen again in this area.' : 'The advisory zone disappears from the map.', confirmLabel: 'Delete the zone', danger: true })) return
    setBusy(true)
    try { await backend.deleteZone(token, saved.id); removeZone(saved.id); setSelectedId(null); setDraft(null); toast('success', `“${saved.name}” deleted.`) } catch (reason) { toast('danger', `Zone not deleted: ${errorMessage(reason)}`) } finally { setBusy(false) }
  }

  const floorRobots = robots.filter((robot) => robot.position.floor === floor).map((robot) => ({ robot, state: displayState(robot, now) }))
  const inside = current && current.polygon.length >= 3 ? floorRobots.filter(({ robot }) => pointInPolygon(robot.position.x, robot.position.y, current.polygon)) : []

  return (
    <div className="zones">
      <Panel className="zone-list" title="Zones" eyebrow={`${zones.length} in the clinic`} actions={<button type="button" className="button is-primary is-small" onClick={startNew} disabled={drawing || emergency} title={emergency ? EMERGENCY_LOCKED : undefined} data-testid="new-zone"><Plus size={14} />New zone</button>}>
        <ul>
          {zones.map((zone) => {
            const received = zone.deliveries.filter((delivery) => delivery.status === 'received').length
            return (
              <li key={zone.id}>
                <button type="button" className={`zone-row kind-${zone.kind} ${zone.id === current?.id ? 'is-selected' : ''}`} onClick={() => select(zone)}>
                  <span className="zone-icon">{zone.kind === 'deaf' ? <EarOff size={15} /> : <ShieldAlert size={15} />}</span>
                  <span><strong>{zone.name}</strong><small>{zone.kind === 'deaf' ? 'Deaf' : 'Restricted · advisory only'} · {floorName(map, zone.floor)}</small></span>
                  <b className="mono" title="Robots that have received this zone">{received}/{zone.deliveries.length}</b>
                </button>
              </li>
            )
          })}
        </ul>
        {!zones.length && <Empty icon={<Hexagon size={20} />} title="No zone yet">Draw the first one on the plan.</Empty>}
      </Panel>

      <Panel flush className="zone-plan">
        <div className="filters">
          <Segmented label="Floor" value={floor} options={map.floors.map((entry) => ({ value: entry.id, label: entry.label }))} onChange={(value) => { setFloor(value); discard(); setSelectedId(null) }} />
          <p className="plan-help">{drawing ? <><b>Drawing.</b> Click the plan to add corners. Click the first corner to close.</> : current ? 'Drag a corner or the shape · “+” adds a corner · double-click removes one' : 'Pick a zone, or draw a new one.'}</p>
        </div>
        <PlanEditor map={map} floor={floor} zone={current && current.floor === floor ? current : null} others={floorZones.filter((zone) => zone.id !== current?.id)} robots={floorRobots} drawing={drawing} onChange={(polygon) => edit({ polygon })} onFinishDrawing={() => setDrawing(false)} />
      </Panel>

      <Panel className="zone-form" title={current ? current.name : 'No zone selected'} eyebrow={isNew ? 'New zone' : 'Zone'}>
        {current ? (
          <div className="card-pad">
            <label className="field">Name<input className="input" value={current.name} onChange={(event) => edit({ name: event.target.value })} maxLength={60} /></label>
            <div className="field">Kind
              <Segmented label="Kind" value={current.kind} options={[{ value: 'deaf', label: <><EarOff size={14} />Deaf</> }, { value: 'restricted', label: <><ShieldAlert size={14} />Restricted</> }]} onChange={(kind) => edit({ kind })} />
            </div>
            <p className={`zone-explain kind-${current.kind}`}>{current.kind === 'restricted' && <Chip tone="pink">Advisory only</Chip>}{EXPLAIN[current.kind]}</p>
            <dl className="kv">
              <div><dt>Corners</dt><dd className="mono">{current.polygon.length}</dd></div>
              <div><dt>Area</dt><dd className="mono">{current.polygon.length >= 3 ? `${polygonArea(current.polygon).toFixed(1)} m²` : '—'}</dd></div>
              <div><dt>Robots inside now</dt><dd>{inside.length ? inside.map(({ robot }) => <Chip key={robot.id} tone={robot.micOpen ? 'mint' : 'blue'}>{robot.micOpen ? <Mic size={12} /> : <MicOff size={12} />}{robot.id} mic {robot.micOpen ? 'open' : 'closed'}</Chip>) : <span className="muted">None</span>}</dd></div>
            </dl>
            <div className="inline-actions">
              <button type="button" className="button is-primary" disabled={!dirty || busy || emergency || drawing && current.polygon.length < 3} title={emergency ? EMERGENCY_LOCKED : undefined} onClick={() => { void save() }} data-testid="save-zone"><Check size={15} />{isNew ? 'Create zone' : 'Save changes'}</button>
              {draft && <button type="button" className="button is-ghost" onClick={discard}><X size={15} />Discard</button>}
              {!isNew && saved && <button type="button" className="button is-danger" disabled={busy || emergency} title={emergency ? EMERGENCY_LOCKED : undefined} onClick={() => { void remove() }}><Trash2 size={15} />Delete</button>}
            </div>
            {!isNew && saved && (
              <div>
                <p className="eyebrow">Received by</p>
                <ul className="deliveries" data-testid="deliveries">
                  {saved.deliveries.map((delivery) => (
                    <li key={delivery.robotId} className={`is-${delivery.status}`}>
                      {delivery.status === 'received' ? <Check size={13} /> : delivery.status === 'pending' ? <Clock size={13} /> : <X size={13} />}
                      <b className="mono">{delivery.robotId}</b>{delivery.status === 'received' ? 'received' : delivery.status === 'pending' ? 'waiting…' : 'failed'}
                    </li>
                  ))}
                </ul>
                {dirty && <p className="detail-note">Unsaved changes. Robots still use the saved shape.</p>}
              </div>
            )}
          </div>
        ) : <Empty icon={<Hexagon size={20} />} title="Pick a zone">Or press “New zone” and draw it on the plan.</Empty>}
      </Panel>
    </div>
  )
}
