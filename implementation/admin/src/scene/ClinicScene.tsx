/**
 * The 3D clinic. One floor at a time, or every floor stacked ("exploded"). Robots, zones, the
 * route of the selected robot's task and the heat map are drawn on top.
 */
import { Suspense, useEffect, useMemo } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { ContactShadows, Html, Line, MapControls, OrbitControls, Text } from '@react-three/drei'
import type { Vector3 } from 'three'
import { displayState, floorName, isOpenTask } from '../lib/format'
import { boundsOf, mapBounds } from '../lib/geometry'
import type { ClinicMap, HeatGrid, Incident, Point, Robot, Tablet, Task, TaskRoute, Zone } from '../types'
import { FloorLayer } from './FloorLayer'
import { IncidentLayer } from './IncidentLayer'
import { HeatLayer, RouteLine, ZoneShape } from './Overlays'
import { DARK_SCENE, LIGHT_SCENE } from './palette'
import type { ScenePalette } from './palette'
import { RobotMarker } from './RobotMarker'
import { TabletMarker } from './TabletMarker'
import { CLINIC_DIMENSIONS } from './scale'
import { TEXT_PROPS, safeLabel } from './shapes'

export const FLOOR_GAP = CLINIC_DIMENSIONS.floorToFloor

/** The part of the camera controls the rig moves. */
interface ControlsLike {
  target: Vector3
  update: () => void
}

export interface ClinicSceneProps {
  map: ClinicMap
  robots: Robot[]
  tasks: Task[]
  zones: Zone[]
  floor: number
  exploded: boolean
  view: 'iso' | 'top'
  theme: 'dark' | 'light'
  selectedRobotId: string | null
  showZones: boolean
  showHeat: boolean
  bigLabels: boolean
  now: number
  /** The server's estimate of the selected robot's task path. */
  route: TaskRoute | null
  /** The heat map, per floor. */
  heat: Map<number, HeatGrid>
  onSelectRobot: (robotId: string) => void
  tablets: Tablet[]
  showTablets: boolean
  selectedTabletId: string | null
  onSelectTablet: (tabletId: string) => void
  /** Open incidents: always drawn, there is no switch to hide them. */
  incidents: Incident[]
  selectedIncidentId: string | null
  onSelectIncident: (incidentId: string) => void
  /** Simulated robots can be dragged; resolves true when the server moved the robot. */
  onDropRobot?: (robotId: string, x: number, y: number) => Promise<boolean>
  /** The fleet's home place (emergency, dock, charging), marked with a house. */
  home?: { x: number; y: number; floor: number; label: string } | null
}

/** The fleet's home place: a ring on the floor and a big house above it. */
function HomeMarker({ x, y, label, bigLabels }: { x: number; y: number; label: string; bigLabels: boolean }) {
  return (
    <group position={[x, 0, y]}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.03, 0]}>
        <ringGeometry args={[0.42, 0.5, 48]} />
        <meshBasicMaterial color="#f5b84b" transparent opacity={0.85} />
      </mesh>
      <Html position={[0, 0.7, 0]} center zIndexRange={[30, 0]}>
        <span className={`home-tag ${bigLabels ? 'is-big' : ''}`} title={`Home place: ${label}`} data-testid="home-marker"><span role="img" aria-label="Home place">🏠</span>{label}</span>
      </Html>
    </group>
  )
}

/** Where to draw a tablet: its reported position, or the anchor of its place. */
function tabletSpot(map: ClinicMap, tablet: Tablet): { x: number; y: number; floor: number } | null {
  if (tablet.position) return tablet.position
  const place = map.places.find((entry) => entry.id === tablet.place)
  return place ? { x: place.x, y: place.y, floor: place.floor } : null
}

/** Where the route marks its stops: the shelf (while the robot still has to pick the item up) and the goal. */
function routeStops(map: ClinicMap, route: TaskRoute | null, robot: Robot | undefined, task: Task | undefined): { from: Point | null; to: Point } | null {
  if (!route) return null
  const source = map.places.find((place) => place.id === task?.fromPlace)
  const pickUpFirst = Boolean(source) && source?.floor === route.floor && !robot?.holding
  return { from: pickUpFirst && source ? [source.x, source.y] : null, to: route.points[route.points.length - 1] }
}

const FOV = 34
const TAN_HALF_FOV = Math.tan((FOV / 2) * (Math.PI / 180))

