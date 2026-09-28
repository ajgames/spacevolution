"""Step 4: secondary detail - conduits, cables, vents, lockers, consoles,
signage placeholders and wear accents.

Re-runnable: removes every object tagged stage == "detail" first.
Signage faces (SIGN_*) use MAT_nameplate with UVs filling 0-1, so the game (or a
later art pass) can drop a real sign texture on each one.
"""
import math

import bpy
from mathutils import Euler, Matrix, Vector

import lib_build as B
import lib_ship as L
from build_props import AMBER, CRT_GLOW, glow, marker, up_quad

RAD = math.radians
FILL = B.FILL
H = L.ROOM_H


def put(name, mb, coll, loc=(0, 0, 0), rot=(0, 0, 0), parent=None, **props):
    ob = B.obj(name, mb, coll, loc, rot, parent=parent)
    ob["stage"] = "detail"
    ob["static"] = props.pop("static", True)
    for k, v in props.items():
        ob[k] = v
    return ob


# ---------------------------------------------------------------------------
# shared pieces
# ---------------------------------------------------------------------------
def pipe_run(mb, pts, r=0.04, band="ribbed", flanges=True, segs=10):
    mb.tube(pts, r, segs, band=band, caps=False)
    if flanges:
        for p, q in ((pts[0], pts[1]), (pts[-1], pts[-2])):
            d = (Vector(q) - Vector(p)).normalized()
            rot = d.to_track_quat("Z", "Y").to_euler()
            with mb.at(p, rot=rot):
                mb.lathe([(0, 0), (r * 1.7, 0), (r * 1.7, 0.03), (0, 0.03)], segs, band="steel")


def valve_wheel(mb, loc, normal, r=0.12):
    rot = Vector(normal).to_track_quat("Z", "Y").to_euler()
    with mb.at(loc, rot=rot):
        mb.lathe([(r - 0.015, 0.0), (r, 0.0), (r, 0.02), (r - 0.015, 0.02), (r - 0.015, 0.0)], 16, band="steel")
        mb.lathe([(0, -0.02), (0.03, -0.02), (0.03, 0.03), (0, 0.03)], 10, band="gunmetal")
        for k in range(3):
            with mb.at(rot_z=RAD(120 * k)):
                mb.box((0.02, -0.008, 0.004), (r - 0.012, 0.008, 0.016), band="steel")


def junction_box(mb, w=0.3, h=0.4, d=0.12, lamp=True):
    """Wall box in the current frame: back on y = 0, front toward +Y."""
    mb.cbox((-w / 2, -0.01, 0.0), (w / 2, d, h), 0.015, band="gunmetal", bands={"+y": "panel_gray"}, skip=("-y",))
    mb.cbox((-w / 2 + 0.03, d, h - 0.1), (w / 2 - 0.03, d + 0.008, h - 0.04), 0.003, band="label",
            bands={"+y": "label"}, skip=("-y",))
    for x in (-w / 2 + 0.03, w / 2 - 0.03):
        for z in (0.03, h - 0.03):
            mb.cbox((x - 0.012, d, z - 0.012), (x + 0.012, d + 0.01, z + 0.012), 0.003, band="steel", skip=("-y",))
    if lamp:
        mb.panel((0.0, d + 0.001, 0.12), (-1, 0, 0), (0, 0, 1), 0.03, 0.03, "MAT_emit_amber")


def face_toward(p, target):
    """Z rotation that points local +Y from p toward target (plan view)."""
    d = Vector(target).xy - Vector(p).xy
    return math.atan2(-d.x, d.y)


