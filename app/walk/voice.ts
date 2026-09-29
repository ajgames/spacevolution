import { type Point, audioGraph, filter, placement } from '../demo/audio.ts'
import { LINES, type LineId } from './lines.ts'
import { SPEAKERS } from './world.ts'

// The steward talks over the PA: one voice, EQ'd like a small ceiling speaker,
// playing from every speaker in the ship at once. Each speaker is placed where
// it hangs, so the voice is loudest under one and fades between them, and the
// walls between the player and each speaker muffle it (setWalls, each frame).

type Pa = {
  ctx: AudioContext
  input: GainNode
  analyser: AnalyserNode
  wave: Float32Array<ArrayBuffer>
  speakers: ReturnType<typeof placement>[]
}
let pa: Pa | null = null

function paFor(ctx: AudioContext) {
  if (pa?.ctx === ctx) return pa
  const input = ctx.createGain()
  const lowCut = filter(ctx, 'highpass', 240, 0.7)
  const presence = new BiquadFilterNode(ctx, { type: 'peaking', frequency: 2600, Q: 1.1, gain: 5 })
  const highCut = filter(ctx, 'lowpass', 6000, 0.7)
  const analyser = ctx.createAnalyser()
  analyser.fftSize = 1024
  input.connect(lowCut).connect(presence).connect(highCut).connect(analyser)
  const speakers = SPEAKERS.map((s) => {
    const placed = placement(ctx, s.at, 1.4)
    highCut.connect(placed.input)
    return placed
  })
  pa = { ctx, input, analyser, wave: new Float32Array(analyser.fftSize), speakers }
  return pa
}

// Muffles each speaker by the walls between it and the listener.
export function setWalls(transmission: (point: Point) => number) {
  pa?.speakers.forEach((speaker, i) => speaker.setTransmission(transmission(SPEAKERS[i].at), 0.08))
}

// The voice's waveform this frame (for the steward's screen), and its loudness 0..1.
export function voiceWave() {
  if (!pa) return null
  pa.analyser.getFloatTimeDomainData(pa.wave)
  return pa.wave
}

export function voiceLevel() {
  const wave = voiceWave()
  if (!wave) return 0
  let sum = 0
  for (const v of wave) sum += v * v
  return Math.min(1, Math.sqrt(sum / wave.length) * 5)
}

// --- lines -------------------------------------------------------------------

const buffers = new Map<LineId, Promise<AudioBuffer | null>>()

function load(id: LineId) {
  const graph = audioGraph()
  if (!graph) return Promise.resolve(null)
  let buffer = buffers.get(id)
  if (!buffer) {
    buffer = fetch(`${import.meta.env.BASE_URL}voice/${id}.m4a`)
      .then((res) => (res.ok ? res.arrayBuffer() : Promise.reject(new Error(`${res.url}: ${res.status}`))))
      .then((data) => graph.ctx.decodeAudioData(data))
      .catch((error: unknown) => {
        console.warn(`[voice] ${id}: ${String(error)}. Subtitles only (npm run voice records the lines).`)
        return null
      })
    buffers.set(id, buffer)
  }
  return buffer
}

// Fetch and decode every line ahead of time; call once audio is unlocked.
export function preloadVoice() {
  for (const id of Object.keys(LINES) as LineId[]) void load(id)
}

let playing: AudioBufferSourceNode | null = null

// Plays one line over the PA and resolves when it ends (or is hushed). Without
// the recording, it waits about as long as the line would take to say.
export async function speak(id: LineId) {
  const buffer = await load(id)
  const graph = audioGraph()
  if (!buffer || !graph) {
    await new Promise((resolve) => setTimeout(resolve, LINES[id].split(' ').length * 380))
    return
  }
  const source = graph.ctx.createBufferSource()
  source.buffer = buffer
  source.connect(paFor(graph.ctx).input)
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
}
