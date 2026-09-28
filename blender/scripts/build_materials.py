"""Shared material set. Everything is a Principled BSDF fed by image textures or
flat values, so it survives glTF export 1:1.

Image textures read the first UV map ("UVMap" -> TEXCOORD_0) explicitly, so the
second map ("lightmap" -> TEXCOORD_1) never gets used for surface textures.

Emissive materials carry a custom property "light_role" that the bake script
uses to switch them per lighting state:
  strip     ceiling light strips  (on in normal only)
  indicator amber/red indicator lamps and displays (on in every state)
  screen    workstation / pod screens (on in every state)
  alarm     alarm beacons (on in emergency only)
  dynamic   the blinking engineering button + lamp (driven by code, off in every bake)
"""
import bpy

TEX = "//textures/"


def _img(name, colorspace):
    img = bpy.data.images.get(name)
    if img is None:
        img = bpy.data.images.load(bpy.path.abspath(TEX + name), check_existing=True)
    img.colorspace_settings.name = colorspace
    return img


def _reset(name):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (400, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m, nt, bsdf


def _textured(name, base, orm, normal, normal_strength=1.0, viewport=(0.5, 0.5, 0.5), metal=0.0):
    m, nt, bsdf = _reset(name)
    # Solid-mode viewport colour (the base-colour image is also made the active
    # node so Solid > Texture shows the trim sheet)
    m.diffuse_color = (*viewport, 1)
    m.metallic = metal
    m.roughness = 0.6
    uv = nt.nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    uv.location = (-1000, 0)
    tb = nt.nodes.new("ShaderNodeTexImage")
    tb.image = _img(base, "sRGB")
    tb.location = (-600, 300)
    to = nt.nodes.new("ShaderNodeTexImage")
    to.image = _img(orm, "Non-Color")
    to.location = (-600, 0)
    tn = nt.nodes.new("ShaderNodeTexImage")
    tn.image = _img(normal, "Non-Color")
    tn.location = (-600, -300)
    for t in (tb, to, tn):
        nt.links.new(uv.outputs["UV"], t.inputs["Vector"])
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    sep.location = (-300, 0)
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nm.location = (-300, -300)
    nm.uv_map = "UVMap"
    nm.inputs["Strength"].default_value = normal_strength
    nt.links.new(tb.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(to.outputs["Color"], sep.inputs["Color"])
    nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
    nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    nt.links.new(tn.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    nt.nodes.active = tb
    return m


def _emissive(name, color, strength, role, base=None, image=None, roughness=0.4, viewport=None):
    m, nt, bsdf = _reset(name)
    m.diffuse_color = (*(viewport or color), 1)
    bsdf.inputs["Base Color"].default_value = (*(base or color), 1)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Emission Strength"].default_value = strength
    if image:
        uv = nt.nodes.new("ShaderNodeUVMap")
        uv.uv_map = "UVMap"
        uv.location = (-700, 0)
        ti = nt.nodes.new("ShaderNodeTexImage")
        ti.image = _img(image, "sRGB")
        ti.location = (-400, 0)
        nt.links.new(uv.outputs["UV"], ti.inputs["Vector"])
        nt.links.new(ti.outputs["Color"], bsdf.inputs["Emission Color"])
        nt.nodes.active = ti
    else:
        bsdf.inputs["Emission Color"].default_value = (*color, 1)
    m["light_role"] = role
    m["emission_on"] = strength
    return m


def build():
    made = []
    made.append(_textured("MAT_trim", "trim_basecolor.png", "trim_orm.png", "trim_normal.png", 0.8,
                          viewport=(0.07, 0.13, 0.12)))
    made.append(_textured("MAT_floor", "floor_basecolor.png", "floor_orm.png", "floor_normal.png", 0.8,
                          viewport=(0.035, 0.037, 0.037), metal=0.2))
    # Screens: placeholder CRT image; the game replaces it with a render texture.
    made.append(_emissive("MAT_screen", (1, 1, 1), 1.6, "screen", base=(0.02, 0.03, 0.03),
                          image="screen_placeholder.png", roughness=0.15, viewport=(0.02, 0.06, 0.05)))
    made.append(_emissive("MAT_display", (1, 1, 1), 1.4, "indicator", base=(0.02, 0.03, 0.03),
                          image="display_readouts.png", roughness=0.2, viewport=(0.3, 0.15, 0.02)))
    made.append(_emissive("MAT_emit_amber", (1.0, 0.55, 0.12), 3.0, "indicator"))
    made.append(_emissive("MAT_emit_red", (1.0, 0.06, 0.03), 3.0, "alarm"))
    # The engineering blink button + its lamp: driven by game code, never baked.
    made.append(_emissive("MAT_emit_blink", (1.0, 0.06, 0.03), 4.0, "dynamic"))
    made.append(_emissive("MAT_emit_warm", (1.0, 0.80, 0.58), 6.0, "strip", roughness=0.3))

    # Pod nameplates: UVs fill 0-1 so the game can drop in a per-pod name texture.
    m, nt, bsdf = _reset("MAT_nameplate")
    uv = nt.nodes.new("ShaderNodeUVMap")
    uv.uv_map = "UVMap"
    ti = nt.nodes.new("ShaderNodeTexImage")
    ti.image = _img("nameplate_placeholder.png", "sRGB")
    nt.links.new(uv.outputs["UV"], ti.inputs["Vector"])
    nt.links.new(ti.outputs["Color"], bsdf.inputs["Base Color"])
    nt.nodes.active = ti
    m.diffuse_color = (0.3, 0.3, 0.29, 1)
    bsdf.inputs["Metallic"].default_value = 0.3
    bsdf.inputs["Roughness"].default_value = 0.45
    made.append(m)

    # Frosted glass for the cryo pods (alpha blended; exported as alphaMode BLEND).
    m, nt, bsdf = _reset("MAT_glass_frost")
    bsdf.inputs["Base Color"].default_value = (0.34, 0.45, 0.47, 1)
    bsdf.inputs["Roughness"].default_value = 0.3
    bsdf.inputs["Alpha"].default_value = 0.3
    m.diffuse_color = (0.34, 0.45, 0.47, 0.3)
    m.surface_render_method = "BLENDED"
    m.use_backface_culling = False
    made.append(m)

    # Single-sided everywhere except glass: exports as glTF doubleSided = false, which
    # three.js renders with backface culling (cheaper, and every face here is wound
    # to face the player).
    for m in made:
        m.use_backface_culling = m.name != "MAT_glass_frost"

    # drop the stock material if nothing uses it
    stock = bpy.data.materials.get("Material")
    if stock is not None and stock.users == 0:
        bpy.data.materials.remove(stock)
    return {"materials": [x.name for x in made]}
