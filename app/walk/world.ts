import { Box3, type Material, Mesh, Raycaster, Vector3 } from 'three'
import type { Point } from '../demo/audio.ts'
import type { ShipRoom } from '../scene/useShip.ts'

// The walk mode's world in plan view: three.js x and z (Blender x and -y).
// Walls follow the room outlines and corridor sizes in
// blender/scripts/lib_ship.py; props are boxes measured from the ship export
// when it loads. Nothing here raycasts the ship's meshes while you play.

export type Seg = readonly [x1: number, z1: number, x2: number, z2: number]
export type Rect = { x0: number; z0: number; x1: number; z1: number }
export type Spot = { x: number; z: number }

const DOOR_HALF = 0.5

// A room outline as wall segments, with a doorway cut where `door` lies on an edge.
function outline(points: [number, number][], door: [number, number]): Seg[] {
  return points.flatMap(([ax, az], i): Seg[] => {
    const [bx, bz] = points[(i + 1) % points.length]
    const length = Math.hypot(bx - ax, bz - az)
    const ux = (bx - ax) / length
    const uz = (bz - az) / length
    const along = (door[0] - ax) * ux + (door[1] - az) * uz
    const off = Math.abs((door[0] - ax) * uz - (door[1] - az) * ux)
    if (off > 0.01 || along <= 0 || along >= length) return [[ax, az, bx, bz]]
    const a = along - DOOR_HALF
    const b = along + DOOR_HALF
    return [
      [ax, az, ax + ux * a, az + uz * a],
      [ax + ux * b, az + uz * b, bx, bz],
    ]
  })
}

const COMMAND: [number, number][] = [[-3, -5], [3, -5], [3, -9], [2, -10], [-2, -10], [-3, -9]]
const CRYO: [number, number][] = [[-10, 3], [-6, 3], [-5, 2], [-5, -2], [-6, -3], [-10, -3], [-11, -2], [-11, 2]]
const ENGINEERING: [number, number][] = [[6, 3], [10, 3], [11, 2], [11, -2], [10, -3], [6, -3], [5, -2], [5, 2]]
// The T corridor's floor, with the droid alcove.
const CORRIDOR: [number, number][] = [
  [-4.8, -0.9], [-0.9, -0.9], [-0.9, -4.8], [0.9, -4.8], [0.9, -0.9], [4.8, -0.9],
  [4.8, 0.9], [0.7, 0.9], [0.7, 1.7], [-0.7, 1.7], [-0.7, 0.9], [-4.8, 0.9],
]
// Floor outlines, for the map on the status screen.
export const PLAN = [COMMAND, CRYO, ENGINEERING, CORRIDOR]

// The three modules, then the T corridor (1.8 m wide, ending at the rooms'
// 0.2 m walls at 4.8 m) with the doorway passages through those walls.
const WALLS: Seg[] = [
  ...outline(COMMAND, [0, -5]),
  ...outline(CRYO, [-5, 0]),
  ...outline(ENGINEERING, [5, 0]),
  // stem to command
  [-0.9, -0.9, -0.9, -4.8],
  [0.9, -0.9, 0.9, -4.8],
  [-0.9, -4.8, -0.5, -4.8],
  [0.5, -4.8, 0.9, -4.8],
  [-0.5, -4.8, -0.5, -5],
  [0.5, -4.8, 0.5, -5],
  // the arms, north wall and south wall either side of the droid alcove
  [-4.8, -0.9, -0.9, -0.9],
  [0.9, -0.9, 4.8, -0.9],
  [-4.8, 0.9, -0.7, 0.9],
  [0.7, 0.9, 4.8, 0.9],
  // the droid alcove, 0.8 m deep and 1.4 m tall
  [-0.7, 0.9, -0.7, 1.7],
  [-0.7, 1.7, 0.7, 1.7],
  [0.7, 1.7, 0.7, 0.9],
  // arm ends and the doorways into cryo and engineering
  [-4.8, -0.9, -4.8, -0.5],
  [-4.8, 0.5, -4.8, 0.9],
  [-4.8, -0.5, -5, -0.5],
  [-4.8, 0.5, -5, 0.5],
  [4.8, -0.9, 4.8, -0.5],
  [4.8, 0.5, 4.8, 0.9],
  [4.8, -0.5, 5, -0.5],
  [4.8, 0.5, 5, 0.5],
]

