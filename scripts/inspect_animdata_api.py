import bpy

print("ANIMDATA_PROPS", [p.identifier for p in bpy.types.AnimData.bl_rna.properties])
print("ANIMDATA_FUNCS", [f.identifier for f in bpy.types.AnimData.bl_rna.functions])
print("ID_FUNCS_WITH_ACTION", [f.identifier for f in bpy.types.ID.bl_rna.functions if "action" in f.identifier.lower()])
print("ACTION_SLOT_PROPS", [p.identifier for p in bpy.types.ActionSlot.bl_rna.properties])
