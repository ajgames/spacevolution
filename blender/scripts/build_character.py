"""Build the main character, rigged and ready for clothes, into //characters.blend.

    blender -b --factory-startup --python scripts/build_character.py

The body is the realistic male from Blender Studio's CC0 "Human Base Meshes"
bundle, downloaded into //assets/ on first run (gitignored). Rebuilding replaces the
CHAR_<NAME> collection and leaves any other characters in the file alone.

Pipeline: import -> scale to HEIGHT -> slim -> skeleton -> skin weights -> jaw
weights -> teeth, tongue, eyes -> shape keys (mouth, blinks) -> materials ->
constraints and IK -> hand pose library -> animation clips (anim_character.py)
-> stage -> save + CHARACTER_SUMMARY.md. Export with export_character.py.
"""
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.dont_write_bytecode = True      # scripts/ is synced; keep __pycache__ out of it
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import lib_character as LC  # noqa: E402

BLENDER_DIR = os.path.dirname(SCRIPTS_DIR)
OUT_BLEND = os.path.join(BLENDER_DIR, "characters.blend")
ASSETS_DIR = os.path.join(BLENDER_DIR, "assets")
SUMMARY_MD = os.path.join(BLENDER_DIR, "CHARACTER_SUMMARY.md")

NAME = "caretaker"
HEIGHT = 1.80                    # metres, soles to crown
SCENE = "Characters"
COLL = "CHAR_" + NAME
RIG = "RIG_" + NAME
BODY = "BODY_" + NAME
EYES = "EYES_" + NAME
MOUTH = "MOUTH_" + NAME          # teeth, gums and tongue

SRC_BODY = "GEO-body_male_realistic"
SRC_EYES = ("GEO-body_male_realistic.eye.L", "GEO-body_male_realistic.eye.R")
SRC_JAW = "Jaw - Realistic"

# Mouth landmarks on the source mesh (vertex indices, stable across the bundle's
# v1.4.x): the lowest point of the upper lip and the highest of the lower lip,
# both on the midline. The build asserts they are where they should be.
V_UPPER_LIP = 8004
V_LOWER_LIP = 7986

# ---------------------------------------------------------------------------
# Joint centres (m) on the 1.80 m body, measured once with lib_character.Sectioner
# (limb cross-section centroids; finger joints placed by phalanx proportions along
# each traced finger). Left side (+X); the right side is mirrored.
# ---------------------------------------------------------------------------
J = {
    "hips": (0.0, 0.015, 0.930),
    "spine_01": (0.0, -0.005, 1.040),
    "spine_02": (0.0, 0.000, 1.170),
    "spine_03": (0.0, 0.012, 1.300),
    "neck": (0.0, 0.022, 1.470),
    "head": (0.0, -0.040, 1.615),
    "head_top": (0.0, -0.045, 1.800),
    "jaw": (0.0, -0.050, 1.640),       # between the two jaw hinges
    "chin": (0.0, -0.140, 1.565),
    "clavicle": (0.020, -0.040, 1.455),
    "shoulder": (0.190, 0.010, 1.430),
    "elbow": (0.316, 0.008, 1.163),
    "wrist": (0.401, -0.071, 0.935),
    # finger chains: MCP (knuckle), PIP, DIP, tip.  thumb: CMC, MCP, IP, tip
    "index": [(0.4295, -0.1283, 0.8681), (0.4457, -0.1556, 0.8425), (0.4474, -0.1692, 0.8186), (0.4449, -0.1798, 0.7952)],
    "middle": [(0.4373, -0.1057, 0.8563), (0.4581, -0.1321, 0.8255), (0.4603, -0.1439, 0.7963), (0.4600, -0.1554, 0.7705)],
    "ring": [(0.4431, -0.0911, 0.8537), (0.4573, -0.1041, 0.8151), (0.4559, -0.1128, 0.7882), (0.4528, -0.1224, 0.7651)],
    "pinky": [(0.4336, -0.0757, 0.8554), (0.4469, -0.0678, 0.8196), (0.4510, -0.0666, 0.7958), (0.4526, -0.0711, 0.7745)],
    "thumb": [(0.3920, -0.1000, 0.9150), (0.3912, -0.1455, 0.9000), (0.3935, -0.1680, 0.8782), (0.3927, -0.1911, 0.8686)],
    "hip": (0.090, -0.015, 0.915),
    "knee": (0.153, 0.015, 0.470),
    "ankle": (0.182, 0.058, 0.082),
    "ball": (0.240, -0.072, 0.025),
    "toe": (0.245, -0.140, 0.020),
}
FINGERS = ("index", "middle", "ring", "pinky")

FRONT, BACK, UP, DOWN = (0, -1, 0), (0, 1, 0), (0, 0, 1), (0, 0, -1)


def V(p):
    return Vector(p)


def lerp(a, b, t):
    return V(a).lerp(V(b), t)


def palm_normal():
    """Unit vector out of the left palm (the side the fingers curl towards)."""
    w, i, p = V(J["wrist"]), V(J["index"][0]), V(J["pinky"][0])
    n = (i - w).cross(p - w).normalized()
    return -n if n.x > 0 else n       # the left palm faces the thigh (-X)


# ---------------------------------------------------------------------------
# Skeleton definition
#   (name, head, tail, parent, connected, roll hint = direction of the bone's +Z)
# Rotation about local +X swings the tail towards +Z, so each Z hint points where
# that joint flexes: +X is flexion everywhere (curl, bend forward, open the jaw).
# ---------------------------------------------------------------------------
def skeleton_spec():
    pn = tuple(palm_normal())
    # The thumb curls across the palm towards the little finger.
    thumb_z = tuple((V(pn) * 0.55 + V(BACK) * 0.85).normalized())
    s = [
        ("root", (0, 0, 0), (0, 0.25, 0), None, False, UP),
        ("hips", J["hips"], J["spine_01"], "root", False, FRONT),
        ("spine_01", J["spine_01"], J["spine_02"], "hips", True, FRONT),
        ("spine_02", J["spine_02"], J["spine_03"], "spine_01", True, FRONT),
        ("spine_03", J["spine_03"], J["neck"], "spine_02", True, FRONT),
        ("neck", J["neck"], J["head"], "spine_03", True, FRONT),
        ("head", J["head"], J["head_top"], "neck", True, FRONT),
        ("jaw", J["jaw"], J["chin"], "head", False, DOWN),
        ("eye_L", None, None, "head", False, DOWN),          # placed from the eyeball mesh
        ("clavicle_L", J["clavicle"], J["shoulder"], "spine_03", False, UP),
        ("upperarm_L", J["shoulder"], J["elbow"], "clavicle_L", False, FRONT),
        ("forearm_L", J["elbow"], J["wrist"], "upperarm_L", True, FRONT),
        ("forearm_twist_L", lerp(J["elbow"], J["wrist"], 0.5), J["wrist"], "forearm_L", False, FRONT),
        ("hand_L", J["wrist"], J["middle"][0], "forearm_L", True, pn),
    ]
    for f in FINGERS:
        ch = J[f]
        s.append(("palm_%s_L" % f, lerp(J["wrist"], ch[0], 0.2), ch[0], "hand_L", False, pn))
        parent = "palm_%s_L" % f
        for k in range(3):
            name = "%s_%02d_L" % (f, k + 1)
            s.append((name, ch[k], ch[k + 1], parent, True, pn))
            parent = name
    th = J["thumb"]
    s += [
        ("thumb_01_L", th[0], th[1], "hand_L", False, thumb_z),
        ("thumb_02_L", th[1], th[2], "thumb_01_L", True, thumb_z),
        ("thumb_03_L", th[2], th[3], "thumb_02_L", True, thumb_z),
        ("thigh_L", J["hip"], J["knee"], "hips", False, FRONT),
        ("shin_L", J["knee"], J["ankle"], "thigh_L", True, BACK),
        ("foot_L", J["ankle"], J["ball"], "shin_L", True, DOWN),
        ("toe_L", J["ball"], J["toe"], "foot_L", True, DOWN),
    ]
    return s


