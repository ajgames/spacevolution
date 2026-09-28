import { useCursor } from '@react-three/drei'
import { type ThreeEvent, useFrame } from '@react-three/fiber'
import { useMemo, useRef, useState } from 'react'
import { AdditiveBlending, Box3, Color, type Mesh, MeshBasicMaterial, Vector3 } from 'three'
import { type Hotspot, SPOTS } from './nodes.ts'
import { findObject, meshesOf, useRooms } from './objects.ts'
import { act, isActive, useDemo } from './store.ts'

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

// Clicks land on invisible boxes rather than the ship's meshes: raycasting a
// few boxes is cheap, where raycasting every mesh in four rooms on each
// pointer move is not. Boxes come from the objects' rest pose, so a door's
// hotspot stays in the doorway after the door slides away.
export default function Hotspots() {
  const rooms = useRooms()
  const state = useDemo()
  const [hovered, setHovered] = useState<string | null>(null)

  const boxes = useMemo(() => {
    const map = new Map<string, Box3>()
    for (const spot of Object.values(SPOTS)) {
      for (const h of spot.hotspots) {
        if (map.has(h.id)) continue
        if (h.kind === 'go' && h.area) {
          map.set(h.id, new Box3().setFromCenterAndSize(new Vector3(...h.area.center), new Vector3(...h.area.size)))
          continue
        }
        const box = new Box3()
        for (const name of h.objects ?? []) {
          const object = findObject(rooms, name)
          object.updateWorldMatrix(true, true)
          box.union(new Box3().setFromObject(object))
        }
        map.set(h.id, box.expandByScalar(0.015))
      }
    }
    return map
  }, [rooms])

  const active = SPOTS[state.spot].hotspots.filter((h) => isActive(h, state))
  // A hotspot that stops being clickable stops being hovered too.
  const hoveredSpot = active.find((h) => h.id === hovered)
  useCursor(hoveredSpot !== undefined)

  const click = (h: Hotspot) => (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation()
    if (e.delta > 6) return // a drag, not a click
    setHovered(null)
    act.hotspot(h)
  }

  return (
    <>
      {active.map((h) => {
        const box = boxes.get(h.id)!
        return (
          <mesh
            key={`${state.spot}:${h.id}`}
            position={box.getCenter(new Vector3())}
            onPointerOver={(e) => {
              e.stopPropagation()
              setHovered(h.id)
            }}
            onPointerOut={() => setHovered((id) => (id === h.id ? null : id))}
            onClick={click(h)}
          >
            <boxGeometry args={box.getSize(new Vector3()).toArray()} />
            <meshBasicMaterial visible={false} />
          </mesh>
        )
      })}
      {hoveredSpot?.objects && <Glow names={hoveredSpot.objects} />}
      {hoveredSpot?.kind === 'go' && hoveredSpot.area && (
        <mesh position={[hoveredSpot.area.center[0], 0.03, hoveredSpot.area.center[2]]} rotation-x={-Math.PI / 2}>
          <ringGeometry args={[0.32, 0.42, 48]} />
          <meshBasicMaterial color="#f0a040" transparent opacity={0.45} toneMapped={false} depthWrite={false} />
        </mesh>
      )}
    </>
  )
}

// An additive amber copy of the hovered objects, following them as they move.
function Glow({ names }: { names: string[] }) {
  const rooms = useRooms()
  const meshes = useMemo(() => names.flatMap((name) => meshesOf(findObject(rooms, name))), [rooms, names])
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
