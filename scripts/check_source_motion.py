import bpy
from mathutils import Vector

bpy.ops.import_scene.fbx(filepath=r"D:\ShortsPipeline\assets\mixamo_test\TestWave.fbx",
                         ignore_leaf_bones=True, automatic_bone_orientation=False)
src = next(o for o in bpy.data.objects if o.type == "ARMATURE")
scene = bpy.context.scene
for f in (1, 15, 30):
    scene.frame_set(f)
    hand = src.matrix_world @ src.pose.bones["mixamorig:LeftForeArm"].tail
    arm_q = src.pose.bones["mixamorig:LeftArm"].rotation_quaternion
    fore_q = src.pose.bones["mixamorig:LeftForeArm"].rotation_quaternion
    print("SRC FRAME", f, "ForeArm tail world", tuple(round(c, 3) for c in hand),
          "ArmQ", tuple(round(c, 3) for c in arm_q), "ForeQ", tuple(round(c, 3) for c in fore_q))
    # also print local axes of ForeArm bone in world space, to see what "local X" actually points along
    m = src.matrix_world.to_3x3() @ src.pose.bones["mixamorig:LeftForeArm"].bone.matrix_local.to_3x3()
    print("   ForeArm rest local axes in world: X", tuple(round(c, 2) for c in m.col[0]),
          "Y(bone dir)", tuple(round(c, 2) for c in m.col[1]), "Z", tuple(round(c, 2) for c in m.col[2]))
