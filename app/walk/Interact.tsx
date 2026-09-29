import { useFrame, useThree } from '@react-three/fiber'
import { useMemo, useRef } from 'react'
import { AdditiveBlending, Box3, Color, type Mesh, MeshBasicMaterial, type Object3D, Ray, Vector3 } from 'three'
import { meshesOf, useRooms } from '../demo/objects.ts'
import { useDemo } from '../demo/store.ts'
import { lookUp } from './space.ts'
import { useWalk, walkAct } from './store.ts'
import { TARGETS } from './targets.ts'

// Finds what the crosshair is on each frame: a ray from the eye against each
// usable target's box (taken at rest, like the demo's hotspots, so a door
// stays aimable in its doorway), nearest within reach. Highlights it.
export default function Interact() {
  const rooms = useRooms()
  const camera = useThree((state) => state.camera)
  const boxes = useRef(new Map<string, Box3>())
  const ray = useMemo(() => new Ray(), [])
  const hit = useMemo(() => new Vector3(), [])

  const boxOf = ({ object, pad = 0.015 }: (typeof TARGETS)[number]) => {
    let box = boxes.current.get(object)
    if (!box) {
      const found = lookUp(rooms, object)
      if (!found) return null
      found.updateWorldMatrix(true, true)
      box = new Box3().setFromObject(found).expandByScalar(pad)
      boxes.current.set(object, box)
    }
    return box
  }

  useFrame(() => {
    const demo = useDemo.getState()
    const walk = useWalk.getState()
    if (!demo.started || !walk.locked || walk.ended) return walkAct.setHover(null)
    ray.origin.copy(camera.position)
    camera.getWorldDirection(ray.direction)
    let best: (typeof TARGETS)[number] | null = null
    let nearest = Infinity
    for (const target of TARGETS) {
      if (!target.active(demo, walk)) continue
      const box = boxOf(target)
      if (!box || !ray.intersectBox(box, hit)) continue
      const distance = hit.distanceTo(ray.origin)
      if (distance <= target.reach && distance < nearest) {
        best = target
        nearest = distance
      }
    }
    walkAct.setHover(best && { id: best.id, label: best.label, info: best.info })
  })

  const hover = useWalk((s) => s.hover)
  const object = hover && !hover.info ? lookUp(rooms, TARGETS.find((t) => t.id === hover.id)!.object) : undefined
  return object ? <Glow object={object} /> : null
}

const GLOW = new MeshBasicMaterial({
  color: new Color(1, 0.5, 0.12),
  transparent: true,
  opacity: 0.28,
  blending: AdditiveBlending,
  depthWrite: false,
  polygonOffset: true,
  polygonOffsetFactor: -2,
  polygonOffsetUnits: -2,
  toneMapped: false,
})

// An additive amber copy of the aimed-at object, following it as it moves.
function Glow({ object }: { object: Object3D }) {
  const meshes = useMemo(() => meshesOf(object), [object])
  const copies = useRef<(Mesh | null)[]>([])
  useFrame(() => {
    meshes.forEach((mesh, i) => copies.current[i]?.matrix.copy(mesh.matrixWorld))
  })
  return (
    <>
      {meshes.map((mesh, i) => (
        <mesh
          key={mesh.uuid}
          ref={(copy) => {
            copies.current[i] = copy
          }}
          geometry={mesh.geometry}
          material={GLOW}
          matrixAutoUpdate={false}
          matrix={mesh.matrixWorld}
          renderOrder={2}
        />
      ))}
    </>
  )
}
