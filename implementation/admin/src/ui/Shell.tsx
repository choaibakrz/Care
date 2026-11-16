/** The frame around every page: navigation, connection state, notices, footer. */
import { Component, useEffect, useState } from 'react'
import type { ErrorInfo, ReactNode } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { Activity, BellRing, Boxes, Building2, Layers, CalendarClock, CheckCircle2, ClipboardList, Hexagon, Info, LayoutDashboard, LogOut, Moon, MonitorPlay, ScrollText, Settings2, Siren, Sun, TriangleAlert, Unplug, WifiOff, X } from 'lucide-react'
import { BedDouble } from 'lucide-react'
import { BRAND } from '../lib/brand'
import { config } from '../lib/config'
import { ago, clockTime, placeName } from '../lib/format'
import { incidentTitle } from '../lib/incidents'
import { useStore } from '../state/store'
import { ConfirmHost } from './confirm'
import { Dot } from './kit'
import { LogoMark } from './Logo'
import './shell.css'

/** The current time, refreshed every second. Drives "5 s ago" and the stale check. */
export function useNow(): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])
  return now
}

const NAV = [
  { to: '/', label: 'Live map', icon: LayoutDashboard, end: true },
  { to: '/tasks', label: 'Tasks', icon: ClipboardList },
  { to: '/zones', label: 'Zones', icon: Hexagon },
  { to: '/clinics', label: 'Clinics', icon: Layers },
  { to: '/building', label: 'Building', icon: Building2 },
  { to: '/stock', label: 'Stock', icon: Boxes },
  { to: '/night', label: 'Night round', icon: CalendarClock },
  { to: '/incidents', label: 'Incidents', icon: TriangleAlert },
  { to: '/audit', label: 'Audit log', icon: ScrollText },
  { to: '/monitor', label: 'Monitor', icon: Activity },
  { to: '/patients', label: 'Patients & rooms', icon: BedDouble },
  { to: '/system', label: 'System', icon: Settings2 },
]

const TITLES: Record<string, [string, string]> = {
  '/': ['Live map', 'Where every robot is, what it does, and what it carries.'],
  '/tasks': ['Tasks', 'Every request, who asked, which robot, and what happened.'],
  '/zones': ['Zones', 'Places where robots stop listening, or should stay out.'],
  '/clinics': ['Clinics', 'Stored clinic plans: activate, copy, import and export.'],
  '/building': ['Building', 'Edit the active plan: rooms, walls and places.'],
  '/stock': ['Stock', 'Counts per shelf, low stock and what the robots counted.'],
  '/night': ['Night round', 'The automatic restock round: when, and how it went.'],
  '/audit': ['Audit log', 'Read only. Who did what, when, and the answer.'],
  '/incidents': ['Incidents', 'What is wrong, where, and who is on it. Patient alarms are handled in the emergency service.'],
  '/monitor': ['Monitor', 'Server health, traffic, attacks and blocks, and how the service is doing.'],
  '/patients': ['Patients & rooms', 'Assign a patient to a room, then pair the room tablet securely.'],
  '/system': ['System', 'Connections, the jury screen and the backup stop.'],
}

function Sidebar() {
  const session = useStore((state) => state.session)
  const signOut = useStore((state) => state.signOut)
  const openTasks = useStore((state) => state.tasks.filter((task) => ['requested', 'assigned', 'en_route'].includes(task.state)).length)
  const lowStock = useStore((state) => state.inventory.filter((item) => item.count <= item.lowAt).length)
  const openIncidents = useStore((state) => state.incidents.length)
  const critical = useStore((state) => state.incidents.some((incident) => incident.severity === 'critical'))
  const badges: Record<string, number> = { '/tasks': openTasks, '/stock': lowStock, '/incidents': openIncidents }
  return (
    <aside className="sidebar">
      <div className="sidebar-brand"><LogoMark size={32} /><div><strong>{BRAND.product}</strong><span>{BRAND.adminSubtitle}</span></div></div>
      <nav aria-label="Main">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => `nav-link ${isActive ? 'is-active' : ''}`}>
            <Icon size={17} strokeWidth={1.8} />
            <span>{label}</span>
            {badges[to] ? <b className={to === '/stock' ? 'is-warn' : to === '/incidents' && critical ? 'is-danger' : ''}>{badges[to]}</b> : null}
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-foot">
        {config.useMock && <p className="demo-flag"><MonitorPlay size={14} />Demo clinic · invented data</p>}
        <div className="operator">
          <span className="avatar">{session?.operator.slice(0, 1).toUpperCase()}</span>
          <div><strong>{session?.operator}</strong><span>Administrator</span></div>
          <button type="button" className="icon-button" onClick={signOut} aria-label="Sign out" title="Sign out"><LogOut size={16} /></button>
        </div>
      </div>
    </aside>
  )
}

function ConnectionPill() {
  const connection = useStore((state) => state.connection)
  const label = connection === 'live' ? 'Live' : connection === 'connecting' ? 'Connecting…' : 'Offline'
  const color = connection === 'live' ? 'var(--mint)' : connection === 'connecting' ? 'var(--amber)' : 'var(--coral)'
  return <span className={`conn conn-${connection}`} role="status"><Dot color={color} pulse={connection === 'live'} />{label}</span>
}

