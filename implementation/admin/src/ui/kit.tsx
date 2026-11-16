/** Small building blocks used by every page. */
import { useEffect, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { STATE_LABEL } from '../lib/format'
import type { DisplayState } from '../types'
import './kit.css'

export function StateBadge({ state, size = 'm' }: { state: DisplayState; size?: 's' | 'm' }) {
  return (
    <span className={`state-badge state-${state} size-${size}`}>
      <i />
      {STATE_LABEL[state]}
    </span>
  )
}

type Tone = 'neutral' | 'mint' | 'amber' | 'coral' | 'blue' | 'pink' | 'slate'

export function Chip({ tone = 'neutral', children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return <span className={`chip chip-${tone}`} title={title}>{children}</span>
}

export function Panel({ title, eyebrow, actions, children, className = '', flush = false }: { title?: ReactNode; eyebrow?: string; actions?: ReactNode; children: ReactNode; className?: string; flush?: boolean }) {
  return (
    <section className={`panel ${flush ? 'is-flush' : ''} ${className}`}>
      {(title || actions) && (
        <header className="panel-head">
          <div>
            {eyebrow && <p className="eyebrow">{eyebrow}</p>}
            {title && <h2>{title}</h2>}
          </div>
          {actions && <div className="panel-actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  )
}

export function Battery({ value, compact = false }: { value: number; compact?: boolean }) {
  const level = value < 25 ? 'low' : value < 50 ? 'mid' : 'ok'
  return (
    <span className={`battery battery-${level} ${compact ? 'is-compact' : ''}`} title={`Battery ${Math.round(value)}%`}>
      <span className="battery-track"><span style={{ width: `${Math.max(3, Math.min(100, value))}%` }} /></span>
      <b className="mono">{Math.round(value)}%</b>
    </span>
  )
}

export function Segmented<T extends string | number>({ value, options, onChange, label }: { value: T; options: Array<{ value: T; label: ReactNode; title?: string }>; onChange: (value: T) => void; label: string }) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button key={String(option.value)} type="button" role="radio" aria-checked={option.value === value} className={option.value === value ? 'is-on' : ''} onClick={() => onChange(option.value)} title={option.title}>
          {option.label}
        </button>
      ))}
    </div>
  )
}

export function Toggle({ on, onChange, children, title }: { on: boolean; onChange: (on: boolean) => void; children: ReactNode; title?: string }) {
  return (
    <button type="button" className={`toggle ${on ? 'is-on' : ''}`} aria-pressed={on} onClick={() => onChange(!on)} title={title}>
      {children}
    </button>
  )
}

export function Empty({ icon, title, children }: { icon?: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      {icon && <span className="empty-icon">{icon}</span>}
      <strong>{title}</strong>
      {children && <p>{children}</p>}
    </div>
  )
}

/** A count that rolls to its new value instead of jumping. */
export function Ticker({ value, format = (next: number) => String(Math.round(next)) }: { value: number; format?: (value: number) => string }) {
  const [shown, setShown] = useState(value)
  const from = useRef(value)
  useEffect(() => {
    const start = performance.now()
    const begin = from.current
    let frame = 0
    const tick = (now: number): void => {
      const t = Math.min(1, (now - start) / 600)
      const eased = 1 - (1 - t) ** 3
      const next = begin + (value - begin) * eased
      setShown(next)
      from.current = next
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [value])
  return <>{format(shown)}</>
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="kbd">{children}</kbd>
}

export function Dot({ color, pulse = false }: { color: string; pulse?: boolean }) {
  return <i className={`dot ${pulse ? 'is-pulse' : ''}`} style={{ '--dot': color } as CSSProperties} />
}
