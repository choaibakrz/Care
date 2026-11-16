/**
 * Single source of truth for the physical scale used by the 3D supervision map.
 * The map coordinates are metres: x grows east, y grows south, z is vertical.
 */
export const CLINIC_DIMENSIONS = {
  floorWidth: 24,
  floorDepth: 14,
  wallHeight: 2.7,
  wallThickness: 0.18,
  slabThickness: 0.22,
  floorToFloor: 3.6,
  ceilingFixtureHeight: 2.58,
  doorHeight: 2.1,
  entranceDoorWidth: 1.2,
} as const

/**
 * PrimeBOT Q1 is publicly specified at 0.88 m tall. Width and depth are an
 * intentionally conservative visual envelope because the public product sheet
 * does not publish a complete bounding box.
 */
export const Q1_DIMENSIONS = {
  height: 0.88,
  shoulderWidth: 0.3,
  torso: [0.22, 0.21, 0.15] as [number, number, number],
  pelvis: [0.18, 0.1, 0.13] as [number, number, number],
  upperLeg: [0.075, 0.16, 0.075] as [number, number, number],
  lowerLeg: [0.07, 0.16, 0.07] as [number, number, number],
  foot: [0.105, 0.055, 0.17] as [number, number, number],
  upperArm: [0.065, 0.14, 0.065] as [number, number, number],
  forearm: [0.06, 0.14, 0.06] as [number, number, number],
  hand: [0.07, 0.055, 0.07] as [number, number, number],
  head: [0.16, 0.145, 0.135] as [number, number, number],
} as const

export const Q1_POSE = {
  footY: 0.028,
  lowerLegY: 0.135,
  kneeY: 0.225,
  upperLegY: 0.3,
  pelvisY: 0.44,
  torsoY: 0.6,
  shoulderY: 0.68,
  elbowY: 0.56,
  wristY: 0.45,
  headY: 0.8075,
  beaconY: 0.87,
  ringRadius: 0.2,
  ringSelectedRadius: 0.25,
} as const

