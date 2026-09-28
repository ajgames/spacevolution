import { addAfterEffect, addEffect, useThree } from '@react-three/fiber'
import { useEffect } from 'react'
import { create } from 'zustand'

// A live performance readout: <PerfProbe /> samples the render loop from inside
// the <Canvas>, and <PerfHud /> shows the result over it, once a second.

type PerfStats = {
  fps: number
  worst: number // longest frame in the window, ms: hitches show here before they move the average
  cpu: number // ms per frame in the render loop (useFrame work plus draw submission)
  calls: number
  triangles: number
  programs: number // compiled shaders; a jump alongside a bad `worst` is a compile hitch
  width: number
  height: number
  dpr: number
  gpu: string
}

const usePerf = create<{ stats: PerfStats | null }>(() => ({ stats: null }))

const WINDOW_MS = 1000
// What browsers fall back to without a usable GPU (Chrome, Edge, Linux Mesa).
const SOFTWARE_GPU = /swiftshader|llvmpipe|basic render driver|warp/i

// Global effects bracket the whole frame, so with autoReset off the counts
// cover every pass in it, including the droid feed's second render of the ship.
export function PerfProbe() {
  const gl = useThree((state) => state.gl)

  useEffect(() => {
    const gpu = gpuName(gl.getContext())
    console.info(`[perf] GPU: ${gpu}`)
    gl.info.autoReset = false

    let last = -1
    let frameStart = 0
    let frames = 0
    let elapsed = 0
    let worst = 0
    let cpu = 0
    // A hidden tab stops the loop; the gap isn't a frame.
    const skipGap = () => (last = -1)
    document.addEventListener('visibilitychange', skipGap)

    const offBefore = addEffect((timestamp) => {
      frameStart = performance.now()
      if (last >= 0) {
        const dt = timestamp - last
        frames++
        elapsed += dt
        worst = Math.max(worst, dt)
      }
      last = timestamp
    })
    const offAfter = addAfterEffect(() => {
      cpu += performance.now() - frameStart
      if (elapsed >= WINDOW_MS) {
        const canvas = gl.domElement
        usePerf.setState({
          stats: {
            fps: (frames * 1000) / elapsed,
            worst,
            cpu: cpu / frames,
            calls: gl.info.render.calls,
            triangles: gl.info.render.triangles,
            programs: gl.info.programs?.length ?? 0,
            width: canvas.width,
            height: canvas.height,
            dpr: gl.getPixelRatio(),
            gpu,
          },
        })
        frames = elapsed = worst = cpu = 0
      }
      gl.info.reset()
    })

    return () => {
      offBefore()
      offAfter()
      document.removeEventListener('visibilitychange', skipGap)
      gl.info.autoReset = true
      usePerf.setState({ stats: null })
    }
  }, [gl])

  return null
}

// Chrome and Safari mask RENDERER behind the debug extension; Firefox answers
// RENDERER directly and warns when the extension is used.
function gpuName(ctx: WebGLRenderingContext | WebGL2RenderingContext) {
  const name = String(ctx.getParameter(ctx.RENDERER))
  if (!name.startsWith('WebKit')) return name
  const ext = ctx.getExtension('WEBGL_debug_renderer_info')
  return ext ? String(ctx.getParameter(ext.UNMASKED_RENDERER_WEBGL)) : name
}

export function PerfHud() {
  const stats = usePerf((s) => s.stats)
  if (!stats) return null
  const software = SOFTWARE_GPU.test(stats.gpu)
  return (
    <div className="pointer-events-none absolute right-3 bottom-3 max-w-[min(30rem,calc(100vw-24px))] text-right font-mono text-[11px] leading-relaxed text-[#8a877e] tabular-nums">
      <div>
        <span className={stats.fps < 50 ? 'text-[#f0a040]' : 'text-[#d8d2c4]'}>{Math.round(stats.fps)} fps</span>
        {' · worst '}
        <span className={stats.worst > 50 ? 'text-[#f0a040]' : undefined}>{Math.round(stats.worst)} ms</span>
        {` · cpu ${stats.cpu.toFixed(1)} ms`}
      </div>
      <div>
        {stats.calls} draws · {Math.round(stats.triangles / 1000)}k tris · {stats.programs} shaders · {stats.width}×
        {stats.height} @{Number(stats.dpr.toFixed(2))}x
      </div>
      <div className={software ? 'text-[#f0a040]' : undefined}>
        {software && 'software rendering: '}
        {stats.gpu}
      </div>
    </div>
  )
}
