"""export_ship.py - apply transforms and export every ROOM_* collection to glTF (.glb).

This file is also stored inside spacevelution_ship.blend as the text block
"export_ship.py". Run it from Blender's Text Editor (Run Script), or headless:

    blender spacevelution_ship.blend --background --python-text export_ship.py

Output: //export/ROOM_command.glb, ROOM_cryo.glb, ROOM_engineering.glb, ROOM_corridor.glb
(// = the folder holding the .blend). Each export is re-read and validated.

Per ROOM_* collection it:
  1. Applies transforms.
     * Static meshes: location, rotation and scale are baked into the mesh, so
       their glTF nodes carry identity transforms.
     * Dynamic / interactive objects (DOOR_*, BTN_*, SCREEN_*, CRYO_POD_* and
       their children, SPAWN_*, SEAT_*, INTERACT_*, LIGHT_*): only scale is
       applied. Their origin (press point, hinge, slide axis) and local axes
       survive as the node transform the game code animates.
  2. Checks both UV maps: "UVMap" -> TEXCOORD_0 (trim-sheet textures),
     "lightmap" -> TEXCOORD_1 (baked lighting, one overlap-free atlas per room).
  3. Exports only that collection (meshes and marker empties). Custom
     properties go out as glTF extras, minus build-only keys (stage, glow).
     Lights, cameras and the LIGHTS_*, REF_* and _CAMERAS collections are never
     exported.
The transform step is idempotent, so running the script twice is safe.
"""
import json
import os
import struct

import bpy
from mathutils import Matrix, Vector

ROOMS = ["ROOM_command", "ROOM_cryo", "ROOM_engineering", "ROOM_corridor"]
OUT_DIR = "//export"
EXPORT_FORMAT = "GLB"            # or "GLTF_SEPARATE" to share texture files between rooms
IMAGE_FORMAT = "AUTO"            # "WEBP" shrinks the files a lot
DYNAMIC_PREFIXES = ("DOOR_", "BTN_", "SCREEN_", "CRYO_POD_", "SPAWN_", "SEAT_", "INTERACT_", "LIGHT_")
BUILD_ONLY_PROPS = ("stage", "glow")


def is_dynamic(ob):
    o = ob
    while o is not None:
        if o.name.startswith(DYNAMIC_PREFIXES) or o.get("dynamic"):
            return True
        o = o.parent
    return False


def apply_transforms(objs):
    """Bake transforms into mesh data (data API: no selection/context needed)."""
    applied, scale_only, skipped = [], [], []
    for ob in objs:
        if ob.type != "MESH":
            continue
        me = ob.data
        if me.users > 1:
            skipped.append(ob.name + " (shared mesh)")
            continue
        if is_dynamic(ob) or ob.children:
            s = ob.scale.copy()
            if (s - Vector((1, 1, 1))).length > 1e-6:
                me.transform(Matrix.Diagonal((*s, 1.0)))
                ob.scale = (1, 1, 1)
            scale_only.append(ob.name)
            continue
        mw = ob.matrix_world.copy()
        if ob.parent is not None:
            skipped.append(ob.name + " (has parent)")
            continue
        if mw != Matrix.Identity(4):
            me.transform(mw)
            if mw.determinant() < 0:
                me.flip_normals()
            # keep the bake-glow hint (object-local) pointing at the same spot
            g = ob.get("glow")
            if g is not None:
                c = mw @ Vector(g["center"])
                n = (mw.to_3x3() @ Vector(g["normal"])).normalized()
                g["center"] = list(c)
                g["normal"] = list(n)
            ob.matrix_world = Matrix.Identity(4)
        applied.append(ob.name)
        me.update()
    return applied, scale_only, skipped


def check_uvs(objs):
    bad = []
    for ob in objs:
        if ob.type != "MESH":
            continue
        uvs = ob.data.uv_layers
        if len(uvs) < 2 or uvs[0].name != "UVMap" or uvs[1].name != "lightmap":
            bad.append(ob.name)
        else:
            uvs.active = uvs["UVMap"]
            uvs["UVMap"].active_render = True
    return bad


