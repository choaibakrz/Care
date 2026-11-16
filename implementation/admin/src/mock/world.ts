/**
 * INVENTED DATA, for the demo only. The plan of a clinic that does not exist.
 *
 * It follows the places of `briques/clinique/faux_dossier/lieux.yaml`: a ground floor (hall,
 * reception, two therapy rooms, pool) and floor 2 (nurse station, supply room, rooms 11 to 14,
 * lounge). The robots never take the elevator, so the two floors are not connected.
 *
 * Coordinates are in metres. x grows east, y grows south. Each floor is 24 m by 14 m.
 * The 3D scene uses a 2.70 m clear wall height, 0.22 m slab and 3.60 m floor-to-floor height.
 */
import type { ClinicMap, MapPlace, MapProp, MapRoom, MapWall, Point, PropKind, RoomKind } from '../types'

const WIDTH = 24
const DEPTH = 14
const OUTLINE: Point[] = [[0, 0], [WIDTH, 0], [WIDTH, DEPTH], [0, DEPTH]]

function rect(x0: number, y0: number, x1: number, y1: number): Point[] {
  return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
}

function room(id: string, floor: number, label: string, kind: RoomKind, polygon: Point[], labelAt?: Point): MapRoom {
  return { id, floor, label, kind, polygon, labelAt }
}

function wall(floor: number, ...points: Point[]): MapWall {
  return { floor, points }
}

function place(id: string, floor: number, label: string, x: number, y: number, kind: MapPlace['kind'] = 'room'): MapPlace {
  return { id, label, floor, x, y, kind }
}

let propCount = 0
function prop(floor: number, kind: PropKind, x: number, y: number, width: number, depth: number, solid = true): MapProp {
  propCount += 1
  return { id: `prop-${propCount}`, floor, kind, x, y, width, depth, solid }
}

const groundRooms: MapRoom[] = [
  room('reception', 0, 'Reception', 'care', rect(0, 0, 7, 5.5), [3.5, 1.9]),
  room('elevator-0', 0, 'Elevator', 'elevator', rect(7, 0, 10, 5.5)),
  room('therapy-1', 0, 'Therapy 1', 'therapy', rect(10, 0, 17, 5.5), [13.5, 3.3]),
  room('therapy-2', 0, 'Therapy 2', 'therapy', rect(17, 0, 24, 5.5), [20.5, 3.3]),
  room('hall', 0, 'Hall', 'corridor', [[0, 5.5], [24, 5.5], [24, 8.5], [9, 8.5], [9, 14], [0, 14]], [4.5, 10.6]),
  room('pool', 0, 'Pool', 'pool', rect(9, 8.5, 24, 14), [22.6, 9.4]),
]

const groundWalls: MapWall[] = [
  // Outer walls. The gap on the west side is the main entrance.
  wall(0, [0, 10], [0, 0], [24, 0], [24, 14], [0, 14], [0, 12.2]),
  // North side of the hall, with one opening per room.
  wall(0, [0, 5.5], [2.2, 5.5]),
  wall(0, [4.8, 5.5], [12.6, 5.5]),
  wall(0, [14.4, 5.5], [19.6, 5.5]),
  wall(0, [21.4, 5.5], [24, 5.5]),
  wall(0, [7, 0], [7, 5.5]),
  wall(0, [10, 0], [10, 5.5]),
  wall(0, [17, 0], [17, 2]),
  wall(0, [17, 3.8], [17, 5.5]),
  // Pool.
  wall(0, [9, 14], [9, 8.5], [13, 8.5]),
  wall(0, [14.8, 8.5], [24, 8.5]),
]

