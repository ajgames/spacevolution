// An analog NTSC-M TV signal as HackRF I/Q samples, built one field at a time
// from a 320x240 RGBA picture and a stream of audio.
//
// The picture goes out as "240p" like an old console: 262-line fields with no
// interlace. Sampling at 4x the color subcarrier gives exactly 910 samples a
// line, and the subcarrier's samples are just 0, +1, 0, -1, so adding color
// costs an add rather than a multiply. A field is a whole number of subcarrier
// cycles, so the video part of every field is identical until the picture
// changes and is built once per frame.
//
// The picture carrier sits at 0 Hz of the I/Q stream (the HackRF's own LO
// leakage then only adds to it), amplitude modulated with both sidebands and
// negative modulation, so video lives in I alone. The FM sound carrier is
// 4.5 MHz above it.

export const SAMPLE_RATE = 14_318_182 // 4 x 3.579545 MHz; hackrf_transfer takes whole Hz
export const WIDTH = 320
export const HEIGHT = 240

const LINE = 910 // samples a line
const LINES = 262 // lines a field
export const FIELD = LINE * LINES
const LINE_RATE = SAMPLE_RATE / LINE // 15.734 kHz

// Sample offsets from the leading edge of H sync
const HALF = LINE / 2
const HSYNC = 67 // 4.7 us
const EQ = 33 // 2.3 us equalizing pulse
const BROAD = HALF - 67 // vertical sync pulse, leaving a 4.7 us serration
const BURST_START = 76 // 19 cycles after 0H...
const BURST_END = 112 // ...for 9 cycles
const ACTIVE_START = 135 // 9.4 us after 0H
const ACTIVE = 754 // up to the 1.5 us front porch
const FIRST_ROW_LINE = 21 // picture rows are lines 22-261

// Levels in IRE
const SYNC_IRE = -40
const SETUP_IRE = 7.5
const BURST_IRE = 20 // half of the 40 IRE p-p burst

// Signal levels in DAC steps: the sync-tip carrier, and the sound carrier.
// Their sum plus filter overshoot stays under 127.
const PEAK = 100
const SOUND = 20
const BLANKING = 0.75 * PEAK // blanking is 75% carrier...
const PER_IRE = -0.00625 * PEAK // ...and white (100 IRE) is 12.5%

// FM sound: +/-25 kHz is full scale. 75 us pre-emphasis at the line rate.
const DEVIATION = 25_000
const AUDIO_GAIN = 0.6
const PRE_EMPHASIS = Math.exp(-1 / (75e-6 * LINE_RATE))

// Subcarrier samples at 4x fsc: sin and cos of n * 90 degrees.
const SIN4 = [0, 1, 0, -1]
const COS4 = [1, 0, -1, 0]

// The sound carrier's phase accumulator steps through a 4096-entry table. Q
// is only ever the sound carrier, so the table holds it pre-shifted into the
// high byte of a little-endian I/Q sample.
const TABLE_BITS = 12
const TURN = 2 ** 32
const SOUND_I = new Int8Array(1 << TABLE_BITS)
const SOUND_Q = new Uint16Array(1 << TABLE_BITS)
for (let k = 0; k < SOUND_I.length; k++) {
  const a = (2 * Math.PI * k) / SOUND_I.length
  SOUND_I[k] = Math.round(SOUND * Math.cos(a))
  SOUND_Q[k] = (Math.round(SOUND * Math.sin(a)) & 0xff) << 8
}
const CARRIER_STEP = Math.round((4_500_000 / SAMPLE_RATE) * TURN)
const DEVIATION_STEP = (DEVIATION / SAMPLE_RATE) * TURN

// Windowed-sinc low-pass that keeps the video under 4.2 MHz: the burst and
// chroma at 3.58 MHz pass, and nothing reaches the sound carrier at 4.5 MHz.
function lowPassTaps(cutoff: number, count: number) {
  const taps = new Float32Array(count)
  const mid = (count - 1) / 2
  let sum = 0
  for (let i = 0; i < count; i++) {
    const t = i - mid
    const sinc = t === 0 ? 1 : Math.sin(2 * Math.PI * (cutoff / SAMPLE_RATE) * t) / (Math.PI * t * 2 * (cutoff / SAMPLE_RATE))
    const blackman = 0.42 - 0.5 * Math.cos((2 * Math.PI * i) / (count - 1)) + 0.08 * Math.cos((4 * Math.PI * i) / (count - 1))
    taps[i] = sinc * blackman
    sum += taps[i]
  }
  return taps.map((t) => t / sum)
}

