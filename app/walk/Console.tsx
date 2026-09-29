import { useFBO } from '@react-three/drei'
import { useFrame, useThree } from '@react-three/fiber'
import { useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import {
  type BufferGeometry,
  type Group,
  LatheGeometry,
  type Material,
  type Mesh,
  MeshBasicMaterial,
  type Scene,
  Vector2,
  type WebGLRenderTarget,
  type WebGLRenderer,
} from 'three'
import { AMBER, AMBER_DIM, canvasScreen, clear, crtMaterial, drawStandby, textLines } from '../demo/crt.ts'
import { findObject, meshesOf, useRooms } from '../demo/objects.ts'
import { SCREEN_BOOT_MS, atLeast, useDemo } from '../demo/store.ts'
import { compileShaders } from '../scene/warmUp.ts'
import { propMaterial } from './props.ts'
import { extras, listener } from './space.ts'
import { body, droid, droidEye, stick, useWalk } from './store.ts'
import { droidOnPodSix } from './story.ts'
import { voiceLevel, voiceWave } from './voice.ts'
import { PLAN, zoneOf } from './world.ts'

// --- the joystick ------------------------------------------------------------

// The droid joystick is modelled into the desk (build_props.py, "droid-control
// joystick on the right desk top"), so it's baked into WORKSTATION_desk_mesh.
// The walk mode keeps the baked base and boot, cuts the lever out of a copy of
// the desk's geometry, and puts a lever that moves in its place.
const STICK = { x: 0.9114, y: 0.79, z: -8.2826 } // the base's centre on the desk top
const GIMBAL = 0.06 // pivot height above the base, inside the boot
const TILT = 0.38 // radians at full deflection

const steel = propMaterial({ color: '#9a9e9c', roughness: 0.35, metalness: 0.9 })
const rubber = propMaterial({ color: '#141516', roughness: 0.85, metalness: 0 })
const lamp = new MeshBasicMaterial({ color: '#000000', toneMapped: false })
// The grip's profile from build_props.py, measured from the gimbal.
const GRIP = new LatheGeometry(
  [
    [0, 0.125],
    [0.02, 0.125],
    [0.024, 0.175],
    [0.017, 0.205],
    [0, 0.21],
  ].map(([r, y]) => new Vector2(r, y - GIMBAL)),
  12,
)

// Collapses the desk triangles that belong to the baked lever: close to the
// stick's axis and reaching above the boot.
function withoutLever(geometry: BufferGeometry) {
  const index = geometry.getIndex()
  if (!index) return geometry
  const position = geometry.getAttribute('position')
  const lever = (i: number) =>
    Math.hypot(position.getX(i) - STICK.x, position.getZ(i) - STICK.z) < 0.035 && position.getY(i) > STICK.y + 0.088
  const near = (i: number) => Math.hypot(position.getX(i) - STICK.x, position.getZ(i) - STICK.z) < 0.035
  const kept: number[] = []
  for (let t = 0; t < index.count; t += 3) {
    const [a, b, c] = [index.getX(t), index.getX(t + 1), index.getX(t + 2)]
    if (near(a) && near(b) && near(c) && (lever(a) || lever(b) || lever(c))) continue
    kept.push(a, b, c)
  }
  const copy = geometry.clone()
  copy.setIndex(kept)
  return copy
}

export function Joystick() {
  const rooms = useRooms()
  const lever = useRef<Group>(null)

  useLayoutEffect(() => {
    const meshes = meshesOf(findObject(rooms, 'WORKSTATION_desk'))
    const original = meshes.map((m) => m.geometry)
    for (const m of meshes) m.geometry = withoutLever(m.geometry)
    extras.set('JOYSTICK', lever.current!)
    return () => {
      meshes.forEach((m, i) => {
        if (m.geometry !== original[i]) m.geometry.dispose()
        m.geometry = original[i]
      })
      extras.delete('JOYSTICK')
    }
  }, [rooms])

  useFrame(() => {
    // Forward tips the top away from the seat (-z); right tips it right.
    lever.current!.rotation.set(-stick.y * TILT, 0, -stick.x * TILT)
    lamp.color.setRGB(1, 0.55, 0.16).multiplyScalar(useWalk.getState().mode === 'stick' ? 3 : 0.8)
  })

  return (
    <group ref={lever} position={[STICK.x, STICK.y + GIMBAL, STICK.z]}>
      <mesh material={steel} position-y={0.047}>
        <cylinderGeometry args={[0.009, 0.009, 0.055, 8]} />
      </mesh>
      <mesh material={rubber} geometry={GRIP} />
      {/* The amber thumb lamp, on the grip's far side like the baked one. */}
      <mesh material={lamp} position={[0, 0.135, -0.019]}>
        <boxGeometry args={[0.016, 0.01, 0.014]} />
      </mesh>
    </group>
  )
}

// --- the three workstation screens -------------------------------------------

const secondsSince = (at: number | undefined) => (at === undefined ? -1 : (performance.now() - at) / 1000)
const tick = (fps: number) => Math.floor(performance.now() / (1000 / fps))

const AUX_LOG = ['SYS LOG', 'PRIMARY BUS ..... ONLINE', 'BREAKERS ........ CLOSED', 'LIFE SUPPORT .... NOMINAL', 'STEWARD ......... LOADING']

// SCREEN_status maps the ship with the droid on it, SCREEN_mission is the
// droid's camera under a driving overlay, and SCREEN_aux is the steward.
export function ConsoleScreens() {
  const rooms = useRooms()
  const feed = useFBO(512, 384)

  const screens = useMemo(() => {
    const screen = (name: string, withFeed: boolean) => {
      const mesh = findObject(rooms, name) as Mesh
      const canvas = canvasScreen(512, 384, false)
      const material = crtMaterial(canvas.texture, 150, withFeed ? feed.texture : undefined)
      return { mesh, canvas, material, drawn: -1 }
    }
    return [screen('SCREEN_status', false), screen('SCREEN_mission', true), screen('SCREEN_aux', false)]
  }, [rooms, feed])

  useLayoutEffect(() => wearMaterials(screens), [screens])

  // The feed is its own render pass with its own shaders; build them at load.
  const gl = useThree((state) => state.gl)
  const scene = useThree((state) => state.scene)
  useEffect(() => {
    void compileShaders(gl, scene, droidEye, feed)
  }, [gl, scene, feed])

  useFrame(({ gl, scene, clock }) => {
    const { phase, enteredAt } = useDemo.getState()
    const walk = useWalk.getState()
    const powered = atLeast(phase, 'powered')
    const since = secondsSince(enteredAt.powered)
    screens.forEach((s, i) => {
      const u = s.material.uniforms
      u.time.value = clock.elapsedTime
      const boot = powered ? (since - SCREEN_BOOT_MS[i] / 1000) / 0.8 : 1
      u.power.value = Math.min(1, Math.max(0, boot))
      u.brightness.value = powered ? 2.4 : 1.1
      // The steward's screen moves with its voice, so it redraws faster.
      const frame = tick(i === 2 ? 24 : 10)
      if (s.drawn === frame) return
      s.drawn = frame
      const { ctx } = s.canvas
      const blink = Math.floor(performance.now() / 500) % 2 === 0
      if (!powered || boot <= 0) drawStandby(ctx, i === 1 ? 'NO SIGNAL' : 'STANDBY', blink)
      else if (i === 0) drawTrack(ctx, blink)
      else if (i === 1) drawFeedOverlay(ctx, blink, walk.linked, walk.scan)
      else if (walk.steward) drawSteward(ctx)
      else {
        clear(ctx)
        const shown = Math.min(AUX_LOG.length, Math.floor((since - SCREEN_BOOT_MS[2] / 1000) * 3))
        textLines(ctx, AUX_LOG.slice(0, shown), { size: 0.06, y: 0.08, gap: 1.6 })
      }
      s.canvas.texture.needsUpdate = true
    })

    // The droid's camera, while anyone could see it.
    if (powered && (walk.mode === 'stick' || zoneOf(listener.x, listener.z) === 'command')) {
      renderFeed(gl, scene, feed, screens[1].mesh)
    }
  })
  return null
}

// Puts each screen's CRT material on its mesh; returns the undo.
function wearMaterials(screens: { mesh: Mesh; material: Material }[]) {
  const original = screens.map((s) => s.mesh.material)
  for (const s of screens) s.mesh.material = s.material
  return () => screens.forEach((s, i) => (s.mesh.material = original[i]))
}

// Renders the droid's view into the feed. The mission screen and the droid
// itself are hidden from their own picture.
function renderFeed(gl: WebGLRenderer, scene: Scene, feed: WebGLRenderTarget, mission: Mesh) {
  const droidBody = extras.get('DROID')
  mission.visible = false
  if (droidBody) droidBody.visible = false
  gl.setRenderTarget(feed)
  gl.render(scene, droidEye)
  gl.setRenderTarget(null)
  mission.visible = true
  if (droidBody) droidBody.visible = true
}

// --- drawing -------------------------------------------------------------------

const POD_SIX = { x: -6.7, z: 2.28 }

// The ship to scale, the droid's track on it, and pod six flashing.
function drawTrack(ctx: CanvasRenderingContext2D, blink: boolean) {
  const { width: W, height: H } = ctx.canvas
  clear(ctx)
  textLines(ctx, ['SHIP STATUS', 'D-7 TRACK'], { size: 0.055, y: 0.05, gap: 1.3 })
  // x -11..11, z -10.2..3.2 fitted under the title.
  const scale = Math.min((W * 0.9) / 22, (H * 0.66) / 13.4)
  const px = (x: number) => W / 2 + x * scale
  const pz = (z: number) => H * 0.2 + (z + 10.2) * scale
  ctx.strokeStyle = AMBER
  ctx.lineWidth = Math.max(2, W / 240)
  ctx.shadowColor = AMBER
  ctx.shadowBlur = 6
  for (const outline of PLAN) {
    ctx.beginPath()
    outline.forEach(([x, z], i) => (i ? ctx.lineTo(px(x), pz(z)) : ctx.moveTo(px(x), pz(z))))
    ctx.closePath()
    ctx.stroke()
  }
  ctx.shadowBlur = 0
  // Pod six.
  ctx.fillStyle = blink ? '#ffb040' : '#3a2008'
  ctx.fillRect(px(POD_SIX.x) - scale * 0.5, pz(POD_SIX.z) - scale * 0.6, scale, scale * 1.2)
  // The caretaker, dim; the droid, bright and pointing where it faces.
  ctx.fillStyle = AMBER_DIM
  ctx.beginPath()
  ctx.arc(px(body.x), pz(body.z), scale * 0.22, 0, Math.PI * 2)
  ctx.fill()
  ctx.save()
  ctx.translate(px(droid.x), pz(droid.z))
  ctx.rotate(-droid.yaw)
  ctx.fillStyle = '#ffe0a0'
  ctx.shadowColor = AMBER
  ctx.shadowBlur = 10
  ctx.beginPath()
  ctx.moveTo(0, -scale * 0.55)
  ctx.lineTo(scale * 0.35, scale * 0.35)
  ctx.lineTo(-scale * 0.35, scale * 0.35)
  ctx.closePath()
  ctx.fill()
  ctx.restore()
  textLines(ctx, ['CRYO 06: VITALS LOW'], { size: 0.05, y: 0.88, color: blink ? '#ffb040' : AMBER_DIM })
}

// What's drawn over the droid's picture: before the link, a docked card; on
// the link, a reticle, heading tape, speed and the pod six scan.
function drawFeedOverlay(ctx: CanvasRenderingContext2D, blink: boolean, linked: boolean, scan: number) {
  const { width: W, height: H } = ctx.canvas
  ctx.fillStyle = '#000000'
  ctx.fillRect(0, 0, W, H)
  if (!linked) {
    textLines(ctx, ['MISSION F.P.P.', 'DROID D-7 // DOCKED'], { size: 0.05, y: 0.05, gap: 1.3 })
    textLines(ctx, [blink ? 'LINK: CONSOLE STICK' : ''], { size: 0.045, y: 0.9, color: AMBER_DIM })
    return
  }
  textLines(ctx, ['D-7 // LINK'], { size: 0.05, y: 0.05 })
  if (blink) {
    ctx.fillStyle = '#ff4020'
    ctx.beginPath()
    ctx.arc(W * 0.8, H * 0.085, H * 0.018, 0, Math.PI * 2)
    ctx.fill()
  }
  textLines(ctx, ['LIVE'], { size: 0.05, y: 0.06, x: 0.83 })

  // Reticle corners.
  ctx.strokeStyle = AMBER_DIM
  ctx.lineWidth = 3
  for (const [x, y, dx, dy] of [
    [0.3, 0.3, 1, 1],
    [0.7, 0.3, -1, 1],
    [0.3, 0.7, 1, -1],
    [0.7, 0.7, -1, -1],
  ]) {
    ctx.beginPath()
    ctx.moveTo(W * x, H * y + dy * H * 0.06)
    ctx.lineTo(W * x, H * y)
    ctx.lineTo(W * x + dx * W * 0.05, H * y)
    ctx.stroke()
  }

  // Heading tape: compass degrees, 0 at the bow.
  const heading = ((((-droid.yaw * 180) / Math.PI) % 360) + 360) % 360
  const tapeY = H * 0.84
  ctx.strokeStyle = AMBER
  ctx.fillStyle = AMBER
  ctx.lineWidth = 2
  ctx.font = `bold ${Math.round(H * 0.04)}px ui-monospace, Menlo, monospace`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'top'
  for (let d = Math.ceil((heading - 60) / 15) * 15; d <= heading + 60; d += 15) {
    const x = W / 2 + ((d - heading) / 60) * W * 0.3
    const major = d % 45 === 0
    ctx.beginPath()
    ctx.moveTo(x, tapeY)
    ctx.lineTo(x, tapeY + (major ? H * 0.03 : H * 0.015))
    ctx.stroke()
    if (major) ctx.fillText(['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][(((d / 45) % 8) + 8) % 8], x, tapeY + H * 0.035)
  }
  ctx.beginPath()
  ctx.moveTo(W / 2, tapeY - H * 0.005)
  ctx.lineTo(W / 2 - H * 0.015, tapeY - H * 0.03)
  ctx.lineTo(W / 2 + H * 0.015, tapeY - H * 0.03)
  ctx.closePath()
  ctx.fill()
  ctx.textAlign = 'left'
  textLines(ctx, [`SPD ${Math.abs(droid.speed).toFixed(1)}`], { size: 0.045, y: 0.9, x: 0.05, color: AMBER_DIM })
  textLines(ctx, [`HDG ${String(Math.round(heading) % 360).padStart(3, '0')}`], { size: 0.045, y: 0.9, x: 0.78, color: AMBER_DIM })

  // The scan of pod six.
  if (scan >= 0) {
    const done = scan >= 1
    const label = done ? (blink ? 'NO LIFE SIGNS' : '') : droidOnPodSix() ? 'SCANNING POD 06' : 'TARGET LOST'
    textLines(ctx, [label], { size: 0.055, y: 0.18, x: 0.3, color: done ? '#ffb040' : AMBER })
    ctx.strokeStyle = AMBER
    ctx.strokeRect(W * 0.3, H * 0.27, W * 0.4, H * 0.035)
    ctx.fillStyle = AMBER
    ctx.fillRect(W * 0.3, H * 0.27, W * 0.4 * Math.min(1, scan), H * 0.035)
  }
}

// The steward: an iris that opens with its voice, over the voice's trace.
function drawSteward(ctx: CanvasRenderingContext2D) {
  const { width: W, height: H } = ctx.canvas
  clear(ctx)
  textLines(ctx, ['STEWARD', 'SHIP INTELLIGENCE'], { size: 0.055, y: 0.05, gap: 1.3 })
  const level = voiceLevel()
  const cx = W / 2
  const cy = H * 0.47
  ctx.strokeStyle = AMBER
  ctx.shadowColor = AMBER
  ctx.lineWidth = 3
  ctx.shadowBlur = 10
  for (const [r, a] of [
    [0.2, 0.35],
    [0.15, 0.6],
  ]) {
    ctx.globalAlpha = a
    ctx.beginPath()
    ctx.arc(cx, cy, H * r, 0, Math.PI * 2)
    ctx.stroke()
  }
  ctx.globalAlpha = 1
  ctx.fillStyle = AMBER
  ctx.shadowBlur = 24
  ctx.beginPath()
  ctx.arc(cx, cy, H * (0.04 + level * 0.07 + 0.005 * Math.sin(performance.now() / 700)), 0, Math.PI * 2)
  ctx.fill()
  ctx.shadowBlur = 6
  // The voice trace.
  const wave = voiceWave()
  const y0 = H * 0.82
  ctx.lineWidth = 2
  ctx.beginPath()
  const n = 96
  for (let k = 0; k <= n; k++) {
    const sample = wave ? wave[Math.floor((k / n) * (wave.length - 1))] : 0
    const x = W * 0.08 + (k / n) * W * 0.84
    const y = y0 - sample * H * 0.5
    if (k) ctx.lineTo(x, y)
    else ctx.moveTo(x, y)
  }
  ctx.stroke()
  ctx.shadowBlur = 0
}
