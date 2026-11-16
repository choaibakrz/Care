import type { CSSProperties } from 'react'
import { MicOff } from 'lucide-react'
import { MOOD_EMOJI, MOOD_LABEL, STATE_LABEL, displayMood, displayState, floorName } from '../../lib/format'
import { STATE_COLOR } from '../../scene/palette'
import { useStore } from '../../state/store'
import { Battery, Panel, Segmented } from '../../ui/kit'
import { TabletList } from './TabletList'

export function FleetList({ now }: { now: number }) {
  const robots = useStore((state) => state.robots)
  const map = useStore((state) => state.map)
  const selectedRobotId = useStore((state) => state.selectedRobotId)
  const selectRobot = useStore((state) => state.selectRobot)
  const tab = useStore((state) => state.fleetTab)
  const setTab = useStore((state) => state.setFleetTab)
  const tablets = useStore((state) => state.tablets)
  const inUse = tablets.filter((tablet) => tablet.assigned && tablet.online).length
  const free = tablets.filter((tablet) => !tablet.assigned && tablet.online).length
  const loaded = useStore((state) => state.loaded)
  const switcher = <Segmented label="Show" value={tab} options={[{ value: 'robots', label: 'Robots' }, { value: 'tablets', label: <span data-testid="fleet-tab-tablets">Tablets</span> }]} onChange={setTab} />
  if (tab === 'tablets') {
    return (
      <Panel title="Tablets" eyebrow={`${inUse} in use · ${free} free`} className="fleet" actions={switcher}>
        <TabletList />
      </Panel>
    )
  }
  return (
    <Panel title="Fleet" eyebrow={loaded || robots.length ? `${robots.length} robots` : 'Loading'} className="fleet" actions={switcher}>
      {!loaded && !robots.length && <ul className="fleet-list" aria-busy="true">{[0, 1, 2, 3].map((index) => <li key={index}><span className="fleet-row is-loading"><i className="skeleton is-badge" /><span className="fleet-main"><i className="skeleton is-line" /><i className="skeleton is-line is-short" /></span></span></li>)}</ul>}
      <ul className="fleet-list">
        {robots.map((robot) => {
          const state = displayState(robot, now)
          const mood = displayMood(robot, now)
          return (
            <li key={robot.id}>
              <button type="button" className={`fleet-row ${robot.id === selectedRobotId ? 'is-selected' : ''} ${state === 'offline' ? 'is-offline' : ''}`} style={{ '--state': STATE_COLOR[state] } as CSSProperties} onClick={() => selectRobot(robot.id)} data-testid={`fleet-${robot.id}`}>
                <span className="fleet-id mono">{robot.id}</span>
                <span className="fleet-main">
                  <strong>{STATE_LABEL[state]}</strong>
                  <small>{robot.holding ? `Carries ${robot.holding.toLowerCase()}` : `${robot.role} · ${floorName(map, robot.position.floor)}`}</small>
                </span>
                <span className="fleet-flags">
                  <span className="fleet-mood" role="img" aria-label={MOOD_LABEL[mood]} title={MOOD_LABEL[mood]}>{MOOD_EMOJI[mood]}</span>
                  {!robot.micOpen && state !== 'offline' && <MicOff size={13} className="fleet-mic" aria-label="Microphone closed" />}
                </span>
                <Battery value={robot.battery} compact />
              </button>
            </li>
          )
        })}
      </ul>
    </Panel>
  )
}
