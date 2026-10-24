import bpy

eyes = bpy.data.objects["Hero.high-poly"]
for slot in eyes.material_slots:
    for n in slot.material.node_tree.nodes:
        if n.type == "GROUP":
            print("EYEGROUP", n.node_tree.name, [(i.name, tuple(i.default_value) if hasattr(i.default_value, "__len__") else round(i.default_value, 3))
                                                 for i in n.inputs if hasattr(i, "default_value") and not i.is_linked])
hair = bpy.data.objects["Hero.short02"]
print("HAIRVERTS", len(hair.data.vertices))
print("VGROUPS", [g.name for g in bpy.data.objects["Hero.body"].vertex_groups if not g.name.startswith("mixamorig")][:40])
