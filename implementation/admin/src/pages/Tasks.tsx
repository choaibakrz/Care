/** Every task, newest first. Filters, and the full history of the one that is open. */
import { useMemo, useState } from 'react'
import { ClipboardList, Search, XCircle } from 'lucide-react'
import { backend } from '../lib/backend'
import { TASK_LABEL, clockTime, dayTime, errorMessage, isOpenTask, placeName, shortTime, taskRoute, taskTitle } from '../lib/format'
import { useStore } from '../state/store'
import type { Task, TaskState } from '../types'
import { askConfirm } from '../ui/confirm'
import { Chip, Empty, Panel } from '../ui/kit'
import { GiveTask } from './live/GiveTask'
import './pages.css'

const TONE: Record<TaskState, 'amber' | 'mint' | 'coral' | 'slate' | 'neutral' | 'blue'> = {
  requested: 'neutral', assigned: 'blue', en_route: 'amber', delivered: 'mint', failed: 'coral', resumed: 'slate', cancelled: 'neutral',
}

type Filter = 'open' | 'all' | TaskState

function TaskHistory({ task }: { task: Task }) {
  const map = useStore((state) => state.map)
  const token = useStore((state) => state.session?.token)
  const toast = useStore((state) => state.toast)
  const upsertTask = useStore((state) => state.upsertTask)
  const [busy, setBusy] = useState(false)

  const cancel = async (): Promise<void> => {
    if (!token) return
    const robotNote = task.robotId ? ` ${task.robotId} stops this task${task.state === 'en_route' ? ' and takes back what it carries' : ''}.` : ''
    if (!await askConfirm({ title: `Cancel ${task.id}?`, body: `${taskTitle(task)}, ${taskRoute(task, map)}.${robotNote}`, confirmLabel: 'Cancel the task', danger: true })) return
    setBusy(true)
    try {
      upsertTask(await backend.cancelTask(token, task.id))
      toast('success', `${task.id} cancelled.`)
    } catch (reason) {
      toast('danger', `${task.id} not cancelled: ${errorMessage(reason)}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Panel className="task-detail" eyebrow={`Task ${task.id}`} title={taskTitle(task)} actions={<Chip tone={TONE[task.state]}>{TASK_LABEL[task.state]}</Chip>}>
      <div className="detail-pad">
        <div className="route-card">
          <div><span className="eyebrow">From</span><strong>{task.fromPlace ? placeName(map, task.fromPlace) : '—'}</strong></div>
          <i aria-hidden="true" />
          <div><span className="eyebrow">To</span><strong>{task.kind === 'restock_round' ? 'Every shelf' : placeName(map, task.toPlace)}</strong></div>
        </div>
        <dl className="facts">
          <div><dt>Asked by</dt><dd>{task.requestedBy}</dd></div>
          <div><dt>Robot</dt><dd className="mono">{task.robotId ?? 'Not assigned yet'}</dd></div>
          <div><dt>Created</dt><dd className="mono">{dayTime(task.createdAt)}</dd></div>
          {task.reason && <div><dt>Reason</dt><dd className="is-coral">{task.reason}</dd></div>}
        </dl>
        <p className="eyebrow">History</p>
        <ol className="timeline">
          {[...task.history].reverse().map((entry, index) => (
            <li key={`${entry.at}-${index}`}><i /><div><strong>{entry.label}</strong><small><span className="mono">{clockTime(entry.at)}</span> · {entry.actor}</small></div></li>
          ))}
        </ol>
        {/* The server cancels a task only before the robot sets off (requested or assigned). */}
        {isOpenTask(task) && (task.state === 'requested' || task.state === 'assigned') && <button type="button" className="button is-danger is-wide" disabled={busy} onClick={() => { void cancel() }}><XCircle size={15} />Cancel this task</button>}
        {isOpenTask(task) && task.state !== 'requested' && task.state !== 'assigned' && <p className="detail-note" role="note">{task.robotId ?? 'The robot'} is already on the way, so this task can no longer be cancelled. To stop it, pause the robot or send it to its dock on the live map.</p>}
        <p className="detail-note">Only an item and a place are kept. No patient data.</p>
      </div>
    </Panel>
  )
}

export function Tasks() {
  const tasks = useStore((state) => state.tasks)
  const robots = useStore((state) => state.robots)
  const map = useStore((state) => state.map)
  const [filter, setFilter] = useState<Filter>('all')
  const [robot, setRobot] = useState('all')
  const [query, setQuery] = useState('')
  const [openId, setOpenId] = useState<string | null>(null)

  const shown = useMemo(() => tasks
    .filter((task) => filter === 'all' || (filter === 'open' ? isOpenTask(task) : task.state === filter))
    .filter((task) => robot === 'all' || task.robotId === robot)
    .filter((task) => !query.trim() || `${task.id} ${taskTitle(task)} ${taskRoute(task, map)} ${task.requestedBy}`.toLowerCase().includes(query.trim().toLowerCase())),
  [tasks, filter, robot, query, map])
  const open = tasks.find((task) => task.id === openId) ?? shown[0]
  const counts = (state: Filter): number => state === 'all' ? tasks.length : state === 'open' ? tasks.filter(isOpenTask).length : tasks.filter((task) => task.state === state).length
  const filters: Filter[] = ['all', 'open', 'delivered', 'failed', 'resumed', 'cancelled']

  return (
    <div className="split">
      <div className="tasks-main">
      <Panel flush className="new-task-panel">
        <GiveTask />
      </Panel>
      <Panel flush className="table-panel">
        <div className="filters">
          <div className="filter-tabs" role="tablist">
            {filters.map((value) => (
              <button key={value} type="button" role="tab" aria-selected={filter === value} className={filter === value ? 'is-on' : ''} onClick={() => setFilter(value)}>
                {value === 'all' ? 'All' : value === 'open' ? 'Open' : TASK_LABEL[value]}<b className="mono">{counts(value)}</b>
              </button>
            ))}
          </div>
          <div className="filter-tools">
            <label className="search"><Search size={15} /><input placeholder="Item, place, task…" value={query} onChange={(event) => setQuery(event.target.value)} /></label>
            <select className="select is-compact" value={robot} onChange={(event) => setRobot(event.target.value)} aria-label="Robot">
              <option value="all">All robots</option>
              {robots.map((entry) => <option key={entry.id} value={entry.id}>{entry.id}</option>)}
            </select>
          </div>
        </div>
        {shown.length ? (
          <table className="table">
            <thead><tr><th>Task</th><th>What and where</th><th>State</th><th>Robot</th><th>Asked by</th><th>Updated</th></tr></thead>
            <tbody>
              {shown.map((task) => (
                <tr key={task.id} className={task.id === open?.id ? 'is-selected' : ''} onClick={() => setOpenId(task.id)} tabIndex={0} onKeyDown={(event) => { if (event.key === 'Enter') setOpenId(task.id) }}>
                  <td className="mono">{task.id}</td>
                  <td><strong>{taskTitle(task)}</strong><small>{taskRoute(task, map)}</small></td>
                  <td><Chip tone={TONE[task.state]}>{TASK_LABEL[task.state]}</Chip></td>
                  <td className="mono">{task.robotId ?? '—'}</td>
                  <td>{task.requestedBy}</td>
                  <td className="mono muted">{shortTime(task.updatedAt)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <Empty icon={<ClipboardList size={20} />} title="No task matches">Change the filters, or wait for the next request.</Empty>}
      </Panel>
      </div>
      {open ? <TaskHistory task={open} /> : <Panel><Empty title="No task selected" /></Panel>}
    </div>
  )
}
