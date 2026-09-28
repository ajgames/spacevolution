"""Tiny runner so build steps can be re-executed from inside Blender.

    exec(open(bpy.path.abspath("//scripts/run.py")).read())
    run("build_greybox")          # imports scripts/build_greybox.py and calls build()
"""
import importlib
import sys

import bpy

sys.dont_write_bytecode = True      # keep scripts/ free of __pycache__ (the folder is synced)
SCRIPTS_DIR = bpy.path.abspath("//scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


def run(module_name, func="build", **kwargs):
    import lib_ship
    importlib.reload(lib_ship)
    for name in list(sys.modules):
        if name.startswith(("build_", "lib_", "shots", "verify_")) and name != "lib_ship":
            importlib.reload(sys.modules[name])
    mod = importlib.import_module(module_name)
    mod = importlib.reload(mod)
    return getattr(mod, func)(**kwargs)
