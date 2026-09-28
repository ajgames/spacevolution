import { create } from 'zustand'
import type { LightingState } from '../scene/shipData.ts'
import { playVoice, sfx, unlockAudio } from './audio.ts'
import { ENGINEERING, type Hotspot, SPOTS, type SpotId, headingBetween, nearestFacing } from './nodes.ts'

// The demo is one small state machine. Lighting, screen content and which
// hotspots are clickable are all derived from the phase (see the selectors at
// the bottom), never wired up one object at a time.
export const PHASES = ['blackout', 'emergency', 'breakersSet', 'powered', 'tapePlaying', 'ended'] as const
export type Phase = (typeof PHASES)[number]
type Event = 'PRESS_BLINK' | 'BREAKERS_MATCH' | 'BREAKERS_MISMATCH' | 'PRESS_MAIN' | 'ENTER_ENGINEERING' | 'TAPE_END'

const TRANSITIONS: Record<Phase, Partial<Record<Event, Phase>>> = {
  blackout: { PRESS_BLINK: 'emergency' },
  emergency: { BREAKERS_MATCH: 'breakersSet' },
  breakersSet: { BREAKERS_MISMATCH: 'emergency', PRESS_MAIN: 'powered' },
  powered: { ENTER_ENGINEERING: 'tapePlaying' },
  tapePlaying: { TAPE_END: 'ended' },
  ended: {},
}

export const DOORS = ['DOOR_cryo', 'DOOR_engineering', 'DOOR_command']
// When each command screen (status, mission, aux) starts to boot after full power.
export const SCREEN_BOOT_MS = [900, 1500, 2100]
// The sleeper whose vitals are slipping. Its status panel flickers amber.
export const FAILING_POD = 'CRYO_POD_06'

// About nine seconds of speech before the cut, just after "Pod six isn't".
const VOICE =
  "Caretaker's log. The bus tripped again. If you're hearing this, don't trust the pod telemetry. " +
  "Pod six isn't — the droid knows where"

export type DemoState = {
  started: boolean
  phase: Phase
  enteredAt: Partial<Record<Phase, number>> // performance.now() each phase first began; screens time their boot from it
  spot: SpotId
  facing: number // index into SPOTS[spot].facings
  moving: boolean // the camera is easing between facings or spots
  busy: boolean // a door or the pod is opening; clicks wait
  podOpen: boolean
  doorsOpen: string[]
  pattern: boolean[] // the lit columns on the core lamp matrix: breakers to close
  breakers: boolean[]
  stutter: boolean // wrong combination: lights stutter while the breakers reset
  pressedAt: Record<string, number> // last press per button object, for the press animation
  muted: boolean
  generation: number // bumps on every reset, so the camera snaps instead of flying back
}

// Three to five breakers closed, never the same as all-open.
function randomPattern() {
  for (;;) {
    const pattern = Array.from({ length: 8 }, () => Math.random() < 0.5)
    const lit = pattern.filter(Boolean).length
    if (lit >= 3 && lit <= 5) return pattern
  }
}

const initial = (): DemoState => ({
  started: false,
  phase: 'blackout',
  enteredAt: { blackout: performance.now() },
  spot: 'pod',
  facing: 0,
  moving: false,
  busy: false,
  podOpen: false,
  doorsOpen: ['DOOR_cryo'], // left open when the power failed, so the pulse shows through
  pattern: randomPattern(),
  breakers: Array(8).fill(false),
  stutter: false,
  pressedAt: {},
  muted: false,
  generation: 0,
})

export const useDemo = create<DemoState>(initial)
const get = useDemo.getState
const set = useDemo.setState

let timers: ReturnType<typeof setTimeout>[] = []
const later = (ms: number, fn: () => void) => timers.push(setTimeout(fn, ms))
let stopTapeSound: (() => void) | null = null

function send(event: Event) {
  const next = TRANSITIONS[get().phase][event]
  if (!next) return false
  const from = get().phase
  set((s) => ({ phase: next, enteredAt: { [next]: performance.now(), ...s.enteredAt } }))
  onEnter[next]?.(from)
  return true
}

const onEnter: Partial<Record<Phase, (from?: Phase) => void>> = {
  emergency: (from) => {
    if (from !== 'blackout') return
    sfx.relay()
    later(900, sfx.crtOn) // the core monitor wakes (see CoreCrt)
    // Step back from the panel so the lights and the core monitor are in view.
    later(1300, () => act.go('eng', 72))
  },
  powered: () => {
    for (const ms of SCREEN_BOOT_MS) later(ms, sfx.crtOn)
  },
  tapePlaying: () => {
    // Give the camera time to arrive in engineering before the reels start.
    later(1600, () => {
      const stopTape = sfx.tape()
      stopTapeSound = stopTape
      let cut = false
      // The tape cuts out mid-sentence, with a clunk, and the scene ends shortly after.
      const cutTape = () => {
        if (cut) return
        cut = true
        window.speechSynthesis?.cancel()
        stopTape()
        later(3000, () => send('TAPE_END'))
      }
      later(1400, () => playVoice(VOICE, 'the droid', cutTape))
      later(12500, cutTape) // voices without word events, or no speech synthesis at all
    })
  },
}

