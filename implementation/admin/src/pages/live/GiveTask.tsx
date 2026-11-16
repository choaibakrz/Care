/**
 * Gives a task: go to a place, fetch an item, follow a staff tablet, or go charge.
 * With a robot: that robot gets it. Without one: the server's optimizer picks the best robot,
 * or says why no robot can do it.
 */
import { useState } from 'react'
import { Send } from 'lucide-react'
import { backend } from '../../lib/backend'
import { errorMessage } from '../../lib/format'
import { useStore } from '../../state/store'
import type { Robot, Task } from '../../types'
import { useCommand } from '../../ui/useCommand'
import '../live.css'

type Choice = 'go_to' | 'fetch' | 'follow' | 'charge'

const LABEL: Record<Choice, string> = { go_to: 'Go to', fetch: 'Fetch', follow: 'Follow', charge: 'Go charge' }
/** Without a chosen robot only the trips make sense: follow and charge name one robot. */
const AUTO_CHOICES: Choice[] = ['go_to', 'fetch']

type Outcome = { tone: 'ok' | 'error'; text: string } | null

/** What the server's answer means for the person who asked. */
function outcomeOf(task: Task, auto: boolean): Outcome {
  if (task.robotId) {
    return { tone: 'ok', text: auto ? `The optimizer chose ${task.robotId} for task ${task.id}.` : `Task ${task.id} given to ${task.robotId}.` }
  }
  if (task.state === 'failed' || task.state === 'cancelled' || task.reason) {
    return { tone: 'error', text: `No robot can do this task. ${task.reason ?? 'The server gave no reason.'}` }
  }
  return { tone: 'ok', text: `Task ${task.id} is waiting for a free robot.` }
}

export function GiveTask({ robot, disabled = false }: { robot?: Robot; disabled?: boolean }) {
  const token = useStore((state) => state.session?.token)
  const toast = useStore((state) => state.toast)
  const upsertTask = useStore((state) => state.upsertTask)
  // Select stable store values and filter here: a selector that builds a new array each call
  // makes React re-render forever ("Maximum update depth exceeded").
  const map = useStore((state) => state.map)
  const places = map?.places ?? []
  const items = useStore((state) => state.inventory)
  const allTablets = useStore((state) => state.tablets)
  const tablets = allTablets.filter((tablet) => tablet.kind === 'staff' && tablet.assigned && tablet.online)
  const { run } = useCommand()
  const auto = !robot
  const choices = auto ? AUTO_CHOICES : (Object.keys(LABEL) as Choice[])
  const [choice, setChoice] = useState<Choice>('go_to')
  const [place, setPlace] = useState('')
  const [itemId, setItemId] = useState('')
  const [tabletId, setTabletId] = useState('')
  const [sending, setSending] = useState(false)
  const [outcome, setOutcome] = useState<Outcome>(null)

  const placeOptions = <>{[<option key="" value="">Choose a place…</option>, ...places.map((entry) => <option key={entry.id} value={entry.id}>{entry.label}</option>)]}</>
  const item = items.find((entry) => entry.id === itemId)
  const ready = (choice === 'charge' && !auto) || (choice === 'go_to' && place !== '') || (choice === 'fetch' && Boolean(item) && place !== '') || (choice === 'follow' && tabletId !== '' && !auto)

  const submit = async (): Promise<void> => {
    if (!token) return
    setOutcome(null)
    if (choice === 'charge') { if (robot) await run(robot, 'dock'); return }
    setSending(true)
    try {
      const robotId = robot?.id
      const task = await backend.createTask(token, choice === 'go_to' ? { robotId, kind: 'go_to', toPlace: place }
        : choice === 'fetch' ? { robotId, kind: 'fetch', item: itemId, fromPlace: item?.place, toPlace: place }
          : { robotId, kind: 'follow', targetDevice: tabletId })
      upsertTask(task)
      const result = outcomeOf(task, auto)
      setOutcome(result)
      if (result) toast(result.tone === 'ok' ? 'success' : 'danger', result.text)
    } catch (reason) {
      const text = `The task was not created. ${errorMessage(reason)}`
      setOutcome({ tone: 'error', text })
      toast('danger', text)
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="give-task" data-testid={auto ? 'new-task' : 'give-task'}>
      <span className="eyebrow">{auto ? 'New task: the best robot is chosen for you' : 'Give a task'}</span>
      <div className="give-task-row">
        <select className="select" value={choice} onChange={(event) => { setChoice(event.target.value as Choice); setOutcome(null) }} aria-label="Kind of task" disabled={disabled}>
          {choices.map((entry) => <option key={entry} value={entry}>{LABEL[entry]}</option>)}
        </select>
        {choice === 'go_to' && <select className="select" value={place} onChange={(event) => { setPlace(event.target.value); setOutcome(null) }} aria-label="Place" disabled={disabled}>{placeOptions}</select>}
        {choice === 'fetch' && (
          <>
            <select className="select" value={itemId} onChange={(event) => { setItemId(event.target.value); setOutcome(null) }} aria-label="Item" disabled={disabled}>
              <option value="">Choose an item…</option>
              {items.map((entry) => <option key={entry.id} value={entry.id}>{entry.label}</option>)}
            </select>
            <select className="select" value={place} onChange={(event) => { setPlace(event.target.value); setOutcome(null) }} aria-label="Bring it to" disabled={disabled}>{placeOptions}</select>
          </>
        )}
        {choice === 'follow' && (
          <select className="select" value={tabletId} onChange={(event) => setTabletId(event.target.value)} aria-label="Staff tablet" disabled={disabled}>
            <option value="">{tablets.length ? 'Choose a staff tablet…' : 'No staff tablet online'}</option>
            {tablets.map((tablet) => <option key={tablet.id} value={tablet.id}>{tablet.label}</option>)}
          </select>
        )}
        <button type="button" className="button is-primary" disabled={disabled || sending || !ready} onClick={() => { void submit() }}>
          <Send size={15} />{choice === 'charge' ? 'Send to charge' : sending ? 'Sending…' : auto ? 'Find a robot' : 'Give task'}
        </button>
      </div>
      {outcome && <p className={`give-task-outcome is-${outcome.tone}`} role={outcome.tone === 'error' ? 'alert' : 'status'} data-testid="task-outcome">{outcome.text}</p>}
    </div>
  )
}
