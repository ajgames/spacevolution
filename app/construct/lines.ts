// What the caretaker says in the construct demo, one recording per line:
// public/voice/caretaker/<id>.m4a, rendered by `npm run voice` (macOS speech
// synthesis). Edit a line here, then re-run the script.

export const CARETAKER_VOICE = { voice: 'Daniel', rate: 172 }

export const CARETAKER_LINES = {
  hello: "Hello. I'm the caretaker. At least, I will be, once somebody writes my story.",
  room: "For now I live in this white room. No floor, no walls, no furniture. It's very peaceful.",
  tricks: 'I can walk, jump, crouch, and step sideways. Talking is my newest trick.',
  mouth: 'My jaw does the heavy lifting. My lips go wide for "see", round for "who", and press shut for "maybe".',
  bye: "Pick another button whenever you like. I'll be right here. I really have nowhere else to go.",
} as const

export type CaretakerLineId = keyof typeof CARETAKER_LINES
