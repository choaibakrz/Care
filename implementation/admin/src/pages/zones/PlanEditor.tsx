/**
 * Top-down plan of one floor, with one zone you can edit: drag a corner, drag the whole
 * shape, click a "+" on an edge to add a corner, double-click a corner to remove it.
 * While drawing a new zone, each click adds a corner.
 */
import { useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'
import { boundsOf, centroid, roundTo } from '../../lib/geometry'
import { STATE_COLOR, ZONE_COLOR } from '../../scene/palette'
import type { ClinicMap, DisplayState, Point, Robot, Zone } from '../../types'

const SNAP = 0.1
const MARGIN = 0.8

type Drag = { kind: 'corner'; index: number } | { kind: 'body'; last: Point } | null

interface PlanEditorProps {
  map: ClinicMap
  floor: number
  zone: Zone | null
  others: Zone[]
  robots: Array<{ robot: Robot; state: DisplayState }>
  drawing: boolean
  onChange: (polygon: Point[]) => void
  onFinishDrawing: () => void
}

export function PlanEditor({ map, floor, zone, others, robots, drawing, onChange, onFinishDrawing }: PlanEditorProps) {
  const svg = useRef<SVGSVGElement>(null)
  const [drag, setDrag] = useState<Drag>(null)
  const outline = map.floors.find((entry) => entry.id === floor)?.outline ?? []
  const bounds = boundsOf(outline.length ? outline : [[0, 0], [24, 14]])
  const polygon = zone?.polygon ?? []
  const color = zone ? ZONE_COLOR[zone.kind] : ZONE_COLOR.deaf

  const toMap = (event: ReactPointerEvent): Point => {
    const matrix = svg.current?.getScreenCTM()
    if (!svg.current || !matrix) return [0, 0]
    const point = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse())
    return [roundTo(Math.max(bounds.minX, Math.min(bounds.maxX, point.x)), SNAP), roundTo(Math.max(bounds.minY, Math.min(bounds.maxY, point.y)), SNAP)]
  }

  const handleMove = (event: ReactPointerEvent): void => {
    if (!drag) return
    const at = toMap(event)
    if (drag.kind === 'corner') { onChange(polygon.map((point, index) => index === drag.index ? at : point)); return }
    const dx = at[0] - drag.last[0]
    const dy = at[1] - drag.last[1]
    if (!dx && !dy) return
    const fits = polygon.every(([x, y]) => x + dx >= bounds.minX && x + dx <= bounds.maxX && y + dy >= bounds.minY && y + dy <= bounds.maxY)
    if (fits) onChange(polygon.map(([x, y]): Point => [roundTo(x + dx, SNAP), roundTo(y + dy, SNAP)]))
    setDrag({ kind: 'body', last: at })
  }

  const handleBackgroundClick = (event: ReactPointerEvent): void => {
    if (drawing && zone) onChange([...polygon, toMap(event)])
  }

  const startDrag = (event: ReactPointerEvent, next: Drag): void => {
    event.stopPropagation()
    if (drawing) return
    svg.current?.setPointerCapture(event.pointerId)
    setDrag(next)
  }

  const insertAfter = (index: number): void => {
    const a = polygon[index]
    const b = polygon[(index + 1) % polygon.length]
    const middle: Point = [roundTo((a[0] + b[0]) / 2, SNAP), roundTo((a[1] + b[1]) / 2, SNAP)]
    onChange([...polygon.slice(0, index + 1), middle, ...polygon.slice(index + 1)])
  }

  const path = (points: Point[]): string => points.map((point) => point.join(',')).join(' ')

  return (
    <svg ref={svg} className={`plan ${drawing ? 'is-drawing' : ''}`} viewBox={`${bounds.minX - MARGIN} ${bounds.minY - MARGIN} ${bounds.width + MARGIN * 2} ${bounds.depth + MARGIN * 2}`} onPointerMove={handleMove} onPointerUp={() => setDrag(null)} onPointerDown={handleBackgroundClick} data-testid="plan-editor">
      <polygon className="plan-slab" points={path(outline)} />
      {map.rooms.filter((room) => room.floor === floor).map((room) => {
        const [x, y] = room.labelAt ?? centroid(room.polygon)
        return (
          <g key={room.id}>
            <polygon className={`plan-room kind-${room.kind}`} points={path(room.polygon)} />
            <text className="plan-label" x={x} y={y}>{room.label}</text>
          </g>
        )
      })}
      {map.props.filter((prop) => prop.floor === floor && prop.solid).map((prop) => <rect key={prop.id} className="plan-prop" x={prop.x - prop.width / 2} y={prop.y - prop.depth / 2} width={prop.width} height={prop.depth} rx={0.08} />)}
      {map.walls.filter((wall) => wall.floor === floor).map((wall, index) => <polyline key={index} className="plan-wall" points={path(wall.points)} />)}
      {others.map((other) => <polygon key={other.id} className="plan-zone-other" points={path(other.polygon)} style={{ stroke: ZONE_COLOR[other.kind], fill: ZONE_COLOR[other.kind] }} />)}

      {zone && polygon.length > 0 && (
        <g style={{ color }}>
          {polygon.length >= 3 || !drawing
            ? <polygon className="plan-zone" points={path(polygon)} strokeDasharray={zone.kind === 'restricted' ? '0.3 0.2' : undefined} onPointerDown={(event) => startDrag(event, { kind: 'body', last: toMap(event) })} />
            : <polyline className="plan-zone is-open" points={path(polygon)} />}
          {!drawing && polygon.map((point, index) => {
            const next = polygon[(index + 1) % polygon.length]
            return <circle key={`mid-${index}`} className="plan-mid" cx={(point[0] + next[0]) / 2} cy={(point[1] + next[1]) / 2} r={0.2} onPointerDown={(event) => { event.stopPropagation(); insertAfter(index) }}><title>Add a corner here</title></circle>
          })}
          {polygon.map((point, index) => (
            <circle key={`corner-${index}`} className="plan-corner" cx={point[0]} cy={point[1]} r={0.3}
              onPointerDown={(event) => { if (drawing && index === 0 && polygon.length >= 3) { event.stopPropagation(); onFinishDrawing() } else startDrag(event, { kind: 'corner', index }) }}
              onDoubleClick={() => { if (!drawing && polygon.length > 3) onChange(polygon.filter((_, position) => position !== index)) }}>
              <title>{drawing && index === 0 ? 'Click to close the zone' : 'Drag to move · double-click to remove'}</title>
            </circle>
          ))}
        </g>
      )}

      {robots.map(({ robot, state }) => (
        <g key={robot.id} className="plan-robot" style={{ color: STATE_COLOR[state] }} transform={`translate(${robot.position.x} ${robot.position.y})`}>
          <circle r={0.34} />
          <text y={-0.55}>{robot.id}{robot.micOpen ? '' : ' · mic off'}</text>
        </g>
      ))}
    </svg>
  )
}
