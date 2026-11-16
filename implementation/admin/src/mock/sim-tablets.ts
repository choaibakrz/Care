/**
 * The demo clinic's tablets: staff tablets that follow their owner from room to room, bedside
 * tablets that stay with a bed, and free tablets waiting on the shelf of the nurse station.
 * Labels are invented pseudonyms. There is no patient name and no health information here.
 */
import type { Tablet, TabletAssignment } from '../types'
import type { SimState } from './sim-state'
import { raise } from './sim-incidents'
import { audit, emit, iso, placeById } from './sim-state'

export interface SimTablet {
  tablet: Tablet
  /** Staff only: the places its owner walks between. */
  rounds: string[]
  nextMoveIn: number
  /** Incidents already raised for the current low battery / offline spell (raised once, not every tick). */
  lowRaised: boolean
  offlineRaised: boolean
}

/** Where free tablets wait, per floor. */
const SHELF: Record<number, string> = { 0: 'reception', 2: 'nurse-station' }
const DRAIN_PER_SECOND = 0.012
const CHARGE_PER_SECOND = 0.08
const MOVE_MIN_SECONDS = 18
const MOVE_SPREAD_SECONDS = 25
const BATTERY_REPORT_SECONDS = 10
const MAX_LABEL = 40

interface Seed {
  id: string
  kind: Tablet['kind']
  label: string
  speciality?: string
  place: string
  battery: number
  online?: boolean
  rounds?: string[]
}

const SEEDS: Seed[] = [
  { id: 'tab-bed-11', kind: 'bedside', label: 'Bed 11', place: 'room-11', battery: 82 },
  { id: 'tab-bed-12', kind: 'bedside', label: 'Bed 12', place: 'room-12', battery: 64 },
  { id: 'tab-bed-13', kind: 'bedside', label: 'Bed 13', place: 'room-13', battery: 18 },
  { id: 'tab-bed-14', kind: 'bedside', label: 'Bed 14', place: 'room-14', battery: 91, online: false },
  { id: 'tab-dr-a', kind: 'staff', label: 'Dr. A', speciality: 'Cardiology', place: 'room-12', battery: 71, rounds: ['room-11', 'room-12', 'room-13', 'room-14', 'nurse-station'] },
  { id: 'tab-nurse-2', kind: 'staff', label: 'Ward 2 nurse', speciality: 'Nursing', place: 'nurse-station', battery: 48, rounds: ['nurse-station', 'room-13', 'room-11', 'lounge', 'room-14'] },
  { id: 'tab-physio-b', kind: 'staff', label: 'Physio B', speciality: 'Physiotherapy', place: 'therapy-1', battery: 33, rounds: ['therapy-1', 'pool', 'therapy-2', 'hall'] },
  { id: 'tab-reception', kind: 'staff', label: 'Reception desk', speciality: 'Reception', place: 'reception', battery: 96 },
  { id: 'tab-spare-1', kind: 'staff', label: '', place: 'nurse-station', battery: 100 },
  { id: 'tab-spare-2', kind: 'bedside', label: '', place: 'nurse-station', battery: 77 },
]

/** Free tablets stand in a row on the shelf, this far from the shelf's place (clear of robot docks). */
const SHELF_OFFSET = { x: 1.4, y: 1.7, step: 0.75 }

/** Tablets in one room stand side by side, not on top of each other. */
function spot(state: SimState, placeId: string, tabletId: string): Tablet['position'] {
  const place = placeById(state, placeId)
  if (!place) return null
  const self = state.tablets.find((entry) => entry.tablet.id === tabletId)?.tablet
  if (self && !self.assigned) {
    const shelved = state.tablets.filter((entry) => !entry.tablet.assigned && entry.tablet.place === placeId && entry.tablet.id < tabletId).length
    return { x: place.x + SHELF_OFFSET.x + shelved * SHELF_OFFSET.step, y: place.y + SHELF_OFFSET.y, floor: place.floor }
  }
  const others = state.tablets.filter((entry) => entry.tablet.place === placeId && entry.tablet.id !== tabletId).length
  const angle = others * 1.9 + 0.6
  const radius = 0.55 + 0.15 * others
  return { x: place.x + Math.cos(angle) * radius, y: place.y + Math.sin(angle) * radius, floor: place.floor }
}

export function copyTablet(tablet: Tablet): Tablet {
  return { ...tablet, position: tablet.position ? { ...tablet.position } : null }
}

function announce(state: SimState, entry: SimTablet): void {
  entry.tablet.lastSeen = iso(state)
  emit(state, { type: 'device.updated', tablet: copyTablet(entry.tablet) })
}

export function seedTablets(state: SimState): SimTablet[] {
  state.tablets = []
  for (const seed of SEEDS) {
    const assigned = seed.label !== ''
    const tablet: Tablet = {
      id: seed.id,
      kind: seed.kind,
      label: seed.label,
      speciality: seed.speciality ?? null,
      battery: seed.battery,
      online: seed.online ?? true,
      assigned,
      place: seed.place,
      position: null,
      uncertainty: seed.kind === 'staff' && assigned ? 2.5 : null,
      lastSeen: iso(state),
    }
    const entry: SimTablet = { tablet, rounds: seed.rounds ?? [], nextMoveIn: MOVE_MIN_SECONDS * state.random(), lowRaised: false, offlineRaised: false }
    state.tablets.push(entry)
    tablet.position = spot(state, seed.place, seed.id)
  }
  return state.tablets
}

