// Draws the Spacevelution logo and favicons, then renders the raster sizes.
//
// The mark is the ship's own floor plan (blender/screenshots/step6_final/top_plan.png):
// the command module on top, a T-shaped corridor, and the cryo and engineering pods
// either side, drawn as an amber vector-scope trace. The red dot is engineering's
// blinking button, the first thing the demo sends you to.
//
// Writes into public/:
//   logo.svg, logo.png (2048², transparent)   landing screen
//   favicon.svg, favicon.ico (16/32/48)        browser tabs; Safari only reads the .ico
//   apple-touch-icon.png (180², opaque)        iOS home screen
//
// Rasterizing goes through headless Chrome (set CHROME to override the macOS path).
// Run with `npm run icons`.
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'

const PUBLIC = join(import.meta.dirname, '../public')
const CHROME = process.env.CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'

// The landing page's palette (app/routes/landing.tsx), plus the alarm red.
const AMBER = '#f0a040'
const HOT = '#ffe4bd'
const RED = '#ff4a3d'
const TILE = '#0c1010'

// ---- The ship plan, in top-plan pixels with the origin at the centre ----
// Command 460 × 385 with chamfered top corners, pods 460² octagons, corridors ~118 wide.
const PLAN: [number, number][] = [
  [-155, -500], [155, -500], [230, -425], [230, -115], [60, -115], [60, 212],
  [390, 212], [390, 125], [475, 40], [765, 40], [850, 125], [850, 415], [765, 500],
  [475, 500], [390, 415], [390, 328],
  [-390, 328], [-390, 415], [-475, 500], [-765, 500], [-850, 415], [-850, 125],
  [-765, 40], [-475, 40], [-390, 125], [-390, 212], [-60, 212], [-60, -115],
  [-230, -115], [-230, -425],
]

const n = (v: number) => +v.toFixed(2)

type LogoOptions = {
  /** Plan pixels to logo units. */
  scale?: number
  /** Nudges the ship up: the pods carry most of its mass, so true centring reads low. */
  dy?: number
  /** Cryo pods, core racks, console and the dashed route. Too fine below ~300px. */
  detail?: boolean
  /** Scope graduations. Too fine below ~300px. */
  ticks?: boolean
  /** Multiplies every line weight and glow radius, for small renders. */
  weight?: number
  /** Extra markup painted first, e.g. an opaque background. */
  background?: string
  /** Rendered width and height; the viewBox is always 1024. */
  px?: number
}

