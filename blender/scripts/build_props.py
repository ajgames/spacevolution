"""Step 3b: hero props, doors, interactive objects, markers and dynamic light
placeholders.

Conventions used by the game code
---------------------------------
* Buttons (BTN_*): origin at the press point (centre of the cap's top face).
  Local +Z is the outward face normal; a press moves the button along local -Z.
* Doors (DOOR_*): origin at the bottom centre of the closed panel, which sits in
  the middle of the wall. The door opens by sliding +1.0 m along its local +X
  into the wall pocket. Local +Y faces the room the door belongs to.
* Cryo pod glass (CRYO_POD_NN_glass): child of the pod, origin on the hinge
  line (left edge seen from outside); it swings about its local Z.
* Screens (SCREEN_*), pod status displays and nameplates: flat quads, UVs fill
  0-1, origin at the centre. Screens face their local -Y.
* Markers (SPAWN_*, SEAT_*, INTERACT_*): empties whose local +Y is the facing
  direction (glTF -Z after the Y-up conversion, i.e. Object3D forward).
  SPAWN_/SEAT_ origins are at floor / seat-cushion level; the custom property
  "eye_height" gives the camera offset above the origin.
* LIGHT_BLINK_engineering and LIGHT_alarm_*: empties placed at the lamp centre,
  with light settings in custom properties (exported as glTF extras).

Re-runnable: removes every object tagged stage == "props" and the greybox.
"""
import math

import bpy
from mathutils import Euler, Matrix, Vector

import lib_build as B
import lib_ship as L

RAD = math.radians
FILL = B.FILL
AMBER = (1.0, 0.62, 0.25)
CRT_GLOW = (0.9, 0.75, 0.5)
RED = (1.0, 0.07, 0.03)

SEAT_PIVOT = Vector((0.0, 7.75, 0.0))


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def M(loc=(0, 0, 0), rot=(0, 0, 0)):
    return Matrix.Translation(Vector(loc)) @ Euler(rot).to_matrix().to_4x4()


def tag(ob, **props):
    ob["stage"] = "props"
    for k, v in props.items():
        ob[k] = v
    return ob


def put(name, mb, coll, loc=(0, 0, 0), rot=(0, 0, 0), parent=None, **props):
    ob = B.obj(name, mb, coll, loc, rot, parent=parent)
    return tag(ob, **props)


def put_matrix(name, mb, coll, matrix, parent=None, **props):
    loc, rq, _ = matrix.decompose()
    return put(name, mb, coll, loc, rq.to_euler(), parent=parent, **props)


def marker(name, coll, loc, rot=(0, 0, 0), display="ARROWS", size=0.2, **props):
    ob = bpy.data.objects.get(name)
    if ob is not None and ob.type != "EMPTY":
        bpy.data.objects.remove(ob, do_unlink=True)
        ob = None
    if ob is None:
        ob = bpy.data.objects.new(name, None)
    L.link_only(ob, coll)
    ob.empty_display_type = display
    ob.empty_display_size = size
    ob.location = loc
    ob.rotation_euler = rot
    return tag(ob, **props)


def screen_quad(mb, w, h, mat, y=0.0, facing=-1):
    """Quad centred on the origin in the XZ plane. facing=-1: normal -Y (viewer
    at -Y sees +X to the right); facing=+1: normal +Y. UV (0,0) = viewer's bottom-left."""
    hw, hh = w / 2, h / 2
    if facing < 0:
        pts = [(-hw, y, -hh), (hw, y, -hh), (hw, y, hh), (-hw, y, hh)]
    else:
        pts = [(hw, y, -hh), (-hw, y, -hh), (-hw, y, hh), (hw, y, hh)]
    return mb.fill_quad(*pts, mat)


def up_quad(mb, x0, y0, x1, y1, z, mat):
    """Quad facing +Z with UV (0,0) at (x0, y0)."""
    return mb.fill_quad((x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z), mat)


def glow(center, normal, size, power, color=AMBER):
    return {"center": list(center), "normal": list(normal), "size": list(size), "power": power,
            "color": list(color)}


# ---------------------------------------------------------------------------
# workstation (ROOM_command)
# ---------------------------------------------------------------------------
DESK_PROFILE = [(0.90, 0.0), (0.90, 1.82), (0.62, 1.82), (0.58, 1.78), (0.52, 0.98), (0.24, 0.79),
                (0.02, 0.79), (0.0, 0.77), (0.0, 0.72), (0.36, 0.72), (0.36, 0.10), (0.40, 0.10),
                (0.40, 0.0)]
DESK_BANDS = ["panel_teal", "gunmetal", "steel", "gunmetal", "console", "rubber", "steel", "steel",
              "gunmetal", "panel_teal", "gunmetal", "gunmetal"]
DESK_Y0 = 0.62          # front lip distance from the seat pivot on the centre facet
SLOPE_TILT = math.atan2(0.98 - 0.79, 0.52 - 0.24)   # ~34 degrees


def desk_path():
    c = 0.5
    d1 = Vector((math.cos(RAD(-30)), math.sin(RAD(-30))))
    d2 = Vector((math.cos(RAD(-60)), math.sin(RAD(-60))))
    p0 = Vector((c, DESK_Y0))
    p1 = p0 + d1 * 0.8
    p2 = p1 + d2 * 0.35
    right = [p0, p1, p2]
    left = [Vector((-p.x, p.y)) for p in reversed(right)]
    return [(p.x, p.y) for p in left + right]