const groundProps: MapProp[] = [
  prop(0, 'counter', 3.5, 3.6, 3.6, 0.8),
  prop(0, 'cabinet', 1.6, 0.45, 2.4, 0.6),
  prop(0, 'plant', 6.3, 0.7, 0.6, 0.6),
  prop(0, 'bench', 0.5, 2.3, 0.6, 1.8),
  prop(0, 'door', 8.5, 5.5, 1.4, 0.2, false),
  prop(0, 'bed', 12.1, 1.9, 2.0, 0.8),
  prop(0, 'cabinet', 15.2, 0.45, 2.2, 0.6),
  prop(0, 'mat', 15.4, 3.6, 1.8, 0.9, false),
  prop(0, 'bed', 21.9, 1.9, 2.0, 0.8),
  prop(0, 'bars', 19.1, 1.5, 2.6, 0.9),
  prop(0, 'cabinet', 22.6, 5.05, 1.6, 0.5),
  prop(0, 'sofa', 2.4, 13.35, 2.4, 0.9),
  prop(0, 'sofa', 5.6, 13.35, 2.4, 0.9),
  prop(0, 'table', 4.0, 12.1, 1.2, 0.6),
  prop(0, 'plant', 0.6, 13.4, 0.6, 0.6),
  prop(0, 'plant', 8.4, 13.4, 0.6, 0.6),
  prop(0, 'shelf', 8.55, 10.6, 0.6, 2.4),
  prop(0, 'dock', 0.5, 8.6, 0.7, 0.9),
  prop(0, 'dock', 23.5, 7.0, 0.7, 0.9),
  prop(0, 'pool', 16.5, 11.9, 9.0, 3.2),
  prop(0, 'bench', 11.2, 13.55, 2.4, 0.5),
  prop(0, 'bench', 22.9, 11.9, 0.5, 2.4),
]

const groundPlaces: MapPlace[] = [
  place('reception', 0, 'Reception', 3.5, 4.65, 'shelf'),
  place('linen-shelf', 0, 'Linen shelf', 7.55, 10.6, 'shelf'),
  place('hall', 0, 'Hall', 4.4, 10.2),
  place('therapy-1', 0, 'Therapy 1', 13.5, 4.2),
  place('therapy-2', 0, 'Therapy 2', 20.5, 4.0),
  place('pool', 0, 'Pool', 13.9, 9.45),
  place('dock-a', 0, 'Dock A', 1.5, 8.6, 'dock'),
  place('dock-b', 0, 'Dock B', 22.5, 7.0, 'dock'),
]

const upperRooms: MapRoom[] = [
  room('supply', 2, 'Supply room', 'storage', rect(0, 0, 7, 5.5), [4.2, 3.4]),
  room('elevator-2', 2, 'Elevator', 'elevator', rect(7, 0, 10, 5.5)),
  room('room-11', 2, 'Room 11', 'room', rect(10, 0, 17, 5.5), [14.4, 2.6]),
  room('room-12', 2, 'Room 12', 'room', rect(17, 0, 24, 5.5), [21.4, 2.6]),
  room('corridor', 2, 'Corridor', 'corridor', rect(0, 5.5, 24, 8.5), [12, 7]),
  room('nurse-station', 2, 'Nurse station', 'care', rect(0, 8.5, 8, 14), [4.3, 11.4]),
  room('room-13', 2, 'Room 13', 'room', rect(8, 8.5, 13, 14), [11.2, 10.6]),
  room('room-14', 2, 'Room 14', 'room', rect(13, 8.5, 18, 14), [16.2, 10.6]),
  room('lounge', 2, 'Lounge', 'lounge', rect(18, 8.5, 24, 14), [20.6, 10.2]),
]

const upperWalls: MapWall[] = [
  wall(2, [0, 0], [24, 0], [24, 14], [0, 14], [0, 0]),
  wall(2, [0, 5.5], [2.6, 5.5]),
  wall(2, [4.4, 5.5], [12.6, 5.5]),
  wall(2, [14.4, 5.5], [19.6, 5.5]),
  wall(2, [21.4, 5.5], [24, 5.5]),
  wall(2, [7, 0], [7, 5.5]),
  wall(2, [10, 0], [10, 5.5]),
  wall(2, [17, 0], [17, 5.5]),
  // South side of the corridor. The nurse station and the lounge are wide open.
  wall(2, [0, 8.5], [1, 8.5]),
  wall(2, [7, 8.5], [9.6, 8.5]),
  wall(2, [11.4, 8.5], [14.6, 8.5]),
  wall(2, [16.4, 8.5], [19, 8.5]),
  wall(2, [23, 8.5], [24, 8.5]),
  wall(2, [8, 8.5], [8, 14]),
  wall(2, [13, 8.5], [13, 14]),
  wall(2, [18, 8.5], [18, 14]),
]

