import { useThree } from '@react-three/fiber'
import { useEffect } from 'react'
import { type Camera, Mesh, type Object3D, ShaderMaterial, type Texture, type WebGLRenderTarget, type WebGLRenderer } from 'three'
import type { ShipRoom } from './useShip.ts'

// three.js compiles a material's shader and uploads its textures the first
// time the material is drawn, and that frame stalls until both are done: here,
// on each new camera view and lighting change. Chrome on Windows compiles
// through Direct3D, which is several times slower. These do the work up front,
// while nothing is moving.

// Uploads every texture the scene's materials use, plus any extras (textures
// swapped in later, like other lighting states' lightmaps). Synchronous: image
// decode and upload happen here, on the main thread. Returns how many.
export function uploadTextures(gl: WebGLRenderer, root: Object3D, extra: Texture[] = []) {
  const textures = new Set(extra)
  root.traverse((object) => {
    if (!(object instanceof Mesh)) return
    for (const material of [object.material].flat()) {
      const values: unknown[] = Object.values(material)
      if (material instanceof ShaderMaterial) values.push(...Object.values(material.uniforms).map((u) => u.value))
      for (const value of values) if ((value as Texture | null)?.isTexture) textures.add(value as Texture)
    }
  })
  for (const texture of textures) gl.initTexture(texture)
  return textures.size
}

// Compiles every material in the scene, hidden ones included, for one render
// pass. Drawing into a render target instead of the canvas needs different
// shaders (no tone mapping, linear output), so each target is its own pass.
// Resolves once the GPU driver has finished, compiling in parallel where the
// browser supports it.
export function compileShaders(gl: WebGLRenderer, scene: Object3D, camera: Camera, target: WebGLRenderTarget | null = null) {
  // three.js only compiles what's visible, so hidden objects are shown for the
  // call. compileAsync collects its materials before it returns (the promise
  // only waits on the driver), and no frame draws in between.
  const hidden: Object3D[] = []
  scene.traverse((object) => {
    if (object.visible) return
    hidden.push(object)
    object.visible = true
  })
  const previous = gl.getRenderTarget()
  gl.setRenderTarget(target)
  const done = gl.compileAsync(scene, camera)
  gl.setRenderTarget(previous)
  for (const object of hidden) object.visible = false
  return done
}

// While the start screen is up: upload every texture, including the lightmaps
// of the lighting states not shown yet, and compile every shader, so no camera
// move or lighting change stalls to build one. Call it from the component
// that mounts the ship: its effects run after its children's, so by then the
// whole ship is mounted and lightmapped.
export function useWarmUp(rooms: ShipRoom[]) {
  const gl = useThree((state) => state.gl)
  const scene = useThree((state) => state.scene)
  const camera = useThree((state) => state.camera)
  useEffect(() => {
    let current = true
    const textures = uploadTextures(gl, scene, rooms.flatMap((room) => Object.values(room.lightmaps)))
    // No timing: the calls only queue work for Chrome's GPU process, which does
    // it after they return. What it costs shows as the HUD's `worst` at load.
    void compileShaders(gl, scene, camera).then(() => {
      if (current) console.info(`[perf] warm-up: ${textures} textures, ${gl.info.programs?.length} shaders`)
    })
    return () => {
      current = false
    }
  }, [gl, scene, camera, rooms])
}
