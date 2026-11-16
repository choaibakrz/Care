import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { BedDouble, ClipboardPlus, Copy, KeyRound, RefreshCw, ShieldCheck, TabletSmartphone, UserRoundPlus } from 'lucide-react'
import { backend } from '../lib/backend'
import { errorMessage } from '../lib/format'
import { useStore } from '../state/store'
import type { ClinicRoom } from '../types'
import { askConfirm } from '../ui/confirm'
import { Chip, Empty, Panel } from '../ui/kit'
import './pages.css'
import './patients.css'

function admittedAt(value: string): string {
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(timestamp) : '—'
}

function roomStatus(room: ClinicRoom): { label: string; tone: 'mint' | 'amber' | 'coral' | 'neutral' } {
  if (!room.patient) return { label: 'Ready for admission', tone: 'mint' }
  if (!room.device) return { label: 'Tablet not registered', tone: 'amber' }
  if (!room.device.paired) return { label: 'Waiting for tablet pairing', tone: 'amber' }
  return { label: room.device.online ? 'Patient tablet online' : 'Patient tablet offline', tone: room.device.online ? 'mint' : 'coral' }
}

export function Patients() {
  const token = useStore((state) => state.session?.token)
  const toast = useStore((state) => state.toast)
  const [rooms, setRooms] = useState<ClinicRoom[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [pairing, setPairing] = useState<{ roomId: string; code: string } | null>(null)
  const [form, setForm] = useState({ firstName: '', medicalRecordRef: '', roomId: '' })

  const refresh = useCallback(async (): Promise<void> => {
    if (!token) return
    setLoading(true)
    try {
      const next = await backend.getRooms(token)
      setRooms(next)
      setForm((current) => current.roomId && next.some((room) => room.id === current.roomId && !room.patient) ? current : { ...current, roomId: '' })
    } catch (reason) {
      toast('danger', `Room data could not be loaded: ${errorMessage(reason)}`)
    } finally {
      setLoading(false)
    }
  }, [token, toast])

  useEffect(() => { void refresh() }, [refresh])

  const freeRooms = useMemo(() => rooms.filter((room) => !room.patient), [rooms])

  const admit = async (event: FormEvent<HTMLFormElement>): Promise<void> => {
    event.preventDefault()
    if (!token) return
    const roomId = form.roomId.trim()
    if (!roomId) {
      toast('warning', 'Select a room before admitting the patient.')
      return
    }
    setBusy('admit')
    setPairing(null)
    try {
      await backend.admitPatient(token, { ...form, roomId })
      const selectedRoom = rooms.find((room) => room.id === roomId)
      toast('success', `${form.firstName.trim()} was admitted to ${selectedRoom?.label || roomId}.`)
      if (selectedRoom && !selectedRoom.device?.paired) {
        try {
          const device = await backend.createRoomDevice(token, { roomId, label: `Tablet ${selectedRoom.label}` })
          setPairing({ roomId, code: device.pairingCode })
          toast('success', `Pairing code generated for ${selectedRoom.label}. Use it on the patient tablet.`)
        } catch (reason) {
          toast('warning', `Patient admitted, but the tablet code could not be generated: ${errorMessage(reason)}`)
        }
      }
      setForm({ firstName: '', medicalRecordRef: '', roomId: '' })
      await refresh()
    } catch (reason) {
      toast('danger', `Patient not admitted: ${errorMessage(reason)}`)
    } finally {
      setBusy(null)
    }
  }

  const registerTablet = async (room: ClinicRoom): Promise<void> => {
    if (!token) return
    setBusy(`device:${room.id}`)
    try {
      const result = await backend.createRoomDevice(token, { roomId: room.id, label: `Tablet ${room.label}` })
      setPairing({ roomId: room.id, code: result.pairingCode })
      toast('success', `Pairing code generated for ${room.label}.`)
      await refresh()
    } catch (reason) {
      toast('danger', `Tablet not registered: ${errorMessage(reason)}`)
    } finally {
      setBusy(null)
    }
  }

  const discharge = async (room: ClinicRoom): Promise<void> => {
    if (!token || !room.patient) return
    const confirmed = await askConfirm({
      title: `Discharge ${room.patient.firstName}?`,
      body: `This closes the assignment in ${room.label}, revokes the tablet session, and makes the room ready for the next patient.`,
      confirmLabel: 'Discharge and reset',
      danger: true,
    })
    if (!confirmed) return
    setBusy(`discharge:${room.id}`)
    try {
      await backend.dischargeRoom(token, room.id)
      if (pairing?.roomId === room.id) setPairing(null)
      toast('success', `${room.label} is ready for the next patient.`)
      await refresh()
    } catch (reason) {
      toast('danger', `Room not reset: ${errorMessage(reason)}`)
    } finally {
      setBusy(null)
    }
  }

  const copyPairingCode = async (): Promise<void> => {
    if (!pairing) return
    try {
      await navigator.clipboard.writeText(pairing.code)
      toast('success', 'Pairing code copied. It is visible only to the admin console.')
    } catch {
      toast('warning', 'Copy was blocked. Read the code directly from this screen.')
    }
  }

  return (
    <div className="patient-console">
      <div className="summary-row patient-summary">
        <div className="stat"><span>Rooms</span><strong className="mono">{rooms.length}</strong><small>Registered in Care</small></div>
        <div className="stat"><span>Admitted patients</span><strong className="mono">{rooms.filter((room) => room.patient).length}</strong><small>One patient per room</small></div>
        <div className="stat"><span>Tablet links</span><strong className="mono">{rooms.filter((room) => room.device?.paired).length}</strong><small>Active room sessions</small></div>
        <div className={`stat ${rooms.some((room) => room.patient && !room.device?.paired) ? 'is-warn' : ''}`}><span>Needs pairing</span><strong className="mono">{rooms.filter((room) => room.patient && !room.device?.paired).length}</strong><small>Care team action</small></div>
      </div>

      <div className="patient-control-grid">
        <Panel title="Admit a patient" eyebrow="Admin only">
          <form className="card-pad patient-form" onSubmit={(event) => { void admit(event) }}>
            <p className="helper-copy"><ShieldCheck size={15} /> The medical record reference stays inside the admin console. The tablet receives only the assigned first name and room.</p>
            <label className="field">First name<input className="input" value={form.firstName} onChange={(event) => setForm({ ...form, firstName: event.target.value })} autoComplete="off" maxLength={40} required /></label>
            <label className="field">Medical record reference<input className="input mono" value={form.medicalRecordRef} onChange={(event) => setForm({ ...form, medicalRecordRef: event.target.value })} autoComplete="off" maxLength={64} required /></label>
            <label className="field">Room<select className="select" value={form.roomId} onChange={(event) => setForm({ ...form, roomId: event.target.value })} required><option value="" disabled>Select a room</option>{rooms.map((room) => <option key={room.id} value={room.id} disabled={Boolean(room.patient)}>{room.label} · {room.wing} · floor {room.floor}{room.patient ? ' · occupied' : ''}</option>)}</select></label>
            <button className="button is-primary" type="submit" disabled={busy === 'admit' || !form.roomId || !freeRooms.length}><UserRoundPlus size={15} />{busy === 'admit' ? 'Admitting…' : 'Admit patient'}</button>
            {!freeRooms.length && <p className="read-only"><Chip tone="amber">All occupied</Chip>Discharge a patient before assigning the next one.</p>}
          </form>
        </Panel>

        <Panel title="Tablet pairing" eyebrow="One-time setup">
          <div className="card-pad pairing-panel">
            {pairing ? (
              <div className="pairing-code-box" role="status">
                <div><span className="eyebrow">Code for {rooms.find((room) => room.id === pairing.roomId)?.label || pairing.roomId}</span><strong className="mono">{pairing.code}</strong><small>Give this code to the tablet in that room. It expires in 15 minutes and can be used once.</small></div>
                <button type="button" className="button is-primary" onClick={() => { void copyPairingCode() }}><Copy size={15} />Copy code</button>
              </div>
            ) : (
              <div className="pairing-empty"><KeyRound size={24} /><strong>Select a room below to create a pairing code.</strong><p>The code never appears in the patient app and is not stored in the browser.</p></div>
            )}
          </div>
        </Panel>
      </div>

      <Panel title="Rooms and patient tablets" eyebrow="Live room assignment" actions={<button type="button" className="button is-ghost" onClick={() => { void refresh() }} disabled={loading}><RefreshCw size={14} className={loading ? 'is-spinning' : ''} />Refresh</button>}>
        {loading && !rooms.length ? <div className="card-pad"><Empty icon={<BedDouble size={20} />} title="Loading room registry">Checking the secure room assignments…</Empty></div> : (
          <div className="room-grid">
            {rooms.map((room) => {
              const status = roomStatus(room)
              const isBusy = busy === `device:${room.id}` || busy === `discharge:${room.id}`
              return (
                <article className="room-card" key={room.id}>
                  <header className="room-card-head"><div><span className="eyebrow">Floor {room.floor} · {room.wing}</span><h3><BedDouble size={17} />{room.label}</h3></div><Chip tone={status.tone}>{status.label}</Chip></header>
                  {room.patient ? <div className="room-patient"><div className="room-person"><span className="room-avatar">{room.patient.firstName.slice(0, 1).toUpperCase()}</span><div><strong>{room.patient.firstName}</strong><small>Admitted {admittedAt(room.patient.admittedAt)}</small></div></div><dl className="room-facts"><div><dt>Medical record</dt><dd className="mono">{room.patient.medicalRecordRef}</dd></div><div><dt>Tablet</dt><dd>{room.device?.label || 'Not registered'}</dd></div></dl></div> : <div className="room-empty"><BedDouble size={20} /><span>No patient assigned. This room is ready.</span></div>}
                  <footer className="room-card-actions">
                    <button type="button" className="button is-primary" onClick={() => { void registerTablet(room) }} disabled={isBusy || !room.patient}><TabletSmartphone size={15} />{room.device?.paired ? 'Tablet paired' : room.device ? 'Show new pairing code' : 'Register tablet'}</button>
                    {room.patient && <button type="button" className="button is-danger" onClick={() => { void discharge(room) }} disabled={isBusy}><ClipboardPlus size={15} />{busy === `discharge:${room.id}` ? 'Resetting…' : 'Discharge and reset'}</button>}
                  </footer>
                </article>
              )
            })}
          </div>
        )}
      </Panel>
    </div>
  )
}
