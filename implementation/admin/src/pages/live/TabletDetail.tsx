/**
 * The selected tablet: who or which bed uses it, battery, where it is, what that bed asked for,
 * and the controls to free it or hand it out. Nothing about a patient beyond the bed label.
 */
import { useState } from 'react'
import { BedDouble, LogOut, Plus, Radio, Stethoscope } from 'lucide-react'
import { backend } from '../../lib/backend'
import { ago, errorMessage, floorName, isOpenTask, placeName, TASK_LABEL, taskTitle } from '../../lib/format'
import { tabletTitle } from '../../scene/tablet'
import { tabletFloor, useStore } from '../../state/store'
import type { Tablet, TabletKind } from '../../types'
import { askConfirm } from '../../ui/confirm'
import { Battery, Chip, Panel } from '../../ui/kit'

const MAX_LABEL = 40

function AssignForm({ tablet, onDone }: { tablet: Tablet; onDone: (next: Tablet) => void }) {
  const token = useStore((state) => state.session?.token ?? '')
  const map = useStore((state) => state.map)
  const toast = useStore((state) => state.toast)
  const [kind, setKind] = useState<TabletKind>(tablet.kind)
  const [label, setLabel] = useState('')
  const [speciality, setSpeciality] = useState('')
  const rooms = (map?.places ?? []).filter((place) => place.kind === 'room')
  const [place, setPlace] = useState(rooms.find((entry) => entry.id === tablet.place)?.id ?? rooms[0]?.id ?? '')
  const [busy, setBusy] = useState(false)

  const submit = async (): Promise<void> => {
    setBusy(true)
    try {
      const next = await backend.assignTablet(token, tablet.id, { kind, label: label.trim(), speciality: kind === 'staff' ? speciality.trim() || null : null, place: kind === 'bedside' ? place : null })
      onDone(next)
      toast('success', `${tablet.id} is now in use: ${next.label}.`)
    } catch (reason) {
      toast('danger', `Not assigned: ${errorMessage(reason)}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="tablet-form" onSubmit={(event) => { event.preventDefault(); void submit() }}>
      <div className="segmented" role="radiogroup" aria-label="Tablet for">
        <button type="button" role="radio" aria-checked={kind === 'staff'} className={kind === 'staff' ? 'is-on' : ''} onClick={() => setKind('staff')}><Stethoscope size={13} />A staff member</button>
        <button type="button" role="radio" aria-checked={kind === 'bedside'} className={kind === 'bedside' ? 'is-on' : ''} onClick={() => setKind('bedside')}><BedDouble size={13} />A bed</button>
      </div>
      <label className="field">{kind === 'staff' ? 'Pseudonym' : 'Bed label'}
        <input className="input" value={label} maxLength={MAX_LABEL} onChange={(event) => setLabel(event.target.value)} placeholder={kind === 'staff' ? 'Dr. A, Ward 2 nurse' : 'Bed 12'} required />
      </label>
      {kind === 'staff' ? (
        <label className="field">Speciality or role
          <input className="input" value={speciality} maxLength={MAX_LABEL} onChange={(event) => setSpeciality(event.target.value)} placeholder="Cardiology, Nursing" />
        </label>
      ) : (
        <label className="field">Room
          <select className="select" value={place} onChange={(event) => setPlace(event.target.value)}>{rooms.map((room) => <option key={room.id} value={room.id}>{room.label}</option>)}</select>
        </label>
      )}
      <p className="detail-note">{kind === 'staff' ? 'A pseudonym, never a full name.' : 'The bed, never the patient: no name, no diagnosis.'}</p>
      <button type="submit" className="button is-primary is-wide" disabled={busy || !label.trim() || !tablet.online} data-testid="tablet-assign"><Plus size={15} />Hand out this tablet</button>
    </form>
  )
}

export function TabletDetail({ now }: { now: number }) {
  const tablet = useStore((state) => state.tablets.find((entry) => entry.id === state.selectedTabletId))
  const managed = useStore((state) => state.tabletsManaged)
  const map = useStore((state) => state.map)
  const tasks = useStore((state) => state.tasks)
  const token = useStore((state) => state.session?.token ?? '')
  const upsertTablet = useStore((state) => state.upsertTablet)
  const toast = useStore((state) => state.toast)
  const [busy, setBusy] = useState(false)
  if (!tablet) return null

  const floor = tabletFloor(tablet, map)
  // A bed's requests are the open tasks going to its room: item and state only.
  const requests = tablet.kind === 'bedside' && tablet.assigned ? tasks.filter((task) => isOpenTask(task) && task.toPlace === tablet.place) : []

  const free = async (): Promise<void> => {
    const sure = await askConfirm({ title: `Free ${tabletTitle(tablet)}?`, body: tablet.kind === 'staff' ? 'Whoever uses it is signed out at once. The tablet goes back to the shelf, free for someone else.' : 'The bed loses its tablet until one is handed out again. Patient alarms do not depend on it.', confirmLabel: 'Free the tablet', danger: true })
    if (!sure) return
    setBusy(true)
    try {
      upsertTablet(await backend.disconnectTablet(token, tablet.id))
      toast('success', `${tablet.id} is free.`)
    } catch (reason) {
      toast('danger', `Not freed: ${errorMessage(reason)}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel className="robot-detail" eyebrow={tablet.kind === 'bedside' ? 'Bedside tablet' : 'Staff tablet'} title={tabletTitle(tablet)} actions={<Chip tone={!tablet.online ? 'neutral' : tablet.assigned ? 'mint' : 'slate'}>{!tablet.online ? 'Offline' : tablet.assigned ? 'In use' : 'Free'}</Chip>}>
      <div className="detail-body" data-testid="tablet-detail">
        {!tablet.online && <p className="detail-stale"><Radio size={14} />Not connected{tablet.lastSeen ? ` since ${ago(tablet.lastSeen, now).replace(' ago', '')}` : ''}. Its place below is the last one known.</p>}

        {tablet.kind === 'bedside' && tablet.assigned && (
          <div className="detail-task">
            <span className="eyebrow">Open requests from this room</span>
            {requests.length ? requests.map((task) => <small key={task.id}>{taskTitle(task)} · {TASK_LABEL[task.state]}</small>) : <strong className="is-muted">None</strong>}
          </div>
        )}

        <dl className="detail-facts">
          <div><dt>Battery</dt><dd>{tablet.battery !== null ? <Battery value={tablet.battery} /> : <span className="is-muted">Not reported by the server</span>}</dd></div>
          {tablet.kind === 'staff' && tablet.assigned && <div><dt>Speciality</dt><dd>{tablet.speciality ?? <span className="is-muted">Not given</span>}</dd></div>}
          <div><dt>Where</dt><dd>{placeName(map, tablet.place)}{floor !== null ? ` · ${floorName(map, floor)}` : ''}{tablet.uncertainty ? <span className="is-muted"> · ± {tablet.uncertainty.toFixed(1)} m</span> : null}</dd></div>
          <div><dt>Device</dt><dd className="mono">{tablet.id}</dd></div>
          {tablet.lastSeen && <div><dt>Last heard</dt><dd>{ago(tablet.lastSeen, now)}</dd></div>}
        </dl>

        {!managed ? (
          <p className="detail-note">This server has no tablet registry yet: tablets are shown, but cannot be freed or handed out from here.</p>
        ) : tablet.assigned ? (
          <div className="detail-controls">
            <button type="button" className="button is-danger is-wide" disabled={busy} onClick={() => { void free() }} data-testid="tablet-free"><LogOut size={15} />Free this tablet</button>
          </div>
        ) : (
          <AssignForm tablet={tablet} onDone={upsertTablet} />
        )}
      </div>
    </Panel>
  )
}
