import { useCallback, useEffect, useRef } from 'react'
import {
  Mesh,
  OrthographicCamera,
  PlaneGeometry,
  Scene,
  ShaderMaterial,
  type Texture,
  type WebGLRenderer,
  WebGLRenderTarget,
} from 'three'
import { audioGraph } from '../demo/audio.ts'

// Puts the mission screen (the droid's camera under its overlay) on the air as
// an analog TV channel, through the dev server's broadcast plugin
// (scripts/broadcast.ts) and a HackRF. It asks the plugin every few seconds
// whether a HackRF is plugged in; until one is, it does nothing. Dev only.

const ENDPOINT = '/__broadcast'
const WIDTH = 320
const HEIGHT = 240
const FPS = 30
const POLL_MS = 3000
const AUDIO_BLOCK = 2048

// Returns a function to call on every frame the feed is rendered.
export function useBroadcast(feed: Texture, overlay: Texture) {
  const station = useRef<Station | null>(null)
  useEffect(() => {
    if (!import.meta.env.DEV) return
    const s = createStation(feed, overlay)
    station.current = s
    return () => {
      s.dispose()
      station.current = null
    }
  }, [feed, overlay])
  return useCallback((gl: WebGLRenderer) => station.current?.capture(gl), [])
}

type Station = { capture(gl: WebGLRenderer): void; dispose(): void }

function createStation(feed: Texture, overlay: Texture): Station {
  let on = false // the plugin has a HackRF to transmit with
  let gone = false // disposed, or there's no plugin to talk to
  let busy = false // a picture is being read back or sent
  let lastPicture = 0
  let poll: ReturnType<typeof setTimeout> | undefined
  let untap: (() => void) | null = null
  let tapping = false
  const pixels = new Uint8Array(WIDTH * HEIGHT * 4)
  let pass: ReturnType<typeof screenPass> | null = null

  const post = (path: string, body: BufferSource) =>
    fetch(`${ENDPOINT}/${path}`, { method: 'POST', body }).catch(() => undefined)

  const stopAudio = () => {
    untap?.()
    untap = null
    tapping = false
  }

  const check = async () => {
    try {
      const res = await fetch(`${ENDPOINT}/status`)
      // Without the plugin the dev server answers with the app's HTML
      if (!res.ok || !res.headers.get('content-type')?.includes('json')) gone = true
      else on = (await res.json()).on === true
    } catch {
      on = false
    }
    if (!on) stopAudio()
    if (!gone) poll = setTimeout(check, POLL_MS)
  }
  void check()

  return {
    capture(gl) {
      if (!on || gone || busy) return
      const now = performance.now()
      if (now - lastPicture < 1000 / FPS - 4) return
      lastPicture = now
      busy = true

      pass ??= screenPass(feed, overlay)
      const previous = gl.getRenderTarget()
      gl.setRenderTarget(pass.target)
      gl.render(pass.scene, pass.camera)
      gl.setRenderTarget(previous)
      // Read back without stalling the GPU; the picture is a frame or two old.
      gl.readRenderTargetPixelsAsync(pass.target, 0, 0, WIDTH, HEIGHT, pixels)
        .then(() => post('picture', pixels))
        .catch(() => undefined)
        .finally(() => (busy = false))

      // The game's sound, once its audio graph exists (the first sound makes it)
      const graph = audioGraph()
      if (graph && !tapping) {
        tapping = true
        tapAudio(graph, (block, rate) => on && post(`audio?rate=${rate}`, block)).then(
          (stop) => (tapping && !gone ? (untap = stop) : stop()),
          () => (tapping = false),
        )
      }
    },

    dispose() {
      gone = true
      clearTimeout(poll)
      stopAudio()
      pass?.dispose()
    },
  }
}

// Draws the mission screen as the game's CRT shader does (overlay plus a warm
// monochrome feed, AgX tone mapped), minus the scanlines and vignette a real
// screen brings, into a 320x240 target. Readback row 0 is the top of the picture.
function screenPass(feed: Texture, overlay: Texture) {
  const target = new WebGLRenderTarget(WIDTH, HEIGHT, { depthBuffer: false })
  const material = new ShaderMaterial({
    toneMapped: false, // tone mapped by hand below; render targets skip it anyway
    uniforms: { map: { value: overlay }, feed: { value: feed }, toneMappingExposure: { value: 1 } },
    vertexShader: /* glsl */ `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = vec4(position.xy, 0.0, 1.0);
      }
    `,
    fragmentShader: /* glsl */ `
      #include <tonemapping_pars_fragment>
      uniform sampler2D map;
      uniform sampler2D feed;
      varying vec2 vUv;

      void main() {
        // The overlay canvas has v = 0 at its top; the feed target at its bottom.
        vec3 col = texture2D(map, vUv).rgb;
        float lum = dot(texture2D(feed, vec2(vUv.x, 1.0 - vUv.y)).rgb, vec3(0.3, 0.59, 0.11));
        col += vec3(lum * 1.3, lum * 1.1, lum * 0.75);
        // The game shows the screen at brightness 2.4 under scanlines averaging ~0.8
        col = AgXToneMapping(col * 1.9);
        gl_FragColor = sRGBTransferOETF(vec4(col, 1.0));
      }
    `,
  })
  const quad = new Mesh(new PlaneGeometry(2, 2), material)
  quad.frustumCulled = false
  const scene = new Scene().add(quad)
  const camera = new OrthographicCamera(-1, 1, 1, -1, 0, 1)
  return {
    target,
    scene,
    camera,
    dispose() {
      target.dispose()
      material.dispose()
      quad.geometry.dispose()
    },
  }
}

// Mono PCM from the master bus, in blocks, through an AudioWorklet. Returns
// the undo. The worklet's output is silent; it's connected so it keeps running.
const TAP = `
registerProcessor('broadcast-tap', class extends AudioWorkletProcessor {
  block = new Float32Array(${AUDIO_BLOCK})
  filled = 0
  process([[left, right = left]]) {
    for (let i = 0; left && i < left.length; i++) {
      this.block[this.filled++] = (left[i] + right[i]) / 2
      if (this.filled === this.block.length) {
        this.port.postMessage(this.block, [this.block.buffer])
        this.block = new Float32Array(${AUDIO_BLOCK})
        this.filled = 0
      }
    }
    return true
  }
})
`
const tapLoaded = new WeakSet<BaseAudioContext>()

async function tapAudio(
  { ctx, master }: { ctx: AudioContext; master: GainNode },
  onBlock: (block: Float32Array<ArrayBuffer>, rate: number) => void,
) {
  if (!tapLoaded.has(ctx)) {
    const url = URL.createObjectURL(new Blob([TAP], { type: 'text/javascript' }))
    try {
      await ctx.audioWorklet.addModule(url)
    } finally {
      URL.revokeObjectURL(url)
    }
    tapLoaded.add(ctx)
  }
  const node = new AudioWorkletNode(ctx, 'broadcast-tap', { outputChannelCount: [1] })
  node.port.onmessage = (e: MessageEvent<Float32Array<ArrayBuffer>>) => onBlock(e.data, ctx.sampleRate)
  master.connect(node)
  node.connect(ctx.destination)
  return () => {
    node.port.onmessage = null
    master.disconnect(node)
    node.disconnect()
  }
}
