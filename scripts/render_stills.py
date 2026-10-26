"""Render full-quality preview stills of the open .blend (for review before a full render).

Run: blender -b scene.blend --python render_stills.py -- <out_dir> [f1,f2,...]
With no frame list, 12 frames spread evenly over the timeline are rendered. Uses the shot camera from the
timeline markers at each frame, OptiX GPU when available.
"""
import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
out_dir = argv[0]
frames = [int(f) for f in argv[1].split(",") if f.strip()] if len(argv) > 1 and argv[1].strip() else []
scene = bpy.context.scene
if not frames:
    n = 12
    frames = [int(scene.frame_start + (scene.frame_end - scene.frame_start) * (i + 0.5) / n) for i in range(n)]
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.refresh_devices()
    for d in prefs.devices:
        d.use = d.type == "OPTIX"
    scene.cycles.device = "GPU"
except Exception as exc:
    print("STILL no OptiX, CPU render:", exc)
os.makedirs(out_dir, exist_ok=True)
for f in frames:
    scene.frame_set(f)
    marks = [m for m in scene.timeline_markers if m.frame <= f and m.camera]
    if marks:
        scene.camera = max(marks, key=lambda m: m.frame).camera
    scene.render.filepath = os.path.join(out_dir, f"still_{f:05d}.png")
    bpy.ops.render.render(write_still=True)
    print("STILL", f, scene.render.filepath, flush=True)
