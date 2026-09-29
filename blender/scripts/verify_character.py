"""Check renders for the character build (Workbench, headless).

    blender -b characters.blend --python scripts/verify_character.py -- <out_dir> [bones|body|poses|face|clips|beauty|all]

bones   X-ray body with every deform bone drawn as a solid (red Z-axis tick = roll)
body    front/side/back/three-quarter of the rest pose
poses   test poses: fists, wrist, fingers, elbows, knees, IK, twist, jaw, eyes
face    mouth shapes, visemes and blinks
clips   8 frames of every animation clip, side and front (clip_<name>.png)
beauty  EEVEE renders from the stage camera (rest pose and a talking gesture)
Single frames go to <out_dir>/frames/, contact sheets to <out_dir>/.
"""
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

sys.dont_write_bytecode = True
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import build_character as B  # noqa: E402


def scene_objects():
    return bpy.data.objects[B.RIG], bpy.data.objects[B.BODY]


def render_setup(res=(900, 900)):
    """Workbench, material colours, and a camera. Callers tweak shading afterwards."""
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    sh.light = "STUDIO"
    sh.color_type = "MATERIAL"
    sh.show_cavity = False
    sh.show_backface_culling = False
    sh.show_xray = False
    return sc, _camera(sc, res)


def _camera(sc, res):
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.film_transparent = False
    sc.display.render_aa = "8"
    cam = bpy.data.objects.get("_verify_cam")
    if cam is None:
        cam = bpy.data.objects.new("_verify_cam", bpy.data.cameras.new("_verify_cam"))
        sc.collection.objects.link(cam)
    sc.camera = cam
    return cam


def shoot(path, ctr, direction, size, ortho=True, res=None):
    sc = bpy.context.scene
    cam = _camera(sc, res or (900, 900))
    d = Vector(direction).normalized()
    cam.data.type = "ORTHO" if ortho else "PERSP"
    cam.data.ortho_scale = size
    cam.data.clip_start, cam.data.clip_end = 0.01, 20
    cam.location = Vector(ctr) + d * 4
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


def bone_proxies(rig, deform_only=True, name="_verify_bones"):
    """Solid octahedra per bone in the current pose, plus a thin tick along local +Z."""
    old = bpy.data.objects.get(name)
    if old:
        bpy.data.objects.remove(old, do_unlink=True)
    verts, faces, tick_faces = [], [], []
    for pb in rig.pose.bones:
        if deform_only and not pb.bone.use_deform:
            continue
        M = rig.matrix_world @ pb.matrix
        L = pb.bone.length
        w = min(0.1 * L, 0.012)
        local = [(0, 0, 0), (w, 0.1 * L, 0), (0, 0.1 * L, w), (-w, 0.1 * L, 0), (0, 0.1 * L, -w), (0, L, 0)]
        base = len(verts)
        verts += [M @ Vector(p) for p in local]
        for a, b in ((1, 2), (2, 3), (3, 4), (4, 1)):
            faces.append((base, base + a, base + b))
            faces.append((base + 5, base + b, base + a))
        # Z tick: a thin quad strip from the bone's middle towards +Z
        t = [(0, 0.45 * L, 0), (0, 0.55 * L, 0), (0, 0.55 * L, 2.5 * w + 0.004), (0, 0.45 * L, 2.5 * w + 0.004)]
        tb = len(verts)
        verts += [M @ Vector(p) for p in t]
        tick_faces.append((tb, tb + 1, tb + 2, tb + 3))
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces + tick_faces)
    me.materials.append(_mat("_vb_bone", (0.15, 0.45, 1.0, 1)))
    me.materials.append(_mat("_vb_tick", (1.0, 0.1, 0.05, 1)))
    for i, p in enumerate(me.polygons):
        p.material_index = 1 if i >= len(faces) else 0
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.color = (0.15, 0.45, 1.0, 1)
    return ob


def _mat(name, rgba):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.diffuse_color = rgba
    return m


