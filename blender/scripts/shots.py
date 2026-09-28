"""Screenshot cameras and render helpers (steps 2 and 6).

Cameras live in the _CAMERAS collection, which is never exported.
"""
import bpy
from mathutils import Vector

import lib_ship as L

# name: (location, look-at target, lens mm)
EYE_CAMS = {
    "CAM_command": ((-1.6, 5.45, L.EYE_H), (0.6, 9.6, 1.15), 16),
    "CAM_cryo": ((-5.45, 0.55, L.EYE_H), (-10.8, -0.4, 1.2), 16),
    "CAM_engineering": ((5.45, -0.9, L.EYE_H), (10.8, 1.0, 1.25), 16),
    "CAM_corridor": ((0.0, 4.4, L.EYE_H), (0.0, -1.8, 0.7), 16),
    "CAM_corridor_arm": ((2.9, -0.35, L.EYE_H), (-4.9, 0.25, 1.15), 18),
}


def _look_at(ob, target):
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def cameras():
    coll = L.collection("_CAMERAS")
    out = {}
    for name, (loc, tgt, lens) in EYE_CAMS.items():
        ob = bpy.data.objects.get(name)
        if ob is None:
            ob = bpy.data.objects.new(name, bpy.data.cameras.new(name))
            coll.objects.link(ob)
        ob.location = loc
        ob.data.lens = lens
        ob.data.clip_start = 0.05
        ob.data.clip_end = 100
        _look_at(ob, tgt)
        out[name] = ob
    top = bpy.data.objects.get("CAM_top")
    if top is None:
        top = bpy.data.objects.new("CAM_top", bpy.data.cameras.new("CAM_top"))
        coll.objects.link(top)
    top.data.type = "ORTHO"
    top.data.ortho_scale = 26
    top.data.clip_end = 100
    top.location = (0, 2.5, 30)
    top.rotation_euler = (0, 0, 0)
    out["CAM_top"] = top
    return out


def _set_hidden(pred, hidden):
    changed = []
    for o in bpy.data.objects:
        if pred(o) and o.hide_render != hidden:
            changed.append((o, o.hide_render))
            o.hide_render = hidden
    return changed


def is_ceiling(o):
    return o.get("gb_part") == "ceiling" or "_ceil_" in o.name


def render_workbench(folder, prefix="", color_type="OBJECT", only=None, texture=False):
    """Flat workbench renders (step 2 greybox, and geometry checks)."""
    s = bpy.context.scene
    cams = cameras()
    if only:
        cams = {k: v for k, v in cams.items() if k in only}
    s.render.engine = "BLENDER_WORKBENCH"
    sh = s.display.shading
    sh.light = "STUDIO"
    sh.color_type = "TEXTURE" if texture else color_type
    sh.single_color = (0.6, 0.6, 0.6)
    sh.show_cavity = True
    sh.cavity_type = "WORLD"
    sh.show_object_outline = True
    sh.show_shadows = False
    s.render.film_transparent = False
    s.render.resolution_percentage = 100
    written = []
    for name, cam in cams.items():
        top = name == "CAM_top"
        s.render.resolution_x, s.render.resolution_y = (1600, 1200) if top else (1600, 900)
        restore = []
        if top:
            restore += _set_hidden(is_ceiling, True)
            restore += _set_hidden(lambda o: o.name.startswith("REF_"), False)
        s.camera = cam
        path = f"{folder}/{prefix}{name.replace('CAM_', '')}.png"
        s.render.filepath = path
        bpy.ops.render.render(write_still=True)
        for o, h in restore:
            o.hide_render = h
        written.append(path)
    return written


def render_lit(folder, prefix="", only=None, engine="BLENDER_EEVEE", samples=64, exposure=0.0,
               resolution=(1600, 900), state=None, suffix=""):
    """Lit renders (steps 3-6). state = normal | emergency | blackout switches the
    LIGHTS_* collection and emissive materials the same way the bake does."""
    s = bpy.context.scene
    bake = None
    if state:
        import bake_lightmaps as bake
        bake.set_state(state)
        bake.set_emission(state, keep_dynamic=True)
    cams = cameras()
    if only:
        cams = {k: v for k, v in cams.items() if k in only}
    s.render.engine = engine
    if engine == "CYCLES":
        s.cycles.samples = samples
        s.cycles.use_denoising = True
        try:
            s.cycles.device = "GPU"
        except Exception:
            pass
    else:
        e = s.eevee
        e.taa_render_samples = samples
        if hasattr(e, "use_raytracing"):
            e.use_raytracing = True
        if hasattr(e, "use_shadows"):
            e.use_shadows = True
    s.view_settings.view_transform = "AgX"
    s.view_settings.look = "None"
    s.view_settings.exposure = exposure
    s.render.film_transparent = False
    s.render.resolution_percentage = 100
    written = []
    hidden = _set_hidden(lambda o: o.name.startswith("REF_") or o.get("stage") == "greybox"
                         and not o.name.startswith("DOOR_"), True)
    for name, cam in cams.items():
        if name == "CAM_top":
            continue
        s.render.resolution_x, s.render.resolution_y = resolution
        s.camera = cam
        path = f"{folder}/{prefix}{name.replace('CAM_', '')}{suffix}.png"
        s.render.filepath = path
        bpy.ops.render.render(write_still=True)
        written.append(path)
    for o, h in hidden:
        o.hide_render = h
    if bake:
        bake.restore_emission()
        bake.set_state("normal")
    s.view_settings.exposure = 0.0
    return written
