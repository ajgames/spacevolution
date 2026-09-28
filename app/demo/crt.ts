import { CanvasTexture, SRGBColorSpace, ShaderMaterial, type Texture } from 'three'

export const AMBER = '#f0a040'
export const AMBER_DIM = '#5a3a14'
export const SCREEN_BG = '#070504'

export type CanvasScreen = { canvas: HTMLCanvasElement; ctx: CanvasRenderingContext2D; texture: CanvasTexture }

// A canvas to draw a screen into. glTF UVs put v = 0 at the top, like the
// canvas, so textures for SCREEN_* meshes use flipY = false; three.js planes
// put v = 0 at the bottom and keep the default.
export function canvasScreen(width: number, height: number, flipY: boolean): CanvasScreen {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const texture = new CanvasTexture(canvas)
  texture.colorSpace = SRGBColorSpace
  texture.flipY = flipY
  return { canvas, ctx: canvas.getContext('2d')!, texture }
}

// CRT look over a canvas texture: scanlines, a slow roll, flicker, vignette,
// and a power-on that opens from a bright horizontal line. `feed` optionally
// blends a render target underneath (render targets put v = 0 at the bottom).
export function crtMaterial(map: Texture, lines: number, feed?: Texture) {
  return new ShaderMaterial({
    uniforms: {
      map: { value: map },
      feed: { value: feed ?? null },
      useFeed: { value: feed ? 1 : 0 },
      feedFlip: { value: 1 },
      time: { value: 0 },
      power: { value: 1 },
      brightness: { value: 1 },
      lines: { value: lines },
    },
    vertexShader: /* glsl */ `
      varying vec2 vUv;
      void main() {
        vUv = uv;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: /* glsl */ `
      uniform sampler2D map;
      uniform sampler2D feed;
      uniform float useFeed;
      uniform float feedFlip;
      uniform float time;
      uniform float power;
      uniform float brightness;
      uniform float lines;
      varying vec2 vUv;

      void main() {
        vec2 c = vUv - 0.5;
        // Power-on: a dot widens into a line, then the line opens into the picture.
        float w = mix(0.0, 0.5, smoothstep(0.0, 0.3, power));
        float h = mix(0.003, 0.5, smoothstep(0.3, 1.0, power));
        float mask = step(abs(c.x), w) * step(abs(c.y), h);

        vec3 col = texture2D(map, vUv).rgb;
        if (useFeed > 0.5) {
          vec2 fuv = vec2(vUv.x, mix(vUv.y, 1.0 - vUv.y, feedFlip));
          vec3 f = texture2D(feed, fuv).rgb;
          float lum = dot(f, vec3(0.3, 0.59, 0.11));
          col += vec3(lum * 1.3, lum * 1.1, lum * 0.75); // warm monochrome feed under the overlay
        }
        float flash = (1.0 - smoothstep(0.3, 0.7, power)) * step(0.001, power);
        col += vec3(1.0, 0.85, 0.6) * flash;

        float scan = 0.72 + 0.28 * sin(vUv.y * lines * 6.2831);
        float roll = 0.94 + 0.06 * sin(vUv.y * 9.0 - time * 2.3);
        float flicker = 0.97 + 0.03 * sin(time * 57.0);
        float vignette = smoothstep(0.9, 0.3, length(c * vec2(1.0, 1.25)));
        col *= scan * roll * flicker * vignette * brightness * mask;
        col += vec3(0.012, 0.009, 0.006) * mask; // faint glass glow even on black

        gl_FragColor = vec4(col, 1.0);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }
    `,
  })
}

// --- drawing ---------------------------------------------------------------

export function clear(ctx: CanvasRenderingContext2D) {
  ctx.fillStyle = SCREEN_BG
  ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height)
}

export function textLines(
  ctx: CanvasRenderingContext2D,
  lines: string[],
  { x = 0.07, y = 0.13, size = 0.075, color = AMBER, gap = 1.45 } = {},
) {
  const { width, height } = ctx.canvas
  const px = Math.round(height * size)
  ctx.font = `bold ${px}px ui-monospace, Menlo, monospace`
  ctx.textBaseline = 'top'
  ctx.fillStyle = color
  ctx.shadowColor = color
  ctx.shadowBlur = px * 0.35
  lines.forEach((line, i) => ctx.fillText(line, width * x, height * y + i * px * gap))
  ctx.shadowBlur = 0
}

// A dim standby screen: the tube is warm but there's no signal.
export function drawStandby(ctx: CanvasRenderingContext2D, label: string, cursorOn: boolean) {
  clear(ctx)
  textLines(ctx, [label + (cursorOn ? ' _' : '')], { color: AMBER_DIM, y: 0.44, x: 0.08, size: 0.08 })
}

// Top-down ship schematic for SCREEN_status, with the failing pod flashing.
export function drawShipMap(ctx: CanvasRenderingContext2D, failingPod: number, flashOn: boolean) {
  const { width: W, height: H } = ctx.canvas
  clear(ctx)
  textLines(ctx, ['SHIP STATUS', 'PRIMARY BUS ONLINE'], { size: 0.055, y: 0.05, gap: 1.3 })
  ctx.strokeStyle = AMBER
  ctx.lineWidth = Math.max(2, W / 220)
  ctx.shadowColor = AMBER
  ctx.shadowBlur = 6
  const box = (x: number, y: number, w: number, h: number) => ctx.strokeRect(W * x, H * y, W * w, H * h)
  box(0.36, 0.24, 0.28, 0.22) // command
  box(0.46, 0.46, 0.08, 0.18) // stem
  box(0.24, 0.6, 0.52, 0.08) // corridor
  box(0.06, 0.5, 0.18, 0.3) // cryo
  box(0.76, 0.5, 0.18, 0.3) // engineering
  ctx.shadowBlur = 0
  // cryo pods: 01-03 on the north wall, 04-06 on the south wall (west to east reversed)
  const pods = [
    [0.19, 0.53],
    [0.14, 0.53],
    [0.09, 0.53],
    [0.09, 0.73],
    [0.14, 0.73],
    [0.19, 0.73],
  ]
  pods.forEach(([x, y], i) => {
    const failing = i + 1 === failingPod
    ctx.fillStyle = failing ? (flashOn ? '#ffb040' : '#3a2008') : AMBER_DIM
    if (failing && flashOn) {
      ctx.shadowColor = '#ffb040'
      ctx.shadowBlur = 16
    }
    ctx.fillRect(W * (x - 0.018), H * (y - 0.03), W * 0.036, H * 0.06)
    ctx.shadowBlur = 0
  })
  textLines(ctx, [`CRYO ${String(failingPod).padStart(2, '0')}: VITALS LOW`], {
    size: 0.05,
    y: 0.87,
    color: flashOn ? '#ffb040' : AMBER_DIM,
  })
}