def facet(side):
    """(frame matrix at the facet's lip midpoint, yaw) for 'center', 'left', 'right'."""
    if side == "center":
        return Vector((0.0, DESK_Y0)), 0.0
    path = desk_path()
    a, b = (Vector(path[3]), Vector(path[4])) if side == "right" else (Vector(path[1]), Vector(path[2]))
    mid = (a + b) / 2
    yaw = RAD(-30) if side == "right" else RAD(30)
    return mid, yaw


def facet_point(side, r, z):
    mid, yaw = facet(side)
    nl = Vector((-math.sin(yaw), math.cos(yaw)))
    p = mid + nl * r
    return Vector((p.x, p.y, z)), yaw


def crt_unit(mb, w, h, bz=0.065, depth=0.12, body=0.32):
    """CRT monitor in the current frame: screen plane at y = 0 facing -Y."""
    hw, hh = w / 2, h / 2
    ow, oh = hw + bz, hh + bz
    f0, f1 = -0.035, depth - 0.035
    mb.cbox((-ow, f0 - 0.05, hh), (ow, f1, oh), 0.015, band="console", bands={"-y": "console"})
    mb.cbox((-ow, f0, -oh), (ow, f1, -hh), 0.015, band="console")
    mb.cbox((-ow, f0, -hh), (-hw, f1, hh), 0.015, band="console")
    mb.cbox((hw, f0, -hh), (ow, f1, hh), 0.015, band="console")
    mb.cbox((-ow + 0.05, f1 - 0.01, -oh + 0.05), (ow - 0.05, f1 + body, oh - 0.05), 0.03, band="gunmetal",
            skip=("-y",))
    # a small status lamp on the bottom bezel
    mb.fill_quad((hw - 0.05, f0 - 0.001, -oh + 0.02), (hw - 0.02, f0 - 0.001, -oh + 0.02),
                 (hw - 0.02, f0 - 0.001, -oh + 0.035), (hw - 0.05, f0 - 0.001, -oh + 0.035), "MAT_emit_amber")


