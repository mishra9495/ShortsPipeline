import bpy
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
for name in ("LeftArm", "LeftShoulder", "Hips"):
    pb = rig.pose.bones["mixamorig:" + name]
    print(name, "rotation_mode", pb.rotation_mode, "euler", tuple(round(c, 3) for c in pb.rotation_euler),
          "quat", tuple(round(c, 3) for c in pb.rotation_quaternion))
