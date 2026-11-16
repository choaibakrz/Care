#!/usr/bin/env node
// Exports the admin console's demo clinic (INVENTED DATA) into the server's seed files:
//
//   seed/clinic_map.json   the plan of `admin/src/mock/world.ts`, as a `locations::ClinicPlan`
//   seed/demo_fleet.json   the robots, stock, zones and schedule of `admin/src/mock/seed.ts`
//
// Usage, from `implementation/server`:
//
//   node scripts/export_console_clinic.mjs
//
// Node 24 runs the console's TypeScript files directly (built-in type stripping). The console
// imports its modules without the `.ts` extension (a bundler habit), so a small resolve hook
// below adds it. No npm package is used.
//
// Changes made on the way, and why:
// - Walls get ids `<floor>-w<index>` (index within the floor, in file order): the server's
//   plan gives every wall an id (Task A4); the console's walls have none yet.
// - `labelAt` becomes `label_at`; nothing else is renamed (the plan uses the console's keys).
// - Robot ids are lowercased (`R1` -> `r1`): server ids are `[a-z0-9_-]`.
// - Every file carries `"marque": "inventé"`: all of this is invented.
import { registerHooks } from 'node:module'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const serverDir = join(here, '..')
const adminSrc = join(serverDir, '..', 'admin', 'src')

// Relative imports without an extension inside the console sources resolve to `.ts`.
registerHooks({
  resolve(specifier, context, nextResolve) {
    const relative = specifier.startsWith('./') || specifier.startsWith('../')
    const fromConsole = context.parentURL?.includes('/admin/src/')
    if (relative && fromConsole && !/\.[a-z]+$/i.test(specifier)) {
      return nextResolve(`${specifier}.ts`, context)
    }
    return nextResolve(specifier, context)
  },
})

const world = await import(pathToFileURL(join(adminSrc, 'mock', 'world.ts')).href)
const seed = await import(pathToFileURL(join(adminSrc, 'mock', 'seed.ts')).href)

const MARQUE = 'inventé'
const map = world.mockMap

const point = ([x, y]) => [x, y]

function wallsWithIds(walls) {
  const perFloor = new Map()
  return walls.map((wall) => {
    const index = perFloor.get(wall.floor) ?? 0
    perFloor.set(wall.floor, index + 1)
    return { id: `${wall.floor}-w${index}`, floor: wall.floor, points: wall.points.map(point) }
  })
}

const plan = {
  marque: MARQUE,
  name: 'Demo clinic',
  floors: map.floors.map((floor) => ({ id: floor.id, label: floor.label, outline: floor.outline.map(point) })),
  rooms: map.rooms.map((room) => {
    const out = { id: room.id, floor: room.floor, label: room.label, kind: room.kind, polygon: room.polygon.map(point) }
    if (room.labelAt) out.label_at = point(room.labelAt)
    return out
  }),
  walls: wallsWithIds(map.walls),
  places: map.places.map((place) => ({ id: place.id, label: place.label, floor: place.floor, x: place.x, y: place.y, kind: place.kind })),
  props: map.props.map((prop) => ({ id: prop.id, floor: prop.floor, kind: prop.kind, x: prop.x, y: prop.y, width: prop.width, depth: prop.depth, solid: prop.solid })),
}

// `seedRobots` and friends read only `map` and `clock` from the simulation state.
const state = { map, clock: Date.UTC(2026, 10, 14, 8, 0, 0) }
const robotId = (id) => id.toLowerCase()
const simRobots = seed.seedRobots(state)

const fleet = {
  marque: MARQUE,
  robots: simRobots.map((entry) => ({
    id: robotId(entry.robot.id),
    name: entry.robot.name,
    role: entry.robot.role,
    home: entry.home,
    battery: entry.robot.battery,
    heading: entry.robot.position.heading,
  })),
  items: seed.seedInventory(state).map((item) => ({ id: item.id, label: item.label, place: item.place, count: item.count, low_at: item.lowAt })),
  zones: seed.seedZones(simRobots.map((entry) => entry.robot.id)).map((zone) => ({ id: zone.id, name: zone.name, floor: zone.floor, kind: zone.kind, polygon: zone.polygon.map(point) })),
  schedules: seed.seedSchedules().map((schedule) => ({ id: schedule.id, label: schedule.label, enabled: schedule.enabled, time: schedule.time, robot_id: schedule.robotId ? robotId(schedule.robotId) : null })),
  destinations: seed.DESTINATIONS,
  requesters: seed.REQUESTERS,
}

const seedDir = join(serverDir, 'seed')
mkdirSync(seedDir, { recursive: true })
writeFileSync(join(seedDir, 'clinic_map.json'), `${JSON.stringify(plan, null, 2)}\n`)
writeFileSync(join(seedDir, 'demo_fleet.json'), `${JSON.stringify(fleet, null, 2)}\n`)

const counts = {
  floors: plan.floors.length,
  rooms: plan.rooms.length,
  walls: plan.walls.length,
  places: plan.places.length,
  props: plan.props.length,
  robots: fleet.robots.length,
  items: fleet.items.length,
  zones: fleet.zones.length,
  schedules: fleet.schedules.length,
}
process.stdout.write(`${JSON.stringify(counts)}\n`)