/** Places the camera so the whole building fits the panel, whatever its shape. */
function CameraRig({ map, floor, exploded, view }: { map: ClinicMap; floor: number; exploded: boolean; view: 'iso' | 'top' }) {
  const camera = useThree((state) => state.camera)
  const controls = useThree((state) => state.controls) as unknown as ControlsLike | null
  const aspect = useThree((state) => Math.round((state.size.width / Math.max(1, state.size.height)) * 10) / 10)
  const bounds = useMemo(() => mapBounds(map), [map])
  const floorCount = map.floors.length
  useEffect(() => {
    const stackHeight = exploded ? (floorCount - 1) * FLOOR_GAP : 0
    const elevation = view === 'top' ? Math.PI / 2 : exploded ? 0.5 : 0.86
    const seenDepth = (bounds.depth + 3) * Math.sin(elevation) + stackHeight * Math.cos(elevation) + (view === 'top' ? 0 : 2)
    const distance = (Math.max((bounds.width + 3) / aspect, seenDepth) / (2 * TAN_HALF_FOV)) * 1.04
    const target: [number, number, number] = [bounds.centerX, stackHeight / 2, bounds.centerY + (view === 'top' ? 0 : 0.6)]
    const yaw = view === 'top' ? 0 : -0.16
    camera.position.set(target[0] + Math.sin(yaw) * Math.cos(elevation) * distance, target[1] + Math.sin(elevation) * distance, target[2] + Math.cos(yaw) * Math.cos(elevation) * distance + (view === 'top' ? 0.01 : 0))
    camera.lookAt(...target)
    if (controls) { controls.target.set(...target); controls.update() }
  }, [camera, controls, bounds, aspect, floor, exploded, view, floorCount])
  return null
}

function FloorTitle({ label, x, z, y, palette }: { label: string; x: number; z: number; y: number; palette: ScenePalette }) {
  return (
    <Text {...TEXT_PROPS} position={[x, y + 0.05, z]} rotation={[-Math.PI / 2, 0, 0]} fontSize={0.55} letterSpacing={0.1} color={palette.label} fillOpacity={0.7} anchorX="left" anchorY="middle">
      {safeLabel(label).toUpperCase()}
    </Text>
  )
}

function Lights({ palette, centerX, centerZ, span }: { palette: ScenePalette; centerX: number; centerZ: number; span: number }) {
  return (
    <>
      <ambientLight intensity={palette.ambient * 0.28} />
      <hemisphereLight args={['#ffffff', palette.ground, palette.ambient * 0.6]} />
      <directionalLight position={[centerX - span * 0.45, span * 1.2, centerZ + span * 0.65]} intensity={palette.sun} castShadow shadow-mapSize={[2048, 2048]} shadow-camera-left={-span * 0.8} shadow-camera-right={span * 0.8} shadow-camera-top={span * 0.8} shadow-camera-bottom={-span * 0.8} shadow-camera-near={1} shadow-camera-far={span * 3} shadow-bias={-0.0004} shadow-normalBias={0.03}>
        <object3D attach="target" position={[centerX, 0, centerZ]} />
      </directionalLight>
      <pointLight position={[centerX, span * 0.75, centerZ]} intensity={palette.sun * 0.2} distance={span * 2.2} decay={2} color="#d9fff2" />
    </>
  )
}

function ScaleReference({ x, z, palette }: { x: number; z: number; palette: ScenePalette }) {
  return (
    <group position={[x, 0, z]}>
      <Line points={[[0, 0.035, 0], [1, 0.035, 0]]} color={palette.label} lineWidth={1.5} transparent opacity={0.65} />
      <Line points={[[0, 0.02, -0.07], [0, 0.02, 0.07]]} color={palette.label} lineWidth={1.5} transparent opacity={0.65} />
      <Line points={[[1, 0.02, -0.07], [1, 0.02, 0.07]]} color={palette.label} lineWidth={1.5} transparent opacity={0.65} />
      <Text {...TEXT_PROPS} position={[0.5, 0.08, 0.13]} rotation={[-Math.PI / 2, 0, 0]} fontSize={0.18} color={palette.label} fillOpacity={0.68} anchorX="center" anchorY="middle">
        1 m
      </Text>
    </group>
  )
}

