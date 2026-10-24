import bpy

rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
print("OBJECTS", [(o.name, o.type, o.parent.name if o.parent else None) for o in bpy.data.objects])
print("RIG_LOC", tuple(rig.location))
for n in ("Hips", "Spine", "Spine2", "Neck", "Head", "HeadTop_End", "LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase",
          "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand", "RightHand", "LeftHandIndex1", "LeftHandThumb1"):
    b = rig.data.bones.get("mixamorig:" + n)
    if b:
        print("BONE", n, tuple(round(v, 3) for v in b.head_local), tuple(round(v, 3) for v in b.tail_local))
meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.data.shape_keys]
for o in meshes:
    print("SHAPEKEYS", o.name, len(o.data.shape_keys.key_blocks), [k.name for k in o.data.shape_keys.key_blocks])
body = bpy.data.objects["Hero.body"]
for i, s in enumerate(body.material_slots):
    print("BODY_MAT", i, s.material.name)
print("FINGER_BONES", [b.name for b in rig.data.bones if "Hand" in b.name])
