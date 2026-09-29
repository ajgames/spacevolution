import { useFrame } from '@react-three/fiber'
import { useEffect, useRef } from 'react'
import { MathUtils, type PerspectiveCamera, Vector3 } from 'three'
import { listenFrom, sfx } from '../demo/audio.ts'
import { useDemo } from '../demo/store.ts'
import { feel } from './cues.ts'
import { listener } from './space.ts'
import { PLACES, body, stick, useWalk, walkAct } from './store.ts'
import { activateHovered } from './targets.ts'
import { type Seg, collide, solids, walls } from './world.ts'

const EYE = 1.7
const POD_EYE = 1.9 // the pod floor is raised
const RADIUS = 0.28
const WALK = 1.7 // m/s
const RUN = 2.8
const STRIDE = 0.72 // metres per footstep
const LOOK = 0.0022 // radians per mouse pixel
const FOV = 70
const deg = MathUtils.degToRad

// Seated at the console, turned a little right so the droid feed on the centre
// screen and the joystick on the right desk top are both in view.
const SEAT = { x: 0.3, y: 1.38, z: -7.5, yaw: deg(-13), pitch: deg(-12), fov: 62 }
// Where the step out of the pod lands.
const OUT_OF_POD = PLACES.cryo
const STEP_OUT_SECONDS = 1.9

const keys = new Set<string>()
const mouse = { dx: 0, dy: 0, held: false }
const held = (...codes: string[]) => codes.some((c) => keys.has(c))

function useInput() {
  useEffect(() => {
    const locked = () => document.pointerLockElement !== null
    const onKeyDown = (e: KeyboardEvent) => {
      if (!locked()) return
      keys.add(e.code)
      if (e.code !== 'KeyE' || e.repeat) return
      if (useWalk.getState().mode === 'stick') walkAct.leaveStick()
      else activateHovered()
    }
    const onKeyUp = (e: KeyboardEvent) => keys.delete(e.code)
    const onMouseMove = (e: MouseEvent) => {
      // Some browsers report a wild jump now and then under pointer lock.
      if (!locked() || Math.abs(e.movementX) > 300 || Math.abs(e.movementY) > 300) return
      mouse.dx += e.movementX
      mouse.dy += e.movementY
    }
    const onMouseDown = (e: MouseEvent) => {
      if (!locked()) return
      const stickMode = useWalk.getState().mode === 'stick'
      if (e.button === 0) {
        mouse.held = true
        if (!stickMode) activateHovered()
      } else if (e.button === 2 && stickMode) walkAct.leaveStick()
    }
    const onMouseUp = (e: MouseEvent) => {
      if (e.button === 0) mouse.held = false
    }
    const release = () => {
      keys.clear()
      mouse.held = false
    }
    const onLockChange = () => {
      walkAct.setLocked(locked())
      if (!locked()) release()
    }
    const onContextMenu = (e: MouseEvent) => {
      if (locked()) e.preventDefault()
    }
    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('keyup', onKeyUp)
    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mousedown', onMouseDown)
    document.addEventListener('mouseup', onMouseUp)
    document.addEventListener('pointerlockchange', onLockChange)
    document.addEventListener('contextmenu', onContextMenu)
    window.addEventListener('blur', release)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('keyup', onKeyUp)
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mousedown', onMouseDown)
      document.removeEventListener('mouseup', onMouseUp)
      document.removeEventListener('pointerlockchange', onLockChange)
      document.removeEventListener('contextmenu', onContextMenu)
      window.removeEventListener('blur', release)
      release()
    }
  }, [])
}

// Walls for the current doors, rebuilt only when a door opens.
let wallCache: { doors: readonly string[]; segs: Seg[] } | null = null
function playerWalls(doors: readonly string[]) {
  if (wallCache?.doors !== doors) wallCache = { doors, segs: walls('player', doors) }
  return wallCache.segs
}

const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2)
const lerpAngle = (a: number, b: number, t: number) => a + (((b - a + Math.PI * 3) % (Math.PI * 2)) - Math.PI) * t
// Smooth noise in -1..1 for the shake: a few incommensurate sines.
const wobble = (t: number, seed: number) => Math.sin(t * 17.3 + seed) * 0.6 + Math.sin(t * 29.1 + seed * 2.7) * 0.4

