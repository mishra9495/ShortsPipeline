"""Remove the per-frame NOISE f-curve modifiers from every camera (they were causing visible
high-frequency jitter / shake instead of subtle handheld motion) and re-save.
Run: blender -b blend/sneeze.blend --python fix_camera_shake.py -- blend/sneeze.blend
"""
import sys

import bpy

out = sys.argv[sys.argv.index("--") + 1]
removed = 0
for obj in bpy.data.objects:
    if obj.type != "CAMERA":
        continue
    if not obj.animation_data or not obj.animation_data.action:
        continue
    act = obj.animation_data.action
    fcurves = act.fcurves if hasattr(act, "fcurves") else []
    # Blender 5.x layered actions: fall back to legacy fcurves if present, else channelbag.
    if not list(fcurves):
        try:
            from bpy_extras import anim_utils
            slot = obj.animation_data.action_slot
            cb = anim_utils.action_get_channelbag_for_slot(act, slot)
            fcurves = cb.fcurves
        except Exception as e:
            print("WARN no fcurves for", obj.name, e)
            continue
    for fc in fcurves:
        for mod in list(fc.modifiers):
            if mod.type == "NOISE":
                fc.modifiers.remove(mod)
                removed += 1
    print(obj.name, "cleaned")

print("REMOVED", removed, "noise modifiers")
bpy.ops.wm.save_as_mainfile(filepath=out)
print("SAVED", out)
