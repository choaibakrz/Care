/** The main screen: the 3D clinic, the fleet, the selected robot and the live activity. */
import { lazy, Suspense } from 'react'
import { Box, Flame, Grid2x2, Layers, Map as MapIcon, Rotate3d, Tablet as TabletIcon } from 'lucide-react'
import { backend } from '../lib/backend'
import { displayState, errorMessage, floorName, isOpenTask } from '../lib/format'
import { SEVERITY_COLOR, incidentRoom, worse } from '../lib/incidents'
import type { Incident } from '../types'
import { useStore } from '../state/store'
import { useHeat, useTaskRoute } from '../state/useMapData'
import { STATE_COLOR, TABLET_COLOR, ZONE_COLOR } from '../scene/palette'
import { CLINIC_DIMENSIONS, Q1_DIMENSIONS } from '../scene/scale'
import { Panel, Segmented, Ticker, Toggle } from '../ui/kit'
import { useNow } from '../ui/Shell'
import { ActivityFeed } from './live/ActivityFeed'
import { FleetList } from './live/FleetList'
import { RobotDetail } from './live/RobotDetail'
import { IncidentsPanel } from './live/IncidentsPanel'
import { TabletDetail } from './live/TabletDetail'
import { HomePlace } from './live/HomePlace'
import './live.css'

// The 3D code is the heaviest part: it loads on its own so the rest of the panel opens at once.
const ClinicScene = lazy(() => import('../scene/ClinicScene').then((module) => ({ default: module.ClinicScene })))

const ALL_FLOORS = -1

const KPI_LABELS = ['Robots working', 'Need attention', 'Open tasks', 'Delivered', 'Low stock']

/** Shapes in place of numbers while the first answers arrive: never a misleading 0. */
function KpisLoading() {
  return (
    <div className="kpis" aria-busy="true">
      {KPI_LABELS.map((label) => <div key={label} className="kpi"><span>{label}</span><strong><i className="skeleton is-number" /></strong><small><i className="skeleton is-line" /></small></div>)}
    </div>
  )
}

function Kpis({ now }: { now: number }) {
  const loaded = useStore((state) => state.loaded)
  const robots = useStore((state) => state.robots)
  const tasks = useStore((state) => state.tasks)
  const inventory = useStore((state) => state.inventory)
  const working = robots.filter((robot) => displayState(robot, now) === 'busy').length
  const alarms = robots.filter((robot) => ['fault', 'estop', 'offline'].includes(displayState(robot, now))).length
  const open = tasks.filter(isOpenTask).length
  const delivered = tasks.filter((task) => task.state === 'delivered' && task.kind === 'fetch').length
  const closed = tasks.filter((task) => ['delivered', 'failed', 'resumed'].includes(task.state) && task.kind === 'fetch').length
  const low = inventory.filter((item) => item.count <= item.lowAt).length
  if (!loaded && !robots.length) return <KpisLoading />
  return (
    <div className="kpis">
      <div className="kpi"><span>Robots working</span><strong className="mono"><Ticker value={working} />/{robots.length}</strong><small>{robots.length - working} idle, paused or charging</small></div>
      <div className={`kpi ${alarms ? 'is-alarm' : ''}`}><span>Need attention</span><strong className="mono"><Ticker value={alarms} /></strong><small>{alarms ? 'Fault, stop or no signal' : 'Nothing to check'}</small></div>
      <div className="kpi"><span>Open tasks</span><strong className="mono"><Ticker value={open} /></strong><small>Waiting or on the way</small></div>
      <div className="kpi"><span>Delivered</span><strong className="mono"><Ticker value={delivered} /></strong><small>{closed ? `${Math.round((delivered / closed) * 100)}% of closed tasks` : 'No closed task yet'}</small></div>
      <div className={`kpi ${low ? 'is-warn' : ''}`}><span>Low stock</span><strong className="mono"><Ticker value={low} /></strong><small>{low ? 'Below the threshold' : 'All above threshold'}</small></div>
    </div>
  )
}