def build_workstation(coll):
    P = SEAT_PIVOT
    mb = B.MB()
    mb.sweep(desk_path(), DESK_PROFILE, DESK_BANDS, caps=True, cap_band="panel_teal")

    screens = {
        "SCREEN_mission": ("center", 0.72, 0.54, 1.38),
        "SCREEN_status": ("left", 0.48, 0.36, 1.34),
        "SCREEN_aux": ("right", 0.48, 0.36, 1.34),
    }
    screen_frames = {}
    for name, (side, w, h, zc) in screens.items():
        p, yaw = facet_point(side, 0.50, zc)
        fr = M(p, (RAD(-8), 0, yaw))
        screen_frames[name] = (fr, w, h)
        with mb.at(rot=fr):
            crt_unit(mb, w, h)

    # ---- control surfaces on the three slope facets
    rz = 0.885
    rr = 0.38
    btn_frames = []
    for side in ("center", "left", "right"):
        p, yaw = facet_point(side, rr, rz)
        fr = M(p, (SLOPE_TILT, 0, yaw))
        with mb.at(rot=fr):
            mb.cbox((-0.47 if side == "center" else -0.3, -0.11, -0.012), (0.47 if side == "center" else 0.3, 0.11, 0.012),
                    0.008, band="gunmetal", skip=("-z",))
            if side == "center":
                for i in range(8):
                    x = -0.40 + 0.075 * i
                    mb.cbox((x - 0.031, -0.031, 0.012), (x + 0.031, 0.031, 0.02), 0.004, band="steel", skip=("-z",))
                    up_quad(mb, x - 0.008, 0.05, x + 0.008, 0.062, 0.0125,
                            "MAT_emit_amber" if i % 3 != 1 else "MAT_display")
                    btn_frames.append((f"BTN_console_{i + 1:02d}", fr @ M((x, 0, 0.042)), 0.046, 0.022))
                mb.cbox((0.24, -0.06, 0.012), (0.36, 0.06, 0.022), 0.006, band="steel", skip=("-z",))
                btn_frames.append(("BTN_console_main", fr @ M((0.30, 0, 0.052)), 0.09, 0.03))
            elif side == "left":
                # toggle switches + a small readout
                for i in range(6):
                    x = -0.22 + i * 0.07
                    mb.cbox((x - 0.018, -0.07, 0.012), (x + 0.018, -0.03, 0.024), 0.004, band="steel", skip=("-z",))
                    with mb.at((x, -0.05, 0.024), rot=Euler((RAD(-25 if i % 2 else 25), 0, 0))):
                        mb.cbox((-0.005, -0.005, 0.0), (0.005, 0.005, 0.045), 0.002, band="steel", skip=("-z",))
                up_quad(mb, -0.2, 0.0, 0.2, 0.09, 0.0125, "MAT_display")
            else:
                # rotary knobs + a small readout
                for i in range(3):
                    x = -0.16 + i * 0.16
                    with mb.at((x, -0.05, 0.012)):
                        mb.lathe([(0, 0), (0.032, 0), (0.032, 0.012), (0.024, 0.03), (0, 0.03)], 12, band="rubber")
                        mb.box((-0.003, 0.012, 0.03), (0.003, 0.028, 0.032), band="steel", skip=("-z",))
                up_quad(mb, -0.2, 0.0, 0.2, 0.09, 0.0125, "MAT_display")

    # ---- keyboard on the centre desk top
    kz = 0.79
    mb.cbox((-0.26, DESK_Y0 + 0.055, kz - 0.005), (0.26, DESK_Y0 + 0.215, kz + 0.025), 0.008, band="console",
            skip=("-z",))
    for r in range(3):
        for c in range(13):
            x = -0.216 + c * 0.036
            y = DESK_Y0 + 0.085 + r * 0.04
            mb.box((x - 0.014, y - 0.014, kz + 0.025), (x + 0.014, y + 0.014, kz + 0.037), band="rubber", skip=("-z",))

    # ---- droid-control joystick on the right desk top
    jp, jyaw = facet_point("right", 0.13, kz)
    with mb.at(jp):
        mb.lathe([(0, 0), (0.065, 0), (0.065, 0.02), (0.05, 0.035), (0, 0.035)], 14, band="gunmetal")
        mb.lathe([(0, 0.035), (0.034, 0.035), (0.014, 0.085), (0, 0.085)], 10, band="rubber")
        mb.tube([(0, 0, 0.08), (0, 0, 0.13)], 0.009, 8, band="steel")
        mb.lathe([(0, 0.125), (0.02, 0.125), (0.024, 0.175), (0.017, 0.205), (0, 0.21)], 10, band="rubber")
        mb.cbox((-0.008, 0.012, 0.19), (0.008, 0.026, 0.2), 0.003, band=FILL, mat="MAT_emit_amber")

    # ---- cable run from the back of the desk into the wall
    for dx in (-0.35, -0.3, 0.3, 0.36):
        mb.tube([(dx, 1.45, 0.3), (dx, 1.75, 0.3), (dx, 1.95, 0.55), (dx, 2.18, 0.55)], 0.03, 8, band="rubber")

    desk = put("WORKSTATION_desk", mb, coll, P, static=True)

    for name, (fr, w, h) in screen_frames.items():
        smb = B.MB()
        screen_quad(smb, w, h, "MAT_screen")
        wm = Matrix.Translation(P) @ fr
        put_matrix(name, smb, coll, wm, dynamic=True,
                   glow=glow((0, -0.01, 0), (0, -1, 0), (w, h), 5.0 if name == "SCREEN_mission" else 3.0, CRT_GLOW))

    for name, fr, size, height in btn_frames:
        bmb = B.MB()
        top = ("+z", (FILL, "MAT_emit_amber")) if name == "BTN_console_main" else ("+z", "console")
        bmb.cbox((-size / 2, -size / 2, -height), (size / 2, size / 2, 0.0), 0.004 if size < 0.06 else 0.008,
                 band="rubber", bands={top[0]: top[1]}, skip=("-z",))
        put_matrix(name, bmb, coll, Matrix.Translation(P) @ fr, dynamic=True, interactive=True)

    # ---- seat
    smb = B.MB()
    smb.lathe([(0, 0), (0.3, 0), (0.3, 0.025), (0.22, 0.045), (0, 0.05)], 16, band="gunmetal")
    smb.tube([(0, 0, 0.04), (0, 0, 0.4)], 0.045, 10, band="steel")
    smb.cbox((-0.25, -0.24, 0.38), (0.25, 0.24, 0.46), 0.02, band="gunmetal")
    smb.cbox((-0.23, -0.22, 0.46), (0.23, 0.25, 0.53), 0.03, band="rubber")
    with smb.at((0, -0.25, 0.5), rot=Euler((RAD(-12), 0, 0))):
        smb.cbox((-0.04, -0.03, 0.0), (0.04, 0.02, 0.18), 0.01, band="steel")
        smb.cbox((-0.23, -0.06, 0.12), (0.23, 0.03, 0.66), 0.035, band="rubber")
        smb.cbox((-0.15, -0.06, 0.7), (0.15, 0.03, 0.86), 0.03, band="rubber")
        smb.cbox((-0.03, -0.04, 0.62), (0.03, 0.0, 0.72), 0.008, band="steel")
    for sx in (-1, 1):
        smb.cbox((sx * 0.26 - 0.02, -0.12, 0.46), (sx * 0.26 + 0.02, -0.08, 0.66), 0.008, band="steel")
        smb.cbox((sx * 0.26 - 0.035, -0.2, 0.66), (sx * 0.26 + 0.035, 0.16, 0.7), 0.012, band="rubber")
    put("PROP_workstation_seat", smb, coll, (P.x, P.y - 0.03, 0.0), static=True)

    marker("SEAT_workstation", coll, (P.x, P.y - 0.03, 0.53), eye_height=0.72, kind="seat")
    cp, _ = facet_point("center", rr, rz)
    marker("INTERACT_workstation", coll, tuple(P + cp + Vector((0, 0, 0.05))), size=0.12,
           target="WORKSTATION_desk", radius=1.2)
    return desk


# ---------------------------------------------------------------------------
# cryo pods (ROOM_cryo)
# ---------------------------------------------------------------------------
POD_OUTER = [(-0.4, -0.48), (0.4, -0.48), (0.53, -0.3), (0.53, 0.36), (-0.53, 0.36), (-0.53, -0.3)]
POD_CAVITY = [(-0.34, -0.38), (0.34, -0.38), (0.44, -0.26), (0.44, 0.36), (-0.44, 0.36), (-0.44, -0.26)]
POD_PLINTH = [(-0.45, -0.5), (0.45, -0.5), (0.56, -0.35), (0.56, 0.45), (0.46, 0.55), (-0.46, 0.55),
              (-0.56, 0.45), (-0.56, -0.35)]
POD_GLASS_Z = (0.3, 2.25)     # cavity is tall enough for a 1.7 m eye height standing on the footplate
POD_HINGE = (-0.365, 0.40)
POD_STATUS = (0.46, 0.501, 1.33)
POD_NAMEPLATE = (0.0, 0.471, 2.435)