# Rotation mode and Limit Rotation ranges (degrees, left side, local axes).
# None = free, (0, 0) = locked. Bones not listed use quaternions and no limits.
# The right side mirrors these: X is unchanged, Y and Z are negated.
LIMITS = {
    "jaw": {"x": (-3, 30), "y": (0, 0), "z": (-8, 8)},
    "eye": {"x": (-30, 25), "y": (0, 0), "z": (-35, 35)},
    "clavicle": {"x": (-15, 35), "y": (-10, 10), "z": (-20, 20)},
    "forearm": {"x": (-20, 135), "y": (0, 0), "z": (0, 0)},
    "hand": {"x": (-70, 80), "y": (-85, 85), "z": (-35, 25)},
    "palm_index": {"x": (-5, 10), "y": (-5, 5), "z": (-8, 8)},
    "palm_middle": {"x": (-5, 10), "y": (-5, 5), "z": (-5, 5)},
    "palm_ring": {"x": (-5, 20), "y": (-10, 10), "z": (-10, 10)},
    "palm_pinky": {"x": (-5, 30), "y": (-15, 15), "z": (-12, 12)},
    "finger_01": {"x": (-30, 95), "y": (-5, 5), "z": (-25, 25)},
    "finger_02": {"x": (-5, 110), "y": (0, 0), "z": (0, 0)},
    "finger_03": {"x": (-15, 85), "y": (0, 0), "z": (0, 0)},
    "thumb_01": {"x": (-30, 50), "y": (-40, 40), "z": (-40, 45)},
    "thumb_02": {"x": (-15, 65), "y": (-10, 10), "z": (-10, 10)},
    "thumb_03": {"x": (-25, 85), "y": (0, 0), "z": (0, 0)},
    "shin": {"x": (-5, 150), "y": (0, 0), "z": (0, 0)},
    "foot": {"x": (-45, 50), "y": (-15, 15), "z": (-25, 25)},     # -45: deep squats
    "toe": {"x": (-40, 60), "y": (0, 0), "z": (0, 0)},
}
EULER_ORDER = "XZY"   # twist (Y) outermost, then side-to-side (Z), then flexion (X)


def limit_key(bone):
    base = bone[:-2] if bone.endswith(("_L", "_R")) else bone
    for f in FINGERS:
        if base.startswith(f + "_"):
            return "finger" + base[len(f):]
    return base


def side_limits(bone):
    lim = LIMITS.get(limit_key(bone))
    if lim is None:
        return None
    if not bone.endswith("_R"):
        return dict(lim)
    out = {"x": lim["x"]}
    for ax in ("y", "z"):
        lo, hi = lim[ax]
        out[ax] = (-hi, -lo)
    return out


# What each local axis does, for the summary and the bones' glTF extras.
AXES = {
    "hips": "whole body about the pelvis: +X tip forward, +Z lean to his right, +Y turn to his left (quaternion)",
    "spine": "+X bend forward, +Z lean to his right, +Y turn to his left (quaternion)",
    "neck": "+X nod forward, +Z tilt to his right, +Y turn to his left (quaternion)",
    "head": "+X nod forward, +Z tilt to his right, +Y turn to his left (quaternion)",
    "jaw": "+X open, +Z chin to his right",
    "eye": "+X look down, +Z look to his right (same on both eyes)",
    "clavicle": "+X shrug up, +Z pull back (L) / forward (R)",
    "upperarm": "+X swing forward, +Z raise out to the side (L) / lower (R), Y twist (quaternion)",
    "forearm": "+X bend the elbow (hinge only)",
    "forearm_twist": "driven: copies the hand's Y (pronation) to spread it along the forearm",
    "hand": "+X flex palm-ward, +Y pronate (L) / supinate (R), +Z radial deviation (L) / ulnar (R)",
    "palm": "+X cup the palm (metacarpal), Z fan",
    "finger_01": "+X curl at the knuckle, +Z spread towards the thumb (L) / away (R)",
    "finger_02": "+X curl (middle joint, hinge)",
    "finger_03": "+X curl (end joint, hinge)",
    "thumb_01": "+X across the palm, +Z away from the palm (L) / towards it (R), Y opposition twist",
    "thumb_02": "+X curl (middle joint)",
    "thumb_03": "+X curl (end joint, hinge)",
    "thigh": "+X swing forward, +Z swing out (L) / in (R), Y twist (quaternion)",
    "shin": "+X bend the knee (hinge only)",
    "foot": "+X point the toes down, +Z toes in (L) / out (R), Y roll the sole",
    "toe": "+X curl the toes down",
}


def axes_key(bone):
    k = limit_key(bone)
    if k.startswith("spine"):
        return "spine"
    if k.startswith("palm"):
        return "palm"
    return k


# ---------------------------------------------------------------------------
# Build: the source body is athletic. SLIM pulls each region in along its normals
# (metres) and SOFTEN blends muscle definition towards a smoothed copy, giving a
# medium-to-thin build. Head, hands, feet, glutes and crotch are left alone.
# ---------------------------------------------------------------------------
SLIM = {"hips": 0.0015, "spine_01": 0.003, "spine_02": 0.005, "spine_03": 0.007, "neck": 0.003,
        "clavicle": 0.009, "upperarm": 0.007, "forearm": 0.003, "thigh": 0.005, "shin": 0.003}
SOFTEN = {"spine_02": 0.35, "spine_03": 0.5, "clavicle": 0.5, "upperarm": 0.45, "forearm": 0.2,
          "thigh": 0.2, "neck": 0.3}


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------
def setup_scene():
    sc = bpy.context.scene
    if bpy.data.scenes.get(SCENE) is None:
        sc.name = SCENE
    sc = bpy.data.scenes[SCENE]
    if bpy.context.window:
        bpy.context.window.scene = sc
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    # Wipe this character (and anything left from the factory scene).
    old = bpy.data.collections.get(COLL)
    doomed = set(old.all_objects) if old else set()
    factory = bpy.data.collections.get("Collection")     # --factory-startup's cube, light, camera
    if factory and {o.name for o in factory.objects} <= {"Cube", "Light", "Camera"}:
        doomed |= set(factory.objects)
        bpy.data.collections.remove(factory)
    for o in doomed:
        bpy.data.objects.remove(o, do_unlink=True)
    for c in (COLL, "WGT_" + NAME):
        if bpy.data.collections.get(c):
            bpy.data.collections.remove(bpy.data.collections[c])
    for block in (bpy.data.meshes, bpy.data.armatures, bpy.data.materials, bpy.data.actions):
        for d in [d for d in block if d.users == 0]:
            block.remove(d)
    coll = LC.collection(COLL, sc.collection)
    return sc, coll


# ---------------------------------------------------------------------------
# Import and scale
# ---------------------------------------------------------------------------
def import_source(coll):
    path = LC.ensure_bundle(ASSETS_DIR)
    names = [SRC_BODY, *SRC_EYES, SRC_JAW]
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        missing = [n for n in names if n not in src.objects]
        assert not missing, "bundle is missing %s" % missing
        dst.objects = names
    body, eye_l, eye_r, jaw = dst.objects
    for o in dst.objects:
        coll.objects.link(o)
    bpy.context.view_layer.update()      # appended children have stale world matrices

    # One transform for everything: body centred on X/Y, soles on Z=0, scaled to HEIGHT.
    co = LC.get_co(body.data)
    zmin, zmax = co[:, 2].min(), co[:, 2].max()
    s = HEIGHT / (zmax - zmin)
    bx = body.matrix_world.translation.x
    M = Matrix.Scale(s, 4) @ Matrix.Translation((-bx, 0, -zmin))
    M_body = M @ body.matrix_world
    mw_eyes = [e.matrix_world.copy() for e in (eye_l, eye_r)]
    for e in (eye_l, eye_r):
        e.parent = None
    # transform_apply (unlike mesh.transform) also scales the multires displacements.
    body.matrix_world = M_body
    with bpy.context.temp_override(active_object=body, object=body, selected_objects=[body],
                                   selected_editable_objects=[body]):
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for mr in [m for m in body.modifiers if m.type == "MULTIRES"]:
        mr.name = "Multires"
    for e, mw in zip((eye_l, eye_r), mw_eyes):
        e.data.transform(M @ mw)
        e.matrix_world = Matrix.Identity(4)
    body.name = BODY
    body.data.name = BODY
    eye_l.name, eye_r.name = "_src_eye_L", "_src_eye_R"
    jaw.name = "_src_jaw"

    co = LC.get_co(body.data)
    for idx, z in ((V_UPPER_LIP, 1.606), (V_LOWER_LIP, 1.606)):
        assert abs(co[idx, 0]) < 1e-3 and abs(co[idx, 2] - z) < 0.004, \
            "lip landmark %d moved: %s (bundle version changed?)" % (idx, co[idx])
    return body, eye_l, eye_r, jaw, s


def region_weights(co, segments, sigma=0.02):
    """Soft assignment of vertices to named segments: (names, weights (N, S))."""
    names = [n for n, _, _ in segments]
    D = np.stack([LC.seg_dist(co, a, b)[0] for _, a, b in segments], axis=1)
    W = np.exp(-((D - D.min(1, keepdims=True)) / sigma) ** 2)
    return names, W / W.sum(1, keepdims=True)


def body_segments():
    """Deform-bone segments (both sides) keyed by region name, for the build steps."""
    segs = []
    for name, h, t, *_ in skeleton_spec():
        if h is None or name == "root":
            continue
        region = name[:-2] if name.endswith("_L") else name
        region = "forearm" if region == "forearm_twist" else region
        segs.append((region, V(h), V(t)))
        if name.endswith("_L"):
            m = Vector((-1, 1, 1))
            segs.append((region, V(h) * m, V(t) * m))
    return segs


