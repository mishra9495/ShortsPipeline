"""Render a frame range of the open .blend on the GPU (OptiX prefs are not stored in .blend files).

Run: blender -b scene.blend --python render_anim.py -- <out_dir> <start> <end>
Skips frames that already exist, so interrupted renders resume.
"""
import os
import sys

import bpy

out_dir, start, end = sys.argv[sys.argv.index("--") + 1:][:3]
prefs = bpy.context.preferences.addons["cycles"].preferences
prefs.compute_device_type = "OPTIX"
prefs.refresh_devices()
for d in prefs.devices:
    d.use = d.type == "OPTIX"
scene = bpy.context.scene
scene.cycles.device = "GPU"
scene.render.use_persistent_data = True
os.makedirs(out_dir, exist_ok=True)
for f in range(int(start), int(end) + 1):
    path = os.path.join(out_dir, f"f{f:04d}.png")
    if os.path.exists(path):
        continue
    scene.frame_set(f)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("FRAME", f, flush=True)
