"""The caretaker's animation clips, baked into //characters.blend.

    blender -b characters.blend --python scripts/anim_character.py

build_character.py runs this at the end of a rebuild; run it on its own to redo
only the clips. Every clip is a function of time, sampled on every frame:

  * The legs are posed through the rig's leg IK (feet planted exactly, knees
    bending towards their poles), then baked to plain FK keys, so the actions
    play with IK switched off and export the same way.
  * The hips drop wherever a leg would otherwise have to over-reach its target,
    which gives the walk its natural dip at each heel strike.
  * Clips are in place. The game moves the character at the speed stored in
    RIG_<name>["clips"], which matches how fast the planted foot slides back.
  * The jaw and eyes are never keyed: the game drives them (lip sync, gaze).

Clips: idle, walk, strafe_left, strafe_right, jump, crouch, talk.
"""
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Euler, Matrix, Quaternion, Vector

sys.dont_write_bytecode = True
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import build_character as B  # noqa: E402

FPS = 30
UNKEYED = {"root", "jaw", "eye_L", "eye_R", "forearm_twist_L", "forearm_twist_R"}
ARM_DOWN = 17.0          # degrees to lower the A-pose arms to hang at the sides

WALK_T, WALK_STRIDE = 1.1, 1.1          # seconds per cycle, metres per cycle
STRAFE_T, STRAFE_STEP = 0.75, 0.34
JUMP_T, CROUCH_T, IDLE_T, TALK_T = 2.2, 3.6, 6.0, 6.0


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def minjerk(x):
    x = min(max(x, 0.0), 1.0)
    return x ** 3 * (10 - 15 * x + 6 * x * x)


