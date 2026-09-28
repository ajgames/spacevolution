import { useFBO } from '@react-three/drei'
import { useFrame } from '@react-three/fiber'
import { useLayoutEffect, useMemo, useRef } from 'react'
import { CanvasTexture, type Group, MathUtils, type Mesh, MeshBasicMaterial, PerspectiveCamera, SRGBColorSpace } from 'three'
import { sfx } from './audio.ts'
import {
  AMBER,
  AMBER_DIM,
  canvasScreen,
  clear,
  crtMaterial,
  drawShipMap,
  drawStandby,
  textLines,
} from './crt.ts'
import { FACING_OUT_OF_RACK, findObject, rackPoint, useRooms } from './objects.ts'
import { FAILING_POD, SCREEN_BOOT_MS, atLeast, useDemo } from './store.ts'

const failingPodNumber = Number(FAILING_POD.slice(-2))
const secondsSince = (at: number | undefined) => (at === undefined ? -1 : (performance.now() - at) / 1000)
// Canvases redraw a few times a second, not every frame.
const tick = (fps: number) => Math.floor(performance.now() / (1000 / fps))

// --- command workstation: SCREEN_status, SCREEN_mission, SCREEN_aux -------

const AUX_LOG = [
  'SYS LOG',
  'PRIMARY BUS ..... ONLINE',
  'BREAKERS ........ CLOSED',
  'LIFE SUPPORT .... NOMINAL',
  `CRYO ${String(failingPodNumber).padStart(2, '0')} ......... FAULT`,
  'DROID D-7 ....... DOCKED',
  'TAPE TRANSPORT .. CUED',
]

export function CommandScreens() {
  const rooms = useRooms()
  // The droid's live feed renders into this target, then onto SCREEN_mission.
  const feed = useFBO(320, 240)
  const droidEye = useMemo(() => {
    const cam = new PerspectiveCamera(72, 4 / 3, 0.05, 40)
    const dock = findObject(rooms, 'SPAWN_droid').position
    cam.position.set(dock.x, dock.y + 0.45, dock.z)
    cam.lookAt(dock.x, 1.0, -6) // up the stem toward command
    return cam
  }, [rooms])

  const screens = useMemo(() => {
    const screen = (name: string, withFeed: boolean) => {
      const mesh = findObject(rooms, name) as Mesh
      const canvas = canvasScreen(512, 384, false)
      const material = crtMaterial(canvas.texture, 150, withFeed ? feed.texture : undefined)
      return { mesh, canvas, material, drawn: -1 }
    }
    return [screen('SCREEN_status', false), screen('SCREEN_mission', true), screen('SCREEN_aux', false)]
  }, [rooms, feed])

  useLayoutEffect(() => {
    const original = screens.map((s) => s.mesh.material)
    for (const s of screens) s.mesh.material = s.material
    return () => screens.forEach((s, i) => (s.mesh.material = original[i]))
  }, [screens])

  useFrame(({ gl, scene, clock }) => {
    const { phase, enteredAt } = useDemo.getState()
    const powered = atLeast(phase, 'powered')
    const since = secondsSince(enteredAt.powered)
    const frame = tick(8)
    screens.forEach((s, i) => {
      const u = s.material.uniforms
      u.time.value = clock.elapsedTime
      const boot = powered ? (since - SCREEN_BOOT_MS[i] / 1000) / 0.8 : 1
      u.power.value = Math.min(1, Math.max(0, boot))
      u.brightness.value = powered ? 2.4 : 1.1
      if (s.drawn === frame) return
      s.drawn = frame
      const { ctx } = s.canvas
      const blink = frame % 8 < 4
      if (!powered || boot <= 0) drawStandby(ctx, i === 1 ? 'NO SIGNAL' : 'STANDBY', blink)
      else if (i === 0) drawShipMap(ctx, failingPodNumber, frame % 4 < 2)
      else if (i === 1) drawMissionOverlay(ctx, blink, since)
      else {
        clear(ctx)
        const shown = Math.min(AUX_LOG.length, Math.floor((since - SCREEN_BOOT_MS[2] / 1000) * 3))
        textLines(ctx, AUX_LOG.slice(0, shown), { size: 0.06, y: 0.08, gap: 1.6 })
      }
      s.canvas.texture.needsUpdate = true
    })

    // Only while the screens can be seen. The mission screen is hidden while
    // the feed renders, or it would sample the texture being drawn into.
    const { spot } = useDemo.getState()
    if (powered && (spot === 'command' || spot === 'console')) {
      const mission = screens[1].mesh
      mission.visible = false
      gl.setRenderTarget(feed)
      gl.render(scene, droidEye)
      gl.setRenderTarget(null)
      mission.visible = true
    }
  })
  return null
}

