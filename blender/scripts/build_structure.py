"""Step 3a: modular structure (walls, doors, corridor segments, floors, ceilings).

Each module is built once as a mesh named MOD_* and placed as linked duplicates.
Re-runnable: removes every object tagged stage == "structure" first and hides the
greybox.
"""
import math

import bpy
from mathutils import Vector

import lib_build as B
import lib_ship as L

FLOOR = B.FLOOR
T = L.WALL_T
H = L.ROOM_H

# Room wall cross-section (y toward the room, z up), traced floor -> ceiling.
WALL_PROFILE = [(0.06, 0.00), (0.06, 0.18), (0.02, 0.22), (0.02, 0.94), (0.08, 0.99), (0.08, 1.09),
                (0.00, 1.14), (0.00, 2.30), (0.04, 2.34), (0.04, 2.52), (0.00, 2.56), (0.00, 2.66),
                (0.12, 2.80)]
WALL_BANDS = ["gunmetal", "gunmetal", "panel_gray", "gunmetal", "rivets", "gunmetal", "panel_teal",
              "gunmetal", "vent", "gunmetal", "seam", "gunmetal"]

# Corridor cross-section loop (y across, z up); faces point into the corridor.
CORR_PROFILE = [(0.6, 0.0), (-0.6, 0.0), (-0.75, 0.0), (-0.9, 0.3), (-0.9, 0.95), (-0.86, 0.98),
                (-0.86, 1.08), (-0.9, 1.11), (-0.9, 1.9), (-0.6, 2.4), (0.6, 2.4), (0.9, 1.9),
                (0.9, 1.11), (0.86, 1.08), (0.86, 0.98), (0.9, 0.95), (0.9, 0.3), (0.75, 0.0),
                (0.6, 0.0)]
CORR_BANDS = [FLOOR, "vent", "gunmetal", "panel_gray", "gunmetal", "rivets", "gunmetal", "panel_teal",
              "panel_gray", "gunmetal", "panel_gray", "panel_teal", "gunmetal", "rivets", "gunmetal",
              "panel_gray", "gunmetal", "vent"]
CORR_MATS = ["MAT_floor"] + ["MAT_trim"] * 17
CORR_SEG = 1.3
CORR_OCTAGON = [(-0.75, 0.0), (-0.9, 0.3), (-0.9, 1.9), (-0.6, 2.4), (0.6, 2.4), (0.9, 1.9), (0.9, 0.3), (0.75, 0.0)]

DOOR_X0, DOOR_X1 = 0.5, 1.5        # door opening inside the 2 m door module
FRAME_W = 0.16
FRAME_FRONT = 0.14                 # frame stands this far into the room
DOOR_SLOT = (-0.14, -0.06)         # slot in the right jamb the door slides through


# ---------------------------------------------------------------------------
# Module builders
# ---------------------------------------------------------------------------
def _rib(mb, x=0.0, h=H):
    mb.cbox((x - 0.08, -0.03, 0.0), (x + 0.08, 0.13, h), 0.025, band="gunmetal",
            bands={"+y": "rivets"}, skip=("-y", "-z", "+z"))


def _bolts(mb, pts, y0, y1=None, s=0.018):
    y1 = y1 if y1 is not None else y0 + 0.012
    for x, z in pts:
        mb.cbox((x - s, y0, z - s), (x + s, y1, z + s), 0.005, band="steel", skip=("-y",))


def wall_module(width, variant="A"):
    mb = B.MB()
    mb.extrude_profile(WALL_PROFILE, 0.0, width, WALL_BANDS)
    _rib(mb)
    W = width
    if variant == "A" and W > 1.5:
        mb.box((W / 2 - 0.015, -0.01, 1.14), (W / 2 + 0.015, 0.012, 2.30), band="seam", skip=("-y", "-z", "+z"))
    elif variant == "B":
        # bolted service hatch on the upper panel, with a stencil plate
        mb.cbox((0.45, -0.01, 1.32), (W - 0.45, 0.028, 2.14), 0.012, band="gunmetal",
                bands={"+y": "panel_gray"}, skip=("-y",))
        _bolts(mb, [(0.52, 1.39), (W - 0.52, 1.39), (0.52, 2.07), (W - 0.52, 2.07)], 0.02, 0.036)
        mb.cbox((W / 2 - 0.2, 0.02, 1.98), (W / 2 + 0.2, 0.034, 2.06), 0.004, band="label",
                bands={"+y": "label"}, skip=("-y",))
    elif variant == "C":
        # low vent grille (return air)
        mb.cbox((0.35, 0.0, 0.3), (W - 0.35, 0.045, 0.8), 0.012, band="gunmetal",
                bands={"+y": "vent"}, skip=("-y",))
    return mb


