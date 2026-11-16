/**
 * The panel's memory: who is signed in, what the server last said, what the operator is looking at.
 * One live connection feeds it. Pages read from it and never talk to the socket themselves.
 */
import { create } from 'zustand'
import { setEstopContext } from '../estop/bridge'
import { backend } from '../lib/backend'
import { errorMessage, placeName } from '../lib/format'
import { connectLive } from '../lib/live'
import { incidentTitle } from '../lib/incidents'
import type { FleetHome, ClinicMap, ConnectionState, Incident, InventoryItem, LiveMessage, Robot, Schedule, SecurityAlert, Session, SystemMode, Tablet, TabletFix, Task, Zone } from '../types'
import { eventsFromHistory, eventsFromMessage } from './events'
import type { ActivityEvent, Tone } from './events'

export interface Toast {
  id: number
  tone: Tone
  message: string
}

export type Theme = 'dark' | 'light'
export type MapView = 'iso' | 'top'

interface AppState {
  session: Session | null
  connection: ConnectionState
  hasBeenLive: boolean
  loaded: boolean
  loadError: string | null
  map: ClinicMap | null
  /** Normal or emergency operation. Null when the server has no emergency mode (or did not answer yet). */
  mode: SystemMode | null
  robots: Robot[]
  /** Where robots go in an emergency, on "dock" and to recharge. Null until read. */
  fleetHome: FleetHome | null
  tablets: Tablet[]
  /** False when the server has no tablet registry: tablets are shown but cannot be freed or assigned. */
  tabletsManaged: boolean
  tasks: Task[]
  /** Open incidents. A closed one leaves this list (the Incidents page asks for closed ones itself). */
  incidents: Incident[]
  /** The latest security alerts from the live stream, newest first. */
  securityAlerts: SecurityAlert[]
  inventory: InventoryItem[]
  zones: Zone[]
  schedules: Schedule[]
  events: ActivityEvent[]
  toasts: Toast[]
  selectedRobotId: string | null
  selectedTabletId: string | null
  /** The incident picked on the map or in a list: highlighted in both. */
  selectedIncidentId: string | null
  /** Which list the side panel shows. */
  fleetTab: 'robots' | 'tablets'
  showTablets: boolean
  floor: number
  theme: Theme
  demoMode: boolean
  showHeat: boolean
  showZones: boolean
  exploded: boolean
  view: MapView

  signIn: (session: Session) => void
  signOut: () => void
  loadAll: () => Promise<void>
  selectRobot: (robotId: string) => void
  selectTablet: (tabletId: string) => void
  selectIncident: (incidentId: string | null) => void
  setFleetTab: (tab: 'robots' | 'tablets') => void
  setShowTablets: (on: boolean) => void
  upsertTablet: (tablet: Tablet) => void
  /** Applies an incident the server sent back; null means "read the list again". */
  applyIncident: (incident: Incident | null) => void
  setFloor: (floor: number) => void
  setTheme: (theme: Theme) => void
  setDemoMode: (on: boolean) => void
  setShowHeat: (on: boolean) => void
  setShowZones: (on: boolean) => void
  setExploded: (on: boolean) => void
  setView: (view: MapView) => void
  toast: (tone: Tone, message: string) => void
  dismissToast: (id: number) => void
  upsertTask: (task: Task) => void
  upsertRobot: (robot: Robot) => void
  setFleetHome: (home: FleetHome) => void
  upsertItem: (item: InventoryItem) => void
  upsertZone: (zone: Zone) => void
  removeZone: (zoneId: string) => void
  upsertSchedule: (schedule: Schedule) => void
}

const THEME_KEY = 'clinic-pilot-theme'
const MAX_EVENTS = 40
const MAX_SECURITY_ALERTS = 30
const MAX_TOASTS = 4
const TOAST_MS = 6500

