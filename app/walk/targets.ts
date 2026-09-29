import { type DemoState, DOORS, atLeast, puzzle, useDemo } from '../demo/store.ts'
import { type WalkState, useWalk, walkAct } from './store.ts'
import { doorButton } from './world.ts'

// Everything the crosshair can use: the demo's puzzle pieces, by the Blender
// object that is aimed at, plus the door panel buttons and the droid joystick
// (objects the walk mode adds; see space.ts extras). `reach` is metres from the
// eye to the point aimed at.
export type Target = {
  id: string
  object: string
  label: string
  reach: number
  pad?: number // metres added around the object's box, for small things
  info?: boolean // only says something (a closed door points you to its panel); nothing to use
  active: (d: DemoState, w: WalkState) => boolean
  use: () => void
}

const onFoot = (w: WalkState) => w.mode === 'walk'
const breakersLive = (d: DemoState, w: WalkState) =>
  onFoot(w) && (d.phase === 'emergency' || d.phase === 'breakersSet') && !d.stutter

export const TARGETS: Target[] = [
  {
    id: 'glass',
    object: 'CRYO_POD_01_glass',
    label: 'Open the pod',
    reach: 1.6,
    active: (d, w) => w.mode === 'pod' && !d.podOpen,
    use: walkAct.openPod,
  },
  // Doors open from the panel beside them, on either side.
  ...DOORS.flatMap((door) =>
    (['room', 'corridor'] as const).map(
      (side): Target => ({
        id: doorButton(door, side),
        object: doorButton(door, side),
        label: 'Open the door',
        reach: 1.9,
        pad: 0.03,
        active: (d, w) => onFoot(w) && !d.doorsOpen.includes(door),
        use: () => walkAct.pressDoorButton(door, doorButton(door, side)),
      }),
    ),
  ),
  ...DOORS.map(
    (door): Target => ({
      id: door,
      object: door,
      label: 'Use the panel beside the door',
      reach: 2.4,
      info: true,
      active: (d, w) => onFoot(w) && !d.doorsOpen.includes(door),
      use: () => {},
    }),
  ),
  {
    id: 'blink',
    object: 'BTN_blink',
    label: 'Press',
    reach: 1.9,
    active: (d, w) => onFoot(w) && d.phase === 'blackout',
    use: puzzle.pressBlink,
  },
  ...Array.from(
    { length: 8 },
    (_, i): Target => ({
      id: `breaker${i}`,
      object: `BTN_console_0${i + 1}`,
      label: `Breaker ${i + 1}`,
      reach: 2.1,
      active: breakersLive,
      use: () => puzzle.toggleBreaker(i),
    }),
  ),
  { id: 'main', object: 'BTN_console_main', label: 'Main power', reach: 2.1, active: breakersLive, use: puzzle.pressMain },
  {
    id: 'stick',
    object: 'JOYSTICK',
    label: 'Take the joystick',
    reach: 2.2,
    pad: 0.05,
    active: (d, w) => onFoot(w) && atLeast(d.phase, 'powered'),
    use: walkAct.takeStick,
  },
]

// Uses whatever the crosshair is on, if it still can be.
export function activateHovered() {
  const w = useWalk.getState()
  const target = TARGETS.find((t) => t.id === w.hover?.id)
  if (!target || target.info || !target.active(useDemo.getState(), w)) return
  walkAct.setHover(null)
  target.use()
}
