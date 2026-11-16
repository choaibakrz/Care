/**
 * The Monitor page's two chart forms, in plain SVG and HTML (no chart library):
 * a line chart over time with a crosshair and tooltip, and a horizontal bar list.
 * Colours come from `--series-*` in monitor.css (validated palette, light and dark).
 */
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent } from 'react'

export interface Series {
  key: string
  label: string
  /** A CSS colour, normally `var(--series-1)`. */
  color: string
  values: number[]
}

const HEIGHT = 220
const MARGIN = { top: 14, right: 104, bottom: 26, left: 44 }
const LABEL_GAP = 15

function niceCeil(value: number): number {
  if (value <= 0) return 1
  const power = 10 ** Math.floor(Math.log10(value))
  const step = [1, 2, 2.5, 5, 10].find((candidate) => candidate * power >= value) ?? 10
  return step * power
}

function useWidth(): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(600)
  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return undefined
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(280, Math.round(entry.contentRect.width))))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  return [ref, width]
}

function formatRate(value: number): string {
  return value >= 100 ? String(Math.round(value)) : value >= 10 ? value.toFixed(0) : value.toFixed(1).replace(/\.0$/, '')
}

/** Requests per second over time. `times` are ISO strings, one per value. */
export function LineChart({ series, times, unit, title }: { series: Series[]; times: string[]; unit: string; title: string }) {
  const [ref, width] = useWidth()
  const [hover, setHover] = useState<number | null>(null)
  const count = times.length
  const plotWidth = width - MARGIN.left - MARGIN.right
  const plotHeight = HEIGHT - MARGIN.top - MARGIN.bottom
  const max = useMemo(() => niceCeil(Math.max(1, ...series.flatMap((entry) => entry.values))), [series])
  const x = (index: number): number => MARGIN.left + (count <= 1 ? 0 : (index / (count - 1)) * plotWidth)
  const y = (value: number): number => MARGIN.top + plotHeight - (value / max) * plotHeight
  const path = (values: number[]): string => values.map((value, index) => `${index ? 'L' : 'M'}${x(index).toFixed(1)},${y(value).toFixed(1)}`).join('')

  // Direct labels at the right end, pushed apart when they would touch.
  const ends = series.map((entry) => ({ entry, at: y(entry.values[count - 1] ?? 0) })).sort((a, b) => a.at - b.at)
  for (let index = 1; index < ends.length; index++) if (ends[index].at - ends[index - 1].at < LABEL_GAP) ends[index].at = ends[index - 1].at + LABEL_GAP

  const minutes = Math.floor(((count - 1) * 1) / 60)
  const ticks = Array.from({ length: minutes + 1 }, (_, minute) => count - 1 - minute * 60).filter((index) => index >= 0)

  const onMove = (event: ReactPointerEvent<SVGRectElement>): void => {
    const box = event.currentTarget.getBoundingClientRect()
    const share = (event.clientX - box.left) / box.width
    setHover(Math.max(0, Math.min(count - 1, Math.round(share * (count - 1)))))
  }

  const hoverTime = hover !== null ? new Date(times[hover]).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''
  const tooltipLeft = hover !== null ? Math.min(x(hover) + 12, width - 170) : 0

  return (
    <div className="viz" ref={ref}>
      <div className="viz-legend" aria-hidden="true">
        {series.map((entry) => <span key={entry.key}><i style={{ background: entry.color }} />{entry.label}</span>)}
      </div>
      <svg width={width} height={HEIGHT} role="img" aria-label={`${title}: ${series.map((entry) => `${entry.label} ${formatRate(entry.values[count - 1] ?? 0)} ${unit} now`).join(', ')}`}>
        {[0, max / 2, max].map((value) => (
          <g key={value}>
            <line className="viz-grid" x1={MARGIN.left} x2={MARGIN.left + plotWidth} y1={y(value)} y2={y(value)} />
            <text className="viz-axis" x={MARGIN.left - 8} y={y(value)} textAnchor="end" dominantBaseline="middle">{formatRate(value)}</text>
          </g>
        ))}
        {ticks.map((index) => (
          <text key={index} className="viz-axis" x={x(index)} y={HEIGHT - 6} textAnchor="middle">{index === count - 1 ? 'now' : `−${Math.round((count - 1 - index) / 60)} min`}</text>
        ))}
        {series.map((entry) => <path key={entry.key} d={path(entry.values)} fill="none" stroke={entry.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />)}
        {ends.map(({ entry, at }) => (
          <g key={entry.key}>
            <circle cx={x(count - 1)} cy={y(entry.values[count - 1] ?? 0)} r={4} fill={entry.color} className="viz-ring" />
            <text className="viz-direct" x={x(count - 1) + 10} y={at} dominantBaseline="middle">{entry.label} <tspan className="viz-direct-value">{formatRate(entry.values[count - 1] ?? 0)}</tspan></text>
          </g>
        ))}
        {hover !== null && (
          <g pointerEvents="none">
            <line className="viz-crosshair" x1={x(hover)} x2={x(hover)} y1={MARGIN.top} y2={MARGIN.top + plotHeight} />
            {series.map((entry) => <circle key={entry.key} cx={x(hover)} cy={y(entry.values[hover] ?? 0)} r={4.5} fill={entry.color} className="viz-ring" />)}
          </g>
        )}
        <rect x={MARGIN.left} y={MARGIN.top} width={plotWidth} height={plotHeight} fill="transparent" onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
      </svg>
      {hover !== null && (
        <div className="viz-tooltip" style={{ left: tooltipLeft, top: MARGIN.top + 26 }} role="status">
          <b>{hoverTime}</b>
          {series.map((entry) => <span key={entry.key}><i style={{ background: entry.color }} />{entry.label}<em>{formatRate(entry.values[hover] ?? 0)} {unit}</em></span>)}
        </div>
      )}
      <details className="viz-table">
        <summary>Show as a table (last 30 s)</summary>
        <table>
          <thead><tr><th>Time</th>{series.map((entry) => <th key={entry.key}>{entry.label} ({unit})</th>)}</tr></thead>
          <tbody>
            {times.slice(-30).map((time, offset) => {
              const index = count - Math.min(30, count) + offset
              return <tr key={time}><td>{new Date(time).toLocaleTimeString()}</td>{series.map((entry) => <td key={entry.key}>{formatRate(entry.values[index] ?? 0)}</td>)}</tr>
            })}
          </tbody>
        </table>
      </details>
    </div>
  )
}

/** Horizontal bars, one hue, value at the end of each bar. */
export function BarList({ rows, unit = '', empty }: { rows: Array<{ key: string; label: string; value: number; note?: string }>; unit?: string; empty: string }) {
  const max = Math.max(1, ...rows.map((row) => row.value))
  if (!rows.length || rows.every((row) => row.value === 0)) return <p className="viz-empty">{empty}</p>
  return (
    <ul className="bar-list">
      {rows.map((row) => (
        <li key={row.key} title={`${row.label}: ${row.value}${unit}${row.note ? ` · ${row.note}` : ''}`}>
          <span className="bar-label">{row.label}</span>
          <span className="bar-track"><span className="bar-fill" style={{ width: `${row.value > 0 ? Math.max(2, (row.value / max) * 100) : 0}%` }} /></span>
          <b className="bar-value mono">{row.value}{unit}</b>
        </li>
      ))}
    </ul>
  )
}
