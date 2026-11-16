/**
 * One robot on the map. The server speaks about once a second; between two messages the
 * robot glides from where it is drawn to where it was last reported, so it never jumps.
 */
import { useEffect, useLayoutEffect, useRef } from 'react'
import type { CSSProperties, PointerEvent as ReactPointerEvent } from 'react'
import { Html, RoundedBox } from '@react-three/drei'
import { useFrame, useThree } from '@react-three/fiber'
import type { ThreeEvent } from '@react-three/fiber'
import { MicOff, WifiOff } from 'lucide-react'
import { Plane, Vector2, Vector3 } from 'three'
import type { Group, Mesh } from 'three'
import { MOOD_EMOJI, MOOD_LABEL, STATE_LABEL, displayMood } from '../lib/format'
import { angleDelta, clamp } from '../lib/geometry'
import type { DisplayState, Robot } from '../types'
import { STATE_COLOR } from './palette'
import type { ScenePalette } from './palette'
import { Q1_DIMENSIONS, Q1_POSE } from './scale'
import { headingToRotation } from './shapes'

interface Pose {
  x: number
  y: number
  heading: number
}

interface Track {
  from: Pose
  to: Pose
  startedAt: number
  duration: number
  lastSample: number
}

const MIN_GLIDE_MS = 120
const MAX_GLIDE_MS = 1500
const STALE_GREY = '#8a9692'

function poseAt(track: Track, now: number): Pose {
  const t = clamp((now - track.startedAt) / track.duration, 0, 1)
  return {
    x: track.from.x + (track.to.x - track.from.x) * t,
    y: track.from.y + (track.to.y - track.from.y) * t,
    heading: track.from.heading + angleDelta(track.from.heading, track.to.heading) * t,
  }
}

interface RobotBodyProps {
  shell: string
  dark: string
  accent: string
  glow: number
  opacity: number
  holding: boolean
  beacon: React.RefObject<Mesh | null>
}

interface PartProps {
  size: [number, number, number]
  at: [number, number, number]
  color: string
  roughness?: number
  metalness?: number
  radius?: number
  opacity: number
  rotation?: [number, number, number]
}

function Part({ size, at, color, roughness = 0.34, metalness = 0.12, radius = 0.025, opacity, rotation = [0, 0, 0] }: PartProps) {
  const faded = opacity < 1
  return (
    <RoundedBox args={size} position={at} rotation={rotation} radius={radius} smoothness={4} castShadow>
      <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} transparent={faded} opacity={opacity} />
    </RoundedBox>
  )
}

function Joint({ at, radius, color, opacity, emissive = false }: { at: [number, number, number]; radius: number; color: string; opacity: number; emissive?: boolean }) {
  const faded = opacity < 1
  return (
    <mesh position={at} castShadow>
      <sphereGeometry args={[radius, 18, 14]} />
      <meshStandardMaterial color={color} roughness={0.28} metalness={0.3} emissive={emissive ? color : '#000000'} emissiveIntensity={emissive ? 1.25 : 0} transparent={faded} opacity={opacity} />
    </mesh>
  )
}

