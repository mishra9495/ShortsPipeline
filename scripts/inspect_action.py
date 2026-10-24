import sys
import bpy

path, name = sys.argv[sys.argv.index("--") + 1:][:2]
with bpy.data.libraries.load(path) as (src, dst):
    dst.actions = [name]
action = bpy.data.actions[name]
print("FRAME_RANGE", tuple(action.frame_range))
fcurves = action.fcurves if hasattr(action, "fcurves") else None
print("HAS_FCURVES_DIRECT", fcurves is not None, len(fcurves) if fcurves else 0)
if fcurves is None:
    print("SLOTS", [s.name for s in action.slots])
    for layer in action.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                print("CHANNELBAG for slot", cb.slot.name if hasattr(cb, 'slot') else '?', "fcurves", len(cb.fcurves))
                for fc in list(cb.fcurves)[:3]:
                    vals = [(kp.co.x, round(kp.co.y, 4)) for kp in fc.keyframe_points]
                    print(" FC", fc.data_path, fc.array_index, vals[:5], "..." if len(vals) > 5 else "")
else:
    for fc in list(fcurves)[:5]:
        vals = [(kp.co.x, round(kp.co.y, 4)) for kp in fc.keyframe_points]
        print(" FC", fc.data_path, fc.array_index, vals[:5])
