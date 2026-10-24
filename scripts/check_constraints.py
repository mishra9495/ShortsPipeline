import bpy
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
for name in ("LeftArm", "LeftForeArm", "LeftHand", "Hips"):
    pb = rig.pose.bones["mixamorig:" + name]
    print(name, "constraints", [(c.type, c.name) for c in pb.constraints],
          "bone.length", round(pb.bone.length, 4),
          "bone.use_connect", pb.bone.use_connect,
          "parent", pb.parent.name if pb.parent else None)
print("ARMATURE_MODS on Hero.body", [(m.type, m.name, getattr(m, 'use_deform_preserve_volume', None)) for m in bpy.data.objects["Hero.body"].modifiers])
