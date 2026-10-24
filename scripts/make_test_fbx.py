"""Build a synthetic Mixamo-style skeleton (T-pose, same bone names) with a simple arm-raise
animation, and export as FBX, purely to validate retarget.py before real Mixamo downloads arrive.
"""
import math
import sys

import bpy
from mathutils import Vector

OUT = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)

# bone, head, tail, parent  (meters, true T-pose: arms along +/-X)
BONES = [
    ("Hips", (0, 0, 0.95), (0, 0, 1.05), None),
    ("Spine", (0, 0, 1.05), (0, 0, 1.18), "Hips"),
    ("Spine1", (0, 0, 1.18), (0, 0, 1.32), "Spine"),
    ("Spine2", (0, 0, 1.32), (0, 0, 1.45), "Spine1"),
    ("Neck", (0, 0, 1.45), (0, 0, 1.52), "Spine2"),
    ("Head", (0, 0, 1.52), (0, 0, 1.68), "Neck"),
    ("LeftShoulder", (0.05, 0, 1.44), (0.14, 0, 1.44), "Spine2"),
    ("LeftArm", (0.14, 0, 1.44), (0.42, 0, 1.44), "LeftShoulder"),
    ("LeftForeArm", (0.42, 0, 1.44), (0.68, 0, 1.44), "LeftArm"),
    ("LeftHand", (0.68, 0, 1.44), (0.78, 0, 1.44), "LeftForeArm"),
    ("RightShoulder", (-0.05, 0, 1.44), (-0.14, 0, 1.44), "Spine2"),
    ("RightArm", (-0.14, 0, 1.44), (-0.42, 0, 1.44), "RightShoulder"),
    ("RightForeArm", (-0.42, 0, 1.44), (-0.68, 0, 1.44), "RightArm"),
    ("RightHand", (-0.68, 0, 1.44), (-0.78, 0, 1.44), "RightForeArm"),
    ("LeftUpLeg", (0.09, 0, 0.95), (0.1, 0, 0.5), "Hips"),
    ("LeftLeg", (0.1, 0, 0.5), (0.1, 0, 0.08), "LeftUpLeg"),
    ("LeftFoot", (0.1, 0, 0.08), (0.1, 0.12, 0.02), "LeftLeg"),
    ("RightUpLeg", (-0.09, 0, 0.95), (-0.1, 0, 0.5), "Hips"),
    ("RightLeg", (-0.1, 0, 0.5), (-0.1, 0, 0.08), "RightUpLeg"),
    ("RightFoot", (-0.1, 0, 0.08), (-0.1, 0.12, 0.02), "RightLeg"),
]

arm_data = bpy.data.armatures.new("mixamorig")
arm = bpy.data.objects.new("mixamorig:Hips", arm_data)
bpy.context.collection.objects.link(arm)
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode="EDIT")
eb = arm_data.edit_bones
for name, head, tail, parent in BONES:
    b = eb.new("mixamorig:" + name)
    b.head, b.tail = Vector(head), Vector(tail)
    if parent:
        b.parent = eb["mixamorig:" + parent]
bpy.ops.object.mode_set(mode="OBJECT")

action = bpy.data.actions.new("TestWave")
arm.animation_data_create()
arm.animation_data.action = action
for pb in arm.pose.bones:
    pb.rotation_mode = "QUATERNION"
for f in (1, 15, 30):
    t = (f - 1) / 29
    raise_amt = math.sin(t * math.pi)
    from mathutils import Quaternion
    for side, sign in (("Left", 1), ("Right", -1)):
        pb = arm.pose.bones[f"mixamorig:{side}Arm"]
        # Rotate about local Z (perpendicular to the bone's own Y-axis length), which actually
        # swings the arm up/down -- a rotation about the bone's own axis (Y) would do nothing.
        pb.rotation_quaternion = Quaternion((0, 0, 1), math.radians(60 * raise_amt) * sign)
        pb.keyframe_insert("rotation_quaternion", frame=f)
        fpb = arm.pose.bones[f"mixamorig:{side}ForeArm"]
        fpb.rotation_quaternion = Quaternion((1, 0, 0), math.radians(50 * raise_amt))
        fpb.keyframe_insert("rotation_quaternion", frame=f)
    hips = arm.pose.bones["mixamorig:Hips"]
    hips.location = Vector((0, 0, 0.04 * raise_amt))
    hips.keyframe_insert("location", frame=f)
action.frame_range = (1, 30)
bpy.context.scene.frame_end = 30

bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.fbx(filepath=OUT, use_selection=True, bake_anim=True, add_leaf_bones=False)
print("EXPORTED", OUT)
