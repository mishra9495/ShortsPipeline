"""Apply a saved retargeted action to the hero and render 3 stills to sanity-check it."""
import sys

import bpy
from mathutils import Vector

sys.path.append(r"D:\ShortsPipeline\scripts")
import pipeline as P  # noqa: E402

action_path, action_name, out_prefix = sys.argv[sys.argv.index("--") + 1:][:3]
with bpy.data.libraries.load(action_path) as (src, dst):
    dst.actions = [action_name]
action = bpy.data.actions[action_name]

rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
if rig.animation_data is None:
    rig.animation_data_create()
rig.animation_data.action = action
if action.slots:  # Blender 4.4+ layered-action system: binding the slot is required when the
    rig.animation_data.action_slot = action.slots[0]  # action was assigned to a different object
fs, fe = int(action.frame_range[0]), int(action.frame_range[1])

scene = bpy.context.scene
P.setup_render(scene, samples=64)
P.studio_lighting(scene)
head = rig.matrix_world @ rig.data.bones["mixamorig:Head"].head_local
scene.camera = P.add_camera(scene, "VerifyCam", (2.2, -4.2, 1.0), (0, 0, 0.9), 35)

for f in (fs, (fs + fe) // 2, fe):
    scene.frame_set(f)
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    erig = rig.evaluated_get(deps)
    elbow_w = erig.matrix_world @ erig.pose.bones["mixamorig:LeftArm"].tail
    hand_w = erig.matrix_world @ erig.pose.bones["mixamorig:LeftHand"].tail
    print("FRAME", f, "LeftArm(elbow) world pos", tuple(round(c, 3) for c in elbow_w),
          "LeftHand world pos", tuple(round(c, 3) for c in hand_w))
    for name in ("Hips", "Spine", "Spine1", "Spine2", "LeftShoulder", "LeftArm"):
        q = erig.pose.bones["mixamorig:" + name].rotation_quaternion
        loc = erig.pose.bones["mixamorig:" + name].location
        print("  CHAIN", name, "quat", tuple(round(c, 4) for c in q), "loc", tuple(round(c, 4) for c in loc))
    scene.render.filepath = f"{out_prefix}_f{f:03d}.png"
    bpy.ops.render.render(write_still=True)
    print("RENDERED", scene.render.filepath)

pbL = rig.pose.bones["mixamorig:LeftArm"]
pbR = rig.pose.bones["mixamorig:RightArm"]
print("ARM_WORLD_Z", round((rig.matrix_world @ pbL.tail).z, 3), round((rig.matrix_world @ pbR.tail).z, 3))
