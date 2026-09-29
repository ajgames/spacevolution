import { useFrame } from '@react-three/fiber'
import { useLayoutEffect, useMemo, useRef } from 'react'
import { AdditiveBlending, type Mesh, MeshBasicMaterial, Vector3 } from 'three'
import { useRooms } from '../demo/objects.ts'
import { extras } from './space.ts'
import { buttonsPressedAt } from './store.ts'
import { findDoorButtons } from './world.ts'

const FLASH_MS = 450

// The door panel buttons are baked into the walls, so each gets a box of its
// own over it: the crosshair aims at it, the hover glow outlines it, sounds
// play from it (all by name, through extras), and it flashes when pressed.
export default function DoorButtons() {
  const rooms = useRooms()
  const buttons = useMemo(
    () =>
      findDoorButtons(rooms).map(({ name, box }) => ({
        name,
        center: box.getCenter(new Vector3()),
        size: box.getSize(new Vector3()),
        material: new MeshBasicMaterial({
          color: '#ffb050',
          transparent: true,
          opacity: 0,
          blending: AdditiveBlending,
          depthWrite: false,
          toneMapped: false,
        }),
      })),
    [rooms],
  )
  const meshes = useRef<(Mesh | null)[]>([])

  useLayoutEffect(() => {
    buttons.forEach((button, i) => extras.set(button.name, meshes.current[i]!))
    return () => {
      for (const button of buttons) {
        extras.delete(button.name)
        button.material.dispose()
      }
    }
  }, [buttons])

  useFrame(() => {
    const now = performance.now()
    buttons.forEach((button, i) => {
      const since = now - (buttonsPressedAt[button.name] ?? -Infinity)
      const flash = since < FLASH_MS ? 1 - since / FLASH_MS : 0
      button.material.opacity = flash * 0.9
      // Hidden between presses; kept mounted so its shader is built at load.
      meshes.current[i]!.visible = flash > 0
    })
  })

  return (
    <>
      {buttons.map((button, i) => (
        <mesh
          key={button.name}
          ref={(mesh) => {
            meshes.current[i] = mesh
          }}
          position={button.center}
          material={button.material}
          visible={false}
        >
          <boxGeometry args={button.size.toArray()} />
        </mesh>
      ))}
    </>
  )
}
