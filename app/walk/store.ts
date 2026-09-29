import { PerspectiveCamera } from 'three'
import { create } from 'zustand'
import { sfx, soundAt } from '../demo/audio.ts'
import { type Phase, act, atLeast, puzzle, useDemo } from '../demo/store.ts'

// The walk mode plays the demo's puzzle (useDemo: phase, breakers, doors) on
// foot. This store holds what's only true on foot: how the player is moving,
// what they're looking at, and the steward's side of the story once the power
// is back. Per-frame state (poses, the stick) lives in plain objects below.

export type Mode =
  | 'pod' // inside the pod, looking out through the glass
  | 'stepping' // climbing out once it opens
  | 'walk'
  | 'stick' // seated at the console, driving the droid

export type WalkState = {
  mode: Mode
  locked: boolean // pointer lock is held, so the mouse looks around
  hover: { id: string; label: string; info?: boolean } | null // info: a pointer, not something to use
  subtitle: string | null // the steward's current line
  objective: string | null
  speaking: boolean
  steward: boolean // the steward is online (its face is on the right-hand screen)
  linked: boolean // the droid link has been taken at least once
  scan: number // 0..1 while the droid scans pod six; -1 before, 1 after
  ended: boolean
  generation: number
}

const initial = (): Omit<WalkState, 'generation'> => ({
  mode: 'pod',
  locked: false,
  hover: null,
  subtitle: null,
  objective: null,
  speaking: false,
  steward: false,
  linked: false,
  scan: -1,
  ended: false,
})

export const useWalk = create<WalkState>(() => ({ ...initial(), generation: 0 }))
const get = useWalk.getState
const set = useWalk.setState

// --- per-frame state ---------------------------------------------------------

// Headings are three.js yaw (rotation.y): 0 faces -z (the bow), positive turns left.
export const body = { x: 0, z: 0, yaw: 0, pitch: 0 }
export const DROID_HOME = { x: 0, z: 1.3, yaw: 0 } // SPAWN_droid, facing out of the alcove
export const droid = { ...DROID_HOME, speed: 0, spin: 0, travelled: 0 }
// The droid's camera, carried on its head (Droid) and shown on SCREEN_mission (Console).
export const droidEye = new PerspectiveCamera(70, 4 / 3, 0.03, 40)
// When each door panel button was last pressed (performance.now()), for its flash.
export const buttonsPressedAt: Record<string, number> = {}
// The droid joystick: x steers (right positive), y drives (forward positive).
export const stick = { x: 0, y: 0 }

const deg = (d: number) => (d * Math.PI) / 180
// Compass headings, as in the demo's nodes.ts: 0 north (-z), 90 east.
const facing = (heading: number) => -deg(heading)

// Where debug links can start: /walk?at=console&phase=emergency
export const PLACES = {
  pod: { x: -6.7, z: -2.3, yaw: facing(180), pitch: deg(-8) },
  cryo: { x: -6.6, z: -0.85, yaw: facing(148), pitch: deg(-4) },
  junction: { x: 0, z: 0, yaw: facing(90), pitch: 0 },
  eng: { x: 6.3, z: 0.2, yaw: facing(62), pitch: deg(-4) },
  command: { x: 0, z: -5.9, yaw: facing(0), pitch: deg(-6) },
  console: { x: 0, z: -7.3, yaw: facing(0), pitch: deg(-22) },
}
export type Place = keyof typeof PLACES

let timers: ReturnType<typeof setTimeout>[] = []
const later = (ms: number, fn: () => void) => timers.push(setTimeout(fn, ms))

export const walkAct = {
  // A fresh start in the pod, or a later beat for debug links.
  reset(options: { phase?: Phase; at?: Place; pattern?: boolean[] } = {}) {
    for (const t of timers) clearTimeout(t)
    timers = []
    act.reset({ phase: options.phase, pattern: options.pattern, started: false })
    const past = atLeast(useDemo.getState().phase, 'emergency')
    const at = options.at ?? (past ? 'command' : 'pod')
    Object.assign(body, PLACES[at])
    Object.assign(droid, DROID_HOME, { speed: 0, spin: 0, travelled: 0 })
    Object.assign(stick, { x: 0, y: 0 })
    for (const button of Object.keys(buttonsPressedAt)) delete buttonsPressedAt[button]
    // Out of the pod, it's open.
    if (at !== 'pod') useDemo.setState({ podOpen: true })
    const mode = useDemo.getState().podOpen ? 'walk' : 'pod'
    set({ ...initial(), mode, generation: get().generation + 1 })
  },

  start() {
    act.start()
  },

  setLocked(locked: boolean) {
    set({ locked })
  },

  setHover(hover: WalkState['hover']) {
    if (hover?.id !== get().hover?.id) set({ hover })
  },

  openPod() {
    puzzle.openPod()
    later(1300, () => set({ mode: 'stepping' }))
  },

  // A door's control panel: the button acknowledges, then the door slides open.
  pressDoorButton(door: string, button: string) {
    buttonsPressedAt[button] = performance.now()
    soundAt(button, sfx.doorPanel)
    later(350, () => puzzle.openDoor(door))
  },

  stepOut() {
    set({ mode: 'walk' })
  },

  takeStick() {
    soundAt('JOYSTICK', () => sfx.grab(true))
    set({ mode: 'stick', linked: true, hover: null })
  },

  leaveStick() {
    soundAt('JOYSTICK', () => sfx.grab(false))
    Object.assign(stick, { x: 0, y: 0 })
    set({ mode: 'walk' })
  },

  wakeSteward() {
    set({ steward: true })
  },

  say(subtitle: string | null) {
    set({ subtitle, speaking: subtitle !== null })
  },

  setObjective(objective: string | null) {
    set({ objective })
  },

  setScan(scan: number) {
    set({ scan })
  },

  end() {
    set({ ended: true, objective: null, subtitle: null })
  },
}