def door_module():
    """2 m wall module with a 1.0 x 2.1 m opening at x 0.5..1.5 (room side)."""
    mb = B.MB()
    fx0, fx1 = DOOR_X0 - FRAME_W, DOOR_X1 + FRAME_W
    top = L.DOOR_H + FRAME_W
    mb.extrude_profile(WALL_PROFILE, 0.0, fx0, WALL_BANDS)
    mb.extrude_profile(WALL_PROFILE, fx1, 2.0, WALL_BANDS)
    mb.extrude_profile(WALL_PROFILE, fx0, fx1, WALL_BANDS, zclip=(top, H))
    _rib(mb)
    hz = {"+y": "hazard", "-x": "gunmetal", "+x": "gunmetal"}
    # jambs run through the wall (they line the opening); the right one is slotted
    mb.cbox((fx0, -T, 0.0), (DOOR_X0, FRAME_FRONT, L.DOOR_H), 0.02, bands=hz, skip=("-y", "-z", "+z"))
    mb.cbox((DOOR_X1, -T, 0.0), (fx1, DOOR_SLOT[0], L.DOOR_H), 0.01, skip=("-y", "-z", "+z"))
    mb.cbox((DOOR_X1, DOOR_SLOT[1], 0.0), (fx1, FRAME_FRONT, L.DOOR_H), 0.02, bands=hz, skip=("-z", "+z"))
    mb.cbox((fx0, -T, L.DOOR_H), (fx1, FRAME_FRONT, top), 0.02, bands={"+y": "rivets"}, skip=("-y",))
    # threshold plate with the door track
    mb.box((DOOR_X0, -T - 0.05, -0.02), (DOOR_X1, 0.06, 0.012), band="steel", skip=("-z",))
    # sign plate above the frame
    mb.cbox((0.7, 0.0, top + 0.08), (1.3, 0.05, top + 0.26), 0.01, bands={"+y": "label"}, skip=("-y",))
    # door control panel on the right flank
    mb.cbox((fx1 + 0.04, 0.0, 1.15), (fx1 + 0.24, 0.07, 1.5), 0.015, band="console", skip=("-y",))
    mb.panel((fx1 + 0.14, 0.071, 1.40), (-1, 0, 0), (0, 0, 1), 0.14, 0.12, "MAT_display")
    mb.cbox((fx1 + 0.1, 0.06, 1.2), (fx1 + 0.18, 0.1, 1.28), 0.01, band="console",
            bands={"+y": (B.FILL, "MAT_emit_amber")}, skip=("-y",))
    return mb


def corridor_segment(variant):
    mb = B.MB(floor_tile=CORR_SEG)
    mb.extrude_profile(CORR_PROFILE, 0.0, CORR_SEG, CORR_BANDS, mats=CORR_MATS)
    mb.ring_rib(CORR_PROFILE[2:18], 0.08, 0.0, 0.12, band="gunmetal", inner_band="rivets")
    if variant == "light":
        mb.cbox((0.3, -0.16, 2.3), (1.0, 0.16, 2.42), 0.02, band="gunmetal", skip=("+z",))
        mb.fill_quad((0.36, 0.1, 2.296), (0.94, 0.1, 2.296), (0.94, -0.1, 2.296), (0.36, -0.1, 2.296),
                     "MAT_emit_warm")
        for x in (0.45, 0.65, 0.85):
            mb.box((x - 0.01, -0.13, 2.27), (x + 0.01, 0.13, 2.3), band="steel", skip=("+z",))
    else:
        mb.cbox((0.35, -0.32, 2.37), (0.95, 0.32, 2.42), 0.012, band="gunmetal",
                bands={"-z": "vent"}, skip=("+z",))
    return mb


