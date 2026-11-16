/**
 * Rooms with an open incident, on one floor: the room is tinted in the colour of its most serious
 * incident (critical red, warning orange, info yellow), its outline pulses when it is critical,
 * and a tag says what it is. A patient alarm always wins its room.
 */
import { useEffect, useMemo, useRef } from 'react'
import type { CSSProperties } from 'react'
import { Html, Line } from '@react-three/drei'
import { useFrame } from '@react-three/fiber'
import { BellRing, TriangleAlert } from 'lucide-react'
import { ShapeGeometry } from 'three'
import type { MeshBasicMaterial } from 'three'
import { centroid } from '../lib/geometry'
import { SEVERITY_COLOR, incidentRoom, incidentTitle, worse } from '../lib/incidents'
import type { ClinicMap, Incident, MapRoom } from '../types'
import { groundShape } from './shapes'

interface RoomIncidents {
  room: MapRoom
  top: Incident
  count: number
}

function RoomAlarm({ room, top, count, selected, onSelect }: RoomIncidents & { selected: boolean; onSelect: (incidentId: string) => void }) {
  const geometry = useMemo(() => new ShapeGeometry(groundShape(room.polygon)), [room.polygon])
  useEffect(() => () => geometry.dispose(), [geometry])
  const outline = useMemo((): Array<[number, number, number]> => [...room.polygon, room.polygon[0]].map(([x, y]) => [x, 0.06, y]), [room.polygon])
  const fill = useRef<MeshBasicMaterial>(null)
  const color = SEVERITY_COLOR[top.severity]
  const critical = top.severity === 'critical'
  const alarm = top.code === 'emergency_alarm'
  const [labelX, labelY] = room.labelAt ?? centroid(room.polygon)

  // Critical rooms breathe so they are seen from across the room; the rest stay still.
  useFrame(({ clock }) => {
    if (!fill.current) return
    fill.current.opacity = critical ? 0.2 + (Math.sin(clock.elapsedTime * 4) + 1) * 0.12 : 0.18
  })

  const Icon = alarm ? BellRing : TriangleAlert
  return (
    <group>
      <mesh geometry={geometry} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.045, 0]}>
        <meshBasicMaterial ref={fill} color={color} transparent opacity={0.18} depthWrite={false} />
      </mesh>
      <Line points={outline} color={color} lineWidth={critical ? 3.5 : 2} />
      <Html position={[labelX, 1.6, labelY]} center zIndexRange={[50, 0]}>
        <button type="button" className={`incident-tag ${critical ? 'is-critical' : ''} ${selected ? 'is-selected' : ''}`} style={{ '--incident': color } as CSSProperties} onClick={() => onSelect(top.id)} title={`${incidentTitle(top)}${count > 1 ? ` and ${count - 1} more` : ''}`} data-testid={`incident-tag-${top.id}`}>
          <Icon size={12} aria-hidden="true" />
          <b>{incidentTitle(top)}</b>
          {count > 1 && <em>+{count - 1}</em>}
        </button>
      </Html>
    </group>
  )
}

export function IncidentLayer({ map, floor, incidents, selectedIncidentId, onSelect }: { map: ClinicMap; floor: number; incidents: Incident[]; selectedIncidentId: string | null; onSelect: (incidentId: string) => void }) {
  const rooms = useMemo(() => {
    const byRoom = new Map<string, RoomIncidents>()
    for (const incident of incidents) {
      const room = incidentRoom(map, incident)
      if (!room || room.floor !== floor) continue
      const known = byRoom.get(room.id)
      byRoom.set(room.id, known ? { room, top: worse(known.top, incident), count: known.count + 1 } : { room, top: incident, count: 1 })
    }
    return [...byRoom.values()]
  }, [map, floor, incidents])
  return <>{rooms.map((entry) => <RoomAlarm key={entry.room.id} {...entry} selected={entry.top.id === selectedIncidentId} onSelect={onSelect} />)}</>
}