function Legend() {
  const showZones = useStore((state) => state.showZones)
  const showHeat = useStore((state) => state.showHeat)
  const showTablets = useStore((state) => state.showTablets)
  const states = [['idle', 'Available'], ['busy', 'On a task'], ['paused', 'Paused'], ['fault', 'Fault'], ['estop', 'Stopped'], ['offline', 'No signal']] as const
  return (
    <div className="map-legend">
      {states.map(([state, label]) => <span key={state}><i style={{ background: STATE_COLOR[state] }} />{label}</span>)}
      {showZones && <><span><i className="is-zone" style={{ borderColor: ZONE_COLOR.deaf }} />Deaf zone</span><span><i className="is-zone is-dashed" style={{ borderColor: ZONE_COLOR.restricted }} />Restricted</span></>}
      {showHeat && <span><i className="is-heat" />Time spent</span>}
      {showTablets && <><span><i style={{ background: TABLET_COLOR.staff }} />Staff tablet</span><span><i style={{ background: TABLET_COLOR.bedside }} />Bedside tablet</span><span><i style={{ background: TABLET_COLOR.free }} />Free or offline</span></>}
      <span><i className="is-route" />Route (estimate)</span>
    </div>
  )
}

function MapToolbar() {
  const map = useStore((state) => state.map)
  const robots = useStore((state) => state.robots)
  const floor = useStore((state) => state.floor)
  const exploded = useStore((state) => state.exploded)
  const view = useStore((state) => state.view)
  const showZones = useStore((state) => state.showZones)
  const showHeat = useStore((state) => state.showHeat)
  const showTablets = useStore((state) => state.showTablets)
  const incidents = useStore((state) => state.incidents)
  const { setFloor, setExploded, setView, setShowZones, setShowHeat, setShowTablets } = useStore.getState()
  const floors = map ? [...map.floors].sort((a, b) => a.id - b.id) : []
  // A floor with an open incident says so, so an alarm upstairs is seen from the ground floor.
  const worstOn = (floorId: number): Incident | null => incidents
    .filter((incident) => (incident.floor ?? (map ? incidentRoom(map, incident)?.floor : null)) === floorId)
    .reduce<Incident | null>((top, incident) => (top ? worse(top, incident) : incident), null)
  const options = [
    ...floors.map((entry) => {
      const top = worstOn(entry.id)
      return { value: entry.id, title: top ? `Open incident on this floor: ${top.severity}` : undefined, label: <>{top && <i className={`floor-incident ${top.severity === 'critical' ? 'is-critical' : ''}`} style={{ background: SEVERITY_COLOR[top.severity] }} aria-label={`Open ${top.severity} incident`} data-testid={`floor-incident-${entry.id}`} />}{entry.label}<b className="mono floor-count">{robots.filter((robot) => robot.position.floor === entry.id).length}</b></> }
    }),
    { value: ALL_FLOORS, label: <><Layers size={14} />All floors</>, title: 'Exploded view: every floor, stacked' },
  ]
  return (
    <div className="map-toolbar">
      <Segmented label="Floor" value={exploded ? ALL_FLOORS : floor} options={options} onChange={(value) => { if (value === ALL_FLOORS) setExploded(true); else { setExploded(false); setFloor(value) } }} />
      <div className="map-toolbar-right">
        <Segmented label="Camera" value={view} options={[{ value: 'iso', label: <><Rotate3d size={14} />3D</> }, { value: 'top', label: <><Grid2x2 size={14} />Plan</> }]} onChange={setView} />
        <Toggle on={showZones} onChange={setShowZones} title="Show deaf and restricted zones"><MapIcon size={14} />Zones</Toggle>
        <Toggle on={showTablets} onChange={setShowTablets} title="Show staff and bedside tablets"><TabletIcon size={14} />Tablets</Toggle>
        <Toggle on={showHeat} onChange={setShowHeat} title="Where robots spent their time, counted by the server"><Flame size={14} />Heat</Toggle>
      </div>
    </div>
  )
}

