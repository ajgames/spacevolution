import { Loader } from '@react-three/drei'
import { Canvas, type RootState, advance, useThree } from '@react-three/fiber'
import { useEffect } from 'react'
import { Link } from 'react-router'
import { NeutralToneMapping } from 'three'
import ConstructScene from '../construct/ConstructScene.tsx'
import { MODES, body, constructAct, useConstruct } from '../construct/store.ts'
import { PerfHud, PerfProbe } from '../scene/Perf.tsx'

// The caretaker alone in an endless white room: 1 walk, 2 jump, 3 talk,
// 4 strafe, 5 crouch (press the active one again, or 0, to stand still).

// Dev only: drive it from the console. __construct.step(seconds) renders frames at
// 30 fps on demand (a background or automated tab barely gets animation frames);
// __construct.resume() hands the loop back to the browser.
const devHandle = {
  constructAct,
  useConstruct,
  body,
  three: null as (() => RootState) | null,
  step: (_seconds: number) => {},
  resume: () => {},
}
if (import.meta.env.DEV) Object.assign(window, { __construct: devHandle })

function DevHandle() {
  const get = useThree((s) => s.get)
  useEffect(() => {
    devHandle.step = (seconds: number) => {
      // advance() only uses our timestamps in 'never'. Switching resets R3F's clock, so only once.
      if (get().frameloop !== 'never') get().setFrameloop('never')
      const state = get()
      let t = state.clock.elapsedTime
      for (let i = 0; i < Math.round(seconds * 30); i++) advance((t += 1 / 30), true, state)
    }
    devHandle.resume = () => get().setFrameloop('always')
    devHandle.three = get
  }, [get])
  return null
}

export default function Construct() {
  useKeys()
  useEffect(() => constructAct.reset, [])
  return (
    <main className="relative h-dvh w-full overflow-hidden bg-white font-mono text-[#1c1c1c] select-none">
      <Canvas gl={{ toneMapping: NeutralToneMapping }} dpr={[1, 2]} camera={{ fov: 32, near: 0.05, far: 60, position: [2.2, 1.6, 5.2] }}>
        <ConstructScene />
        <PerfProbe />
        {import.meta.env.DEV && <DevHandle />}
      </Canvas>
      <Loader />
      <TopBar />
      <Subtitle />
      <ModeBar />
      <PerfHud />
    </main>
  )
}

function useKeys() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const mode = MODES.find((m) => m.key === e.key)
      if (mode) constructAct.setMode(mode.id)
      else if (e.key === '0' || e.key === 'Escape') constructAct.setMode('idle')
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
}

function TopBar() {
  const muted = useConstruct((s) => s.muted)
  return (
    <div className="absolute inset-x-3 top-3 flex items-center justify-between text-xs tracking-widest text-[#7a7a7a] uppercase">
      <div className="flex gap-4">
        <Link to="/" className="hover:text-[#1c1c1c]">
          ← menu
        </Link>
        <button type="button" className="cursor-pointer uppercase hover:text-[#1c1c1c]" onClick={() => constructAct.setMuted(!muted)}>
          {muted ? 'sound off' : 'sound on'}
        </button>
      </div>
      <span className="hidden sm:inline">Construct // caretaker</span>
    </div>
  )
}

function Subtitle() {
  const line = useConstruct((s) => s.subtitle)
  return (
    <div
      className={`pointer-events-none absolute bottom-24 left-1/2 w-[min(40rem,calc(100vw-32px))] -translate-x-1/2 text-center transition-opacity duration-300 ${line ? 'opacity-100' : 'opacity-0'}`}
    >
      <p className="inline bg-white/85 px-2 py-1 text-sm leading-7 [box-decoration-break:clone]">
        <span className="tracking-widest text-[#7a7a7a]">CARETAKER</span> {line}
      </p>
    </div>
  )
}

function ModeBar() {
  const mode = useConstruct((s) => s.mode)
  return (
    <div className="absolute inset-x-4 bottom-6 flex flex-wrap justify-center gap-2 text-xs tracking-widest uppercase">
      {MODES.map((m) => {
        const on = mode === m.id
        return (
          <button
            key={m.id}
            type="button"
            onClick={() => constructAct.setMode(m.id)}
            className={`cursor-pointer border px-3 py-2 transition-colors ${on ? 'border-[#1c1c1c] bg-[#1c1c1c] text-white' : 'border-[#cfcfcf] bg-white/80 text-[#1c1c1c] hover:border-[#1c1c1c]'}`}
          >
            <span className="text-[#9a9a9a]">{m.key}</span> {m.label}
          </button>
        )
      })}
    </div>
  )
}
