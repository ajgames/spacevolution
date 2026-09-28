"""Step 7 wrap-up: store the text blocks in the .blend and write the object index.

Text blocks: export_ship.py, bake_lightmaps.py (copied from scripts/), ASSET_CREDITS,
README_ship. Also writes //SCENE_SUMMARY.md with every named interactive object.
"""
import datetime

import bpy

import lib_ship as L

SCRIPTS = {"export_ship.py": "//scripts/export_ship.py", "bake_lightmaps.py": "//scripts/bake_lightmaps.py"}

ASSET_CREDITS = """ASSET_CREDITS - Space Veluton starter ship interior
=====================================================
External assets used: NONE.

No Poly Haven or other CC0 asset integration was available through the Blender MCP
when this scene was built, so nothing was downloaded or imported.

Textures - original, generated procedurally for this project by
scripts/gen_textures.py (numpy, fixed random seeds; re-run to regenerate):
  textures/trim_basecolor.png, trim_orm.png, trim_normal.png     2048 px trim sheet (12 bands)
  textures/floor_basecolor.png, floor_orm.png, floor_normal.png  1024 px diamond plate, 1 m tile
  textures/display_readouts.png                                   512 px emissive readouts
  textures/screen_placeholder.png                                 512 px CRT placeholder (MAT_screen)
  textures/nameplate_placeholder.png                              512x96 px nameplate / sign placeholder
Geometry - original, modeled procedurally by the scripts in scripts/.

No real brand names, logos or copyrighted designs are used. All "text" on labels,
signs and screens is random block glyphs.

License: original project work; no third-party license terms apply.
"""

README = """README_ship - Space Veluton starter ship interior
==================================================
Units: 1 Blender unit = 1 m, Z up (glTF export converts to Y up).
Plan: +Y = ship top / fore (command), -X = left (cryo), +X = right (engineering).

Collections
  ROOM_command, ROOM_cryo, ROOM_engineering, ROOM_corridor   exported, one .glb each
  LIGHTS_normal, LIGHTS_emergency, LIGHTS_blackout           bake-only lights (one state enabled at a time)
  REF_layout (hull reference ring, labels), _CAMERAS          never exported

Pipeline (scripts/ on disk; run.py re-runs any step inside Blender)
  build_greybox -> build_structure -> gen_textures -> build_materials -> build_props
  -> build_detail -> prepare_lightmaps -> build_lighting -> export_ship (text block)
  bake_lightmaps (text block) is the separate bake step; run it headless:
    blender spacevelution_ship.blend --background --python-text bake_lightmaps.py -- --samples 256 --res 1024

Game-ready output (export/)
  ROOM_*.glb                 one per room; TEXCOORD_1 = lightmap UVs
  lightmaps/LM_<ROOM>_<state>.png + manifest.json   states: normal, emergency, blackout
  preview.html               three.js reference viewer: `python3 -m http.server 8765 --directory export`
  Apply per room: material.lightMap = texture (channel 1, flipY false, sRGB colour space),
  material.lightMapIntensity = manifest.rooms[room].lightmaps[state].lightMapIntensity.
  Switch emissives per state by material name (see ROLE tables in preview.html).
  build_structure/build_props place linked duplicates of MOD_* meshes;
  prepare_lightmaps makes them single-user (one lightmap atlas per room needs
  unique UVs) and records the source module in the "module" custom property.

Conventions the game code relies on  (Blender local axis -> three.js local axis after glTF Y-up)
  UV maps       UVMap -> TEXCOORD_0 (trim sheet), lightmap -> TEXCOORD_1 (per-room atlas)
  BTN_*         origin = press point (top of cap). Outward normal: Blender +Z -> three.js +Y.
                A press moves the button along three.js local -Y (a few mm).
  DOOR_*        origin = bottom centre of the closed panel, in the wall. Opens by sliding
                +1.0 m along local +X (same axis in both). extras.slide_distance = 1.0
  CRYO_POD_NN   parent node (extras.static = true: the body never moves and is lightmapped,
                but its node transform is kept so the children stay pod-relative); children _glass (origin on the hinge line; swings about the
                vertical axis: Blender local Z -> three.js local Y), _status (display, UV 0-1),
                _nameplate (plate, UV 0-1, MAT_nameplate)
  SCREEN_*      flat quads, MAT_screen, UV 0-1 (0,0 = bottom-left as seen by the player).
                Face normal: Blender local -Y -> three.js local +Z (like a PlaneGeometry)
  SIGN_*        sign faces, MAT_nameplate, UV 0-1 (swap in real sign textures)
  SPAWN_/SEAT_  empties; facing = Blender local +Y -> three.js local -Z (Object3D forward);
                origin at floor / seat-cushion level, extras.eye_height = camera offset (m)
  INTERACT_*    empties at each interactable; extras.target (object name), extras.radius (m)
  LIGHT_*       empties for code-driven lights; extras.color / intensity / range (+ blink_hz,
                rotate_hz). They are placeholders: create the three.js lights in code.
  Material light_role: strip | alarm | indicator | screen | dynamic (see bake_lightmaps.py)
                MAT_emit_blink (BTN_blink cap + lamp) is "dynamic": drive it from code.
"""