// Filters a whole field circularly, since fields repeat.
function lowPassField(x: Float32Array) {
  const taps = lowPassTaps(4_150_000, 127)
  const mid = (taps.length - 1) / 2
  const out = new Float32Array(x.length)
  for (let n = 0; n < x.length; n++) {
    let acc = 0
    for (let k = 0; k < taps.length; k++) acc += taps[k] * x[(n + k - mid + x.length) % x.length]
    out[n] = acc
  }
  return out
}

// Sync, blanking and burst: everything but the picture, as carrier levels.
function blankField() {
  const ire = new Float32Array(FIELD)
  for (let line = 0; line < LINES; line++) {
    const o = line * LINE
    if (line < 3 || (line >= 6 && line < 9)) {
      ire.fill(SYNC_IRE, o, o + EQ)
      ire.fill(SYNC_IRE, o + HALF, o + HALF + EQ)
    } else if (line < 6) {
      ire.fill(SYNC_IRE, o, o + BROAD)
      ire.fill(SYNC_IRE, o + HALF, o + HALF + BROAD)
    } else {
      ire.fill(SYNC_IRE, o, o + HSYNC)
      // Burst at 180 degrees, on the -(B-Y) axis
      for (let n = o + BURST_START; n < o + BURST_END; n++) ire[n] = -BURST_IRE * SIN4[n & 3]
    }
  }
  return lowPassField(ire).map((v) => BLANKING + PER_IRE * v)
}

// Where each active sample reads the picture: Lanczos-3 weights over six
// pixels for luma, linear between two for chroma, and a short fade in and out
// of blanking at the line's ends.
const LUMA_TAPS = 6
const lumaFrom = new Int32Array(ACTIVE * LUMA_TAPS)
const lumaWeight = new Float32Array(ACTIVE * LUMA_TAPS)
const chromaFrom = new Int32Array(ACTIVE)
const chromaTo = new Int32Array(ACTIVE)
const chromaMix = new Float32Array(ACTIVE)
const edge = new Float32Array(ACTIVE)
{
  const lanczos = (t: number) => (t === 0 ? 1 : Math.abs(t) >= 3 ? 0 : (3 * Math.sin(Math.PI * t) * Math.sin((Math.PI * t) / 3)) / (Math.PI * Math.PI * t * t))
  const clampX = (x: number) => Math.min(WIDTH - 1, Math.max(0, x))
  const FADE = 6
  for (let s = 0; s < ACTIVE; s++) {
    const x = ((s + 0.5) * WIDTH) / ACTIVE - 0.5
    const left = Math.floor(x)
    let sum = 0
    for (let k = 0; k < LUMA_TAPS; k++) {
      const px = left - 2 + k
      lumaFrom[s * LUMA_TAPS + k] = clampX(px)
      lumaWeight[s * LUMA_TAPS + k] = lanczos(x - px)
      sum += lanczos(x - px)
    }
    for (let k = 0; k < LUMA_TAPS; k++) lumaWeight[s * LUMA_TAPS + k] /= sum
    chromaFrom[s] = clampX(left)
    chromaTo[s] = clampX(left + 1)
    chromaMix[s] = left < 0 ? 0 : left >= WIDTH - 1 ? 0 : x - left
    const fromEnd = Math.min(s, ACTIVE - 1 - s)
    edge[s] = fromEnd >= FADE ? 1 : 0.5 - 0.5 * Math.cos((Math.PI * (fromEnd + 0.5)) / FADE)
  }
}

export type Modulator = {
  // A 320x240 RGBA picture, top row first. It goes out from the next field.
  setPicture(rgba: Uint8Array): void
  // Mono audio at any sample rate. About 100 ms is buffered to ride out gaps.
  pushAudio(samples: Float32Array, sampleRate: number): void
  // Writes the next field: FIELD samples, each int8 I in the low byte and int8
  // Q in the high byte, which is hackrf_transfer's byte order on a
  // little-endian machine.
  fill(out: Uint16Array): void
}

