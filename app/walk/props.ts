import { useThree } from '@react-three/fiber'
import { useLayoutEffect } from 'react'
import { MeshStandardMaterial, type MeshStandardMaterialParameters } from 'three'
import type { LightingState } from '../scene/shipData.ts'

// Materials for the props the walk mode adds (droid, joystick, speakers). The
// ship is lit by its baked lightmaps and has no lights, so these take their
// light from the scene's environment, turned up or down with the ship's lighting.

const ENV: Record<LightingState, number> = { normal: 0.55, emergency: 0.06, blackout: 0.025 }
const materials = new Set<MeshStandardMaterial>()

export function propMaterial(parameters: MeshStandardMaterialParameters) {
  const material = new MeshStandardMaterial(parameters)
  materials.add(material)
  return material
}

// Mount after <Reflections>, which creates the environment in its own layout effect.
export function PropLighting({ lighting }: { lighting: LightingState }) {
  const scene = useThree((state) => state.scene)
  useLayoutEffect(() => {
    for (const m of materials) {
      if (m.envMap !== scene.environment) m.needsUpdate = true
      m.envMap = scene.environment
      m.envMapIntensity = ENV[lighting]
    }
  }, [scene, lighting])
  return null
}