function RobotBody({ shell, dark, accent, glow, opacity, holding, beacon }: RobotBodyProps) {
  const faded = opacity < 1
  return (
    <>
      {[-1, 1].map((side) => <Part key={`foot-${side}`} size={Q1_DIMENSIONS.foot} at={[side * 0.055, Q1_POSE.footY, 0.025]} color={dark} roughness={0.42} metalness={0.35} opacity={opacity} radius={0.018} />)}
      {[-1, 1].map((side) => (
        <group key={`leg-${side}`}>
          <Part size={Q1_DIMENSIONS.lowerLeg} at={[side * 0.055, Q1_POSE.lowerLegY, -0.005]} color={shell} opacity={opacity} radius={0.026} />
          <Joint at={[side * 0.055, Q1_POSE.kneeY, 0]} radius={0.047} color={accent} opacity={opacity} emissive={glow > 0} />
          <Part size={Q1_DIMENSIONS.upperLeg} at={[side * 0.055, Q1_POSE.upperLegY, 0]} color={shell} opacity={opacity} radius={0.028} />
        </group>
      ))}
      <Part size={Q1_DIMENSIONS.pelvis} at={[0, Q1_POSE.pelvisY, 0]} color={dark} roughness={0.28} metalness={0.28} opacity={opacity} radius={0.055} />
      <Part size={Q1_DIMENSIONS.torso} at={[0, Q1_POSE.torsoY, 0]} color={shell} roughness={0.3} metalness={0.14} opacity={opacity} radius={0.06} />
      <Part size={[0.12, 0.035, 0.025]} at={[0, Q1_POSE.torsoY + 0.01, 0.085]} color={accent} roughness={0.24} metalness={0.2} opacity={opacity} radius={0.012} />
      {[-1, 1].map((side) => (
        <group key={`arm-${side}`}>
          <Joint at={[side * 0.16, Q1_POSE.shoulderY, 0]} radius={0.052} color={accent} opacity={opacity} emissive={glow > 0} />
          <Part size={Q1_DIMENSIONS.upperArm} at={[side * 0.17, Q1_POSE.elbowY, 0.005]} color={shell} opacity={opacity} radius={0.027} rotation={[0, 0, side * 0.08]} />
          <Joint at={[side * 0.17, Q1_POSE.elbowY - 0.09, 0.01]} radius={0.038} color={accent} opacity={opacity} emissive={glow > 0} />
          <Part size={Q1_DIMENSIONS.forearm} at={[side * 0.17, Q1_POSE.wristY, 0.025]} color={shell} opacity={opacity} radius={0.025} rotation={[side * 0.08, 0, side * 0.05]} />
          <Part size={Q1_DIMENSIONS.hand} at={[side * 0.17, Q1_POSE.wristY - 0.09, 0.045]} color={dark} roughness={0.4} metalness={0.28} opacity={opacity} radius={0.022} />
        </group>
      ))}
      <mesh position={[0, Q1_POSE.headY, 0]} scale={[Q1_DIMENSIONS.head[0] / 0.16, Q1_DIMENSIONS.head[1] / 0.145, Q1_DIMENSIONS.head[2] / 0.135]} castShadow>
        <sphereGeometry args={[0.08, 28, 20]} />
        <meshStandardMaterial color={shell} roughness={0.26} metalness={0.12} transparent={faded} opacity={opacity} />
      </mesh>
      <mesh position={[0, Q1_POSE.headY - 0.002, 0.061]} scale={[0.9, 0.74, 0.42]}>
        <sphereGeometry args={[0.065, 24, 16]} />
        <meshStandardMaterial color={dark} roughness={0.12} metalness={0.48} transparent={faded} opacity={opacity} />
      </mesh>
      {[-0.025, 0.025].map((side) => (
        <mesh key={side} position={[side, Q1_POSE.headY, 0.086]}>
          <sphereGeometry args={[0.008, 12, 10]} />
          <meshBasicMaterial color={accent} transparent={faded} opacity={opacity} />
        </mesh>
      ))}
      <mesh ref={beacon} position={[0, Q1_POSE.beaconY, 0]}>
        <sphereGeometry args={[0.012, 12, 10]} />
        <meshBasicMaterial color={accent} transparent={faded} opacity={opacity} />
      </mesh>
      {holding && (
        <>
          <Part size={[0.22, 0.025, 0.14]} at={[0, 0.43, 0.12]} color={dark} roughness={0.4} metalness={0.25} opacity={opacity} radius={0.01} />
          <Part size={[0.14, 0.1, 0.1]} at={[0, 0.49, 0.15]} color="#f3dfb4" roughness={0.8} metalness={0} opacity={opacity} radius={0.012} />
        </>
      )}
    </>
  )
}

