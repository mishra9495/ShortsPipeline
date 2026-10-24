import sys
import bpy

path, name = sys.argv[sys.argv.index("--") + 1:][:2]
with bpy.data.libraries.load(path) as (src, dst):
    dst.actions = [name]
action = bpy.data.actions[name]
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
print("SUITABLE", [s.identifier for s in rig.action_suitable_slots] if hasattr(rig, "action_suitable_slots") else "n/a")
rig.animation_data_create()
rig.animation_data.action = action
print("SLOT_AFTER_ACTION_ASSIGN", rig.animation_data.action_slot)
rig.animation_data.action_slot = action.slots[0]
print("SLOT_AFTER_EXPLICIT", rig.animation_data.action_slot, rig.animation_data.action_slot_handle)

scene = bpy.context.scene
for f in (1, 15, 30):
    scene.frame_set(f)
    pb = rig.pose.bones["mixamorig:LeftArm"]
    print("FRAME", f, "quat", tuple(round(c, 3) for c in pb.rotation_quaternion))