def laplacian_smooth(me, co, iterations=6, lam=0.5):
    ev = np.empty(len(me.edges) * 2, np.int64)
    me.edges.foreach_get("vertices", ev)
    a, b = ev[0::2], ev[1::2]
    deg = np.bincount(np.concatenate([a, b]), minlength=len(co)).astype(float)[:, None]
    out = co.copy()
    for _ in range(iterations):
        acc = np.zeros_like(out)
        np.add.at(acc, a, out[b])
        np.add.at(acc, b, out[a])
        out += lam * (acc / np.maximum(deg, 1) - out)
    return out


def slim(body):
    me = body.data
    co = LC.get_co(me)
    nrm = LC.get_normals(me)
    names, W = region_weights(co, body_segments())
    amount = W @ np.array([SLIM.get(n, 0.0) for n in names])
    soften = W @ np.array([SOFTEN.get(n, 0.0) for n in names])
    co = co - nrm * amount[:, None]
    co = co + (laplacian_smooth(me, co) - co) * soften[:, None]
    LC.set_co(me, co)
    return float(amount.max())


# ---------------------------------------------------------------------------
# Skeleton
# ---------------------------------------------------------------------------
def eye_centre(eye_ob):
    co = LC.get_co(eye_ob.data)
    return Vector(((co.max(0) + co.min(0)) / 2).tolist()), float((co.max(0) - co.min(0)).max() / 2)


def build_armature(coll, eye_l):
    arm = bpy.data.armatures.new(RIG)
    rig = bpy.data.objects.new(RIG, arm)
    coll.objects.link(rig)
    arm.display_type = "OCTAHEDRAL"
    rig.show_in_front = True

    ec, er = eye_centre(eye_l)
    spec = []
    for name, h, t, parent, conn, z in skeleton_spec():
        if name == "eye_L":
            h, t = ec, ec + Vector((0, -2.5 * er, 0))
        spec.append((name, V(h), V(t), parent, conn, V(z)))
    # Mirror every _L bone.
    full = []
    for name, h, t, parent, conn, z in spec:
        full.append((name, h, t, parent, conn, z))
        if name.endswith("_L"):
            m = Vector((-1, 1, 1))
            full.append((LC.mirror_name(name), h * m, t * m, LC.mirror_name(parent), conn, z * m))

    view = bpy.context.view_layer
    view.objects.active = rig
    with bpy.context.temp_override(active_object=rig, object=rig, selected_objects=[rig]):
        bpy.ops.object.mode_set(mode="EDIT")
        ebs = arm.edit_bones
        for name, h, t, parent, conn, z in full:
            eb = ebs.new(name)
            eb.head, eb.tail = h, t
            eb.align_roll(z)
        for name, h, t, parent, conn, z in full:
            if parent:
                ebs[name].parent = ebs[parent]
                ebs[name].use_connect = conn
        add_controls(ebs)
        bpy.ops.object.mode_set(mode="OBJECT")
    return rig


CONTROL_BONES = []   # filled by add_controls: (name, kind)


def add_controls(ebs):
    """IK targets and poles (non-deforming) for arms and legs."""
    CONTROL_BONES.clear()
    for side in ("L", "R"):
        for tgt, src, pole, joint, off in (("ik_hand", "hand", "pole_elbow", "forearm", (0, 0.35, 0)),
                                           ("ik_foot", "foot", "pole_knee", "shin", (0, -0.5, 0))):
            s = ebs["%s_%s" % (src, side)]
            eb = ebs.new("%s_%s" % (tgt, side))
            eb.head, eb.tail, eb.roll = s.head, s.tail, s.roll
            eb.parent = ebs["root"]
            p = ebs.new("%s_%s" % (pole, side))
            p.head = ebs["%s_%s" % (joint, side)].head + Vector(off)
            p.tail = p.head + Vector((0, 0, 0.06))
            p.parent = ebs["root"]
            CONTROL_BONES.extend([(eb.name, "ik"), (p.name, "pole")])
    for name, _ in CONTROL_BONES:
        ebs[name].use_deform = False


# ---------------------------------------------------------------------------
# Skin weights
# ---------------------------------------------------------------------------
NO_HEAT = ("root", "jaw", "eye_L", "eye_R")   # weighted by hand below, never by heat


def select_only(objs, active):
    view = bpy.context.view_layer
    for o in view.objects:
        o.select_set(o in objs)
    view.objects.active = active


def skin(body, rig):
    """Heat weights from every deforming bone except NO_HEAT, Armature before Multires."""
    bones = rig.data.bones
    for n in NO_HEAT:
        bones[n].use_deform = False
    select_only([body, rig], rig)
    with bpy.context.temp_override(active_object=rig, object=rig, selected_objects=[body, rig],
                                   selected_editable_objects=[body, rig]):
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    for n in NO_HEAT:
        bones[n].use_deform = True
    mod = next(m for m in body.modifiers if m.type == "ARMATURE")
    mod.name = "Armature"
    body.modifiers.move(body.modifiers.find("Armature"), 0)
    empty = [b.name for b in bones if b.use_deform and b.name not in NO_HEAT
             and b.name not in body.vertex_groups]
    assert not empty, "heat weighting left bones without weights: %s" % empty


