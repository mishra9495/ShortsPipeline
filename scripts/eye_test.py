"""Eye shader A/B test: renders tight eye close-ups for several cornea settings."""
import sys

import bpy
from mathutils import Vector

sys.path.append(r"D:\ShortsPipeline\scripts")
import pipeline as P  # noqa: E402

scene = bpy.context.scene
P.setup_render(scene, samples=96, w=720, h=360)
P.studio_lighting(scene)
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
head = rig.matrix_world @ rig.data.bones["mixamorig:Head"].head_local
eye_c = head + Vector((0.0, -0.09, 0.075))
cam = P.add_camera(scene, "EyeCam", eye_c + Vector((0.05, -0.32, 0.0)), eye_c, 85, fstop=8)
scene.camera = cam

eyes = bpy.data.objects["Hero.high-poly"]
mat = eyes.material_slots[0].material
grp = next(n for n in mat.node_tree.nodes if n.type == "GROUP")
print("EYEMATS", [s.material.name for s in eyes.material_slots], "blend", getattr(mat, "blend_method", None))
for k in [k for k in eyes.data.shape_keys.key_blocks] if eyes.data.shape_keys else []:
    pass

variants = {
    "a_default": {},
    "b_no_transmission": {"OuterLayerTransmission": 0.0, "OuterLayerAlpha": 0.0},
    "c_brown_open": {"OuterLayerTransmission": 0.0, "OuterLayerAlpha": 0.0,
                     "IrisMajorColor": (0.32, 0.19, 0.07, 1), "IrisMinorColor": (0.09, 0.05, 0.02, 1),
                     "PupilSize": 0.22},
}
orig = {i.name: (tuple(i.default_value) if hasattr(i.default_value, "__len__") else i.default_value)
        for i in grp.inputs if hasattr(i, "default_value")}
for name, settings in variants.items():
    for k, v in orig.items():
        grp.inputs[k].default_value = v
    for k, v in settings.items():
        grp.inputs[k].default_value = v
    scene.render.filepath = rf"D:\ShortsPipeline\renders\eye_{name}.png"
    bpy.ops.render.render(write_still=True)
    print("RENDERED", name)
