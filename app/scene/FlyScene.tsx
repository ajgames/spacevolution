import { OrbitControls } from '@react-three/drei'
import { useThree } from '@react-three/fiber'
import { type ComponentRef, Suspense, useLayoutEffect, useRef } from 'react'
import Reflections from './Reflections.tsx'
import ShipRooms from './ShipRooms.tsx'
import { ENV_INTENSITY, type LightingState, VIEWS, type View } from './shipData.ts'
import { useShip } from './useShip.ts'

// Orbit the whole ship from one of the preset views. The baked lightmaps and
// emissive materials are the lighting, so the scene adds no lights of its own.
export default function FlyScene({ view, lighting }: { view: View; lighting: LightingState }) {
  const camera = useThree((state) => state.camera)
  const controls = useRef<ComponentRef<typeof OrbitControls>>(null)

  useLayoutEffect(() => {
    const [position, target] = VIEWS[view]
    camera.position.set(...position)
    controls.current?.target.set(...target)
    controls.current?.update()
  }, [camera, view])

  return (
    <>
      <color attach="background" args={['#000000']} />
      <Reflections intensity={ENV_INTENSITY[lighting]} />
      <Suspense fallback={null}>
        <Ship lighting={lighting} />
      </Suspense>
      <OrbitControls ref={controls} makeDefault />
    </>
  )
}

function Ship({ lighting }: { lighting: LightingState }) {
  return <ShipRooms rooms={useShip()} lighting={lighting} />
}
