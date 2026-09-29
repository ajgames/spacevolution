// Records the steward's lines (app/walk/lines.ts) with macOS speech synthesis
// and writes one AAC file per line into public/voice/<id>.m4a. The walk mode
// plays them through Web Audio, so the voice can come out of the ceiling
// speakers; the browser's own speech synthesis can't be routed that way.
//
// Needs macOS (`say`, `afconvert`). Set VOICE or RATE to override the voice
// and words per minute. Run with `npm run voice`.
//
// Also records the construct demo's caretaker (app/construct/lines.ts) into
// public/voice/caretaker/<id>.m4a, in his own voice (VOICE and RATE don't apply).
import { execFileSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { CARETAKER_LINES, CARETAKER_VOICE } from '../app/construct/lines.ts'
import { LINES, STEWARD_VOICE } from '../app/walk/lines.ts'

const OUT = join(import.meta.dirname, '../public/voice')
const voice = process.env.VOICE ?? STEWARD_VOICE.voice
const rate = String(process.env.RATE ?? STEWARD_VOICE.rate)

mkdirSync(OUT, { recursive: true })
const scratch = mkdtempSync(join(tmpdir(), 'voice-'))
try {
  for (const [id, text] of Object.entries(LINES)) {
    const aiff = join(scratch, `${id}.aiff`)
    const m4a = join(OUT, `${id}.m4a`)
    execFileSync('say', ['-v', voice, '-r', rate, '-o', aiff, text])
    // 22 kHz mono speech at 48 kbps: about 6 KB a second.
    execFileSync('afconvert', ['-f', 'm4af', '-d', 'aac', '-b', '48000', aiff, m4a])
    console.log(`${id}.m4a  ${text}`)
  }
  // The construct demo's caretaker (app/construct/lines.ts) has his own voice and folder.
  const caretakerOut = join(OUT, 'caretaker')
  mkdirSync(caretakerOut, { recursive: true })
  for (const [id, text] of Object.entries(CARETAKER_LINES)) {
    const aiff = join(scratch, `caretaker-${id}.aiff`)
    const m4a = join(caretakerOut, `${id}.m4a`)
    execFileSync('say', ['-v', CARETAKER_VOICE.voice, '-r', String(CARETAKER_VOICE.rate), '-o', aiff, text])
    execFileSync('afconvert', ['-f', 'm4af', '-d', 'aac', '-b', '48000', aiff, m4a])
    console.log(`caretaker/${id}.m4a  ${text}`)
  }
} finally {
  rmSync(scratch, { recursive: true, force: true })
}