// The alcove is too low to walk into, but the droid lives there.
const ALCOVE_MOUTH: Seg = [-0.7, 0.9, 0.7, 0.9]

// Each door's leaf, closed. The doors slide into the wall once opened.
const DOOR_LEAVES: Record<string, Seg> = {
  DOOR_command: [-0.5, -4.9, 0.5, -4.9],
  DOOR_cryo: [-4.9, -0.5, -4.9, 0.5],
  DOOR_engineering: [4.9, -0.5, 4.9, 0.5],
}

// --- door control panels -----------------------------------------------------

export type DoorSide = 'room' | 'corridor'
export const doorButton = (door: string, side: DoorSide) => `${door}_button_${side}`

// Every door opens from a control panel beside it, one on each side, baked into
// the wall modules (build_structure.py: door_module on the room side,
// corridor_end_cap on the corridor side). The button's lit face is the only
// MAT_emit_amber at button height beside a doorway, so that's how it's found.
// Returns each button's box, keyed by doorButton(door, side).
export function findDoorButtons(rooms: ShipRoom[]) {
  const faces = new Map<string, { door: string; box: Box3 }>()
  const corners = [new Vector3(), new Vector3(), new Vector3()]
  for (const room of rooms) {
    room.scene.updateWorldMatrix(true, true)
    room.scene.traverse((object) => {
      if (!(object instanceof Mesh) || (object.material as Material).name !== 'MAT_emit_amber') return
      const position = object.geometry.getAttribute('position')
      const index = object.geometry.getIndex()
      const count = index ? index.count : position.count
      for (let t = 0; t < count; t += 3) {
        corners.forEach((v, k) => v.fromBufferAttribute(position, index ? index.getX(t + k) : t + k).applyMatrix4(object.matrixWorld))
        const [a, b, c] = corners
        const y = (a.y + b.y + c.y) / 3
        if (y < 1.18 || y > 1.3) continue
        const x = (a.x + b.x + c.x) / 3
        const z = (a.z + b.z + c.z) / 3
        for (const [door, [x1, z1, x2, z2]] of Object.entries(DOOR_LEAVES)) {
          if (Math.hypot(x - (x1 + x2) / 2, z - (z1 + z2) / 2) > 1.2) continue
          const name = doorButton(door, zoneOf(x, z) === 'corridor' ? 'corridor' : 'room')
          const face = faces.get(name) ?? { door, box: new Box3() }
          face.box.expandByPoint(a).expandByPoint(b).expandByPoint(c)
          faces.set(name, face)
        }
      }
    })
  }
  // The lit face is the front of an 8 x 8 x 4 cm button: grow it into the button,
  // back toward the wall (the doorway's centre line).
  return [...faces].map(([name, { door, box }]) => {
    const [x1, z1, x2, z2] = DOOR_LEAVES[door]
    const across = box.max.x - box.min.x < box.max.z - box.min.z ? 'x' : 'z'
    const wall = across === 'x' ? (x1 + x2) / 2 : (z1 + z2) / 2
    box.expandByScalar(0.01)
    if (wall > box.max[across]) box.max[across] += 0.03
    else box.min[across] -= 0.03
    return { name, door, box }
  })
}

export function walls(who: 'player' | 'droid', doorsOpen: readonly string[]): Seg[] {
  const shut = Object.entries(DOOR_LEAVES).flatMap(([door, leaf]) => (doorsOpen.includes(door) ? [] : [leaf]))
  return who === 'player' ? [...WALLS, ALCOVE_MOUTH, ...shut] : [...WALLS, ...shut]
}

// Props you'd walk into, by Blender name. Overhead pipes, trays and conduits
// aren't in the list; the droid dock is behind the alcove mouth.
const SOLID =
  /^(CRYO_POD_\d+$|CORE_rack_|DET_(cryo_(tank|monitor)|engineering_(power_unit|pipes)|command_(comms|locker)|corridor_jbox)|WORKSTATION_desk$|PROP_workstation_seat$|PANEL_blink$)/

// The props measured once the ship has loaded (WalkScene), for everyone to collide with.
export const solids: { rects: Rect[] } = { rects: [] }

export function measureProps(rooms: ShipRoom[]): Rect[] {
  const rects: Rect[] = []
  for (const room of rooms) {
    room.scene.updateWorldMatrix(true, true)
    for (const object of room.scene.children) {
      if (!SOLID.test(object.name)) continue
      const box = new Box3().setFromObject(object)
      rects.push({ x0: box.min.x, z0: box.min.z, x1: box.max.x, z1: box.max.z })
    }
  }
  return rects
}

