"""bake_lightmaps.py - bake one lightmap per room per lighting state (Cycles).

Stored inside spacevelution_ship.blend as the text block "bake_lightmaps.py".
Run it headless so the editor stays usable (the .blend must be saved first):

    blender spacevelution_ship.blend --background --python-text bake_lightmaps.py -- [options]

Options (after "--"):
    --samples N          Cycles samples per texel            (default 256)
    --res N              lightmap size in pixels, per room    (default 1024)
    --rooms A,B          subset of ROOM_* collections         (default: all four)
    --states A,B         subset of normal,emergency,blackout  (default: all three)
    --exr                also write linear HDR masters to //export/lightmaps/exr/
    --no-denoise         skip the edge-preserving denoise pass
    --dry-run            everything except the bake itself

For each lighting state:
  * only LIGHTS_<state> is enabled (bake lights; never exported),
  * emissive materials are switched by their "light_role" custom property:
        strip      ceiling light strips          on in: normal
        alarm      alarm beacons                  on in: emergency
        indicator  amber lamps, small displays    on in: normal, emergency, blackout
        screen     SCREEN_* (MAT_screen)          on in: normal, emergency, blackout
        dynamic    blink button + lamp            never (driven by game code)
  * every ROOM_* collection is baked (Cycles DIFFUSE, direct + indirect, no albedo)
    through the "lightmap" UV map of all its meshes into one atlas. All rooms stay
    visible, so geometry outside a room still casts shadow (doors are closed).

Output (//export/lightmaps/):
  LM_<ROOM>_<state>.png  8-bit sRGB PNG of (baked light x scale). Each room/state has
                         its own scale so dark states keep their precision; the
                         matching intensity undoes it, so rooms still match exactly.
  manifest.json          per room/state: file, scale, lightMapIntensity; and the
                         three.js texture settings:
                           texture.channel = 1 (TEXCOORD_1 -> uv1), flipY = false,
                           colorSpace = SRGBColorSpace,
                           material.lightMapIntensity = Math.PI / scale
                         (three.js divides diffuse by PI; Cycles' diffuse light pass
                         is irradiance / PI.)
"""
import json
import math
import os
import sys
import time

import bpy
import numpy as np

STATES = ["normal", "emergency", "blackout"]
ROOMS = ["ROOM_command", "ROOM_cryo", "ROOM_engineering", "ROOM_corridor"]
RESOLUTION = 1024
SAMPLES = 256
MARGIN_PX = 8
DENOISE = True
WRITE_EXR = False
DRY_RUN = False
OUT_DIR = "//export/lightmaps"
SCALE_TARGET = 0.9          # each lightmap's 99th-percentile texel maps to this PNG value
SCALE_PERCENTILE = 99.0     # brighter texels (fixture housings next to lights) clip
MAX_SCALE = 2000.0
ROLE_ON = {
    "normal": {"strip", "indicator", "screen"},
    "emergency": {"alarm", "indicator", "screen"},
    "blackout": {"indicator", "screen"},
}
TARGET_NODE = "LIGHTMAP_TARGET"


# ---------------------------------------------------------------------------
# scene state
# ---------------------------------------------------------------------------
def set_state(state):
    vl = bpy.context.view_layer
    for lc in vl.layer_collection.children:
        if lc.name.startswith("LIGHTS_"):
            lc.exclude = lc.name != "LIGHTS_" + state


def _bsdf(mat):
    if not mat.use_nodes:
        return None
    return next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)


def set_emission(state, keep_dynamic=False):
    """keep_dynamic=True leaves code-driven emissives lit (used for screenshots)."""
    for m in bpy.data.materials:
        role = m.get("light_role")
        b = _bsdf(m)
        if role is None or b is None:
            continue
        on = role in ROLE_ON[state] or (keep_dynamic and role == "dynamic")
        b.inputs["Emission Strength"].default_value = m.get("emission_on", 1.0) if on else 0.0


