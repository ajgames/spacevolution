import { Suspense, useLayoutEffect, useMemo } from 'react'
import { BufferGeometry, Float32BufferAttribute } from 'three'
import { useLighting } from '../demo/lighting.ts'
import { RoomsContext, prepareRooms } from '../demo/objects.ts'
import { AlarmSync, Buttons, Doors, FailingPod, PodGlass, PulseLights } from '../demo/Props.tsx'
import { CoreCrt, LampMatrix } from '../demo/Screens.tsx'
import { useDemo } from '../demo/store.ts'
import Reflections from '../scene/Reflections.tsx'
import ShipRooms from '../scene/ShipRooms.tsx'
import { ENV_INTENSITY } from '../scene/shipData.ts'
import { useShip } from '../scene/useShip.ts'
import { useWarmUp } from '../scene/warmUp.ts'
import { ConsoleScreens, Joystick } from './Console.tsx'
import DoorButtons from './DoorButtons.tsx'
import Droid from './Droid.tsx'
import Interact from './Interact.tsx'
import Player from './Player.tsx'
import { PropLighting } from './props.ts'
import { CueProjector } from './SoundCues.tsx'
import { Hearing } from './space.ts'
import Speakers from './Speakers.tsx'
import { type Rect, measureProps, settleSpeakers, solids, walls } from './world.ts'

// The walk mode's scene: the demo's ship, props and engineering screens, with
// the player on foot, the PA speakers, the droid and its joystick, and the
// command screens rebuilt around the steward.
export default function WalkScene({ debugWalls = false }: { debugWalls?: boolean }) {
  return (
    <>
      <color attach="background" args={['#000000']} />
      <Player />
      <Suspense fallback={null}>
        <Ship debugWalls={debugWalls} />
      </Suspense>
    </>
  )
}

function Ship({ debugWalls }: { debugWalls: boolean }) {
  const loaded = useShip()
  const rooms = useMemo(() => prepareRooms(loaded), [loaded])
  const phase = useDemo((s) => s.phase)
  const lighting = useLighting()
  useWarmUp(rooms)
  // Props to bump into and the ceiling for the speakers, measured once the ship is in.
  const rects = useMemo(() => {
    settleSpeakers(rooms)
    return measureProps(rooms)
  }, [rooms])
  useLayoutEffect(() => {
    solids.rects = rects
    return () => {
      solids.rects = []
    }
  }, [rects])

  return (
    <RoomsContext value={rooms}>
      <Reflections intensity={ENV_INTENSITY[lighting]} />
      <PropLighting lighting={lighting} />
      <Hearing />
      <ShipRooms rooms={rooms} lighting={lighting} blink={phase === 'blackout' ? 'blink' : 'off'} pulse />
      <PodGlass />
      <Doors />
      <Buttons />
      <FailingPod />
      <PulseLights />
      <AlarmSync />
      <CoreCrt />
      <LampMatrix />
      <DoorButtons />
      <Speakers />
      <Droid />
      <Joystick />
      <ConsoleScreens />
      <Interact />
      <CueProjector />
      {debugWalls && <WallLines rects={rects} />}
    </RoomsContext>
  )
}

// /walk?debug=walls: the collision plan drawn on the floor.
function WallLines({ rects }: { rects: Rect[] }) {
  const doors = useDemo((s) => s.doorsOpen)
  const geometry = useMemo(() => {
    const segs = [
      ...walls('player', doors),
      ...rects.flatMap((r) => [
        [r.x0, r.z0, r.x1, r.z0],
        [r.x1, r.z0, r.x1, r.z1],
        [r.x1, r.z1, r.x0, r.z1],
        [r.x0, r.z1, r.x0, r.z0],
      ]),
    ]
    const positions = segs.flatMap(([x1, z1, x2, z2]) => [x1, 0.03, z1, x2, 0.03, z2])
    return new BufferGeometry().setAttribute('position', new Float32BufferAttribute(positions, 3))
  }, [doors, rects])
  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color="#40ff80" depthTest={false} toneMapped={false} />
    </lineSegments>
  )
}
