/** Colour and title of a tablet, shared by the 3D marker and the side panel. */
import type { Tablet } from '../types'
import { TABLET_COLOR } from './palette'

export function tabletColor(tablet: Tablet): string {
  if (!tablet.assigned || !tablet.online) return TABLET_COLOR.free
  return TABLET_COLOR[tablet.kind]
}

export function tabletTitle(tablet: Tablet): string {
  if (!tablet.assigned) return tablet.kind === 'bedside' ? 'Free bedside tablet' : 'Free staff tablet'
  return tablet.label || (tablet.kind === 'bedside' ? 'Bedside tablet' : 'Staff tablet')
}