function Topbar() {
  const { pathname } = useLocation()
  const [title, subtitle] = TITLES[pathname] ?? TITLES['/']
  const theme = useStore((state) => state.theme)
  const setTheme = useStore((state) => state.setTheme)
  const demoMode = useStore((state) => state.demoMode)
  const setDemoMode = useStore((state) => state.setDemoMode)
  return (
    <header className="topbar">
      <div className="topbar-title">
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      <div className="topbar-tools">
        <ConnectionPill />
        {pathname === '/' && <button type="button" className={`toggle ${demoMode ? 'is-on' : ''}`} onClick={() => setDemoMode(!demoMode)} aria-pressed={demoMode} title="Big screen: hide side panels, larger labels"><MonitorPlay size={15} />Presenter</button>}
        <button type="button" className="icon-button is-boxed" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} aria-label="Switch theme" title="Switch theme">{theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}</button>
      </div>
    </header>
  )
}

function EmergencyBanner() {
  const mode = useStore((state) => state.mode)
  if (mode?.mode !== 'emergency') return null
  return (
    <div className="banner is-emergency" role="alert" data-testid="emergency-banner">
      <Siren size={18} />
      <div>
        <strong>Emergency mode{mode.since ? ` since ${clockTime(mode.since)}` : ''}{mode.by ? ` · ${mode.by}` : ''}.</strong> {BRAND.server} accepts only emergency actions; other changes are refused. Robots go to their docks. Patient alarms are not affected. Leave it with the switch top right.
      </div>
    </div>
  )
}

/**
 * Patient alarms mirrored from the emergency service, and a lost link to it: on every page,
 * because they matter more than anything else here. Read only: the emergency service handles them.
 */
function AlarmBanners() {
  const incidents = useStore((state) => state.incidents)
  const map = useStore((state) => state.map)
  const now = useNow()
  const alarms = incidents.filter((incident) => incident.code === 'emergency_alarm')
  const linkDown = incidents.some((incident) => incident.code === 'emergency_link_down')
  return (
    <>
      {alarms.map((alarm) => (
        <div key={alarm.id} className="banner is-alarm" role="alert" data-testid="alarm-banner">
          <BellRing size={18} />
          <div><strong>{incidentTitle(alarm)}{alarm.place ? ` · ${placeName(map, alarm.place)}` : ''}</strong> · {ago(alarm.openedAt, now)}{alarm.acknowledgedBy ? ` · ${alarm.acknowledgedBy} is on the way` : ' · nobody has answered yet'}. The emergency service pages the staff; this panel only shows it.</div>
        </div>
      ))}
      {linkDown && (
        <div className="banner is-danger" role="alert">
          <Unplug size={17} />
          <div><strong>No link to the emergency service.</strong> Patient alarms may not show on this map. The emergency service itself keeps paging the staff.</div>
        </div>
      )}
    </>
  )
}

function OfflineBanner() {
  const connection = useStore((state) => state.connection)
  const hasBeenLive = useStore((state) => state.hasBeenLive)
  const loadError = useStore((state) => state.loadError)
  if (connection === 'offline' || (connection === 'connecting' && hasBeenLive)) {
    return (
      <div className="banner is-danger" role="alert">
        <WifiOff size={17} />
        <div><strong>No connection to {BRAND.server}.</strong> Robots keep working on their own. Positions on screen are old and shown greyed out. Trying again…</div>
      </div>
    )
  }
  if (loadError) return <div className="banner is-warning" role="alert"><TriangleAlert size={17} /><div><strong>Some data did not load.</strong> {loadError}</div></div>
  return null
}

const TOAST_ICON = { info: Info, success: CheckCircle2, warning: TriangleAlert, danger: TriangleAlert }

function Toasts() {
  const toasts = useStore((state) => state.toasts)
  const dismiss = useStore((state) => state.dismissToast)
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((toast) => {
        const Icon = TOAST_ICON[toast.tone]
        return (
          <div key={toast.id} className={`toast is-${toast.tone}`}>
            <Icon size={16} />
            <p>{toast.message}</p>
            <button type="button" onClick={() => dismiss(toast.id)} aria-label="Dismiss"><X size={14} /></button>
          </div>
        )
      })}
    </div>
  )
}

/** A page that crashes shows a message; the navigation and the stop button stay. */
export class PageBoundary extends Component<{ children: ReactNode; resetKey: string }, { error: Error | null }> {
  state: { error: Error | null } = { error: null }

  static getDerivedStateFromError(error: Error): { error: Error } {
    return { error }
  }

  componentDidUpdate(previous: { resetKey: string }): void {
    if (previous.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null })
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Kept for the developer console only; nothing leaves the machine.
    console.error('Page crashed', error, info.componentStack)
  }

  render(): ReactNode {
    if (!this.state.error) return this.props.children
    return (
      <div className="page-crash">
        <TriangleAlert size={22} />
        <strong>This page stopped working.</strong>
        <p>{this.state.error.message}</p>
        <p>The emergency stop, top right, still works.</p>
        <button type="button" className="button" onClick={() => this.setState({ error: null })}>Try again</button>
      </div>
    )
  }
}

export function Shell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation()
  const demoMode = useStore((state) => state.demoMode)
  return (
    <div className={`shell ${demoMode && pathname === '/' ? 'is-presenting' : ''}`}>
      <Sidebar />
      <div className="main">
        <Topbar />
        <AlarmBanners />
        <EmergencyBanner />
        <OfflineBanner />
        <main className="page"><PageBoundary resetKey={pathname}>{children}</PageBoundary></main>
        <footer className="footer">{config.useMock ? 'Invented data, demonstration only · no patient data is shown' : 'Real room assignments · patient data stays in the admin console'} · this panel asks, each robot decides</footer>
      </div>
      <Toasts />
      <ConfirmHost />
    </div>
  )
}