def lip_margins(me):
    """The two lip-margin edge loops (upper, lower) as vertex-index lists running from
    the left mouth corner through the midline to the right corner."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()

    def walk(i0, sign):
        v = bm.verts[i0]
        e = max(v.link_edges, key=lambda e: sign * e.other_vert(v).co.x)
        out = [v.index]
        v = e.other_vert(v)
        for _ in range(40):
            out.append(v.index)
            faces = set(e.link_faces)
            nxt = [x for x in v.link_edges if x is not e and not (set(x.link_faces) & faces)]
            if len(v.link_edges) != 4 or len(nxt) != 1:
                break
            e = nxt[0]
            if sign * e.other_vert(v).co.x < sign * v.co.x:
                break
            v = e.other_vert(v)
        return out

    loops = [walk(i, 1)[::-1] + walk(i, -1)[1:] for i in (V_UPPER_LIP, V_LOWER_LIP)]
    bm.free()
    return loops


def lip_line(me):
    """(x, z) samples of where the lips meet, midline to corner. Returns (xs, zs, corner_x)."""
    co = LC.get_co(me)
    up, lo = (co[[i for i in loop if co[i, 0] >= 0]] for loop in lip_margins(me))
    up, lo = up[np.argsort(up[:, 0])], lo[np.argsort(lo[:, 0])]
    corner = float(min(up[-1, 0], lo[-1, 0]))
    xs = np.linspace(0, corner, 12)
    zs = (np.interp(xs, up[:, 0], up[:, 2]) + np.interp(xs, lo[:, 0], lo[:, 2])) / 2
    return xs, zs, corner


def mouth_frame(me):
    xs, zs, corner = lip_line(me)
    co = LC.get_co(me)
    ax = np.abs(co[:, 0])
    zc = np.interp(np.minimum(ax, corner), xs, zs)       # lip contact height under each vertex
    beyond = np.maximum(ax - corner, 0.0)
    return co, ax, zc, beyond, corner


def jaw_field(me):
    """How much each vertex follows the jaw (0..1): the lower lip, chin, the floor of the
    mouth and the lower cheeks, fading out towards the ear, the throat and the cheekbones."""
    co, ax, zc, beyond, corner = mouth_frame(me)
    y, z = co[:, 1], co[:, 2]
    u = np.minimum(ax / corner, 1.0)
    ztop = zc - 0.30 * beyond                   # the split line drops across the cheek
    # Razor sharp between the lips (they are 0.4 mm apart on the midline), widening
    # towards the corners so they stretch into an oval instead of tearing into slits.
    width = 0.0004 + 0.012 * u ** 3 + 0.5 * beyond
    low = LC.smoothstep(ztop + 0.0002 + 0.4 * (width - 0.0004), ztop - width, z)
    back = LC.smoothstep(-0.035, -0.080, y)     # nothing behind the jaw hinge
    throat = LC.smoothstep(1.505, 1.560, z)     # under the chin, fading into the neck
    side = LC.smoothstep(0.085, 0.060, ax)
    return low * back * throat * side


def fix_weights(body, rig):
    """Forearm twist gradient, the jaw, and at most four influences per vertex."""
    names, W = LC.read_weights(body)
    for n in ("jaw",):
        if n not in names:
            names.append(n)
            W = np.hstack([W, np.zeros((len(W), 1))])
    col = {n: i for i, n in enumerate(names)}
    co = LC.get_co(body.data)
    bones = rig.data.bones
    # Forearm: all of it shared between forearm and forearm_twist, ramping from the
    # elbow (no twist) to the wrist (full twist).
    for side in "LR":
        f, t = col["forearm_" + side], col["forearm_twist_" + side]
        b = bones["forearm_" + side]
        _, u = LC.seg_dist(co, b.head_local, b.tail_local)
        total = W[:, f] + W[:, t]
        ramp = LC.smoothstep(0.1, 0.95, u)
        W[:, t] = total * ramp
        W[:, f] = total * (1 - ramp)
    # Jaw: taken from the head and neck.
    J = jaw_field(body.data)
    take = W[:, col["head"]] + W[:, col["neck"]]
    W[:, col["jaw"]] = J * take
    W[:, col["head"]] *= 1 - J
    W[:, col["neck"]] *= 1 - J
    LC.write_weights(body, names, W, max_influences=4)


# ---------------------------------------------------------------------------
# Mouth parts and eyes (separate skinned meshes)
# ---------------------------------------------------------------------------
TEETH_SCALE = 0.85
INCISOR_Y = -0.146       # front of the upper incisors, just behind the lips
TEETH_DROP = 0.0015      # incisor edges this far below the lip line, so they show when talking


def rigid_skin(ob, rig, groups):
    """groups: {group name: vertex indices}. Adds an Armature modifier and parents to rig."""
    ob.vertex_groups.clear()
    for name, idx in groups.items():
        g = ob.vertex_groups.new(name=name)
        g.add([int(i) for i in idx], 1.0, "REPLACE")
    ob.parent = rig
    m = ob.modifiers.new("Armature", "ARMATURE")
    m.object = rig


def islands(me):
    """Vertex island id per vertex."""
    ev = np.empty(len(me.edges) * 2, np.int64)
    me.edges.foreach_get("vertices", ev)
    parent = np.arange(len(me.vertices))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in ev.reshape(-1, 2):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return np.array([find(i) for i in range(len(parent))])


def build_mouth(coll, src, rig, zc_mid):
    """Teeth and gums from the bundle's realistic jaw, plus a simple tongue."""
    import bmesh
    me = src.data
    occlusal = -0.001                     # between the upper and lower incisors (source units)
    # The gums are one piece: cut them exactly along the occlusal plane. Teeth stay whole.
    isl = islands(me)
    big = set(np.nonzero(np.bincount(isl) >= 400)[0])
    bm = bmesh.new()
    bm.from_mesh(me)
    gum = [f for f in bm.faces if isl[f.verts[0].index] in big]
    geom = list({v for f in gum for v in f.verts}) + list({e for f in gum for e in f.edges}) + gum
    res = bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-6, plane_co=(0, 0, occlusal), plane_no=(0, 0, 1))
    cut = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)]
    bmesh.ops.split_edges(bm, edges=cut)
    bm.to_mesh(me)
    bm.free()
    co = LC.get_co(me)
    # Place: incisors just behind the lips, their edges a little below the lip line.
    front = co[:, 1].min()
    M = (Matrix.Translation((0, INCISOR_Y, zc_mid - TEETH_DROP)) @ Matrix.Scale(TEETH_SCALE, 4)
         @ Matrix.Translation((0, -front, -occlusal)))
    me.transform(M)
    src.matrix_world = Matrix.Identity(4)

    # Tongue: a flattened, slightly pointed sphere resting on the floor of the mouth.
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=20, v_segments=10, radius=1.0)
    for v in bm.verts:
        x, y, z = v.co
        taper = 1.0 - 0.35 * max(0.0, -y)          # narrower towards the tip (-Y)
        v.co = Vector((x * 0.019 * taper, y * 0.038, z * (0.008 if z > 0 else 0.006)))
        v.co += Vector((0, -0.097, zc_mid - 0.013))
    tongue_me = bpy.data.meshes.new("_tongue")
    bm.to_mesh(tongue_me)
    bm.free()
    n_teeth = len(me.vertices)
    tongue = bpy.data.objects.new("_tongue", tongue_me)
    coll.objects.link(tongue)
    select_only([src, tongue], src)
    with bpy.context.temp_override(active_object=src, object=src, selected_objects=[src, tongue],
                                   selected_editable_objects=[src, tongue]):
        bpy.ops.object.join()
    ob = src
    ob.name = ob.data.name = MOUTH
    me = ob.data
    co = LC.get_co(me)
    isl = islands(me)
    sizes = np.bincount(isl, minlength=len(isl))[isl]
    is_tongue = np.arange(len(co)) >= n_teeth
    is_tooth = (~is_tongue) & (sizes < 400)
    # Whole pieces go to the head or the jaw by their centre height.
    zsum = np.bincount(isl, weights=co[:, 2], minlength=len(isl))
    zmid = (zsum / np.maximum(np.bincount(isl, minlength=len(isl)), 1))[isl]
    upper = (~is_tongue) & (zmid > zc_mid - TEETH_DROP)
    rigid_skin(ob, rig, {"head": np.nonzero(upper)[0], "jaw": np.nonzero(~upper)[0]})
    me.materials.clear()
    for n in ("MAT_gums", "MAT_teeth", "MAT_tongue"):
        me.materials.append(material(n))
    kind = np.where(is_tongue, 2, np.where(is_tooth, 1, 0))
    for p in me.polygons:
        p.material_index = int(kind[p.vertices[0]])
        p.use_smooth = True
    return ob


IRIS_DEG, PUPIL_DEG = 29.0, 11.0     # angular radius from the front of the eyeball


def build_eyes(coll, eye_l, eye_r, rig):
    select_only([eye_l, eye_r], eye_l)
    with bpy.context.temp_override(active_object=eye_l, object=eye_l, selected_objects=[eye_l, eye_r],
                                   selected_editable_objects=[eye_l, eye_r]):
        bpy.ops.object.join()
    ob = eye_l
    ob.name = ob.data.name = EYES
    import bmesh

    def front_angle(co):
        ang = np.zeros(len(co))
        for sgn in (1, -1):
            idx = np.nonzero(co[:, 0] * sgn > 0)[0]
            e = co[idx]
            c = (e.max(0) + e.min(0)) / 2
            d = (e - c) / np.linalg.norm(e - c, axis=1, keepdims=True)
            ang[idx] = np.degrees(np.arccos(np.clip(-d[:, 1], -1, 1)))    # from straight ahead (-Y)
        return ang

    # Finer rings only on the front cap, so the pupil and iris edges come out round.
    ang = front_angle(LC.get_co(ob.data))
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    cap = [e for e in bm.edges if all(ang[v.index] < IRIS_DEG + 12 for v in e.verts)]
    bmesh.ops.subdivide_edges(bm, edges=cap, cuts=2, use_grid_fill=True, smooth=1.0)
    bm.to_mesh(ob.data)
    bm.free()
    co = LC.get_co(ob.data)
    ang = front_angle(co)
    kind = np.where(ang < PUPIL_DEG, 2, np.where(ang < IRIS_DEG, 1, 0))
    rigid_skin(ob, rig, {"eye_L": np.nonzero(co[:, 0] > 0)[0], "eye_R": np.nonzero(co[:, 0] < 0)[0]})
    me = ob.data
    me.materials.clear()
    for n in ("MAT_eye_white", "MAT_iris", "MAT_pupil"):
        me.materials.append(material(n))
    for p in me.polygons:
        k = kind[list(p.vertices)]
        p.material_index = int(np.bincount(k).argmax())
        p.use_smooth = True
    return ob


# ---------------------------------------------------------------------------
# Materials. Plain Principled BSDFs: placeholders the game can swap, and they map
# straight onto glTF PBR. The body's mouth interior gets its own slot.
# ---------------------------------------------------------------------------
MATERIALS = {
    "MAT_skin": ((0.78, 0.58, 0.48), 0.55),
    "MAT_mouth": ((0.36, 0.11, 0.12), 0.60),
    "MAT_teeth": ((0.88, 0.85, 0.76), 0.30),
    "MAT_gums": ((0.70, 0.30, 0.32), 0.50),
    "MAT_tongue": ((0.66, 0.27, 0.29), 0.60),
    "MAT_eye_white": ((0.90, 0.88, 0.84), 0.15),
    "MAT_iris": ((0.22, 0.26, 0.20), 0.20),
    "MAT_pupil": ((0.02, 0.02, 0.02), 0.10),
}
V_PALATE = 7996          # a vertex on the roof of the mouth, for the interior flood fill