def corridor_end_cap():
    """Plate closing the corridor at a room door. Local +X points into the corridor."""
    mb = B.MB()
    y0, y1 = -L.DOOR_W / 2, L.DOOR_W / 2
    polys = [
        [(y0, 0.0), (-0.75, 0.0), (-0.9, 0.3), (-0.9, 1.9), (-0.6, 2.4), (y0, 2.4)],
        [(y1, 0.0), (y1, 2.4), (0.6, 2.4), (0.9, 1.9), (0.9, 0.3), (0.75, 0.0)],
        [(y0, L.DOOR_H), (y1, L.DOOR_H), (y1, 2.4), (y0, 2.4)],
    ]
    faces = []
    for poly in polys:
        faces.append(mb.face([(0.0, y, z) for y, z in poly], band="panel_teal"))
    mb._orient(faces, (1, 0, 0))
    fw = FRAME_W
    hz = {"+x": "hazard"}
    mb.cbox((-0.02, y0 - fw, 0.0), (0.12, y0, L.DOOR_H), 0.02, bands=hz, skip=("-x", "-z", "+z"))
    mb.cbox((-0.02, y1, 0.0), (0.12, y1 + fw, L.DOOR_H), 0.02, bands=hz, skip=("-x", "-z", "+z"))
    mb.cbox((-0.02, y0 - fw, L.DOOR_H), (0.12, y1 + fw, L.DOOR_H + fw), 0.02, bands={"+x": "rivets"}, skip=("-x",))
    # control panel beside the door (corridor side)
    py0, py1 = y1 + fw + 0.02, 0.88
    mb.cbox((0.0, py0, 1.15), (0.07, py1, 1.5), 0.015, band="console", skip=("-x",))
    mb.panel((0.071, (py0 + py1) / 2, 1.40), (0, 1, 0), (0, 0, 1), py1 - py0 - 0.04, 0.12, "MAT_display")
    mb.cbox((0.06, (py0 + py1) / 2 - 0.04, 1.2), (0.1, (py0 + py1) / 2 + 0.04, 1.28), 0.01, band="console",
            bands={"+x": (B.FILL, "MAT_emit_amber")}, skip=("-x",))
    return mb


