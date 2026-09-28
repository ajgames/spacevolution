import { useFrame, useThree } from '@react-three/fiber'
import { useLayoutEffect, useRef } from 'react'
import { MathUtils, Matrix4, type PerspectiveCamera, Quaternion, Vector3 } from 'three'
import { SPOTS, type SpotId } from './nodes.ts'
import { act, useDemo } from './store.ts'

const UP = new Vector3(0, 1, 0)
const DEFAULT_FOV = 65

function pose(spotId: SpotId, facing: number) {
  const spot = SPOTS[spotId]
  const { heading, pitch = 0 } = spot.facings[facing]
  const h = MathUtils.degToRad(heading)
  const p = MathUtils.degToRad(pitch)
  const position = new Vector3(...spot.at)
  const direction = new Vector3(Math.sin(h) * Math.cos(p), Math.sin(p), -Math.cos(h) * Math.cos(p))
  const quaternion = new Quaternion().setFromRotationMatrix(
    new Matrix4().lookAt(position, position.clone().add(direction), UP),
  )
  return { position, quaternion, fov: spot.fov ?? DEFAULT_FOV }
}

const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2)

type Tween = {
  from: { position: Vector3; quaternion: Quaternion; fov: number }
  to: ReturnType<typeof pose>
  t: number
  duration: number
}

// Eases the camera to whichever spot and facing the store names. There's no
// free movement: the camera only ever rests on a node.
export default function NodeCamera() {
  const camera = useThree((state) => state.camera) as PerspectiveCamera
  const spot = useDemo((s) => s.spot)
  const facing = useDemo((s) => s.facing)
  const generation = useDemo((s) => s.generation)
  const tween = useRef<Tween | null>(null)
  const placed = useRef(-1)

  useLayoutEffect(() => {
    const to = pose(spot, facing)
    if (placed.current !== generation) {
      placed.current = generation
      tween.current = null
      act.setMoving(false)
      camera.position.copy(to.position)
      camera.quaternion.copy(to.quaternion)
      camera.fov = to.fov
      camera.updateProjectionMatrix()
      return
    }
    const distance = camera.position.distanceTo(to.position)
    tween.current = {
      from: { position: camera.position.clone(), quaternion: camera.quaternion.clone(), fov: camera.fov },
      to,
      t: 0,
      duration: distance > 0.01 ? Math.min(2.6, 0.9 + distance * 0.35) : 0.7,
    }
    act.setMoving(true)
  }, [camera, spot, facing, generation])

  useFrame((_, dt) => {
    const tw = tween.current
    if (!tw) return
    tw.t = Math.min(1, tw.t + dt / tw.duration)
    const e = ease(tw.t)
    camera.position.lerpVectors(tw.from.position, tw.to.position, e)
    camera.quaternion.slerpQuaternions(tw.from.quaternion, tw.to.quaternion, e)
    camera.fov = MathUtils.lerp(tw.from.fov, tw.to.fov, e)
    camera.updateProjectionMatrix()
    if (tw.t === 1) {
      tween.current = null
      act.setMoving(false)
    }
  })

  return null
}