def pod_body():
    mb = B.MB()
    mb.prism(POD_PLINTH, 0.0, 0.16, band="gunmetal", caps=(False, True))
    mb.cbox((-0.4, 0.5, 0.0), (0.4, 0.82, 0.1), 0.012, band="gunmetal", bands={"+z": "steel", "+y": "hazard"},
            skip=("-z",))
    top = POD_GLASS_Z[1]            # cavity / glass top
    shell = top + 0.12             # top rail / shell top
    mb.prism(POD_OUTER, 0.16, shell, band="console", caps=(False, True), skip_sides=(3,))
    B.MB.flip(mb.prism(POD_CAVITY, 0.3, top, band="panel_gray", skip_sides=(3,), cap_band="gunmetal"))
    # front frame
    mb.cbox((-0.53, 0.34, 0.16), (-0.37, 0.46, shell), 0.02, band="gunmetal", bands={"+y": "panel_teal"})
    mb.cbox((0.37, 0.34, 0.16), (0.53, 0.46, shell), 0.02, band="gunmetal", bands={"+y": "panel_teal"})
    mb.cbox((-0.37, 0.34, top), (0.37, 0.46, shell), 0.015, band="gunmetal", bands={"+y": "rivets"})
    mb.cbox((-0.37, 0.34, 0.16), (0.37, 0.46, 0.3), 0.015, band="gunmetal", bands={"+y": "hazard"})
    # hinge knuckles on the left stile
    for z in (0.55, 1.95):
        mb.cbox((-0.4, 0.44, z), (-0.35, 0.48, z + 0.12), 0.008, band="steel")
    # hood
    mb.cbox((-0.5, -0.45, shell), (0.5, 0.47, shell + 0.13), 0.035, band="gunmetal", bands={"+y": "gunmetal"})
    # status panel housing on the right stile
    mb.cbox((0.38, 0.44, 1.18), (0.54, 0.5, 1.46), 0.012, band="console", skip=("-y",))
    for z in (1.44, 1.2):
        mb.panel((0.41, 0.5005, z), (-1, 0, 0), (0, 0, 1), 0.02, 0.016, "MAT_emit_amber")
    # interior: back cushion, head rest, foot plate, light strip
    mb.cbox((-0.26, -0.38, 0.42), (0.26, -0.29, 1.95), 0.04, band="rubber", skip=("-y",))
    mb.cbox((-0.13, -0.38, 1.99), (0.13, -0.26, 2.13), 0.03, band="rubber", skip=("-y",))
    mb.cbox((-0.3, -0.29, 0.3), (0.3, 0.3, 0.33), 0.008, band="gunmetal", bands={"+z": "vent"}, skip=("-z",))
    zs = top - 0.003
    strip = mb.fill_quad((-0.3, 0.12, zs), (0.3, 0.12, zs), (0.3, 0.26, zs), (-0.3, 0.26, zs), "MAT_emit_amber")
    mb._orient([strip], (0, 0, -1))
    # side ribs
    for sx in (-1, 1):
        for z in (0.62, 1.3, 1.98):
            x0, x1 = (0.53, 0.56) if sx > 0 else (-0.56, -0.53)
            mb.cbox((x0, -0.3, z), (x1, 0.34, z + 0.06), 0.01, band="gunmetal")
    # coolant hoses into the wall behind the pod
    hz = shell + 0.13
    for x in (-0.22, 0.22):
        mb.tube([(x, -0.3, hz - 0.02), (x, -0.3, hz + 0.04), (x, -0.48, 2.6), (x, -0.67, 2.6)], 0.035, 8,
                band="ribbed")
        with mb.at((x, -0.3, hz - 0.02)):
            mb.lathe([(0, 0), (0.05, 0), (0.05, 0.04), (0, 0.04)], 10, band="steel")
    return mb


def pod_glass():
    mb = B.MB()
    z0, z1 = POD_GLASS_Z
    h = z1 - z0
    xs = [0.01, 0.25, 0.49, 0.73]
    ys = [0.0, 0.035, 0.035, 0.0]
    for i in range(3):
        f = mb.face([(xs[i], ys[i], 0.0), (xs[i + 1], ys[i + 1], 0.0), (xs[i + 1], ys[i + 1], h),
                     (xs[i], ys[i], h)], band="steel", mat="MAT_glass_frost")
        mb._orient([f], (0, 1, 0))
    # steel rim so it reads as a door
    mb.cbox((0.0, -0.012, 0.0), (0.74, 0.02, 0.03), 0.006, band="steel")
    mb.cbox((0.0, -0.012, h - 0.03), (0.74, 0.02, h), 0.006, band="steel")
    mb.cbox((0.0, -0.012, 0.03), (0.03, 0.02, h - 0.03), 0.006, band="steel")
    mb.cbox((0.71, -0.012, 0.03), (0.74, 0.02, h - 0.03), 0.006, band="steel")
    mb.cbox((0.66, 0.02, h / 2 - 0.15), (0.69, 0.05, h / 2 + 0.15), 0.008, band="steel")   # handle
    return mb