def restore_emission():
    for m in bpy.data.materials:
        b = _bsdf(m)
        if m.get("light_role") is not None and b is not None:
            b.inputs["Emission Strength"].default_value = m.get("emission_on", 1.0)


def room_meshes(room):
    return [o for o in bpy.data.collections[room].all_objects if o.type == "MESH"]


def prepare_targets(objs, image):
    """Every material on the room's meshes gets an unlinked, active image node
    pointing at this room's lightmap (Cycles bakes into the active image node)."""
    mats = {m for o in objs for m in o.data.materials if m}
    for m in mats:
        nt = m.node_tree
        node = nt.nodes.get(TARGET_NODE)
        if node is None:
            node = nt.nodes.new("ShaderNodeTexImage")
            node.name = node.label = TARGET_NODE
            node.location = (-1200, -600)
        node.image = image
        node.interpolation = "Linear"
        nt.nodes.active = node
    return mats


def remove_targets():
    for m in bpy.data.materials:
        if m.use_nodes and TARGET_NODE in m.node_tree.nodes:
            m.node_tree.nodes.remove(m.node_tree.nodes[TARGET_NODE])


def enable_gpu():
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for dev_type in ("METAL", "OPTIX", "CUDA", "HIP", "ONEAPI"):
        try:
            prefs.compute_device_type = dev_type
        except TypeError:
            continue
        prefs.get_devices()
        gpus = [d for d in prefs.devices if d.type == dev_type]
        if gpus:
            for d in prefs.devices:
                d.use = d.type == dev_type
            bpy.context.scene.cycles.device = "GPU"
            return dev_type
    bpy.context.scene.cycles.device = "CPU"
    return "CPU"


def check_bake_operator():
    props = {p.identifier: p for p in bpy.ops.object.bake.get_rna_type().properties}
    need = {"type": "DIFFUSE", "pass_filter": {"DIRECT", "INDIRECT"}, "margin_type": "EXTEND",
            "target": "IMAGE_TEXTURES"}
    problems = []
    for k in ("type", "pass_filter", "uv_layer", "margin", "margin_type", "use_clear", "target"):
        if k not in props:
            problems.append("missing parameter " + k)
    for k, v in need.items():
        if k in props:
            items = {i.identifier for i in props[k].enum_items}
            for val in (v if isinstance(v, set) else {v}):
                if val not in items:
                    problems.append(f"{k} has no option {val}")
    return problems


# ---------------------------------------------------------------------------
# post-processing (numpy)
# ---------------------------------------------------------------------------
def island_mask(objs, res):
    """Texels covered by the room's lightmap UV triangles (pixel centres)."""
    mask = np.zeros((res, res), bool)
    for o in objs:
        me = o.data
        lm = me.uv_layers.get("lightmap")
        if lm is None:
            continue
        uv = np.zeros(len(me.loops) * 2, np.float32)
        lm.data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2) * res
        me.calc_loop_triangles()
        tl = np.zeros(len(me.loop_triangles) * 3, np.int32)
        me.loop_triangles.foreach_get("loops", tl)
        for t in uv[tl.reshape(-1, 3)]:
            x0, y0 = np.floor(t.min(0)).astype(int)
            x1, y1 = np.ceil(t.max(0)).astype(int)
            x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, res), min(y1, res)
            if x1 <= x0 or y1 <= y0:
                continue
            px, py = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
            (ax, ay), (bx, by), (cx, cy) = t
            d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
            if abs(d) < 1e-12:
                continue
            w0 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / d
            w1 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / d
            inside = (w0 >= -1e-3) & (w1 >= -1e-3) & (1 - w0 - w1 >= -1e-3)
            mask[y0:y1, x0:x1] |= inside
    return mask