def hub_module():
    """T-junction hub: floor, ceiling, portal plates and the south wall with the dock alcove."""
    mb = B.MB(floor_tile=CORR_SEG)
    h = L.HALF
    ch = L.CORR_H
    dw, dd, dh = L.DOCK_W / 2, L.DOCK_D, L.DOCK_H
    mb.face([(-h, -h, 0), (h, -h, 0), (h, h, 0), (-h, h, 0)], band=FLOOR, mat="MAT_floor")
    # ceiling (faces down) with a light housing
    mb._orient([mb.face([(-h, -h, ch), (h, -h, ch), (h, h, ch), (-h, h, ch)], band="gunmetal")], (0, 0, -1))
    mb.cbox((-0.35, -0.35, ch - 0.1), (0.35, 0.35, ch + 0.02), 0.03, band="gunmetal", skip=("+z",))
    mb.fill_quad((-0.28, 0.28, ch - 0.104), (0.28, 0.28, ch - 0.104), (0.28, -0.28, ch - 0.104),
                 (-0.28, -0.28, ch - 0.104), "MAT_emit_warm")
    # portal corner plates + rib frames around the three corridor openings
    corners = [
        [(-0.9, 0.0), (-0.75, 0.0), (-0.9, 0.3)],
        [(-0.9, 1.9), (-0.6, 2.4), (-0.9, 2.4)],
        [(0.6, 2.4), (0.9, 1.9), (0.9, 2.4)],
        [(0.75, 0.0), (0.9, 0.0), (0.9, 0.3)],
    ]
    # (rotation about Z, position of the portal plane along local +X)
    # rz = 0: west portal, pi: east portal, -pi/2: north portal (local +X points into the hub)
    for rz in (0.0, math.pi, -math.pi / 2):
        with mb.at((0, 0, 0), rot_z=rz):
            fs = [mb.face([(-h, y, z) for y, z in tri], band="gunmetal") for tri in corners]
            mb._orient(fs, (1, 0, 0))
    # portal rings: a ring rib swept along +X from the portal plane into the hub
    for rz in (0.0, math.pi, -math.pi / 2):
        with mb.at((0, 0, 0), rot_z=rz):
            with mb.at((-h, 0, 0)):
                prof = [(-0.75, 0.0), (-0.9, 0.3), (-0.9, 1.9), (-0.6, 2.4), (0.6, 2.4), (0.9, 1.9),
                        (0.9, 0.3), (0.75, 0.0)]
                mb.ring_rib(prof, 0.1, -0.02, 0.14, band="gunmetal", inner_band="rivets")
    # south wall with alcove opening (faces +Y)
    fs = [
        mb.face([(-h, -h, 0), (-dw, -h, 0), (-dw, -h, ch), (-h, -h, ch)], band="panel_teal"),
        mb.face([(dw, -h, 0), (h, -h, 0), (h, -h, ch), (dw, -h, ch)], band="panel_teal"),
        mb.face([(-dw, -h, dh), (dw, -h, dh), (dw, -h, ch), (-dw, -h, ch)], band="panel_teal"),
    ]
    mb._orient(fs, (0, 1, 0))
    # alcove lining
    back = -h - dd
    fs = [mb.face([(-dw, back, 0), (dw, back, 0), (dw, back, dh), (-dw, back, dh)], band="gunmetal")]
    mb._orient(fs, (0, 1, 0))
    fs = [mb.face([(-dw, -h, 0), (-dw, back, 0), (-dw, back, dh), (-dw, -h, dh)], band="gunmetal")]
    mb._orient(fs, (1, 0, 0))
    fs = [mb.face([(dw, -h, 0), (dw, back, 0), (dw, back, dh), (dw, -h, dh)], band="gunmetal")]
    mb._orient(fs, (-1, 0, 0))
    fs = [mb.face([(-dw, -h, dh), (dw, -h, dh), (dw, back, dh), (-dw, back, dh)], band="gunmetal")]
    mb._orient(fs, (0, 0, -1))
    mb.face([(-dw, back, 0), (dw, back, 0), (dw, -h, 0), (-dw, -h, 0)], band=FLOOR, mat="MAT_floor")
    # alcove frame with hazard stripes
    mb.cbox((-dw - 0.12, -h - 0.02, 0.0), (-dw, -h + 0.1, dh), 0.02, bands={"+y": "hazard"}, skip=("-y", "-z"))
    mb.cbox((dw, -h - 0.02, 0.0), (dw + 0.12, -h + 0.1, dh), 0.02, bands={"+y": "hazard"}, skip=("-y", "-z"))
    mb.cbox((-dw - 0.12, -h - 0.02, dh), (dw + 0.12, -h + 0.1, dh + 0.12), 0.02,
            bands={"+y": "hazard"}, skip=("-y",))
    # sign plate over the alcove
    mb.cbox((-0.35, -h, dh + 0.3), (0.35, -h + 0.04, dh + 0.48), 0.01, bands={"+y": "label"}, skip=("-y",))
    return mb


def _clip(poly, nx, ny, c):
    """Keep the part of a polygon with nx*x + ny*y <= c."""
    out = []
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        dp = nx * p[0] + ny * p[1] - c
        dq = nx * q[0] + ny * q[1] - c
        if dp <= 1e-9:
            out.append(p)
        if (dp < -1e-9 < dq) or (dq < -1e-9 < dp):
            t = dp / (dp - dq)
            out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
    return out


def _tile_poly(w, d, cut):
    """Tile outline centred on the origin (w along X, d along Y) with an optional
    45-degree corner cut of 1 m: cut in {None, 'NE', 'NW', 'SW', 'SE'}."""
    hw, hd = w / 2, d / 2
    poly = [(-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)]
    if cut:
        sx = 1 if "E" in cut else -1
        sy = 1 if "N" in cut else -1
        # line through the two points 1 m back from the corner along each edge
        c = hw + hd - 1.0
        poly = _clip(poly, sx, sy, c)
    return poly, cut


