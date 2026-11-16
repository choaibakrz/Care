/** Every colour of the 3D map, for both themes. Colour carries meaning here: state, zone kind, route. */
import type { DisplayState, RoomKind, ZoneKind } from '../types'

export const STATE_COLOR: Record<DisplayState, string> = {
  idle: '#4fe0b5',
  busy: '#f6c453',
  paused: '#9fb4d1',
  fault: '#ff9440',
  estop: '#ff5468',
  offline: '#76837f',
}

export const ZONE_COLOR: Record<ZoneKind, string> = {
  deaf: '#5db4ff',
  restricted: '#ea7bd0',
}

export const ROUTE_COLOR = '#f6c453'

/** Tablets: staff and bedside differ by colour and by icon; free or offline tablets are grey. */
export const TABLET_COLOR = { staff: '#a78bfa', bedside: '#f2d0a4', free: '#76837f' } as const

export interface ScenePalette {
  background: string
  ground: string
  slab: string
  floor: Record<RoomKind, string>
  wall: string
  wallCap: string
  ceilingLight: string
  label: string
  wood: string
  fabric: string
  fabricAlt: string
  linen: string
  metal: string
  dark: string
  leaf: string
  water: string
  robotShell: string
  robotDark: string
  ambient: number
  sun: number
}

export const DARK_SCENE: ScenePalette = {
  background: '#0b1615',
  ground: '#0e1b19',
  slab: '#1b322e',
  floor: { corridor: '#25413c', room: '#2c4c46', care: '#2a4b4c', storage: '#30483f', therapy: '#28494e', pool: '#234751', lounge: '#354a3f', elevator: '#172927' },
  wall: '#cfdbd6',
  wallCap: '#f4f9f7',
  ceilingLight: '#f2fff9',
  label: '#d9ebe5',
  wood: '#b08f6c',
  fabric: '#5e9990',
  fabricAlt: '#c9866b',
  linen: '#e9efec',
  metal: '#8b9c96',
  dark: '#22302d',
  leaf: '#58b27a',
  water: '#37b5dc',
  robotShell: '#f2f6f4',
  robotDark: '#15201e',
  ambient: 0.85,
  sun: 2.1,
}

export const LIGHT_SCENE: ScenePalette = {
  background: '#e6ede9',
  ground: '#dbe4df',
  slab: '#b9c8c1',
  floor: { corridor: '#f6f9f7', room: '#ecf4f0', care: '#e2f2ef', storage: '#edf1e7', therapy: '#e1eef3', pool: '#d6ecf3', lounge: '#f0f1e2', elevator: '#cdd8d3' },
  wall: '#53665f',
  wallCap: '#33443e',
  ceilingLight: '#fff8d4',
  label: '#2c3e38',
  wood: '#b99872',
  fabric: '#5f9d93',
  fabricAlt: '#d08a6d',
  linen: '#ffffff',
  metal: '#8a9a94',
  dark: '#3b4b46',
  leaf: '#4aa66d',
  water: '#39a9d0',
  robotShell: '#ffffff',
  robotDark: '#1c2927',
  ambient: 1.25,
  sun: 2.4,
}