def read_glb(path):
    with open(path, "rb") as f:
        data = f.read()
    magic, version, length = struct.unpack("<III", data[:12])
    clen, ctype = struct.unpack("<II", data[12:20])
    js = json.loads(data[20:20 + clen])
    off = 20 + clen
    blen, btype = struct.unpack("<II", data[off:off + 8])
    return js, data[off + 8:off + 8 + blen], length


def read_vec2(js, binchunk, acc_index):
    """Float VEC2 accessor -> list of (u, v)."""
    acc = js["accessors"][acc_index]
    bv = js["bufferViews"][acc["bufferView"]]
    start = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    stride = bv.get("byteStride", 8)
    out = []
    for i in range(acc["count"]):
        out.append(struct.unpack_from("<ff", binchunk, start + i * stride))
    return out


def validate(path, objs):
    js, binchunk, size = read_glb(path)
    nodes = {n["name"] for n in js.get("nodes", [])}
    expected = {o.name for o in objs}
    missing_nodes = sorted(expected - nodes)
    no_lm, lm_range_bad = [], []
    for m in js.get("meshes", []):
        for p in m["primitives"]:
            a = p["attributes"]
            if "TEXCOORD_0" not in a or "TEXCOORD_1" not in a:
                no_lm.append(m["name"])
                continue
            lm = read_vec2(js, binchunk, a["TEXCOORD_1"])
            us = [u for u, v in lm]
            vs = [v for u, v in lm]
            if min(us) < -1e-4 or max(us) > 1 + 1e-4 or min(vs) < -1e-4 or max(vs) > 1 + 1e-4:
                lm_range_bad.append(m["name"])
    return {"file": os.path.basename(path), "bytes": size, "nodes": len(nodes), "meshes": len(js.get("meshes", [])),
            "missing_nodes": missing_nodes, "primitives_missing_uv": sorted(set(no_lm)),
            "lightmap_uv_outside_0_1": sorted(set(lm_range_bad)),
            "ok": not missing_nodes and not no_lm and not lm_range_bad}


def export_room(name, out_dir):
    coll = bpy.data.collections[name]
    objs = list(coll.all_objects)
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    applied, scale_only, skipped = apply_transforms(objs)
    bad_uv = check_uvs(objs)
    # strip build-only custom properties for the export, restore afterwards
    stash = {}
    for o in objs:
        for k in BUILD_ONLY_PROPS:
            if k in o:
                v = o[k]
                # copy to plain Python first: deleting the property frees the ID data
                v = v.to_dict() if hasattr(v, "to_dict") else (v.to_list() if hasattr(v, "to_list") else v)
                stash[(o.name, k)] = v
                del o[k]
    vl = bpy.context.view_layer
    for o in vl.objects:
        o.select_set(False)
    hidden = []
    for o in objs:
        if o.hide_get():
            hidden.append(o)
            o.hide_set(False)
        o.select_set(True)
    ext = ".glb" if EXPORT_FORMAT == "GLB" else ".gltf"
    path = os.path.join(out_dir, name + ext)
    try:
        bpy.ops.export_scene.gltf(
            filepath=path, export_format=EXPORT_FORMAT, use_selection=True,
            export_texcoords=True, export_normals=True, export_tangents=False,
            export_materials="EXPORT", export_image_format=IMAGE_FORMAT,
            export_extras=True, export_yup=True, export_apply=True,
            export_cameras=False, export_lights=False, export_animations=False,
            export_attributes=False)
    finally:
        for (oname, k), v in stash.items():
            bpy.data.objects[oname][k] = v
        for o in objs:
            o.select_set(False)
        for o in hidden:
            o.hide_set(True)
    report = validate(path, objs) if EXPORT_FORMAT == "GLB" else {"file": path}
    report.update({"transforms_applied": len(applied), "scale_only": len(scale_only), "skipped": skipped,
                   "uv_layout_bad": bad_uv})
    report["ok"] = report.get("ok", True) and not bad_uv and not skipped
    return report


def main():
    out_dir = bpy.path.abspath(OUT_DIR)
    os.makedirs(out_dir, exist_ok=True)
    reports = {r: export_room(r, out_dir) for r in ROOMS}
    for r, rep in reports.items():
        print(f"[export_ship] {r}: {'OK' if rep['ok'] else 'PROBLEM'} -> {rep}")
    return reports


if __name__ == "__main__":
    main()
