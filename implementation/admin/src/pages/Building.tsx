/** Edits the active clinic plan as a local draft, floor by floor. Saving sends the differences from the base plan as the overlay (`PUT .../overlay`, `If-Match`). */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { RotateCcw, Save, Trash2, Undo2 } from 'lucide-react'
import { config } from '../lib/config'
import { errorMessage } from '../lib/format'
import { ApiError, getBasePlan, getClinic, listClinics, resetOverlay, saveOverlay } from '../lib/http'
import { countModifications, diffOverlay, newId, nextFloorId, problemShapes } from '../lib/plan'
import { useStore } from '../state/store'
import type { ClinicPlan, PlaceKind, Point, PropKind, RoomKind } from '../types'
import { askConfirm } from '../ui/confirm'
import { Empty, Panel, Segmented } from '../ui/kit'
import { Problems } from './Clinics'
import { BuildingPlan } from './building/BuildingPlan'
import type { Selection, Tool } from './building/BuildingPlan'
import './pages.css'
import './building/building.css'

const ROOM_KINDS: RoomKind[] = ['room', 'corridor', 'elevator', 'care', 'storage', 'therapy', 'pool', 'lounge']
const PLACE_KINDS: PlaceKind[] = ['room', 'shelf', 'dock', 'point']
const PROP_KINDS: PropKind[] = ['bed', 'counter', 'desk', 'shelf', 'cabinet', 'sofa', 'armchair', 'table', 'plant', 'dock', 'pool', 'bench', 'crate', 'mat', 'bars', 'nightstand', 'door']
const HELP: Record<Tool, string> = {
  select: 'Click a room, wall or place. Drag corners, click a + to add one, double-click a corner to remove it.',
  room: 'Click the corners of the room. Click the first corner again to close it.',
  wall: 'Click the points of the wall, then press Finish wall.',
  place: 'Click where the new place goes.',
  prop: 'Click where the new piece of furniture goes. Drag it to move it.',
  floor: 'Click the corners of the floor outline. Click the first corner again to close it.',
}

function asError(reason: unknown): ApiError {
  return reason instanceof ApiError ? reason : new ApiError(errorMessage(reason), 0, 'error')
}

