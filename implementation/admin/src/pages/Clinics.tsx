/** Stored clinic plans: list, activate, delete, export, import, copy. The building itself is edited on the Building page. */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Copy, Download, Power, Trash2, Upload } from 'lucide-react'
import { activateClinic, ApiError, createClinic, deleteClinic, getBasePlan, getClinic, getOverlay, listClinics, saveOverlay } from '../lib/http'
import { config } from '../lib/config'
import { toOverlay, toPlan } from '../lib/adapt'
import { errorMessage } from '../lib/format'
import { useStore } from '../state/store'
import type { ClinicSummary } from '../types'
import { askConfirm } from '../ui/confirm'
import { Chip, Empty, Panel } from '../ui/kit'
import './pages.css'
import './building/building.css'

export function Problems({ error }: { error: ApiError | null }) {
  if (!error) return null
  return (
    <div className="plan-error" role="alert">
      <strong>{error.message}</strong>
      {error.details.length > 0 && <ul>{error.details.map((detail, index) => <li key={index}><code>{detail.path}</code> {detail.problem}</li>)}</ul>}
    </div>
  )
}

export function Clinics() {
  const token = useStore((state) => state.session?.token) ?? ''
  const toast = useStore((state) => state.toast)
  const [clinics, setClinics] = useState<ClinicSummary[] | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [busy, setBusy] = useState(false)
  const file = useRef<HTMLInputElement>(null)
  const overlayFile = useRef<HTMLInputElement>(null)
  const overlayTarget = useRef('')

  const reload = useCallback(async () => {
    try { setClinics(await listClinics(token)) } catch (reason) { setError(reason instanceof ApiError ? reason : new ApiError(errorMessage(reason), 0, 'error')) }
  }, [token])
  useEffect(() => { if (!config.useMock) void reload() }, [reload])

  if (config.useMock) return <Panel title="Clinic plans"><Empty title="Clinic plans need the server">The demo clinic runs in the browser and has no stored plans. Set VITE_USE_MOCK=false.</Empty></Panel>

  const run = async (action: () => Promise<unknown>, done: string): Promise<void> => {
    setBusy(true); setError(null)
    try { await action(); toast('success', done) } catch (reason) { setError(reason instanceof ApiError ? reason : new ApiError(errorMessage(reason), 0, 'error')) }
    setBusy(false)
    await reload()
  }

  const download = async (name: string, read: () => Promise<unknown>): Promise<void> => {
    try {
      const link = document.createElement('a')
      link.href = URL.createObjectURL(new Blob([JSON.stringify(await read(), null, 2)], { type: 'application/json' }))
      link.download = name
      link.click()
      URL.revokeObjectURL(link.href)
    } catch (reason) { setError(reason instanceof ApiError ? reason : new ApiError(errorMessage(reason), 0, 'error')) }
  }
  const exportPlan = (clinic: ClinicSummary): Promise<void> => download(`${clinic.id}.json`, async () => (await getClinic(token, clinic.id)).plan)
  const exportBase = (clinic: ClinicSummary): Promise<void> => download(`${clinic.id}.base.json`, async () => (await getBasePlan(token, clinic.id)).plan)
  const exportOverlay = (clinic: ClinicSummary): Promise<void> => download(`${clinic.id}.overlay.json`, async () => (await getOverlay(token, clinic.id)).overlay)

  const importOverlay = async (picked: File | undefined): Promise<void> => {
    if (!picked) return
    let overlay
    try { overlay = toOverlay(JSON.parse(await picked.text())) } catch { overlay = null }
    if (!overlay) { setError(new ApiError('This file is not a set of modifications (JSON with upsert and remove).', 0, 'bad_file')); return }
    const id = overlayTarget.current
    await run(async () => { await saveOverlay(token, id, overlay, (await getOverlay(token, id)).version) }, `Modifications imported into “${id}”.`)
  }

  const importFile = async (picked: File | undefined): Promise<void> => {
    if (!picked) return
    let plan
    try { plan = toPlan(JSON.parse(await picked.text())) } catch { plan = null }
    if (!plan) { setError(new ApiError('This file is not a clinic plan (JSON with a name, floors, rooms, walls, places).', 0, 'bad_file')); return }
    await run(() => createClinic(token, plan), `Imported “${plan.name}”.`)
  }

  const copyActive = async (): Promise<void> => {
    const active = clinics?.find((clinic) => clinic.active)
    if (!active) return
    const name = window.prompt('Name of the new clinic', `${active.name} copy`)?.trim()
    if (!name) return
    await run(async () => { const { plan } = await getClinic(token, active.id); await createClinic(token, { ...plan, name }) }, `Created “${name}”.`)
  }

  return (
    <div className="stack">
      <Problems error={error} />
      <Panel title="Clinic plans" actions={<>
        <button type="button" className="button" disabled={busy || !clinics?.some((clinic) => clinic.active)} onClick={() => void copyActive()}><Copy size={14} /> New from the active one</button>
        <button type="button" className="button" disabled={busy} onClick={() => file.current?.click()}><Upload size={14} /> Import</button>
        <input ref={overlayFile} type="file" accept="application/json,.json" hidden data-testid="import-overlay-file" onChange={(event) => { void importOverlay(event.target.files?.[0]); event.target.value = '' }} />
        <input ref={file} type="file" accept="application/json,.json" hidden data-testid="import-file" onChange={(event) => { void importFile(event.target.files?.[0]); event.target.value = '' }} />
      </>}>
        {!clinics ? <Empty title="Loading…" /> : (
          <table className="table">
            <thead><tr><th>Name</th><th>Id</th><th>Version</th><th>Updated</th><th /></tr></thead>
            <tbody>
              {clinics.map((clinic) => (
                <tr key={clinic.id}>
                  <td><strong>{clinic.name}</strong> {clinic.active && <Chip tone="mint">Active</Chip>}</td>
                  <td><code>{clinic.id}</code></td>
                  <td>{clinic.version}</td>
                  <td>{clinic.updatedAt.slice(0, 16).replace('T', ' ')}</td>
                  <td className="row-actions">
                    {!clinic.active && <button type="button" className="button" disabled={busy} onClick={() => void run(() => activateClinic(token, clinic.id), `“${clinic.name}” is now the active clinic.`)}><Power size={14} /> Activate</button>}
                    <button type="button" className="button" disabled={busy} onClick={() => void exportPlan(clinic)}><Download size={14} /> Export</button>
                    <button type="button" className="button" disabled={busy} onClick={() => void exportBase(clinic)}><Download size={14} /> Export base</button>
                    <button type="button" className="button" disabled={busy} onClick={() => void exportOverlay(clinic)}><Download size={14} /> Export modifications</button>
                    <button type="button" className="button" disabled={busy} onClick={() => { overlayTarget.current = clinic.id; overlayFile.current?.click() }}><Upload size={14} /> Import modifications</button>
                    {!clinic.active && <button type="button" className="button is-danger" disabled={busy} onClick={async () => { if (await askConfirm({ title: `Delete “${clinic.name}”?`, body: 'The stored plan is removed. This cannot be undone.', confirmLabel: 'Delete', danger: true })) void run(() => deleteClinic(token, clinic.id), 'Deleted.') }}><Trash2 size={14} /> Delete</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  )
}
