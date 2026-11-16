/** What is drawn on top of a floor: zones, the planned route of a task, and the heat map. */
import { useEffect, useMemo } from 'react'
import { Line, Text } from '@react-three/drei'
import { ShapeGeometry } from 'three'
import { heatCells } from '../lib/heat'
import { centroid } from '../lib/geometry'
import type { HeatGrid, Point, Zone } from '../types'
import { ROUTE_COLOR, ZONE_COLOR } from './palette'
import { TEXT_PROPS, groundShape } from './shapes'

export function ZoneShape({ zone, highlighted = false }: { zone: Zone; highlighted?: boolean }) {
  const geometry = useMemo(() => new ShapeGeometry(groundShape(zone.polygon)), [zone.polygon])
  useEffect(() => () => geometry.dispose(), [geometry])
  const outline = useMemo((): Array<[number, number, number]> => [...zone.polygon, zone.polygon[0]].map(([x, y]) => [x, 0.07, y]), [zone.polygon])
  const color = ZONE_COLOR[zone.kind]
  const [labelX, labelY] = centroid(zone.polygon)
  return (
    <>
      <mesh geometry={geometry} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.05, 0]}>
        <meshBasicMaterial color={color} transparent opacity={highlighted ? 0.3 : 0.16} depthWrite={false} />
      </mesh>
      <Line points={outline} color={color} lineWidth={highlighted ? 3 : 2} dashed={zone.kind === 'restricted'} dashSize={0.35} gapSize={0.2} />
      <Text {...TEXT_PROPS} position={[labelX, 0.08, labelY + 0.55]} rotation={[-Math.PI / 2, 0, 0]} fontSize={0.24} color={color} anchorX="center" anchorY="middle">
        {zone.kind === 'deaf' ? 'DEAF ZONE · MIC OFF' : 'RESTRICTED · ADVISORY'}
      </Text>
    </>
  )
}

export function RouteLine({ path, from, to, estimate = true }: { path: Point[]; from: Point | null; to: Point; estimate?: boolean }) {
  const points = useMemo((): Array<[number, number, number]> => path.map(([x, y]) => [x, 0.09, y]), [path])
  if (points.length < 2) return null
  return (
    <>
      <Line points={points} color={ROUTE_COLOR} lineWidth={4} transparent opacity={0.22} />
      <Line points={points} color={ROUTE_COLOR} lineWidth={2} dashed dashSize={0.25} gapSize={0.16} />
      {from && (
        <mesh position={[from[0], 0.06, from[1]]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.2, 0.3, 32]} />
          <meshBasicMaterial color={ROUTE_COLOR} />
        </mesh>
      )}
      <group position={[to[0], 0, to[1]]}>
        <mesh position={[0, 0.06, 0]} rotation={[-Math.PI / 2, 0, 0]}>
          <circleGeometry args={[0.32, 32]} />
          <meshBasicMaterial color={ROUTE_COLOR} transparent opacity={0.35} />
        </mesh>
        <mesh position={[0, 0.5, 0]}>
          <cylinderGeometry args={[0.02, 0.02, 1, 8]} />
          <meshBasicMaterial color={ROUTE_COLOR} />
        </mesh>
        <mesh position={[0, 1.02, 0]}>
          <sphereGeometry args={[0.09, 16, 12]} />
          <meshBasicMaterial color={ROUTE_COLOR} />
        </mesh>
        {estimate && (
          // The server only estimates the path: the robot plans its own way.
          <Text {...TEXT_PROPS} position={[0, 0.08, 0.55]} rotation={[-Math.PI / 2, 0, 0]} fontSize={0.2} letterSpacing={0.08} color={ROUTE_COLOR} anchorX="center" anchorY="middle">
            ESTIMATE
          </Text>
        )}
      </group>
    </>
  )
}

/** Warm squares where robots spend the most time, from the floor's heat grid. */
export function HeatLayer({ grid }: { grid: HeatGrid | undefined }) {
  const cells = useMemo(() => (grid ? heatCells(grid) : []), [grid])
  return (
    <>
      {cells.map((cell) => (
        <mesh key={`${cell.x}-${cell.y}`} position={[cell.x, 0.045, cell.y]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[cell.size * 0.96, cell.size * 0.96]} />
          <meshBasicMaterial color={cell.weight > 0.66 ? '#ff5468' : cell.weight > 0.33 ? '#ff9440' : '#f6c453'} transparent opacity={0.18 + cell.weight * 0.5} depthWrite={false} />
        </mesh>
      ))}
    </>
  )
}
