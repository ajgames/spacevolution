import { useFrame } from '@react-three/fiber'
import { useLayoutEffect } from 'react'
import { Box3, type Object3D, Vector3 } from 'three'
import { type Point, setSpace } from '../demo/audio.ts'
import { findObject, useRooms } from '../demo/objects.ts'
import { useDemo } from '../demo/store.ts'
import type { ShipRoom } from '../scene/useShip.ts'
import { JOLTS, flashCue, holdCue, jolt } from './cues.ts'
import { droid, useWalk } from './store.ts'
import { setWalls, voiceLevel } from './voice.ts'
import { SPEAKERS, transmission, zoneOf } from './world.ts'

// Where the player hears from, updated by the Player each frame.
export const listener = { x: 0, y: 1.7, z: 0 }

// Objects the walk mode adds to the ship (the joystick, the droid), by name,
// so sounds and targets find them the way they find Blender objects.
export const extras = new Map<string, Object3D>()

export function lookUp(rooms: ShipRoom[], name: string) {
  const extra = extras.get(name)
  if (extra) return extra
  try {
    return findObject(rooms, name)
  } catch {
    return undefined
  }
}

export const transmissionTo = ([x, , z]: Point) =>
  transmission(zoneOf(listener.x, listener.z), zoneOf(x, z), useDemo.getState().doorsOpen)

// A panner's inverse-distance gain (audio.ts placement), so cues fade like the sound.
export const gainAt = ([x, y, z]: Point, reach: number) => {
  const d = Math.hypot(x - listener.x, y - listener.y, z - listener.z)
  return d <= reach ? 1 : reach / (reach + 1.4 * (d - reach))
}

const SPEAKER_POINTS = SPEAKERS.map((s) => s.at)

// Installs the walk mode's Space (audio.ts): sounds tied to ship objects play
// from them, walls muffle them, and each shows as a cue and, if it's loud and
// close, knocks the camera.
export function Hearing() {
  const rooms = useRooms()

  useLayoutEffect(() => {
    // Objects sit at rest when first heard (a door, before it slides), so their positions keep.
    const positions = new Map<string, Point>()
    const locate = (name: string): Point | undefined => {
      if (name === 'DROID') return [droid.x, 0.35, droid.z]
      const speaker = SPEAKERS.find((s) => s.name === name)
      if (speaker) return speaker.at
      const known = positions.get(name)
      if (known) return known
      const object = lookUp(rooms, name)
      if (!object) return undefined
      object.updateWorldMatrix(true, true)
      const box = new Box3().setFromObject(object)
      const at = box.isEmpty() ? object.getWorldPosition(new Vector3()) : box.getCenter(new Vector3())
      const point: Point = [at.x, at.y, at.z]
      positions.set(name, point)
      return point
    }
    setSpace({
      locate,
      transmission: transmissionTo,
      heard(cue, points, reach) {
        flashCue(cue, points, reach)
        const strength = JOLTS[cue]
        if (!strength) return
        const nearest = Math.min(...points.map(([x, y, z]) => Math.hypot(x - listener.x, y - listener.y, z - listener.z)))
        const closeness = Math.max(0, Math.min(1, 1 - (nearest - 2) / 8))
        jolt(strength * closeness * Math.max(...points.map(transmissionTo)))
      },
    })
    return () => {
      setSpace(null)
    }
  }, [rooms])

  useFrame(() => {
    setWalls(transmissionTo)
    if (useWalk.getState().speaking) holdCue('voice', 'voice', SPEAKER_POINTS, 1.4, 0.35 + voiceLevel())
  })

  return null
}