def denoise(rgb, mask, radius=2, sigma_s=1.5, sigma_r=0.3):
    """Joint-bilateral filter in log luminance that only averages texels inside UV
    islands (islands sit >= 6 px apart, wider than the kernel, so nothing bleeds
    between them). Removes sampling noise while keeping shadow edges."""
    lum = np.log(np.maximum(rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32), 1e-4))
    pad = radius
    rp = np.pad(rgb, ((pad, pad), (pad, pad), (0, 0)))
    lp = np.pad(lum, pad)
    mp = np.pad(mask.astype(np.float32), pad)
    h, w = mask.shape
    acc = np.zeros_like(rgb)
    wsum = np.zeros((h, w), np.float32)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            ws = math.exp(-(dx * dx + dy * dy) / (2 * sigma_s * sigma_s))
            sl = (slice(pad + dy, pad + dy + h), slice(pad + dx, pad + dx + w))
            wr = np.exp(-((lp[sl] - lum) ** 2) / (2 * sigma_r * sigma_r))
            wt = ws * wr * mp[sl]
            acc += rp[sl] * wt[..., None]
            wsum += wt
    out = rgb.copy()
    ok = mask & (wsum > 0)
    out[ok] = acc[ok] / wsum[ok][:, None]
    return out


def to_srgb(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def write_png(rgb_linear, scale, path, name):
    h, w = rgb_linear.shape[:2]
    enc = to_srgb(rgb_linear * scale).astype(np.float32)
    rgba = np.concatenate([enc, np.ones((h, w, 1), np.float32)], -1)
    img = bpy.data.images.new("_png_" + name, w, h, alpha=False)
    img.colorspace_settings.name = "sRGB"
    img.pixels.foreach_set(rgba.ravel())      # byte image: values are stored as given
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)


# ---------------------------------------------------------------------------
# bake
# ---------------------------------------------------------------------------
def bake_room(room, state, res, samples):
    objs = room_meshes(room)
    name = f"LM_{room}_{state}"
    img = bpy.data.images.new(name, res, res, alpha=False, float_buffer=True)
    prepare_targets(objs, img)
    vl = bpy.context.view_layer
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for o in vl.objects:
        o.select_set(False)
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    vl.objects.active = objs[0]
    bpy.context.scene.cycles.samples = samples
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"DIRECT", "INDIRECT"}, uv_layer="lightmap",
                        margin=MARGIN_PX, margin_type="EXTEND", use_clear=True, target="IMAGE_TEXTURES")
    px = np.zeros(res * res * 4, np.float32)
    img.pixels.foreach_get(px)
    rgb = px.reshape(res, res, 4)[..., :3].copy()
    return img, rgb, objs


def parse_args(argv):
    a = argv[argv.index("--") + 1:] if "--" in argv else []
    cfg = {"samples": SAMPLES, "res": RESOLUTION, "rooms": list(ROOMS), "states": list(STATES),
           "exr": WRITE_EXR, "denoise": DENOISE, "dry": DRY_RUN}
    i = 0
    while i < len(a):
        k = a[i]
        if k == "--samples":
            cfg["samples"] = int(a[i + 1])
            i += 1
        elif k == "--res":
            cfg["res"] = int(a[i + 1])
            i += 1
        elif k == "--rooms":
            cfg["rooms"] = [r if r.startswith("ROOM_") else "ROOM_" + r for r in a[i + 1].split(",")]
            i += 1
        elif k == "--states":
            cfg["states"] = a[i + 1].split(",")
            i += 1
        elif k == "--exr":
            cfg["exr"] = True
        elif k == "--no-denoise":
            cfg["denoise"] = False
        elif k == "--dry-run":
            cfg["dry"] = True
        i += 1
    # bake in a fixed order (normal, emergency, blackout)
    cfg["states"] = sorted(cfg["states"], key=STATES.index)
    return cfg


def log(*a):
    print("[bake_lightmaps]", *a, flush=True)