function bedroom(x0: number, y0: number, north: boolean): MapProp[] {
  if (north) {
    return [prop(2, 'bed', x0 + 1.3, y0 + 1.5, 1.1, 2.2), prop(2, 'nightstand', x0 + 2.3, y0 + 0.5, 0.5, 0.5), prop(2, 'armchair', x0 + 5.9, y0 + 1.1, 0.8, 0.8), prop(2, 'cabinet', x0 + 6.6, y0 + 3.6, 0.5, 1.6)]
  }
  return [prop(2, 'bed', x0 + 1.3, y0 + 4.0, 1.1, 2.2), prop(2, 'nightstand', x0 + 2.3, y0 + 5.0, 0.5, 0.5), prop(2, 'armchair', x0 + 4.1, y0 + 4.5, 0.8, 0.8)]
}

const upperProps: MapProp[] = [
  prop(2, 'shelf', 0.5, 2.6, 0.6, 3.6),
  prop(2, 'shelf', 3.8, 0.45, 4.2, 0.6),
  prop(2, 'crate', 6.2, 1.3, 0.9, 0.9),
  prop(2, 'crate', 6.2, 2.5, 0.9, 0.7),
  prop(2, 'door', 8.5, 5.5, 1.4, 0.2, false),
  ...bedroom(10, 0, true),
  ...bedroom(17, 0, true),
  ...bedroom(8, 8.5, false),
  ...bedroom(13, 8.5, false),
  prop(2, 'counter', 3.2, 9.4, 3.6, 0.7),
  prop(2, 'cabinet', 7.55, 11.6, 0.6, 2.4),
  prop(2, 'desk', 3.4, 13.3, 2.6, 0.8),
  prop(2, 'dock', 0.5, 11.0, 0.7, 0.9),
  prop(2, 'dock', 0.5, 7.0, 0.7, 0.9),
  prop(2, 'sofa', 21.8, 13.35, 2.6, 0.9),
  prop(2, 'sofa', 23.4, 11.2, 0.9, 2.2),
  prop(2, 'table', 21.7, 11.9, 1.0, 1.0),
  prop(2, 'plant', 18.6, 13.4, 0.6, 0.6),
  prop(2, 'plant', 23.4, 6.1, 0.6, 0.6),
]

const upperPlaces: MapPlace[] = [
  place('supply-a', 2, 'Supply shelf A', 1.55, 2.6, 'shelf'),
  place('supply-b', 2, 'Supply shelf B', 3.8, 1.5, 'shelf'),
  place('nurse-cabinet', 2, 'Nurse cabinet', 6.55, 11.6, 'shelf'),
  place('nurse-station', 2, 'Nurse station', 3.2, 7.8),
  place('room-11', 2, 'Room 11', 13.5, 3.7),
  place('room-12', 2, 'Room 12', 20.5, 3.7),
  place('room-13', 2, 'Room 13', 10.5, 10.4),
  place('room-14', 2, 'Room 14', 15.5, 10.4),
  place('lounge', 2, 'Lounge', 20.4, 10.4),
  place('dock-w', 2, 'Dock W', 1.5, 7.0, 'dock'),
  place('dock-n', 2, 'Dock N', 1.5, 11.0, 'dock'),
]

export const mockMap: ClinicMap = {
  floors: [
    { id: 0, label: 'Ground floor', outline: OUTLINE },
    { id: 2, label: 'Floor 2', outline: OUTLINE },
  ],
  rooms: [...groundRooms, ...upperRooms],
  walls: [...groundWalls, ...upperWalls],
  places: [...groundPlaces, ...upperPlaces],
  props: [...groundProps, ...upperProps],
}