def sign(name, coll, loc, right, up, w, h):
    """Sign placeholder: a backing plate + a face object (SIGN_*) with 0-1 UVs.
    `right`/`up` are the reader's screen axes; the sign faces the reader."""
    right, up = Vector(right).normalized(), Vector(up).normalized()
    n = right.cross(up)                     # toward the reader
    # right-handed local frame: X = -right, Y = n (face normal), Z = up
    rot = Matrix((-right, n, up)).transposed().to_euler()
    mb = B.MB()
    mb.cbox((-w / 2 - 0.02, -0.02, -h / 2 - 0.02), (w / 2 + 0.02, 0.0, h / 2 + 0.02), 0.006, band="gunmetal",
            bands={"+y": "steel"}, skip=("-y",))
    put(name + "_plate", mb, coll, loc, rot)
    fmb = B.MB()
    fmb.panel((0, 0.001, 0), (-1, 0, 0), (0, 0, 1), w, h, "MAT_nameplate")   # reader's right = local -X
    return put(name, fmb, coll, loc, rot, sign=True)


# ---------------------------------------------------------------------------
# command
# ---------------------------------------------------------------------------
def locker():
    mb = B.MB()
    w, d, h = 0.76, 0.5, 2.0
    mb.cbox((-w / 2, 0.0, 0.0), (w / 2, d, h), 0.02, band="panel_gray", bands={"+y": "gunmetal"}, skip=("-y", "-z"))
    # door with vent slots, handle and stencil plate
    mb.cbox((-w / 2 + 0.04, d, 0.08), (w / 2 - 0.04, d + 0.025, h - 0.06), 0.012, band="gunmetal",
            bands={"+y": "panel_teal"}, skip=("-y",))
    for z in (1.62, 0.28):
        mb.cbox((-0.2, d + 0.025, z), (0.2, d + 0.03, z + 0.16), 0.004, band="vent", bands={"+y": "vent"},
                skip=("-y",))
    mb.cbox((w / 2 - 0.12, d + 0.025, 0.95), (w / 2 - 0.08, d + 0.07, 1.2), 0.008, band="steel")
    mb.cbox((-0.17, d + 0.025, 1.4), (0.17, d + 0.032, 1.47), 0.003, band="label", bands={"+y": "label"}, skip=("-y",))
    return mb.finish("MOD_locker")


def comms_console():
    """East-wall station: pedestal, sloped panel, upright CRT housing."""
    mb = B.MB()
    prof = [(0.62, 0.0), (0.62, 1.7), (0.4, 1.7), (0.34, 1.02), (0.06, 0.86), (0.0, 0.84), (0.0, 0.08),
            (0.04, 0.08), (0.04, 0.0)]
    bands = ["gunmetal", "gunmetal", "gunmetal", "console", "steel", "panel_teal", "gunmetal", "gunmetal"]
    # path runs along the wall; r grows toward the wall (left normal of +X travel is +Y)
    mb.sweep([(-0.78, 0.0), (0.78, 0.0)], prof, bands, caps=True, cap_band="panel_teal")
    tilt = math.atan2(1.02 - 0.86, 0.34 - 0.06)
    with mb.at((0, 0.2, 0.94), rot=Euler((tilt, 0, 0))):
        mb.cbox((-0.7, -0.12, -0.01), (0.7, 0.12, 0.012), 0.006, band="gunmetal", skip=("-z",))
        for i in range(10):
            x = -0.6 + i * 0.1
            mb.cbox((x - 0.025, -0.06, 0.012), (x + 0.025, -0.01, 0.028), 0.004, band="rubber",
                    bands={"+z": "console"}, skip=("-z",))
            up_quad(mb, x - 0.01, 0.02, x + 0.01, 0.035, 0.0125, "MAT_emit_amber" if i % 4 == 0 else "MAT_display")
        up_quad(mb, 0.25, 0.04, 0.62, 0.1, 0.0125, "MAT_display")
    # CRT set into the upright housing (faces -Y = into the room)
    mb.cbox((-0.3, 0.3, 1.14), (0.3, 0.37, 1.62), 0.015, band="console")
    mb.panel((0, 0.299, 1.38), (1, 0, 0), (0, 0, 1), 0.44, 0.34, "MAT_display")
    # headset hook + handset
    mb.cbox((0.55, 0.32, 1.3), (0.62, 0.4, 1.5), 0.01, band="rubber")
    return mb


