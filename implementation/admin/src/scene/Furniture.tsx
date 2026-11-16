/** Furniture drawn from a few boxes each. Light on the graphics card, and it works offline. */
import type { ReactNode } from 'react'
import type { MapProp } from '../types'
import { ZONE_COLOR } from './palette'
import type { ScenePalette } from './palette'
import { CLINIC_DIMENSIONS } from './scale'

interface BoxProps {
  size: [number, number, number]
  at: [number, number, number]
  color: string
  roughness?: number
  metalness?: number
  emissive?: string
  noShadow?: boolean
}

/** A box given by its size and the centre of its base. */
function Box({ size, at, color, roughness = 0.75, metalness = 0, emissive, noShadow = false }: BoxProps) {
  return (
    <mesh position={[at[0], at[1] + size[1] / 2, at[2]]} castShadow={!noShadow} receiveShadow>
      <boxGeometry args={size} />
      <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} emissive={emissive ?? '#000000'} emissiveIntensity={emissive ? 0.9 : 0} />
    </mesh>
  )
}

function Bed({ prop, palette }: FurnitureProps) {
  const { width: w, depth: d } = prop
  const lengthwise = d >= w
  const pillow: [number, number, number] = lengthwise ? [w * 0.7, 0.1, 0.42] : [0.42, 0.1, d * 0.7]
  const pillowAt: [number, number, number] = lengthwise ? [0, 0.52, -d / 2 + 0.36] : [-w / 2 + 0.36, 0.52, 0]
  const cover: [number, number, number] = lengthwise ? [w * 0.96, 0.07, d * 0.56] : [w * 0.56, 0.07, d * 0.96]
  const coverAt: [number, number, number] = lengthwise ? [0, 0.52, d * 0.2] : [w * 0.2, 0.52, 0]
  return (
    <>
      <Box size={[w, 0.3, d]} at={[0, 0, 0]} color={palette.metal} />
      <Box size={[w * 0.94, 0.22, d * 0.96]} at={[0, 0.3, 0]} color={palette.linen} roughness={0.9} />
      <Box size={pillow} at={pillowAt} color={palette.linen} roughness={0.95} />
      <Box size={cover} at={coverAt} color={palette.fabric} roughness={0.95} />
    </>
  )
}

function Shelf({ prop, palette }: FurnitureProps) {
  const { width: w, depth: d } = prop
  const levels = [0.35, 0.8, 1.25]
  return (
    <>
      <Box size={[w, 1.6, d]} at={[0, 0, 0]} color={palette.dark} />
      {levels.map((level) => <Box key={level} size={[w * 1.02, 0.05, d * 1.02]} at={[0, level, 0]} color={palette.wood} noShadow />)}
      <Box size={[w * 1.02, 0.05, d * 1.02]} at={[0, 1.6, 0]} color={palette.wood} />
    </>
  )
}

function Sofa({ prop, palette }: FurnitureProps) {
  const { width: w, depth: d } = prop
  const wide = w >= d
  const back: [number, number, number] = wide ? [w, 0.42, 0.24] : [0.24, 0.42, d]
  const backAt: [number, number, number] = wide ? [0, 0.4, d / 2 - 0.12] : [w / 2 - 0.12, 0.4, 0]
  return (
    <>
      <Box size={[w, 0.4, d]} at={[0, 0, 0]} color={palette.fabricAlt} roughness={0.95} />
      <Box size={back} at={backAt} color={palette.fabricAlt} roughness={0.95} />
    </>
  )
}

function Plant({ palette }: FurnitureProps) {
  return (
    <>
      <mesh position={[0, 0.2, 0]} castShadow><cylinderGeometry args={[0.2, 0.15, 0.4, 14]} /><meshStandardMaterial color={palette.wood} roughness={0.8} /></mesh>
      <mesh position={[0, 0.72, 0]} castShadow><icosahedronGeometry args={[0.36, 1]} /><meshStandardMaterial color={palette.leaf} roughness={0.9} flatShading /></mesh>
      <mesh position={[0.12, 1.02, 0.06]} castShadow><icosahedronGeometry args={[0.22, 1]} /><meshStandardMaterial color={palette.leaf} roughness={0.9} flatShading /></mesh>
    </>
  )
}

