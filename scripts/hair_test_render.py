"""Lookdev render focused on the hair: face close-up and a 3/4 head shot."""
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
    "head34": (head + Vector((0.5, -0.55, 0.12)), head + Vector((0, 0, 0.1)), 70),
    "headfront": (head + Vector((0.08, -0.7, 0.08)), head + Vector((0, 0, 0.08)), 85),
}
for name, (loc, target, lens) in shots.items():
    cam = P.add_camera(scene, name, loc, target, lens, fstop=2.2)
    scene.camera = cam
    scene.render.filepath = f"{out}_{name}.png"
    bpy.ops.render.render(write_still=True)
    print("RENDERED", scene.render.filepath)