export function ClinicScene(props: ClinicSceneProps) {
  const { map, robots, tasks, zones, floor, exploded, view, theme, selectedRobotId, showZones, showHeat, bigLabels, now, route, heat, onSelectRobot, tablets, showTablets, selectedTabletId, onSelectTablet, incidents, selectedIncidentId, onSelectIncident, onDropRobot, home } = props
  const palette = theme === 'light' ? LIGHT_SCENE : DARK_SCENE
  const bounds = useMemo(() => mapBounds(map), [map])
  const span = Math.max(bounds.width, bounds.depth)
  const floors = useMemo(() => [...map.floors].sort((a, b) => a.id - b.id), [map])
  const visible = exploded ? floors : floors.filter((entry) => entry.id === floor)
  const heightOf = (floorId: number): number => exploded ? floors.findIndex((entry) => entry.id === floorId) * FLOOR_GAP : 0
  const selected = robots.find((robot) => robot.id === selectedRobotId)
  const selectedTask = tasks.find((task) => task.id === selected?.taskId && isOpenTask(task))
  const stops = routeStops(map, route, selected, selectedTask)
  const placedTablets = useMemo(() => (showTablets ? tablets.flatMap((tablet) => { const spot = tabletSpot(map, tablet); return spot ? [{ tablet, spot }] : [] }) : []), [map, tablets, showTablets])

  const ControlsKind = view === 'top' ? MapControls : OrbitControls

  return (
    <Canvas shadows="percentage" dpr={[1, 2]} camera={{ fov: FOV, near: 0.1, far: 400, position: [bounds.centerX, span, bounds.centerY + span] }} gl={{ antialias: true, preserveDrawingBuffer: true }} onPointerMissed={() => { document.body.style.cursor = '' }}>
      <color attach="background" args={[palette.background]} />
      <fog attach="fog" args={[palette.background, span * 1.6, span * 4]} />
      <Lights palette={palette} centerX={bounds.centerX} centerZ={bounds.centerY} span={span} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[bounds.centerX, -0.36, bounds.centerY]} receiveShadow>
        <planeGeometry args={[span * 6, span * 6]} />
        <meshStandardMaterial color={palette.ground} roughness={1} />
      </mesh>
      <ContactShadows position={[bounds.centerX, -0.015, bounds.centerY]} opacity={theme === 'light' ? 0.18 : 0.28} scale={span * 1.25} blur={2.4} far={8} resolution={1024} frames={1} />
      <ScaleReference x={bounds.minX + 0.8} z={bounds.maxY + 0.65} palette={palette} />
      <Suspense fallback={null}>
        {visible.map((entry) => {
          const outline = boundsOf(entry.outline)
          return (
            <group key={entry.id} position={[0, heightOf(entry.id), 0]}>
              <FloorLayer map={map} floorId={entry.id} palette={palette} bigLabels={bigLabels} />
              {exploded && <FloorTitle label={floorName(map, entry.id)} x={outline.minX} z={outline.maxY + 1.1} y={0} palette={palette} />}
              <IncidentLayer map={map} floor={entry.id} incidents={incidents} selectedIncidentId={selectedIncidentId} onSelect={onSelectIncident} />
              {showZones && zones.filter((zone) => zone.floor === entry.id).map((zone) => <ZoneShape key={zone.id} zone={zone} />)}
              {showHeat && <HeatLayer grid={heat.get(entry.id)} />}
              {route && stops && route.floor === entry.id && <RouteLine path={route.points} from={stops.from} to={stops.to} estimate={route.estimate} />}
              {placedTablets.filter(({ spot }) => spot.floor === entry.id).map(({ tablet, spot }) => (
                <TabletMarker key={tablet.id} tablet={tablet} x={spot.x} y={spot.y} selected={tablet.id === selectedTabletId} hideLabel={bigLabels} onSelect={onSelectTablet} />
              ))}
              {home && home.floor === entry.id && <HomeMarker x={home.x} y={home.y} label={home.label} bigLabels={bigLabels} />}
              {robots.filter((robot) => robot.position.floor === entry.id).map((robot) => (
                <RobotMarker key={robot.id} robot={robot} display={displayState(robot, now)} selected={robot.id === selectedRobotId} palette={palette} bigLabels={bigLabels} now={now} onSelect={onSelectRobot} onDrop={onDropRobot} />
              ))}
            </group>
          )
        })}
      </Suspense>
      <ControlsKind makeDefault enableDamping dampingFactor={0.12} minDistance={8} maxDistance={span * 3} maxPolarAngle={view === 'top' ? 0.0001 : 1.32} minPolarAngle={0} enableRotate={view !== 'top'} screenSpacePanning={view === 'top'} />
      <CameraRig map={map} floor={floor} exploded={exploded} view={view} />
    </Canvas>
  )
}
