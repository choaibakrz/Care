/** Top-down plan of one floor of a draft clinic: rooms, walls and places you can draw, select and drag. */
import { useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import { boundsOf, centroid, roundTo } from '../../lib/geometry'
import type { ClinicPlan, Point } from '../../types'

const SNAP = 0.1
const MARGIN = 0.8

export type Tool = 'select' | 'room' | 'wall' | 'place' | 'prop' | 'floor'
export type Selection = { kind: 'room' | 'wall' | 'place' | 'prop' | 'floor'; index: number } | null
type Drag = { kind: 'corner'; index: number } | { kind: 'place' } | { kind: 'prop' } | null

interface Props {
  plan: ClinicPlan
  floor: number
  tool: Tool
  selection: Selection
  pending: Point[]
  /** Shapes the server refused, as `rooms:2`, `walls:0`, `places:5`. */
  bad: Set<string>
  onSelect: (selection: Selection) => void
  onPoints: (kind: 'room' | 'wall' | 'floor', index: number, points: Point[]) => void
  onMovePlace: (index: number, at: Point) => void
  onMoveProp: (index: number, at: Point) => void
  onAddPoint: (at: Point) => void
  onFinish: () => void
}

export function BuildingPlan({ plan, floor, tool, selection, pending, bad, onSelect, onPoints, onMovePlace, onMoveProp, onAddPoint, onFinish }: Props) {
  const svg = useRef<SVGSVGElement>(null)
  const [drag, setDrag] = useState<Drag>(null)
  const outline = plan.floors.find((entry) => entry.id === floor)?.outline ?? []
  const floorIndex = plan.floors.findIndex((entry) => entry.id === floor)
  const bounds = boundsOf(outline.length ? outline : [[0, 0], [24, 14]])
  const drawing = tool !== 'select'

  const at = (event: ReactPointerEvent): Point => {
    const matrix = svg.current?.getScreenCTM()
    if (!svg.current || !matrix) return [0, 0]
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse())
    return [roundTo(Math.max(bounds.minX, Math.min(bounds.maxX, point.x)), SNAP), roundTo(Math.max(bounds.minY, Math.min(bounds.maxY, point.y)), SNAP)]
  }

  const shape = selection?.kind === 'room' ? plan.rooms[selection.index]?.polygon : selection?.kind === 'wall' ? plan.walls[selection.index]?.points : selection?.kind === 'floor' ? plan.floors[selection.index]?.outline : undefined
  const minPoints = selection?.kind === 'wall' ? 2 : 3
  const setShape = (points: Point[]): void => { if (selection && (selection.kind === 'room' || selection.kind === 'wall' || selection.kind === 'floor')) onPoints(selection.kind, selection.index, points) }

  const move = (event: ReactPointerEvent): void => {
    if (!drag || !selection) return
    const point = at(event)
    if (drag.kind === 'corner' && shape) setShape(shape.map((corner, index) => index === drag.index ? point : corner))
    if (drag.kind === 'place') onMovePlace(selection.index, point)
    if (drag.kind === 'prop') onMoveProp(selection.index, point)
  }

  const start = (event: ReactPointerEvent, next: Drag): void => {
    event.stopPropagation()
    svg.current?.setPointerCapture(event.pointerId)
    setDrag(next)
  }

  const path = (points: Point[]): string => points.map((point) => point.join(',')).join(' ')
  const here = (entry: { floor: number }): boolean => entry.floor === floor

  return (
    <svg ref={svg} className={`plan ${drawing ? 'is-drawing' : ''}`} viewBox={`${bounds.minX - MARGIN} ${bounds.minY - MARGIN} ${bounds.width + MARGIN * 2} ${bounds.depth + MARGIN * 2}`}
      onPointerMove={move} onPointerUp={() => setDrag(null)}
      onPointerDown={(event) => { if (drawing) onAddPoint(at(event)); else onSelect(null) }} data-testid="building-plan">
      <polygon className={`plan-slab ${selection?.kind === 'floor' && selection.index === floorIndex ? 'is-selected' : ''} ${bad.has(`floors:${floorIndex}`) ? 'is-bad' : ''}`} points={path(outline)}
        onPointerDown={(event) => { if (!drawing && floorIndex >= 0) { event.stopPropagation(); onSelect({ kind: 'floor', index: floorIndex }) } }} />
      {plan.rooms.map((room, index) => here(room) && (
        <g key={`${room.id}-${index}`}>
          <polygon className={`plan-room kind-${room.kind} ${selection?.kind === 'room' && selection.index === index ? 'is-selected' : ''} ${bad.has(`rooms:${index}`) ? 'is-bad' : ''}`} points={path(room.polygon)}
            onPointerDown={(event) => { if (!drawing) { event.stopPropagation(); onSelect({ kind: 'room', index }) } }} />
          <text className="plan-label" x={(room.label_at ?? centroid(room.polygon))[0]} y={(room.label_at ?? centroid(room.polygon))[1]}>{room.label}</text>
        </g>
      ))}
      {plan.props.map((prop, index) => here(prop) && (
        <rect key={`${prop.id}-${index}`} className={`plan-prop building-prop ${selection?.kind === 'prop' && selection.index === index ? 'is-selected' : ''} ${bad.has(`props:${index}`) ? 'is-bad' : ''}`}
          x={prop.x - prop.width / 2} y={prop.y - prop.depth / 2} width={prop.width} height={prop.depth}
          onPointerDown={(event) => { if (drawing) return; onSelect({ kind: 'prop', index }); start(event, { kind: 'prop' }) }}><title>{prop.kind}{prop.solid ? ' (solid)' : ''}</title></rect>
      ))}
      {plan.walls.map((wall, index) => here(wall) && (
        <g key={`${wall.id}-${index}`}>
          <polyline className={`plan-wall ${selection?.kind === 'wall' && selection.index === index ? 'is-selected' : ''} ${bad.has(`walls:${index}`) ? 'is-bad' : ''}`} points={path(wall.points)} />
          <polyline className="plan-wall-hit" points={path(wall.points)} onPointerDown={(event) => { if (!drawing) { event.stopPropagation(); onSelect({ kind: 'wall', index }) } }} />
        </g>
      ))}
      {plan.places.map((place, index) => here(place) && (
        <circle key={`${place.id}-${index}`} className={`plan-place ${selection?.kind === 'place' && selection.index === index ? 'is-selected' : ''} ${bad.has(`places:${index}`) ? 'is-bad' : ''}`} cx={place.x} cy={place.y} r={0.28}
          onPointerDown={(event) => { if (drawing) return; onSelect({ kind: 'place', index }); start(event, { kind: 'place' }) }}><title>{place.label} ({place.kind})</title></circle>
      ))}

      {shape && !drawing && (
        <g style={{ color: 'var(--mint)' }}>
          {shape.map((point, index) => {
            if (index === shape.length - 1 && selection?.kind === 'wall') return null
            const next = shape[(index + 1) % shape.length]
            const middle: Point = [roundTo((point[0] + next[0]) / 2, SNAP), roundTo((point[1] + next[1]) / 2, SNAP)]
            return <circle key={`mid-${index}`} className="plan-mid" cx={middle[0]} cy={middle[1]} r={0.2} onPointerDown={(event) => { event.stopPropagation(); setShape([...shape.slice(0, index + 1), middle, ...shape.slice(index + 1)]) }}><title>Add a corner here</title></circle>
          })}
          {shape.map((point, index) => (
            <circle key={`corner-${index}`} className="plan-corner" cx={point[0]} cy={point[1]} r={0.3}
              onPointerDown={(event) => start(event, { kind: 'corner', index })}
              onDoubleClick={() => { if (shape.length > minPoints) setShape(shape.filter((_, position) => position !== index)) }}>
              <title>Drag to move · double-click to remove</title>
            </circle>
          ))}
        </g>
      )}

      {pending.length > 0 && (
        <g style={{ color: 'var(--amber)' }}>
          <polyline className="plan-zone is-open" points={path(pending)} />
          {pending.map((point, index) => (
            <circle key={index} className="plan-corner" cx={point[0]} cy={point[1]} r={0.3}
              onPointerDown={(event) => { if ((tool === 'room' || tool === 'floor') && index === 0 && pending.length >= 3) { event.stopPropagation(); onFinish() } }}>
              <title>{(tool === 'room' || tool === 'floor') && index === 0 ? 'Click to close the shape' : ''}</title>
            </circle>
          ))}
        </g>
      )}
    </svg>
  )
}