def render_bones(out):
    rig, body = scene_objects()
    bone_proxies(rig)
    sc, _ = render_setup()
    sh = sc.display.shading
    sh.color_type = "MATERIAL"
    sh.show_xray = True
    sh.xray_alpha = 0.25
    body.color = (0.8, 0.7, 0.6, 1)
    views = {
        "bones_front": ((0, 0, 0.92), (0, -1, 0), 1.9),
        "bones_side": ((0, 0, 0.92), (1, 0, 0), 1.9),
        "bones_hand_out": ((0.42, -0.11, 0.86), (1, 0, 0), 0.26),
        "bones_hand_front": ((0.42, -0.11, 0.86), (0, -1, 0), 0.26),
        "bones_hand_in": ((0.42, -0.11, 0.86), (-1, -0.2, 0), 0.26),
        "bones_head_side": ((0, -0.06, 1.64), (1, 0, 0), 0.38),
        "bones_foot": ((0.2, 0, 0.12), (1, -0.4, 0.2), 0.45),
        "bones_shoulder": ((0.18, 0, 1.35), (0, -1, 0), 0.5),
    }
    for n, (c, d, s) in views.items():
        shoot(os.path.join(out, n + ".png"), c, d, s)
    sh.show_xray = False


def render_body(out, prefix="body"):
    rig, body = scene_objects()
    for o in bpy.context.scene.objects:
        o.hide_render = o is not body and not o.name.startswith(("EYES_", "_src_eye"))
    sc, _ = render_setup((700, 1000))
    sh = sc.display.shading
    sh.color_type = "SINGLE"
    sh.single_color = (0.8, 0.7, 0.62)
    sh.show_cavity = True
    for n, d in (("front", (0, -1, 0)), ("side", (1, 0, 0)), ("back", (0, 1, 0)), ("q", (0.7, -0.7, 0))):
        shoot(os.path.join(out, "%s_%s.png" % (prefix, n)), (0, 0, 0.9), d, 1.95, res=(700, 1000))
    sh.show_cavity = False


# name: ({bone: (x, y, z) degrees in the bone's local axes}, camera)
# camera: (target bone, view direction, ortho size) or ("world", centre, direction, size)
FIST = {"index_01_L": (80, 0, 0), "index_02_L": (95, 0, 0), "index_03_L": (55, 0, 0),
        "middle_01_L": (85, 0, 0), "middle_02_L": (95, 0, 0), "middle_03_L": (55, 0, 0),
        "ring_01_L": (88, 0, 0), "ring_02_L": (95, 0, 0), "ring_03_L": (55, 0, 0),
        "pinky_01_L": (90, 0, 0), "pinky_02_L": (90, 0, 0), "pinky_03_L": (55, 0, 0),
        "palm_ring_L": (8, 0, 0), "palm_pinky_L": (15, 0, 0),
        "thumb_01_L": (30, 20, 10), "thumb_02_L": (35, 0, 0), "thumb_03_L": (45, 0, 0)}
POINT = dict(FIST, index_01_L=(0, 0, 0), index_02_L=(0, 0, 0), index_03_L=(0, 0, 0))
SPREAD = {"index_01_L": (-10, 0, 18), "middle_01_L": (-10, 0, 3), "ring_01_L": (-10, 0, -12),
          "pinky_01_L": (-10, 0, -25), "thumb_01_L": (-20, 0, 35), "thumb_02_L": (-10, 0, 0),
          "thumb_03_L": (-15, 0, 0)}