def material(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    col, rough = MATERIALS[name]
    m.diffuse_color = (*col, 1.0)
    m.roughness = rough
    if m.node_tree is None:           # new materials already have nodes in Blender 5
        m.use_nodes = True
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (*col, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    return m


def mouth_interior_faces(me):
    """Faces inside the mouth: flood fill from the palate, stopped by the lip margins."""
    import bmesh
    up, lo = lip_margins(me)
    barrier = set()
    for loop in (up, lo):
        barrier |= {frozenset(p) for p in zip(loop, loop[1:])}
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    # The loops stop just short of each other at the corners: close the ring with the
    # shortest edge path between their ends.
    for a, b in ((up[0], lo[0]), (up[-1], lo[-1])):
        prev, frontier = {a: None}, [a]
        while b not in prev:
            nxt = []
            for i in frontier:
                for e in bm.verts[i].link_edges:
                    j = e.other_vert(bm.verts[i]).index
                    if j not in prev:
                        prev[j] = i
                        nxt.append(j)
            frontier = nxt
        j = b
        while prev[j] is not None:
            barrier.add(frozenset((j, prev[j])))
            j = prev[j]
    start = bm.verts[V_PALATE].link_faces[0]
    seen, stack = {start.index}, [start]
    while stack:
        f = stack.pop()
        for e in f.edges:
            if frozenset(v.index for v in e.verts) in barrier:
                continue
            for g in e.link_faces:
                if g.index not in seen:
                    seen.add(g.index)
                    stack.append(g)
    bm.free()
    assert len(seen) < 1500, "mouth flood fill leaked past the lips (%d faces)" % len(seen)
    return seen


def body_materials(body):
    me = body.data
    me.materials.clear()
    me.materials.append(material("MAT_skin"))
    me.materials.append(material("MAT_mouth"))
    inside = mouth_interior_faces(me)
    idx = np.zeros(len(me.polygons), np.int32)
    idx[list(inside)] = 1
    me.polygons.foreach_set("material_index", idx)
    return len(inside)


# ---------------------------------------------------------------------------
# Shape keys. Mouth shapes are lip-only: the jaw bone does the opening, so a talking
# character drives jaw rotation plus a mix of these. Blinks are per eye.
#   mouth_wide   EE / I / S: corners out and back
#   mouth_round  OO / W / O: corners in, lips pushed forward into a funnel
#   mouth_press  M / B / P: lips pressed together and rolled in
#   mouth_fv     F / V: lower lip tucked up and back under the upper teeth
#   lip_upper_up shows the upper teeth (TH, CH, snarl)
#   mouth_smile  corners up and out, cheeks lifted
# ---------------------------------------------------------------------------
MOUTH_KEYS = ("mouth_wide", "mouth_round", "mouth_press", "mouth_fv", "lip_upper_up", "mouth_smile")
BLINK_KEYS = ("blink_L", "blink_R")


def mouth_deltas(me):
    co, ax, zc, beyond, corner = mouth_frame(me)
    x, y, z = co[:, 0], co[:, 1], co[:, 2]
    sx = np.sign(x)
    au = np.minimum(ax / corner, 1.0)
    dz = z - zc
    # Upper/lower lip split: the same blend as the jaw uses around the lips.
    w = 0.0004 + 0.012 * au ** 3
    lower = LC.smoothstep(zc + 0.0002 + 0.4 * (w - 0.0004), zc - w, z)
    upper = 1.0 - lower
    front = LC.smoothstep(-0.105, -0.135, y)         # the lips and the mouth's entrance

    def area(sx_, sz_):
        """Falloff away from the lip line: sx_ past the corners, sz_ up/down."""
        return np.exp(-(beyond / sx_) ** 2 - (dz / sz_) ** 2) * front

    lips = area(0.008, 0.009)
    near = area(0.016, 0.018)
    wide = area(0.022, 0.022)
    D = {}
    d = np.zeros_like(co)
    d[:, 0] = sx * 0.007 * au ** 1.3 * wide
    d[:, 1] = 0.003 * au ** 2 * wide
    D["mouth_wide"] = d
    d = np.zeros_like(co)
    d[:, 0] = -sx * 0.010 * au * near
    d[:, 1] = -0.007 * (1 - 0.4 * au ** 2) * near
    d[:, 2] = 0.0016 * (1 - au ** 2) * lips * (upper - lower)
    D["mouth_round"] = d
    d = np.zeros_like(co)
    d[:, 1] = 0.003 * lips
    d[:, 2] = 0.0012 * (1 - au ** 2) * lips * (lower - upper)
    D["mouth_press"] = d
    d = np.zeros_like(co)
    d[:, 1] = 0.005 * lower * lips * (1 - 0.5 * au ** 2)
    d[:, 2] = (0.0035 * lower + 0.001 * upper) * lips * (1 - 0.5 * au ** 2)
    D["mouth_fv"] = d
    d = np.zeros_like(co)
    raise_ = upper * np.exp(-(beyond / 0.008) ** 2 - (np.maximum(dz, 0) / 0.016) ** 2) * front
    d[:, 2] = 0.0032 * (1 - 0.6 * au ** 2) * raise_
    d[:, 1] = -0.001 * raise_
    D["lip_upper_up"] = d
    d = np.zeros_like(co)
    cheek = np.exp(-((ax - 0.040) / 0.014) ** 2 - ((dz - 0.018) / 0.014) ** 2) * LC.smoothstep(-0.07, -0.11, y)
    d[:, 0] = sx * 0.004 * au ** 2 * wide
    d[:, 1] = 0.003 * au ** 2 * wide
    d[:, 2] = 0.006 * au ** 2 * wide + 0.002 * cheek
    D["mouth_smile"] = d
    return D


def blink_deltas(me, eyes_ob):
    """Upper lid rotates down over the eyeball (about the eye centre), lower lid up a little."""
    co = LC.get_co(me)
    ec = LC.get_co(eyes_ob.data)
    out = {}
    for side, sgn in (("L", 1), ("R", -1)):
        e = ec[ec[:, 0] * sgn > 0]
        c = (e.max(0) + e.min(0)) / 2
        r = float((e.max(0) - e.min(0)).max() / 2)
        v = co - c
        d = np.linalg.norm(v, axis=1)
        th = np.degrees(np.arctan2(v[:, 2], -v[:, 1]))
        band = (np.abs(v[:, 0]) < 0.006) & (d < r + 0.003) & (v[:, 1] < -0.3 * r)
        th_u = th[band & (v[:, 2] > 0)].min()
        th_l = th[band & (v[:, 2] < 0)].max()
        th_mid = (th_u + th_l) / 2
        th_close = th_l + 0.2 * (th_u - th_l)
        hw = 1.2 * r
        g = np.sqrt(np.clip(1 - (v[:, 0] / hw) ** 2, 0, 1))
        lat = LC.smoothstep(1.3 * hw, 1.0 * hw, np.abs(v[:, 0]))
        near = LC.smoothstep(r + 0.013, r + 0.002, d) * lat
        w_up = near * LC.smoothstep(th_mid - 4, th_mid + 4, th)
        w_lo = near * LC.smoothstep(th_mid + 4, th_mid - 4, th) * LC.smoothstep(r + 0.008, r + 0.002, d)
        alpha = np.radians(-(th_u - th_close) * g * w_up + (th_close - th_l) * g * w_lo)
        f, zz = -v[:, 1], v[:, 2]
        f2 = f * np.cos(alpha) - zz * np.sin(alpha)
        z2 = f * np.sin(alpha) + zz * np.cos(alpha)
        nv = np.stack([v[:, 0], -f2, z2], axis=1)
        # keep the moving lid just outside the eyeball, or it would slide underneath it
        moved = np.clip(np.abs(alpha) / max(np.abs(alpha).max(), 1e-9), 0, 1)
        nd = np.linalg.norm(nv, axis=1)
        push = np.maximum(r + 0.0007 - nd, 0) * moved * (f2 > 0)
        nv += nv / np.maximum(nd, 1e-9)[:, None] * push[:, None]
        out["blink_" + side] = nv - v
    return out


def shape_keys(body, eyes):
    me = body.data
    body.shape_key_add(name="Basis", from_mix=False)
    base = LC.get_co(me)
    deltas = {**mouth_deltas(me), **blink_deltas(me, eyes)}
    for name in MOUTH_KEYS + BLINK_KEYS:
        kb = body.shape_key_add(name=name, from_mix=False)
        kb.data.foreach_set("co", (base + deltas[name]).ravel())
        kb.slider_min, kb.slider_max = 0.0, 1.0
        kb.value = 0.0                   # new keys come in at 1.0
    body.active_shape_key_index = 0
    me.shape_keys.name = "SK_" + NAME
    return list(deltas)


# ---------------------------------------------------------------------------
# Controls: rotation modes, joint limits, forearm twist, IK with IK/FK sliders,
# bone collections and colours. Limits and axis notes are also written onto each
# deform bone as custom properties, which the glTF exporter keeps as node extras.
# ---------------------------------------------------------------------------
IK_PROPS = {"ik_arm_L": "arm", "ik_arm_R": "arm", "ik_leg_L": "leg", "ik_leg_R": "leg"}
BONE_GROUPS = [   # (collection, colour palette, predicate on bone name)
    ("IK", "THEME01", lambda n: n.startswith(("ik_", "pole_"))),
    ("Face", "THEME03", lambda n: n in ("jaw", "eye_L", "eye_R")),
    ("Fingers", "THEME04", lambda n: n.startswith(("palm_", "thumb_", "index_", "middle_", "ring_", "pinky_"))),
    ("Mechanism", "THEME08", lambda n: "twist" in n),
    ("Body", "DEFAULT", lambda n: True),
]


def signed_angle(u, v, normal):
    a = u.angle(v)
    return -a if u.cross(v).angle(normal) < 1 else a


def pole_angle(base, tip, pole_loc):
    """IK pole angle that keeps the chain in its rest pose (base, tip: data bones)."""
    h, t = base.head_local, tip.tail_local
    pole_normal = (t - h).cross(pole_loc - h)
    projected = pole_normal.cross(base.tail_local - h)
    return signed_angle(base.matrix_local.col[0].xyz, projected, base.tail_local - h)


def drive(target_owner, path, rig, prop):
    fc = target_owner.driver_add(path)
    d = fc.driver
    d.type = "AVERAGE"
    v = d.variables.new()
    v.type = "SINGLE_PROP"
    v.targets[0].id_type = "OBJECT"
    v.targets[0].id = rig
    v.targets[0].data_path = '["%s"]' % prop


def widgets():
    """Wireframe shapes for the IK controls, in a hidden top-level collection."""
    import bmesh
    wc = LC.collection("WGT_" + NAME, bpy.context.scene.collection)
    out = {}
    for name, make in (("cube", lambda bm: bmesh.ops.create_cube(bm, size=1.0)),
                       ("sphere", lambda bm: bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=6, radius=0.5))):
        full = "WGT_%s_%s" % (NAME, name)
        me = bpy.data.meshes.new(full)
        bm = bmesh.new()
        make(bm)
        bm.to_mesh(me)
        bm.free()
        me.polygons.foreach_set("hide", [False] * len(me.polygons))
        ob = bpy.data.objects.new(full, me)
        wc.objects.link(ob)
        out[name] = ob
    wc.hide_render = True
    bpy.context.view_layer.layer_collection.children[wc.name].exclude = True
    return out


def setup_controls(rig):
    arm, pose = rig.data, rig.pose
    for prop, what in IK_PROPS.items():
        rig[prop] = 0.0
        rig.id_properties_ui(prop).update(min=0.0, max=1.0, soft_min=0.0, soft_max=1.0,
                                          description="0 = FK, 1 = IK for the %s %s" % (prop[-1], what))

    for pb in pose.bones:
        n = pb.name
        lim = side_limits(n)
        pb.lock_scale = (True, True, True) if n != "root" else (False, False, False)
        movable = n in ("root", "hips") or n.startswith(("ik_", "pole_"))
        pb.lock_location = (not movable,) * 3
        if lim is None:
            pb.rotation_mode = "QUATERNION"
        else:
            pb.rotation_mode = EULER_ORDER
            c = pb.constraints.new("LIMIT_ROTATION")
            c.name = "Limits"
            c.owner_space = "LOCAL"
            c.use_transform_limit = True
            for ax in "xyz":
                lo, hi = lim[ax]
                setattr(c, "use_limit_" + ax, True)
                setattr(c, "min_" + ax, math.radians(lo))
                setattr(c, "max_" + ax, math.radians(hi))
        b = arm.bones[n]
        if b.use_deform and n != "root":
            if lim is not None:
                b["limits_deg"] = {ax: list(lim[ax]) for ax in "xyz"}
                b["rotation_order"] = EULER_ORDER
            key = axes_key(n)
            if key in AXES:
                b["axes"] = AXES[key]

    for side in "LR":
        tw = pose.bones["forearm_twist_" + side]
        tw.rotation_mode = EULER_ORDER
        c = tw.constraints.new("COPY_ROTATION")
        c.name = "Twist"
        c.target, c.subtarget = rig, "hand_" + side
        c.use_x, c.use_y, c.use_z = False, True, False
        c.euler_order = EULER_ORDER
        c.owner_space = c.target_space = "LOCAL"
        for chain, tip, target, pole, prop in (("upperarm", "forearm", "ik_hand", "pole_elbow", "ik_arm"),
                                                ("thigh", "shin", "ik_foot", "pole_knee", "ik_leg")):
            tip_pb = pose.bones["%s_%s" % (tip, side)]
            tip_pb.lock_ik_y = tip_pb.lock_ik_z = True
            ik = tip_pb.constraints.new("IK")
            ik.name = "IK"
            ik.target, ik.subtarget = rig, "%s_%s" % (target, side)
            ik.pole_target, ik.pole_subtarget = rig, "%s_%s" % (pole, side)
            ik.pole_angle = pole_angle(arm.bones["%s_%s" % (chain, side)], arm.bones["%s_%s" % (tip, side)],
                                       arm.bones["%s_%s" % (pole, side)].head_local)
            ik.chain_count = 2
            ik.use_stretch = False
            drive(ik, "influence", rig, "%s_%s" % (prop, side))
            end = pose.bones["%s_%s" % ("hand" if tip == "forearm" else "foot", side)]
            cr = end.constraints.new("COPY_ROTATION")
            cr.name = "IK rotation"
            cr.target, cr.subtarget = rig, "%s_%s" % (target, side)
            drive(cr, "influence", rig, "%s_%s" % (prop, side))

    wgt = widgets()
    for pb in pose.bones:
        if pb.name.startswith("ik_"):
            pb.custom_shape = wgt["cube"]
            pb.custom_shape_scale_xyz = (0.5, 1.0, 0.5)
        elif pb.name.startswith("pole_"):
            pb.custom_shape = wgt["sphere"]
            pb.custom_shape_scale_xyz = (0.8, 0.8, 0.8)

    colls = {name: arm.collections.new(name) for name, _, _ in BONE_GROUPS}
    for b in arm.bones:
        for name, palette, pred in BONE_GROUPS:
            if pred(b.name):
                colls[name].assign(b)
                b.color.palette = palette
                break
    colls["Mechanism"].is_visible = False
    return rig


def check_ik_rest(rig):
    """Switching IK on at rest must not move anything (pole angles are right)."""
    view = bpy.context.view_layer
    names = [n for n in IK_PROPS]
    view.update()
    before = {pb.name: pb.matrix.copy() for pb in rig.pose.bones}
    for n in names:
        rig[n] = 1.0
    rig.update_tag()
    view.update()
    worst = max((before[pb.name].translation - pb.matrix.translation).length for pb in rig.pose.bones)
    for n in names:
        rig[n] = 0.0
    rig.update_tag()
    view.update()
    assert worst < 1e-3, "IK moves the rest pose by %.4f m: pole angles are off" % worst
    return worst


# ---------------------------------------------------------------------------
# Hand pose library: pose assets (Actions marked as assets) for both hands. In Pose
# Mode they appear in the asset shelf; with bones selected, only those are posed.
# Values are the left hand in degrees (x, y, z); the right hand is mirrored.
# ---------------------------------------------------------------------------
def _fingers(curls, spread=None):
    """curls: {finger: (mcp, pip, dip)}"""
    out = {}
    for f, (a, b, c) in curls.items():
        z = (spread or {}).get(f, 0)
        out["%s_01" % f], out["%s_02" % f], out["%s_03" % f] = (a, 0, z), (b, 0, 0), (c, 0, 0)
    return out


HAND_POSES = {
    "hand_relaxed": {**_fingers({"index": (8, 12, 6), "middle": (12, 16, 8), "ring": (16, 20, 10),
                                 "pinky": (20, 24, 12)}), "thumb_02": (8, 0, 0), "thumb_03": (10, 0, 0)},
    "hand_flat": {**_fingers({f: (-4, -3, -3) for f in FINGERS}), "thumb_01": (-10, 0, 10),
                  "thumb_02": (-5, 0, 0), "thumb_03": (-8, 0, 0)},
    "hand_fist": {**_fingers({"index": (80, 95, 55), "middle": (85, 95, 55), "ring": (88, 95, 55),
                              "pinky": (90, 90, 55)}), "palm_ring": (8, 0, 0), "palm_pinky": (15, 0, 0),
                  "thumb_01": (30, 20, 10), "thumb_02": (35, 0, 0), "thumb_03": (45, 0, 0)},
    "hand_point": {**_fingers({"index": (0, 0, 0), "middle": (85, 95, 55), "ring": (88, 95, 55),
                               "pinky": (90, 90, 55)}), "palm_ring": (8, 0, 0), "palm_pinky": (15, 0, 0),
                   "thumb_01": (30, 20, 10), "thumb_02": (35, 0, 0), "thumb_03": (45, 0, 0)},
    "hand_spread": {**_fingers({f: (-10, 0, 0) for f in FINGERS},
                               spread={"index": 18, "middle": 3, "ring": -12, "pinky": -25}),
                    "thumb_01": (-20, 0, 35), "thumb_02": (-10, 0, 0), "thumb_03": (-15, 0, 0)},
    "hand_grip": {**_fingers({"index": (50, 60, 30), "middle": (55, 62, 32), "ring": (58, 64, 34),
                              "pinky": (60, 64, 34)}), "palm_pinky": (8, 0, 0),
                  "thumb_01": (35, 25, 5), "thumb_02": (25, 0, 0), "thumb_03": (30, 0, 0)},
    "hand_pinch": {**_fingers({"index": (42, 45, 25), "middle": (30, 40, 20), "ring": (35, 45, 22),
                               "pinky": (40, 45, 25)}),
                   "thumb_01": (35, 30, 15), "thumb_02": (20, 0, 0), "thumb_03": (15, 0, 0)},
}


def side_values(bone, deg):
    """Left-hand degrees -> this bone's Euler (the right side negates Y and Z)."""
    x, y, z = deg
    return (x, -y, -z) if bone.endswith("_R") else (x, y, z)


def pose_library(rig):
    made = []
    for pose_name, values in HAND_POSES.items():
        act = bpy.data.actions.get(pose_name)
        if act:
            bpy.data.actions.remove(act)
        act = bpy.data.actions.new(pose_name)
        rig.animation_data_create().action = act
        # every hand bone is keyed (zero where the pose doesn't say), so poses replace each other
        hand_bones = [pb for pb in rig.pose.bones if pb.name[:-2] in HAND_KEYS and pb.name[-2:] in ("_L", "_R")]
        for pb in hand_bones:
            deg = side_values(pb.name, values.get(pb.name[:-2], (0, 0, 0)))
            for i, a in enumerate(deg):
                fc = act.fcurve_ensure_for_datablock(rig, 'pose.bones["%s"].rotation_euler' % pb.name,
                                                     index=i, group_name=pb.name)
                fc.keyframe_points.insert(1, math.radians(a))
        rig.animation_data.action = None
        act.asset_mark()
        act.asset_data.tags.new("hand")
        act.asset_data.description = "Both hands. Select bones first to pose only those."
        made.append(act.name)
    return made


HAND_KEYS = {"palm_" + f for f in FINGERS} | {"%s_%02d" % (f, k) for f in FINGERS + ("thumb",) for k in (1, 2, 3)}


# ---------------------------------------------------------------------------
# Multires, stage, text blocks
# ---------------------------------------------------------------------------
def multires_levels(body):
    """Keep levels 0-2: level 3 is the source's athletic detail (six-pack etc.)."""
    mr = body.modifiers["Multires"]
    mr.levels = mr.sculpt_levels = 2
    with bpy.context.temp_override(object=body, active_object=body):
        bpy.ops.object.multires_higher_levels_delete(modifier="Multires")
    mr.levels = mr.sculpt_levels = 1
    mr.render_levels = 1
    mr.quality = 4
    return mr.total_levels


STAGE = "_STAGE_" + NAME


def stage(sc):
    """Camera, three lights and a floor for looking at the character (never exported)."""
    coll = LC.collection(STAGE, sc.collection)
    for o in list(coll.objects):
        bpy.data.objects.remove(o, do_unlink=True)

    def obj(name, data, loc):
        o = bpy.data.objects.new(name, data)
        coll.objects.link(o)
        o.location = loc
        return o

    cam = obj("CAM_" + NAME, bpy.data.cameras.new("CAM_" + NAME), (1.55, -3.2, 1.35))
    cam.data.lens = 50
    LC.look_at(cam, (0, 0, 0.98))
    sc.camera = cam
    for name, loc, energy, size, color in (("key", (2.2, -2.4, 3.0), 180, 1.5, (1.0, 0.93, 0.85)),
                                           ("fill", (-2.6, -1.8, 1.6), 50, 2.5, (0.85, 0.9, 1.0)),
                                           ("rim", (-0.8, 2.6, 2.6), 140, 1.0, (1.0, 1.0, 1.0))):
        ld = bpy.data.lights.new("LGT_%s_%s" % (NAME, name), "AREA")
        ld.energy, ld.size, ld.color = energy, size, color
        lo = obj(ld.name, ld, loc)
        LC.look_at(lo, (0, 0, 1.1))
    fm = bpy.data.meshes.new("FLOOR_" + NAME)
    fm.from_pydata([(-3, -3, 0), (3, -3, 0), (3, 3, 0), (-3, 3, 0)], [], [(0, 1, 2, 3)])
    fmat = bpy.data.materials.get("MAT_stage_floor") or bpy.data.materials.new("MAT_stage_floor")
    fmat.diffuse_color = (0.18, 0.18, 0.19, 1)
    bsdf = next(n for n in fmat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.18, 0.18, 0.19, 1)
    fm.materials.append(fmat)
    obj("FLOOR_" + NAME, fm, (0, 0, 0))
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = 1080, 1350
    sc.frame_start, sc.frame_end = 1, 1
    world = sc.world or bpy.data.worlds.new("World")
    sc.world = world
    bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg:
        bg.inputs["Color"].default_value = (0.05, 0.055, 0.06, 1)
        bg.inputs["Strength"].default_value = 1.0
    # Point the 3D viewports at the character.
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                r3d = area.spaces[0].region_3d
                r3d.view_location = (0, 0, 0.95)
                r3d.view_distance = 3.2
    return cam


ASSET_CREDITS = """ASSET_CREDITS - characters.blend
================================
Human Base Meshes bundle v1.4.1, by Blender Studio
  https://www.blender.org/download/demo-files/ (asset bundles)
  License: CC0 1.0 (public domain dedication). No attribution required; credited anyway.
  Used: "GEO-body_male_realistic" (body, with its eyeballs) and "Jaw - Realistic"
  (teeth and gums), downloaded by scripts/build_character.py into //assets/.

Changed for this project by scripts/build_character.py: rescaled to %.2f m, slimmed to a
medium-to-thin build (normal shrink + softened muscle detail, multires level 3 removed),
rigged, skinned, mouth interior/teeth/tongue fitted, and shape keys added. The tongue,
rig, weights, shape keys and materials are original project work.
""" % HEIGHT

README = """README_characters
=================
Rebuild everything:  blender -b --factory-startup --python scripts/build_character.py
Redo only the clips: blender -b characters.blend --python scripts/anim_character.py
Export for the game: blender -b characters.blend --python scripts/export_character.py
Check renders:       blender -b characters.blend --python scripts/verify_character.py -- <dir> all
Full reference (bones, axes, limits, shape keys, viseme mixes): //CHARACTER_SUMMARY.md

Collections
  CHAR_%(n)s   the character: RIG_%(n)s, BODY_%(n)s, EYES_%(n)s, MOUTH_%(n)s
  WGT_%(n)s    control shapes (excluded)       _STAGE_%(n)s  camera, lights, floor

Posing
  FK: rotate bones directly. +X is flexion everywhere (curl, bend, open the jaw).
  IK: RIG_%(n)s object properties ik_arm_L/R, ik_leg_L/R (0 = FK, 1 = IK), then move
      ik_hand_* / ik_foot_* and the pole_* elbow/knee targets.
  Hands: Pose Mode -> asset shelf -> hand_* poses (select bones to pose one hand).
  Face: jaw bone opens the mouth; BODY_%(n)s shape keys shape the lips and blink.
  Joint limits are Limit Rotation constraints ("Limits") with Affect Transform on.

Notes
  BODY_%(n)s modifiers: Armature, then Multires (viewport/render level 1, max 2).
  The game mesh is the multires base (level 0) with the shape keys as morph targets.
  Sculpting on the multires is limited while shape keys exist; reshape through the
  SLIM/SOFTEN tables in the build script, or sculpt a copy.
""" % {"n": NAME}


def text_blocks():
    for name, body in (("ASSET_CREDITS", ASSET_CREDITS), ("README_characters", README)):
        t = bpy.data.texts.get(name) or bpy.data.texts.new(name)
        t.clear()
        t.write(body)


# Suggested jaw + shape-key mixes for the 15 Oculus/ReadyPlayerMe visemes, so off-the-
# shelf lip sync can drive this face. Stored on BODY_<name> as the "visemes" extra.
VISEMES = {
    "sil": (0, {}), "PP": (0, {"mouth_press": 1.0}), "FF": (4, {"mouth_fv": 1.0}),
    "TH": (6, {"lip_upper_up": 0.5}), "DD": (8, {"mouth_wide": 0.3}), "kk": (10, {"mouth_wide": 0.2}),
    "CH": (6, {"mouth_round": 0.5, "lip_upper_up": 0.4}), "SS": (3, {"mouth_wide": 0.7}),
    "nn": (6, {"mouth_wide": 0.2}), "RR": (6, {"mouth_round": 0.6}), "aa": (14, {}),
    "E": (8, {"mouth_wide": 0.8, "lip_upper_up": 0.3}), "I": (5, {"mouth_wide": 1.0}),
    "O": (10, {"mouth_round": 0.8}), "U": (4, {"mouth_round": 1.0}),
}


def store_extras(body, rig):
    body["visemes"] = {k: {"jaw_deg": j, "keys": dict(m)} for k, (j, m) in VISEMES.items()}
    body["jaw_bone"] = "jaw"
    rig["height_m"] = HEIGHT


def write_summary(rig, body):
    """//CHARACTER_SUMMARY.md, generated from the built rig so it can't drift."""
    import datetime

    def tris(ob):
        return sum(len(p.vertices) - 2 for p in ob.data.polygons)

    def gl(v):
        return "%.3f, %.3f, %.3f" % (v.x, v.z, -v.y)

    meshes = [bpy.data.objects[n] for n in (BODY, EYES, MOUTH)]
    deform = [b for b in rig.data.bones if b.use_deform]
    L = []
    w = L.append
    w("# Characters - %s\n" % NAME)
    w("Generated %s by scripts/build_character.py into characters.blend (scene `%s`)."
      % (datetime.date.today().isoformat(), SCENE))
    w("Blender is Z-up and the character faces -Y (his left is +X). glTF/three.js is Y-up: "
      "a Blender point (x, y, z) is (x, z, -y) in glTF, so he faces +Z there.\n")
    w("## Objects (collection `%s`)\n" % COLL)
    w("| Object | What | Verts | Tris (game mesh) |")
    w("|---|---|---|---|")
    w("| `%s` | armature, %d deforming bones (+ %d IK controls) | | |" %
      (RIG, len(deform), sum(1 for b in rig.data.bones if not b.use_deform)))
    notes = {BODY: "skin; Armature then Multires (level 1 shown, level 0 is the game mesh)",
             EYES: "both eyeballs, rigid to `eye_L`/`eye_R`", MOUTH: "teeth, gums, tongue: upper to `head`, lower to `jaw`"}
    for ob in meshes:
        w("| `%s` | %s | %d | %d |" % (ob.name, notes[ob.name], len(ob.data.vertices), tris(ob)))
    w("\nHeight %.2f m, eyes at %.3f m. Materials (placeholders, plain PBR): %s.\n" % (
        HEIGHT, rig.data.bones["eye_L"].head_local.z,
        ", ".join("`%s`" % m for m in MATERIALS)))

    w("## Posing conventions\n")
    w("- **+X is flexion on every bone**: curl a finger, bend an elbow or knee, bend the spine forward, "
      "nod, open the jaw. It means the same thing on both sides.")
    w("- Y and Z are mirrored between sides: a value that rolls the left hand one way rolls the right "
      "hand the mirror-image way when negated. Mirror a left pose to the right with (x, -y, -z).")
    w("- Euler bones use order `%s`. Quaternion bones: root, hips, spine, neck, head, upper arms, thighs." % EULER_ORDER)
    w("- Limits are Limit Rotation constraints named `Limits` (Affect Transform on). glTF can't carry "
      "constraints, so each deforming bone also has `limits_deg` and `axes` custom properties, which "
      "export as node extras (`bone.userData` in three.js).")
    w("- IK: object properties `ik_arm_L/R`, `ik_leg_L/R` on `%s` (0 = FK, 1 = IK). Targets `ik_hand_*`, "
      "`ik_foot_*`; poles `pole_elbow_*`, `pole_knee_*`. Switching to IK at rest doesn't move anything." % RIG)
    w("- `forearm_twist_*` copies the hand's Y rotation, and the forearm skin ramps from elbow (none) to "
      "wrist (full), so pronation/supination on `hand_*` twists the forearm smoothly. In three.js, "
      "set `forearm_twist.rotation.y` yourself (the constraint doesn't export).")
    w("- Hand pose assets (Pose Mode asset shelf): %s. They also export as one-frame glTF clips that key only the 38 hand bones, so they layer over body animation."
      % ", ".join("`%s`" % n for n in HAND_POSES))
    w("- **In three.js** the joints keep these exact local axes (checked on export). A joint's "
      "`quaternion` holds its rest orientation, so apply a pose on top of it instead of overwriting "
      "`rotation`: `bone.quaternion.copy(rest).multiply(q.setFromEuler(new Euler(x, y, z, 'YZX')))`. "
      "Order `YZX` in three.js is Blender's `XZY`. Export with `scripts/export_character.py`.\n")

    w("## Bones\n")
    w("Head positions in metres. Limits are degrees for the left side (right: X same, Y and Z negated "
      "and swapped).\n")
    w("| Bone | Parent | Head (Blender x, y, z) | Head (glTF) | Rotation | X | Y | Z | Axes |")
    w("|---|---|---|---|---|---|---|---|---|")
    for b in rig.data.bones:
        if not b.use_deform or b.name.endswith("_R"):
            continue
        pb = rig.pose.bones[b.name]
        lim = side_limits(b.name)
        cols = ["%g..%g" % lim[a] if lim and lim[a] != (0, 0) else ("locked" if lim else "")
                for a in "xyz"]
        w("| `%s` | %s | %.3f, %.3f, %.3f | %s | %s | %s | %s | %s | %s |" % (
            b.name, "`%s`" % b.parent.name if b.parent else "", *b.head_local, gl(b.head_local),
            pb.rotation_mode.lower(), *cols, AXES.get(axes_key(b.name), "")))
    w("\nEvery `_L` bone has an `_R` mirror (x negated).\n")

    w("## Shape keys (`%s`)\n" % BODY)
    w("Mouth shapes are lip-only: rotate `jaw` (+X, 0-30 deg) to open the mouth. "
      "In glTF these are morph targets with the same names.\n")
    desc = {"mouth_wide": "EE / I / S: corners out and back", "mouth_round": "OO / W / O: lips forward, corners in",
            "mouth_press": "M / B / P: lips pressed and rolled in", "mouth_fv": "F / V: lower lip under the upper teeth",
            "lip_upper_up": "upper lip raised, shows the upper teeth", "mouth_smile": "corners up and out, cheeks lifted",
            "blink_L": "close the left eye", "blink_R": "close the right eye"}
    w("| Key | Use |")
    w("|---|---|")
    for k in MOUTH_KEYS + BLINK_KEYS:
        w("| `%s` | %s |" % (k, desc[k]))
    w("\n### Viseme mixes\n")
    w("For lip sync that emits the 15 Oculus / Ready Player Me visemes (`viseme_sil` ... `viseme_U`): "
      "weight each viseme's jaw angle and shape-key mix by its strength and add them up. The same table "
      "is on `%s` as the `visemes` extra.\n" % BODY)
    w("| Viseme | Jaw (deg) | Shape keys |")
    w("|---|---|---|")
    for k, (j, m) in VISEMES.items():
        w("| `%s` | %g | %s |" % (k, j, ", ".join("%s %.1f" % kv for kv in m.items()) or "-"))
    clips = rig.get("clips")
    if clips:
        w("\n## Animation clips\n")
        w("Authored by `scripts/anim_character.py` (legs through IK, baked to FK keys on every frame). "
          "They play in place: move the character at `speed` metres per second along the clip's "
          "direction and the planted feet stay put. The speeds are also the rig node's `clips` extra.\n")
        w("| Clip | Seconds | Loops | Speed (m/s) |")
        w("|---|---|---|---|")
        for name, c in clips.items():
            w("| `%s` | %.2f | %s | %s |" % (name, c["seconds"], "yes" if c["loop"] else "no",
                                          ("%.3f" % c["speed"]) if c["speed"] else "-"))
        w("\n`strafe_left` moves to his left (+X in Blender), `strafe_right` is its mirror. No clip keys "
          "the jaw or eyes, which the game drives (see `app/construct/`).")
    w("\n## Rebuild\n")
    w("```\nblender -b --factory-startup --python scripts/build_character.py\n"
      "blender -b characters.blend --python scripts/verify_character.py -- screenshots/characters all\n```\n")
    w("Source: Blender Studio *Human Base Meshes* v1.4.1 (CC0), downloaded to `assets/` (gitignored). "
      "See the `ASSET_CREDITS` text block.")
    with open(SUMMARY_MD, "w") as f:
        f.write("\n".join(L) + "\n")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def build(stop_after=None, save=True):
    here = bpy.data.filepath
    if here and os.path.abspath(here) != OUT_BLEND:
        raise RuntimeError("build_character rebuilds characters.blend: open that file, or run headless "
                           "with --factory-startup (refusing to touch %s)" % here)
    sc, coll = setup_scene()
    body, eye_l, eye_r, jaw, scale = import_source(coll)
    if stop_after == "import":
        return finish(sc, save)
    slim(body)
    rig = build_armature(coll, eye_l)
    if stop_after == "rig":
        return finish(sc, save)
    skin(body, rig)
    fix_weights(body, rig)
    xs, zs, _ = lip_line(body.data)
    build_mouth(coll, jaw, rig, float(zs[0]))
    build_eyes(coll, eye_l, eye_r, rig)
    body_materials(body)
    setup_controls(rig)
    print("IK rest drift: %.6f m" % check_ik_rest(rig))
    shape_keys(body, bpy.data.objects[EYES])
    if stop_after == "skin":
        return finish(sc, save)
    multires_levels(body)
    pose_library(rig)
    import anim_character
    anim_character.build_clips(rig)       # before the summary, which lists the clips
    store_extras(body, rig)
    stage(sc)
    text_blocks()
    for o in (rig, body):
        o.select_set(o is rig)
    bpy.context.view_layer.objects.active = rig
    write_summary(rig, body)
    return finish(sc, save)


def finish(sc, save):
    if save:
        bpy.context.preferences.filepaths.save_version = 0     # no .blend1 next to it
        bpy.ops.wm.save_as_mainfile(filepath=OUT_BLEND, compress=True)
        print("saved", OUT_BLEND)
    return sc


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    stop = argv[0] if argv else None
    build(stop_after=stop)