def build_command(coll):
    lk = locker()
    for i, y in enumerate((6.44, 5.64)):
        put(f"DET_command_locker_{i + 1:02d}", lk, coll, (-2.92, y, 0.0), (0, 0, -math.pi / 2), module="MOD_locker")
    cc = comms_console()
    put("DET_command_comms", cc, coll, (2.28, 6.05, 0.0), (0, 0, -math.pi / 2),
        glow=glow((0, 0.3, 1.38), (0, -1, 0), (0.44, 0.34), 1.5, CRT_GLOW))
    # conduit bundle climbing the north wall behind the desk and running over the ceiling
    mb = B.MB()
    for sx in (-1, 1):
        for i, x in enumerate((1.26, 1.36)):
            pipe_run(mb, [(sx * x, 9.93, 0.55), (sx * x, 9.93, 2.55), (sx * x, 9.7, 2.72), (sx * x, 6.4, 2.72)],
                     r=0.03 if i % 2 else 0.04, band="ribbed" if i % 2 else "rubber", flanges=False, segs=8)
        for y in (9.2, 7.6):
            mb.cbox((sx * 1.31 - 0.12, y - 0.03, 2.66), (sx * 1.31 + 0.12, y + 0.03, 2.8), 0.008, band="steel")
    with mb.at((0, 9.98, 1.86), rot=Euler((0, 0, math.pi))):
        junction_box(mb, 0.5, 0.45, 0.14)
    put("DET_command_conduits", mb, coll, glow=glow((0.0, 9.83, 1.98), (0, -1, 0), (0.03, 0.03), 0.15))
    sign("SIGN_command_room", coll, (-1.0, 9.94, 2.12), (1, 0, 0), (0, 0, 1), 0.5, 0.12)


# ---------------------------------------------------------------------------
# cryo
# ---------------------------------------------------------------------------
def cryo_monitor():
    mb = B.MB()
    prof = [(0.55, 0.0), (0.55, 1.55), (0.36, 1.55), (0.3, 0.98), (0.04, 0.84), (0.0, 0.82), (0.0, 0.08),
            (0.04, 0.08), (0.04, 0.0)]
    bands = ["panel_gray", "gunmetal", "gunmetal", "console", "steel", "panel_gray", "gunmetal", "gunmetal"]
    mb.sweep([(-0.8, 0.0), (0.8, 0.0)], prof, bands, caps=True, cap_band="panel_gray")
    tilt = math.atan2(0.98 - 0.84, 0.3 - 0.04)
    with mb.at((0, 0.17, 0.91), rot=Euler((tilt, 0, 0))):
        mb.cbox((-0.72, -0.1, -0.01), (0.72, 0.1, 0.012), 0.006, band="gunmetal", skip=("-z",))
        for i in range(6):
            x = -0.55 + i * 0.22
            up_quad(mb, x - 0.05, -0.02, x + 0.05, 0.06, 0.0125, "MAT_display")
            mb.cbox((x - 0.02, -0.08, 0.012), (x + 0.02, -0.04, 0.03), 0.004, band="rubber",
                    bands={"+z": (FILL, "MAT_emit_amber")}, skip=("-z",))
    mb.cbox((-0.36, 0.28, 1.08), (0.36, 0.34, 1.5), 0.015, band="console")
    mb.panel((0, 0.279, 1.29), (1, 0, 0), (0, 0, 1), 0.6, 0.34, "MAT_display")
    return mb


def coolant_tank():
    mb = B.MB()
    mb.lathe([(0, 0), (0.3, 0), (0.3, 0.12), (0.26, 0.14), (0, 0.14)], 16, band="gunmetal")
    mb.lathe([(0, 0.14), (0.24, 0.14), (0.24, 1.7), (0.18, 1.82), (0.06, 1.86), (0, 1.86)], 16,
             band=["ribbed", "ribbed", "steel", "steel", "steel"])
    for z in (0.45, 1.1, 1.55):
        with mb.at((0, 0, z)):
            mb.lathe([(0.24, 0), (0.26, 0), (0.26, 0.05), (0.24, 0.05), (0.24, 0)], 16, band="hazard")
    mb.tube([(0, 0, 1.86), (0, 0, 2.3), (0.0, 0.0, 2.8)], 0.05, 10, band="ribbed")
    valve_wheel(mb, (0.0, 0.26, 1.0), (0, 1, 0), 0.1)
    mb.tube([(0, 0.2, 1.0), (0, 0.26, 1.0)], 0.02, 8, band="steel")
    return mb.finish("MOD_coolant_tank")


