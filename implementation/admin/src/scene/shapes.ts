/** Small helpers shared by the parts of the 3D map. */
import { Shape } from 'three'
// The label font is bundled with the app: the map never fetches anything from the Internet.
import labelFont from '@fontsource/space-grotesk/files/space-grotesk-latin-600-normal.woff?url'
import type { Point } from '../types'
import { CLINIC_DIMENSIONS } from './scale'

export const WALL_HEIGHT = CLINIC_DIMENSIONS.wallHeight
export const WALL_THICKNESS = CLINIC_DIMENSIONS.wallThickness
export const SLAB_DEPTH = CLINIC_DIMENSIONS.slabThickness
export const LABEL_CHARACTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .-·'
export { labelFont }

/**
 * Props for every 3D label. The text library fetches a fallback font from a public CDN when a
 * character is missing from the font: pointing that lookup at a local path keeps the map offline.
 */
export const TEXT_PROPS = { font: labelFont, characters: LABEL_CHARACTERS, unicodeFontsURL: '/offline-no-font-fallback' } as const

/** Keeps only characters the bundled font has (Latin and Latin-1). Others become a space. */
export function safeLabel(text: string): string {
  return text.replace(/[^ -ÿ·]/g, ' ')
}

/** A flat shape lying on the ground. Map y becomes world z. */
export function groundShape(polygon: Point[]): Shape {
  const shape = new Shape()
  polygon.forEach(([x, y], index) => { if (index === 0) shape.moveTo(x, -y); else shape.lineTo(x, -y) })
  shape.closePath()
  return shape
}

/** Map heading (0 = east, turning towards south) to the rotation of a model whose nose points to +z. */
export function headingToRotation(heading: number): number {
  return Math.PI / 2 - heading
}
