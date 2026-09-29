import { audioGraph } from '../demo/audio.ts'
import { CARETAKER_LINES, type CaretakerLineId } from './lines.ts'

// The caretaker's voice: recorded lines (npm run voice) played flat through an
// analyser, so the face can read how loud and how bright the sound is each frame
// and shape the mouth from that. Without a recording the line is "read" from its
// text at a speaking pace instead, which keeps the subtitles and the mouth in step.

type Voice = {
  ctx: AudioContext
  input: GainNode
  analyser: AnalyserNode
  wave: Float32Array<ArrayBuffer>
  spectrum: Float32Array<ArrayBuffer>
}
let voice: Voice | null = null

function voiceFor(ctx: AudioContext, master: GainNode) {
  if (voice?.ctx === ctx) return voice
  const input = ctx.createGain()
  const analyser = ctx.createAnalyser()
  analyser.fftSize = 1024
  analyser.smoothingTimeConstant = 0.3
  input.connect(analyser).connect(master)
  voice = {
    ctx,
    input,
    analyser,
    wave: new Float32Array(analyser.fftSize),
    spectrum: new Float32Array(analyser.frequencyBinCount),
  }
  return voice
}

const buffers = new Map<CaretakerLineId, Promise<AudioBuffer | null>>()

function load(id: CaretakerLineId) {
  const graph = audioGraph()
  if (!graph) return Promise.resolve(null)
  let buffer = buffers.get(id)
  if (!buffer) {
    buffer = fetch(`${import.meta.env.BASE_URL}voice/caretaker/${id}.m4a`)
      .then((res) => (res.ok ? res.arrayBuffer() : Promise.reject(new Error(`${res.url}: ${res.status}`))))
      .then((data) => graph.ctx.decodeAudioData(data))
      .catch((error: unknown) => {
        console.warn(`[caretaker] ${id}: ${String(error)}. Reading the text instead (npm run voice records it).`)
        return null
      })
    buffers.set(id, buffer)
  }
  return buffer
}

export function preloadCaretaker() {
  for (const id of Object.keys(CARETAKER_LINES) as CaretakerLineId[]) void load(id)
}

let playing: AudioBufferSourceNode | null = null
// Set while a line is being read from its text (no recording).
let reading: { text: string; start: number } | null = null
const CHARS_PER_SECOND = 14

// Plays one line and resolves when it ends, or when hush() cuts it off.
export async function say(id: CaretakerLineId) {
  const text = CARETAKER_LINES[id]
  const buffer = await load(id)
  const graph = audioGraph()
  if (!buffer || !graph) {
    const read = { text, start: performance.now() }
    reading = read
    await new Promise((resolve) => setTimeout(resolve, (text.length / CHARS_PER_SECOND) * 1000))
    if (reading === read) reading = null
    return
  }
  const source = graph.ctx.createBufferSource()
  source.buffer = buffer
  source.connect(voiceFor(graph.ctx, graph.master).input)
  playing = source
  await new Promise((resolve) => {
    source.onended = resolve
    source.start()
  })
  if (playing === source) playing = null
}

export function hush() {
  playing?.stop()
  playing = null
  reading = null
}

// This frame's mouth signal: loudness 0..1, and brightness 0..1 (how much of the
// sound sits high: "ee" and "s" are bright, "oo" and "o" are dark).
export function mouthSignal() {
  if (reading) return readSignal(reading)
  if (!playing || !voice) return { level: 0, bright: 0.5 }
  const { analyser, wave, spectrum, ctx } = voice
  analyser.getFloatTimeDomainData(wave)
  let sum = 0
  for (const v of wave) sum += v * v
  const level = Math.min(1, Math.sqrt(sum / wave.length) * 6)
  analyser.getFloatFrequencyData(spectrum)
  const hz = ctx.sampleRate / analyser.fftSize
  let weight = 0
  let centroid = 0
  for (let i = Math.floor(150 / hz); i < Math.min(spectrum.length, 5000 / hz); i++) {
    const magnitude = 10 ** (spectrum[i] / 20)
    weight += magnitude
    centroid += magnitude * i * hz
  }
  const bright = weight > 0 ? Math.min(1, Math.max(0, (centroid / weight - 500) / 2000)) : 0.5
  return { level, bright }
}

const DARK = 'ouwOUW'
const BRIGHT = 'eiyEIY'
function readSignal({ text, start }: { text: string; start: number }) {
  const ch = text[Math.floor(((performance.now() - start) / 1000) * CHARS_PER_SECOND)] ?? ' '
  if ('mbpMBP .,!?;:"'.includes(ch)) return { level: 0, bright: 0.5 }
  if (DARK.includes(ch)) return { level: 0.7, bright: 0.15 }
  if (BRIGHT.includes(ch)) return { level: 0.6, bright: 0.8 }
  if ('aA'.includes(ch)) return { level: 0.8, bright: 0.5 }
  if ('sSzZcCtTfF'.includes(ch)) return { level: 0.25, bright: 0.95 }
  return { level: 0.35, bright: 0.55 }
}