function savedTheme(): Theme {
  try {
    return window.localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

function upsert<T extends { id: string }>(items: T[], next: T, prepend = false): T[] {
  if (items.some((item) => item.id === next.id)) return items.map((item) => item.id === next.id ? next : item)
  return prepend ? [next, ...items] : [...items, next]
}

/** The floor a tablet is on: from its position, or from its place. */
export function tabletFloor(tablet: Tablet, map: ClinicMap | null): number | null {
  if (tablet.position) return tablet.position.floor
  return map?.places.find((place) => place.id === tablet.place)?.floor ?? null
}

/**
 * Applies the tablets part of `positions.delta`. A tablet that leaves the live view is offline when
 * the registry knows it, and simply gone when there is no registry.
 */
function moveTablets(tablets: Tablet[], fixes: TabletFix[], removed: string[], managed: boolean): Tablet[] {
  const byId = new Map(fixes.map((fix) => [fix.id, fix]))
  const next = tablets
    .filter((tablet) => managed || !removed.includes(tablet.id))
    .map((tablet) => {
      if (removed.includes(tablet.id)) return { ...tablet, online: false }
      const fix = byId.get(tablet.id)
      if (!fix) return tablet
      byId.delete(tablet.id)
      return { ...tablet, online: true, place: fix.place ?? tablet.place, position: fix.position ?? tablet.position, uncertainty: fix.uncertainty, label: fix.label ?? tablet.label }
    })
  // Without a registry, a tablet seen for the first time joins the list as it is.
  if (!managed) for (const fix of byId.values()) next.push({ id: fix.id, kind: 'staff', label: fix.label ?? '', speciality: null, battery: null, online: true, assigned: true, place: fix.place, position: fix.position, uncertainty: fix.uncertainty, lastSeen: null })
  return next
}

let closeLive: (() => void) | null = null
let toastCount = 0

/** Why a change is refused while the clinic is in emergency mode. Shown as the button's tooltip. */
export const EMERGENCY_LOCKED = 'Emergency mode: only emergency actions are accepted.'

export const useStore = create<AppState>((set, get) => {
  const applyLive = (message: LiveMessage): void => {
    const state = get()
    const events = eventsFromMessage(message, state.robots, state.map)
    const withEvents = events.length ? { events: [...events, ...state.events].slice(0, MAX_EVENTS) } : {}
    if (message.type === 'map.updated') {
      // Only the active plan is on screen; a newer version of it means the building changed.
      const shown = state.map
      const sameVersion = shown?.clinicId === message.clinicId && shown.version === message.version
      if (message.active && !sameVersion) void reloadMap(message.clinicId !== shown?.clinicId)
      return
    }
    if (message.type === 'incident.updated') {
      const known = state.incidents.some((entry) => entry.id === message.incident.id)
      get().applyIncident(message.incident)
      // A new patient alarm or critical incident is announced at once, on every page.
      if (!known && !message.incident.closedAt && message.incident.severity === 'critical') get().toast('danger', `${incidentTitle(message.incident)}${message.incident.place ? ` · ${placeName(state.map, message.incident.place)}` : ''}`)
      return
    }
    if (message.type === 'security.alert') {
      set({ securityAlerts: [message.alert, ...state.securityAlerts].slice(0, MAX_SECURITY_ALERTS) })
      if (message.alert.kind === 'auto_blocked' || message.alert.kind === 'login_burst') get().toast('warning', message.alert.message)
      return
    }
    if (message.type === 'device.updated') {
      set({ tablets: upsert(state.tablets, message.tablet) })
      return
    }
    if (message.type === 'positions.delta') {
      set({ tablets: moveTablets(state.tablets, message.tablets, message.removedTablets, state.tabletsManaged) })
      return
    }
    if (message.type === 'mode.updated') {
      setEstopContext({ mode: message.mode })
      set({ mode: message.mode })
      return
    }
    if (message.type === 'resync') {
      // The server could not keep up with this panel and dropped events: start again from its state.
      void get().loadAll()
      return
    }
    if (message.type === 'robot.updated') {
      const known = state.robots.some((robot) => robot.id === message.robot.id)
      const robots = upsert(state.robots, message.robot)
      if (!known) setEstopContext({ robotIds: robots.map((robot) => robot.id) })
      set({ robots, ...withEvents })
    } else if (message.type === 'task.updated') set({ tasks: upsert(state.tasks, message.task, true), ...withEvents })
    else if (message.type === 'inventory.updated') set({ inventory: upsert(state.inventory, message.item), ...withEvents })
    else if (message.type === 'zone.updated') set({ zones: upsert(state.zones, message.zone), ...withEvents })
    else if (message.type === 'zone.deleted') set({ zones: state.zones.filter((zone) => zone.id !== message.zoneId), ...withEvents })
    else if (message.type === 'schedule.updated') set({ schedules: upsert(state.schedules, message.schedule), ...withEvents })
    else {
      set(withEvents)
      // Stops already have their own report next to the stop button: no second notice.
      const coveredByStopReport = /emergency stop/i.test(message.message)
      if (message.level !== 'info' && !coveredByStopReport) get().toast(message.level === 'critical' ? 'danger' : 'warning', message.message)
    }
  }

  let mapRequest = 0
  /** Fetches the active plan again and redraws it, without touching anything else on screen. */
  const reloadMap = async (otherClinic: boolean): Promise<void> => {
    const token = get().session?.token
    if (!token) return
    mapRequest += 1
    const request = mapRequest
    try {
      const map = await backend.getMap(token)
      // A newer reload or a sign-out happened meanwhile: this answer is out of date.
      if (request !== mapRequest || get().session?.token !== token) return
      const floors = map.floors.map((floor) => floor.id)
      const state = get()
      set({ map, floor: floors.includes(state.floor) ? state.floor : floors[0] ?? 0 })
      get().toast('info', otherClinic ? `Another clinic plan is now active: ${map.clinicId ?? 'unknown'}. The map was redrawn.` : 'The clinic plan changed. The map was redrawn.')
    } catch (reason) {
      if (request === mapRequest && get().session?.token === token) get().toast('warning', `The clinic plan changed, but the new map could not be loaded: ${errorMessage(reason)}`)
    }
  }

  const applyStatus = (status: ConnectionState): void => {
    const previous = get().connection
    set({ connection: status, hasBeenLive: get().hasBeenLive || status === 'live' })
    if (status !== 'live' || previous === 'live') return
    const reconnected = get().hasBeenLive && previous === 'offline'
    void get().loadAll().then(() => { if (reconnected && !get().loadError) get().toast('success', 'Connection restored. Data is up to date again.') })
  }

  return {
    session: null,
    connection: 'connecting',
    hasBeenLive: false,
    loaded: false,
    loadError: null,
    map: null,
    mode: null,
    robots: [],
    fleetHome: null,
    tablets: [],
    tabletsManaged: false,
    incidents: [],
    securityAlerts: [],
    tasks: [],
    inventory: [],
    zones: [],
    schedules: [],
    events: [],
    toasts: [],
    selectedRobotId: null,
    selectedTabletId: null,
    selectedIncidentId: null,
    fleetTab: 'robots',
    showTablets: true,
    floor: 0,
    theme: savedTheme(),
    demoMode: false,
    showHeat: false,
    showZones: true,
    exploded: false,
    view: 'iso',

    signIn: (session) => {
      closeLive?.()
      set({ session, loaded: false, loadError: null, connection: 'connecting', hasBeenLive: false })
      setEstopContext({ token: session.token })
      void get().loadAll()
      closeLive = connectLive(session.token, { onMessage: applyLive, onStatus: applyStatus })
    },

    signOut: () => {
      closeLive?.()
      closeLive = null
      setEstopContext({ token: null, robotIds: [] })
      set({ session: null, loaded: false, robots: [], tasks: [], inventory: [], zones: [], schedules: [], events: [], toasts: [], map: null, mode: null, fleetHome: null, tablets: [], tabletsManaged: false, incidents: [], securityAlerts: [], selectedRobotId: null, selectedTabletId: null, fleetTab: 'robots', demoMode: false })
    },

    loadAll: async () => {
      const token = get().session?.token
      if (!token) return
      // Tablets too: a server without them must not stop the rest loading.
      backend.getTablets(token).then(({ tablets, managed }) => {
        if (get().session?.token === token) set({ tablets, tabletsManaged: managed })
      }, () => { /* Shown as "no tablet" until the live stream brings some. */ })
      backend.getFleetHome(token).then((fleetHome) => {
        if (get().session?.token === token) set({ fleetHome })
      }, () => { /* No home place shown: the selector says it could not be read. */ })
      // The mode is read on its own: a server without emergency mode must not stop the rest loading.
      backend.getMode(token).then((mode) => {
        if (get().session?.token !== token) return
        set({ mode })
        if (mode) setEstopContext({ mode })
      }, () => { /* The switch keeps asking on its own; the banner waits for the live stream. */ })
      // Each part is shown as soon as it arrives: the map does not wait for the stock, nor the
      // robots for the audit. The selection and the activity feed settle once what they need is in.
      const current = (): boolean => get().session?.token === token
      const arrived = { map: false, robots: false, tasks: false }
      const done = { placed: false, feed: false }
      const settle = (): void => {
        const state = get()
        if (!state.map) return
        // Once per load: a floor the operator picks meanwhile is never taken back.
        if (!done.placed && arrived.map && arrived.robots) {
          done.placed = true
          const floors = state.map.floors.map((floor) => floor.id)
          const selected = state.robots.find((robot) => robot.id === state.selectedRobotId) ?? state.robots.find((robot) => robot.state === 'busy') ?? state.robots[0]
          set({ selectedRobotId: selected?.id ?? null, floor: state.loaded && floors.includes(state.floor) ? state.floor : selected?.position.floor ?? floors[0] ?? 0 })
        }
        if (!done.feed && arrived.map && arrived.tasks) {
          done.feed = true
          if (!state.events.length) set({ events: eventsFromHistory(state.tasks, state.map) })
        }
      }
      const part = <T,>(load: Promise<T>, apply: (value: T) => void): Promise<void> => load.then((value) => { if (current()) { apply(value); settle() } })
      const results = await Promise.allSettled([
        part(backend.getRobots(token), (robots) => { arrived.robots = true; setEstopContext({ robotIds: robots.map((robot) => robot.id) }); set({ robots }) }),
        part(backend.getMap(token), (map) => { arrived.map = true; set({ map }) }),
        part(backend.getTasks(token), (tasks) => { arrived.tasks = true; set({ tasks }) }),
        part(backend.getInventory(token), (inventory) => set({ inventory })),
        part(backend.getZones(token), (zones) => set({ zones })),
        part(backend.getSchedules(token), (schedules) => set({ schedules })),
        part(backend.getIncidents(token, false), (incidents) => set({ incidents: incidents.filter((incident) => !incident.closedAt) })),
      ])
      if (!current()) return
      const failed = results.find((result): result is PromiseRejectedResult => result.status === 'rejected')
      set({ loaded: true, loadError: failed ? errorMessage(failed.reason) : null })
      settle()
    },

    selectRobot: (robotId) => {
      const robot = get().robots.find((entry) => entry.id === robotId)
      set({ selectedRobotId: robotId, fleetTab: 'robots', ...(robot && !get().exploded ? { floor: robot.position.floor } : {}) })
    },
    selectTablet: (tabletId) => {
      const tablet = get().tablets.find((entry) => entry.id === tabletId)
      const floor = tablet ? tabletFloor(tablet, get().map) : null
      set({ selectedTabletId: tabletId, fleetTab: 'tablets', ...(floor !== null && !get().exploded ? { floor } : {}) })
    },
    selectIncident: (incidentId) => {
      const incident = get().incidents.find((entry) => entry.id === incidentId)
      const floor = incident?.floor ?? (incident?.place ? get().map?.places.find((place) => place.id === incident.place)?.floor : undefined)
      set({ selectedIncidentId: incidentId, ...(typeof floor === 'number' && !get().exploded ? { floor } : {}) })
    },
    setFleetTab: (fleetTab) => set({ fleetTab }),
    setShowTablets: (showTablets) => set({ showTablets }),
    upsertTablet: (tablet) => set({ tablets: upsert(get().tablets, tablet) }),
    applyIncident: (incident) => {
      if (!incident) {
        const token = get().session?.token
        if (token) backend.getIncidents(token, false).then((incidents) => { if (get().session?.token === token) set({ incidents: incidents.filter((entry) => !entry.closedAt) }) }, () => undefined)
        return
      }
      const others = get().incidents.filter((entry) => entry.id !== incident.id)
      set({ incidents: incident.closedAt ? others : [...others, incident] })
    },
    setFloor: (floor) => set({ floor }),
    setTheme: (theme) => {
      try { window.localStorage.setItem(THEME_KEY, theme) } catch { /* Private mode: the choice lasts for this visit only. */ }
      set({ theme })
    },
    setDemoMode: (demoMode) => set({ demoMode }),
    setShowHeat: (showHeat) => set({ showHeat }),
    setShowZones: (showZones) => set({ showZones }),
    setExploded: (exploded) => set({ exploded }),
    setView: (view) => set({ view }),

    toast: (tone, message) => {
      toastCount += 1
      const id = toastCount
      set({ toasts: [...get().toasts.filter((entry) => entry.message !== message), { id, tone, message }].slice(-MAX_TOASTS) })
      window.setTimeout(() => get().dismissToast(id), tone === 'danger' ? TOAST_MS * 2 : TOAST_MS)
    },
    dismissToast: (id) => set({ toasts: get().toasts.filter((entry) => entry.id !== id) }),

    upsertTask: (task) => set({ tasks: upsert(get().tasks, task, true) }),
    upsertRobot: (robot) => set({ robots: upsert(get().robots, robot) }),
    setFleetHome: (fleetHome) => set({ fleetHome }),
    upsertItem: (item) => set({ inventory: upsert(get().inventory, item) }),
    upsertZone: (zone) => set({ zones: upsert(get().zones, zone) }),
    removeZone: (zoneId) => set({ zones: get().zones.filter((zone) => zone.id !== zoneId) }),
    upsertSchedule: (schedule) => set({ schedules: upsert(get().schedules, schedule) }),
  }
})

/** True while the server runs in emergency mode: changes that are not about the emergency are refused. */
export function useEmergency(): boolean {
  return useStore((state) => state.mode?.mode === 'emergency')
}