def build_cryo(coll):
    body = pod_body().finish("MOD_cryo_pod")
    glass = pod_glass().finish("MOD_cryo_pod_glass")
    smb = B.MB()
    screen_quad(smb, 0.12, 0.2, "MAT_display", facing=1)
    status = smb.finish("MOD_cryo_pod_status")
    nmb = B.MB()
    screen_quad(nmb, 0.36, 0.068, "MAT_nameplate", facing=1)
    nameplate = nmb.finish("MOD_cryo_pod_nameplate")

    xs = [-6.7, -8.0, -9.3]
    slots = [(x, 2.35, math.pi) for x in xs] + [(x, -2.35, 0.0) for x in reversed(xs)]
    pods = []
    for i, (x, y, rz) in enumerate(slots):
        n = f"CRYO_POD_{i + 1:02d}"
        pod = put(n, body, coll, (x, y, 0.0), (0, 0, rz), static=True, module="MOD_cryo_pod",
                  glow=glow((0, 0.19, POD_GLASS_Z[1] - 0.02), (0, 0, -1), (0.5, 0.12), 3.0))
        put(n + "_glass", glass, coll, (POD_HINGE[0], POD_HINGE[1], POD_GLASS_Z[0]), parent=pod,
            dynamic=True, hinge_axis="local Z", module="MOD_cryo_pod_glass")
        put(n + "_status", status, coll, POD_STATUS, parent=pod, dynamic=True,
            glow=glow((0, 0.01, 0), (0, 1, 0), (0.12, 0.2), 0.8))
        put(n + "_nameplate", nameplate, coll, POD_NAMEPLATE, parent=pod, dynamic=True)
        mw = pod.matrix_basis
        sp = mw @ Vector(POD_STATUS)
        marker(f"INTERACT_cryo_pod_{i + 1:02d}", coll, tuple(sp + (mw.to_3x3() @ Vector((0, 0.05, 0)))),
               (0, 0, rz), size=0.1, target=n, radius=0.9)
        pods.append(pod)
    p1 = pods[0]
    marker("SPAWN_player", coll, tuple(p1.matrix_basis @ Vector((0, 0.0, 0.33))), (0, 0, p1.rotation_euler.z),
           size=0.3, eye_height=L.EYE_H, kind="spawn", inside="CRYO_POD_01")
    return pods


# ---------------------------------------------------------------------------
# core computer (ROOM_engineering)
# ---------------------------------------------------------------------------
def rack_base(mb):
    mb.cbox((-0.38, -0.83, 0.0), (0.38, -0.06, 0.08), 0.01, band="gunmetal", skip=("-z", "-y"))
    mb.cbox((-0.4, -0.85, 0.08), (0.4, -0.02, 2.25), 0.02, band="gunmetal",
            bands={"+x": "panel_gray", "-x": "panel_gray"}, skip=("-y", "-z"))
    mb.cbox((-0.42, -0.87, 2.25), (0.42, 0.02, 2.34), 0.02, band="gunmetal", bands={"+y": "rivets"}, skip=("-y",))
    for x0, x1 in ((-0.4, -0.34), (0.34, 0.4)):
        mb.cbox((x0, -0.04, 0.08), (x1, 0.03, 2.25), 0.012, band="gunmetal", bands={"+y": "rivets"}, skip=("-y",))
    mb.cbox((-0.34, -0.03, 0.14), (0.34, 0.0, 0.95), 0.01, band="gunmetal", bands={"+y": "vent"}, skip=("-y",))
    # cable bundle from the top into the ceiling
    for dx in (-0.2, -0.12, 0.15):
        mb.tube([(dx, -0.45, 2.33), (dx, -0.45, 2.55), (dx, -0.62, 2.82)], 0.022, 6, band="rubber")


def reel(mb, loc):
    with mb.at(loc, rot=Euler((RAD(-90), 0, 0))):
        mb.lathe([(0, 0), (0.12, 0), (0.12, 0.005), (0, 0.005)], 16, band="steel")
        mb.lathe([(0, 0.005), (0.085, 0.005), (0.085, 0.03), (0, 0.03)], 16, band="rubber")
        mb.lathe([(0.1, 0.03), (0.12, 0.03), (0.12, 0.035), (0.1, 0.035), (0.1, 0.03)], 16, band="steel")
        mb.lathe([(0, 0.03), (0.026, 0.03), (0.026, 0.05), (0, 0.05)], 10, band="steel")
        for k in range(3):
            with mb.at(rot_z=RAD(120 * k)):
                mb.box((0.024, -0.01, 0.03), (0.1, 0.01, 0.036), band="steel", skip=("-z",))


def rack_tape():
    mb = B.MB()
    rack_base(mb)
    # window frame
    mb.cbox((-0.34, -0.03, 2.05), (0.34, 0.04, 2.13), 0.01, band="gunmetal", skip=("-y",))
    mb.cbox((-0.34, -0.03, 1.3), (0.34, 0.04, 1.38), 0.01, band="gunmetal", skip=("-y",))
    mb.cbox((-0.34, -0.03, 1.38), (-0.29, 0.04, 2.05), 0.01, band="gunmetal", skip=("-y",))
    mb.cbox((0.29, -0.03, 1.38), (0.34, 0.04, 2.05), 0.01, band="gunmetal", skip=("-y",))
    reel(mb, (-0.14, -0.015, 1.76))
    reel(mb, (0.14, -0.015, 1.76))
    mb.cbox((-0.05, -0.02, 1.47), (0.05, 0.02, 1.54), 0.008, band="steel")
    for x in (-0.09, 0.09):
        with mb.at((x, -0.02, 1.5), rot=Euler((RAD(-90), 0, 0))):
            mb.lathe([(0, 0), (0.018, 0), (0.018, 0.03), (0, 0.03)], 10, band="steel")
    # control strip
    mb.cbox((-0.34, -0.03, 1.02), (0.34, 0.02, 1.28), 0.01, band="console", skip=("-y",))
    for i in range(5):
        x = -0.24 + i * 0.12
        mb.cbox((x - 0.035, 0.02, 1.08), (x + 0.035, 0.045, 1.16), 0.006, band="rubber", skip=("-y",))
        mb.panel((x, 0.0205, 1.225), (-1, 0, 0), (0, 0, 1), 0.024, 0.03,
                 "MAT_emit_amber" if i % 2 == 0 else "MAT_display")
    return mb


