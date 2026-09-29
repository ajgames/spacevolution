import { useFrame } from '@react-three/fiber'
import { useLayoutEffect, useMemo, useRef } from 'react'
import { type Group, MathUtils, MeshBasicMaterial, type Mesh } from 'three'
import { type Point, audioGraph, filter, noiseSource, placement, sfx, soundAt } from '../demo/audio.ts'
import { useDemo } from '../demo/store.ts'
import { holdCue, jolt } from './cues.ts'
import { propMaterial } from './props.ts'
import { extras, transmissionTo } from './space.ts'
import { droid, droidEye, stick, useWalk } from './store.ts'
import { type Seg, collide, solids, walls } from './world.ts'

// D-7, the maintenance droid: a tracked box with a camera head, docked in the
// junction alcove until the player takes the joystick. Its camera feeds the
// centre screen in command (ConsoleScreens).

const RADIUS = 0.3
const TOP_SPEED = 1.1 // m/s forward; reverse is half
const TURN_RATE = 1.8 // rad/s
const WHEEL = 0.07 // wheel radius, for the spin

const paint = propMaterial({ color: '#4d5d59', roughness: 0.55, metalness: 0.35 })
const dark = propMaterial({ color: '#1d2021', roughness: 0.8, metalness: 0.2 })
const metal = propMaterial({ color: '#8a8f8e', roughness: 0.35, metalness: 0.9 })
const hazard = propMaterial({ color: '#b07a22', roughness: 0.6, metalness: 0.2 })
const lens = new MeshBasicMaterial({ color: '#ffb050', toneMapped: false })
const status = new MeshBasicMaterial({ color: '#ff3020', toneMapped: false })

let wallCache: { doors: readonly string[]; segs: Seg[] } | null = null
function droidWalls(doors: readonly string[]) {
  if (wallCache?.doors !== doors) wallCache = { doors, segs: walls('droid', doors) }
  return wallCache.segs
}

// The motor: a servo whine and track rumble from the droid itself, and the
// same through the console while the link is held, as if from its mic.
function motorSound(ctx: AudioContext, relay: Point) {
  const out = ctx.createGain()
  out.gain.value = 0
  const whine = new OscillatorNode(ctx, { type: 'sawtooth', frequency: 80 })
  const tracks = noiseSource(ctx, true)
  whine.connect(filter(ctx, 'lowpass', 900, 3)).connect(out)
  tracks.connect(filter(ctx, 'bandpass', 180, 0.9)).connect(out)
  const body = placement(ctx, [droid.x, 0.3, droid.z], 1.2)
  const feed = placement(ctx, relay, 1)
  const feedGain = ctx.createGain()
  feedGain.gain.value = 0
  out.connect(body.input)
  out.connect(feedGain).connect(feed.input)
  whine.start()
  tracks.start()
  return {
    update(effort: number, linked: boolean) {
      const now = ctx.currentTime
      out.gain.setTargetAtTime(effort * 0.22, now, 0.05)
      whine.frequency.setTargetAtTime(70 + effort * 150, now, 0.08)
      body.panner.positionX.value = droid.x
      body.panner.positionZ.value = droid.z
      body.setTransmission(transmissionTo([droid.x, 0.3, droid.z]), 0.1)
      feedGain.gain.setTargetAtTime(linked ? 0.3 : 0, now, 0.1)
    },
    stop() {
      out.gain.setTargetAtTime(0, ctx.currentTime, 0.05)
      whine.stop(ctx.currentTime + 0.3)
      tracks.stop(ctx.currentTime + 0.3)
    },
  }
}

