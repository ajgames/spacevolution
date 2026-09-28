"""Shared helpers and layout constants for the Space Veluton starter ship.

Conventions
-----------
* 1 Blender unit = 1 m, Z up.
* Ship "top" (fore, command module) is +Y. The ship's left (cryo pod) is -X.
* Room outlines are listed counter-clockwise when seen from above, so the room
  interior is on the left of every edge and walls grow to the right (outward).
"""
import math

import bmesh
import bpy
from mathutils import Vector

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
WALL_T = 0.2      # structural wall thickness
ROOM_H = 2.8      # room clear height
CORR_W = 1.8      # corridor clear width
CORR_H = 2.4      # corridor clear height
DOOR_W = 1.0
DOOR_H = 2.1
EYE_H = 1.7
HALF = CORR_W / 2
ARM_END = 4.8     # corridor arms end at the pods' outer wall faces (x = +-4.8)
STEM_END = 4.8    # stem ends at the command module's outer wall face (y = 4.8)
HULL_R = 5.0      # central hull radius, centred on the T junction

# Dock alcove cut into the south wall of the T junction.
DOCK_W = 1.4
DOCK_D = 0.8
DOCK_H = 1.4

# Interior outlines (CCW). "door" = (edge index, offset of the door centre from
# the edge start).
ROOMS = {
    "command": dict(
        outline=[(-3, 5), (3, 5), (3, 9), (2, 10), (-2, 10), (-3, 9)],
        height=ROOM_H,
        door=(0, 3.0),
    ),
    "cryo": dict(
        outline=[(-10, -3), (-6, -3), (-5, -2), (-5, 2), (-6, 3), (-10, 3), (-11, 2), (-11, -2)],
        height=ROOM_H,
        door=(2, 2.0),
    ),
    "engineering": dict(
        outline=[(6, -3), (10, -3), (11, -2), (11, 2), (10, 3), (6, 3), (5, 2), (5, -2)],
        height=ROOM_H,
        door=(6, 2.0),
    ),
}

ROOM_COLLECTIONS = ["ROOM_command", "ROOM_cryo", "ROOM_engineering", "ROOM_corridor"]
LIGHT_COLLECTIONS = ["LIGHTS_normal", "LIGHTS_emergency", "LIGHTS_blackout"]


# ---------------------------------------------------------------------------
# Collections / objects
# ---------------------------------------------------------------------------
def collection(name, parent=None):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
    parent = parent or bpy.context.scene.collection
    if c.name not in parent.children:
        parent.children.link(c)
    return c


def clear_objects(predicate):
    """Delete every object for which predicate(obj) is true, plus orphaned meshes."""
    doomed = [o for o in bpy.data.objects if predicate(o)]
    for o in doomed:
        bpy.data.objects.remove(o, do_unlink=True)
    for me in [m for m in bpy.data.meshes if m.users == 0]:
        bpy.data.meshes.remove(me)
    return len(doomed)


def link_only(obj, coll):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def mesh_object(name, verts, faces, coll, location=(0, 0, 0), mesh=None):
    if mesh is None:
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata([tuple(v) for v in verts], [], faces)
        mesh.validate()
        mesh.update()
    ob = bpy.data.objects.new(name, mesh)
    ob.location = location
    coll.objects.link(ob)
    return ob


def empty(name, coll, location, rot_z=0.0, display="ARROWS", size=0.25):
    ob = bpy.data.objects.get(name)
    if ob is None:
        ob = bpy.data.objects.new(name, None)
        coll.objects.link(ob)
    else:
        link_only(ob, coll)
    ob.empty_display_type = display
    ob.empty_display_size = size
    ob.location = location
    ob.rotation_euler = (0, 0, rot_z)
    return ob


# ---------------------------------------------------------------------------
# Geometry builders (return verts, faces)
# ---------------------------------------------------------------------------
def box_geo(mn, mx):
    x0, y0, z0 = mn
    x1, y1, z1 = mx
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    return v, f


