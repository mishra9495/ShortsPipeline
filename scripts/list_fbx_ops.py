import bpy
ops = [o for o in dir(bpy.ops.export_scene)] if hasattr(bpy.ops, "export_scene") else []
print("EXPORT_SCENE", ops)
ops2 = [o for o in dir(bpy.ops.import_scene)] if hasattr(bpy.ops, "import_scene") else []
print("IMPORT_SCENE", ops2)
print("WM_HAS_FBX_EXPORT", hasattr(bpy.ops.wm, "fbx_export"))
print("WM_HAS_FBX_IMPORT", hasattr(bpy.ops.wm, "fbx_import"))
