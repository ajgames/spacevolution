// The radio half of the broadcast plugin (scripts/broadcast.ts). It runs in a
// worker thread so building the signal never holds up the dev server: it
// starts hackrf_transfer and keeps its stdin fed with fields from
// scripts/ntsc.ts, and the HackRF's sample clock paces the whole thing.
//
// hackrf_transfer stops transmitting when its stdin closes, so if this worker
// or the dev server dies, the HackRF goes quiet with it.
import { spawn } from 'node:child_process'
import { parentPort, workerData } from 'node:worker_threads'
import { FIELD, SAMPLE_RATE, createModulator } from './ntsc.ts'

export type RadioSettings = { frequency: number; gain: number }
export type ToRadio =
  | { type: 'picture'; rgba: Uint8Array }
  | { type: 'audio'; samples: Float32Array; rate: number }
  | { type: 'stop' }
export type FromRadio = { type: 'on-air' } | { type: 'failed'; reason: string }

const port = parentPort!
const { frequency, gain } = workerData as RadioSettings
const modulator = createModulator()
const send = (message: FromRadio) => port.postMessage(message)

const tx = spawn(
  'hackrf_transfer',
  [
    ['-t', '-'], // transmit from stdin
    ['-f', String(frequency)],
    ['-s', String(SAMPLE_RATE)],
    ['-b', '10000000'],
    ['-x', String(gain)],
    ['-a', '0'], // RF amp off
    ['-p', '0'], // antenna port power off
  ].flat(),
  { stdio: ['pipe', 'ignore', 'pipe'] },
)

let stopping = false
let onAir = false
let tail: string[] = [] // hackrf_transfer's last words, for when it fails

tx.stderr.setEncoding('utf8')
tx.stderr.on('data', (text: string) => {
  tail = [...tail, ...text.split('\n').filter(Boolean)].slice(-4)
  if (!onAir && text.includes('Stop with Ctrl-C')) {
    onAir = true
    send({ type: 'on-air' })
  }
})
tx.on('error', (err) => {
  send({ type: 'failed', reason: `can't run hackrf_transfer: ${err.message}` })
  process.exit(0)
})
tx.on('exit', () => {
  if (!stopping) send({ type: 'failed', reason: `hackrf_transfer quit: ${tail.join(' / ') || 'no output'}` })
  process.exit(0)
})
tx.stdin.on('error', () => {}) // EPIPE once it has quit; 'exit' reports why

// Three fields in flight at most (about 50 ms), each built when the last one
// using its buffer has gone down the pipe.
const spare = [0, 1, 2].map(() => new Uint16Array(FIELD))
function pump() {
  while (!stopping && spare.length) {
    const field = spare.pop()!
    modulator.fill(field)
    tx.stdin.write(new Uint8Array(field.buffer), () => {
      spare.push(field)
      pump()
    })
  }
}
pump()

port.on('message', (message: ToRadio) => {
  if (message.type === 'picture') modulator.setPicture(message.rgba)
  else if (message.type === 'audio') modulator.pushAudio(message.samples, message.rate)
  else if (!stopping) {
    stopping = true
    tx.stdin.end()
    // It should exit on the end of its input; make sure.
    setTimeout(() => tx.kill('SIGINT'), 1000).unref()
    setTimeout(() => tx.kill('SIGKILL'), 3000).unref()
  }
})