HAND_CAM_OUT = ("hand_L", (1, -0.35, 0.1), 0.24)
HAND_CAM_IN = ("hand_L", (-1, -0.5, 0.2), 0.24)
POSES = {
    "fist_out": (FIST, HAND_CAM_OUT),
    "fist_in": (FIST, HAND_CAM_IN),
    "point_out": (POINT, HAND_CAM_OUT),
    "spread_in": (SPREAD, HAND_CAM_IN),
    "wrist_flex": ({"hand_L": (65, 0, 0)}, ("forearm_L", (0.2, -1, 0), 0.4)),
    "wrist_extend": ({"hand_L": (-60, 0, 0)}, ("forearm_L", (0.2, -1, 0), 0.4)),
    "wrist_radial_ulnar": ({"hand_L": (0, 0, 22), "hand_R": (0, 0, 30)}, ("world", (0, -0.1, 0.9), (0, -1, 0), 1.1)),
    "wrist_pronate": ({"hand_L": (0, 80, 0), "hand_R": (0, -80, 0)}, ("world", (0, -0.1, 0.9), (0.15, -1, 0.3), 1.1)),
    "elbows": ({"forearm_L": (110, 0, 0), "forearm_R": (70, 0, 0)}, ("world", (0, 0, 1.2), (0.5, -1, 0.1), 1.2)),
    "arms_up": ({"upperarm_L": (0, 0, 70), "upperarm_R": (0, 0, -70), "clavicle_L": (15, 0, 0)},
                ("world", (0, 0, 1.4), (0, -1, 0), 1.4)),
    "arm_forward": ({"upperarm_L": (80, 0, 0), "forearm_L": (20, 0, 0)}, ("world", (0.1, -0.1, 1.3), (1, -0.6, 0.1), 1.2)),
    "legs": ({"thigh_L": (85, 0, 0), "shin_L": (100, 0, 0), "thigh_R": (-20, 0, 0), "foot_R": (30, 0, 0)},
             ("world", (0, -0.1, 0.7), (1, -0.3, 0), 1.6)),
    "spine_head": ({"spine_01": (15, 0, 0), "spine_02": (15, 0, 0), "spine_03": (10, 0, 0),
                    "neck": (10, 30, 0), "head": (10, 30, 0)}, ("world", (0, -0.05, 1.3), (0.6, -1, 0), 1.0)),
    "jaw_open": ({"jaw": (22, 0, 0)}, ("world", (0, -0.1, 1.62), (0.25, -1, 0), 0.26)),
    "jaw_open_side": ({"jaw": (22, 0, 0)}, ("world", (0, -0.08, 1.62), (1, -0.15, 0), 0.3)),
    "eyes": ({"eye_L": (0, 0, 25), "eye_R": (0, 0, 25)}, ("world", (0, -0.12, 1.68), (0, -1, 0), 0.16)),
    "ik_reach": ({"_props": {"ik_arm_L": 1.0}, "_move": {"ik_hand_L": (-0.15, -0.40, 0.45)}},
                 ("world", (0.1, -0.2, 1.2), (1, -0.8, 0.2), 1.3)),
    "ik_crouch": ({"_props": {"ik_leg_L": 1.0, "ik_leg_R": 1.0}, "_move": {"hips": (0, 0.05, -0.30)},
                   "spine_01": (20, 0, 0)}, ("world", (0, 0, 0.7), (1, -0.8, 0.1), 1.8)),
    "twist_close": ({"hand_L": (0, 85, 0)}, ("forearm_L", (1, -0.2, 0), 0.4)),
    "twist_rest": ({}, ("forearm_L", (1, -0.2, 0), 0.4)),
}


FACE_TESTS = [   # (name, {shape key: value}, jaw degrees)
    ("rest", {}, 0), ("wide", {"mouth_wide": 1}, 0), ("round", {"mouth_round": 1}, 0),
    ("press", {"mouth_press": 1}, 0), ("fv", {"mouth_fv": 1}, 4), ("upper_up", {"lip_upper_up": 1}, 0),
    ("smile", {"mouth_smile": 1}, 0), ("aa", {}, 14), ("ee", {"mouth_wide": 0.8, "lip_upper_up": 0.4}, 6),
    ("oo", {"mouth_round": 1}, 6), ("blink_L", {"blink_L": 1}, 0), ("blinks", {"blink_L": 1, "blink_R": 1}, 0),
]


