"""Patch sneeze.blend to render at full 1080x1920 (resolution_percentage=100) and re-save.
Run: blender -b blend/sneeze.blend --python fix_resolution.py -- blend/sneeze.blend
"""
import sys

import bpy

out = sys.argv[sys.argv.index("--") + 1]
scene = bpy.context.scene
print("BEFORE", scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage)
scene.render.resolution_percentage = 100
print("AFTER", scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage)
bpy.ops.wm.save_as_mainfile(filepath=out)
print("SAVED", out)