def floor_tile(w, d, cut=None, grate=False):
    mb = B.MB(floor_tile=1.0)
    poly, _ = _tile_poly(w, d, cut)
    if not grate:
        mb.face([(x, y, 0.0) for x, y in poly], band=FLOOR, mat="MAT_floor")
        return mb
    # drain grate recessed in the middle (4 strips of 0.25 m, each showing the full vent band)
    g = 0.5
    ring = [(-g, -g), (g, -g), (g, g), (-g, g)]
    outer = poly
    # frame between tile edge and grate, as 4 quads
    ox0, oy0 = min(p[0] for p in outer), min(p[1] for p in outer)
    ox1, oy1 = max(p[0] for p in outer), max(p[1] for p in outer)
    for a, b in (((ox0, oy0), (ox1, -g)), ((ox0, g), (ox1, oy1)), ((ox0, -g), (-g, g)), ((g, -g), (ox1, g))):
        mb.face([(a[0], a[1], 0), (b[0], a[1], 0), (b[0], b[1], 0), (a[0], b[1], 0)], band=FLOOR, mat="MAT_floor")
    z = -0.04
    for i in range(4):
        y0 = -g + i * 0.25
        mb.face([(-g, y0, z), (g, y0, z), (g, y0 + 0.25, z), (-g, y0 + 0.25, z)], band="vent")
    # inner walls of the recess
    fs = []
    for (ax, ay), (bx, by) in zip(ring, ring[1:] + ring[:1]):
        fs.append(mb.face([(ax, ay, z), (bx, by, z), (bx, by, 0), (ax, ay, 0)], band="steel"))
    for f in fs:
        f.normal_update()
        if f.calc_center_median().xy.dot(f.normal.xy) > 0:
            f.normal_flip()
    return mb


