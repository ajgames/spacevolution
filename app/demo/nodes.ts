// Camera nodes for the Myst-style demo. Each spot is a fixed camera position
// with one or more facings; the player turns between facings and clicks
// hotspots to move between spots. Positions are three.js world coordinates
// (Blender (x, y, z) is three.js (x, z, -y)). Headings are compass degrees
// as seen on the Blender top view: 0 north (-z), 90 east (+x), 180 south (+z).

export type Vec3 = [number, number, number]

export type SpotId =
  | 'pod'
  | 'cryo'
  | 'corrW'
  | 'junction'
  | 'corrE'
  | 'eng'
  | 'engPanel'
  | 'engRacks'
  | 'corrN'
  | 'command'
  | 'console'

export type Facing = { heading: number; pitch?: number }

// An axis-aligned click volume, for spots with nothing solid to click on.
export type Area = { center: Vec3; size: Vec3 }

export type UseAction = 'openPod' | 'pressBlink' | 'breaker' | 'main'

export type Hotspot =
  | { id: string; kind: 'go'; to: SpotId; objects?: string[]; area?: Area; door?: string; heading?: number }
  | { id: string; kind: 'use'; action: UseAction; objects: string[]; index?: number }

export type Spot = {
  at: Vec3
  facings: Facing[] // in clockwise order; turning steps through them
  back?: SpotId // close-ups step back out to this spot
  fov?: number
  hotspots: Hotspot[]
}

// A standing-height click volume on the floor around another spot.
const around = (x: number, z: number): Area => ({ center: [x, 1.1, z], size: [1.4, 2.2, 1.4] })

const BREAKERS: Hotspot[] = Array.from({ length: 8 }, (_, i) => ({
  id: `breaker${i}`,
  kind: 'use',
  action: 'breaker',
  index: i,
  objects: [`BTN_console_0${i + 1}`],
}))

export const SPOTS: Record<SpotId, Spot> = {
  // Inside CRYO_POD_01, looking out through the glass at pods 04-06.
  pod: {
    at: [-6.7, 1.9, -2.3],
    facings: [{ heading: 180, pitch: -8 }],
    hotspots: [{ id: 'glass', kind: 'use', action: 'openPod', objects: ['CRYO_POD_01_glass'] }],
  },
  cryo: {
    at: [-6.6, 1.7, -0.75],
    // First facing: the door (and the pulse beyond it) and the failing pod across the aisle.
    facings: [{ heading: 148, pitch: -6 }, { heading: 235, pitch: -6 }, { heading: 330, pitch: -6 }],
    hotspots: [{ id: 'cryoDoor', kind: 'go', to: 'corrW', door: 'DOOR_cryo', objects: ['DOOR_cryo'] }],
  },
  corrW: {
    at: [-3.5, 1.7, 0],
    facings: [{ heading: 90, pitch: -3 }, { heading: 270, pitch: -3 }],
    hotspots: [
      { id: 'toJunction', kind: 'go', to: 'junction', area: around(0, 0) },
      { id: 'toCryo', kind: 'go', to: 'cryo', door: 'DOOR_cryo', objects: ['DOOR_cryo'], heading: 235 },
    ],
  },
  junction: {
    at: [0, 1.7, 0],
    facings: [
      { heading: 0, pitch: -3 },
      { heading: 90, pitch: -3 },
      { heading: 180, pitch: -12 },
      { heading: 270, pitch: -3 },
    ],
    hotspots: [
      { id: 'toCorrW', kind: 'go', to: 'corrW', area: around(-3.5, 0) },
      { id: 'toCorrE', kind: 'go', to: 'corrE', area: around(3.5, 0) },
      { id: 'toCorrN', kind: 'go', to: 'corrN', area: around(0, -3.5) },
    ],
  },
  corrE: {
    at: [3.5, 1.7, 0],
    facings: [{ heading: 90, pitch: -3 }, { heading: 270, pitch: -3 }],
    hotspots: [
      { id: 'engDoor', kind: 'go', to: 'eng', door: 'DOOR_engineering', objects: ['DOOR_engineering'] },
      { id: 'toJunction', kind: 'go', to: 'junction', area: around(0, 0) },
    ],
  },
  // Sees the blink panel on the north wall and the core racks on the east wall.
  eng: {
    at: [6.3, 1.7, 0.2],
    facings: [{ heading: 62, pitch: -5 }, { heading: 270, pitch: -3 }],
    hotspots: [
      { id: 'toPanel', kind: 'go', to: 'engPanel', objects: ['PANEL_blink', 'BTN_blink'] },
      { id: 'toRacks', kind: 'go', to: 'engRacks', objects: ['CORE_rack_02', 'CORE_rack_03'] },
      { id: 'engDoorOut', kind: 'go', to: 'corrE', door: 'DOOR_engineering', objects: ['DOOR_engineering'] },
    ],
  },
  engPanel: {
    at: [9.0, 1.62, -1.75],
    facings: [{ heading: 0, pitch: -6 }],
    back: 'eng',
    hotspots: [{ id: 'blink', kind: 'use', action: 'pressBlink', objects: ['BTN_blink'] }],
  },
  engRacks: {
    at: [8.2, 1.65, 0],
    facings: [{ heading: 90, pitch: -3 }],
    back: 'eng',
    hotspots: [],
  },
  corrN: {
    at: [0, 1.7, -3.5],
    facings: [{ heading: 0, pitch: -3 }, { heading: 180, pitch: -3 }],
    hotspots: [
      { id: 'cmdDoor', kind: 'go', to: 'command', door: 'DOOR_command', objects: ['DOOR_command'] },
      { id: 'toJunction', kind: 'go', to: 'junction', area: around(0, 0) },
    ],
  },
  command: {
    at: [0, 1.7, -5.9],
    facings: [{ heading: 0, pitch: -10 }, { heading: 180, pitch: -3 }],
    hotspots: [
      { id: 'toConsole', kind: 'go', to: 'console', objects: ['WORKSTATION_desk', 'PROP_workstation_seat'] },
      { id: 'cmdDoorOut', kind: 'go', to: 'corrN', door: 'DOOR_command', objects: ['DOOR_command'] },
    ],
  },
  // Standing behind the chair, over the workstation: the breaker row, the main
  // button and all three screens in one view.
  console: {
    at: [0, 1.66, -6.95],
    facings: [{ heading: 0, pitch: -16 }],
    back: 'command',
    fov: 58,
    hotspots: [...BREAKERS, { id: 'main', kind: 'use', action: 'main', objects: ['BTN_console_main'] }],
  },
}

export const ENGINEERING: SpotId[] = ['eng', 'engPanel', 'engRacks']

// The facing at `spot` closest to `heading`.
export function nearestFacing(spot: SpotId, heading: number) {
  const diff = (a: number) => Math.abs(((a - heading + 540) % 360) - 180)
  let best = 0
  SPOTS[spot].facings.forEach((f, i) => {
    if (diff(f.heading) < diff(SPOTS[spot].facings[best].heading)) best = i
  })
  return best
}

// Compass heading of travel from one spot to another.
export function headingBetween(from: SpotId, to: SpotId) {
  const [x0, , z0] = SPOTS[from].at
  const [x1, , z1] = SPOTS[to].at
  return (Math.atan2(x1 - x0, -(z1 - z0)) * 180) / Math.PI
}
