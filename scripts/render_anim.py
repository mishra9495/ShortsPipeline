"""Render a frame range of the open .blend on the GPU (OptiX prefs are not stored in .blend files).

Run: blender -b scene.blend --python render_anim.py -- <out_dir> <start> <end>
Skips frames that already exist, so interrupted renders resume.
"""
import os
import sys

import bpy

out_dir, start, end = sys.argv[sys.argv.index("--") + 1:][:3]
prefs = bpy.context.preferences.addons["cycles"].preferences
scene = bpy.context.scene
try:
    prefs.compute_device_type = "OPTIX"
    prefs.refresh_devices()
    for d in prefs.devices:
        d.use = d.type == "OPTIX"
    scene.cycles.device = "GPU"
except TypeError:  # no NVIDIA driver: CPU render (test boxes); the render PC always has OptiX
    scene.cycles.device = "CPU"
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
scene.render.use_persistent_data = True
os.makedirs(out_dir, exist_ok=True)
# Never run past the scene's own end: daily_render.ps1 passes 9999 as "all of it".
start, end = max(int(start), scene.frame_start), min(int(end), scene.frame_end)
print("RANGE", start, end, flush=True)
for f in range(start, end + 1):
    path = os.path.join(out_dir, f"f{f:04d}.png")
    if os.path.exists(path):
        continue
    scene.frame_set(f)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("FRAME", f, flush=True)