def render_face(out):
    rig, body = scene_objects()
    for o in bpy.context.scene.objects:
        o.hide_render = o.type != "MESH" or o.name.startswith(("_", "WGT", "FLOOR"))
    sc, _ = render_setup()
    keys = body.data.shape_keys.key_blocks
    files = []
    for name, vals, jaw in FACE_TESTS:
        for kb in keys:
            kb.value = float(vals.get(kb.name, 0.0))
        set_pose(rig, {"jaw": (jaw, 0, 0)})
        f = os.path.join(out, "face_%s.png" % name)
        c = (0, -0.12, 1.66) if name.startswith("blink") else (0, -0.12, 1.615)
        shoot(f, c, (0.25, -1, 0.05), 0.11 if not name.startswith("blink") else 0.14, res=(500, 500))
        files.append(f)
    for kb in keys:
        kb.value = 0.0
    set_pose(rig, {})
    return files


def set_pose(rig, pose):
    for pb in rig.pose.bones:
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)
    for n in [k for k in rig.keys() if k.startswith("ik_")]:
        rig[n] = float(pose.get("_props", {}).get(n, 0.0))
    for name, delta in pose.get("_move", {}).items():
        pb = rig.pose.bones[name]      # world-space offset -> bone-local location
        pb.location = pb.bone.matrix_local.to_3x3().inverted() @ Vector(delta)
    for name, deg in pose.items():
        if name.startswith("_"):
            continue
        pb = rig.pose.bones[name]
        e = Euler([math.radians(a) for a in deg], "XZY")
        if pb.rotation_mode == "QUATERNION":
            pb.rotation_quaternion = e.to_quaternion()
        elif pb.rotation_mode == "AXIS_ANGLE":
            raise ValueError(name)
        else:
            pb.rotation_euler = e.to_matrix().to_euler(pb.rotation_mode)
    rig.update_tag()
    bpy.context.view_layer.update()


def render_poses(out, names=None):
    rig, body = scene_objects()
    for o in bpy.context.scene.objects:
        o.hide_render = o.type != "MESH" or o.name.startswith(("_", "WGT", "FLOOR"))
    sc, _ = render_setup()
    sc.display.shading.color_type = "MATERIAL"
    for name, (pose, cam) in POSES.items():
        if names and name not in names:
            continue
        set_pose(rig, pose)
        if cam[0] == "world":
            _, ctr, d, size = cam
        else:
            bone, d, size = cam
            pb = rig.pose.bones[bone]
            ctr = rig.matrix_world @ ((pb.head + pb.tail) / 2 if bone != "hand_L" else pb.tail)
        shoot(os.path.join(out, "pose_%s.png" % name), ctr, d, size, res=(700, 700))
    set_pose(rig, {})


GESTURE = {"upperarm_R": (35, 0, 10), "forearm_R": (100, 0, 0), "hand_R": (-15, -30, 0),
           "index_01_R": (10, 0, 0), "middle_01_R": (18, 0, 0), "ring_01_R": (25, 0, 0), "pinky_01_R": (32, 0, 0),
           "index_02_R": (10, 0, 0), "middle_02_R": (18, 0, 0), "ring_02_R": (25, 0, 0), "pinky_02_R": (30, 0, 0),
           "thumb_01_R": (0, 0, -15), "upperarm_L": (0, 0, -20), "forearm_L": (15, 0, 0),
           "index_01_L": (8, 0, 0), "middle_01_L": (14, 0, 0), "ring_01_L": (20, 0, 0), "pinky_01_L": (24, 0, 0),
           "spine_02": (3, 5, 0), "neck": (4, 8, 3), "head": (-3, 10, 3), "jaw": (7, 0, 0),
           "eye_L": (0, 0, -6), "eye_R": (0, 0, -6)}


def play(rig, action, frame):
    ad = rig.animation_data_create()
    ad.action = action
    if action and not ad.action_slot and action.slots:
        ad.action_slot = action.slots[0]
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()


