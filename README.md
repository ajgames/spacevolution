# Spacevelution

First-person space maintenance game built with React Three Fiber (`three`, `@react-three/fiber`, `@react-three/drei`). The front end is a Vite + React app using React Router in declarative mode (`<BrowserRouter>` / `<Routes>`), with source in `app/`. The ship interior is built in Blender under `blender/` (see `blender/PROMPT.md`), and its glTF exports land in `blender/export/`.

- `npm run dev`: start the Vite dev server
- `npm run build`: typecheck and build to `dist/`
- `npm run typecheck`: typecheck only
- `npm run sync:ship`: copy the ship assets into `public/ship/` by hand

## Scenes

- `/` picks a scene.
- `/fly` orbits the whole ship from preset views in any lighting state (`app/scene/FlyScene.tsx`).
- `/demo` is the Myst-style opening (`app/demo/`): wake in the cryo bay during a blackout, follow the red pulse to engineering, match the core lamp matrix on the command console's breakers, and restore power.

Both load the ship through `useShip()` (`app/scene/useShip.ts`), which returns a private copy of the rooms, and light it with `<ShipRooms>`.

### How the demo is put together

- `store.ts`: one zustand store around a transition table (`blackout → emergency → breakersSet → powered → tapePlaying → ended`). Lighting, screen content and which hotspots are clickable are derived from the phase.
- `nodes.ts`: the camera nodes. Each spot has fixed facings; the player turns at the screen edges and clicks hotspots (Blender objects by name, or floor areas) to move.
- `Props.tsx`, `Screens.tsx`, `Hotspots.tsx`: named objects animated from the store, the CRT screens (canvas textures under a scanline shader; the droid feed is a render target) and the click volumes.
- `audio.ts`: every sound is synthesized with Web Audio. The caretaker's voice is the browser's speech synthesis standing in for a recording.
- The engineering CRT, lamp matrix and tape reels are baked into the static `CORE_rack_*` meshes, so the demo draws overlays at positions taken from `blender/scripts/build_props.py`. Separate named objects in Blender would let the game drive them directly.

Jump straight to a beat with `/demo?spot=console&phase=emergency&pattern=10110010` (`spot` is a key of `SPOTS`, `phase` one of `PHASES`, `pattern` the eight lamp columns). In dev, `window.__demo` exposes the store and its actions.

## Ship assets

`scripts/sync-ship.ts` mirrors what the game needs from `blender/export/` into `public/ship/`, which is generated and gitignored. `blender/export/lightmaps/manifest.json` decides what that is: every room GLB and baked lightmap it lists, plus the manifest itself. `preview.html` and any `lightmaps/exr/` masters stay behind.

```
public/ship/
├── manifest.json            # paths inside resolve relative to this file
├── ROOM_<room>.glb
└── lightmaps/LM_ROOM_<room>_<state>.png
```

The game loads `/ship/manifest.json` and resolves each `glb` and lightmap `file` against it. The manifest also carries the three.js texture settings and each lightmap's `lightMapIntensity`; `app/scene/` wires it up, ported from `blender/export/preview.html`, which stays as the reference.

The sync runs on its own:

- **Dev server:** once on start, then again about a second after Blender stops writing to `blender/export/`, followed by a page reload.
- **`vite build`:** before `public/` is copied into `dist/`. A missing or half-written export fails the build.

Unchanged files are skipped by size and mtime, so the copy only costs something after a real export or bake. A warning means a room's GLB is newer than its lightmaps, which can happen if the bake hasn't been re-run since geometry or UVs changed.
