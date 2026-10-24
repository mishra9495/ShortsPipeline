import sys
import bpy
from mathutils import Vector
sys.path.append(r"D:\ShortsPipeline\scripts")
import pipeline as P

out = sys.argv[sys.argv.index("--") + 1]
scene = bpy.context.scene
P.setup_render(scene, samples=400, w=600, h=600)
scene.cycles.use_denoising = True
P.sky_world(scene, strength=0.5)
P.area_light("Key", (0.3, -0.5, 1.9), (0, 0, 1.6), 200, 1.0)

rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
head = rig.matrix_world @ rig.data.bones["mixamorig:Head"].head_local
scene.camera = P.add_camera(scene, "Cam", head + Vector((0.2, -0.55, 0.2)), head + Vector((0, 0, 0.15)), 85, fstop=4)
scene.render.filepath = out
bpy.ops.render.render(write_still=True)
print("RENDERED", out)

mat = bpy.data.objects["Hero.hair"].data.materials[0]
bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_HAIR_PRINCIPLED")
print("HAIR_PARAM", bsdf.parametrization)
print("PROFILE_RADIUS check via modifier eval:")
hair_obj = bpy.data.objects["Hero.hair"]
deps = bpy.context.evaluated_depsgraph_get()
eh = hair_obj.evaluated_get(deps)
print("N_CURVES", len(eh.data.curves), "N_POINTS", len(eh.data.points))
if hasattr(eh.data, "attributes") and "radius" in eh.data.attributes:
    rad = eh.data.attributes["radius"].data[0].value
    print("FIRST_RADIUS", rad)
