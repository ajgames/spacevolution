import { useFrame } from '@react-three/fiber'
import { useLayoutEffect, useRef } from 'react'
import type { MeshStandardMaterial } from 'three'
import { EMISSIVE_ROLES, type LightingState, ROLES_ON } from './shipData.ts'
import { type ShipRoom, standardMaterials } from './useShip.ts'

type ShipRoomsProps = {
  rooms: ShipRoom[]
  lighting: LightingState
  // The engineering wall button: blinking once a second, steady, or dark.
  blink?: 'blink' | 'steady' | 'off'
  // Emergency lighting swells with the rotating alarm beacons (0.5 Hz).
  pulse?: boolean
}

// Every material in a room shares that room's lightmap atlas for the current
// lighting state, at the intensity the manifest gives it. Emissive materials
// switch by role, the same way the bake switched them.
export default function ShipRooms({ rooms, lighting, blink = 'blink', pulse = false }: ShipRoomsProps) {
  const lit = useRef<{ materials: MeshStandardMaterial[]; intensity: number }[]>([])

  useLayoutEffect(() => {
    lit.current = rooms.map((room) => {
      const lightMap = room.lightmaps[lighting] ?? null
      const intensity = room.info.lightmaps[lighting]?.lightMapIntensity ?? 1
      // Traversed here rather than once, so materials cloned per object are included.
      const materials = standardMaterials(room.scene)
      for (const m of materials) {
        if (!m.lightMap !== !lightMap) m.needsUpdate = true // lightmap on/off changes the shader
        m.lightMap = lightMap
        m.lightMapIntensity = intensity
        m.userData.baseEmissive ??= m.emissiveIntensity
        const role = EMISSIVE_ROLES[m.name]
        if (role) m.emissiveIntensity = ROLES_ON[lighting].includes(role) ? m.userData.baseEmissive : 0
      }
      return { materials, intensity }
    })
  }, [rooms, lighting])

  useFrame(({ clock }) => {
    const t = clock.elapsedTime
    const on = blink === 'steady' || (blink === 'blink' && Math.sin(t * Math.PI * 2) > 0)
    const swell = pulse && lighting === 'emergency' ? 0.8 + 0.2 * Math.sin(t * Math.PI) : 1
    for (const { materials, intensity } of lit.current) {
      for (const m of materials) {
        if (m.name === 'MAT_emit_blink') m.emissiveIntensity = (on ? 1 : blink === 'off' ? 0.03 : 0.08) * m.userData.baseEmissive
        m.lightMapIntensity = intensity * swell
      }
    }
  })

  return (
    <>
      {rooms.map((room) => (
        <primitive key={room.name} object={room.scene} />
      ))}
    </>
  )
}

