import { useEffect, useMemo, useState } from 'react'
import { Suspense } from 'react'
import Reflections from '../scene/Reflections.tsx'
import ShipRooms from '../scene/ShipRooms.tsx'
import { ENV_INTENSITY, type LightingState } from '../scene/shipData.ts'
import { useShip } from '../scene/useShip.ts'
import Hotspots from './Hotspots.tsx'
import NodeCamera from './NodeCamera.tsx'
import { RoomsContext, prepareRooms } from './objects.ts'
import { AlarmSync, Buttons, Doors, FailingPod, PodGlass, PulseLights } from './Props.tsx'
import { CommandScreens, CoreCrt, LampMatrix, TapeReels } from './Screens.tsx'
import { lightingFor, useDemo } from './store.ts'

export default function DemoScene() {
  return (
    <>
      <color attach="background" args={['#000000']} />
      <NodeCamera />
      <Suspense fallback={null}>
        <Ship />
      </Suspense>
    </>
  )
}

function Ship() {
  const loaded = useShip()
  const rooms = useMemo(() => prepareRooms(loaded), [loaded])
  const phase = useDemo((s) => s.phase)
  const lighting = useLighting()
  return (
    <RoomsContext value={rooms}>
      <Reflections intensity={ENV_INTENSITY[lighting]} />
      {/* Once pressed, the blink button has done its job and goes dark. */}
      <ShipRooms rooms={rooms} lighting={lighting} blink={phase === 'blackout' ? 'blink' : 'off'} pulse />
      <PodGlass />
      <Doors />
      <Buttons />
      <FailingPod />
      <PulseLights />
      <AlarmSync />
      <CommandScreens />
      <CoreCrt />
      <LampMatrix />
      <TapeReels />
      <Hotspots />
    </RoomsContext>
  )
}

// The phase picks the lighting; a breaker fault stutters it between emergency
// and blackout until the breakers have reset.
function useLighting(): LightingState {
  const phase = useDemo((s) => s.phase)
  const stutter = useDemo((s) => s.stutter)
  const [flicker, setFlicker] = useState<LightingState>('blackout')
  useEffect(() => {
    if (!stutter) return
    let timer: ReturnType<typeof setTimeout>
    const step = () => {
      setFlicker((f) => (f === 'blackout' ? 'emergency' : 'blackout'))
      timer = setTimeout(step, 40 + Math.random() * 180)
    }
    step()
    return () => clearTimeout(timer)
  }, [stutter])
  return stutter ? flicker : lightingFor(phase)
}
