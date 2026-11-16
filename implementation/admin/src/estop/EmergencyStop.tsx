/**
 * The emergency stop button and its result panel.
 *
 * It lives in its own React root, with its own styles and its own network code. A crash in the
 * 3D map, in the store or in any page leaves this button on screen and working.
 */
import { useSyncExternalStore } from 'react'
import { createRoot } from 'react-dom/client'
import { config } from '../lib/config'
import { dismissStops, getSnapshot, isResolving, requestFallback, requestRearm, requestStop, subscribe } from './bridge'
import type { RobotStop, StopPhase } from './bridge'
import { ModeSwitch } from './ModeSwitch'
import { fallbackUrl } from './send'
import './estop.css'

const PHASE_LABEL: Record<StopPhase, string> = {
  sending: 'Sending…',
  sent: 'Sent',
  confirmed: 'Confirmed stopped',
  unconfirmed: 'Not confirmed',
  failed: 'FAILED',
  rearmed: 'Re-armed',
  rearm_refused: 'Not re-armed',
}

function StopRow({ stop }: { stop: RobotStop }) {
  return (
    <li className={`estop-row estop-${stop.phase}`}>
      <strong>{stop.robotId}</strong>
      <span className="estop-phase">{PHASE_LABEL[stop.phase]}</span>
      <small>{stop.detail}</small>
    </li>
  )
}

function EmergencyStop() {
  const state = useSyncExternalStore(subscribe, getSnapshot)
  if (!state.token) return null

  const open = state.stops.length > 0 || state.problem !== null
  const failed = (state.problem !== null && !state.looking) || state.stops.some((stop) => stop.phase === 'failed' || stop.phase === 'unconfirmed')
  const pending = isResolving(state)
  const allConfirmed = open && !failed && !pending
  const canRearm = !pending && state.stops.some((stop) => stop.phase === 'confirmed' || stop.phase === 'unconfirmed' || stop.phase === 'rearm_refused')
  const rearm = (): void => {
    if (window.confirm('The robots will be able to move again. Check that the area around them is safe.')) void requestRearm()
  }

  return (
    <div className="estop">
      <ModeSwitch />
      <div className="estop-stop">
      <button className="estop-button" type="button" onClick={() => { void requestStop() }} data-testid="estop-all">
        <span className="estop-icon" aria-hidden="true" />
        <span className="estop-text">
          <strong>Emergency stop</strong>
          <small>All robots, at once</small>
        </span>
      </button>

      {open && (
        <section className={`estop-panel ${failed ? 'estop-panel-failed' : ''}`} role="alert" aria-live="assertive" data-testid="estop-panel">
          <header>
            <h2>{failed ? 'Stop not confirmed' : allConfirmed ? 'Robots stopped' : 'Stopping robots'}</h2>
            <button type="button" className="estop-close" onClick={dismissStops} disabled={pending} aria-label="Close the stop report" title={pending ? "Wait for the robots to answer" : "Close"}>×</button>
          </header>
          {config.useMock && <p className="estop-demo">Demo clinic: these are simulated robots. No real robot is stopped.</p>}
          {state.problem && <p className={state.looking ? 'estop-note' : 'estop-problem'}>{state.problem}</p>}
          <ul>{state.stops.map((stop) => <StopRow key={stop.robotId} stop={stop} />)}</ul>
          {failed && (
            <div className="estop-physical">
              <strong>Use the physical red button on the robot now.</strong>
              <p>Backup, for the robot plugged on the robot-side screen only:</p>
              <code>POST {fallbackUrl}</code>
              <button type="button" onClick={() => { void requestFallback() }} disabled={state.fallback === 'sending'}>
                {state.fallback === 'sending' ? 'Sending backup…' : 'Send the backup stop'}
              </button>
              {state.fallbackDetail && <p className={`estop-fallback-${state.fallback}`}>{state.fallbackDetail}</p>}
            </div>
          )}
          {canRearm && <button type="button" onClick={rearm} data-testid="rearm-all">Re-arm all stopped robots</button>}
          {allConfirmed && <p className="estop-note">A stopped robot moves again only after an admin re-arms it, or a person releases its red button.</p>}
          <p className="estop-note">The panel asks. The robot decides and reports.</p>
        </section>
      )}
      </div>
    </div>
  )
}

/** Mounts the button in its own root. Called before the rest of the app starts. */
export function mountEmergencyStop(container: HTMLElement | null): void {
  if (!container) return
  createRoot(container).render(<EmergencyStop />)
}