/** Batteries drain in use and charge on the shelf; staff walk their rounds. */
export function stepTablets(state: SimState, dt: number): void {
  state.tabletReportIn -= dt
  const report = state.tabletReportIn <= 0
  if (report) state.tabletReportIn = BATTERY_REPORT_SECONDS
  for (const entry of state.tablets) {
    const { tablet } = entry
    if (tablet.battery !== null && tablet.online) {
      tablet.battery = tablet.assigned ? Math.max(0, tablet.battery - DRAIN_PER_SECOND * dt) : Math.min(100, tablet.battery + CHARGE_PER_SECOND * dt)
      if (tablet.battery === 0) tablet.online = false
    }
    checkTablet(state, entry)
    if (tablet.assigned && tablet.online && entry.rounds.length) {
      entry.nextMoveIn -= dt
      if (entry.nextMoveIn <= 0) {
        entry.nextMoveIn = MOVE_MIN_SECONDS + state.random() * MOVE_SPREAD_SECONDS
        const next = entry.rounds[(entry.rounds.indexOf(tablet.place ?? '') + 1) % entry.rounds.length]
        tablet.place = next
        tablet.position = spot(state, next, tablet.id)
        announce(state, entry)
        continue
      }
    }
    if (report && tablet.online) announce(state, entry)
  }
}

const LOW_BATTERY = 20

/** A tablet in use that runs low or goes silent raises an incident on its room, once per spell. */
function checkTablet(state: SimState, entry: SimTablet): void {
  const { tablet } = entry
  const room = tablet.place
  const floor = tablet.position?.floor ?? null
  const low = tablet.assigned && tablet.online && tablet.battery !== null && tablet.battery < LOW_BATTERY
  if (low && !entry.lowRaised) raise(state, { code: 'tablet_battery_low', severity: 'warning', subject: { kind: 'tablet', id: tablet.id }, place: room, floor })
  entry.lowRaised = low
  const offline = tablet.assigned && !tablet.online
  if (offline && !entry.offlineRaised) raise(state, { code: 'tablet_offline', severity: tablet.kind === 'bedside' ? 'warning' : 'info', subject: { kind: 'tablet', id: tablet.id }, place: room, floor })
  entry.offlineRaised = offline
}

function tabletEntry(state: SimState, tabletId: string): SimTablet {
  const entry = state.tablets.find((candidate) => candidate.tablet.id === tabletId)
  if (!entry) throw new Error(`Tablet ${tabletId} is not registered.`)
  return entry
}

function shelfOf(state: SimState, tablet: Tablet): string {
  const floor = tablet.position?.floor ?? placeById(state, tablet.place ?? '')?.floor ?? 2
  return SHELF[floor] ?? SHELF[2]
}

/** Ends the session: whoever used it is signed out, and the tablet goes back to the shelf, free. */
export function disconnectTablet(state: SimState, tabletId: string, actor: string): Tablet {
  const entry = tabletEntry(state, tabletId)
  const { tablet } = entry
  if (!tablet.assigned) throw new Error(`${tabletId} is already free.`)
  const shelf = shelfOf(state, tablet)
  audit(state, actor, 'Tablet freed', tabletId, 'ok', tablet.kind === 'bedside' ? tablet.label : null)
  tablet.assigned = false
  tablet.label = ''
  tablet.speciality = null
  tablet.uncertainty = null
  entry.rounds = []
  tablet.place = shelf
  tablet.position = spot(state, shelf, tablet.id)
  announce(state, entry)
  return copyTablet(tablet)
}

/** Labels follow the server's rule: 1 to 40 characters, not digits only. */
function checkLabel(label: string): string {
  const trimmed = label.trim()
  if (!trimmed) throw new Error('Give the tablet a label: a pseudonym ("Dr. A") or a bed ("Bed 12").')
  if (trimmed.length > MAX_LABEL) throw new Error(`The label is too long: ${MAX_LABEL} characters at most.`)
  if (/^\d+$/.test(trimmed)) throw new Error('The label cannot be digits only.')
  return trimmed
}

export function assignTablet(state: SimState, tabletId: string, assignment: TabletAssignment, actor: string): Tablet {
  const entry = tabletEntry(state, tabletId)
  const { tablet } = entry
  if (tablet.assigned) throw new Error(`${tabletId} is in use. Free it first.`)
  if (!tablet.online) throw new Error(`${tabletId} is offline. Switch it on first.`)
  const label = checkLabel(assignment.label)
  const placeId = assignment.place ?? tablet.place
  const place = placeId ? placeById(state, placeId) : undefined
  if (assignment.kind === 'bedside' && (!place || place.kind !== 'room')) throw new Error('A bedside tablet needs a patient room.')
  tablet.kind = assignment.kind
  tablet.label = label
  tablet.speciality = assignment.kind === 'staff' ? assignment.speciality?.trim() || null : null
  tablet.assigned = true
  tablet.uncertainty = assignment.kind === 'staff' ? 2.5 : null
  if (place) { tablet.place = place.id; tablet.position = spot(state, place.id, tablet.id) }
  audit(state, actor, 'Tablet assigned', tabletId, 'ok', assignment.kind === 'bedside' ? label : null)
  announce(state, entry)
  return copyTablet(tablet)
}
