"""Step 5c: three bakeable lighting states, one collection each.

LIGHTS_normal     warm overhead strips (one area light per ceiling fixture)
LIGHTS_emergency  dim red from the alarm beacons
LIGHTS_blackout   only screen and indicator glow (small, dim area lights)

Light objects are named BAKE_<state>_<where>_NN: they exist for baking only and
are not exported. The dynamic lights the game drives (LIGHT_BLINK_engineering,
LIGHT_alarm_*) are empties placed with the props.
Only one LIGHTS_* collection is enabled at a time; bake_lightmaps.py switches them.
"""
import math

import bpy
from mathutils import Euler, Vector

import lib_ship as L

WARM = (1.0, 0.78, 0.55)
RED = (1.0, 0.07, 0.03)
AMBER = (1.0, 0.6, 0.2)
CRT = (0.75, 0.85, 0.7)


def _area(name, coll, loc, size, power, color, rot=(0, 0, 0), shape="RECTANGLE"):
    ob = bpy.data.objects.get(name)
    if ob is None:
        ob = bpy.data.objects.new(name, bpy.data.lights.new(name, "AREA"))
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    coll.objects.link(ob)
    ld = ob.data
    ld.shape = shape
    ld.size = size[0]
    ld.size_y = size[1]
    ld.energy = power
    ld.color = color
    ob.location = loc
    ob.rotation_euler = rot
    ob["stage"] = "lighting"
    return ob


def _point(name, coll, loc, power, color, radius=0.05):
    ob = bpy.data.objects.get(name)
    if ob is None:
        ob = bpy.data.objects.new(name, bpy.data.lights.new(name, "POINT"))
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    coll.objects.link(ob)
    ob.data.energy = power
    ob.data.color = color
    ob.data.shadow_soft_size = radius
    ob.location = loc
    ob["stage"] = "lighting"
    return ob


def _facing(normal):
    """Euler that points an area light (which emits along its local -Z) along `normal`."""
    return Vector(normal).to_track_quat("-Z", "Y").to_euler()


def build():
    L.clear_objects(lambda o: o.get("stage") == "lighting")
    for ld in [d for d in bpy.data.lights if d.users == 0]:
        bpy.data.lights.remove(ld)
    colls = {n: L.collection(n) for n in L.LIGHT_COLLECTIONS}
    counts = {n: 0 for n in L.LIGHT_COLLECTIONS}

    # ---------------------------------------------------------------- normal
    # One area light under every warm light-strip lens (faces using MAT_emit_warm),
    # read from the evaluated geometry so it works before and after transforms are
    # applied by the export script.
    cn = colls["LIGHTS_normal"]
    for cname in L.ROOM_COLLECTIONS:
        room = cname[len("ROOM_"):]
        for ob in bpy.data.collections[cname].all_objects:
            if ob.type != "MESH":
                continue
            me = ob.data
            slots = [i for i, m in enumerate(me.materials) if m and m.name == "MAT_emit_warm"]
            if not slots:
                continue
            mw = ob.matrix_world
            for poly in me.polygons:
                if poly.material_index not in slots:
                    continue
                vs = [mw @ me.vertices[i].co for i in poly.vertices]
                c = sum(vs, Vector()) / len(vs)
                n = (mw.to_3x3() @ poly.normal).normalized()
                e0, e1 = vs[1] - vs[0], vs[2] - vs[1]
                a, b = sorted((e0.length, e1.length), reverse=True)
                area = a * b
                power = 160 if area > 0.5 else (60 if area > 0.2 else 45)
                long_axis = e0 if e0.length >= e1.length else e1
                rot = n.to_track_quat("-Z", "Y").to_euler()
                counts["LIGHTS_normal"] += 1
                lt = _area(f"BAKE_normal_{room}_{counts['LIGHTS_normal']:02d}", cn, c + n * 0.045,
                           (a * 0.96, b * 0.9), power, WARM, rot=rot)
                # align the light's long side with the lens
                lx = rot.to_matrix() @ Vector((1, 0, 0))
                if abs(lx.normalized().dot(long_axis.normalized())) < 0.7:
                    lt.data.size, lt.data.size_y = b * 0.9, a * 0.96

    # ------------------------------------------------------------- emergency
    ce = colls["LIGHTS_emergency"]
    for ob in bpy.data.objects:
        if ob.name.startswith("LIGHT_alarm_") and ob.type == "EMPTY":
            counts["LIGHTS_emergency"] += 1
            # the empty sits at the lens centre, inside the opaque dome: put the bake
            # light just below the beacon so it is not occluded
            _point("BAKE_emergency_" + ob.name[len("LIGHT_alarm_"):], ce,
                   ob.matrix_world.translation + Vector((0, 0, -0.1)), ob.get("bake_power", 25.0), RED, 0.05)

    # -------------------------------------------------------------- blackout
    cb = colls["LIGHTS_blackout"]
    for ob in bpy.data.objects:
        glow = ob.get("glow")
        if not glow or ob.type != "MESH":
            continue
        # a small area light hovering in front of the glowing face (+Y of the object)
        mw = ob.matrix_world
        n = (mw.to_3x3() @ Vector(glow.get("normal", (0, 1, 0)))).normalized()
        c = mw @ Vector(glow.get("center", (0, 0, 0)))
        counts["LIGHTS_blackout"] += 1
        _area(f"BAKE_blackout_{ob.name}", cb, c + n * 0.02, tuple(glow.get("size", (0.2, 0.2))),
              glow.get("power", 2.0), tuple(glow.get("color", CRT)), rot=_facing(n))

    # world: pitch black so nothing leaks into the bakes
    w = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0, 0, 0, 1)
        bg.inputs["Strength"].default_value = 0.0

    set_state("normal")
    return counts


def set_state(state):
    """Enable exactly one LIGHTS_* collection in the view layer."""
    vl = bpy.context.view_layer
    for lc in vl.layer_collection.children:
        if lc.name in L.LIGHT_COLLECTIONS:
            lc.exclude = lc.name != "LIGHTS_" + state
    return state