export function createModulator(): Modulator {
  const blank = blankField()
  const blankSteps = Int8Array.from(blank, Math.round)
  const video = blankSteps.slice() // the field's I channel without sound, in DAC steps
  let picture: Uint8Array | null = null

  // Per-pixel luma and chroma in IRE, reused between frames
  const y = new Float32Array(WIDTH * HEIGHT)
  const u = new Float32Array(WIDTH * HEIGHT)
  const v = new Float32Array(WIDTH * HEIGHT)
  const row = new Float32Array(WIDTH)

  // Chroma gets a [1 4 6 4 1] blur along the row, to keep it near 1 MHz wide.
  const blurRow = (plane: Float32Array, o: number) => {
    const last = o + WIDTH - 1
    for (let x = 0; x < WIDTH; x++) {
      const at = o + x
      const a = plane[Math.max(o, at - 2)]
      const b = plane[Math.max(o, at - 1)]
      const d = plane[Math.min(last, at + 1)]
      const e = plane[Math.min(last, at + 2)]
      row[x] = (a + 4 * b + 6 * plane[at] + 4 * d + e) / 16
    }
    plane.set(row, o)
  }

  const buildVideo = (rgba: Uint8Array) => {
    // Locals, not closure variables, for the hot loops
    const [Y, U, V, out, base] = [y, u, v, video, blank]
    const [from, weight, cFrom, cTo, cMix, fade] = [lumaFrom, lumaWeight, chromaFrom, chromaTo, chromaMix, edge]
    for (let p = 0; p < WIDTH * HEIGHT; p++) {
      const r = rgba[p * 4] / 255
      const g = rgba[p * 4 + 1] / 255
      const b = rgba[p * 4 + 2] / 255
      const luma = 0.299 * r + 0.587 * g + 0.114 * b
      Y[p] = SETUP_IRE + 92.5 * luma
      U[p] = 92.5 * 0.492111 * (b - luma)
      V[p] = 92.5 * 0.877283 * (r - luma)
    }
    out.set(blankSteps)
    for (let r = 0; r < HEIGHT; r++) {
      const o = r * WIDTH
      blurRow(U, o)
      blurRow(V, o)
      const start = (FIRST_ROW_LINE + r) * LINE + ACTIVE_START
      for (let s = 0; s < ACTIVE; s++) {
        const n = start + s
        const k = s * LUMA_TAPS
        const luma =
          weight[k] * Y[o + from[k]] +
          weight[k + 1] * Y[o + from[k + 1]] +
          weight[k + 2] * Y[o + from[k + 2]] +
          weight[k + 3] * Y[o + from[k + 3]] +
          weight[k + 4] * Y[o + from[k + 4]] +
          weight[k + 5] * Y[o + from[k + 5]]
        // Only one of U and V is nonzero on any sample of the subcarrier
        const phase = n & 3
        const plane = phase & 1 ? U : V
        const c0 = plane[o + cFrom[s]]
        const chroma = (phase < 2 ? 1 : -1) * (c0 + cMix[s] * (plane[o + cTo[s]] - c0))
        const level = base[n] + PER_IRE * fade[s] * (luma + chroma)
        out[n] = Math.round(level > 100 ? 100 : level < -100 ? -100 : level)
      }
    }
  }

  // Audio: a ring buffer read at the line rate, one sample per line.
  const ring = new Float32Array(1 << 17)
  const mask = ring.length - 1
  let rate = 48_000
  let written = 0
  let read = 0
  let playing = false
  let last = 0
  let phase = 0

  const nextAudio = () => {
    const step = rate / LINE_RATE
    const buffered = written - read
    if (!playing && buffered >= rate * 0.1) playing = true
    if (!playing || buffered < step + 1) {
      playing = false
      return 0
    }
    // Average the input samples that fall in this line
    let sum = 0
    let count = 0
    for (let i = Math.ceil(read); i < read + step; i++, count++) sum += ring[i & mask]
    read += step
    const x = count ? sum / count : 0
    const emphasized = (x - PRE_EMPHASIS * last) / (1 - PRE_EMPHASIS)
    last = x
    return Math.max(-1, Math.min(1, AUDIO_GAIN * emphasized))
  }

  return {
    setPicture(rgba) {
      if (rgba.length !== WIDTH * HEIGHT * 4) throw new Error(`expected a ${WIDTH}x${HEIGHT} RGBA picture`)
      picture = rgba
    },

    pushAudio(samples, sampleRate) {
      if (sampleRate !== rate) {
        rate = sampleRate
        read = written
        playing = false
      }
      for (let i = 0; i < samples.length; i++) ring[written++ & mask] = samples[i]
      // Fell behind the browser: skip ahead, keeping 100 ms
      if (written - read > rate * 0.3) read = written - rate * 0.1
    },

    fill(out) {
      if (picture) {
        buildVideo(picture)
        picture = null
      }
      // Locals, not closure variables: this loop runs 14 million times a second
      let at = phase
      const steps = video
      for (let line = 0; line < LINES; line++) {
        const step = CARRIER_STEP + Math.round(nextAudio() * DEVIATION_STEP)
        const end = (line + 1) * LINE
        for (let n = line * LINE; n < end; n++) {
          at = (at + step) >>> 0 // wraps at 2^32
          const k = at >>> (32 - TABLE_BITS)
          out[n] = SOUND_Q[k] | ((steps[n] + SOUND_I[k]) & 0xff)
        }
      }
      phase = at
    },
  }
}
