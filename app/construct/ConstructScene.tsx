import { OrbitControls } from '@react-three/drei'
import { useFrame } from '@react-three/fiber'
import { type ComponentRef, Suspense, useMemo, useRef } from 'react'
import { CanvasTexture, type Mesh, type MeshBasicMaterial, Vector3 } from 'three'
import Caretaker from './Caretaker.tsx'
import { body, ground } from './store.ts'

// An endless white room. There is no floor mesh: the background is the floor,
// and the only sign of the ground is soft shadow under him (a lit white plane
// would tone-map to grey and show a horizon line).

const CHEST = 1.05 // the camera orbits this height
const DEAD_ZONE = 0.9 // metres he can move off-centre before the camera turns after him
const NEAR = 2.2 // closest he may come to the lens
const step = new Vector3()

export default function ConstructScene() {
  const controls = useRef<ComponentRef<typeof OrbitControls>>(null)

  // The camera stays put and turns lazily after him. With nothing else in the
  // room, a camera that travelled with him would make every walk look like a
  // treadmill; this way he crosses the frame.
  useFrame((state, delta) => {
    const c = controls.current
    if (!c) return
    const dt = Math.min(delta, 0.1)
    step.set(body.x - c.target.x, 0, body.z - c.target.z)
    const off = step.length()
    if (off > DEAD_ZONE) c.target.addScaledVector(step, ((off - DEAD_ZONE) / off) * (1 - Math.exp(-dt / 0.6)))
    // Back off if he walks at the lens.
    step.set(state.camera.position.x - body.x, 0, state.camera.position.z - body.z)
    const near = step.length()
    if (near < NEAR && near > 1e-3) state.camera.position.addScaledVector(step, (NEAR - near) / near)
    c.update()
  })

  return (
    <>
      <color attach="background" args={['#ffffff']} />
      <hemisphereLight args={['#ffffff', '#d9d9d9', 1.9]} />
      <directionalLight position={[2.5, 5, 4]} intensity={2.1} />
      <directionalLight position={[-3, 2.5, -4]} intensity={0.9} />
      <GroundShadows />
      <Suspense fallback={null}>
        <Caretaker />
      </Suspense>
      <OrbitControls
        ref={controls}
        makeDefault
        target={[0, CHEST, 0]}
        enablePan={false}
        minDistance={1.6}
        maxDistance={9}
        maxPolarAngle={Math.PI * 0.495}
      />
    </>
  )
}

// Blob shadows: a wide soft one under the hips and a tighter one under each foot,
// each fading as what casts it leaves the ground (a jump, a lifted foot).
const BLOBS = [
  { size: [1.0, 0.75], opacity: 0.2, fade: 1.2 },
  { size: [0.16, 0.3], opacity: 0.34, fade: 0.22 }, // long along the foot
  { size: [0.16, 0.3], opacity: 0.34, fade: 0.22 },
] as const

function blobTexture() {
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = 128
  const ctx = canvas.getContext('2d')!
  const g = ctx.createRadialGradient(64, 64, 0, 64, 64, 64)
  g.addColorStop(0, 'rgba(0,0,0,1)')
  g.addColorStop(0.45, 'rgba(0,0,0,0.55)')
  g.addColorStop(1, 'rgba(0,0,0,0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, 128, 128)
  return new CanvasTexture(canvas)
}

function GroundShadows() {
  const texture = useMemo(() => blobTexture(), [])
  const blobs = useRef<(Mesh | null)[]>([])
  useFrame(() => {
    const sources = [ground.hips, ...ground.feet]
    blobs.current.forEach((mesh, i) => {
      if (!mesh) return
      const p = sources[i]
      const lift = i === 0 ? p.y - 0.93 : p.y - 0.04 // height above where it rests when standing
      mesh.position.set(p.x, 0.001 + i * 0.0005, p.z)
      mesh.rotation.z = ground.yaw
      ;(mesh.material as MeshBasicMaterial).opacity = BLOBS[i].opacity * Math.max(0, 1 - Math.max(0, lift) / BLOBS[i].fade)
    })
  })
  return (
    <>
      {BLOBS.map((b, i) => (
        <mesh
          key={i}
          ref={(m) => {
            blobs.current[i] = m
          }}
          rotation-x={-Math.PI / 2}
          renderOrder={1}
        >
          <planeGeometry args={[b.size[0], b.size[1]]} />
          <meshBasicMaterial map={texture} transparent depthWrite={false} toneMapped={false} />
        </mesh>
      ))}
    </>
  )
}
