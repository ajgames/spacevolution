import { sfx, soundAt } from '../demo/audio.ts'
import { LINES, type LineId } from './lines.ts'
import { DROID_HOME, droid, useWalk, walkAct } from './store.ts'
import { hush, speak } from './voice.ts'
import { SPEAKER_NAMES } from './world.ts'

// The steward's side of the scene, from full power to the end card. Where the
// demo plays the caretaker's tape and cuts out, the ship's own steward comes
// online in the command room and picks the story up from there. Each beat
// waits, says its line over the PA, then holds an objective until it's done.

type Beat = {
  id: string
  pause?: number // ms before the line
  chime?: boolean // the PA chime first
  say?: LineId
  objective?: string // shown from the end of the line until the beat is done
  until?: () => boolean
  run?: (live: () => boolean) => Promise<void>
}

// CRYO_POD_06's centre: the first pod on the left coming in from the door.
const POD_SIX = { x: -6.7, z: 2.28 }

// Close to pod six and pointed at it, so the camera has it in frame.
export function droidOnPodSix() {
  const dx = POD_SIX.x - droid.x
  const dz = POD_SIX.z - droid.z
  const d = Math.hypot(dx, dz)
  return d < 2.1 && (dx * -Math.sin(droid.yaw) + dz * -Math.cos(droid.yaw)) / d > 0.82
}

const SCAN_SECONDS = 3.5

// Scanning only advances while the droid stays on the pod.
async function scan(live: () => boolean) {
  let progress = 0
  walkAct.setScan(0)
  while (progress < 1) {
    await sleep(100)
    if (!live()) return
    if (droidOnPodSix()) progress = Math.min(1, progress + 0.1 / SCAN_SECONDS)
    walkAct.setScan(progress)
  }
}

export const BEATS: Beat[] = [
  // The command screens boot first (SCREEN_BOOT_MS), then the steward.
  { id: 'online', pause: 3400, chime: true, say: 'online' },
  { id: 'hello', pause: 500, say: 'hello' },
  { id: 'memory', pause: 600, say: 'memory' },
  { id: 'droid', pause: 500, say: 'droid', objective: 'Take the joystick', until: () => useWalk.getState().mode === 'stick' },
  {
    id: 'stick',
    pause: 300,
    say: 'stick',
    objective: 'Drive out of the dock',
    until: () => Math.hypot(droid.x - DROID_HOME.x, droid.z - DROID_HOME.z) > 1,
  },
  { id: 'turn', say: 'turn', objective: 'Drive west to the cryo bay', until: () => droid.x < -4.3 },
  { id: 'cryo', say: 'cryo', objective: 'Point the droid at pod six', until: droidOnPodSix },
  { id: 'scan', say: 'scan', objective: 'Hold the droid on pod six', run: scan },
  { id: 'empty', pause: 400, say: 'empty' },
  { id: 'who', pause: 700, say: 'who' },
  { id: 'end', pause: 2600, run: async () => walkAct.end() },
]

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
let run = 0

// Plays the beats from `from` (a beat id; the start by default) to the end.
// Starting again, or stopping, abandons the run in progress.
export function startStory(from?: string | null) {
  const token = ++run
  const live = () => token === run
  const start = Math.max(0, BEATS.findIndex((b) => b.id === from))
  if (start > 0) walkAct.wakeSteward()
  void (async () => {
    for (const beat of BEATS.slice(start)) {
      if (beat.pause) await sleep(beat.pause)
      if (!live()) return
      if (beat.chime) {
        walkAct.wakeSteward()
        soundAt(SPEAKER_NAMES, sfx.chime, { cue: 'voice', reach: 1.4 })
        await sleep(1100)
      }
      if (beat.say) {
        walkAct.say(LINES[beat.say])
        await speak(beat.say)
        if (!live()) return
        walkAct.say(null)
      }
      if (beat.objective) walkAct.setObjective(beat.objective)
      if (beat.run) await beat.run(live)
      while (beat.until && !beat.until()) {
        await sleep(150)
        if (!live()) return
      }
      if (!live()) return
      walkAct.setObjective(null)
    }
  })()
}

export function stopStory() {
  run++
  hush()
  walkAct.say(null)
}
