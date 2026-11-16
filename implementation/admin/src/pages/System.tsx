/** Connections, the link to the jury screen, the documented backup stop, and the demo controls. */
import { lazy, Suspense } from 'react'
import { ExternalLink, OctagonAlert, PlugZap, Presentation } from 'lucide-react'
import { fallbackUrl } from '../estop/send'
import { BRAND } from '../lib/brand'
import { config } from '../lib/config'
import { useStore } from '../state/store'
import { Chip, Panel } from '../ui/kit'
import './pages.css'

const DemoControls = lazy(() => import('./system/DemoControls').then((module) => ({ default: module.DemoControls })))

export function System() {
  const connection = useStore((state) => state.connection)
  const session = useStore((state) => state.session)
  return (
    <div className="cards">
      <Panel title="Connections" eyebrow={`This panel talks only to ${BRAND.server}`}>
        <div className="card-pad">
          <dl className="kv">
            <div><dt>Mode</dt><dd>{config.useMock ? <Chip tone="amber">Demo clinic in the browser</Chip> : <Chip tone="mint">Real server</Chip>}</dd></div>
            <div><dt>Live stream</dt><dd><Chip tone={connection === 'live' ? 'mint' : connection === 'connecting' ? 'amber' : 'coral'}>{connection}</Chip></dd></div>
            <div><dt>{BRAND.server} (C3)</dt><dd><code>{config.apiUrl}</code></dd></div>
            <div><dt>WebSocket</dt><dd><code>{config.wsUrl}</code></dd></div>
            <div><dt>Signed in as</dt><dd>{session?.operator} · admin</dd></div>
          </dl>
          <p><PlugZap size={14} style={{ verticalAlign: -2 }} /> No Internet is needed. Fonts, icons and the 3D code are bundled. There is no analytics and no tracking.</p>
        </div>
      </Panel>

      <Panel title="Jury screen" eyebrow="Existing screen, not rebuilt">
        <div className="card-pad">
          <p>The jury screen of <code>b13_ecran</code> shows what the robot hears, understands and decides. It opens in a new tab.</p>
          <a className="button is-primary" href={config.juryUrl} target="_blank" rel="noopener noreferrer"><Presentation size={15} />Open the jury screen<ExternalLink size={13} /></a>
          <code>{config.juryUrl}</code>
        </div>
      </Panel>

      <Panel title="If the stop button fails" eyebrow="Backup, documented">
        <div className="card-pad">
          <p><OctagonAlert size={14} style={{ verticalAlign: -2, color: 'var(--coral)' }} /> <strong>First: the physical red button on the robot.</strong> It always wins.</p>
          <p>Second: the robot-side screen keeps a stop route open to everyone on the local network. It stops the robot plugged on that computer only. The panel offers it in the stop report when a stop is not confirmed.</p>
          <code>POST {fallbackUrl}</code>
          <p>A stopped robot starts again only when a person re-arms it on the robot side.</p>
        </div>
      </Panel>

      {config.useMock && <Suspense fallback={null}><DemoControls /></Suspense>}
    </div>
  )
}