export function Building() {
  const token = useStore((state) => state.session?.token) ?? ''
  const toast = useStore((state) => state.toast)
  const [clinicId, setClinicId] = useState<string | null>(null)
  const [version, setVersion] = useState('')
  const [draft, setDraft] = useState<ClinicPlan | null>(null)
  const [base, setBase] = useState<ClinicPlan | null>(null)
  const [propKind, setPropKind] = useState<PropKind>('table')
  const [dirty, setDirty] = useState(false)
  const [floor, setFloor] = useState(0)
  const [tool, setTool] = useState<Tool>('select')
  const [selection, setSelection] = useState<Selection>(null)
  const [pending, setPending] = useState<Point[]>([])
  const [error, setError] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const active = (await listClinics(token)).find((clinic) => clinic.active)
      if (!active) throw new Error('No clinic plan is active.')
      const loaded = await getClinic(token, active.id)
      setBase((await getBasePlan(token, active.id)).plan)
      setClinicId(active.id); setVersion(loaded.version); setDraft(loaded.plan); setDirty(false); setError(null); setSelection(null); setPending([])
      setFloor((current) => loaded.plan.floors.some((entry) => entry.id === current) ? current : loaded.plan.floors[0]?.id ?? 0)
    } catch (reason) { setError(asError(reason)) }
  }, [token])
  useEffect(() => { if (!config.useMock) void load() }, [load])

  const bad = useMemo(() => problemShapes(error?.details ?? []), [error])
  const overlay = useMemo(() => (base && draft ? diffOverlay(base, draft, Number(version) || 0) : null), [base, draft, version])
  const modifications = overlay ? countModifications(overlay) : 0

  if (config.useMock) return <Panel title="Building"><Empty title="Clinic plans need the server">The demo clinic runs in the browser and cannot be edited. Set VITE_USE_MOCK=false.</Empty></Panel>
  if (!draft || !clinicId || !base || !overlay) return <div className="stack"><Problems error={error} /><Empty title="Loading the active plan…" /></div>

  const edit = (change: (plan: ClinicPlan) => ClinicPlan): void => { setDraft(change(draft)); setDirty(true) }
  const chooseTool = (next: Tool): void => { setTool(next); setPending([]); setSelection(null) }

  const finish = (): void => {
    if (tool === 'floor' && pending.length >= 3) {
      edit((plan) => ({ ...plan, floors: plan.floors.map((entry) => entry.id === floor ? { ...entry, outline: pending } : entry) }))
      setSelection(null); setPending([]); setTool('select'); return
    }
    if (tool === 'room' && pending.length >= 3) edit((plan) => ({ ...plan, rooms: [...plan.rooms, { id: newId('room'), floor, label: 'New room', kind: 'room', polygon: pending }] }))
    else if (tool === 'wall' && pending.length >= 2) edit((plan) => ({ ...plan, walls: [...plan.walls, { id: newId('wall'), floor, points: pending }] }))
    else return
    setSelection({ kind: tool, index: (tool === 'room' ? draft.rooms.length : draft.walls.length) })
    setPending([]); setTool('select')
  }

  const addPoint = (at: Point): void => {
    if (tool === 'place') {
      edit((plan) => ({ ...plan, places: [...plan.places, { id: newId('place'), label: 'New place', floor, x: at[0], y: at[1], kind: 'point' }] }))
      setSelection({ kind: 'place', index: draft.places.length }); setTool('select')
    } else if (tool === 'prop') {
      edit((plan) => ({ ...plan, props: [...plan.props, { id: newId('prop'), floor, kind: propKind, x: at[0], y: at[1], width: 1, depth: 1, solid: true }] }))
      setSelection({ kind: 'prop', index: draft.props.length }); setTool('select')
    } else setPending([...pending, at])
  }

  const setPoints = (kind: 'room' | 'wall' | 'floor', index: number, points: Point[]): void =>
    edit((plan) => kind === 'room'
      ? { ...plan, rooms: plan.rooms.map((room, i) => i === index ? { ...room, polygon: points } : room) }
      : kind === 'floor'
        ? { ...plan, floors: plan.floors.map((entry, i) => i === index ? { ...entry, outline: points } : entry) }
        : { ...plan, walls: plan.walls.map((wall, i) => i === index ? { ...wall, points } : wall) })

  const changeProp = (index: number, change: Partial<ClinicPlan['props'][number]>): void =>
    edit((plan) => ({ ...plan, props: plan.props.map((entry, i) => i === index ? { ...entry, ...change } : entry) }))

  const addFloor = (): void => {
    const id = nextFloorId(draft)
    edit((plan) => ({ ...plan, floors: [...plan.floors, { id, label: `Floor ${id}`, outline: [] }] }))
    setFloor(id); setSelection(null); setPending([]); setTool('floor')
  }

  const remove = (): void => {
    if (!selection) return
    const { kind, index } = selection
    if (kind === 'floor') {
      const gone = draft.floors[index]
      if (!gone) return
      const used = [draft.rooms, draft.places, draft.walls, draft.props].some((items) => items.some((item) => item.floor === gone.id))
      if (used) { toast('danger', `“${gone.label}” still has rooms, places, walls or furniture. Delete them first.`); return }
      edit((plan) => ({ ...plan, floors: plan.floors.filter((_, i) => i !== index) }))
      setFloor(draft.floors.find((entry) => entry.id !== gone.id)?.id ?? 0); setSelection(null)
      return
    }
    edit((plan) => kind === 'room' ? { ...plan, rooms: plan.rooms.filter((_, i) => i !== index) } : kind === 'prop' ? { ...plan, props: plan.props.filter((_, i) => i !== index) } : kind === 'wall' ? { ...plan, walls: plan.walls.filter((_, i) => i !== index) } : { ...plan, places: plan.places.filter((_, i) => i !== index) })
    setSelection(null)
  }

  const save = async (): Promise<void> => {
    setBusy(true); setError(null)
    try {
      const saved = await saveOverlay(token, clinicId, overlay, version)
      setDraft(saved.plan); setVersion(saved.version); setDirty(false)
      toast('success', 'Modifications saved. The live map redraws.')
    } catch (reason) { setError(asError(reason)) }
    setBusy(false)
  }

  const resetModifications = async (): Promise<void> => {
    if (!(await askConfirm({ title: 'Reset all modifications?', body: 'The plan goes back to the base design. Furniture and floor edits are dropped.', confirmLabel: 'Reset', danger: true }))) return
    setBusy(true); setError(null)
    try {
      const saved = await resetOverlay(token, clinicId, version)
      setDraft(saved.plan); setBase(saved.plan); setVersion(saved.version); setDirty(false); setSelection(null)
      toast('success', 'Modifications reset.')
    } catch (reason) { setError(asError(reason)) }
    setBusy(false)
  }

  /** 412: someone saved meanwhile. Keep the draft, take the server's version number, and save again to overwrite. */
  const keepDraft = async (): Promise<void> => {
    try { setVersion((await getClinic(token, clinicId)).version); setError(null) } catch (reason) { setError(asError(reason)) }
  }

  const room = selection?.kind === 'room' ? draft.rooms[selection.index] : null
  const place = selection?.kind === 'place' ? draft.places[selection.index] : null
  const prop = selection?.kind === 'prop' ? draft.props[selection.index] : null
  const floorEntry = selection?.kind === 'floor' ? draft.floors[selection.index] : null

  return (
    <div className="stack">
      <Problems error={error} />
      {error?.status === 412 && (
        <div className="plan-error"><div className="row-actions">
          <button type="button" className="button" onClick={() => void load()}>Reload server version (discard draft)</button>
          <button type="button" className="button" onClick={() => void keepDraft()}>Keep editing (my save will overwrite)</button>
        </div></div>
      )}
      <div className="building">
        <Panel title={draft.name} eyebrow={`Active plan · version ${version} · ${modifications} modification${modifications === 1 ? '' : 's'}${dirty ? ' · unsaved changes' : ''}`} actions={<>
          <button type="button" className="button" disabled={busy || modifications === 0} onClick={() => void resetModifications()}><RotateCcw size={14} /> Reset modifications</button>
          <button type="button" className="button" disabled={!dirty || busy} onClick={() => void load()}><Undo2 size={14} /> Discard</button>
          <button type="button" className="button is-primary" disabled={!dirty || busy} onClick={() => void save()}><Save size={14} /> Save</button>
        </>}>
          <div className="building-tools">
            <Segmented label="Floor" value={floor} options={draft.floors.map((entry) => ({ value: entry.id, label: entry.label }))} onChange={(next) => { setFloor(next); setSelection(null); setPending([]) }} />
            <Segmented<Tool> label="Tool" value={tool} options={[{ value: 'select', label: 'Select' }, { value: 'room', label: 'Add room' }, { value: 'wall', label: 'Add wall' }, { value: 'place', label: 'Add place' }, { value: 'prop', label: 'Add furniture' }]} onChange={chooseTool} />
            {tool === 'prop' && <select className="input" aria-label="Furniture kind" value={propKind} onChange={(event) => setPropKind(event.target.value as PropKind)}>{PROP_KINDS.map((kind) => <option key={kind}>{kind}</option>)}</select>}
            <button type="button" className="button" onClick={addFloor}>Add floor</button>
            {tool === 'wall' && <button type="button" className="button" disabled={pending.length < 2} onClick={finish}>Finish wall</button>}
            <span className="plan-help">{HELP[tool]}</span>
          </div>
          <BuildingPlan plan={draft} floor={floor} tool={tool} selection={selection} pending={pending} bad={bad} onSelect={setSelection} onPoints={setPoints}
            onMovePlace={(index, at) => edit((plan) => ({ ...plan, places: plan.places.map((entry, i) => i === index ? { ...entry, x: at[0], y: at[1] } : entry) }))}
            onMoveProp={(index, at) => changeProp(index, { x: at[0], y: at[1] })}
            onAddPoint={addPoint} onFinish={finish} />
        </Panel>
        <Panel title={selection ? { room: 'Room', wall: 'Wall', place: 'Place', prop: 'Furniture', floor: 'Floor' }[selection.kind] : 'Selection'}>
          <div className="building-side">
            {!selection && <p className="plan-help">Nothing selected.</p>}
            {room && selection && <>
              <label>Name<input className="input" value={room.label} onChange={(event) => edit((plan) => ({ ...plan, rooms: plan.rooms.map((entry, i) => i === selection.index ? { ...entry, label: event.target.value } : entry) }))} /></label>
              <label>Kind<select className="input" value={room.kind} onChange={(event) => edit((plan) => ({ ...plan, rooms: plan.rooms.map((entry, i) => i === selection.index ? { ...entry, kind: event.target.value as RoomKind } : entry) }))}>{ROOM_KINDS.map((kind) => <option key={kind}>{kind}</option>)}</select></label>
            </>}
            {place && selection && <>
              <label>Name<input className="input" value={place.label} onChange={(event) => edit((plan) => ({ ...plan, places: plan.places.map((entry, i) => i === selection.index ? { ...entry, label: event.target.value } : entry) }))} /></label>
              <label>Kind<select className="input" value={place.kind} onChange={(event) => edit((plan) => ({ ...plan, places: plan.places.map((entry, i) => i === selection.index ? { ...entry, kind: event.target.value as PlaceKind } : entry) }))}>{PLACE_KINDS.map((kind) => <option key={kind}>{kind}</option>)}</select></label>
            </>}
            {prop && selection && <>
              <label>Kind<select className="input" value={prop.kind} onChange={(event) => changeProp(selection.index, { kind: event.target.value as PropKind })}>{PROP_KINDS.map((kind) => <option key={kind}>{kind}</option>)}</select></label>
              <label>Width (m)<input className="input" type="number" min="0.1" step="0.1" value={prop.width} onChange={(event) => changeProp(selection.index, { width: Number(event.target.value) })} /></label>
              <label>Depth (m)<input className="input" type="number" min="0.1" step="0.1" value={prop.depth} onChange={(event) => changeProp(selection.index, { depth: Number(event.target.value) })} /></label>
              <label><input type="checkbox" checked={prop.solid} onChange={(event) => changeProp(selection.index, { solid: event.target.checked })} /> Solid (robots go around it)</label>
            </>}
            {floorEntry && selection && <label>Name<input className="input" value={floorEntry.label} onChange={(event) => edit((plan) => ({ ...plan, floors: plan.floors.map((entry, i) => i === selection.index ? { ...entry, label: event.target.value } : entry) }))} /></label>}
            {selection && <button type="button" className="button is-danger" onClick={remove}><Trash2 size={14} /> Delete</button>}
          </div>
        </Panel>
      </div>
    </div>
  )
}
