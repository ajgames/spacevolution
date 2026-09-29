import type { Point } from '../demo/audio.ts'

// Sound cues: what the on-screen indicators know about each sound the player
// can hear. One-shots flash and fade; continuous sounds (the steward's voice,
// the droid's motor) are held by their owner every frame they're audible.

export type Cue = {
  label: string
  points: Point[] // every position it plays from; the nearest reads loudest
  reach: number // the panner's refDistance, so the cue fades the way the sound does
  level: number // 0..1 at the source
  born: number // performance.now()
  life: number // ms
}

// How long each kind of one-shot stays on screen.
const LIFE: Record<string, number> = { pulse: 650, alarm: 1400, door: 1500, relay: 1300, fault: 1800, seal: 1800 }

const cues = new Map<string, Cue>()
let serial = 0

export function flashCue(label: string, points: Point[], reach: number) {
  cues.set(`flash${serial++}`, { label, points, reach, level: 1, born: performance.now(), life: LIFE[label] ?? 1200 })
}

// Call every frame the sound is audible; the cue lapses a moment after the last call.
export function holdCue(key: string, label: string, points: Point[], reach: number, level: number) {
  const cue = cues.get(key)
  if (cue) Object.assign(cue, { points, level, born: performance.now() })
  else cues.set(key, { label, points, reach, level, born: performance.now(), life: 250 })
}

// Live cues and how far through its life each is (0 new, 1 gone).
export function liveCues(now: number) {
  const live: { cue: Cue; age: number }[] = []
  for (const [key, cue] of cues) {
    const age = (now - cue.born) / cue.life
    if (age >= 1) cues.delete(key)
    else live.push({ cue, age })
  }
  return live
}

export function clearCues() {
  cues.clear()
}

// --- camera shake ------------------------------------------------------------

// Trauma, 0..1, raised to 1.5 in the shake so small knocks stay small. Loud
// things nearby add some; a rumble holds a floor under it for a while.
export const feel = { trauma: 0, floor: 0, floorUntil: 0 }

export function jolt(amount: number) {
  feel.trauma = Math.min(1, feel.trauma + amount)
}

export function rumble(amount: number, seconds: number) {
  feel.floor = amount
  feel.floorUntil = performance.now() + seconds * 1000
}

// Which placed sounds knock the camera, at full strength within 2 m.
export const JOLTS: Record<string, number> = { relay: 0.5, fault: 0.4, door: 0.2, seal: 0.3 }
