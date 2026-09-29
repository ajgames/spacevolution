import { Vector3 } from 'three'
import { create } from 'zustand'
import { setMuted, unlockAudio } from '../demo/audio.ts'
import { CARETAKER_LINES, type CaretakerLineId } from './lines.ts'
import { hush, preloadCaretaker, say } from './voice.ts'

// The construct: the caretaker alone in an endless white room, showing off one
// motion at a time. Per-frame state (where he stands) lives in `body` below.

export const MODES = [
  { id: 'walk', key: '1', label: 'Walk' },
  { id: 'jump', key: '2', label: 'Jump' },
  { id: 'talk', key: '3', label: 'Talk' },
  { id: 'strafe', key: '4', label: 'Strafe' },
  { id: 'crouch', key: '5', label: 'Crouch' },
] as const
export type Mode = (typeof MODES)[number]['id'] | 'idle'

export type ConstructState = {
  mode: Mode
  subtitle: string | null
  muted: boolean
}

export const useConstruct = create<ConstructState>(() => ({ mode: 'idle', subtitle: null, muted: false }))
const set = useConstruct.setState

// Where he stands and which way he faces. Yaw is three.js rotation.y: 0 faces +z
// (towards the default camera), positive turns to his left.
export const body = { x: 0, z: 0, yaw: 0 }
// Where his hips and midfeet are this frame, in world space (for the ground shadows).
export const ground = { hips: new Vector3(0, 0.93, 0), feet: [new Vector3(), new Vector3()], yaw: 0 }

const LINE_ORDER = Object.keys(CARETAKER_LINES) as CaretakerLineId[]
let dialogue = 0 // bumped to stop a running conversation

async function talk() {
  const run = ++dialogue
  const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
  await wait(500) // let him turn to the camera first
  while (run === dialogue) {
    for (const id of LINE_ORDER) {
      if (run !== dialogue) return
      set({ subtitle: CARETAKER_LINES[id] })
      await say(id)
      if (run !== dialogue) return
      set({ subtitle: null })
      await wait(650)
    }
    await wait(2500)
  }
}

export const constructAct = {
  // Buttons and keys call this, so it doubles as the gesture that unlocks audio.
  setMode(mode: Mode) {
    unlockAudio()
    preloadCaretaker()
    const was = useConstruct.getState().mode
    const next = was === mode ? 'idle' : mode // pressing the active mode again stops it
    if (was === 'talk') {
      dialogue++
      hush()
      set({ subtitle: null })
    }
    set({ mode: next })
    if (next === 'talk') void talk()
  },
  setMuted(muted: boolean) {
    unlockAudio()
    setMuted(muted)
    set({ muted })
  },
  reset() {
    dialogue++
    hush()
    Object.assign(body, { x: 0, z: 0, yaw: 0 })
    set({ mode: 'idle', subtitle: null })
  },
}
