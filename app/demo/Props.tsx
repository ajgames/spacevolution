import { useFrame } from '@react-three/fiber'
import { useMemo, useRef } from 'react'
import { MathUtils, type MeshStandardMaterial, type PointLight, Vector3 } from 'three'
import { sfx, soundAt } from './audio.ts'
import { BREAKER_BUTTONS, findObject, meshesOf, useRooms } from './objects.ts'
import { DOORS, FAILING_POD, useDemo } from './store.ts'

// Everything here reads the store every frame (getState, no re-renders) and
// eases the named Blender objects toward what the state says.

export function PodGlass() {
  const rooms = useRooms()
  const glass = useMemo(() => findObject(rooms, 'CRYO_POD_01_glass'), [rooms])
  useFrame((_, dt) => {
    // hinge_axis "local Z" in Blender is the node's local Y in glTF; positive swings it out.
    glass.rotation.y = MathUtils.damp(glass.rotation.y, useDemo.getState().podOpen ? 1.75 : 0, 2.2, dt)
  })
  return null
}

export function Doors() {
  const rooms = useRooms()
  const doors = useMemo(
    () =>
      DOORS.map((name) => {
        const object = findObject(rooms, name)
        // slide_axis "local +X", slide_distance 1 m (Blender extras on each DOOR_*)
        return { name, object, base: object.position.clone(), axis: new Vector3(1, 0, 0).applyQuaternion(object.quaternion), open: 0 }
      }),
    [rooms],
  )
  useFrame((_, dt) => {
    const open = useDemo.getState().doorsOpen
    for (const door of doors) {
      door.open = MathUtils.damp(door.open, open.includes(door.name) ? 1 : 0, 3.5, dt)
      door.object.position.copy(door.base).addScaledVector(door.axis, door.open)
    }
  })
  return null
}

// Buttons have their origin at the press point and push in along local -Y.
// Breakers stay half in and lit while they're closed; the main button glows
// once the breakers match.
export function Buttons() {
  const rooms = useRooms()
  const buttons = useMemo(
    () =>
      ['BTN_blink', 'BTN_console_main', ...BREAKER_BUTTONS].map((name) => {
        const object = findObject(rooms, name)
        return {
          name,
          object,
          breaker: BREAKER_BUTTONS.indexOf(name),
          base: object.position.clone(),
          axis: new Vector3(0, -1, 0).applyQuaternion(object.quaternion),
          depth: name === 'BTN_blink' ? 0.03 : 0.014,
          materials: meshesOf(object).map((m) => m.material as MeshStandardMaterial),
        }
      }),
    [rooms],
  )
  useFrame(({ clock }) => {
    const { pressedAt, breakers, phase, stutter } = useDemo.getState()
    const now = performance.now()
    for (const b of buttons) {
      const since = now - (pressedAt[b.name] ?? -Infinity)
      const tap = since < 90 ? 1 : since < 280 ? 1 - (since - 90) / 190 : 0
      const closed = b.breaker >= 0 && breakers[b.breaker]
      b.object.position.copy(b.base).addScaledVector(b.axis, b.depth * Math.max(tap, closed ? 0.55 : 0))
      if (b.breaker >= 0) {
        const glow = closed ? (stutter ? Math.random() * 1.5 : 1.3) : 0
        for (const m of b.materials) m.emissiveIntensity = glow
      }
      if (b.name === 'BTN_console_main') {
        for (const m of b.materials) {
          if (m.name !== 'MAT_emit_amber') continue
          const base = m.userData.baseEmissive ?? 3
          m.emissiveIntensity =
            phase === 'breakersSet' ? base * (0.55 + 0.45 * Math.sin(clock.elapsedTime * 5)) : base * 0.35
        }
      }
    }
  })
  return null
}

// The failing sleeper's status panel flickers amber in every lighting state.
export function FailingPod() {
  const rooms = useRooms()
  const materials = useMemo(
    () => meshesOf(findObject(rooms, `${FAILING_POD}_status`)).map((m) => m.material as MeshStandardMaterial),
    [rooms],
  )
  useFrame(({ clock }) => {
    const t = clock.elapsedTime
    // Two beating sines read as an irregular, failing flicker.
    const n = Math.sin(t * 7.3) + Math.sin(t * 17.1 + 1.3) * 0.6 + Math.sin(t * 2.1) * 0.5
    for (const m of materials) m.emissiveIntensity = n > 0.2 ? 3.2 : 0.25
  })
  return null
}

// The red pulse in the blackout: the blink lamp in engineering, and a trail of
// the same pulse down the corridor that grows toward engineering, so it reads
// as coming from somewhere down there, and shows through the open cryo door.
const CORRIDOR_PULSE: { position: [number, number, number]; intensity: number }[] = [
  { position: [-2.6, 2.2, 0], intensity: 0.35 },
  { position: [0.8, 2.2, 0], intensity: 0.7 },
  { position: [3.9, 2.2, 0], intensity: 1.3 },
]

const PULSE_SOURCES = ['LIGHT_BLINK_engineering', ...CORRIDOR_PULSE.map((p) => p.position)]

// The lights stay mounted and go dark after the blackout: adding or removing a
// light changes every lit material's shader, and three.js recompiles them all
// in the frame it happens.
export function PulseLights() {
  const rooms = useRooms()
  const lamp = useMemo(() => findObject(rooms, 'LIGHT_BLINK_engineering').getWorldPosition(new Vector3()), [rooms])
  const lights = useRef<(PointLight | null)[]>([])
  const wasOn = useRef(false)
  const level = useRef(0)
  useFrame(({ clock }, dt) => {
    const { phase, started } = useDemo.getState()
    // Same clock and phase as the blinking button material in ShipRooms.
    const on = phase === 'blackout' && Math.sin(clock.elapsedTime * Math.PI * 2) > 0
    // The tick sounds from the lamp and the trail alike (in the walk mode; the demo plays it flat).
    if (on && !wasOn.current && started) soundAt(PULSE_SOURCES, sfx.pulseTick, { cue: 'pulse', reach: 4 })
    wasOn.current = on
    level.current = MathUtils.damp(level.current, on ? 1 : 0, 16, dt)
    lights.current.forEach((light, i) => {
      if (light) light.intensity = level.current * (i === 0 ? 2.5 : CORRIDOR_PULSE[i - 1].intensity)
    })
  })
  return (
    <>
      {[[lamp.x, lamp.y, lamp.z + 0.25] as const, ...CORRIDOR_PULSE.map((p) => p.position)].map((position, i) => (
        <pointLight
          key={i}
          ref={(light) => {
            lights.current[i] = light
          }}
          position={position}
          color="#ff1a0a"
          distance={i === 0 ? 4 : 4.5}
          decay={2}
          intensity={0}
        />
      ))}
    </>
  )
}

// The rotating alarm beacons sweep past every two seconds in emergency lighting
// (ShipRooms swells the lightmaps in time); a quiet whoop goes with each sweep,
// from every beacon at once.
const BEACONS = ['LIGHT_alarm_command', 'LIGHT_alarm_corridor', 'LIGHT_alarm_cryo', 'LIGHT_alarm_engineering']

export function AlarmSync() {
  const wasUp = useRef(false)
  useFrame(({ clock }) => {
    const { phase, started } = useDemo.getState()
    const up = Math.sin(clock.elapsedTime * Math.PI) > 0.95
    if (up && !wasUp.current && started && (phase === 'emergency' || phase === 'breakersSet'))
      soundAt(BEACONS, sfx.alarm, { cue: 'alarm', reach: 3 })
    wasUp.current = up
  })
  return null
}
