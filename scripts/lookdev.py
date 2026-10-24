"""Lookdev render of a character .blend: one close-up and one full-body still.

Run: blender -b <char.blend> --python lookdev.py -- <out_prefix>
"""
import math
import sys

import bpy
from mathutils import Vector

sys.path.append(r"D:\ShortsPipeline\scripts")
import pipeline as P  # noqa: E402

out = sys.argv[sys.argv.index("--") + 1]
scene = bpy.context.scene
P.setup_render(scene, samples=160)
P.studio_lighting(scene)

rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
head = rig.matrix_world @ rig.data.bones["mixamorig:Head"].head_local

shots = {
    "face": (head + Vector((0.35, -0.75, 0.06)), head + Vector((0, 0, 0.06)), 70),
    "body": (Vector((1.3, -3.6, 1.05)), Vector((0, 0, 0.9)), 50),
}
for name, (loc, target, lens) in shots.items():
    cam = P.add_camera(scene, name, loc, target, lens)
    scene.camera = cam
    scene.render.filepath = f"{out}_{name}.png"
    bpy.ops.render.render(write_still=True)
    print("RENDERED", scene.render.filepath)