def rack_cartridge():
    mb = B.MB()
    rack_base(mb)
    # CRT readout
    w, h = 0.46, 0.34
    with mb.at((0, 0.0, 1.84), rot=Euler((0, 0, math.pi))):
        crt_unit(mb, w, h, bz=0.05, depth=0.07, body=0.05)
    cz = 1.84
    mb.panel((0, 0.0, cz), (-1, 0, 0), (0, 0, 1), w, h, "MAT_display")
    # cartridge bay: chunky housing around a slot
    sz, sh, sw = 1.22, 0.04, 0.28
    y0, y1 = -0.03, 0.12
    mb.cbox((-0.22, y0, sz + sh / 2), (0.22, y1, 1.38), 0.015, band="gunmetal", bands={"+y": "steel"}, skip=("-y",))
    mb.cbox((-0.22, y0, 1.04), (0.22, y1, sz - sh / 2), 0.015, band="gunmetal", bands={"+y": "steel"}, skip=("-y",))
    mb.cbox((-0.22, y0, sz - sh / 2), (-sw / 2, y1, sz + sh / 2), 0.004, band="gunmetal", skip=("-y", "-z", "+z"))
    mb.cbox((sw / 2, y0, sz - sh / 2), (0.22, y1, sz + sh / 2), 0.004, band="gunmetal", skip=("-y", "-z", "+z"))
    back = mb.face([(-sw / 2, 0.0, sz - sh / 2), (sw / 2, 0.0, sz - sh / 2), (sw / 2, 0.0, sz + sh / 2),
                    (-sw / 2, 0.0, sz + sh / 2)], band="rubber")
    mb._orient([back], (0, 1, 0))
    for zz, nz in ((sz - sh / 2, 1), (sz + sh / 2, -1)):
        f = mb.face([(-sw / 2, 0.0, zz), (sw / 2, 0.0, zz), (sw / 2, y1, zz), (-sw / 2, y1, zz)], band="rubber")
        mb._orient([f], (0, 0, nz))
    mb.panel((0, y1 + 0.001, 1.1715), (-1, 0, 0), (0, 0, 1), 0.24, 0.013, "MAT_emit_amber")
    mb.cbox((-0.16, 0.0, 1.42), (0.16, 0.018, 1.49), 0.004, band="label", bands={"+y": "label"}, skip=("-y",))
    return mb


def rack_lamps():
    mb = B.MB()
    rack_base(mb)
    mb.cbox((-0.33, -0.03, 1.36), (0.33, 0.01, 2.12), 0.01, band="gunmetal", skip=("-y",))
    for c in range(6):
        for r in range(8):
            x = -0.25 + c * 0.1
            z = 1.44 + r * 0.085
            lit = (c * 7 + r * 3) % 5 < 2
            mb.panel((x, 0.0105, z), (-1, 0, 0), (0, 0, 1), 0.05, 0.03, "MAT_emit_amber" if lit else "MAT_display")
    mb.cbox((-0.34, -0.03, 1.02), (0.34, 0.02, 1.3), 0.01, band="console", skip=("-y",))
    for i in range(8):
        x = -0.27 + i * 0.077
        mb.cbox((x - 0.02, 0.02, 1.13), (x + 0.02, 0.035, 1.19), 0.004, band="steel", skip=("-y",))
        with mb.at((x, 0.035, 1.16), rot=Euler((RAD(-90 + (20 if i % 3 else -20)), 0, 0))):
            mb.cbox((-0.005, -0.005, 0.0), (0.005, 0.005, 0.05), 0.002, band="steel", skip=("-z",))
    mb.cbox((-0.2, 0.02, 1.235), (0.2, 0.03, 1.28), 0.003, band="label", bands={"+y": "label"}, skip=("-y",))
    return mb


def build_core(coll):
    tape = rack_tape().finish("MOD_core_rack_tape")
    cart = rack_cartridge().finish("MOD_core_rack_cartridge")
    lamps = rack_lamps().finish("MOD_core_rack_lamps")
    x = 10.02
    rot = (0, 0, math.pi / 2)
    specs = [("CORE_rack_01", tape, 1.2, glow((0, 0.03, 1.23), (0, 1, 0), (0.5, 0.06), 0.8)),
             ("CORE_rack_02", lamps, 0.4, glow((0, 0.02, 1.74), (0, 1, 0), (0.55, 0.62), 2.0)),
             ("CORE_rack_03", cart, -0.4, glow((0, 0.01, 1.84), (0, 1, 0), (0.46, 0.34), 2.0)),
             ("CORE_rack_04", tape, -1.2, glow((0, 0.03, 1.23), (0, 1, 0), (0.5, 0.06), 0.8))]
    racks = []
    for name, mesh, y, gl in specs:
        racks.append(put(name, mesh, coll, (x, y, 0.0), rot, static=True, module=mesh.name, glow=gl))
    slot = racks[2].matrix_basis @ Vector((0, 0.13, 1.22))
    marker("INTERACT_core_cartridge", coll, tuple(slot), rot, size=0.1, target="CORE_rack_03", radius=0.8)
    return racks


# ---------------------------------------------------------------------------
# blinking button panel (ROOM_engineering, north wall)
# ---------------------------------------------------------------------------
BLINK_LOC = Vector((9.0, 3.0, 0.0))


