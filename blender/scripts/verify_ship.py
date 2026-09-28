"""Checks the scene against PROMPT.md. Run after any build step:
    exec(open(bpy.path.abspath("//scripts/run.py")).read()); run("verify_ship", "verify")
Returns a dict of {check: {"ok": bool, ...}}.
"""
import numpy as np

import bpy

import lib_ship as L

REQUIRED_OBJECTS = (
    ["SCREEN_status", "SCREEN_mission", "SCREEN_aux"]
    + [f"BTN_console_{i:02d}" for i in range(1, 9)] + ["BTN_console_main", "BTN_blink"]
    + ["LIGHT_BLINK_engineering"]
    + [f"CRYO_POD_{i:02d}" for i in range(1, 7)]
    + ["SPAWN_player", "SPAWN_droid", "SEAT_workstation"]
    + ["DOOR_command", "DOOR_cryo", "DOOR_engineering"]
)
REQUIRED_COLLECTIONS = L.ROOM_COLLECTIONS + L.LIGHT_COLLECTIONS
TRI_BUDGET = 150_000
OVERLAP_TOLERANCE_PX = 0      # at the 1024 check resolution
HERO_BUDGET = 15_000
HEROES = {
    "workstation": lambda o: o.name.startswith(("WORKSTATION_", "SCREEN_", "BTN_console", "PROP_workstation")),
    "cryo_pods": lambda o: o.name.startswith("CRYO_POD_"),
    "core_computer": lambda o: o.name.startswith("CORE_rack_"),
}


def _tris(o, dg):
    eo = o.evaluated_get(dg)
    me = eo.to_mesh()
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    eo.to_mesh_clear()
    return n


def room_meshes(cname):
    return [o for o in bpy.data.collections[cname].all_objects if o.type == "MESH"]


def raster_lightmap(objs, res=1024):
    """Rasterise every lightmap triangle (pixel centres). Returns (overlap count,
    owner id map, list of out-of-range objects). A texel counts as overlapping
    only when two different polygons claim it (the two triangles of one quad
    share a diagonal and must not be counted)."""
    count = np.zeros((res, res), np.int32)
    owner = np.full((res, res), -1, np.int32)
    poly_owner = np.full((res, res), -1, np.int64)
    out_of_range = []
    base = 0
    for oid, o in enumerate(objs):
        me = o.data
        lm = me.uv_layers.get("lightmap")
        if lm is None:
            continue
        uv = np.zeros(len(me.loops) * 2, np.float32)
        lm.data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)
        if uv.min() < -1e-4 or uv.max() > 1 + 1e-4:
            out_of_range.append(o.name)
        me.calc_loop_triangles()
        tl = np.zeros(len(me.loop_triangles) * 3, np.int32)
        me.loop_triangles.foreach_get("loops", tl)
        tri = uv[tl.reshape(-1, 3)] * res          # (n, 3, 2) in pixels
        polys = np.zeros(len(me.loop_triangles), np.int32)
        me.loop_triangles.foreach_get("polygon_index", polys)
        polys = polys.astype(np.int64) + base
        base += len(me.polygons) + 1
        for t, pid in zip(tri, polys):
            x0, y0 = np.floor(t.min(0)).astype(int)
            x1, y1 = np.ceil(t.max(0)).astype(int)
            x0, y0 = max(x0, 0), max(y0, 0)
            x1, y1 = min(x1, res), min(y1, res)
            if x1 <= x0 or y1 <= y0:
                continue
            xs = np.arange(x0, x1) + 0.5
            ys = np.arange(y0, y1) + 0.5
            px, py = np.meshgrid(xs, ys)
            (ax, ay), (bx, by), (cx, cy) = t
            d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(d) < 1e-12:
                continue
            w0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / d
            w1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / d
            w2 = 1 - w0 - w1
            inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            if not inside.any():
                continue
            psub = poly_owner[y0:y1, x0:x1]
            other = inside & (psub >= 0) & (psub != pid)
            count[y0:y1, x0:x1] += inside & ((psub < 0) | other)
            psub[inside] = pid
            sub = owner[y0:y1, x0:x1]
            sub[inside] = oid
    return count, owner, out_of_range


def lightmap_check(res=1024):
    out = {}
    for cname in L.ROOM_COLLECTIONS:
        objs = room_meshes(cname)
        missing = [o.name for o in objs if "lightmap" not in o.data.uv_layers]
        order = [o.name for o in objs if o.data.uv_layers and o.data.uv_layers[0].name != "UVMap"]
        count, owner, oor = raster_lightmap(objs, res)
        overlap_px = int((count > 1).sum())
        # margin between different objects: any pixel whose 4-neighbour belongs to another object
        o = owner
        touch = 0
        for dy, dx in ((0, 1), (1, 0)):
            a = o[: res - dy, : res - dx]
            b = o[dy:, dx:]
            touch += int(((a >= 0) & (b >= 0) & (a != b)).sum())
        out[cname] = {"ok": not missing and not order and not oor and overlap_px <= OVERLAP_TOLERANCE_PX,
                      "objects": len(objs), "missing_lightmap": missing, "uv_order_bad": order,
                      "out_of_range": oor, "overlap_px": overlap_px, "adjacent_object_px": touch,
                      "coverage": round(float((count > 0).mean()), 3)}
    return out


