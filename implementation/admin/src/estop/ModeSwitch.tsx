import { useSyncExternalStore } from 'react'
import { askExit, cancelExit, confirmExit, enterEmergency, getModeSnapshot, subscribeMode } from './mode'

/** Emergency mode: one click on, two clicks off. Shown next to the stop, in the same independent root. */
export function ModeSwitch() {
  const state = useSyncExternalStore(subscribeMode, getModeSnapshot)
  const on = state.mode?.mode === 'emergency'
  const switching = state.action === 'switching'
  const unknown = state.mode === null
  const title = !state.supported
    ? 'This server has no emergency mode yet.'
    : on ? 'Emergency mode is on. Click to go back to normal operation.' : 'Only emergency actions are accepted, robots go to their docks. Patient alarms are not affected.'

  return (
    <div className="mode">
      <button
        type="button"
        className={`mode-button ${on ? 'is-on' : ''}`}
        onClick={() => { if (on) askExit(); else void enterEmergency() }}
        disabled={switching || !state.supported || unknown}
        aria-pressed={on}
        title={title}
        data-testid="mode-switch"
      >
        <span className="mode-light" aria-hidden="true" />
        <span className="estop-text">
          <strong>{switching ? 'Switching…' : 'Emergency mode'}</strong>
          <small>{!state.supported ? 'Not on this server' : unknown ? 'Checking…' : on ? 'ON · click to leave' : 'Off · click to start'}</small>
        </span>
      </button>
      {state.confirmingExit && (
        <section className="mode-confirm" role="alertdialog" aria-label="Leave emergency mode" data-testid="mode-confirm">
          <p><strong>Leave emergency mode?</strong> The server accepts every request again and the robots resume their work.</p>
          <div>
            <button type="button" onClick={() => { void confirmExit() }} data-testid="mode-exit">Back to normal</button>
            <button type="button" onClick={cancelExit}>Stay in emergency</button>
          </div>
        </section>
      )}
      {state.error && <p className="mode-error" role="alert">{state.error}</p>}
    </div>
  )
}
