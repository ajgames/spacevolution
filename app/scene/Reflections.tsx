import { useThree } from '@react-three/fiber'
import { useEffect, useLayoutEffect } from 'react'
import { PMREMGenerator } from 'three'
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js'

// Faint environment reflections so metal edges read. The bake does the lighting.
export default function Reflections({ intensity }: { intensity: number }) {
  const gl = useThree((state) => state.gl)
  const scene = useThree((state) => state.scene)

  // A layout effect, so the environment is in place before any effect
  // precompiles shaders (warmUp.ts): an env map changes the shader.
  useLayoutEffect(() => {
    const pmrem = new PMREMGenerator(gl)
    const room = new RoomEnvironment()
    const env = pmrem.fromScene(room, 0.04).texture
    scene.environment = env
    return () => {
      scene.environment = null
      env.dispose()
      room.dispose()
      pmrem.dispose()
    }
  }, [gl, scene])

  useEffect(() => {
    scene.environmentIntensity = intensity
  }, [scene, intensity])

  return null
}
