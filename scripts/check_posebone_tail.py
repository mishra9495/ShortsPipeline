import bpy
props = [p.identifier for p in bpy.types.PoseBone.bl_rna.properties]
print("POSEBONE_HAS_TAIL", "tail" in props)
print("POSEBONE_PROPS_WITH_TAIL_OR_HEAD", [p for p in props if "tail" in p or "head" in p])
