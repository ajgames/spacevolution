import { Loader } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { Link, useSearchParams } from 'react-router'
import { AgXToneMapping } from 'three'
import FlyScene from '../scene/FlyScene.tsx'
import { PerfHud, PerfProbe } from '../scene/Perf.tsx'
import { LIGHTING_STATES, type LightingState, VIEWS, type View } from '../scene/shipData.ts'

const isView = (value: string | null): value is View => value !== null && Object.hasOwn(VIEWS, value)
const isLighting = (value: string | null): value is LightingState =>
  LIGHTING_STATES.includes(value as LightingState)

export default function Fly() {
  // ?view=cryo&lighting=emergency makes any camera and lighting state linkable.
  const [params, setParams] = useSearchParams()
  const viewParam = params.get('view')
  const lightingParam = params.get('lighting')
  const view = isView(viewParam) ? viewParam : 'command'
  const lighting = isLighting(lightingParam) ? lightingParam : 'normal'

  const setParam = (key: string, value: string) =>
    setParams(
      (prev) => {
        prev.set(key, value)
        return prev
      },
      { replace: true },
    )

  return (
    <main className="relative h-dvh w-full bg-black font-mono text-[13px] text-[#d8d2c4]">
      {/* AgX matches Blender's view transform, which the bake was judged in. */}
      <Canvas gl={{ toneMapping: AgXToneMapping }} camera={{ fov: 65, near: 0.05, far: 100 }}>
        <FlyScene view={view} lighting={lighting} />
        <PerfProbe />
      </Canvas>
      <Loader />
      <div className="absolute top-3 left-3 max-w-[calc(100vw-24px)] border border-[#2a3130] bg-[#0c1010]/80 px-3 py-2.5">
        <div className="mb-2 flex items-baseline justify-between gap-4">
          <h1 className="text-xs tracking-widest text-[#f0a040] uppercase">Fly around ship</h1>
          <Link to="/" className="text-xs text-[#8a877e] hover:text-[#f0a040]">
            ← menu
          </Link>
        </div>
        <Options label="view" options={Object.keys(VIEWS)} value={view} onChange={(v) => setParam('view', v)} />
        <Options label="lighting" options={LIGHTING_STATES} value={lighting} onChange={(v) => setParam('lighting', v)} />
      </div>
      <PerfHud />
    </main>
  )
}

function Options(props: {
  label: string
  options: readonly string[]
  value: string
  onChange: (value: string) => void
}) {
  return (
    <div className="my-1.5 flex flex-wrap items-center gap-1.5">
      <span className="min-w-16 text-[#8a877e]">{props.label}</span>
      {props.options.map((option) => (
        <button
          key={option}
          type="button"
          onClick={() => props.onChange(option)}
          className={`cursor-pointer border bg-[#1a2020] px-2 py-1 ${option === props.value ? 'border-[#f0a040] text-[#f0a040]' : 'border-[#2a3130]'}`}
        >
          {option}
        </button>
      ))}
    </div>
  )
}