def track(t, keys):
    """Scalar through (time, value) keys, eased between them, held outside."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            return v0 + (v1 - v0) * smooth((t - t0) / (t1 - t0))
    return keys[-1][1]


def add(*poses):
    """Sum pose dicts {bone: (x, y, z)}."""
    out = {}
    for p in poses:
        for k, v in p.items():
            o = out.get(k, (0.0, 0.0, 0.0))
            out[k] = (o[0] + v[0], o[1] + v[1], o[2] + v[2])
    return out


def scale(pose, s):
    return {k: (v[0] * s, v[1] * s, v[2] * s) for k, v in pose.items()}


def sided(pose_left):
    """Left-side values -> both sides (the right mirrors: X kept, Y and Z negated)."""
    out = {}
    for k, (x, y, z) in pose_left.items():
        out[k + "_L"] = (x, y, z)
        out[k + "_R"] = (x, -y, -z)
    return out


def cos1(p):
    return math.cos(2 * math.pi * p)


# ---------------------------------------------------------------------------
# Rest geometry the clips are written against
# ---------------------------------------------------------------------------
class Rest:
    def __init__(self, rig):
        bones = rig.data.bones
        self.ankle, self.ball, self.heel, self.foot_x = {}, {}, {}, {}
        for s in "LR":
            f = bones["foot_" + s]
            self.ankle[s] = f.head_local.copy()
            self.ball[s] = f.tail_local.copy()
            self.heel[s] = Vector((f.head_local.x, f.head_local.y + 0.045, 0.012))
            self.foot_x[s] = f.matrix_local.col[0].xyz.normalized()
        self.leg = bones["thigh_L"].length + bones["shin_L"].length

    def planted(self, s, dx=0.0, dy=0.0, dz=0.0, pitch=0.0):
        """Ankle target for a foot on the ground moved by (dx, dy), pitched about the
        ball (pitch > 0, heel up) or the heel (pitch < 0, toes up), then lifted by dz."""
        piv = self.ball[s] if pitch >= 0 else self.heel[s]
        R = Matrix.Rotation(math.radians(pitch), 3, self.foot_x[s])
        return piv + Vector((dx, dy, dz)) + R @ (self.ankle[s] - piv)


BASE = sided({"upperarm": (-7, 0, -ARM_DOWN), "forearm": (8, 0, 0), "hand": (-4, 0, 0), "clavicle": (-2, 0, 0)})


def relaxed_hands(amount=1.0):
    return scale(sided({k: v for k, v in B.HAND_POSES["hand_relaxed"].items()}), amount)


def feet_at_rest(rest, pitch=0.0, spread=0.0):
    return {s: (rest.planted(s, dx=spread * (1 if s == "L" else -1), pitch=pitch), pitch) for s in "LR"}


# ---------------------------------------------------------------------------
# Clips: t in seconds -> {"rot": {bone: (x, y, z) deg}, "hips": (x, y, z),
#                          "feet": {side: (ankle target, pitch deg)}, "toes": {side: deg}}
# Rotations are the bones' local Euler XZY (quaternion bones are converted).
# ---------------------------------------------------------------------------
def idle(rest, t):
    ph = t / IDLE_T
    br = math.sin(2 * math.pi * 2 * ph)                 # two breaths per loop
    sway = math.sin(2 * math.pi * ph)
    rot = add(BASE, relaxed_hands(), sided({"clavicle": (1.2 * br, 0, 0)}), {
        "spine_02": (0.8 * br, 0, 0), "spine_03": (0.6 * br, 0, 0),
        "hips": (0, 1.5 * sway, 1.0 * sway), "spine_01": (0, -1.0 * sway, -1.0 * sway),
        "neck": (1.0 * math.sin(2 * math.pi * (ph + 0.2)), 3 * math.sin(2 * math.pi * (ph + 0.1)), 0),
        "head": (-0.6 * br, 1.5 * math.sin(2 * math.pi * (ph + 0.3)), 1.0 * sway),
    })
    return {"rot": rot, "hips": (0.012 * sway, 0, -0.004 + 0.002 * br), "feet": feet_at_rest(rest), "toes": {}}


def walk(rest, t):
    T, SL, S = WALK_T, WALK_STRIDE, 0.6                  # S: stance share of the cycle
    ph = (t / T) % 1
    c = -0.03                                            # stance centred a little ahead of the ankle
    feet, toes = {}, {}

    def stance(s, p):
        dy = c - SL * S / 2 + SL * p
        if p < 0.08:
            pitch = -12 * (1 - smooth(p / 0.08))
        elif p < 0.42:
            pitch = 0.0
        else:
            pitch = 30 * smooth((p - 0.42) / (S - 0.42))
        dx = -0.045 if s == "L" else 0.045               # feet a little closer while walking
        return rest.planted(s, dx=dx, dy=dy, pitch=pitch), pitch

    for s, off in (("L", 0.0), ("R", 0.5)):
        p = (ph + off) % 1
        if p < S:
            feet[s] = stance(s, p)
            toes[s] = -max(feet[s][1], 0.0)
        else:
            u = (p - S) / (1 - S)
            a, pa = stance(s, S - 1e-6)
            b, pb = stance(s, 0.0)
            pos = a.lerp(b, minjerk(u)) + Vector((0, 0, 0.085 * math.sin(math.pi * u ** 0.75)))
            pitch = pa * (1 - smooth(u / 0.35)) + pb * smooth((u - 0.4) / 0.6)
            feet[s] = (pos, pitch)
            toes[s] = -pa * (1 - smooth(u / 0.3))
    yaw = -5 * cos1(ph)
    roll = -3 * cos1(ph - 0.8)
    swing_l, swing_r = cos1(ph - 0.5), cos1(ph)          # each arm forward with the opposite leg
    rot = add(BASE, relaxed_hands(0.8), {
        "hips": (3, yaw, roll),
        "spine_01": (2, -0.5 * yaw, -0.5 * roll), "spine_02": (1, -0.6 * yaw, -0.3 * roll),
        "spine_03": (0, -0.5 * yaw, -0.2 * roll),
        "neck": (-3, 0.3 * yaw, 0), "head": (-1, 0.3 * yaw, 0),
        "upperarm_L": (14 * swing_l, 0, 0), "upperarm_R": (14 * swing_r, 0, 0),
        "forearm_L": (10 * max(0.0, swing_l), 0, 0), "forearm_R": (10 * max(0.0, swing_r), 0, 0),
    })
    hips = (0.018 * cos1(ph - 0.3), 0.0, -0.006 + 0.010 * math.cos(4 * math.pi * (ph - 0.3)))
    return {"rot": rot, "hips": hips, "feet": feet, "toes": toes}


def _strafe_x():
    """Lateral ankle offsets for a step to the left (+X), in the moving frame."""
    s_frac = 0.35
    SL = STRAFE_STEP
    D = 0.17 + SL / 2                                    # mean ankle separation; closest is 0.17 m

    def raw(p, x0):
        u = min(p / s_frac, 1.0)
        return x0 + SL * minjerk(u) - SL * p

    ps = np.linspace(0, 1, 200, endpoint=False)
    mean_l = np.mean([raw(p, 0) for p in ps])
    mean_r = np.mean([raw((p - 0.5) % 1, 0) for p in ps])
    xl0, xr0 = D / 2 - mean_l, -D / 2 - mean_r
    return s_frac, lambda p: raw(p, xl0), lambda p: raw((p - 0.5) % 1, xr0)


def strafe_left(rest, t):
    s_frac, xl, xr = _strafe_x()
    ph = (t / STRAFE_T) % 1
    feet = {}
    for s, x, p in (("L", xl(ph), ph), ("R", xr(ph), (ph - 0.5) % 1)):
        u = p / s_frac
        lift = 0.055 * math.sin(math.pi * u) if u < 1 else 0.0
        pitch = 6 * math.sin(math.pi * u) if u < 1 else 0.0
        dx = x - rest.ankle[s].x
        feet[s] = (rest.planted(s, dx=dx, dy=-0.02, dz=lift, pitch=0.0), pitch)
    bob = math.cos(4 * math.pi * ph)
    rot = add(BASE, relaxed_hands(0.8), sided({"upperarm": (4, 0, 7), "forearm": (12, 0, 0)}), {
        "hips": (4, 0, -2.5), "spine_01": (2, 0, 1.0), "spine_02": (1, 0, 0.8), "head": (-2, 0, 0.7),
        "neck": (-3, 0, 0),
    })
    return {"rot": rot, "hips": (0.0, 0.0, -0.03 + 0.006 * bob), "feet": feet, "toes": {}}


def jump(rest, t):
    g, t_off, flight = 9.81, 0.62, 0.5
    t_land = t_off + flight
    vz = g * flight / 2
    crouch = track(t, [(0.10, 0.0), (0.45, 1.0), (0.62, -0.1)]) if t < t_off else 0.0
    land = track(t, [(t_land, 0.0), (t_land + 0.2, 1.0), (t_land + 0.65, 0.0)]) if t >= t_land else 0.0
    if t_off <= t < t_land:
        tau = t - t_off
        dz = 0.02 + vz * tau - g * tau * tau / 2
        tuck = 0.11 * math.sin(math.pi * tau / flight)
        pitch = track(tau, [(0.0, 34.0), (0.25, 15.0), (flight, -4.0)])
        feet = {s: (rest.planted(s, dz=dz + tuck, pitch=0.0) + Vector((0, 0, 0)), pitch) for s in "LR"}
        hips_z = dz
    else:
        dz = 0.0
        push = track(t, [(0.47, 0.0), (0.62, 1.0)]) if t < t_off else 0.0
        pitch = 34 * push
        feet = feet_at_rest(rest, pitch=pitch)
        hips_z = -0.20 * crouch - 0.22 * land + 0.02 * push
    arm_x = track(t, [(0.10, 2.0), (0.45, -45.0), (0.62, 95.0), (0.85, 110.0), (t_land, 35.0),
                      (t_land + 0.25, 30.0), (1.9, 2.0)])
    fore = track(t, [(0.10, 0.0), (0.45, 15.0), (0.62, 25.0), (t_land, 20.0), (t_land + 0.25, 40.0), (1.9, 0.0)])
    spine = 22 * crouch + 22 * land - 4 * track(t, [(0.5, 0.0), (0.7, 1.0), (1.0, 0.0)])
    rot = add(BASE, relaxed_hands(), sided({"upperarm": (arm_x, 0, 0), "forearm": (fore, 0, 0)}), {
        "spine_01": (0.5 * spine, 0, 0), "spine_02": (0.3 * spine, 0, 0), "spine_03": (0.2 * spine, 0, 0),
        "neck": (-0.4 * spine, 0, 0), "head": (-0.3 * spine, 0, 0),
    })
    toes = {s: -min(max(feet[s][1], 0.0), 34.0) for s in "LR"} if t < t_off else {}
    return {"rot": rot, "hips": (0.0, 0.03 * crouch + 0.02 * land, hips_z), "feet": feet, "toes": toes}


def crouch(rest, t):
    c = track(t, [(0.2, 0.0), (0.9, 1.0), (2.6, 1.0), (3.3, 0.0)])
    br = math.sin(2 * math.pi * t / 1.8) * c
    look = math.sin(2 * math.pi * t / CROUCH_T) * c
    down = sided({"upperarm": (38, 0, 6), "forearm": (42, 0, 0), "hand": (6, 0, 0)})
    rot = add(BASE, relaxed_hands(), scale(down, c), {
        "spine_01": (22 * c + 0.8 * br, 0, 0), "spine_02": (12 * c + 0.6 * br, 0, 0), "spine_03": (6 * c, 0, 0),
        "neck": (-18 * c, 6 * look, 0), "head": (-12 * c, 6 * look, 0),
    })
    return {"rot": rot, "hips": (0.0, 0.07 * c, -0.42 * c + 0.004 * br),
            "feet": feet_at_rest(rest, spread=0.02 * c), "toes": {}}


def talk(rest, t):
    """Idle stance with conversational gestures; the mouth is driven by the game."""
    base = idle(rest, t)
    k = lambda keys: track(t, keys)  # noqa: E731
    up_r = k([(0.3, 0.0), (0.9, 1.0), (4.6, 1.0), (5.4, 0.0)])
    up_l = k([(2.2, 0.0), (2.8, 1.0), (4.0, 1.0), (4.8, 0.0)])
    beat = k([(0.9, 0.0), (1.2, 1.0), (1.5, 0.0), (1.9, 1.0), (2.2, 0.0), (3.1, 1.0), (3.5, 0.0), (4.1, 0.8), (4.5, 0.0)])
    turn = k([(0.9, 1.0), (2.0, 0.3), (2.8, 1.0), (4.6, 0.6)])
    gesture = add(
        scale({"upperarm_R": (28, 0, -10), "forearm_R": (70, 0, 0), "hand_R": (-8, 55, 0)}, up_r),
        {"hand_R": (0, 25 * turn * up_r, 0), "forearm_R": (-12 * beat * up_r, 0, 0)},
        scale({"upperarm_L": (22, 0, 8), "forearm_L": (62, 0, 0), "hand_L": (-8, -50, 0)}, up_l),
        scale(sided({"index_01": (-10, 0, 0), "middle_01": (-8, 0, 0)}), 0.5 * (up_r + up_l)),
        {"neck": (4 * beat, 0, 0), "head": (2 * beat, -3 * up_l, 2 * up_r),
         "spine_02": (2 * up_r, 3 * up_r - 3 * up_l, 0)},
    )
    base["rot"] = add(base["rot"], gesture)
    return base


CLIPS = {   # name: (function, seconds, loops, game speed m/s)
    "idle": (idle, IDLE_T, True, 0.0),
    "walk": (walk, WALK_T, True, WALK_STRIDE / WALK_T),
    "strafe_left": (strafe_left, STRAFE_T, True, STRAFE_STEP / STRAFE_T),
    "jump": (jump, JUMP_T, False, 0.0),
    "crouch": (crouch, CROUCH_T, True, 0.0),
    "talk": (talk, TALK_T, True, 0.0),
}


# ---------------------------------------------------------------------------
# Baking
# ---------------------------------------------------------------------------
def to_local(pb, delta_world):
    return pb.bone.matrix_local.to_3x3().inverted() @ Vector(delta_world)


def set_rot(pb, deg):
    e = Euler([math.radians(a) for a in deg], B.EULER_ORDER)
    if pb.rotation_mode == "QUATERNION":
        pb.rotation_quaternion = e.to_quaternion()
    else:
        pb.rotation_euler = e.to_matrix().to_euler(pb.rotation_mode)


def apply(rig, rest, fr, drop=0.0):
    pose = rig.pose.bones
    for pb in pose:
        pb.location = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
    for name, deg in fr["rot"].items():
        set_rot(pose[name], deg)
    hx, hy, hz = fr["hips"]
    pose["hips"].location = to_local(pose["hips"], (hx, hy, hz - drop))
    for s in "LR":
        ankle, pitch = fr["feet"][s]
        ik = pose["ik_foot_" + s]
        ik.location = to_local(ik, ankle - rest.ankle[s])
        ik.rotation_quaternion = Euler((math.radians(pitch), 0, 0), B.EULER_ORDER).to_quaternion()
        set_rot(pose["toe_" + s], (fr["toes"].get(s, 0.0), 0, 0))
        rig["ik_leg_" + s] = 1.0
    rig.update_tag()
    bpy.context.view_layer.update()


def needed_drop(rig, rest, fr):
    """How far the hips must come down so neither leg over-reaches. 99.5% of the leg's
    length still leaves the knee about 8 degrees bent; the leg straightens fast near 100%."""
    reach = 0.995 * rest.leg
    need = 0.0
    for s in "LR":
        hip = rig.matrix_world @ rig.pose.bones["thigh_" + s].head
        a = fr["feet"][s][0]
        h = math.hypot(a.x - hip.x, a.y - hip.y)
        v = hip.z - a.z
        if h < reach:
            need = max(need, v - math.sqrt(reach * reach - h * h))
    return need


def bake(rig, rest, name, fn, seconds, loops):
    n = int(round(seconds * FPS))
    times = [f / FPS for f in range(n + 1)]
    frames = [fn(rest, t) for t in times]
    # pass 1: hip drop, smoothed (a running max first, so the smoothing never undershoots)
    drops = []
    for fr in frames:
        apply(rig, rest, fr)
        drops.append(needed_drop(rig, rest, fr))
    d = np.array(drops)
    k = 3
    pad = (np.concatenate([d[-k - 1:-1], d, d[1:k + 1]]) if loops else np.pad(d, k, mode="edge"))
    mx = np.array([pad[i:i + 2 * k + 1].max() for i in range(len(d))])
    pad = (np.concatenate([mx[-k - 1:-1], mx, mx[1:k + 1]]) if loops else np.pad(mx, k, mode="edge"))
    drop = np.convolve(pad, np.ones(2 * k + 1) / (2 * k + 1), mode="valid")
    # pass 2: pose with IK, read every deform bone back as a local transform
    keyed = [pb for pb in rig.pose.bones if pb.bone.use_deform and pb.name not in UNKEYED]
    samples = {pb.name: [] for pb in keyed}
    hips_loc = []
    for fr, dr in zip(frames, drop):
        apply(rig, rest, fr, drop=float(dr))
        for pb in keyed:
            m = rig.convert_space(pose_bone=pb, matrix=pb.matrix, from_space="POSE", to_space="LOCAL")
            samples[pb.name].append(m.to_quaternion())
        hips_loc.append(rig.pose.bones["hips"].location.copy())
    for s in "LR":
        rig["ik_leg_" + s] = 0.0
    # keys
    act = bpy.data.actions.get(name)
    if act:
        bpy.data.actions.remove(act)
    act = bpy.data.actions.new(name)
    rig.animation_data_create().action = act

    def curve(path, index, group, values):
        fc = act.fcurve_ensure_for_datablock(rig, path, index=index, group_name=group)
        fc.keyframe_points.add(len(values))
        co = np.empty(2 * len(values))
        co[0::2] = np.arange(len(values)) + 1
        co[1::2] = values
        fc.keyframe_points.foreach_set("co", co)
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
        fc.update()

    for pb in keyed:
        qs = samples[pb.name]
        if pb.rotation_mode == "QUATERNION":
            prev = Quaternion()
            vals = []
            for q in qs:
                if q.dot(prev) < 0:
                    q = -q
                vals.append(q)
                prev = q
            for i in range(4):
                curve('pose.bones["%s"].rotation_quaternion' % pb.name, i, pb.name, [q[i] for q in vals])
        else:
            prev = None
            vals = []
            for q in qs:
                e = q.to_euler(pb.rotation_mode, prev) if prev else q.to_euler(pb.rotation_mode)
                vals.append(e)
                prev = e
            for i in range(3):
                curve('pose.bones["%s"].rotation_euler' % pb.name, i, pb.name, [e[i] for e in vals])
    for i in range(3):
        curve('pose.bones["hips"].location', i, "hips", [v[i] for v in hips_loc])
    act.use_frame_range = True
    act.frame_start, act.frame_end = 1, n + 1
    act.use_cyclic = loops
    act.use_fake_user = True
    rig.animation_data.action = None
    return act


def flip(rig, src, name):
    act = bpy.data.actions.get(name)
    if act:
        bpy.data.actions.remove(act)
    act = src.copy()
    act.name = name
    act.use_fake_user = True
    reset_pose(rig)
    act.flip_with_pose(rig)
    return act


def reset_pose(rig):
    for pb in rig.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
    for s in "LR":
        rig["ik_leg_" + s] = 0.0
        rig["ik_arm_" + s] = 0.0
    rig.update_tag()
    bpy.context.view_layer.update()


def build_clips(rig=None):
    rig = rig or bpy.data.objects[B.RIG]
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.parent is rig]
    hidden = {o: o.hide_viewport for o in meshes}
    for o in meshes:                      # nothing to deform while baking: much faster
        o.hide_viewport = True
    rest = Rest(rig)
    made = {}
    try:
        for name, (fn, seconds, loops, _) in CLIPS.items():
            made[name] = bake(rig, rest, name, fn, seconds, loops)
            print("clip %-12s %3d frames" % (name, int(round(seconds * FPS)) + 1))
        made["strafe_right"] = flip(rig, made["strafe_left"], "strafe_right")
    finally:
        reset_pose(rig)
        for o, h in hidden.items():
            o.hide_viewport = h
    info = {name: {"seconds": sec, "loop": loops, "speed": round(speed, 4)}
            for name, (_, sec, loops, speed) in CLIPS.items()}
    info["strafe_right"] = dict(info["strafe_left"])
    rig["clips"] = info
    return made


if __name__ == "__main__":
    build_clips()
    bpy.context.preferences.filepaths.save_version = 0     # no .blend1 next to it
    bpy.ops.wm.save_mainfile()
    print("saved", bpy.data.filepath)