def set_text(name, body):
    t = bpy.data.texts.get(name) or bpy.data.texts.new(name)
    t.clear()
    t.write(body)
    t.use_fake_user = True
    return t


INTERACTIVE = ("SCREEN_", "BTN_", "LIGHT_", "DOOR_", "CRYO_POD_", "SPAWN_", "SEAT_", "INTERACT_", "SIGN_")


def room_of(o):
    for c in o.users_collection:
        if c.name.startswith("ROOM_"):
            return c.name
    return o.parent and room_of(o.parent) or "-"


def object_index():
    rows = []
    for o in sorted(bpy.data.objects, key=lambda x: x.name):
        if not o.name.startswith(INTERACTIVE) or o.name.endswith("_plate"):
            continue
        p = o.matrix_world.translation
        if o.type == "MESH" and o.get("static") and not o.name.startswith("CRYO_POD_"):
            # transforms get applied on export, so use the world-space bounds centre
            from mathutils import Vector
            bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
            p = sum(bb, Vector()) / 8
        kind = "empty" if o.type == "EMPTY" else "mesh"
        rows.append((o.name, room_of(o), kind, (p.x, p.y, p.z), (p.x, p.z, -p.y),
                     o.parent.name if o.parent else ""))
    return rows


def write_summary(path):
    rows = object_index()
    lines = ["# Space Veluton starter ship - named objects", "",
             f"Generated {datetime.date.today().isoformat()} by scripts/finalize.py from spacevelution_ship.blend.",
             "Positions are world-space origins in metres (static SIGN_ meshes: bounds centre). "
             "Blender is Z-up; glTF/Three.js is Y-up, so the glTF position is (x, z, -y).", "",
             "| Object | Collection | Type | Blender (x, y, z) | glTF (x, y, z) | Parent |",
             "|---|---|---|---|---|---|"]
    for name, room, kind, b, g, parent in rows:
        fb = ", ".join(f"{v:.2f}" for v in b)
        fg = ", ".join(f"{v:.2f}" for v in g)
        lines.append(f"| `{name}` | {room} | {kind} | {fb} | {fg} | {parent} |")
    body = "\n".join(lines) + "\n"
    with open(bpy.path.abspath(path), "w") as f:
        f.write(body)
    return len(rows)


def build():
    out = {}
    for name, path in SCRIPTS.items():
        with open(bpy.path.abspath(path)) as f:
            set_text(name, f.read())
        out[name] = "stored"
    set_text("ASSET_CREDITS", ASSET_CREDITS)
    set_text("README_ship", README)
    out["summary_rows"] = write_summary("//SCENE_SUMMARY.md")
    return out