function press(object: string) {
  set((s) => ({ pressedAt: { ...s.pressedAt, [object]: performance.now() } }))
}

export const act = {
  start() {
    unlockAudio()
    set({ started: true })
  },

  // Restart from the pod, or jump straight to a later beat (debug URLs).
  reset(options: { spot?: SpotId; phase?: Phase; pattern?: boolean[]; started?: boolean } = {}) {
    for (const t of timers) clearTimeout(t)
    timers = []
    stopTapeSound?.()
    stopTapeSound = null
    window.speechSynthesis?.cancel()
    const state = initial()
    const phase = options.phase ?? 'blackout'
    const spot = options.spot ?? 'pod'
    const pattern = options.pattern ?? state.pattern
    const past = PHASES.indexOf(phase)
    // Phases already behind us began long ago, so their screens are already on.
    const enteredAt = Object.fromEntries(PHASES.slice(0, past + 1).map((p) => [p, performance.now() - 60_000]))
    set({
      ...state,
      muted: get().muted,
      generation: get().generation + 1,
      started: options.started ?? false,
      phase,
      enteredAt,
      spot,
      pattern,
      podOpen: spot !== 'pod' || past > 0,
      doorsOpen: past > 0 ? DOORS : state.doorsOpen,
      breakers: past >= PHASES.indexOf('breakersSet') ? [...pattern] : state.breakers,
    })
    if (phase === 'tapePlaying') onEnter.tapePlaying?.()
  },

  go(to: SpotId, heading?: number) {
    const s = get()
    if (s.moving) return
    sfx.step()
    set({ spot: to, facing: nearestFacing(to, heading ?? headingBetween(s.spot, to)), busy: false })
    if (ENGINEERING.includes(to)) send('ENTER_ENGINEERING')
  },

  turn(direction: 1 | -1) {
    const s = get()
    const count = SPOTS[s.spot].facings.length
    if (count < 2 || s.moving) return
    set({ facing: (s.facing + direction + count) % count })
  },

  // Close-ups step back out, still looking the same way.
  back() {
    const s = get()
    const back = SPOTS[s.spot].back
    if (back) act.go(back, SPOTS[s.spot].facings[s.facing].heading)
  },

  hotspot(h: Hotspot) {
    if (h.kind === 'go') {
      if (!h.door || get().doorsOpen.includes(h.door)) return act.go(h.to, h.heading)
      set((s) => ({ busy: true, doorsOpen: [...s.doorsOpen, h.door!] }))
      sfx.door()
      return later(800, () => act.go(h.to, h.heading))
    }
    if (h.action === 'openPod') {
      set({ podOpen: true, busy: true })
      sfx.podOpen()
      return later(1500, () => act.go('cryo', 148))
    }
    if (h.action === 'pressBlink') {
      press('BTN_blink')
      sfx.clunk()
      return later(180, () => send('PRESS_BLINK'))
    }
    if (h.action === 'breaker') {
      const i = h.index!
      const breakers = get().breakers.map((b, j) => (j === i ? !b : b))
      press(h.objects[0])
      sfx.toggle(breakers[i])
      set({ breakers })
      return send(breakers.every((b, j) => b === get().pattern[j]) ? 'BREAKERS_MATCH' : 'BREAKERS_MISMATCH')
    }
    // The main button: full power with the right breakers, a fault without them.
    press('BTN_console_main')
    sfx.clunk()
    if (send('PRESS_MAIN')) return
    set({ stutter: true })
    sfx.stutter()
    const closed = get()
      .breakers.map((b, i) => (b ? i : -1))
      .filter((i) => i >= 0)
    closed.forEach((i, k) =>
      later(1300 + k * 110, () => {
        set((s) => ({ breakers: s.breakers.map((b, j) => (j === i ? false : b)) }))
        sfx.toggle(false)
      }),
    )
    later(1400 + closed.length * 110, () => set({ stutter: false }))
  },

  setMoving(moving: boolean) {
    set({ moving })
  },

  setMuted(muted: boolean) {
    set({ muted })
  },
}

// --- derived state -------------------------------------------------------

export function lightingFor(phase: Phase): LightingState {
  if (phase === 'blackout') return 'blackout'
  if (phase === 'emergency' || phase === 'breakersSet') return 'emergency'
  return 'normal'
}

export const atLeast = (phase: Phase, than: Phase) => PHASES.indexOf(phase) >= PHASES.indexOf(than)

export function isActive(h: Hotspot, s: DemoState) {
  if (!s.started || s.moving || s.busy || s.phase === 'ended') return false
  if (h.kind === 'go') return true
  switch (h.action) {
    case 'openPod':
      return !s.podOpen
    case 'pressBlink':
      return s.phase === 'blackout'
    case 'breaker':
    case 'main':
      return (s.phase === 'emergency' || s.phase === 'breakersSet') && !s.stutter
  }
}