def build_blink_panel(coll):
    mb = B.MB()
    mb.cbox((-0.36, -0.01, 1.16), (0.36, 0.05, 2.02), 0.015, band="gunmetal", bands={"+y": "panel_gray"}, skip=("-y",))
    for mn, mx in (((-0.36, 0.04, 1.96), (0.36, 0.08, 2.02)), ((-0.36, 0.04, 1.16), (0.36, 0.08, 1.22)),
                   ((-0.36, 0.04, 1.22), (-0.3, 0.08, 1.96)), ((0.3, 0.04, 1.22), (0.36, 0.08, 1.96))):
        mb.cbox(mn, mx, 0.008, band="gunmetal", bands={"+y": "hazard"}, skip=("-y",))
    with mb.at((0, 0.05, 1.5), rot=Euler((RAD(-90), 0, 0))):
        mb.lathe([(0.10, 0.0), (0.13, 0.0), (0.13, 0.055), (0.10, 0.055), (0.10, 0.0)], 20, band="steel")
        mb.lathe([(0, 0.0), (0.1, 0.0), (0.1, 0.008), (0, 0.008)], 20, band="gunmetal")
    with mb.at((0, 0.05, 1.8), rot=Euler((RAD(-90), 0, 0))):
        mb.lathe([(0, 0), (0.065, 0), (0.065, 0.03), (0, 0.03)], 14, band="steel")
        mb.lathe([(0, 0.03), (0.05, 0.03), (0.05, 0.055), (0.036, 0.09), (0, 0.1)], 14,
                 band=[FILL] * 4, mat=["MAT_emit_blink"] * 4)
        for k in range(2):
            with mb.at(rot_z=RAD(90 * k)):
                mb.box((-0.058, -0.005, 0.03), (-0.05, 0.005, 0.098), band="steel")
                mb.box((0.05, -0.005, 0.03), (0.058, 0.005, 0.098), band="steel")
                mb.box((-0.058, -0.005, 0.098), (0.058, 0.005, 0.106), band="steel")
    mb.cbox((-0.2, 0.05, 1.27), (0.2, 0.066, 1.33), 0.004, band="label", bands={"+y": "label"}, skip=("-y",))
    mb.tube([(0.26, 0.03, 2.02), (0.26, 0.03, 2.3), (0.26, -0.02, 2.36)], 0.025, 8, band="ribbed")
    panel = put("PANEL_blink", mb, coll, BLINK_LOC, (0, 0, math.pi), static=True)

    bmb = B.MB()
    prof = [(0, -0.075), (0.045, -0.075), (0.045, -0.04), (0.08, -0.035), (0.08, -0.018), (0.062, -0.004), (0, 0.0)]
    bmb.lathe(prof, 20, band=["gunmetal", "gunmetal", "gunmetal", FILL, FILL, FILL],
              mat=["MAT_trim", "MAT_trim", "MAT_trim", "MAT_emit_blink", "MAT_emit_blink", "MAT_emit_blink"])
    btn_loc = BLINK_LOC + Vector((0, -(0.05 + 0.075), 1.5))
    put("BTN_blink", bmb, coll, btn_loc, (math.pi / 2, 0, 0), dynamic=True, interactive=True)
    lamp = BLINK_LOC + Vector((0, -(0.05 + 0.065), 1.8))
    marker("LIGHT_BLINK_engineering", coll, tuple(lamp), (math.pi / 2, 0, 0), display="SPHERE", size=0.06,
           light_type="point", color=list(RED), intensity=2.0, range=4.0, blink_hz=1.0)
    marker("INTERACT_blink_button", coll, tuple(btn_loc), (0, 0, math.pi), size=0.12, target="BTN_blink", radius=0.9)
    return panel


# ---------------------------------------------------------------------------
# droid charging dock (ROOM_corridor, alcove south of the junction)
# ---------------------------------------------------------------------------
DOCK_LOC = Vector((0.0, -1.3, 0.0))


def build_dock(coll):
    mb = B.MB()
    mb.cbox((-0.45, -0.3, 0.0), (0.45, 0.36, 0.05), 0.01, band="gunmetal", bands={"+z": "vent", "+y": "hazard"},
            skip=("-z",))
    for x in (-0.22, 0.22):
        up_quad(mb, x - 0.02, -0.2, x + 0.02, 0.2, 0.0505, "MAT_emit_amber")
    mb.cbox((-0.3, -0.42, 0.25), (0.3, -0.2, 0.8), 0.02, band="console", skip=("-y",))
    mb.cbox((-0.05, -0.2, 0.42), (0.05, -0.06, 0.5), 0.008, band="steel", skip=("-y",))
    mb.cbox((-0.075, -0.06, 0.4), (0.075, -0.02, 0.52), 0.01, band="gunmetal", bands={"+y": "hazard"})
    mb.panel((-0.11, -0.1995, 0.67), (-1, 0, 0), (0, 0, 1), 0.22, 0.14, "MAT_display")
    for i, x in enumerate((0.08, 0.14, 0.2)):
        mb.panel((x, -0.1995, 0.705), (-1, 0, 0), (0, 0, 1), 0.03, 0.03, "MAT_emit_amber" if i != 1 else "MAT_display")
    for x in (-0.18, 0.18):
        mb.tube([(x, -0.32, 0.8), (x, -0.32, 1.1), (x, -0.36, 1.4)], 0.03, 8, band="rubber")
    mb.cbox((-0.25, -0.4, 1.02), (0.25, -0.34, 1.1), 0.006, band="label", bands={"+y": "label"})
    dock = put("DOCK_droid", mb, coll, DOCK_LOC, static=True,
               glow=glow((-0.11, -0.19, 0.67), (0, 1, 0), (0.22, 0.14), 0.6))
    marker("SPAWN_droid", coll, tuple(DOCK_LOC + Vector((0, 0, 0.05))), (0, 0, 0), size=0.25, kind="spawn")
    marker("INTERACT_droid_dock", coll, tuple(DOCK_LOC + Vector((0, -0.18, 0.62))), (0, 0, 0), size=0.1,
           target="DOCK_droid", radius=1.0)
    return dock


