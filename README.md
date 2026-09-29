# Spacevelution

First-person space maintenance game built with React Three Fiber (`three`, `@react-three/fiber`, `@react-three/drei`). The front end is a Vite + React app using React Router in declarative mode (`<BrowserRouter>` / `<Routes>`), with source in `app/`. The ship interior is built in Blender under `blender/` (see `blender/PROMPT.md`), and its glTF exports land in `blender/export/`.

- `npm run dev`: start the Vite dev server
- `npm run build`: typecheck and build to `dist/`
- `npm run typecheck`: typecheck only
- `npm run sync:ship`: copy the ship assets into `public/ship/` (and the character GLBs into `public/characters/`) by hand
- `npm run icons`: redraw the logo and favicons into `public/` (`scripts/icons.ts`, needs Chrome)
- `npm run voice`: record the steward's lines into `public/voice/`, and the caretaker's into `public/voice/caretaker/` (`scripts/voice.ts`, needs macOS)

## Scenes

- `/` picks a scene.
- `/fly` orbits the whole ship from preset views in any lighting state (`app/scene/FlyScene.tsx`).
- `/demo` is the Myst-style opening (`app/demo/`): wake in the cryo bay during a blackout, follow the red pulse to engineering, match the core lamp matrix on the command console's breakers, and restore power.
- `/walk` is the same opening on foot (`app/walk/`), carried past the tape: once the power is back, the ship's steward comes online in the command room and talks you through driving the droid to pod six.
- `/construct` puts the caretaker alone in an endless white room (`app/construct/`). Keys 1–5 (or the buttons) switch between walk, jump, talk, strafe and crouch; pressing the active one again, or 0, stands him still. Talking plays his recorded lines with subtitles, and the jaw and lips follow the voice. In dev, `window.__construct.step(seconds)` renders frames on demand for a background or automated tab.

The three ship scenes load the ship through `useShip()` (`app/scene/useShip.ts`), which returns a private copy of the rooms, and light it with `<ShipRooms>`.

### How the demo is put together

- `store.ts`: one zustand store around a transition table (`blackout → emergency → breakersSet → powered → tapePlaying → ended`). Lighting, screen content and which hotspots are clickable are derived from the phase.
- `nodes.ts`: the camera nodes. Each spot has fixed facings; the player turns at the screen edges and clicks hotspots (Blender objects by name, or floor areas) to move.
- `Props.tsx`, `Screens.tsx`, `Hotspots.tsx`: named objects animated from the store, the CRT screens (canvas textures under a scanline shader; the droid feed is a render target) and the click volumes.
- `audio.ts`: every sound is synthesized with Web Audio. The caretaker's voice is the browser's speech synthesis standing in for a recording.
- The engineering CRT, lamp matrix and tape reels are baked into the static `CORE_rack_*` meshes, so the demo draws overlays at positions taken from `blender/scripts/build_props.py`. Separate named objects in Blender would let the game drive them directly.

Jump straight to a beat with `/demo?spot=console&phase=emergency&pattern=10110010` (`spot` is a key of `SPOTS`, `phase` one of `PHASES`, `pattern` the eight lamp columns). In dev, `window.__demo` exposes the store and its actions.

### How the walk is put together

The walk mode plays the demo's puzzle state (`useDemo`, and the shared `puzzle` actions in `app/demo/store.ts`) and reuses its props, core monitor and lamp matrix. On top of that:

- `store.ts`: what's only true on foot (in the pod, walking, or seated at the joystick; subtitles; the objective), plus the per-frame poses of the player, the droid and the stick.
- `world.ts`: the plan the player and droid collide with. Walls come from the room outlines in `blender/scripts/lib_ship.py`, props are boxes measured from the export at load, and closed doors block their doorways. It also places the ceiling speakers, settling each one onto the ceiling above it at load, and finds the door panel buttons.
- `DoorButtons.tsx`: doors open from the control panel beside them, one on each side of every door. The panels are baked into the wall modules (`door_module` and `corridor_end_cap` in `build_structure.py`), so the walk mode finds each button by its lit amber face at load and puts an aim box over it that flashes when pressed. Aiming at a closed door only points you to its panel.
- `Player.tsx`: pointer-lock mouse look, WASD, sliding collisions, a light head bob with footsteps, and a shake from loud things nearby. At the joystick it eases into the seat and the input moves the stick instead.
- `space.ts` and `voice.ts`: positional sound. In the walk mode every sound tied to a ship object plays from that object through an HRTF panner (`soundAt` in `app/demo/audio.ts`; the Myst demo plays the same calls flat), and closed doors muffle it. The steward talks over the PA, from every ceiling speaker at once, so it's loudest under one.
- `SoundCues.tsx`: the on-screen cues. Each audible sound draws an arc around the crosshair in the direction it comes from, labelled and as bright as it is loud, and a marker where it is when it's in view.
- `story.ts` and `lines.ts`: the steward's beats after full power. Each says a line, then holds an objective until it's done. The recordings are `public/voice/<id>.m4a`, made from `lines.ts` by `npm run voice`; re-run it after editing a line.
- `Droid.tsx` and `Console.tsx`: the droid (tank steering, its own collisions, a motor you hear from it and through the console while linked), the desk's joystick, and the three command screens: a to-scale track of the droid, its camera under a driving overlay, and the steward. The joystick is modelled into `WORKSTATION_desk`, so the walk mode cuts the baked lever out of a copy of the desk's geometry and moves its own in its place. A separate named lever in Blender would remove that step.

Start later with `/walk?phase=powered&at=console&beat=droid` (`at` is a key of `PLACES` in `store.ts`, `beat` an id in `story.ts`'s `BEATS`, plus `phase` and `pattern` as above). `/walk?debug=walls` draws the collision plan on the floor. In dev, `window.__walk` exposes the stores, the player (`body`) and the droid.

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

## Characters

`blender/characters.blend` holds the characters, one `CHAR_<name>` collection each, in a scene called `Characters`. It's separate from the ship file. The first is `CHAR_caretaker`: a 1.80 m, medium-to-thin man with a smooth, featureless crotch and no clothes yet. He's built on Blender Studio's CC0 Human Base Meshes, which `blender/assets/` holds (gitignored, downloaded on first build).

- `scripts/build_character.py` rebuilds him from scratch: `blender -b --factory-startup --python scripts/build_character.py` (run from `blender/`).
- `scripts/anim_character.py` bakes his clips (idle, walk, strafe left/right, jump, crouch, talk). The rebuild runs it too, or run it on its own against `characters.blend` to redo only the clips.
- `scripts/verify_character.py` renders the check sheets into `blender/screenshots/characters/`.
- `scripts/export_character.py` writes `blender/export/characters/<name>.glb` and validates it. The ship sync mirrors that folder into `public/characters/` (dev server, build and `npm run sync:ship`), and `/construct` loads it from there.

The rig has 66 deforming bones: spine, a full hand (metacarpals, three joints per finger, a two-axis thumb base, wrist flex/deviation/pronation with a forearm twist bone), IK for the arms and legs, and a jaw. Its shape keys cover lip shapes and blinks. The clips play in place, and the game moves him at each clip's authored speed so his feet stay planted. `blender/CHARACTER_SUMMARY.md` is the generated reference for bone axes and limits, shape keys, viseme mixes, clip speeds, and applying poses in three.js.