def verify():
    res = {}
    names = set(bpy.data.objects.keys())
    missing = [n for n in REQUIRED_OBJECTS if n not in names]
    for pod in [f"CRYO_POD_{i:02d}" for i in range(1, 7)]:
        g = bpy.data.objects.get(pod + "_glass")
        if g is None or g.parent is None or g.parent.name != pod:
            missing.append(pod + "_glass (child)")
    alarms = [n for n in names if n.startswith("LIGHT_alarm_")]
    interacts = [n for n in names if n.startswith("INTERACT_")]
    res["names"] = {"ok": bool(not missing and alarms and interacts), "missing": missing, "alarm_lights": sorted(alarms),
                    "interact_markers": sorted(interacts)}
    colls = [c for c in REQUIRED_COLLECTIONS if c not in bpy.data.collections]
    res["collections"] = {"ok": not colls, "missing": colls}

    # every object of a room lives in exactly one ROOM_ collection
    stray = []
    for o in bpy.data.objects:
        rc = [c.name for c in o.users_collection if c.name.startswith("ROOM_")]
        if len(rc) > 1:
            stray.append(o.name)
    res["single_room"] = {"ok": not stray, "multi_room": stray}

    # screens
    bad = []
    for n in ["SCREEN_status", "SCREEN_mission", "SCREEN_aux"]:
        o = bpy.data.objects.get(n)
        if o is None:
            continue
        me = o.data
        mats = [m.name for m in me.materials]
        uv = np.zeros(len(me.loops) * 2, np.float32)
        me.uv_layers["UVMap"].data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)
        flat = max(abs(v.co.y) for v in me.vertices) < 1e-6
        if mats != ["MAT_screen"] or not np.allclose(uv.min(0), 0) or not np.allclose(uv.max(0), 1) or not flat:
            bad.append({"name": n, "mats": mats, "uv_min": uv.min(0).tolist(), "uv_max": uv.max(0).tolist(), "flat": flat})
    res["screens"] = {"ok": not bad, "bad": bad}

    # buttons: origin on the top face centre
    bad = []
    for n in [f"BTN_console_{i:02d}" for i in range(1, 9)] + ["BTN_console_main", "BTN_blink"]:
        o = bpy.data.objects.get(n)
        if o is None:
            continue
        zmax = max(v.co.z for v in o.data.vertices)
        if abs(zmax) > 1e-4:
            bad.append((n, zmax))
    res["button_origins"] = {"ok": not bad, "bad": bad}

    # headroom: the spawn eye point must sit inside CRYO_POD_01's cavity with room for the head
    sp = bpy.data.objects.get("SPAWN_player")
    pod = bpy.data.objects.get("CRYO_POD_01")
    if sp and pod:
        import build_props
        eye_z = sp.matrix_world.translation.z + sp.get("eye_height", L.EYE_H)
        cavity_top = pod.matrix_world.translation.z + build_props.POD_GLASS_Z[1]
        res["spawn_headroom"] = {"ok": cavity_top - eye_z >= 0.15, "eye_z": round(eye_z, 3),
                                 "cavity_top": round(cavity_top, 3)}

    # triangles
    dg = bpy.context.evaluated_depsgraph_get()
    per_room = {c: sum(_tris(o, dg) for o in room_meshes(c)) for c in L.ROOM_COLLECTIONS}
    total = sum(per_room.values())
    heroes = {k: sum(_tris(o, dg) for o in bpy.data.objects if o.type == "MESH" and f(o)) for k, f in HEROES.items()}
    per_pod = max(_tris(bpy.data.objects[f"CRYO_POD_{i:02d}"], dg)
                  + sum(_tris(c, dg) for c in bpy.data.objects[f"CRYO_POD_{i:02d}"].children) for i in range(1, 7))
    res["triangles"] = {"ok": total < TRI_BUDGET and heroes["workstation"] < HERO_BUDGET
                        and heroes["core_computer"] < HERO_BUDGET and per_pod < HERO_BUDGET,
                        "total": total, "per_room": per_room, "heroes": heroes, "largest_single_pod": per_pod}

    # topology / modifiers
    ngons, mods = [], []
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        if any(len(p.vertices) > 4 for p in o.data.polygons):
            ngons.append(o.name)
        if o.modifiers:
            mods.append(o.name)
    res["topology"] = {"ok": not ngons and not mods, "ngons": ngons, "modifiers": mods}

    # materials
    mats = sorted({m.name for o in bpy.data.objects if o.type == "MESH" for m in o.data.materials if m})
    res["materials"] = {"ok": len(mats) <= 12, "count": len(mats), "names": mats}

    res["lightmap"] = lightmap_check()
    res["text_blocks"] = {"ok": all(t in bpy.data.texts for t in ("export_ship.py", "ASSET_CREDITS")),
                          "present": sorted(bpy.data.texts.keys())}
    res["all_ok"] = all(v.get("ok", True) for v in res.values() if isinstance(v, dict) and "ok" in v) and \
        all(v["ok"] for v in res["lightmap"].values())
    return res


def save_lightmap_preview(cname, path, res=1024):
    objs = room_meshes(cname)
    count, owner, _ = raster_lightmap(objs, res)
    rng = np.random.default_rng(3)
    pal = rng.random((len(objs) + 1, 3)).astype(np.float32) * 0.8 + 0.2
    img = np.where((owner >= 0)[..., None], pal[owner], 0.05).astype(np.float32)
    img[count > 1] = (1, 0, 0)
    rgba = np.concatenate([img, np.ones((res, res, 1), np.float32)], -1)
    im = bpy.data.images.get("_lm_preview") or bpy.data.images.new("_lm_preview", res, res)
    im.pixels.foreach_set(rgba.ravel())
    im.filepath_raw = path
    im.file_format = "PNG"
    im.save()
    bpy.data.images.remove(im)
    return path
