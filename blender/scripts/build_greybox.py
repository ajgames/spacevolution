"""Step 2: greybox of the full ship layout.

Re-runnable: deletes every GB_*, REF_* and greybox-stage DOOR_* object first.
Run from Blender with:
    exec(open(bpy.path.abspath("//scripts/run.py")).read()); run("build_greybox")
"""
import math

import bpy

import lib_ship as L


def build():
    L.clear_objects(lambda o: o.name.startswith(("GB_", "REF_")) or o.get("stage") == "greybox")

    # Remove the stock startup objects if they are still around.
    for n in ("Cube", "Light", "Camera"):
        o = bpy.data.objects.get(n)
        if o is not None:
            bpy.data.objects.remove(o, do_unlink=True)
    stock = bpy.data.collections.get("Collection")
    if stock is not None and not stock.objects and not stock.children:
        bpy.data.collections.remove(stock)

    rooms = {n: L.collection(n) for n in L.ROOM_COLLECTIONS}
    ref = L.collection("REF_layout")

    colors = {
        "command": (0.45, 0.62, 0.60, 1),
        "cryo": (0.55, 0.66, 0.78, 1),
        "engineering": (0.78, 0.60, 0.42, 1),
        "corridor": (0.62, 0.62, 0.62, 1),
        "prop": (0.30, 0.30, 0.33, 1),
        "door": (0.85, 0.72, 0.30, 1),
    }

    def tag(ob, room, part, color=None):
        ob["stage"] = "greybox"
        ob["gb_part"] = part
        ob.color = color or colors[room]
        return ob

    # ---------------------------------------------------------------- rooms
    for name, spec in L.ROOMS.items():
        coll = rooms["ROOM_" + name]
        outline, h = spec["outline"], spec["height"]
        edge, off = spec["door"]
        v, f = L.wall_ring_geo(outline, L.WALL_T, h, {edge: [(off, L.DOOR_W, L.DOOR_H)]})
        tag(L.mesh_object(f"GB_{name}_walls", v, f, coll), name, "wall")
        outer = [(p.x, p.y) for p in L.miter_offsets(outline, L.WALL_T)]
        v, f = L.polygon_slab_geo(outer, -0.1, 0.0)
        tag(L.mesh_object(f"GB_{name}_floor", v, f, coll), name, "floor")
        v, f = L.polygon_slab_geo(outer, h, h + 0.1)
        tag(L.mesh_object(f"GB_{name}_ceiling", v, f, coll), name, "ceiling")

    # ------------------------------------------------------------- corridor
    cc = rooms["ROOM_corridor"]
    H, T, A, S = L.HALF, L.WALL_T, L.ARM_END, L.STEM_END
    CH = L.CORR_H
    dw, dd, dh = L.DOCK_W / 2, L.DOCK_D, L.DOCK_H
    walls = [
        L.box_geo((-A, H, 0), (-H, H + T, CH)),                   # arm north, west half
        L.box_geo((H, H, 0), (A, H + T, CH)),                     # arm north, east half
        L.box_geo((-H - T, H, 0), (-H, S, CH)),                   # stem west
        L.box_geo((H, H, 0), (H + T, S, CH)),                     # stem east
        L.box_geo((-A, -H - T, 0), (-dw, -H, CH)),                # arm south, west
        L.box_geo((dw, -H - T, 0), (A, -H, CH)),                  # arm south, east
        L.box_geo((-dw, -H - T, dh), (dw, -H, CH)),               # header over the dock
        L.box_geo((-dw - T, -H - dd - T, 0), (-dw, -H - T, dh + T)),   # dock side W
        L.box_geo((dw, -H - dd - T, 0), (dw + T, -H - T, dh + T)),     # dock side E
        L.box_geo((-dw - T, -H - dd - T, 0), (dw + T, -H - dd, dh + T)),  # dock back
        L.box_geo((-dw, -H - dd, dh), (dw, -H - T, dh + T)),      # dock roof
    ]
    v, f = L.merge_geo(walls)
    tag(L.mesh_object("GB_corridor_walls", v, f, cc), "corridor", "wall")
    floors = [
        L.box_geo((-A, -H - T, -0.1), (A, H + T, 0)),
        L.box_geo((-H - T, H + T, -0.1), (H + T, S, 0)),
        L.box_geo((-dw - T, -H - dd - T, -0.1), (dw + T, -H - T, 0)),
    ]
    v, f = L.merge_geo(floors)
    tag(L.mesh_object("GB_corridor_floor", v, f, cc), "corridor", "floor")
    ceil = [
        L.box_geo((-A, -H - T, CH), (A, H + T, CH + 0.1)),
        L.box_geo((-H - T, H + T, CH), (H + T, S, CH + 0.1)),
    ]
    v, f = L.merge_geo(ceil)
    tag(L.mesh_object("GB_corridor_ceiling", v, f, cc), "corridor", "ceiling")

    # ---------------------------------------------------------------- doors
    # Sliding doors. Origin = bottom centre of the closed panel; the panel
    # slides along its local X axis into the wall pocket.
    doors = [
        ("DOOR_command", rooms["ROOM_command"], (0, 4.9, 0), 0.0),
        ("DOOR_cryo", rooms["ROOM_cryo"], (-4.9, 0, 0), math.pi / 2),
        ("DOOR_engineering", rooms["ROOM_engineering"], (4.9, 0, 0), math.pi / 2),
    ]
    for name, coll, loc, rz in doors:
        old = bpy.data.objects.get(name)
        if old is not None:
            bpy.data.objects.remove(old, do_unlink=True)
        v, f = L.box_geo((-L.DOOR_W / 2, -0.04, 0), (L.DOOR_W / 2, 0.04, L.DOOR_H))
        ob = L.mesh_object(name, v, f, coll, location=loc)
        ob.rotation_euler = (0, 0, rz)
        tag(ob, "door", "door")

    # --------------------------------------------------------- blockout props
    P = colors["prop"]
    cm, cr, en = rooms["ROOM_command"], rooms["ROOM_cryo"], rooms["ROOM_engineering"]
    props = [
        # command
        ("GB_workstation_desk", cm, (0, 8.85, 0.4), (2.8, 0.9, 0.8)),
        ("GB_workstation_screens", cm, (0, 9.45, 1.5), (2.6, 0.25, 0.8)),
        ("GB_workstation_seat", cm, (0, 7.75, 0.55), (0.6, 0.6, 1.1)),
        ("GB_command_lockers", cm, (-2.7, 6.8, 1.0), (0.6, 2.0, 2.0)),
        ("GB_command_side_console", cm, (2.6, 7.0, 0.5), (0.8, 1.6, 1.0)),
        # cryo: pods 01-03 on the north wall (east to west), 04-06 on the south wall (west to east)
        ("GB_cryo_console", cr, (-10.65, 0, 0.55), (0.7, 1.8, 1.1)),
        # engineering
        ("GB_core_racks", en, (10.55, 0, 1.1), (0.9, 3.2, 2.2)),
        ("GB_blink_panel", en, (8.0, 2.95, 1.35), (1.0, 0.1, 0.8)),
        ("GB_power_unit", en, (8.0, -2.65, 0.8), (2.0, 0.7, 1.6)),
        # corridor
        ("GB_droid_dock", cc, (0, -1.55, 0.15), (1.2, 0.5, 0.3)),
    ]
    pod_x = [-6.7, -8.0, -9.3]
    for i, x in enumerate(pod_x):
        props.append((f"GB_cryo_pod_{i + 1:02d}", cr, (x, 2.5, 1.15), (1.1, 1.0, 2.3)))
    for i, x in enumerate(reversed(pod_x)):
        props.append((f"GB_cryo_pod_{i + 4:02d}", cr, (x, -2.5, 1.15), (1.1, 1.0, 2.3)))
    for name, coll, c, s in props:
        tag(L.box(name, coll, c, s), "prop", "prop", P)

    # ------------------------------------------------------ reference hull
    # Thin ring marking the rounded central hull that houses the T corridor.
    segs = 48
    inner = L.circle_pts(0, 0, L.HULL_R, segs)
    outer = L.circle_pts(0, 0, L.HULL_R + L.WALL_T, segs)
    ring = [L.prism_geo([inner[i], outer[i], outer[(i + 1) % segs], inner[(i + 1) % segs]], 3.2, 3.25)
            for i in range(segs)]
    v, f = L.merge_geo(ring)
    hull = L.mesh_object("REF_hull_central", v, f, ref)
    hull.hide_render = True
    hull.color = (0.85, 0.35, 0.2, 1)

    labels = [("COMMAND", (0, 7.2)), ("CRYO BAY", (-8, 0)), ("ENGINEERING", (8, 0)),
              ("DOCK", (0, -2.6)), ("CENTRAL HULL", (0, -4.2))]
    for text, (x, y) in labels:
        cu = bpy.data.curves.new("REF_label_" + text, "FONT")
        cu.body = text
        cu.size = 0.55
        cu.align_x = "CENTER"
        cu.align_y = "CENTER"
        ob = bpy.data.objects.new("REF_label_" + text.replace(" ", "_"), cu)
        ob.location = (x, y, 3.3)
        inside_room = text in ("COMMAND", "CRYO BAY", "ENGINEERING")
        ob.color = (0.05, 0.05, 0.05, 1) if inside_room else (0.85, 0.85, 0.85, 1)
        ob.hide_render = True
        ref.objects.link(ob)

    return {"objects": len([o for o in bpy.data.objects if o.get("stage") == "greybox"])}
