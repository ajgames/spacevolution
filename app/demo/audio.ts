// Every sound in the demo is synthesized with Web Audio, so there are no audio
// assets yet. The AudioContext can only start after a user gesture; call
// unlockAudio() from a click before anything else plays.

let ctx: AudioContext | null = null
let master: GainNode | null = null
let noise: AudioBuffer | null = null

export function unlockAudio() {
  if (!ctx) {
    ctx = new AudioContext()
    master = ctx.createGain()
    master.gain.value = 0.8
    master.connect(ctx.destination)
    noise = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate)
    const data = noise.getChannelData(0)
    for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1
  }
  void ctx.resume()
}

export function setMuted(muted: boolean) {
  if (ctx && master) master.gain.setTargetAtTime(muted ? 0 : 0.8, ctx.currentTime, 0.05)
}

type Env = { at?: number; attack?: number; hold?: number; release: number; peak: number }

// A gain node with an attack/hold/release envelope, feeding the master bus.
function envelope(c: AudioContext, { at = 0, attack = 0.005, hold = 0, release, peak }: Env) {
  const g = c.createGain()
  const t = c.currentTime + at
  g.gain.setValueAtTime(0, t)
  g.gain.linearRampToValueAtTime(peak, t + attack)
  g.gain.setValueAtTime(peak, t + attack + hold)
  g.gain.exponentialRampToValueAtTime(0.0001, t + attack + hold + release)
  g.connect(master!)
  return { gain: g, start: t, end: t + attack + hold + release + 0.05 }
}

function noiseSource(c: AudioContext, loop = false) {
  const src = c.createBufferSource()
  src.buffer = noise
  src.loop = loop
  return src
}

function filter(c: AudioContext, type: BiquadFilterType, frequency: number, q = 0.7) {
  const f = c.createBiquadFilter()
  f.type = type
  f.frequency.value = frequency
  f.Q.value = q
  return f
}

function burst(type: BiquadFilterType, freq: number, env: Env, q = 0.7) {
  if (!ctx) return
  const e = envelope(ctx, env)
  const src = noiseSource(ctx)
  const f = filter(ctx, type, freq, q)
  src.connect(f).connect(e.gain)
  src.start(e.start, Math.random())
  src.stop(e.end)
}

function tone(type: OscillatorType, from: number, to: number, env: Env) {
  if (!ctx) return
  const e = envelope(ctx, env)
  const osc = ctx.createOscillator()
  osc.type = type
  osc.frequency.setValueAtTime(from, e.start)
  osc.frequency.exponentialRampToValueAtTime(to, e.end)
  osc.connect(e.gain)
  osc.start(e.start)
  osc.stop(e.end)
}

// A continuous layer that fades in and can be faded out later.
function bed(build: (c: AudioContext, out: GainNode) => AudioScheduledSourceNode[], level: number, fade = 1.5) {
  if (!ctx) return () => {}
  const c = ctx
  const out = c.createGain()
  out.gain.setValueAtTime(0, c.currentTime)
  out.gain.linearRampToValueAtTime(level, c.currentTime + fade)
  out.connect(master!)
  const sources = build(c, out)
  for (const s of sources) s.start()
  let stopped = false
  return (release = 1) => {
    if (stopped) return
    stopped = true
    out.gain.cancelScheduledValues(c.currentTime)
    out.gain.setTargetAtTime(0, c.currentTime, release / 4)
    for (const s of sources) s.stop(c.currentTime + release + 0.1)
  }
}