def prism_geo(footprint, z0, z1):
    """Extrude a convex CCW quad footprint [(x,y)*4] from z0 to z1."""
    n = len(footprint)
    v = [(x, y, z0) for x, y in footprint] + [(x, y, z1) for x, y in footprint]
    f = [tuple(reversed(range(n))), tuple(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        f.append((i, j, n + j, n + i))
    return v, f


def merge_geo(parts):
    verts, faces = [], []
    for v, f in parts:
        off = len(verts)
        verts.extend(v)
        faces.extend(tuple(i + off for i in face) for face in f)
    return verts, faces


def box(name, coll, center, size, rot_z=0.0):
    """Axis-aligned (optionally Z-rotated) box with its origin at the centre."""
    sx, sy, sz = (s / 2 for s in size)
    v, f = box_geo((-sx, -sy, -sz), (sx, sy, sz))
    ob = mesh_object(name, v, f, coll, location=center)
    ob.rotation_euler = (0, 0, rot_z)
    return ob


def miter_offsets(outline, t):
    """Outer points of a wall of thickness t grown outward from a CCW outline."""
    pts = [Vector(p) for p in outline]
    n = len(pts)
    out = []
    for i in range(n):
        p_prev, p, p_next = pts[i - 1], pts[i], pts[(i + 1) % n]
        d0 = (p - p_prev).normalized()
        d1 = (p_next - p).normalized()
        n0 = Vector((d0.y, -d0.x))
        n1 = Vector((d1.y, -d1.x))
        m = (n0 + n1).normalized()
        out.append(p + m * (t / m.dot(n0)))
    return out


def wall_ring_geo(outline, t, h, openings=None, z0=0.0):
    """Mitred wall ring around a CCW outline.

    openings: {edge_index: [(centre_offset, width, top_height), ...]}
    """
    openings = openings or {}
    pts = [Vector(p) for p in outline]
    outer = miter_offsets(outline, t)
    n = len(pts)
    parts = []
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        oa, ob = outer[i], outer[(i + 1) % n]
        d = (b - a)
        L = d.length
        d = d.normalized()
        nrm = Vector((d.y, -d.x))

        def inner(s):
            return a + d * s

        def outer_pt(s):
            if s <= 1e-6:
                return oa
            if s >= L - 1e-6:
                return ob
            return a + d * s + nrm * t

        cuts = sorted(openings.get(i, []))
        spans = []  # (s0, s1, zlo, zhi)
        s = 0.0
        for c, w, top in cuts:
            spans.append((s, c - w / 2, z0, z0 + h))
            spans.append((c - w / 2, c + w / 2, z0 + top, z0 + h))
            s = c + w / 2
        spans.append((s, L, z0, z0 + h))
        for s0, s1, zl, zh in spans:
            if s1 - s0 < 1e-4 or zh - zl < 1e-4:
                continue
            # CCW footprint: the inner edge runs along +d and the outer edge lies to its right.
            fp = [inner(s0), outer_pt(s0), outer_pt(s1), inner(s1)]
            parts.append(prism_geo([(p.x, p.y) for p in fp], zl, zh))
    return merge_geo(parts)


def polygon_slab_geo(outline, z0, z1):
    """Slab from an arbitrary convex CCW polygon (n-gon caps; greybox only)."""
    n = len(outline)
    v = [(x, y, z0) for x, y in outline] + [(x, y, z1) for x, y in outline]
    f = [tuple(reversed(range(n))), tuple(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        f.append((i, j, n + j, n + i))
    return v, f


def circle_pts(cx, cy, r, segs, start=0.0):
    return [(cx + r * math.cos(start + 2 * math.pi * i / segs),
             cy + r * math.sin(start + 2 * math.pi * i / segs)) for i in range(segs)]


def tri_count(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    total = 0
    for o in objs:
        if o.type != "MESH":
            continue
        eo = o.evaluated_get(dg)
        me = eo.to_mesh()
        me.calc_loop_triangles()
        total += len(me.loop_triangles)
        eo.to_mesh_clear()
    return total