// Pushes a circle of radius `r` at `p` out of every wall and prop, sliding
// along them. A few passes settle corners.
export function collide(p: Spot, r: number, segs: readonly Seg[], rects: readonly Rect[]) {
  for (let pass = 0; pass < 3; pass++) {
    for (const [x1, z1, x2, z2] of segs) {
      const dx = x2 - x1
      const dz = z2 - z1
      const t = Math.max(0, Math.min(1, ((p.x - x1) * dx + (p.z - z1) * dz) / (dx * dx + dz * dz)))
      pushOut(p, r, x1 + dx * t, z1 + dz * t)
    }
    for (const b of rects) {
      if (p.x > b.x0 && p.x < b.x1 && p.z > b.z0 && p.z < b.z1) {
        // Inside: leave by the nearest face.
        const exits = [p.x - b.x0, b.x1 - p.x, p.z - b.z0, b.z1 - p.z]
        const nearest = exits.indexOf(Math.min(...exits))
        if (nearest === 0) p.x = b.x0 - r
        else if (nearest === 1) p.x = b.x1 + r
        else if (nearest === 2) p.z = b.z0 - r
        else p.z = b.z1 + r
        continue
      }
      pushOut(p, r, Math.max(b.x0, Math.min(b.x1, p.x)), Math.max(b.z0, Math.min(b.z1, p.z)))
    }
  }
}

function pushOut(p: Spot, r: number, cx: number, cz: number) {
  const dx = p.x - cx
  const dz = p.z - cz
  const d2 = dx * dx + dz * dz
  if (d2 >= r * r || d2 === 0) return
  const d = Math.sqrt(d2)
  p.x = cx + (dx / d) * r
  p.z = cz + (dz / d) * r
}

// --- rooms and sound -------------------------------------------------------

export type Zone = 'cryo' | 'engineering' | 'command' | 'corridor'

export const zoneOf = (x: number, z: number): Zone =>
  x < -4.9 ? 'cryo' : x > 4.9 ? 'engineering' : z < -4.9 ? 'command' : 'corridor'

const ZONE_DOOR: Record<Exclude<Zone, 'corridor'>, string> = {
  cryo: 'DOOR_cryo',
  engineering: 'DOOR_engineering',
  command: 'DOOR_command',
}

// How much of a sound gets from one zone to another. Every room opens onto the
// corridor, so each room on the way costs one doorway: open, most of it gets
// through; shut, a dull thud.
export function transmission(a: Zone, b: Zone, doorsOpen: readonly string[]) {
  if (a === b) return 1
  let t = 1
  for (const zone of [a, b]) {
    if (zone !== 'corridor') t *= doorsOpen.includes(ZONE_DOOR[zone]) ? 0.55 : 0.12
  }
  return t
}

// The PA's ceiling speakers, on flat ceiling clear of the light panels, vents
// and trays. Heights are nominal until settleSpeakers finds the real ceiling.
export const SPEAKERS: { name: string; at: Point }[] = [
  { name: 'SPEAKER_command_w', at: [-1.8, 2.8, -6.7] },
  { name: 'SPEAKER_command_e', at: [1.8, 2.8, -6.7] },
  { name: 'SPEAKER_stem', at: [-0.1, 2.37, -1.6] },
  { name: 'SPEAKER_west', at: [-1.6, 2.37, -0.1] },
  { name: 'SPEAKER_east', at: [1.6, 2.37, 0] },
  { name: 'SPEAKER_cryo', at: [-8, 2.8, -0.8] },
  { name: 'SPEAKER_engineering', at: [7.8, 2.8, 0.7] },
]
export const SPEAKER_NAMES = SPEAKERS.map((s) => s.name)

// Puts each speaker just under the ceiling above it, found by casting up through
// the ship. Call once the ship has loaded, before the PA plays anything.
export function settleSpeakers(rooms: ShipRoom[]) {
  const ray = new Raycaster()
  const scenes = rooms.map((room) => room.scene)
  for (const speaker of SPEAKERS) {
    ray.set(new Vector3(speaker.at[0], 1.5, speaker.at[2]), new Vector3(0, 1, 0))
    const hit = ray.intersectObjects(scenes, true)[0]
    if (hit) speaker.at[1] = hit.point.y - 0.004
  }
}