function logo({
  scale: s = 0.45,
  dy = -30,
  detail = true,
  ticks: showTicks = true,
  weight: w = 1,
  background = '',
  px = 1024,
}: LogoOptions = {}) {
  const c = 512
  const cy = c + dy
  const P = (x: number, y: number) => [n(c + x * s), n(cy + y * s)] as const
  const ship = 'M' + PLAN.map(([x, y]) => P(x, y).join(' ')).join(' L') + ' Z'
  const R = 440

  // Scope graduations outside the ring: every 6°, longer every 30°, arrows at the cardinals.
  const polar = (deg: number, r: number) => {
    const t = ((deg - 90) * Math.PI) / 180
    return [n(c + Math.cos(t) * r), n(c + Math.sin(t) * r)] as const
  }
  const ticks: string[] = []
  for (let a = 0; showTicks && a < 360; a += 6) {
    if (a % 90 === 0) continue
    ticks.push(`M${polar(a, 450).join(' ')} L${polar(a, a % 30 === 0 ? 474 : 462).join(' ')}`)
  }
  const k = Math.sqrt(w)
  const arrows = [0, 90, 180, 270]
    .map((a) => {
      const [x, y] = polar(a, R + 10)
      const t = ((a - 90) * Math.PI) / 180
      const [nx, ny] = [Math.cos(t), Math.sin(t)]
      return `M${n(x - ny * 12 * k)} ${n(y + nx * 12 * k)} L${n(x + nx * 34 * k)} ${n(y + ny * 34 * k)} L${n(x + ny * 12 * k)} ${n(y - nx * 12 * k)} Z`
    })
    .join(' ')

  const rect = (x: number, y: number, rw: number, rh: number, r = 0) => {
    const [X, Y] = P(x, y)
    return `<rect x="${X}" y="${Y}" width="${n(rw * s)}" height="${n(rh * s)}" rx="${n(r * s)}"/>`
  }
  const interior = [
    // six cryo pods
    ...[-715, -615, -515].flatMap((x) => [rect(x - 38, 70, 76, 100, 14), rect(x - 38, 370, 76, 100, 14)]),
    // the core's rack cabinets
    ...[0, 1, 2, 3].map((i) => rect(730, 140 + i * 70, 80, 64, 4)),
    // the curved console and its chair
    `<path d="M${P(-150, -330).join(' ')} L${P(-95, -405).join(' ')} L${P(95, -405).join(' ')} L${P(150, -330).join(' ')}"/>`,
    rect(-22, -330, 44, 44, 8),
    // the demo's route, from the cryo bay down the corridor to engineering
    `<path d="M${P(-615, 270).join(' ')} L${P(560, 270).join(' ')}" stroke-width="4" stroke-dasharray="4 14" stroke-linecap="round" opacity="0.9"/>`,
  ]
  const [bx, by] = P(630, 270)

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="${px}" height="${px}">
  <defs>
    <filter id="glow" filterUnits="userSpaceOnUse" x="0" y="0" width="1024" height="1024" color-interpolation-filters="sRGB">
      <feGaussianBlur in="SourceGraphic" stdDeviation="${5 * w}" result="near"/>
      <feGaussianBlur in="SourceGraphic" stdDeviation="${20 * w}" result="far"/>
      <feComponentTransfer in="far" result="farDim"><feFuncA type="linear" slope="0.75"/></feComponentTransfer>
      <feMerge><feMergeNode in="farDim"/><feMergeNode in="near"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="soft" filterUnits="userSpaceOnUse" x="0" y="0" width="1024" height="1024" color-interpolation-filters="sRGB">
      <feGaussianBlur in="SourceGraphic" stdDeviation="${4 * w}" result="near"/>
      <feMerge><feMergeNode in="near"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <clipPath id="hull"><path d="${ship}"/></clipPath>
    <radialGradient id="wash" cx="${c}" cy="${c}" r="${R}" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="${AMBER}" stop-opacity="0.09"/>
      <stop offset="0.75" stop-color="${AMBER}" stop-opacity="0.03"/>
      <stop offset="1" stop-color="${AMBER}" stop-opacity="0.06"/>
    </radialGradient>
  </defs>
${background}
  <!-- scope: faint phosphor wash, ring, graduations -->
  <circle cx="${c}" cy="${c}" r="${R}" fill="url(#wash)"/>
  <g filter="url(#soft)" fill="none" stroke="${AMBER}" stroke-linecap="round">
    <circle cx="${c}" cy="${c}" r="${R}" stroke-width="${5 * w}" opacity="0.7"/>
    ${ticks.length ? `<path d="${ticks.join(' ')}" stroke-width="${4 * w}" opacity="0.5"/>` : ''}
    <path d="${arrows}" fill="${AMBER}" stroke="none" opacity="0.8"/>
  </g>

  <path d="${ship}" fill="${AMBER}" opacity="0.1"/>
  ${
    detail
      ? `<g clip-path="url(#hull)" fill="none" stroke="${AMBER}" stroke-width="3" opacity="0.5" stroke-linejoin="round">
    ${interior.join('\n    ')}
  </g>`
      : ''
  }

  <!-- hull: an amber beam with a hot core -->
  <g filter="url(#glow)" fill="none" stroke-linejoin="round">
    <path d="${ship}" stroke="${AMBER}" stroke-width="${11 * w}"/>
    <path d="${ship}" stroke="${HOT}" stroke-width="${3.5 * w}" opacity="0.85"/>
  </g>

  <!-- engineering's blinking button -->
  <g filter="url(#glow)">
    <circle cx="${bx}" cy="${by}" r="${n(62 * s * k)}" fill="none" stroke="${RED}" stroke-width="${3 * w}" opacity="0.55"/>
    <circle cx="${bx}" cy="${by}" r="${n(26 * s * k)}" fill="${RED}"/>
    <circle cx="${bx}" cy="${by}" r="${n(10 * s * k)}" fill="#ffd2c8"/>
  </g>
</svg>
`
}

// ---- Favicon: the same plan snapped to a 16px grid, drawn at 2 units per pixel ----
// Command 6×5 px, stem 2 px, corridor 1 px, pods 5×5 px with 1 px chamfers. Solid fill on
// a dark tile, so it holds up on light and dark tab bars alike. Firefox blinks the dot.
const FAVICON = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <style>@keyframes blink{50%{opacity:.2}}.blink{animation:blink 1.4s steps(1) infinite}</style>
  <rect width="32" height="32" rx="7" fill="${TILE}"/>
  <path fill="${AMBER}" d="M12 4 H20 L22 6 V14 H18 V22 H20 V20 L22 18 H28 L30 20 V26 L28 28 H22 L20 26 V24 H12 V26 L10 28 H4 L2 26 V20 L4 18 H10 L12 20 V22 H14 V14 H10 V6 Z"/>
  <rect class="blink" x="24" y="22" width="2" height="2" fill="${RED}"/>
</svg>
`

// ---- Home-screen icon: the logo on an opaque screen (iOS rounds the corners itself) ----
const APPLE_TOUCH = logo({
  px: 180,
  detail: false,
  ticks: false,
  weight: 2.6,
  background: `  <radialGradient id="screen" cx="50%" cy="46%" r="72%">
    <stop offset="0" stop-color="#141c1b"/><stop offset="1" stop-color="#040606"/>
  </radialGradient>
  <rect width="1024" height="1024" fill="url(#screen)"/>`,
})

// ---- Rendering ----

const tmp = mkdtempSync(join(tmpdir(), 'spacevelution-icons-'))

function render(svg: string, size: number, name: string) {
  const svgPath = join(tmp, `${name}.svg`)
  const htmlPath = join(tmp, `${name}.html`)
  const pngPath = join(tmp, `${name}.png`)
  writeFileSync(svgPath, svg)
  writeFileSync(
    htmlPath,
    `<body style="margin:0"><img src="${pathToFileURL(svgPath).href}" width="${size}" height="${size}" style="display:block">`,
  )
  execFileSync(
    CHROME,
    [
      '--headless=new',
      '--disable-gpu',
      '--hide-scrollbars',
      '--force-device-scale-factor=1',
      '--default-background-color=00000000',
      `--window-size=${size},${size}`,
      `--screenshot=${pngPath}`,
      pathToFileURL(htmlPath).href,
    ],
    { stdio: 'ignore' },
  )
  return readFileSync(pngPath)
}

/** An .ico holding PNG-encoded images, which every current browser reads. */
function ico(images: { size: number; png: Buffer }[]) {
  const header = Buffer.alloc(6 + 16 * images.length)
  header.writeUInt16LE(0, 0)
  header.writeUInt16LE(1, 2) // type: icon
  header.writeUInt16LE(images.length, 4)
  let offset = header.length
  images.forEach(({ size, png }, i) => {
    const entry = 6 + 16 * i
    header.writeUInt8(size % 256, entry) // 0 means 256
    header.writeUInt8(size % 256, entry + 1)
    header.writeUInt16LE(1, entry + 4) // colour planes
    header.writeUInt16LE(32, entry + 6) // bits per pixel
    header.writeUInt32LE(png.length, entry + 8)
    header.writeUInt32LE(offset, entry + 12)
    offset += png.length
  })
  return Buffer.concat([header, ...images.map((image) => image.png)])
}

try {
  const logoSvg = logo()
  writeFileSync(join(PUBLIC, 'logo.svg'), logoSvg)
  writeFileSync(join(PUBLIC, 'logo.png'), render(logoSvg, 2048, 'logo'))

  writeFileSync(join(PUBLIC, 'favicon.svg'), FAVICON)
  const sizes = [16, 32, 48]
  writeFileSync(
    join(PUBLIC, 'favicon.ico'),
    ico(sizes.map((size) => ({ size, png: render(FAVICON, size, `favicon-${size}`) }))),
  )

  writeFileSync(join(PUBLIC, 'apple-touch-icon.png'), render(APPLE_TOUCH, 180, 'apple-touch-icon'))
  console.log('icons: wrote logo.svg, logo.png, favicon.svg, favicon.ico, apple-touch-icon.png to public/')
} finally {
  rmSync(tmp, { recursive: true, force: true })
}
