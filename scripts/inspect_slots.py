import sys
import bpy

path, name = sys.argv[sys.argv.index("--") + 1:][:2]
with bpy.data.libraries.load(path) as (src, dst):
    dst.actions = [name]
action = bpy.data.actions[name]
print("SLOTS", [(s.identifier, s.name_display, s.target_id_type) for s in action.slots])
for layer in action.layers:
    for strip in layer.strips:
        for cb in strip.channelbags:
            print("CB slot_handle", cb.slot_handle, "fcurves", len(cb.fcurves))
            for fc in cb.fcurves:
                if "LeftArm" in fc.data_path and "rotation" in fc.data_path:
                    vals = [(kp.co.x, round(kp.co.y, 4)) for kp in fc.keyframe_points]
                    print("  FC", fc.data_path, fc.array_index, vals)
