"""Rebuild the whole ship from scratch, in pipeline order (a few seconds).

    exec(open(bpy.path.abspath("//scripts/run.py")).read()); run("rebuild_all")

Does not export or bake: run the export_ship.py / bake_lightmaps.py text blocks
afterwards.
"""
import importlib

STEPS = ["gen_textures", "build_materials", "build_structure", "build_props", "build_detail",
         "prepare_lightmaps", "build_lighting", "finalize"]


def build():
    out = {}
    for step in STEPS:
        mod = importlib.reload(importlib.import_module(step))
        out[step] = mod.build()
    return out
