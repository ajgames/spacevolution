import { createContext, use } from 'react'
import { Mesh, MeshStandardMaterial, type Object3D } from 'three'
import type { ShipRoom } from '../scene/useShip.ts'
import type { Vec3 } from './nodes.ts'
import { FAILING_POD } from './store.ts'

// The demo's private copy of the rooms, shared with every demo component.
export const RoomsContext = createContext<ShipRoom[]>([])
export const useRooms = () => use(RoomsContext)

// Blender object names survive the glTF export, so the demo finds everything by name.
export function findObject(rooms: ShipRoom[], name: string) {
  for (const room of rooms) {
    const object = room.scene.getObjectByName(name)
    if (object) return object
  }
  throw new Error(`${name} is missing from the ship export`)
}

export function meshesOf(root: Object3D) {
  const meshes: Mesh[] = []
  root.traverse((object) => {
    if (object instanceof Mesh) meshes.push(object)
  })
  return meshes
}

export const BREAKER_BUTTONS = Array.from({ length: 8 }, (_, i) => `BTN_console_0${i + 1}`)

// Gives the objects the demo lights up individually their own materials; the
// export shares one material per look across a whole room. Runs before the
// rooms first render, so ShipRooms picks the copies up for lightmapping.
export function prepareRooms(rooms: ShipRoom[]) {
  const own = (mesh: Mesh) => (mesh.material = (mesh.material as MeshStandardMaterial).clone())
  for (const mesh of meshesOf(findObject(rooms, `${FAILING_POD}_status`))) own(mesh).emissive.set(1, 0.5, 0.1)
  for (const name of BREAKER_BUTTONS) {
    for (const mesh of meshesOf(findObject(rooms, name))) {
      const m = own(mesh)
      m.emissive.set(1, 0.5, 0.1)
      m.emissiveIntensity = 0
    }
  }
  for (const mesh of meshesOf(findObject(rooms, 'BTN_console_main'))) {
    if ((mesh.material as MeshStandardMaterial).name === 'MAT_emit_amber') own(mesh)
  }
  return rooms
}

// The core racks are static meshes with their transforms baked in, so their
// placement comes from blender/scripts/build_props.py (build_core): all four
// at Blender x 10.02, rotated 90 degrees, facing into the room along -x.
const RACK_Y = { CORE_rack_01: 1.2, CORE_rack_02: 0.4, CORE_rack_03: -0.4, CORE_rack_04: -1.2 }
export type Rack = keyof typeof RACK_Y

// A point in a rack's local frame (as build_props.py builds it) in three.js
// world space. Rack-local -x is the viewer's right.
export const rackPoint = (rack: Rack, lx: number, ly: number, lz: number): Vec3 => [
  10.02 - ly,
  lz,
  -(RACK_Y[rack] + lx),
]
// Turns a three.js plane (facing +z) to face out of a rack, text reading left to right.
export const FACING_OUT_OF_RACK: Vec3 = [0, -Math.PI / 2, 0]
