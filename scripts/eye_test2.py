"""Eye close-up render of a character .blend (any eye material). Arg: out png."""
import sys

import bpy
from mathutils import Vector

sys.path.append(r"D:\ShortsPipeline\scripts")
import pipeline as P  # noqa: E402

out = sys.argv[sys.argv.index("--") + 1]
scene = bpy.context.scene
P.setup_render(scene, samples=96, w=720, h=360)
P.studio_lighting(scene)
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
head = rig.matrix_world @ rig.data.bones["mixamorig:Head"].head_local
eye_c = head + Vector((0.0, -0.09, 0.115))
scene.camera = P.add_camera(scene, "EyeCam", eye_c + Vector((0.05, -0.32, 0.0)), eye_c, 85, fstop=8)
mat = bpy.data.objects["Hero.high-poly"].material_slots[0].material
print("EYEMAT", mat.name, [n.type for n in mat.node_tree.nodes])
scene.render.filepath = out
bpy.ops.render.render(write_still=True)
print("RENDERED", out)