function drawMissionOverlay(ctx: CanvasRenderingContext2D, blink: boolean, since: number) {
  const { width: W, height: H } = ctx.canvas
  ctx.fillStyle = '#000000'
  ctx.fillRect(0, 0, W, H)
  textLines(ctx, ['MISSION F.P.P.', 'DROID D-7 // DOCK A'], { size: 0.05, y: 0.05, gap: 1.3 })
  if (blink) {
    ctx.fillStyle = '#ff4020'
    ctx.beginPath()
    ctx.arc(W * 0.8, H * 0.085, H * 0.018, 0, Math.PI * 2)
    ctx.fill()
  }
  textLines(ctx, ['LIVE'], { size: 0.05, y: 0.06, x: 0.83 })
  const t = Math.max(0, since)
  const stamp = `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(Math.floor(t % 60)).padStart(2, '0')}:${String(Math.floor((t * 24) % 24)).padStart(2, '0')}`
  textLines(ctx, [`T+ ${stamp}`], { size: 0.045, y: 0.9, color: AMBER_DIM })
  // corner brackets of the camera reticle
  ctx.strokeStyle = AMBER_DIM
  ctx.lineWidth = 3
  for (const [x, y, dx, dy] of [
    [0.3, 0.35, 1, 1],
    [0.7, 0.35, -1, 1],
    [0.3, 0.75, 1, -1],
    [0.7, 0.75, -1, -1],
  ]) {
    ctx.beginPath()
    ctx.moveTo(W * x, H * y + dy * H * 0.06)
    ctx.lineTo(W * x, H * y)
    ctx.lineTo(W * x + dx * W * 0.05, H * y)
    ctx.stroke()
  }
}

// --- engineering: the core monitor on CORE_rack_03 -------------------------

const FAULT = [
  'CORE MONITOR 2.1',
  '----------------',
  'BACKUP POWER 12%',
  'PRIMARY BUS FAULT',
  'BREAKERS TRIPPED',
  '',
  '> MATCH CORE MATRIX',
  '  AT COMMAND CONSOLE',
]
const ONLINE = ['CORE MONITOR 2.1', '----------------', 'PRIMARY BUS ONLINE', 'POWER 100%', 'BREAKERS CLOSED', '']

// An overlay on the rack's baked CRT (0.46 x 0.34 m, build_props.py rack_cartridge).
export function CoreCrt() {
  const canvas = useMemo(() => canvasScreen(512, 378, true), [])
  const material = useMemo(() => crtMaterial(canvas.texture, 130), [canvas])
  const drawn = useRef({ frame: -1, chars: 0 })

  useFrame(({ clock }) => {
    const { phase, enteredAt } = useDemo.getState()
    const u = material.uniforms
    u.time.value = clock.elapsedTime
    const since = secondsSince(enteredAt.emergency)
    const awake = since >= 0
    u.power.value = awake ? Math.min(1, Math.max(0, (since - 0.9) / 0.7)) : 1
    u.brightness.value = awake ? 2.2 : 1
    const frame = tick(20)
    if (drawn.current.frame === frame) return
    drawn.current.frame = frame
    const { ctx } = canvas
    const blink = frame % 16 < 8
    if (!awake) drawStandby(ctx, 'CORE MONITOR', blink)
    else if (!atLeast(phase, 'powered')) {
      // Type the fault out once the tube has warmed up, with a teletype tick per character.
      const text = FAULT.join('\n')
      const chars = Math.max(0, Math.min(text.length, Math.floor((since - 1.8) * 24)))
      if (chars > drawn.current.chars && text[chars - 1]?.trim()) sfx.type()
      drawn.current.chars = chars
      clear(ctx)
      const lines = text.slice(0, chars).split('\n')
      if (chars === text.length && blink) lines[lines.length - 1] += ' _'
      textLines(ctx, lines, { size: 0.07, y: 0.07, gap: 1.35 })
    } else {
      clear(ctx)
      const tape = phase === 'tapePlaying' ? (blink ? '> TAPE 2: PLAYBACK' : '') : '> TAPE 2: CUED'
      textLines(ctx, [...ONLINE, tape], { size: 0.07, y: 0.07, gap: 1.35 })
    }
    canvas.texture.needsUpdate = true
  })

  return (
    <mesh position={rackPoint('CORE_rack_03', 0, 0.004, 1.84)} rotation={FACING_OUT_OF_RACK} material={material}>
      <planeGeometry args={[0.46, 0.34]} />
    </mesh>
  )
}