export default function Droid() {
  const group = useRef<Group>(null)
  const wheels = useRef<(Mesh | null)[]>([])
  const head = useRef<Group>(null)
  const motor = useRef<ReturnType<typeof motorSound> | null>(null)
  const lastBump = useRef(0)

  useLayoutEffect(() => {
    extras.set('DROID', group.current!)
    return () => {
      extras.delete('DROID')
      motor.current?.stop()
      motor.current = null
    }
  }, [])

  // Four wheels a side, under the tracks.
  const wheelSpots = useMemo(() => [-0.17, -0.06, 0.06, 0.17].flatMap((z) => [-0.2, 0.2].map((x) => [x, z] as const)), [])

  useFrame(({ clock }, rawDt) => {
    const dt = Math.min(rawDt, 0.05)
    const walk = useWalk.getState()
    const driving = walk.mode === 'stick' && walk.locked && !walk.ended
    const ahead = driving ? stick.y : 0
    const turn = driving ? stick.x : 0
    droid.speed = MathUtils.damp(droid.speed, ahead * (ahead > 0 ? TOP_SPEED : TOP_SPEED / 2), 4, dt)
    droid.spin = MathUtils.damp(droid.spin, -turn * TURN_RATE, 7, dt)
    droid.yaw += droid.spin * dt

    const x0 = droid.x
    const z0 = droid.z
    droid.x += -Math.sin(droid.yaw) * droid.speed * dt
    droid.z += -Math.cos(droid.yaw) * droid.speed * dt
    collide(droid, RADIUS, droidWalls(useDemo.getState().doorsOpen), solids.rects)
    const moved = Math.hypot(droid.x - x0, droid.z - z0)
    const direction = droid.speed >= 0 ? 1 : -1
    droid.travelled += moved * direction

    // Driving into something: a knock, and the picture jumps.
    const blocked = Math.abs(droid.speed) > 0.45 && moved < Math.abs(droid.speed) * dt * 0.3
    if (blocked && clock.elapsedTime - lastBump.current > 0.7) {
      lastBump.current = clock.elapsedTime
      soundAt('DROID', sfx.clunk, { cue: 'droid', reach: 1.2 })
      if (walk.mode === 'stick') jolt(0.25)
    }

    const g = group.current!
    g.position.set(droid.x, 0, droid.z)
    g.rotation.y = droid.yaw
    // Wheels roll with the ground covered, and turn against each other on the spot.
    wheels.current.forEach((wheel, i) => {
      if (!wheel) return
      const side = wheelSpots[i][0] > 0 ? 1 : -1
      wheel.rotation.x -= (moved * direction + side * droid.spin * dt * 0.2) / WHEEL
    })
    // The head bobs a little on the tracks; the feed shows it.
    if (head.current) head.current.position.y = 0.36 + Math.sin(droid.travelled * 40) * 0.0025 * Math.min(1, Math.abs(droid.speed))
    status.color.setRGB(1, 0.19, 0.12).multiplyScalar(Math.sin(clock.elapsedTime * 4) > 0 ? 2.5 : 0.4)

    // Motor sound, once there's audio.
    const graph = audioGraph()
    if (graph && !motor.current && useDemo.getState().started) motor.current = motorSound(graph.ctx, [0, 1.38, -8.87])
    const effort = Math.min(1, Math.abs(droid.speed) / TOP_SPEED + Math.abs(droid.spin) / (TURN_RATE * 1.5))
    motor.current?.update(effort, walk.mode === 'stick')
    if (effort > 0.05) holdCue('droid', 'droid', [[droid.x, 0.3, droid.z]], 1.2, effort)
  })

  return (
    <group ref={group}>
      {/* chassis between the tracks */}
      <mesh material={paint} position={[0, 0.2, 0]}>
        <boxGeometry args={[0.3, 0.16, 0.46]} />
      </mesh>
      <mesh material={hazard} position={[0, 0.2, -0.235]}>
        <boxGeometry args={[0.3, 0.05, 0.012]} />
      </mesh>
      {/* tracks */}
      {[-0.2, 0.2].map((x) => (
        <mesh key={x} material={dark} position={[x, 0.08, 0]}>
          <boxGeometry args={[0.1, 0.14, 0.5]} />
        </mesh>
      ))}
      {wheelSpots.map(([x, z], i) => (
        <mesh
          key={i}
          ref={(wheel) => {
            wheels.current[i] = wheel
          }}
          material={metal}
          position={[x * 1.28, WHEEL, z]}
          rotation-z={Math.PI / 2}
        >
          <cylinderGeometry args={[WHEEL, WHEEL, 0.02, 12]} />
        </mesh>
      ))}
      {/* mast and camera head */}
      <mesh material={metal} position={[0, 0.3, 0.06]}>
        <cylinderGeometry args={[0.025, 0.025, 0.14, 10]} />
      </mesh>
      <group ref={head} position={[0, 0.36, 0.02]}>
        <mesh material={paint} position={[0, 0.05, 0]}>
          <boxGeometry args={[0.2, 0.11, 0.14]} />
        </mesh>
        <mesh material={dark} position={[0, 0.05, -0.075]} rotation-x={Math.PI / 2}>
          <cylinderGeometry args={[0.036, 0.036, 0.02, 20]} />
        </mesh>
        <mesh material={lens} position={[0, 0.05, -0.086]} rotation-x={Math.PI / 2}>
          <cylinderGeometry args={[0.022, 0.022, 0.004, 20]} />
        </mesh>
        <mesh material={status} position={[0.075, 0.09, 0.071]}>
          <boxGeometry args={[0.018, 0.012, 0.004]} />
        </mesh>
        <primitive object={droidEye} position={[0, 0.05, -0.1]} rotation-x={MathUtils.degToRad(4)} />
      </group>
    </group>
  )
}
