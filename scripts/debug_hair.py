import bpy
hair_obj = bpy.data.objects["Hero.hair"]
deps = bpy.context.evaluated_depsgraph_get()
eh = hair_obj.evaluated_get(deps)
data = eh.data
print("CURVES_COUNT", len(data.curves) if hasattr(data, "curves") else "n/a")
print("POINTS_COUNT", len(data.points) if hasattr(data, "points") else "n/a")
body = bpy.data.objects["Hero.body"]
print("HAS_HELPER_HAIR_GROUP", "helper-hair" in body.vertex_groups)
if "helper-hair" in body.vertex_groups:
    vg = body.vertex_groups["helper-hair"]
    idx = vg.index
    count = 0
    maxw = 0
    for v in body.data.vertices:
        for g in v.groups:
            if g.group == idx:
                count += 1
                maxw = max(maxw, g.weight)
    print("HELPER_HAIR_VERTS", count, "maxw", maxw, "total_verts", len(body.data.vertices))
tree = hair_obj.modifiers["HairGen"].node_group
gen = tree.nodes["Group"]
print("GEN_INPUTS", [(i.name, i.default_value if hasattr(i, 'default_value') else None) for i in gen.inputs])
print("GEN_OUTPUTS", [o.name for o in gen.outputs])