function Dock({ prop, palette }: FurnitureProps) {
  const { width: w, depth: d } = prop
  return (
    <>
      <Box size={[w, 0.06, d]} at={[0, 0, 0]} color={palette.dark} roughness={0.4} />
      <Box size={[0.16, 0.9, d * 0.7]} at={[-w / 2 + 0.08, 0, 0]} color={palette.dark} roughness={0.4} />
      <Box size={[0.04, 0.5, d * 0.36]} at={[-w / 2 + 0.18, 0.25, 0]} color="#4fe0b5" emissive="#4fe0b5" noShadow />
    </>
  )
}

function Pool({ prop, palette }: FurnitureProps) {
  const { width: w, depth: d } = prop
  return (
    <>
      <Box size={[w + 0.5, 0.1, d + 0.5]} at={[0, 0, 0]} color={palette.linen} roughness={0.5} />
      <mesh position={[0, 0.105, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[w, d]} />
        <meshStandardMaterial color={palette.water} emissive={palette.water} emissiveIntensity={0.35} roughness={0.15} metalness={0.1} transparent opacity={0.92} />
      </mesh>
      {[-0.25, 0, 0.25].map((lane) => (
        <mesh key={lane} position={[0, 0.11, lane * d]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[w * 0.94, 0.05]} />
          <meshBasicMaterial color="#ffffff" transparent opacity={0.35} />
        </mesh>
      ))}
    </>
  )
}

function Bars({ prop, palette }: FurnitureProps) {
  const { width: w, depth: d } = prop
  return (
    <>
      <Box size={[w, 0.04, d]} at={[0, 0, 0]} color={palette.fabric} roughness={0.95} noShadow />
      {[-1, 1].map((side) => (
        <group key={side}>
          <Box size={[w, 0.05, 0.05]} at={[0, 0.9, side * (d / 2 - 0.05)]} color={palette.metal} roughness={0.3} />
          <Box size={[0.05, 0.9, 0.05]} at={[-w / 2 + 0.1, 0, side * (d / 2 - 0.05)]} color={palette.metal} roughness={0.3} />
          <Box size={[0.05, 0.9, 0.05]} at={[w / 2 - 0.1, 0, side * (d / 2 - 0.05)]} color={palette.metal} roughness={0.3} />
        </group>
      ))}
    </>
  )
}

function Table({ prop, palette }: FurnitureProps) {
  const { width: w, depth: d } = prop
  if (Math.abs(w - d) < 0.05) {
    return (
      <>
        <mesh position={[0, 0.24, 0]} castShadow><cylinderGeometry args={[0.07, 0.12, 0.48, 12]} /><meshStandardMaterial color={palette.dark} /></mesh>
        <mesh position={[0, 0.5, 0]} castShadow><cylinderGeometry args={[w / 2, w / 2, 0.05, 28]} /><meshStandardMaterial color={palette.wood} roughness={0.5} /></mesh>
      </>
    )
  }
  return (
    <>
      <Box size={[w * 0.8, 0.4, d * 0.7]} at={[0, 0, 0]} color={palette.dark} />
      <Box size={[w, 0.05, d]} at={[0, 0.4, 0]} color={palette.wood} roughness={0.5} />
    </>
  )
}

function Simple({ prop, palette }: FurnitureProps): ReactNode {
  const { width: w, depth: d, kind } = prop
  if (kind === 'counter') return <><Box size={[w, 0.95, d]} at={[0, 0, 0]} color={palette.wood} roughness={0.6} /><Box size={[w + 0.08, 0.06, d + 0.08]} at={[0, 0.95, 0]} color={palette.linen} roughness={0.4} /></>
  if (kind === 'desk') return <><Box size={[w * 0.92, 0.68, d * 0.8]} at={[0, 0, 0]} color={palette.dark} /><Box size={[w, 0.05, d]} at={[0, 0.68, 0]} color={palette.wood} roughness={0.5} /></>
  if (kind === 'cabinet') return <><Box size={[w, 0.95, d]} at={[0, 0, 0]} color={palette.linen} roughness={0.6} /><Box size={[w * 1.01, 0.03, d * 1.01]} at={[0, 0.5, 0]} color={palette.metal} noShadow /></>
  if (kind === 'armchair') return <><Box size={[w, 0.4, d]} at={[0, 0, 0]} color={palette.fabric} roughness={0.95} /><Box size={[w, 0.4, 0.2]} at={[0, 0.4, -d / 2 + 0.1]} color={palette.fabric} roughness={0.95} /></>
  if (kind === 'bench') return <Box size={[w, 0.44, d]} at={[0, 0, 0]} color={palette.wood} roughness={0.6} />
  if (kind === 'crate') return <Box size={[w, 0.6, d]} at={[0, 0, 0]} color={palette.wood} roughness={0.9} />
  if (kind === 'mat') return <Box size={[w, 0.04, d]} at={[0, 0, 0]} color={ZONE_COLOR.deaf} roughness={0.95} noShadow />
  if (kind === 'nightstand') return <Box size={[w, 0.5, d]} at={[0, 0, 0]} color={palette.wood} roughness={0.6} />
  // The elevator door: closed, the robots never go through it.
  if (kind === 'door') {
    const height = CLINIC_DIMENSIONS.doorHeight
    return (
      <>
        <Box size={[w, height, d]} at={[0, 0, 0]} color={palette.metal} roughness={0.25} metalness={0.35} />
        <Box size={[0.055, height + 0.03, d + 0.03]} at={[-w / 2 + 0.035, 0, 0]} color={palette.dark} roughness={0.3} metalness={0.4} noShadow />
        <Box size={[0.055, height + 0.03, d + 0.03]} at={[w / 2 - 0.035, 0, 0]} color={palette.dark} roughness={0.3} metalness={0.4} noShadow />
        <Box size={[w + 0.07, 0.055, d + 0.03]} at={[0, height, 0]} color={palette.dark} roughness={0.3} metalness={0.4} noShadow />
      </>
    )
  }
  return <><Box size={[w, 1.25, d]} at={[0, 0, 0]} color={palette.metal} roughness={0.25} /><Box size={[0.04, 1.25, d + 0.02]} at={[0, 0, 0]} color={palette.dark} noShadow /></>
}

interface FurnitureProps {
  prop: MapProp
  palette: ScenePalette
}

interface PlacedFurnitureProps extends FurnitureProps {
  /** The middle of the floor. Docks, beds and armchairs turn their back to the nearest outer wall. */
  centerX: number
  centerY: number
}

export function Furniture({ prop, palette, centerX, centerY }: PlacedFurnitureProps) {
  const flipX = prop.kind === 'dock' && prop.x > centerX
  const flipZ = (prop.kind === 'armchair' || prop.kind === 'bed') && prop.y > centerY
  const body = prop.kind === 'bed' ? <Bed prop={prop} palette={palette} />
    : prop.kind === 'shelf' ? <Shelf prop={prop} palette={palette} />
      : prop.kind === 'sofa' ? <Sofa prop={prop} palette={palette} />
        : prop.kind === 'plant' ? <Plant prop={prop} palette={palette} />
          : prop.kind === 'dock' ? <Dock prop={prop} palette={palette} />
            : prop.kind === 'pool' ? <Pool prop={prop} palette={palette} />
              : prop.kind === 'bars' ? <Bars prop={prop} palette={palette} />
                : prop.kind === 'table' ? <Table prop={prop} palette={palette} />
                  : <Simple prop={prop} palette={palette} />
  return <group position={[prop.x, 0, prop.y]} scale={[flipX ? -1 : 1, 1, flipZ ? -1 : 1]}>{body}</group>
}