def build_cryo(coll):
    put("DET_cryo_monitor", cryo_monitor(), coll, (-10.33, 0.0, 0.0), (0, 0, math.pi / 2),
        glow=glow((0, 0.27, 1.29), (0, -1, 0), (0.6, 0.34), 1.5, CRT_GLOW))
    tank = coolant_tank()
    for i, (x, y) in enumerate(((-10.25, 2.25), (-10.25, -2.25))):
        put(f"DET_cryo_tank_{i + 1:02d}", tank, coll, (x, y, 0.0), (0, 0, face_toward((x, y), (-8.0, 0.0))),
            module="MOD_coolant_tank")
    # manifolds above the pods, fed by the pod hoses
    mb = B.MB()
    for sy in (1, -1):
        y = sy * 2.93
        pipe_run(mb, [(-5.95, y, 2.6), (-10.05, y, 2.6)], r=0.06, band="ribbed", segs=12)
        pipe_run(mb, [(-5.95, y - sy * 0.03, 2.44), (-10.05, y - sy * 0.03, 2.44)], r=0.03, band="rubber",
                 flanges=False, segs=8)
        for x in (-6.2, -7.35, -8.65, -9.8):
            mb.cbox((x - 0.03, y - 0.09, 2.52), (x + 0.03, y + 0.07, 2.68), 0.008, band="steel")
    put("DET_cryo_manifolds", mb, coll)
    sign("SIGN_cryo_room", coll, (-10.94, -1.0, 2.12), (0, 1, 0), (0, 0, 1), 0.5, 0.12)


# ---------------------------------------------------------------------------
# engineering
# ---------------------------------------------------------------------------
def power_unit():
    mb = B.MB()
    w, d, h = 1.6, 0.45, 1.95
    mb.cbox((-w / 2, 0.0, 0.0), (w / 2, d, h), 0.025, band="panel_gray", bands={"+y": "gunmetal"}, skip=("-y", "-z"))
    mb.cbox((-w / 2 - 0.02, -0.02, h), (w / 2 + 0.02, d + 0.03, h + 0.08), 0.02, band="gunmetal",
            bands={"+y": "hazard"}, skip=("-y",))
    for i in range(3):
        x = -0.5 + i * 0.5
        mb.cbox((x - 0.2, d, 0.9), (x + 0.2, d + 0.03, 1.75), 0.012, band="gunmetal", bands={"+y": "panel_teal"},
                skip=("-y",))
        # breaker lever
        mb.cbox((x - 0.06, d + 0.03, 1.2), (x + 0.06, d + 0.07, 1.4), 0.008, band="steel", skip=("-y",))
        with mb.at((x, d + 0.07, 1.3), rot=Euler((RAD(-60 if i != 1 else -120), 0, 0))):
            mb.cbox((-0.012, -0.012, 0.0), (0.012, 0.012, 0.2), 0.004, band="steel", skip=("-z",))
            mb.cbox((-0.05, -0.02, 0.2), (0.05, 0.02, 0.24), 0.01, band="rubber")
        # gauge
        with mb.at((x, d + 0.03, 1.6), rot=Euler((RAD(-90), 0, 0))):
            mb.lathe([(0, 0), (0.07, 0), (0.07, 0.03), (0.06, 0.03), (0.06, 0.02), (0, 0.02)], 16,
                     band=["gunmetal", "gunmetal", "steel", "steel", "label"])
        mb.panel((x, d + 0.031, 1.05), (-1, 0, 0), (0, 0, 1), 0.08, 0.03,
                 "MAT_emit_amber" if i != 1 else "MAT_emit_red")
    mb.cbox((-0.7, d, 0.15), (0.7, d + 0.02, 0.75), 0.01, band="gunmetal", bands={"+y": "vent"}, skip=("-y",))
    for x in (-0.55, -0.35, 0.35, 0.55):
        pipe_run(mb, [(x, 0.2, h + 0.08), (x, 0.2, H + 0.02)], r=0.04 if abs(x) > 0.5 else 0.03,
                 band="ribbed", flanges=False, segs=8)
    return mb


