/**
 * One tablet on the map: a small screen on a stand, in its room. Staff tablets are violet, bedside
 * tablets sand-coloured, free or offline ones grey. A staff tablet whose position is an estimate
 * gets a faint circle of that size on the floor.
 *
 * In Presenter mode the tag shows only what the tablet is (staff or bed), never its label: the big
 * screen is seen by everyone in the room.
 */
import type { CSSProperties } from 'react'
import { Html } from '@react-three/drei'
import type { ThreeEvent } from '@react-three/fiber'
import { BatteryLow, BedDouble, Stethoscope, WifiOff } from 'lucide-react'
import type { Tablet } from '../types'
import { tabletColor, tabletTitle } from './tablet'

const STAND_HEIGHT = 0.8
const LOW_BATTERY = 20
const MAX_DRAWN_UNCERTAINTY_M = 3

interface TabletMarkerProps {
  tablet: Tablet
  x: number
  y: number
  selected: boolean
  hideLabel: boolean
  onSelect: (tabletId: string) => void
}

export function TabletMarker({ tablet, x, y, selected, hideLabel, onSelect }: TabletMarkerProps) {
  const color = tabletColor(tablet)
  const dim = !tablet.online
  const low = tablet.battery !== null && tablet.battery < LOW_BATTERY
  const Icon = tablet.kind === 'bedside' ? BedDouble : Stethoscope
  const tag = !tablet.assigned ? 'Free' : hideLabel ? (tablet.kind === 'bedside' ? 'Bed' : 'Staff') : tablet.label || tablet.id
  const handleClick = (event: ThreeEvent<MouseEvent>): void => { event.stopPropagation(); onSelect(tablet.id) }
  const setCursor = (cursor: string): void => { document.body.style.cursor = cursor }
  const radius = tablet.uncertainty ? Math.min(tablet.uncertainty, MAX_DRAWN_UNCERTAINTY_M) : 0

  return (
    <group position={[x, 0, y]} onClick={handleClick} onPointerOver={(event) => { event.stopPropagation(); setCursor('pointer') }} onPointerOut={() => setCursor('')}>
      {radius > 0 && tablet.online && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.025, 0]}>
          <circleGeometry args={[radius, 40]} />
          <meshBasicMaterial color={color} transparent opacity={0.08} depthWrite={false} />
        </mesh>
      )}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.03, 0]}>
        <ringGeometry args={selected ? [0.24, 0.32, 32] : [0.2, 0.23, 32]} />
        <meshBasicMaterial color={color} transparent opacity={selected ? 0.95 : 0.6} />
      </mesh>
      <mesh position={[0, STAND_HEIGHT / 2, 0]}>
        <cylinderGeometry args={[0.018, 0.018, STAND_HEIGHT, 8]} />
        <meshStandardMaterial color="#56625e" roughness={0.6} />
      </mesh>
      <group position={[0, STAND_HEIGHT + 0.12, 0]} rotation={[-0.35, 0, 0]}>
        <mesh castShadow>
          <boxGeometry args={[0.34, 0.25, 0.03]} />
          <meshStandardMaterial color="#1b2422" roughness={0.4} transparent={dim} opacity={dim ? 0.5 : 1} />
        </mesh>
        <mesh position={[0, 0, 0.017]}>
          <planeGeometry args={[0.3, 0.21]} />
          <meshStandardMaterial color={color} emissive={color} emissiveIntensity={dim ? 0 : 0.9} transparent={dim} opacity={dim ? 0.45 : 1} />
        </mesh>
      </group>
      <Html position={[0, STAND_HEIGHT + 0.55, 0]} center zIndexRange={[30, 0]}>
        <button
          type="button"
          className={`robot-tag tablet-tag ${selected ? 'is-selected' : ''} ${dim ? 'is-offline' : ''} ${tablet.assigned ? '' : 'is-free'}`}
          style={{ '--state': color } as CSSProperties}
          onClick={() => onSelect(tablet.id)}
          title={`${tabletTitle(tablet)}${tablet.battery !== null ? ` · battery ${Math.round(tablet.battery)}%` : ''}${dim ? ' · offline' : ''}`}
          data-testid={`tablet-tag-${tablet.id}`}
        >
          <Icon size={11} aria-hidden="true" />
          <b>{tag}</b>
          {dim ? <WifiOff size={11} aria-label="Offline" /> : low && <BatteryLow size={12} className="is-low" aria-label="Battery low" />}
        </button>
      </Html>
    </group>
  )
}
