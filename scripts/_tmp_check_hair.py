import bpy
print("OBJECTS:", [o.name for o in bpy.data.objects if "hair" in o.name.lower() or "scalp" in o.name.lower() or "short02" in o.name.lower()])
