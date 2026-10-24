"""Isolated check: set frame straight to 15, no prior frame_set/render calls, no camera/render setup."""
import sys
import bpy

action_path, action_name = sys.argv[sys.argv.index("--") + 1:][:2]
with bpy.data.libraries.load(action_path) as (src, dst):
    dst.actions = [action_name]
action = bpy.data.actions[action_name]
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
if rig.animation_data is None:
    rig.animation_data_create()
rig.animation_data.action = action
if action.slots:
    rig.animation_data.action_slot = action.slots[0]

bpy.context.scene.frame_set(15)
bpy.context.view_layer.update()
deps = bpy.context.evaluated_depsgraph_get()
erig = rig.evaluated_get(deps)
elbow_w = erig.matrix_world @ erig.pose.bones["mixamorig:LeftArm"].tail
print("ISOLATED FRAME15 elbow", tuple(round(c, 3) for c in elbow_w))
rest = erig.matrix_world @ erig.data.bones["mixamorig:LeftArm"].tail_local
print("ISOLATED FRAME15 rest_tail", tuple(round(c, 3) for c in rest))
print("ISOLATED FRAME15 delta_len", round((elbow_w - rest).length, 4))
