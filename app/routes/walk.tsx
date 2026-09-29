import { Loader } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { type RefObject, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { AgXToneMapping } from 'three'
import { setMuted, sfx } from '../demo/audio.ts'
import { PHASES, type Phase, act, atLeast, useDemo } from '../demo/store.ts'
import { PerfHud, PerfProbe } from '../scene/Perf.tsx'
import { clearCues, rumble } from '../walk/cues.ts'
import { SoundCues } from '../walk/SoundCues.tsx'
import { type Mode, PLACES, type Place, body, droid, stick, useWalk, walkAct } from '../walk/store.ts'
import { startStory, stopStory } from '../walk/story.ts'
import { preloadVoice } from '../walk/voice.ts'
import WalkScene from '../walk/WalkScene.tsx'
import { solids } from '../walk/world.ts'

// Debug and review links start at a later beat:
// /walk?phase=powered&at=console&beat=droid  (at: a key of PLACES; beat: see story.ts)
// /walk?debug=walls draws the collision plan on the floor.
function useDebugStart() {
  const [params] = useSearchParams()
  useLayoutEffect(() => {
    const phase = params.get('phase')
    const at = params.get('at')
    const pattern = params.get('pattern')
    walkAct.reset({
      phase: PHASES.includes(phase as Phase) ? (phase as Phase) : undefined,
      at: at && at in PLACES ? (at as Place) : undefined,
      pattern: pattern && /^[01]{8}$/.test(pattern) ? [...pattern].map((c) => c === '1') : undefined,
    })
    return () => {
      stopStory()
      act.reset()
    }
  }, [params])
  return { beat: params.get('beat'), debugWalls: params.get('debug') === 'walls' }
}

// Dev only: drive and inspect the walk from the console (window.__walk.body is the player, .droid the droid).
if (import.meta.env.DEV) Object.assign(window, { __walk: { walkAct, useWalk, act, useDemo, body, droid, stick, solids } })

// The browser can refuse (right after Esc, say); the pause screen asks again.
function lockPointer(target: HTMLElement | null) {
  target?.requestPointerLock()?.catch(() => {})
}

export default function Walk() {
  const { beat, debugWalls } = useDebugStart()
  const main = useRef<HTMLElement>(null)
  useAudioBeds()
  useStory(beat)
  useEndUnlock()
  return (
    <main ref={main} className="relative h-dvh w-full overflow-hidden bg-black font-mono text-[#d8d2c4] select-none">
      <Canvas gl={{ toneMapping: AgXToneMapping }} camera={{ fov: 70, near: 0.03, far: 100 }}>
        <WalkScene debugWalls={debugWalls} />
        <PerfProbe />
      </Canvas>
      <Loader />
      <SoundCues />
      <Crosshair />
      <Objective />
      <Subtitle />
      <StickHelp />
      <Hint />
      <FadeIn />
      <Pause main={main} />
      <StartScreen main={main} />
      <EndCard main={main} />
      <PerfHud />
    </main>
  )
}

// --- sound and story ---------------------------------------------------------

function useAudioBeds() {
  const started = useDemo((s) => s.started)
  const powered = useDemo((s) => atLeast(s.phase, 'powered'))
  const muted = useDemo((s) => s.muted)
  const generation = useWalk((s) => s.generation)
  useEffect(() => setMuted(muted), [muted])
  useEffect(() => clearCues(), [generation])
  useEffect(() => {
    if (!started) return
    preloadVoice()
    const stop = sfx.roomTone()
    return () => stop()
  }, [started])
  useEffect(() => {
    if (!started || !powered) return
    // The deck hums up to full power under your feet.
    rumble(0.3, 3)
    const stop = sfx.powerUp()
    return () => stop()
  }, [started, powered])
}

// The steward takes over once the power is back.
function useStory(beat: string | null) {
  const on = useDemo((s) => s.started && atLeast(s.phase, 'powered'))
  const generation = useWalk((s) => s.generation)
  useEffect(() => {
    if (!on) return
    startStory(beat)
    return stopStory
  }, [on, generation, beat])
}

function useEndUnlock() {
  const ended = useWalk((s) => s.ended)
  useEffect(() => {
    if (ended && document.pointerLockElement) document.exitPointerLock()
  }, [ended])
}

// --- HUD -----------------------------------------------------------------------

function Crosshair() {
  const show = useWalk((s) => s.locked && !s.ended && (s.mode === 'walk' || s.mode === 'pod'))
  const hover = useWalk((s) => s.hover)
  const started = useDemo((s) => s.started)
  if (!started || !show) return null
  return (
    <div className="pointer-events-none absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2">
      <div
        className={`rounded-full transition-all duration-150 ${hover && !hover.info ? 'size-5 border border-[#f0a040]' : 'size-1 bg-[#d8d2c4]/70'}`}
      />
      {hover && (
        <p
          className={`absolute top-8 left-1/2 -translate-x-1/2 text-xs tracking-widest whitespace-nowrap uppercase ${hover.info ? 'text-[#8a877e]' : 'text-[#f0a040]'}`}
        >
          {hover.label} {!hover.info && <span className="text-[#8a877e]">· click</span>}
        </p>
      )}
    </div>
  )
}

function Objective() {
  const objective = useWalk((s) => (s.ended ? null : s.objective))
  return (
    <p
      className={`pointer-events-none absolute top-5 left-1/2 -translate-x-1/2 border border-[#2a3130] bg-[#0c1010]/75 px-4 py-1.5 text-xs tracking-widest whitespace-nowrap text-[#f0a040] uppercase transition-opacity duration-500 ${objective ? 'opacity-100' : 'opacity-0'}`}
    >
      ▸ {objective}
    </p>
  )
}

function Subtitle() {
  const line = useWalk((s) => s.subtitle)
  return (
    <div
      className={`pointer-events-none absolute bottom-24 left-1/2 w-[min(40rem,calc(100vw-32px))] -translate-x-1/2 text-center transition-opacity duration-300 ${line ? 'opacity-100' : 'opacity-0'}`}
    >
      <p className="inline bg-black/60 px-2 py-1 text-sm leading-7 [box-decoration-break:clone]">
        <span className="tracking-widest text-[#f0a040]">STEWARD</span> {line}
      </p>
    </div>
  )
}

function StickHelp() {
  const show = useWalk((s) => s.mode === 'stick' && s.locked && !s.ended)
  return (
    <p
      className={`pointer-events-none absolute bottom-6 left-1/2 -translate-x-1/2 text-center text-xs tracking-widest whitespace-nowrap text-[#8a877e] uppercase transition-opacity duration-500 ${show ? 'opacity-90' : 'opacity-0'}`}
    >
      Hold click and drag, or W A S D, to drive <span className="text-[#f0a040]">·</span> E or right-click to stand up
    </p>
  )
}

// Tutorial text waits: the player should feel the urgency before being told anything.
type Situation = { phase: Phase; mode: Mode }
const HINTS: { when: (s: Situation) => boolean; after: number; lasts?: number; text: string }[] = [
  { when: (s) => s.mode === 'pod', after: 8, text: 'Aim at the glass and click.' },
  {
    when: (s) => s.mode === 'walk' && s.phase === 'blackout',
    after: 0.8,
    lasts: 7,
    text: 'W A S D to walk, Shift to run, mouse to look.',
  },
  {
    when: (s) => s.mode === 'walk' && s.phase === 'blackout',
    after: 25,
    text: 'Follow the red pulse. The marks around the crosshair point to each sound.',
  },
  { when: (s) => s.phase === 'emergency', after: 45, text: 'The breakers are on the command console.' },
  { when: (s) => s.phase === 'breakersSet', after: 8, text: 'Press the large button.' },
]

// Every hint for the situation is scheduled; the latest to come due shows.
function Hint() {
  const started = useDemo((s) => s.started)
  const phase = useDemo((s) => s.phase)
  const mode = useWalk((s) => s.mode)
  const locked = useWalk((s) => s.locked)
  const generation = useWalk((s) => s.generation)
  const live = started && locked
  const key = `${phase}:${mode}:${generation}`
  const [shown, setShown] = useState<{ key: string; text: string } | null>(null)
  useEffect(() => {
    if (!live) return
    const timers = HINTS.filter((h) => h.when({ phase, mode })).flatMap((h) => [
      setTimeout(() => setShown({ key, text: h.text }), h.after * 1000),
      ...(h.lasts
        ? [setTimeout(() => setShown((s) => (s?.text === h.text ? null : s)), (h.after + h.lasts) * 1000)]
        : []),
    ])
    return () => timers.forEach(clearTimeout)
  }, [live, key, phase, mode])
  // Only while the situation that scheduled it lasts.
  const text = live && shown?.key === key ? shown.text : null
  return (
    <p
      className={`pointer-events-none absolute bottom-14 left-1/2 w-[min(36rem,calc(100vw-32px))] -translate-x-1/2 text-center text-sm tracking-wide text-[#d8d2c4] transition-opacity duration-1000 ${text ? 'opacity-80' : 'opacity-0'}`}
    >
      {text}
    </p>
  )
}

function FadeIn() {
  const started = useDemo((s) => s.started)
  const generation = useWalk((s) => s.generation)
  if (!started) return null
  return <div key={generation} className="pointer-events-none absolute inset-0 animate-fade-out bg-black" />
}

const CONTROLS = 'W A S D walk · Shift run · Mouse look · Click to use'

function StartScreen({ main }: { main: RefObject<HTMLElement | null> }) {
  const started = useDemo((s) => s.started)
  if (started) return null
  return (
    <button
      type="button"
      onClick={() => {
        walkAct.start()
        lockPointer(main.current)
      }}
      className="absolute inset-0 flex cursor-pointer flex-col items-center justify-center gap-4 bg-black px-4 text-center"
    >
      <span className="text-xs tracking-[0.3em] text-[#8a877e] uppercase">Scene 02</span>
      <span className="text-2xl tracking-[0.25em] text-[#f0a040] uppercase">Click to wake</span>
      <span className="mt-6 text-xs tracking-wider text-[#d8d2c4]">{CONTROLS}</span>
      <span className="max-w-md text-xs leading-relaxed text-[#8a877e]">
        Sound on. Headphones help: every sound comes from where it happens, and the marks around the crosshair point to
        it.
      </span>
    </button>
  )
}

function Pause({ main }: { main: RefObject<HTMLElement | null> }) {
  const started = useDemo((s) => s.started)
  const muted = useDemo((s) => s.muted)
  const show = useWalk((s) => !s.locked && !s.ended)
  if (!started || !show) return null
  return (
    <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-black/70 px-4 text-center">
      <button
        type="button"
        onClick={() => lockPointer(main.current)}
        className="absolute inset-0 cursor-pointer"
        aria-label="Resume"
      />
      <span className="pointer-events-none text-xl tracking-[0.25em] text-[#f0a040] uppercase">Click to resume</span>
      <span className="pointer-events-none text-xs tracking-wider text-[#8a877e]">{CONTROLS}</span>
      <div className="relative mt-4 flex gap-3 text-xs tracking-widest uppercase">
        <button
          type="button"
          onClick={() => act.setMuted(!muted)}
          className="cursor-pointer border border-[#2a3130] px-4 py-2 hover:border-[#f0a040] hover:text-[#f0a040]"
        >
          {muted ? 'Sound off' : 'Sound on'}
        </button>
        <Link to="/" className="border border-[#2a3130] px-4 py-2 hover:border-[#f0a040] hover:text-[#f0a040]">
          Menu
        </Link>
      </div>
    </div>
  )
}

function EndCard({ main }: { main: RefObject<HTMLElement | null> }) {
  const ended = useWalk((s) => s.ended)
  return (
    <div
      className={`absolute inset-0 flex flex-col items-center justify-center gap-5 bg-black px-4 text-center transition-opacity duration-[2500ms] ${ended ? 'opacity-100' : 'pointer-events-none opacity-0'}`}
    >
      <p className="text-sm text-[#8a877e]">The steward goes quiet.</p>
      <p className="text-xl tracking-[0.2em] text-[#f0a040] uppercase">End of scene 02</p>
      <p className="max-w-md text-sm leading-relaxed text-[#8a877e]">Next: the gap in the droid's logs.</p>
      <div className="mt-4 flex gap-3 text-xs tracking-widest uppercase">
        <button
          type="button"
          onClick={() => {
            walkAct.reset()
            walkAct.start()
            lockPointer(main.current)
          }}
          className="cursor-pointer border border-[#2a3130] px-4 py-2 tracking-widest uppercase hover:border-[#f0a040] hover:text-[#f0a040]"
        >
          Replay
        </button>
        <Link to="/" className="border border-[#2a3130] px-4 py-2 hover:border-[#f0a040] hover:text-[#f0a040]">
          Menu
        </Link>
      </div>
    </div>
  )
}
