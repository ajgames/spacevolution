// What the ship's steward says in the walk mode, one recording per line:
// public/voice/<id>.m4a, rendered from this file by `npm run voice` (macOS
// speech synthesis). Edit a line here, then re-run the script.

export const STEWARD_VOICE = { voice: 'Samantha', rate: 168 }

export const LINES = {
  online: "Main bus restored. Ship's steward, online.",
  hello: "Good morning, caretaker. I'm sorry about the dark.",
  memory:
    'The fault took part of my memory with it. Pod six reports a sleeper in distress, ' +
    'but I no longer trust my own telemetry. I need eyes on it.',
  droid:
    'The maintenance droid is docked at the corridor junction. Its camera feeds the centre screen. ' +
    'Take the joystick, to the right of the console.',
  stick: 'Link is up. Push forward to roll out of the dock.',
  turn: 'Good. Steer left or right to turn. Take it west, toward the cryo bay.',
  cryo: 'The cryo door is open. Pod six is the first one on your left.',
  scan: 'Hold it there. Scanning.',
  empty: 'Telemetry says pod six holds a sleeper with failing vitals. The droid reads no heat, no heartbeat, no mass. Pod six is empty.',
  who: "There were six sleepers aboard when we left orbit. And the droid's logs have a gap, right where that night should be.",
} as const

export type LineId = keyof typeof LINES
