/** Demo-only controls of the System page. Loaded only in demo mode: it pulls in the demo clinic. */
import { useState } from 'react'
import { FlaskConical } from 'lucide-react'
import { clearHeat } from '../../lib/heat'
import { demoControls } from '../../mock/server'
import { useStore } from '../../state/store'
import { Chip, Panel } from '../../ui/kit'

const OUTAGE_SECONDS = 15
const LINK_DROP_SECONDS = 20

export function DemoControls() {
  const robots = useStore((state) => state.robots)
  const toast = useStore((state) => state.toast)
  const loadAll = useStore((state) => state.loadAll)
  const [target, setTarget] = useState('')
  const robotId = target || robots[0]?.id || ''
  const stopped = robots.filter((robot) => robot.state === 'estop')

  const cutLine = (): void => {
    demoControls.setOutage(true)
    window.setTimeout(() => demoControls.setOutage(false), OUTAGE_SECONDS * 1000)
  }
  const reset = (): void => { clearHeat(); demoControls.reset(); void loadAll(); toast('info', 'Demo clinic reset.') }

  return (
    <Panel title="Demo controls" eyebrow="Only in demo mode" actions={<Chip tone="amber"><FlaskConical size={12} />Invented data</Chip>}>
      <div className="card-pad">
        <p>Use these to show the jury what the panel does when something goes wrong. None of them exists on the real server.</p>
        <div className="inline-actions">
          <button type="button" className="button" onClick={cutLine} data-testid="demo-outage">Cut the server line for {OUTAGE_SECONDS} s</button>
          <button type="button" className="button" onClick={reset}>Reset the demo clinic</button>
        </div>
        <label className="field">Robot
          <select className="select" value={robotId} onChange={(event) => setTarget(event.target.value)}>{robots.map((robot) => <option key={robot.id} value={robot.id}>{robot.name}</option>)}</select>
        </label>
        <div className="inline-actions">
          <button type="button" className="button" onClick={() => { demoControls.dropLink(robotId, LINK_DROP_SECONDS); toast('info', `${robotId} loses its Wi-Fi for ${LINK_DROP_SECONDS} s. It turns grey after 5 s.`) }} data-testid="demo-drop">Drop its Wi-Fi for {LINK_DROP_SECONDS} s</button>
          <button type="button" className="button" onClick={() => demoControls.injectFault(robotId)}>Block a wheel (fault)</button>
        </div>
        {stopped.length > 0 && (
          <div className="inline-actions">
            {stopped.map((robot) => <button key={robot.id} type="button" className="button is-primary" onClick={() => demoControls.releaseEstop(robot.id)} data-testid={`release-${robot.id}`}>Release the red button of {robot.id}</button>)}
          </div>
        )}
      </div>
    </Panel>
  )
}
