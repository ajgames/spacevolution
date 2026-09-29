"""Export a character collection to glTF (.glb) for the game, then check the file.

    blender -b characters.blend --python scripts/export_character.py -- [out.glb] [name]

Default output: //export/characters/<name>.glb. Nothing syncs it into public/ yet:
add it to the manifest (or the sync script) when the game starts loading characters.

What goes in:
  * BODY / EYES / MOUTH as skinned meshes. The Multires modifier is not applied, so
    the body is its level-0 base (~21k tris). Shape keys become morph targets.
  * Deforming bones only (the IK controls and poles stay in Blender). Constraints
    don't export: limits travel as bone extras (limits_deg, axes), and the viseme
    table as the body's extras.
  * The animation clips (scripts/anim_character.py): idle, walk, strafe_left/right,
    jump, crouch, talk, without jaw or eye channels (the game drives those). Clip
    speeds for foot-locked locomotion are in the rig node's "clips" extra.
  * The hand pose assets as one-frame clips (hand_fist, hand_point, ...) that only
    touch the 38 hand bones, so they layer over whatever the body is doing.
"""
import json
import os
import struct
import sys

import bpy

sys.dont_write_bytecode = True
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import build_character as B  # noqa: E402


def export(path, name=B.NAME):
    coll = bpy.data.collections["CHAR_" + name]
    view = bpy.context.view_layer
    view.active_layer_collection = view.layer_collection.children[coll.name]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        use_active_collection=True,
        use_active_collection_with_nested=True,
        export_apply=False,              # keep shape keys; Multires stays in Blender
        export_skins=True,
        export_def_bones=True,
        export_all_influences=False,     # four per vertex, as painted
        export_morph=True,
        export_morph_normal=True,
        export_try_sparse_sk=True,
        export_extras=True,
        export_animations=True,
        export_animation_mode="ACTIONS",
        export_leaf_bone=False,
        export_yup=True,
    )
    trim_clips(path)
    return check(path, name)


FACE_BONES = {"jaw", "eye_L", "eye_R"}


def trim_clips(path):
    """The exporter samples every joint into every clip. Hand poses keep only the hand
    bones, so they can play over other animation without snapping the body to rest;
    body clips drop the jaw and eyes, which the game drives (lip sync, gaze)."""
    with open(path, "rb") as f:
        data = f.read()
    n = struct.unpack_from("<I", data, 12)[0]
    g = json.loads(data[20:20 + n])
    rest = data[20 + n:]                      # the BIN chunk, untouched
    names = [nd.get("name", "") for nd in g["nodes"]]
    for a in g.get("animations", []):
        if a["name"].startswith("hand_"):
            keep = [c for c in a["channels"] if names[c["target"]["node"]][:-2] in B.HAND_KEYS]
        else:
            keep = [c for c in a["channels"] if names[c["target"]["node"]] not in FACE_BONES]
        used = sorted({c["sampler"] for c in keep})
        remap = {old: new for new, old in enumerate(used)}
        a["samplers"] = [a["samplers"][i] for i in used]
        for c in keep:
            c["sampler"] = remap[c["sampler"]]
        a["channels"] = keep
    js = json.dumps(g, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + len(rest)) + struct.pack("<II", len(js), 0x4E4F534A) + js + rest
    with open(path, "wb") as f:
        f.write(out)


def read_glb(path):
    with open(path, "rb") as f:
        data = f.read()
    magic, _, _ = struct.unpack_from("<III", data, 0)
    assert magic == 0x46546C67, "not a GLB"
    n, _ = struct.unpack_from("<II", data, 12)
    return json.loads(data[20:20 + n])


def check(path, name=B.NAME):
    g = read_glb(path)
    nodes = g["nodes"]
    names = [n.get("name", "") for n in nodes]
    skins = g.get("skins", [])
    assert skins, "no skin exported"
    joints = [names[j] for j in skins[0]["joints"]]
    rig = bpy.data.objects["RIG_" + name]
    want = sorted(b.name for b in rig.data.bones if b.use_deform)
    assert sorted(joints) == want, "joint mismatch: %s" % sorted(set(want) ^ set(joints))
    meshes = {m["name"]: m for m in g["meshes"]}
    body = next(m for n, m in meshes.items() if n.startswith("BODY_"))
    targets = body.get("extras", {}).get("targetNames", [])
    assert set(B.MOUTH_KEYS + B.BLINK_KEYS) <= set(targets), "morph targets: %s" % targets
    body_node = next(n for n in nodes if n.get("name") == "BODY_" + name)
    assert "visemes" in body_node.get("extras", {}), "viseme table missing from body extras"
    hand = next(n for n in nodes if n.get("name") == "hand_L")
    assert "limits_deg" in hand.get("extras", {}), "bone limits missing from joint extras"
    clips = [a["name"] for a in g.get("animations", [])]
    for a in g.get("animations", []):
        touched = {names[c["target"]["node"]] for c in a["channels"]}
        if a["name"].startswith("hand_"):
            stray = sorted(n for n in touched if n[:-2] not in B.HAND_KEYS)
        else:
            stray = sorted(touched & FACE_BONES)
        assert not stray, "clip %s moves bones it shouldn't: %s" % (a["name"], stray[:5])
    rig_node = next(n for n in nodes if n.get("name") == "RIG_" + name)
    assert "clips" in rig_node.get("extras", {}), "clip speeds missing from the rig's extras"
    tris = 0
    for m in g["meshes"]:
        for p in m["primitives"]:
            tris += g["accessors"][p["indices"]]["count"] // 3
    size = os.path.getsize(path)
    report = dict(file=path, bytes=size, joints=len(joints), meshes=sorted(meshes), triangles=tris,
                  morph_targets=targets, clips=clips)
    print("glTF check OK:", json.dumps(report, indent=1))
    return report


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    name = argv[1] if len(argv) > 1 else B.NAME
    out = argv[0] if argv else os.path.join(B.BLENDER_DIR, "export", "characters", name + ".glb")
    export(out, name)