def ceiling_tile(w, d, cut=None, light=False):
    """Ceiling tile at z = ROOM_H (faces down): stepped 0.5 m strips running along X,
    a cross beam on the -X edge and an optional hanging light housing."""
    mb = B.MB()
    hw, hd = w / 2, d / 2
    cut_line = None
    if cut:
        sx = 1 if "E" in cut else -1
        sy = 1 if "N" in cut else -1
        cut_line = (sx, sy, hw + hd - 1.0)
    n = int(round(d / 0.5))
    zs = [H if i % 2 == 0 else H - 0.03 for i in range(n)]
    for i in range(n):
        y0, y1 = -hd + i * 0.5, -hd + (i + 1) * 0.5
        strip = [(-hw, y0), (hw, y0), (hw, y1), (-hw, y1)]
        if cut_line:
            strip = _clip(strip, *cut_line)
        if len(strip) >= 3:
            mb._orient([mb.face([(x, y, zs[i]) for x, y in strip], band="panel_gray")], (0, 0, -1))
    for i in range(n - 1):
        y = -hd + (i + 1) * 0.5
        xa, xb = -hw, hw
        if cut_line:
            sx, sy, c = cut_line
            lim = (c - sy * y) / sx          # sx * x + sy * y <= c
            if sx > 0:
                xb = min(xb, lim)
            else:
                xa = max(xa, lim)
        if xb - xa < 1e-3:
            continue
        f = mb.face([(xa, y, H - 0.03), (xb, y, H - 0.03), (xb, y, H), (xa, y, H)], band="gunmetal")
        # the riser faces the lower strip
        mb._orient([f], (0, 1 if zs[i + 1] < zs[i] else -1, 0))
    # cross beam along the -X edge
    beam = [(-hw, -hd), (-hw + 0.1, -hd), (-hw + 0.1, hd), (-hw, hd)]
    if cut_line:
        beam = _clip(beam, *cut_line)
    if len(beam) >= 3:
        ys = [p[1] for p in beam]
        mb.cbox((-hw, min(ys), H - 0.09), (-hw + 0.1, max(ys), H + 0.01), 0.015, band="gunmetal",
                bands={"-z": "rivets"}, skip=("+z", "-y", "+y"))
    if light:
        mb.cbox((-0.85, -0.3, H - 0.1), (0.85, 0.3, H), 0.025, band="gunmetal", skip=("+z",))
        mb.fill_quad((-0.78, 0.2, H - 0.102), (0.78, 0.2, H - 0.102), (0.78, -0.2, H - 0.102),
                     (-0.78, -0.2, H - 0.102), "MAT_emit_warm")
        for x in (-0.5, 0.0, 0.5):
            mb.box((x - 0.012, -0.24, H - 0.13), (x + 0.012, 0.24, H - 0.1), band="steel", skip=("+z",))
    return mb


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def build():
    L.clear_objects(lambda o: o.get("stage") == "structure")
    for me in [m for m in bpy.data.meshes if m.name.startswith("MOD_") and m.users == 0]:
        bpy.data.meshes.remove(me)

    # hide the greybox (kept for reference)
    for o in bpy.data.objects:
        if o.get("stage") == "greybox" and not o.name.startswith("DOOR_"):
            o.hide_set(True)
            o.hide_render = True

    rooms = {n: L.collection(n) for n in L.ROOM_COLLECTIONS}
    mods = {}

    def mod(name, mb):
        if name not in mods:
            mods[name] = mb.finish(name)
        return mods[name]

    mod("MOD_wall_2m_A", wall_module(2.0, "A"))
    mod("MOD_wall_2m_B", wall_module(2.0, "B"))
    mod("MOD_wall_2m_C", wall_module(2.0, "C"))
    mod("MOD_wall_1m", wall_module(1.0, "A"))
    mod("MOD_wall_chamfer", wall_module(math.sqrt(2), "A"))
    mod("MOD_wall_door", door_module())
    mod("MOD_corr_light", corridor_segment("light"))
    mod("MOD_corr_plain", corridor_segment("plain"))
    mod("MOD_corr_endcap", corridor_end_cap())
    mod("MOD_corr_hub", hub_module())
    mod("MOD_floor_2x2", floor_tile(2, 2))
    mod("MOD_floor_2x2_grate", floor_tile(2, 2, grate=True))
    mod("MOD_floor_2x2_cut", floor_tile(2, 2, cut="NE"))
    mod("MOD_floor_2x1", floor_tile(2, 1))
    for c in ("NE", "NW", "SW", "SE"):
        mod(f"MOD_ceil_2x2_cut{c}", ceiling_tile(2, 2, cut=c))
    mod("MOD_ceil_2x2", ceiling_tile(2, 2))
    mod("MOD_ceil_2x2_light", ceiling_tile(2, 2, light=True))
    mod("MOD_ceil_2x1", ceiling_tile(2, 1))
    mod("MOD_floor_2x1_cutNW", floor_tile(2, 1, cut="NW"))
    mod("MOD_floor_2x1_cutNE", floor_tile(2, 1, cut="NE"))
    mod("MOD_ceil_2x1_cutNW", ceiling_tile(2, 1, cut="NW"))
    mod("MOD_ceil_2x1_cutNE", ceiling_tile(2, 1, cut="NE"))

    count = {"n": 0}

    def put(name, mesh_name, coll, loc, rz):
        ob = B.place(name, mods[mesh_name], coll, loc, rz, {"stage": "structure", "static": True,
                                                            "module": mesh_name})
        count["n"] += 1
        return ob

    # ---- room walls ---------------------------------------------------------
    wall_plan = {
        "cryo": [["2m_A", "2m_A"], ["chamfer"], ["1m", "door", "1m"], ["chamfer"],
                 ["2m_A", "2m_A"], ["chamfer"], ["2m_C", "2m_B"], ["chamfer"]],
        "engineering": [["2m_C", "2m_A"], ["chamfer"], ["2m_A", "2m_A"], ["chamfer"],
                        ["2m_A", "2m_B"], ["chamfer"], ["1m", "door", "1m"], ["chamfer"]],
        "command": [["2m_B", "door", "2m_C"], ["2m_A", "2m_B"], ["chamfer"], ["2m_A", "2m_A"],
                    ["chamfer"], ["2m_B", "2m_A"]],
    }
    widths = {"2m_A": 2.0, "2m_B": 2.0, "2m_C": 2.0, "1m": 1.0, "chamfer": math.sqrt(2), "door": 2.0}
    for room, plan in wall_plan.items():
        coll = rooms["ROOM_" + room]
        outline = L.ROOMS[room]["outline"]
        k = 0
        for ei, seq in enumerate(plan):
            a, b = outline[ei], outline[(ei + 1) % len(outline)]
            (x, y, _), rz, length = B.edge_frame(a, b)
            total = sum(widths[s] for s in seq)
            assert abs(total - length) < 1e-4, (room, ei, total, length)
            d = Vector((math.cos(rz), math.sin(rz)))
            s = 0.0
            for m in seq:
                p = Vector((x, y)) + d * s
                k += 1
                mesh = "MOD_wall_door" if m == "door" else ("MOD_wall_" + m)
                put(f"ST_{room}_wall_{k:02d}", mesh, coll, (p.x, p.y, 0.0), rz)
                s += widths[m]

    # ---- room floors & ceilings ---------------------------------------------
    corner_rot = {"NE": 0.0, "NW": math.pi / 2, "SW": math.pi, "SE": -math.pi / 2}
    for room, x0 in (("cryo", -11.0), ("engineering", 5.0)):
        coll = rooms["ROOM_" + room]
        k = 0
        lights = {(1, 1)} if room == "cryo" else {(1, 1), (2, 1)}
        for i in range(3):
            for j in range(3):
                cx, cy = x0 + 1 + 2 * i, -3 + 1 + 2 * j
                corner = None
                if i in (0, 2) and j in (0, 2):
                    corner = ("N" if j == 2 else "S") + ("E" if i == 2 else "W")
                k += 1
                if corner:
                    put(f"ST_{room}_floor_{k:02d}", "MOD_floor_2x2_cut", coll, (cx, cy, 0), corner_rot[corner])
                    put(f"ST_{room}_ceil_{k:02d}", f"MOD_ceil_2x2_cut{corner}", coll, (cx, cy, 0), 0.0)
                else:
                    fm = "MOD_floor_2x2_grate" if (i, j) == (1, 1) else "MOD_floor_2x2"
                    put(f"ST_{room}_floor_{k:02d}", fm, coll, (cx, cy, 0), 0.0)
                    cm = "MOD_ceil_2x2_light" if (i, j) in lights else "MOD_ceil_2x2"
                    put(f"ST_{room}_ceil_{k:02d}", cm, coll, (cx, cy, 0), 0.0)

    coll = rooms["ROOM_command"]
    k = 0
    for i in range(3):
        for j in range(2):
            cx, cy = -2 + 2 * i, 6 + 2 * j
            k += 1
            fm = "MOD_floor_2x2_grate" if (i, j) == (1, 0) else "MOD_floor_2x2"
            put(f"ST_command_floor_{k:02d}", fm, coll, (cx, cy, 0), 0.0)
            cm = "MOD_ceil_2x2_light" if (i, j) in ((1, 0), (1, 1)) else "MOD_ceil_2x2"
            put(f"ST_command_ceil_{k:02d}", cm, coll, (cx, cy, 0), 0.0)
    for i, (fm, cm) in enumerate((("MOD_floor_2x1_cutNW", "MOD_ceil_2x1_cutNW"),
                                  ("MOD_floor_2x1", "MOD_ceil_2x1"),
                                  ("MOD_floor_2x1_cutNE", "MOD_ceil_2x1_cutNE"))):
        k += 1
        put(f"ST_command_floor_{k:02d}", fm, coll, (-2 + 2 * i, 9.5, 0), 0.0)
        put(f"ST_command_ceil_{k:02d}", cm, coll, (-2 + 2 * i, 9.5, 0), 0.0)

    # ---- corridor -------------------------------------------------------------
    cc = rooms["ROOM_corridor"]
    pattern = ["MOD_corr_plain", "MOD_corr_light", "MOD_corr_plain"]
    h = L.HALF
    for i, m in enumerate(pattern):
        put(f"ST_corr_west_{i + 1:02d}", m, cc, (-h - CORR_SEG * (i + 1), 0, 0), 0.0)
        put(f"ST_corr_east_{i + 1:02d}", m, cc, (h + CORR_SEG * (i + 1), 0, 0), math.pi)
        put(f"ST_corr_stem_{i + 1:02d}", m, cc, (0, h + CORR_SEG * (i + 1), 0), -math.pi / 2)
    put("ST_corr_hub", "MOD_corr_hub", cc, (0, 0, 0), 0.0)
    put("ST_corr_end_cryo", "MOD_corr_endcap", cc, (-L.ARM_END, 0, 0), 0.0)
    put("ST_corr_end_engineering", "MOD_corr_endcap", cc, (L.ARM_END, 0, 0), math.pi)
    put("ST_corr_end_command", "MOD_corr_endcap", cc, (0, L.STEM_END, 0), -math.pi / 2)

    return {"objects": count["n"], "modules": len(mods)}