def render_clips(out, frames_per_clip=8, names=None):
    """One strip per clip: evenly spaced frames, side view over front view."""
    rig, body = scene_objects()
    for o in bpy.context.scene.objects:
        o.hide_render = o.type != "MESH" or o.name.startswith(("_", "WGT", "FLOOR"))
    render_setup()
    strips = []
    for name in (names or list(rig["clips"].keys())):
        act = bpy.data.actions[name]
        a, b = int(act.frame_start), int(act.frame_end)
        files = []
        for view, d in (("side", (1, -0.25, 0.05)), ("front", (0.2, -1, 0.05))):
            for i in range(frames_per_clip):
                f = a + round(i * (b - a) / frames_per_clip)
                play(rig, act, f)
                path = os.path.join(out, "clip_%s_%s_%02d.png" % (name, view, i))
                shoot(path, (0, 0, 0.92), d, 2.1, res=(300, 420))
                files.append(path)
        strip = os.path.join(out, "clip_%s.png" % name)
        sheet(strip, files, frames_per_clip)
        strips.append(strip)
    play(rig, None, 1)
    return strips


def render_beauty(out):
    rig, body = scene_objects()
    sc = bpy.context.scene
    for o in sc.objects:
        o.hide_render = o.name.startswith(("_", "WGT"))
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = 1080, 1350
    sc.render.film_transparent = False
    sc.camera = bpy.data.objects["CAM_" + B.NAME]
    keys = body.data.shape_keys.key_blocks
    files = []
    for name, pose, sk in (("rest", {}, {}), ("talking", GESTURE, {"mouth_wide": 0.6, "lip_upper_up": 0.3})):
        set_pose(rig, pose)
        for kb in keys:
            kb.value = float(sk.get(kb.name, 0.0))
        sc.render.filepath = os.path.join(out, "beauty_%s.png" % name)
        bpy.ops.render.render(write_still=True)
        files.append(sc.render.filepath)
    for kb in keys:
        kb.value = 0.0
    set_pose(rig, {})
    return files


def sheet(path, files, cols):
    """Stitch same-sized or smaller images into one grid (top-left aligned per cell)."""
    ims = [bpy.data.images.load(f, check_existing=False) for f in files]
    w = max(i.size[0] for i in ims)
    h = max(i.size[1] for i in ims)
    rows = math.ceil(len(ims) / cols)
    buf = np.zeros((rows * h, cols * w, 4), np.float32)
    buf[..., 3] = 1
    for k, im in enumerate(ims):
        iw, ih = im.size
        a = np.array(im.pixels[:], np.float32).reshape(ih, iw, 4)
        r, c = divmod(k, cols)
        r = rows - 1 - r
        buf[r * h + (h - ih):(r + 1) * h, c * w:c * w + iw] = a
        bpy.data.images.remove(im)
    o = bpy.data.images.new("_sheet", cols * w, rows * h)
    o.pixels[:] = buf.ravel()
    o.filepath_raw = path
    o.file_format = "PNG"
    o.save()
    bpy.data.images.remove(o)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[0] if argv else os.path.join(B.BLENDER_DIR, "screenshots", "characters")
    what = argv[1] if len(argv) > 1 else "all"
    frames = os.path.join(out, "frames")
    os.makedirs(frames, exist_ok=True)
    if what in ("bones", "all"):
        render_bones(frames)
        sheet(os.path.join(out, "bones.png"), [os.path.join(frames, "bones_%s.png" % n) for n in
              ("front", "side", "hand_out", "hand_in", "head_side", "foot")], 3)
    if what in ("body", "all"):
        render_body(frames)
        sheet(os.path.join(out, "body.png"), [os.path.join(frames, "body_%s.png" % n) for n in
              ("front", "side", "back", "q")], 4)
    if what in ("face", "all"):
        sheet(os.path.join(out, "face.png"), render_face(frames), 4)
    if what in ("poses", "all"):
        render_poses(frames, argv[2:] or None)
        if not argv[2:]:
            sheet(os.path.join(out, "poses.png"), [os.path.join(frames, "pose_%s.png" % n) for n in POSES], 5)
    if what in ("clips", "all"):
        for strip in render_clips(frames, names=argv[2:] or None):
            os.replace(strip, os.path.join(out, os.path.basename(strip)))
    if what in ("beauty", "all"):
        sheet(os.path.join(out, "beauty.png"), render_beauty(frames), 2)
