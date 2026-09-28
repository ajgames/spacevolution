import { Link } from 'react-router'

const SCENES = [
  {
    to: '/fly',
    code: 'SCN-00',
    title: 'Fly around ship',
    body: 'Orbit the starter ship and switch between rooms and the three baked lighting states.',
  },
  {
    to: '/demo',
    code: 'SCN-01',
    title: 'Myst-style demo',
    body: 'Wake in the cryo bay during a blackout. Trace the fault, reset the breakers, bring the ship back up.',
  },
]

export default function Landing() {
  return (
    <main className="relative flex min-h-dvh items-center justify-center overflow-hidden bg-black px-4 py-12 font-mono text-[#d8d2c4]">
      {/* CRT scanlines over the whole page */}
      <div className="pointer-events-none absolute inset-0 bg-[repeating-linear-gradient(to_bottom,rgba(255,255,255,0.025)_0_1px,transparent_1px_3px)]" />
      <div className="relative w-full max-w-3xl">
        {/* Same art as public/logo.png at a fraction of the weight; `npm run icons` redraws both. */}
        <img src="/logo.svg" alt="" width={144} height={144} className="mb-6 -ml-2 size-28 sm:size-36" />
        <p className="text-xs tracking-[0.3em] text-[#8a877e] uppercase">Sleeper ship // caretaker terminal</p>
        <h1 className="mt-3 text-4xl font-bold tracking-[0.2em] text-[#f0a040] uppercase sm:text-5xl">
          Spacevelution
        </h1>
        <p className="mt-4 max-w-xl text-sm leading-relaxed text-[#8a877e]">Select a scene.</p>

        <div className="mt-10 grid gap-4 sm:grid-cols-2">
          {SCENES.map((scene) => (
            <Link
              key={scene.to}
              to={scene.to}
              className="group border border-[#2a3130] bg-[#0c1010] p-5 transition-colors hover:border-[#f0a040] focus-visible:border-[#f0a040] focus-visible:outline-none"
            >
              <div className="flex items-center justify-between text-xs text-[#8a877e]">
                <span>{scene.code}</span>
                <span className="size-2.5 rounded-full bg-[#3a2a14] shadow-none transition-shadow group-hover:bg-[#f0a040] group-hover:shadow-[0_0_10px_#f0a040]" />
              </div>
              <h2 className="mt-4 text-lg tracking-wider text-[#d8d2c4] uppercase group-hover:text-[#f0a040]">
                {scene.title}
              </h2>
              <p className="mt-2 text-sm leading-relaxed text-[#8a877e]">{scene.body}</p>
              <p className="mt-5 text-xs tracking-widest text-[#f0a040] uppercase opacity-60 group-hover:opacity-100">
                Enter ▸
              </p>
            </Link>
          ))}
        </div>
      </div>
    </main>
  )
}