function MapStage({ now }: { now: number }) {
  const store = useStore()
  const { map, robots, tasks, zones, floor, exploded, view, theme, selectedRobotId, showZones, showHeat, demoMode, selectRobot, session, tablets, showTablets, selectedTabletId, selectTablet, incidents, selectedIncidentId, selectIncident } = store
  const token = session?.token ?? null
  const selected = robots.find((robot) => robot.id === selectedRobotId)
  const selectedTask = tasks.find((task) => task.id === selected?.taskId && isOpenTask(task))
  const route = useTaskRoute(token, selected, selectedTask)
  const heatFloors = !map ? [] : exploded ? map.floors.map((entry) => entry.id) : [floor]
  const heat = useHeat(token, heatFloors, showHeat)
  const fleetHome = useStore((state) => state.fleetHome)
  const homePlace = map?.places.find((place) => place.id === fleetHome?.placeId)
  const home = homePlace ? { x: homePlace.x, y: homePlace.y, floor: homePlace.floor, label: homePlace.label || homePlace.id } : null
  // A simulated robot dropped after a drag: the server moves it, or says why not (it then glides back).
  const dropRobot = async (robotId: string, x: number, y: number): Promise<boolean> => {
    const robot = robots.find((entry) => entry.id === robotId)
    if (!token || !robot) return false
    try {
      useStore.getState().upsertRobot(await backend.teleportRobot(token, robotId, { x, y, floor: robot.position.floor }))
      return true
    } catch (reason) {
      useStore.getState().toast('warning', `${robotId} was not moved: ${errorMessage(reason)}`)
      return false
    }
  }
  if (!map) return <div className="map-loading"><Box size={22} />Loading the map…</div>
  const label = exploded ? 'All floors' : floorName(map, floor)
  return (
    <div className="map-stage">
      <Suspense fallback={<div className="map-loading"><Box size={22} />Building the 3D clinic…</div>}>
        <ClinicScene map={map} robots={robots} tasks={tasks} zones={zones} floor={floor} exploded={exploded} view={view} theme={theme} selectedRobotId={selectedRobotId} showZones={showZones} showHeat={showHeat} bigLabels={demoMode} now={now} route={route} heat={heat} onSelectRobot={selectRobot} tablets={tablets} showTablets={showTablets} selectedTabletId={selectedTabletId} onSelectTablet={selectTablet} incidents={incidents} selectedIncidentId={selectedIncidentId} onSelectIncident={selectIncident} onDropRobot={dropRobot} home={home} />
      </Suspense>
      <div className="map-floor-tag"><span className="eyebrow">Showing</span><strong>{label}</strong></div>
      <div className="map-scale-note" aria-label="Physical scene scale">
        <span className="eyebrow">Metric scale</span>
        <strong>Q1 · {Q1_DIMENSIONS.height.toFixed(2)} m</strong>
        <small>Floor-to-floor · {CLINIC_DIMENSIONS.floorToFloor.toFixed(2)} m</small>
      </div>
      <Legend />
      <p className="map-hint">Drag to turn · scroll to zoom · click a robot · drag a simulated robot to move it</p>
    </div>
  )
}

export function LiveMap() {
  const now = useNow()
  const loaded = useStore((state) => state.loaded)
  const demoMode = useStore((state) => state.demoMode)
  const fleetTab = useStore((state) => state.fleetTab)
  return (
    <div className={`live ${demoMode ? 'is-presenting' : ''}`}>
      {!demoMode && <Kpis now={now} />}
      <div className="live-grid">
        <Panel className="map-panel" flush>
          <MapToolbar />
          <MapStage now={now} />
        </Panel>
        <div className="live-side">
          <IncidentsPanel now={now} />
          <FleetList now={now} />
          {!demoMode && <HomePlace />}
          {loaded && (fleetTab === 'tablets' ? <TabletDetail now={now} /> : <RobotDetail now={now} />)}
          {!demoMode && <ActivityFeed now={now} />}
        </div>
      </div>
    </div>
  )
}
