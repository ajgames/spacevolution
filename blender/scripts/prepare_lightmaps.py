"""Step 5b: second UV map "lightmap" on every mesh, one overlap-free atlas per room.

For every ROOM_* collection:
  * make each mesh single-user. Linked duplicates share one mesh (and so one UV
    layout), which cannot give each instance its own lightmap space. The module
    each object came from stays in the "module" custom property, and
    build_structure.py / build_props.py regenerate the linked version.
  * add the "lightmap" UV map as the SECOND map (TEXCOORD_1 in glTF); "UVMap"
    stays first and remains the active render map for the surface textures.
  * smart-project every mesh of the room (wide angle limit = few, large
    islands); any mesh whose islands fold over themselves is re-projected with
    a tight limit. Then texel density is equalised across the whole room and
    everything is packed into one 0-1 atlas with a fixed margin.
Re-runnable: re-unwraps "lightmap" from scratch each time.
"""
import math

import bpy

import lib_ship as L

MARGIN = 0.003           # fraction of the atlas (~6 px at 2048, the recommended bake size)
ANGLE_WIDE = 66.0        # first pass: big islands, few seams
ANGLE_TIGHT = 30.0       # second pass for meshes whose wide islands fold over themselves


def _select_only(objs):
    vl = bpy.context.view_layer
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for o in vl.objects:
        o.select_set(False)
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    vl.objects.active = objs[0]


def _edit(objs, fn):
    _select_only(objs)
    ts = bpy.context.scene.tool_settings
    sync = ts.use_uv_select_sync
    ts.use_uv_select_sync = True
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.reveal()
    bpy.ops.mesh.select_all(action="SELECT")
    fn()
    bpy.ops.object.mode_set(mode="OBJECT")
    ts.use_uv_select_sync = sync
    for o in objs:
        o.select_set(False)


def _smart(angle):
    return lambda: bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=0.0, area_weight=0.0,
                                            correct_aspect=True, scale_to_bounds=False)


def _pack():
    bpy.ops.uv.average_islands_scale()
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=MARGIN)


def _self_overlapping(objs):
    import verify_ship
    bad = []
    for o in objs:
        count, _, _ = verify_ship.raster_lightmap([o], 1024)
        if (count > 1).any():
            bad.append(o)
    return bad


def build():
    report = {}
    for cname in L.ROOM_COLLECTIONS:
        coll = bpy.data.collections[cname]
        objs = [o for o in coll.all_objects if o.type == "MESH"]
        for o in objs:
            if o.data.users > 1:
                o["module"] = o.get("module", o.data.name)
                o.data = o.data.copy()
            o.data.name = o.name + "_mesh"
            me = o.data
            if "UVMap" not in me.uv_layers:
                raise RuntimeError(f"{o.name} has no UVMap")
            if me.uv_layers[0].name != "UVMap":
                raise RuntimeError(f"{o.name}: UVMap is not the first UV map")
            lm = me.uv_layers.get("lightmap") or me.uv_layers.new(name="lightmap")
            me.uv_layers["UVMap"].active_render = True
            me.uv_layers.active = lm
        _edit(objs, _smart(ANGLE_WIDE))
        folded = _self_overlapping(objs)
        if folded:
            _edit(folded, _smart(ANGLE_TIGHT))
        _edit(objs, _pack)
        # guard: if the packed atlas still has overlapping texels, re-pack with a
        # slightly larger margin (up to three tries)
        import verify_ship
        margin = MARGIN
        for _ in range(3):
            count, _, _ = verify_ship.raster_lightmap(objs, 1024)
            if not (count > 1).any():
                break
            margin *= 1.25
            _edit(objs, lambda m=margin: (bpy.ops.uv.average_islands_scale(),
                                          bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=m)))
        for o in objs:
            o.data.uv_layers.active = o.data.uv_layers["UVMap"]
            o.data.uv_layers["UVMap"].active_render = True
        report[cname] = {"objects": len(objs), "re_unwrapped": [o.name for o in folded], "margin": round(margin, 5)}
    for me in [m for m in bpy.data.meshes if m.users == 0]:
        bpy.data.meshes.remove(me)
    return report
