import { useGLTF } from '@react-three/drei'
import { useLoader } from '@react-three/fiber'
import { use, useMemo } from 'react'
import { type Group, Mesh, MeshStandardMaterial, type Object3D, SRGBColorSpace, type Texture, TextureLoader } from 'three'
import { LIGHTING_STATES, type LightingState, type RoomInfo, SHIP_URL, manifest } from './shipData.ts'

export type ShipRoom = {
  name: string
  info: RoomInfo
  scene: Group
  lightmaps: Partial<Record<LightingState, Texture>>
}

// Loads every room and its lightmaps (suspends) and returns a private copy of
// each room's scene graph. useGLTF caches scenes for the whole app, so the copy
// keeps one route's opened doors or swapped materials out of another route.
// The copies share geometry and materials; clone a material before changing it
// for one object only.
export function useShip(): ShipRoom[] {
  const { rooms } = use(manifest)
  const entries = useMemo(() => Object.entries(rooms), [rooms])
  const baked = useMemo(
    () =>
      entries.flatMap(([name, info]) =>
        LIGHTING_STATES.flatMap((state) => {
          const lightmap = info.lightmaps[state]
          return lightmap ? [{ name, state, url: SHIP_URL + lightmap.file }] : []
        }),
      ),
    [entries],
  )
  const gltfs = useGLTF(entries.map(([, info]) => SHIP_URL + info.glb))
  const textures = useLoader(
    TextureLoader,
    baked.map((b) => b.url),
  )

  return useMemo(() => {
    for (const texture of textures) {
      if (texture.channel === 1) continue
      texture.flipY = false // glTF UV convention
      texture.colorSpace = SRGBColorSpace // PNG stores sRGB-encoded linear light
      texture.channel = 1 // TEXCOORD_1, the "lightmap" UV map
      texture.needsUpdate = true
    }
    return entries.map(([name, info], i) => ({
      name,
      info,
      scene: gltfs[i].scene.clone(),
      lightmaps: Object.fromEntries(baked.flatMap((b, j) => (b.name === name ? [[b.state, textures[j]]] : []))),
    }))
  }, [entries, baked, gltfs, textures])
}

export function standardMaterials(root: Object3D) {
  const found = new Set<MeshStandardMaterial>()
  root.traverse((object) => {
    if (!(object instanceof Mesh)) return
    for (const m of [object.material].flat()) if (m instanceof MeshStandardMaterial) found.add(m)
  })
  return [...found]
}