// First-person movement: mouse look, WASD, sliding collisions against the
// plan in world.ts. The camera adds a light head bob, a breath of sway and a
// shake when something loud goes off nearby. In the pod it only looks; at the
// joystick it eases into the seat and the mouse and keys drive the stick.
export default function Player() {
  useInput()
  const motion = useRef({ vx: 0, vz: 0, stride: 0, bob: 0, seat: 0, stepping: 0, drag: { x: 0, y: 0 }, generation: -1 })
  const forward = useRef(new Vector3())
  const up = useRef(new Vector3())

  useFrame((state, rawDt) => {
    const camera = state.camera as PerspectiveCamera
    const dt = Math.min(rawDt, 0.05)
    const t = state.clock.elapsedTime
    const m = motion.current
    const demo = useDemo.getState()
    const walk = useWalk.getState()
    const live = demo.started && walk.locked && !walk.ended

    if (m.generation !== walk.generation) {
      // A reset: no easing from wherever the camera was.
      Object.assign(m, { vx: 0, vz: 0, bob: 0, seat: 0, stepping: 0, generation: walk.generation })
    }

    // Looking around.
    const looking = live && (walk.mode === 'walk' || walk.mode === 'pod')
    if (looking) {
      body.yaw -= mouse.dx * LOOK
      body.pitch = MathUtils.clamp(body.pitch - mouse.dy * LOOK, deg(-80), deg(80))
      if (walk.mode === 'pod') {
        // Only as far as the pod's glass lets you see.
        const home = PLACES.pod.yaw
        body.yaw = home + MathUtils.clamp(lerpAngle(0, body.yaw - home, 1), deg(-55), deg(55))
        body.pitch = MathUtils.clamp(body.pitch, deg(-35), deg(20))
      }
    }

    // The joystick: drag with the button held, or the keys; it springs back to centre.
    if (live && walk.mode === 'stick') {
      if (mouse.held) {
        m.drag.x += mouse.dx * 0.006
        m.drag.y -= mouse.dy * 0.006
        const length = Math.hypot(m.drag.x, m.drag.y)
        if (length > 1) {
          m.drag.x /= length
          m.drag.y /= length
        }
      } else m.drag.x = m.drag.y = 0
      const x = MathUtils.clamp(m.drag.x + (held('KeyD', 'ArrowRight') ? 1 : 0) - (held('KeyA', 'ArrowLeft') ? 1 : 0), -1, 1)
      const y = MathUtils.clamp(m.drag.y + (held('KeyW', 'ArrowUp') ? 1 : 0) - (held('KeyS', 'ArrowDown') ? 1 : 0), -1, 1)
      stick.x = MathUtils.damp(stick.x, x, 12, dt)
      stick.y = MathUtils.damp(stick.y, y, 12, dt)
    } else {
      m.drag.x = m.drag.y = 0
      stick.x = MathUtils.damp(stick.x, 0, 12, dt)
      stick.y = MathUtils.damp(stick.y, 0, 12, dt)
    }
    mouse.dx = mouse.dy = 0

    // Walking.
    let targetX = 0
    let targetZ = 0
    if (live && walk.mode === 'walk') {
      const ahead = (held('KeyW', 'ArrowUp') ? 1 : 0) - (held('KeyS', 'ArrowDown') ? 1 : 0)
      const side = (held('KeyD', 'ArrowRight') ? 1 : 0) - (held('KeyA', 'ArrowLeft') ? 1 : 0)
      const length = Math.hypot(ahead, side)
      if (length > 0) {
        const speed = (held('ShiftLeft', 'ShiftRight') ? RUN : WALK) / length
        const sin = Math.sin(body.yaw)
        const cos = Math.cos(body.yaw)
        // Local forward is -z; turn it by the yaw.
        targetX = (side * cos - ahead * sin) * speed
        targetZ = (-side * sin - ahead * cos) * speed
      }
    }
    m.vx = MathUtils.damp(m.vx, targetX, 10, dt)
    m.vz = MathUtils.damp(m.vz, targetZ, 10, dt)
    let moved = 0
    if (walk.mode === 'walk') {
      const x0 = body.x
      const z0 = body.z
      body.x += m.vx * dt
      body.z += m.vz * dt
      collide(body, RADIUS, playerWalls(demo.doorsOpen), solids.rects)
      moved = Math.hypot(body.x - x0, body.z - z0)
    }

    // Climbing out of the pod once it's open.
    let base = { x: body.x, y: walk.mode === 'pod' ? POD_EYE : EYE, z: body.z, yaw: body.yaw, pitch: body.pitch }
    if (walk.mode === 'stepping') {
      const from = m.stepping
      m.stepping = Math.min(1, m.stepping + dt / STEP_OUT_SECONDS)
      const e = ease(m.stepping)
      const pod = PLACES.pod
      base = {
        x: MathUtils.lerp(pod.x, OUT_OF_POD.x, e),
        y: MathUtils.lerp(POD_EYE, EYE, Math.min(1, e * 1.6)),
        z: MathUtils.lerp(pod.z, OUT_OF_POD.z, e),
        yaw: lerpAngle(body.yaw, OUT_OF_POD.yaw, e),
        pitch: MathUtils.lerp(body.pitch, OUT_OF_POD.pitch, e),
      }
      moved = Math.hypot(OUT_OF_POD.x - pod.x, OUT_OF_POD.z - pod.z) * (ease(m.stepping) - ease(from))
      if (from < 0.3 && m.stepping >= 0.3) sfx.footstep(1.4) // down off the pod's step
      if (m.stepping === 1) {
        Object.assign(body, OUT_OF_POD)
        m.stride = 0
        walkAct.stepOut()
      }
    }

    // Footsteps and the head bob that goes with them.
    const pace = moved / Math.max(dt, 1e-4)
    m.bob = MathUtils.damp(m.bob, Math.min(1.5, pace / WALK), 8, dt)
    const stride = m.stride
    m.stride += moved
    if (Math.floor(m.stride / STRIDE) > Math.floor(stride / STRIDE)) sfx.footstep(0.6 + 0.3 * Math.min(1.5, pace / WALK))
    const phase = (m.stride / STRIDE) * Math.PI
    const dip = 0.022 * m.bob * (0.5 - 0.5 * Math.cos(phase * 2))
    const sway = 0.01 * m.bob * Math.sin(phase)
    const roll = deg(0.3) * m.bob * Math.sin(phase)

    // Sitting down at the joystick, and standing back up.
    m.seat = MathUtils.damp(m.seat, walk.mode === 'stick' ? 1 : 0, 4.5, dt)
    const s = ease(MathUtils.clamp(m.seat, 0, 1))
    const pose = {
      x: MathUtils.lerp(base.x, SEAT.x, s),
      y: MathUtils.lerp(base.y, SEAT.y, s),
      z: MathUtils.lerp(base.z, SEAT.z, s),
      yaw: lerpAngle(base.yaw, SEAT.yaw, s),
      pitch: MathUtils.lerp(base.pitch, SEAT.pitch, s),
    }

    // Shake: trauma to the power 1.5, so small knocks stay small. Plus a slow breath.
    if (performance.now() < feel.floorUntil) feel.trauma = Math.max(feel.trauma, feel.floor)
    feel.trauma = Math.max(0, feel.trauma - dt * 1.3)
    const shake = feel.trauma ** 1.5
    const breath = Math.sin(t * 1.3)

    camera.position.set(
      pose.x + Math.cos(pose.yaw) * sway + 0.012 * shake * wobble(t, 1),
      pose.y - dip + 0.003 * breath + 0.012 * shake * wobble(t, 2),
      pose.z - Math.sin(pose.yaw) * sway + 0.012 * shake * wobble(t, 3),
    )
    camera.rotation.set(
      pose.pitch + deg(0.12) * breath + deg(1.2) * shake * wobble(t, 4),
      pose.yaw + deg(1.2) * shake * wobble(t, 5),
      roll + deg(0.8) * shake * wobble(t, 6),
      'YXZ',
    )
    const fov = MathUtils.lerp(FOV, SEAT.fov, s)
    if (Math.abs(camera.fov - fov) > 0.01) {
      camera.fov = fov
      camera.updateProjectionMatrix()
    }
    camera.updateMatrixWorld()

    // The ears go with the eyes.
    Object.assign(listener, { x: camera.position.x, y: camera.position.y, z: camera.position.z })
    camera.getWorldDirection(forward.current)
    up.current.set(0, 1, 0).applyQuaternion(camera.quaternion)
    listenFrom(camera.position.toArray(), forward.current.toArray(), up.current.toArray())
  })

  return null
}