def corner_pipes():
    mb = B.MB()
    for i, (dx, r) in enumerate(((-0.14, 0.06), (0.0, 0.045), (0.14, 0.06))):
        pipe_run(mb, [(dx, 0.0, 0.0), (dx, 0.0, H)], r=r, band="ribbed" if i != 1 else "steel", segs=12)
        for z in (0.5, 1.9):
            with mb.at((dx, 0.0, z)):
                mb.lathe([(r, 0), (r + 0.02, 0), (r + 0.02, 0.05), (r, 0.05), (r, 0)], 12, band="steel")
    valve_wheel(mb, (0.0, 0.12, 1.25), (0, 1, 0), 0.13)
    mb.tube([(0.0, 0.04, 1.25), (0.0, 0.12, 1.25)], 0.02, 8, band="steel")
    for z in (0.25, 2.5):
        mb.cbox((-0.24, -0.08, z), (0.24, 0.03, z + 0.08), 0.01, band="gunmetal", bands={"+y": "hazard"})
    return mb.finish("MOD_corner_pipes")


def build_engineering(coll):
    put("DET_engineering_power_unit", power_unit(), coll, (9.0, -2.93, 0.0), (0, 0, 0),
        glow=glow((0, 0.49, 1.05), (0, 1, 0), (1.2, 0.05), 0.6))
    cp = corner_pipes()
    # NE and SE chamfers: face the room centre
    for i, (x, y) in enumerate(((10.3, 2.3), (10.3, -2.3))):
        put(f"DET_engineering_pipes_{i + 1:02d}", cp, coll, (x, y, 0.0), (0, 0, face_toward((x, y), (8.0, 0.0))),
            module="MOD_corner_pipes")
    # cable tray from the racks to the door, over the south half of the ceiling
    mb = B.MB()
    y0 = -1.25
    mb.cbox((5.2, y0 - 0.2, 2.58), (10.0, y0 + 0.2, 2.6), 0.005, band="gunmetal", bands={"-z": "vent"})
    for sy in (-1, 1):
        mb.cbox((5.2, y0 + sy * 0.2 - 0.01, 2.58), (10.0, y0 + sy * 0.2 + 0.01, 2.66), 0.004, band="steel")
    for x in (5.6, 7.0, 8.6, 9.8):
        mb.box((x - 0.015, y0 - 0.21, 2.6), (x + 0.015, y0 - 0.19, H), band="steel")
        mb.box((x - 0.015, y0 + 0.19, 2.6), (x + 0.015, y0 + 0.21, H), band="steel")
    for k, dy in enumerate((-0.12, -0.04, 0.05, 0.13)):
        mb.tube([(5.2, y0 + dy, 2.63), (10.0, y0 + dy, 2.63), (10.3, y0 + dy, 2.5), (10.55, y0 + dy * 0.5, 2.35)],
                0.028 if k % 2 else 0.034, 8, band="rubber")
    put("DET_engineering_cable_tray", mb, coll)
    # hazard floor strip in front of the core racks
    mb = B.MB()
    f = mb.face([(9.72, -1.75, 0.003), (9.84, -1.75, 0.003), (9.84, 1.75, 0.003), (9.72, 1.75, 0.003)], band="hazard")
    mb._orient([f], (0, 0, 1))
    put("DET_engineering_floor_marking", mb, coll)
    sign("SIGN_engineering_room", coll, (7.0, 2.94, 2.12), (1, 0, 0), (0, 0, 1), 0.5, 0.12)