interface RobotMarkerProps {
  robot: Robot
  display: DisplayState
  selected: boolean
  palette: ScenePalette
  bigLabels: boolean
  now: number
  onSelect: (robotId: string) => void
  /**
   * Simulated robots only: called when the robot is dropped after a drag, with the point in metres.
   * Resolves true when the server moved it; false makes it glide back where it was.
   */
  onDrop?: (robotId: string, x: number, y: number) => Promise<boolean>
}

/** A drag shorter than this is a click, not a move. */
const MIN_DRAG_M = 0.2

/** The part of the camera controls a drag turns off. */
interface ToggleControls { enabled: boolean }

export function RobotMarker({ robot, display, selected, palette, bigLabels, now, onSelect, onDrop }: RobotMarkerProps) {
  const { x, y, heading } = robot.position
  const group = useRef<Group>(null)
  const ring = useRef<Mesh>(null)
  const beacon = useRef<Mesh>(null)
  const track = useRef<Track | null>(null)
  /** While dragged (or waiting for the server's answer), the robot stays where the pointer left it. */
  const held = useRef<Pose | null>(null)
  const camera = useThree((state) => state.camera)
  const raycaster = useThree((state) => state.raycaster)
  const canvas = useThree((state) => state.gl.domElement)
  const getThree = useThree((state) => state.get)

  useLayoutEffect(() => {
    if (!group.current || track.current) return
    const now = performance.now()
    track.current = { from: { x, y, heading }, to: { x, y, heading }, startedAt: now, duration: MIN_GLIDE_MS, lastSample: now }
    group.current.position.set(x, 0, y)
    group.current.rotation.y = headingToRotation(heading)
  }, [x, y, heading])

  useEffect(() => {
    const current = track.current
    if (!current) return
    const now = performance.now()
    track.current = { from: poseAt(current, now), to: { x, y, heading }, startedAt: now, duration: clamp(now - current.lastSample, MIN_GLIDE_MS, MAX_GLIDE_MS), lastSample: now }
  }, [x, y, heading, robot.lastSeen])

  const alarm = display === 'estop' || display === 'fault'
  useFrame(({ clock }) => {
    if (group.current && held.current) {
      group.current.position.set(held.current.x, 0, held.current.y)
    } else if (group.current && track.current) {
      const pose = poseAt(track.current, performance.now())
      group.current.position.set(pose.x, 0, pose.y)
      group.current.rotation.y = headingToRotation(pose.heading)
    }
    if (ring.current) ring.current.scale.setScalar(selected ? 1 + Math.sin(clock.elapsedTime * 3.2) * 0.06 : 1)
    if (beacon.current) beacon.current.visible = !alarm || Math.sin(clock.elapsedTime * 9) > -0.2
  })

  const offline = display === 'offline'
  const accent = STATE_COLOR[display]
  const handleClick = (event: ThreeEvent<MouseEvent>): void => { event.stopPropagation(); onSelect(robot.id) }
  const setCursor = (cursor: string): void => { document.body.style.cursor = cursor }
  const draggable = Boolean(onDrop) && robot.simulated && !offline
  const mood = displayMood(robot, now)

  // Drag on the floor plane: the pointer's ray meets the plane at the height of this robot's floor.
  const startDrag = (event: ThreeEvent<PointerEvent>): void => {
    if (!draggable || event.button !== 0) return
    event.stopPropagation()
    beginDrag()
  }
  // The tag above the robot (its emoji and name) is what people grab: it starts the same drag.
  const startTagDrag = (event: ReactPointerEvent<HTMLButtonElement>): void => {
    if (!draggable || event.button !== 0) return
    event.stopPropagation()
    event.preventDefault()
    beginDrag()
  }
  const beginDrag = (): void => {
    if (!onDrop || !group.current) return
    const floorY = group.current.parent?.getWorldPosition(new Vector3()).y ?? 0
    const plane = new Plane(new Vector3(0, 1, 0), -floorY)
    const start = { x: group.current.position.x, y: group.current.position.z, heading }
    const hit = new Vector3()
    const pointer = new Vector2()
    held.current = start
    // Read at drag time: the camera controls are not ours to keep, only to pause during the drag.
    const controls = getThree().controls as unknown as ToggleControls | null
    if (controls) controls.enabled = false
    setCursor('grabbing')
    const move = (moveEvent: PointerEvent): void => {
      const box = canvas.getBoundingClientRect()
      pointer.set(((moveEvent.clientX - box.left) / box.width) * 2 - 1, -((moveEvent.clientY - box.top) / box.height) * 2 + 1)
      raycaster.setFromCamera(pointer, camera)
      if (raycaster.ray.intersectPlane(plane, hit)) held.current = { x: hit.x, y: hit.z, heading }
    }
    const up = (): void => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      if (controls) controls.enabled = true
      setCursor('')
      const drop = held.current
      if (!drop || Math.hypot(drop.x - start.x, drop.y - start.y) < MIN_DRAG_M) { held.current = null; return }
      void onDrop(robot.id, drop.x, drop.y).then((moved) => {
        const nowMs = performance.now()
        // Moved: glide on from the drop point. Refused: glide back to the last reported position.
        const latest = track.current?.to ?? start
        track.current = { from: drop, to: moved ? drop : latest, startedAt: nowMs, duration: moved ? MIN_GLIDE_MS : 600, lastSample: nowMs }
        held.current = null
      })
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  return (
    <group ref={group} onClick={handleClick} onPointerDown={startDrag} onPointerOver={(event) => { event.stopPropagation(); setCursor(draggable ? 'grab' : 'pointer') }} onPointerOut={() => { if (!held.current) setCursor('') }}>
      <mesh ref={ring} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.035, 0]}>
        <ringGeometry args={selected ? [Q1_POSE.ringSelectedRadius, Q1_POSE.ringSelectedRadius + 0.045, 48] : [Q1_POSE.ringRadius, Q1_POSE.ringRadius + 0.035, 48]} />
        <meshBasicMaterial color={accent} transparent opacity={selected ? 0.95 : 0.55} />
      </mesh>
      {selected && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.03, 0]}>
          <circleGeometry args={[Q1_POSE.ringSelectedRadius, 40]} />
          <meshBasicMaterial color={accent} transparent opacity={0.16} />
        </mesh>
      )}
      {!offline && (
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.04, 0.74]}>
          <circleGeometry args={[0.07, 3, Math.PI / 2]} />
          <meshBasicMaterial color={accent} transparent opacity={0.9} />
        </mesh>
      )}
      <RobotBody shell={offline ? STALE_GREY : palette.robotShell} dark={palette.robotDark} accent={accent} glow={offline ? 0 : 1.6} opacity={offline ? 0.5 : 1} holding={Boolean(robot.holding) && !offline} beacon={beacon} />
      <Html position={[0, Q1_DIMENSIONS.height + 0.14, 0]} center zIndexRange={[40, 0]}>
        <button type="button" className={`robot-tag ${selected ? 'is-selected' : ''} ${bigLabels ? 'is-big' : ''} ${offline ? 'is-offline' : ''}`} style={{ '--state': accent } as CSSProperties} onClick={() => onSelect(robot.id)} onPointerDown={startTagDrag} title={`${robot.name} · ${STATE_LABEL[display]} · ${MOOD_LABEL[mood]}${draggable ? ' · drag to move' : ''}`} data-testid={`robot-tag-${robot.id}`}>
          <span className="robot-mood" role="img" aria-label={MOOD_LABEL[mood]}>{MOOD_EMOJI[mood]}</span>
          <i />
          <b>{robot.id}</b>
          {offline ? <WifiOff size={12} aria-label="No signal" /> : !robot.micOpen && <MicOff size={12} aria-label="Microphone closed" />}
        </button>
      </Html>
    </group>
  )
}
