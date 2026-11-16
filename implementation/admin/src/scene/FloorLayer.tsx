/** One floor of the clinic: slab, coloured room floors, low walls, furniture and room names. */
import { useEffect, useMemo } from 'react'
import { Text } from '@react-three/drei'
import { ExtrudeGeometry, ShapeGeometry } from 'three'
import { boundsOf, centroid } from '../lib/geometry'
import type { ClinicMap, MapRoom, MapWall } from '../types'
import { Furniture } from './Furniture'
import type { ScenePalette } from './palette'
import { CLINIC_DIMENSIONS } from './scale'
import { SLAB_DEPTH, TEXT_PROPS, WALL_HEIGHT, WALL_THICKNESS, groundShape, safeLabel } from './shapes'

function RoomFloor({ room, palette, bigLabels }: { room: MapRoom; palette: ScenePalette; bigLabels: boolean }) {
  const geometry = useMemo(() => new ShapeGeometry(groundShape(room.polygon)), [room.polygon])
  useEffect(() => () => geometry.dispose(), [geometry])
  const [labelX, labelY] = room.labelAt ?? centroid(room.polygon)
  const [lightX, lightY] = centroid(room.polygon)
  const closed = room.kind === 'elevator'
  return (
    <>
      <mesh geometry={geometry} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.012, 0]} receiveShadow>
        <meshStandardMaterial color={palette.floor[room.kind]} roughness={0.92} />
      </mesh>
      <Text {...TEXT_PROPS} position={[labelX, 0.03, labelY]} rotation={[-Math.PI / 2, 0, 0]} fontSize={bigLabels ? 0.62 : 0.4} letterSpacing={0.08} color={palette.label} fillOpacity={closed ? 0.4 : 0.78} anchorX="center" anchorY="middle">
        {safeLabel(room.label).toUpperCase()}
      </Text>
      {closed && (
        <Text {...TEXT_PROPS} position={[labelX, 0.03, labelY + 0.55]} rotation={[-Math.PI / 2, 0, 0]} fontSize={0.2} color={palette.label} fillOpacity={0.4} anchorX="center" anchorY="middle">
          no robot access
        </Text>
      )}
      {!['corridor', 'elevator'].includes(room.kind) && (
        <mesh position={[lightX, CLINIC_DIMENSIONS.ceilingFixtureHeight, lightY]} castShadow={false}>
          <boxGeometry args={[0.52, 0.035, 0.14]} />
          <meshStandardMaterial color={palette.ceilingLight} emissive={palette.ceilingLight} emissiveIntensity={0.5} roughness={0.35} />
        </mesh>
      )}
    </>
  )
}

function WallRun({ wall, palette }: { wall: MapWall; palette: ScenePalette }) {
  return (
    <>
      {wall.points.slice(1).map((end, index) => {
        const start = wall.points[index]
        const dx = end[0] - start[0]
        const dy = end[1] - start[1]
        const length = Math.hypot(dx, dy) + WALL_THICKNESS
        return (
          <group key={`${start[0]}-${start[1]}-${end[0]}-${end[1]}`} position={[(start[0] + end[0]) / 2, 0, (start[1] + end[1]) / 2]} rotation={[0, -Math.atan2(dy, dx), 0]}>
            <mesh position={[0, WALL_HEIGHT / 2, 0]} castShadow receiveShadow>
              <boxGeometry args={[length, WALL_HEIGHT, WALL_THICKNESS]} />
              <meshStandardMaterial color={palette.wall} roughness={0.8} />
            </mesh>
            <mesh position={[0, WALL_HEIGHT + 0.015, 0]}>
              <boxGeometry args={[length, 0.03, WALL_THICKNESS]} />
              <meshStandardMaterial color={palette.wallCap} roughness={0.5} />
            </mesh>
            <mesh position={[0, 0.06, WALL_THICKNESS / 2 + 0.008]}>
              <boxGeometry args={[length, 0.08, 0.018]} />
              <meshStandardMaterial color={palette.wallCap} roughness={0.6} />
            </mesh>
          </group>
        )
      })}
    </>
  )
}

interface FloorLayerProps {
  map: ClinicMap
  floorId: number
  palette: ScenePalette
  bigLabels: boolean
}

export function FloorLayer({ map, floorId, palette, bigLabels }: FloorLayerProps) {
  const floor = map.floors.find((entry) => entry.id === floorId)
  const outline = floor?.outline
  const slab = useMemo(() => outline ? new ExtrudeGeometry(groundShape(outline), { depth: SLAB_DEPTH, bevelEnabled: false }) : null, [outline])
  const bounds = useMemo(() => outline ? boundsOf(outline) : null, [outline])
  useEffect(() => () => slab?.dispose(), [slab])
  if (!slab || !bounds) return null

  return (
    <>
      <mesh geometry={slab} rotation={[-Math.PI / 2, 0, 0]} position={[0, -SLAB_DEPTH, 0]} receiveShadow>
        <meshStandardMaterial color={palette.slab} roughness={0.9} />
      </mesh>
      {map.rooms.filter((room) => room.floor === floorId).map((room) => <RoomFloor key={room.id} room={room} palette={palette} bigLabels={bigLabels} />)}
      {map.walls.filter((wall) => wall.floor === floorId).map((wall, index) => <WallRun key={`wall-${index}`} wall={wall} palette={palette} />)}
      {map.props.filter((prop) => prop.floor === floorId).map((prop) => <Furniture key={prop.id} prop={prop} palette={palette} centerX={bounds.centerX} centerY={bounds.centerY} />)}
    </>
  )
}