# ---------------------------------------------------------------------------
# corridor
# ---------------------------------------------------------------------------
def corridor_pipes(length):
    """Pipes along the right upper chamfer (+Y side) of a corridor section running
    along +X from 0 to `length`, with clamps at every rib."""
    mb = B.MB()
    for (y, z), r, band in (((0.568, 2.18), 0.045, "ribbed"), ((0.692, 1.975), 0.03, "rubber")):
        pipe_run(mb, [(0.02, y, z), (length - 0.02, y, z)], r=r, band=band, flanges=False, segs=10)
    clamps = [0.08] + [1.24 + 1.3 * k for k in range(int(length / 1.3)) if 1.24 + 1.3 * k < length - 0.2]
    clamps.append(length - 0.08)
    for x in clamps:
        with mb.at((x, 0.0, 0.0)):
            mb.cbox((-0.03, 0.52, 1.93), (0.03, 0.76, 2.24), 0.008, band="steel")
    # cable bundle on the left chamfer, sagging between ribs
    pts = []
    n = int(length / 1.3)
    for i in range(n):
        x0 = i * 1.3 + 0.1
        pts += [(x0, -0.6, 2.16), (x0 + 0.65, -0.55, 2.0), (x0 + 1.2, -0.6, 2.16)]
    if pts:
        mb.tube(pts, 0.025, 6, band="rubber")
    return mb


def build_corridor(coll):
    h = L.HALF
    runs = [("west", (-h, 0.0, 0.0), math.pi, L.ARM_END - h),
            ("east", (h, 0.0, 0.0), 0.0, L.ARM_END - h),
            ("stem", (0.0, h, 0.0), math.pi / 2, L.STEM_END - h)]
    for key, loc, rz, length in runs:
        put(f"DET_corridor_pipes_{key}", corridor_pipes(length), coll, loc, (0, 0, rz))
    # wall junction boxes
    for i, (loc, rz) in enumerate((((-3.0, h - 0.0, 1.3), math.pi), ((3.3, -h, 1.3), 0.0), ((h, 3.1, 1.3), math.pi / 2))):
        mb = B.MB()
        junction_box(mb, 0.3, 0.42, 0.12)
        mb.tube([(0.08, 0.06, 0.42), (0.08, 0.06, 0.7), (0.08, 0.02, 0.8)], 0.02, 8, band="ribbed")
        put(f"DET_corridor_jbox_{i + 1:02d}", mb, coll, loc, (0, 0, rz),
            glow=glow((0.0, 0.13, 0.12), (0, 1, 0), (0.03, 0.03), 0.15))
    # direction signs at the junction
    sign("SIGN_corridor_to_cryo", coll, (-1.6, h - 0.02, 1.75), (1, 0, 0), (0, 0, 1), 0.44, 0.1)
    sign("SIGN_corridor_to_engineering", coll, (1.6, h - 0.02, 1.75), (1, 0, 0), (0, 0, 1), 0.44, 0.1)
    sign("SIGN_corridor_to_command", coll, (h - 0.02, 1.6, 1.75), (0, -1, 0), (0, 0, 1), 0.44, 0.1)
    # hazard floor marking at the dock alcove mouth
    mb = B.MB()
    f = mb.face([(-0.7, -0.98, 0.003), (0.7, -0.98, 0.003), (0.7, -0.86, 0.003), (-0.7, -0.86, 0.003)], band="hazard")
    mb._orient([f], (0, 0, 1))
    put("DET_corridor_dock_marking", mb, coll)


def build():
    L.clear_objects(lambda o: o.get("stage") == "detail")
    rooms = {n: L.collection(n) for n in L.ROOM_COLLECTIONS}
    build_command(rooms["ROOM_command"])
    build_cryo(rooms["ROOM_cryo"])
    build_engineering(rooms["ROOM_engineering"])
    build_corridor(rooms["ROOM_corridor"])
    for me in [m for m in bpy.data.meshes if m.users == 0]:
        bpy.data.meshes.remove(me)
    return {c: len(rooms[c].objects) for c in rooms}