def main(argv=None):
    cfg = parse_args(argv if argv is not None else sys.argv)
    scene = bpy.context.scene
    problems = check_bake_operator()
    if problems:
        raise RuntimeError("bake operator mismatch: " + "; ".join(problems))
    out_dir = bpy.path.abspath(OUT_DIR)
    os.makedirs(out_dir, exist_ok=True)
    manifest_path = os.path.join(out_dir, "manifest.json")
    manifest = {}
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            manifest = json.load(f)
    prev_engine = scene.render.engine
    scene.render.engine = "CYCLES"
    device = enable_gpu()
    log("device", device, "config", cfg)
    report = []
    t_all = time.time()
    try:
        for state in cfg["states"]:
            set_state(state)
            set_emission(state)
            for room in cfg["rooms"]:
                path = os.path.join(out_dir, f"LM_{room}_{state}.png")
                if cfg["dry"]:
                    prepare_targets(room_meshes(room), None)
                    report.append({"room": room, "state": state, "would_write": path})
                    continue
                t = time.time()
                img, rgb, objs = bake_room(room, state, cfg["res"], cfg["samples"])
                t_bake = time.time() - t
                mask = island_mask(objs, cfg["res"])
                if cfg["denoise"]:
                    rgb = denoise(rgb, mask)
                if cfg["exr"]:
                    os.makedirs(os.path.join(out_dir, "exr"), exist_ok=True)
                    px = np.concatenate([rgb, np.ones(rgb.shape[:2] + (1,), np.float32)], -1)
                    img.pixels.foreach_set(px.ravel())
                    img.filepath_raw = os.path.join(out_dir, "exr", f"LM_{room}_{state}.exr")
                    img.file_format = "OPEN_EXR"
                    img.save()
                bpy.data.images.remove(img)
                lum = rgb[mask] @ np.array([0.2126, 0.7152, 0.0722], np.float32)
                ref = float(np.percentile(lum, SCALE_PERCENTILE))
                scale = min(SCALE_TARGET / max(ref, 1e-6), MAX_SCALE)
                write_png(rgb, scale, path, f"{room}_{state}")
                entry = {"room": room, "state": state, "file": "lightmaps/" + os.path.basename(path),
                         "scale": round(scale, 6), "lightMapIntensity": round(math.pi / scale, 6),
                         "bake_seconds": round(t_bake, 1),
                         "stats": {"p50": round(float(np.percentile(lum, 50)), 5), "p_scale": round(ref, 5),
                                   "max": round(float(lum.max()), 5)}}
                log(entry)
                report.append(entry)
    finally:
        restore_emission()
        set_state("normal")
        remove_targets()
        scene.render.engine = prev_engine
    if not cfg["dry"]:
        rooms = manifest.get("rooms", {})
        for e in report:
            r = rooms.setdefault(e["room"], {"glb": e["room"] + ".glb", "lightmaps": {}})
            r["lightmaps"][e["state"]] = {"file": e["file"], "scale": e["scale"],
                                          "lightMapIntensity": e["lightMapIntensity"]}
        manifest.pop("scale", None)
        manifest.update({
            "encoding": "8-bit sRGB PNG of Cycles diffuse light (direct + indirect) x scale (per room/state)",
            "resolution": cfg["res"],
            "samples": cfg["samples"],
            "denoised": cfg["denoise"],
            "three_js": {"uv": "TEXCOORD_1 -> geometry.attributes.uv1 (texture.channel = 1)",
                         "texture": {"flipY": False, "colorSpace": "SRGBColorSpace", "channel": 1},
                         "material": "lightMapIntensity = rooms[room].lightmaps[state].lightMapIntensity "
                                     "(= Math.PI / scale)"},
            "rooms": rooms,
            "last_bake": {"device": device, "seconds": round(time.time() - t_all, 1), "entries": report},
        })
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        log("wrote", manifest_path, "total seconds", round(time.time() - t_all, 1))
    return report


if __name__ == "__main__":
    main()