# ---------------------------------------------------------------------------
# doors, alarm beacons
# ---------------------------------------------------------------------------
def door_mesh():
    mb = B.MB()
    hw = L.DOOR_W / 2
    mb.cbox((-hw, -0.025, 0.0), (hw, 0.025, L.DOOR_H), 0.015, band="gunmetal",
            bands={"+y": "panel_teal", "-y": "panel_teal"})
    for sy in (1, -1):
        y0, y1 = (0.025, 0.035) if sy > 0 else (-0.035, -0.025)
        skip = ("-y",) if sy > 0 else ("+y",)
        for z in (0.35, 1.05, 1.75):
            mb.cbox((-0.4, y0, z - 0.045), (0.46, y1, z + 0.045), 0.004, band="rivets",
                    bands={"+y": "rivets", "-y": "rivets"}, skip=skip)
        mb.cbox((-hw + 0.01, y0, 0.05), (-0.42, y1, L.DOOR_H - 0.05), 0.004, band="hazard",
                bands={"+y": "hazard", "-y": "hazard"}, skip=skip)
    return mb.finish("MOD_door")


def beacon_mesh():
    mb = B.MB()
    prof = [(0, -0.16), (0.035, -0.15), (0.05, -0.12), (0.05, -0.07), (0.07, -0.07), (0.07, -0.03),
            (0.08, -0.03), (0.08, 0.0), (0, 0.0)]
    mb.lathe(prof, 16, band=[FILL, FILL, FILL, "gunmetal", "gunmetal", "gunmetal", "gunmetal", "gunmetal"],
             mat=["MAT_emit_red"] * 3 + ["MAT_trim"] * 5)
    for k in range(2):
        with mb.at(rot_z=RAD(90 * k)):
            mb.box((-0.062, -0.005, -0.172), (0.062, 0.005, -0.164), band="steel")
            for x in (-0.062, 0.054):
                mb.box((x, -0.005, -0.164), (x + 0.008, 0.005, -0.07), band="steel")
    return mb.finish("MOD_alarm_beacon")


def build_doors_and_beacons(rooms):
    dm = door_mesh()
    doors = [("DOOR_command", "ROOM_command", (0.0, 4.9, 0.0), 0.0),
             ("DOOR_cryo", "ROOM_cryo", (-4.9, 0.0, 0.0), math.pi / 2),
             ("DOOR_engineering", "ROOM_engineering", (4.9, 0.0, 0.0), -math.pi / 2)]
    for name, room, loc, rz in doors:
        old = bpy.data.objects.get(name)
        if old is not None:
            bpy.data.objects.remove(old, do_unlink=True)
        d = put(name, dm, rooms[room], loc, (0, 0, rz), dynamic=True, interactive=True, module="MOD_door",
                slide_axis="local +X", slide_distance=L.DOOR_W)
        marker("INTERACT_" + name.lower(), rooms[room],
               tuple(Vector(loc) + Vector((0, 0, 1.2))), (0, 0, rz), size=0.15, target=name, radius=1.2)

    bm = beacon_mesh()
    beacons = [("command", "ROOM_command", (1.0, 5.45, L.ROOM_H), 60.0),
               ("cryo", "ROOM_cryo", (-5.45, 1.0, L.ROOM_H), 60.0),
               ("engineering", "ROOM_engineering", (5.45, -1.0, L.ROOM_H), 60.0),
               ("corridor", "ROOM_corridor", (0.55, -0.55, L.CORR_H), 35.0)]
    for key, room, loc, power in beacons:
        put(f"BEACON_alarm_{key}", bm, rooms[room], loc, static=True, module="MOD_alarm_beacon")
        marker(f"LIGHT_alarm_{key}", rooms[room], tuple(Vector(loc) + Vector((0, 0, -0.115))), display="SPHERE",
               size=0.07, light_type="point", color=list(RED), intensity=3.0, range=6.0, rotate_hz=0.5,
               bake_power=power)


def tag_module_glows():
    """Door control panels are part of linked modules; tag their instances so the
    blackout bake gets a faint glow from each little display."""
    for ob in bpy.data.objects:
        mod = ob.get("module")
        if mod == "MOD_wall_door":
            ob["glow"] = glow((1.80, 0.08, 1.40), (0, 1, 0), (0.14, 0.12), 0.4)
        elif mod == "MOD_corr_endcap":
            ob["glow"] = glow((0.08, 0.78, 1.40), (1, 0, 0), (0.12, 0.14), 0.4)


# ---------------------------------------------------------------------------
def build():
    L.clear_objects(lambda o: o.get("stage") == "props")
    L.clear_objects(lambda o: o.name.startswith("GB_"))
    for me in [m for m in bpy.data.meshes if m.users == 0]:
        bpy.data.meshes.remove(me)
    rooms = {n: L.collection(n) for n in L.ROOM_COLLECTIONS}
    build_workstation(rooms["ROOM_command"])
    build_cryo(rooms["ROOM_cryo"])
    build_core(rooms["ROOM_engineering"])
    build_blink_panel(rooms["ROOM_engineering"])
    build_dock(rooms["ROOM_corridor"])
    build_doors_and_beacons(rooms)
    tag_module_glows()
    for me in [m for m in bpy.data.meshes if m.users == 0]:
        bpy.data.meshes.remove(me)
    return {c: len(rooms[c].objects) for c in rooms}
