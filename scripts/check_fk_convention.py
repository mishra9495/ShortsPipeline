"""Empirically determine Blender's pose_bone -> world matrix FK convention for LeftArm."""
import math
import bpy
from mathutils import Quaternion, Vector

rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
pb = rig.pose.bones["mixamorig:LeftArm"]
bone = pb.bone
pb.rotation_mode = "QUATERNION"

# Rest state readings
g_rest = rig.matrix_world.to_quaternion() @ bone.matrix_local.to_quaternion()
parent_g_rest = (rig.matrix_world.to_quaternion() @ bone.parent.matrix_local.to_quaternion()) if bone.parent else rig.matrix_world.to_quaternion()
r_local = parent_g_rest.inverted() @ g_rest  # my computed "rest rotation relative to parent"
print("g_rest", tuple(round(c, 3) for c in g_rest))
print("parent_g_rest", tuple(round(c, 3) for c in parent_g_rest))
print("r_local (my formula)", tuple(round(c, 3) for c in r_local))

test_q = Quaternion((0, 0, 1), math.radians(60))
pb.rotation_quaternion = test_q
bpy.context.view_layer.update()
deps = bpy.context.evaluated_depsgraph_get()
epb = rig.evaluated_get(deps).pose.bones["mixamorig:LeftArm"]
w_actual = rig.matrix_world.to_quaternion() @ epb.matrix.to_quaternion()
print("ACTUAL world rot after setting local=60degZ:", tuple(round(c, 3) for c in w_actual))

my_predicted = parent_g_rest @ r_local @ test_q
print("MY PREDICTED (parent_g_rest @ r_local @ local):", tuple(round(c, 3) for c in my_predicted))

alt_predicted = g_rest @ test_q
print("ALT PREDICTED (g_rest @ local, i.e. R interpreted as world-rest directly):", tuple(round(c, 3) for c in alt_predicted))

alt2 = g_rest @ test_q @ g_rest.inverted() @ g_rest  # same as alt really
rest_dir = Vector((0, 1, 0))
print("tail displacement check:")
old = rig.matrix_world @ bone.tail_local
new = rig.matrix_world @ epb.tail
print(" rest tail", tuple(round(c, 3) for c in old), "-> new tail", tuple(round(c, 3) for c in new),
      "delta", round((new - old).length, 4))