// --- engineering: the lamp matrix on CORE_rack_02 --------------------------

// Eight columns, one per breaker, over the rack's baked lamp panel. Lit columns
// are the breakers that must be closed; the rest are tripped.
export function LampMatrix() {
  const canvas = useMemo(() => canvasScreen(256, 296, true), [])
  const material = useMemo(() => {
    const m = new MeshBasicMaterial({ map: canvas.texture })
    m.color.setScalar(1.6) // lamps read as lit next to the baked emissives
    return m
  }, [canvas])
  const drawn = useRef(-1)

  useFrame(() => {
    const frame = tick(12)
    if (drawn.current === frame) return
    drawn.current = frame
    const { phase, pattern, stutter } = useDemo.getState()
    const { ctx } = canvas
    const W = ctx.canvas.width
    const H = ctx.canvas.height
    ctx.fillStyle = '#0b0c0c'
    ctx.fillRect(0, 0, W, H)
    for (let c = 0; c < 8; c++) {
      for (let r = 0; r < 8; r++) {
        let lit = phase === 'blackout' ? false : atLeast(phase, 'powered') ? true : pattern[c]
        if (stutter) lit = Math.random() < 0.5
        const x = W * (0.075 + c * 0.1225)
        const y = H * (0.07 + r * 0.115)
        const w = W * 0.085
        const h = H * 0.06
        if (lit) {
          const flicker = 0.85 + Math.random() * 0.15
          ctx.shadowColor = AMBER
          ctx.shadowBlur = 10
          ctx.fillStyle = `rgba(255, ${Math.round(170 * flicker)}, ${Math.round(70 * flicker)}, 1)`
        } else {
          ctx.shadowBlur = 0
          ctx.fillStyle = '#1c1409'
        }
        ctx.fillRect(x, y, w, h)
      }
    }
    ctx.shadowBlur = 0
    canvas.texture.needsUpdate = true
  })

  return (
    <mesh position={rackPoint('CORE_rack_02', 0, 0.013, 1.74)} rotation={FACING_OUT_OF_RACK} material={material}>
      <planeGeometry args={[0.64, 0.74]} />
    </mesh>
  )
}

// --- engineering: the reel-to-reel on CORE_rack_04 --------------------------

function reelTexture() {
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 256
  const ctx = canvas.getContext('2d')!
  const c = 128
  ctx.fillStyle = '#3a3633' // flange
  ctx.beginPath()
  ctx.arc(c, c, 127, 0, Math.PI * 2)
  ctx.fill()
  ctx.fillStyle = '#1c1511' // tape pack showing through the flange windows
  for (let k = 0; k < 3; k++) {
    const a = (k * Math.PI * 2) / 3
    ctx.beginPath()
    ctx.moveTo(c, c)
    ctx.arc(c, c, 108, a + 0.35, a + (Math.PI * 2) / 3 - 0.35)
    ctx.closePath()
    ctx.fill()
  }
  ctx.fillStyle = '#4a4540' // hub
  ctx.beginPath()
  ctx.arc(c, c, 30, 0, Math.PI * 2)
  ctx.fill()
  ctx.fillStyle = '#101010'
  ctx.fillRect(c - 4, c - 22, 8, 16) // hub key, so the spin reads
  const texture = new CanvasTexture(canvas)
  texture.colorSpace = SRGBColorSpace
  return texture
}

// The tape rack's reels are part of its static mesh, so turning ones sit over
// them once the tape starts playing on its own.
export function TapeReels() {
  const phase = useDemo((s) => s.phase)
  const material = useMemo(() => new MeshBasicMaterial({ map: reelTexture(), transparent: true }), [])
  const reels = useRef<(Group | null)[]>([])
  const speed = useRef(0)
  useFrame((_, dt) => {
    speed.current = MathUtils.damp(speed.current, useDemo.getState().phase === 'tapePlaying' ? 5 : 0, 1.5, dt)
    reels.current.forEach((reel, i) => {
      if (reel) reel.rotation.z -= speed.current * dt * (i === 0 ? 1 : 0.8)
    })
  })
  if (!atLeast(phase, 'tapePlaying')) return null
  return (
    <>
      {[0.14, -0.14].map((lx, i) => (
        <group key={lx} position={rackPoint('CORE_rack_04', lx, 0.038, 1.76)} rotation={FACING_OUT_OF_RACK}>
          <group
            ref={(reel) => {
              reels.current[i] = reel
            }}
          >
            <mesh material={material}>
              <circleGeometry args={[0.121, 48]} />
            </mesh>
          </group>
        </group>
      ))}
    </>
  )
}
