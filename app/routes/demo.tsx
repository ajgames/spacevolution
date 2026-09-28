import { Loader } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { useEffect, useLayoutEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { AgXToneMapping } from 'three'
import { setMuted, sfx } from '../demo/audio.ts'
import DemoScene from '../demo/DemoScene.tsx'
import { SPOTS, type SpotId } from '../demo/nodes.ts'
import { PerfHud, PerfProbe } from '../scene/Perf.tsx'
import { type DemoState, PHASES, type Phase, act, atLeast, useDemo } from '../demo/store.ts'

// Debug and review links jump straight to a beat, skipping the start screen:
// /demo?spot=console&phase=emergency&pattern=10110010
function useDebugStart() {
  const [params] = useSearchParams()
  useLayoutEffect(() => {
    const spot = params.get('spot')
    const phase = params.get('phase')
    const pattern = params.get('pattern')
    const debug = spot !== null || phase !== null
    act.reset({
      started: debug,
      spot: spot && spot in SPOTS ? (spot as SpotId) : undefined,
      phase: PHASES.includes(phase as Phase) ? (phase as Phase) : undefined,
      pattern: pattern && /^[01]{8}$/.test(pattern) ? [...pattern].map((c) => c === '1') : undefined,
    })
    return () => act.reset()
  }, [params])
}

// Dev only: drive and inspect the demo from the console (window.__demo.act, .useDemo).
if (import.meta.env.DEV) Object.assign(window, { __demo: { act, useDemo } })

export default function Demo() {
  useDebugStart()
  useAudioBeds()
  return (
    <main className="relative h-dvh w-full overflow-hidden bg-black font-mono text-[#d8d2c4] select-none">
      <Canvas gl={{ toneMapping: AgXToneMapping }} camera={{ fov: 65, near: 0.05, far: 100 }}>
        <DemoScene />
        <PerfProbe />
      </Canvas>
      <Loader />
      <Hud />
      <Hint />
      <FadeIn />
      <StartScreen />
      <EndCard />
      <PerfHud />
    </main>
  )
}

// --- sound beds ------------------------------------------------------------

// Continuous layers follow the phase; one-shots are fired by the actions.
function useAudioBeds() {
  const started = useDemo((s) => s.started)
  const powered = useDemo((s) => atLeast(s.phase, 'powered'))
  const muted = useDemo((s) => s.muted)
  useEffect(() => setMuted(muted), [muted])
  useEffect(() => {
    if (!started) return
    const stop = sfx.roomTone()
    return () => stop()
  }, [started])
  useEffect(() => {
    if (!started || !powered) return
    const stop = sfx.powerUp()
    return () => stop()
  }, [started, powered])
}

// --- HUD -------------------------------------------------------------------

function Hud() {
  const s = useDemo()
  const spot = SPOTS[s.spot]
  const idle = s.started && !s.moving && !s.busy && s.phase !== 'ended'
  const canTurn = idle && spot.facings.length > 1
  return (
    <>
      <div className="absolute top-3 left-3 flex gap-4 text-xs text-[#8a877e]">
        <Link to="/" className="hover:text-[#f0a040]">
          ← menu
        </Link>
        <button type="button" className="cursor-pointer hover:text-[#f0a040]" onClick={() => act.setMuted(!s.muted)}>
          {s.muted ? 'sound off' : 'sound on'}
        </button>
      </div>
      {canTurn && (
        <>
          <TurnEdge side="left" onClick={() => act.turn(-1)} />
          <TurnEdge side="right" onClick={() => act.turn(1)} />
        </>
      )}
      {idle && spot.back && (
        <button
          type="button"
          onClick={act.back}
          className="absolute bottom-5 left-1/2 -translate-x-1/2 cursor-pointer border border-[#2a3130] bg-[#0c1010]/80 px-4 py-1.5 text-xs tracking-widest text-[#8a877e] uppercase hover:border-[#f0a040] hover:text-[#f0a040]"
        >
          ↓ step back
        </button>
      )}
    </>
  )
}

// Myst-style turning: hover a screen edge, click to turn to the next facing.
function TurnEdge({ side, onClick }: { side: 'left' | 'right'; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label={`turn ${side}`}
      onClick={onClick}
      className={`group absolute inset-y-16 ${side === 'left' ? 'left-0 bg-gradient-to-r' : 'right-0 bg-gradient-to-l'} flex w-[9%] min-w-12 cursor-pointer items-center ${side === 'left' ? 'justify-start pl-4' : 'justify-end pr-4'} from-black/50 to-transparent opacity-25 transition-opacity hover:opacity-100`}
    >
      <span className="text-3xl text-[#f0a040]">{side === 'left' ? '‹' : '›'}</span>
    </button>
  )
}

// --- hints -----------------------------------------------------------------

// Tutorial text waits: the player should feel the urgency before being told anything.
const HINTS: { when: (s: DemoState) => boolean; after: number; text: string }[] = [
  { when: (s) => s.spot === 'pod' && !s.podOpen, after: 9, text: 'Click the glass.' },
  {
    when: (s) => s.spot === 'cryo' && s.phase === 'blackout',
    after: 7,
    text: 'Click a doorway to move. Click the screen edges to turn.',
  },
  { when: (s) => s.phase === 'blackout' && s.podOpen, after: 35, text: 'Follow the red pulse.' },
  { when: (s) => s.phase === 'emergency' && s.spot !== 'console', after: 45, text: 'The breakers are on the command console.' },
  { when: (s) => s.phase === 'breakersSet', after: 8, text: 'Press the large button.' },
  { when: (s) => s.phase === 'powered', after: 10, text: 'Something is running in engineering.' },
]

function Hint() {
  const hint = useDemo((s) => (s.started && !s.moving ? HINTS.find((h) => h.when(s)) : undefined))
  const key = useDemo((s) => `${s.spot}:${s.phase}:${s.podOpen}`)
  const [shown, setShown] = useState<{ key: string; text: string } | null>(null)
  useEffect(() => {
    if (!hint) return
    const timer = setTimeout(() => setShown({ key, text: hint.text }), hint.after * 1000)
    return () => clearTimeout(timer)
  }, [hint, key])
  // Only while the situation that scheduled it lasts.
  const text = hint && shown?.key === key && shown.text === hint.text ? shown.text : null
  return (
    <p
      className={`pointer-events-none absolute bottom-16 left-1/2 -translate-x-1/2 text-center text-sm tracking-wide text-[#d8d2c4] transition-opacity duration-1000 ${text ? 'opacity-80' : 'opacity-0'}`}
    >
      {text}
    </p>
  )
}

// --- start, fade, end ------------------------------------------------------

function StartScreen() {
  const started = useDemo((s) => s.started)
  if (started) return null
  return (
    <button
      type="button"
      onClick={act.start}
      className="absolute inset-0 flex cursor-pointer flex-col items-center justify-center gap-4 bg-black text-center"
    >
      <span className="text-xs tracking-[0.3em] text-[#8a877e] uppercase">Scene 01</span>
      <span className="text-2xl tracking-[0.25em] text-[#f0a040] uppercase">Click to wake</span>
      <span className="mt-6 text-xs text-[#8a877e]">Sound on. Headphones help.</span>
    </button>
  )
}

// Every start (and replay) fades in from black.
function FadeIn() {
  const started = useDemo((s) => s.started)
  const generation = useDemo((s) => s.generation)
  if (!started) return null
  return <div key={generation} className="pointer-events-none absolute inset-0 animate-fade-out bg-black" />
}

function EndCard() {
  const ended = useDemo((s) => s.phase === 'ended')
  return (
    <div
      className={`absolute inset-0 flex flex-col items-center justify-center gap-5 bg-black px-4 text-center transition-opacity duration-[2500ms] ${ended ? 'opacity-100' : 'pointer-events-none opacity-0'}`}
    >
      <p className="text-sm text-[#8a877e]">The tape cuts out.</p>
      <p className="text-xl tracking-[0.2em] text-[#f0a040] uppercase">End of scene 01</p>
      <p className="max-w-md text-sm leading-relaxed text-[#8a877e]">
        Next: the failing pod, and the droid at the junction.
      </p>
      <div className="mt-4 flex gap-3 text-xs tracking-widest uppercase">
        <button
          type="button"
          onClick={() => act.reset({ started: true })}
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