export const sfx = {
  // Low ship rumble under everything.
  roomTone: () =>
    bed((c, out) => {
      const src = noiseSource(c, true)
      src.connect(filter(c, 'lowpass', 90, 0.5)).connect(out)
      const drone = c.createOscillator()
      drone.frequency.value = 41
      const dg = c.createGain()
      dg.gain.value = 0.25
      drone.connect(dg).connect(out)
      return [src, drone]
    }, 0.35),

  // The pulse's soft warning tick, once a second in the blackout.
  pulseTick: () => tone('sine', 660, 640, { release: 0.25, peak: 0.035 }),

  // Seal hiss and latch as the pod glass swings open.
  podOpen: () => {
    burst('lowpass', 300, { release: 0.3, peak: 0.5 })
    tone('sine', 110, 50, { release: 0.25, peak: 0.4 })
    burst('bandpass', 2400, { at: 0.08, attack: 0.05, hold: 0.4, release: 1.4, peak: 0.25 }, 0.6)
  },

  // Door servo and the thunk at the end of its travel.
  door: () => {
    tone('sawtooth', 95, 70, { attack: 0.08, hold: 0.45, release: 0.2, peak: 0.05 })
    burst('bandpass', 700, { attack: 0.08, hold: 0.45, release: 0.2, peak: 0.08 }, 1.5)
    tone('sine', 80, 45, { at: 0.72, release: 0.2, peak: 0.35 })
  },

  // A soft footstep whoosh when moving between spots.
  step: () => burst('lowpass', 500, { attack: 0.15, hold: 0.2, release: 0.5, peak: 0.07 }),

  // A heavy button clunk.
  clunk: () => {
    tone('sine', 140, 45, { release: 0.18, peak: 0.5 })
    burst('bandpass', 1800, { release: 0.05, peak: 0.25 }, 2)
  },

  // A breaker toggle: a sharp click with a little spring.
  toggle: (on: boolean) => {
    burst('highpass', 3000, { release: 0.03, peak: 0.3 })
    tone('square', on ? 1400 : 1000, on ? 1300 : 900, { release: 0.04, peak: 0.03 })
    tone('sine', 220, 120, { release: 0.08, peak: 0.12 })
  },

  // Relays slamming over to backup power.
  relay: () => {
    for (let i = 0; i < 3; i++) {
      tone('sine', 120, 40, { at: i * 0.11, release: 0.2, peak: 0.45 })
      burst('bandpass', 1200, { at: i * 0.11, release: 0.06, peak: 0.3 }, 3)
    }
  },

  // The breaker fault: arcing buzz that cuts in and out, then a hard click.
  stutter: () => {
    if (!ctx) return
    let at = 0
    for (let i = 0; i < 9; i++) {
      const len = 0.03 + Math.random() * 0.08
      tone('sawtooth', 118, 122, { at, attack: 0.002, hold: len, release: 0.02, peak: 0.1 })
      burst('highpass', 4000, { at, release: 0.02, peak: 0.15 })
      at += len + 0.03 + Math.random() * 0.1
    }
    tone('sine', 90, 40, { at: at + 0.05, release: 0.25, peak: 0.4 })
  },

  // A beacon whoop, every two seconds in emergency lighting.
  alarm: () => tone('triangle', 380, 560, { attack: 0.3, hold: 0.2, release: 0.5, peak: 0.03 }),

  // The ship powering up: a hum that rises over three seconds, then settles
  // into a steady bed. Returns a function that stops the bed.
  powerUp: () => {
    tone('sawtooth', 25, 60, { attack: 2.8, release: 0.6, peak: 0.12 })
    burst('lowpass', 2000, { at: 2.9, release: 0.8, peak: 0.25 })
    return bed(
      (c, out) => {
        const sources: AudioScheduledSourceNode[] = []
        for (const [f, level] of [
          [60, 0.5],
          [120, 0.2],
          [180, 0.08],
        ]) {
          const osc = c.createOscillator()
          osc.type = f === 60 ? 'sine' : 'triangle'
          osc.frequency.value = f
          const g = c.createGain()
          g.gain.value = level
          osc.connect(g).connect(out)
          sources.push(osc)
        }
        const fans = noiseSource(c, true)
        fans.connect(filter(c, 'bandpass', 400, 0.4)).connect(out)
        sources.push(fans)
        return sources
      },
      0.1,
      3,
    )
  },

  // CRT degauss thump and whine as a screen turns on.
  crtOn: () => {
    tone('sine', 60, 35, { release: 0.3, peak: 0.2 })
    burst('bandpass', 5000, { release: 0.25, peak: 0.08 }, 4)
    tone('sine', 15000, 15000, { attack: 0.05, hold: 0.6, release: 0.3, peak: 0.004 })
  },

  // A teletype tick per character on the engineering CRT.
  type: () => burst('bandpass', 3500, { release: 0.015, peak: 0.08 }, 3),

  // Reel-to-reel playback: the motor spinning up, then hiss with a little wow.
  // Returns a function that cuts the tape with a clunk.
  tape: () => {
    tone('sawtooth', 30, 110, { attack: 0.6, release: 0.3, peak: 0.04 })
    const stop = bed((c, out) => {
      const hiss = noiseSource(c, true)
      const hp = filter(c, 'highpass', 2500)
      const wow = c.createOscillator()
      wow.frequency.value = 0.7
      const wowDepth = c.createGain()
      wowDepth.gain.value = 600
      wow.connect(wowDepth).connect(hp.frequency)
      hiss.connect(hp).connect(out)
      const motor = c.createOscillator()
      motor.frequency.value = 100
      const mg = c.createGain()
      mg.gain.value = 0.15
      motor.connect(mg).connect(out)
      return [hiss, wow, motor]
    }, 0.12, 0.4)
    return () => {
      stop(0.08)
      sfx.clunk()
    }
  },
}

// The previous caretaker's voice. There's no recording yet, so the browser's
// speech synthesis stands in for it over the tape hiss. It is cut off as it
// reaches `cutAt`, and `onCut` runs then (or when speech ends early). Voices
// without word-boundary events never report reaching `cutAt`, so callers keep
// their own fallback timer.
export function playVoice(text: string, cutAt: string, onCut: () => void) {
  const synth = window.speechSynthesis
  if (!synth) return
  const cutIndex = text.indexOf(cutAt)
  const say = () => {
    const utterance = new SpeechSynthesisUtterance(text)
    const voices = synth.getVoices().filter((v) => v.lang.startsWith('en'))
    utterance.voice = voices.find((v) => /daniel|fred|alex|male/i.test(v.name)) ?? voices[0] ?? null
    utterance.rate = 0.88
    utterance.pitch = 0.7
    utterance.addEventListener('boundary', (e) => {
      if (cutIndex >= 0 && e.charIndex >= cutIndex) onCut()
    })
    utterance.addEventListener('end', onCut)
    synth.cancel()
    synth.speak(utterance)
  }
  // getVoices() is empty until the browser has loaded its voice list.
  if (synth.getVoices().length) say()
  else synth.addEventListener('voiceschanged', say, { once: true })
}
