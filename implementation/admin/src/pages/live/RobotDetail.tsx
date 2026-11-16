/** The selected robot: what it does, what it carries, whether it listens, and the controls. */
import { Anchor, Mic, MicOff, Octagon, Package, Pause, Play, Radio, RotateCcw } from 'lucide-react'
import { requestStop } from '../../estop/bridge'
import { MOOD_EMOJI, MOOD_LABEL, ago, clockTime, displayMood, displayState, floorName, placeName, taskRoute, taskTitle, TASK_LABEL } from '../../lib/format'
import { useStore } from '../../state/store'
import { Battery, Chip, Panel, StateBadge } from '../../ui/kit'
import { useCommand } from '../../ui/useCommand'
import { GiveTask } from './GiveTask'

export function RobotDetail({ now }: { now: number }) {
  const robot = useStore((state) => state.robots.find((entry) => entry.id === state.selectedRobotId))
  const task = useStore((state) => state.tasks.find((entry) => entry.id === robot?.taskId))
  const map = useStore((state) => state.map)
  const { run, pending } = useCommand()
  if (!robot) return null

  const state = displayState(robot, now)
  const offline = state === 'offline'
  const canPause = robot.state === 'busy'
  const canResume = robot.state === 'paused'
  const locked = robot.state === 'estop' || robot.state === 'fault'
  const busy = (name: string): boolean => pending === `${robot.id}:${name}`

  return (
    <Panel className="robot-detail" eyebrow={robot.simulated ? 'Simulated robot' : 'Robot on the plug'} title={robot.name} actions={<StateBadge state={state} />}>
      <div className="detail-body" data-testid="robot-detail">
        {offline && <p className="detail-stale"><Radio size={14} />Not heard from for {ago(robot.lastSeen, now).replace(' ago', '')}. The position below is the last one known, not a live one.</p>}

        <div className="detail-task">
          {task ? (
            <>
              <span className="eyebrow">Current task · {task.id}</span>
              <strong>{taskTitle(task)}</strong>
              <small>{taskRoute(task, map)}</small>
              <Chip tone={task.state === 'en_route' ? 'amber' : 'slate'}>{TASK_LABEL[task.state]}</Chip>
            </>
          ) : (
            <>
              <span className="eyebrow">Current task</span>
              <strong className="is-muted">None</strong>
              <small>{robot.state === 'estop' ? 'Stopped by an emergency stop. Re-arm it below once the area around it is safe.' : robot.state === 'fault' ? 'A person must check the robot.' : 'Waiting for a request or charging.'}</small>
            </>
          )}
        </div>

        <dl className="detail-facts">
          <div><dt>Mood</dt><dd><span className="fleet-mood" role="img" aria-hidden="true">{MOOD_EMOJI[displayMood(robot, now)]}</span>{MOOD_LABEL[displayMood(robot, now)]}{robot.inDeafZone ? ' · in a deaf zone' : ''}{robot.goingHome ? ' · going home' : ''}</dd></div>
          <div><dt>Battery</dt><dd><Battery value={robot.battery} /></dd></div>
          <div><dt>Carrying</dt><dd>{robot.holding ? <><Package size={14} />{robot.holding}</> : <span className="is-muted">Nothing</span>}</dd></div>
          <div><dt>Microphone</dt><dd className={robot.micOpen ? 'is-mint' : 'is-blue'}>{robot.micOpen ? <><Mic size={14} />Open, listening</> : <><MicOff size={14} />Closed</>}</dd></div>
          <div><dt>Where</dt><dd>{floorName(map, robot.position.floor)} · <span className="mono">{robot.position.x.toFixed(1)}, {robot.position.y.toFixed(1)} m</span></dd></div>
          <div><dt>Last update</dt><dd className={offline ? 'is-coral' : ''}><span className="mono">{clockTime(robot.lastSeen)}</span> · {ago(robot.lastSeen, now)}</dd></div>
          {task?.fromPlace && <div><dt>Pick-up</dt><dd>{placeName(map, task.fromPlace)}</dd></div>}
        </dl>

        <GiveTask robot={robot} disabled={offline || locked} />

        <div className="detail-controls">
          {robot.state === 'estop' && (
            <button type="button" className="button is-primary is-wide" disabled={offline || busy('resume')} onClick={() => { void run(robot, 'resume') }} data-testid="rearm-one"><RotateCcw size={15} />Re-arm robot</button>
          )}
          <button type="button" className="button" disabled={offline || locked || !(canPause || canResume) || busy('pause') || busy('resume')} onClick={() => { void run(robot, canResume ? 'resume' : 'pause') }}>
            {canResume ? <><Play size={15} />Resume</> : <><Pause size={15} />Pause</>}
          </button>
          <button type="button" className="button" disabled={offline || locked || busy('dock')} onClick={() => { void run(robot, 'dock') }}><Anchor size={15} />Send to dock</button>
          <button type="button" className="button is-danger is-wide" onClick={() => { void requestStop([robot.id]) }} data-testid="estop-one"><Octagon size={15} />Stop {robot.id} now</button>
        </div>
        <p className="detail-note">These buttons send a request. {robot.id} decides, and says why when it refuses.</p>
      </div>
    </Panel>
  )
}
