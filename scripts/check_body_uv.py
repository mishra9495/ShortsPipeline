import bpy
body = bpy.data.objects["Hero.body"]
print("UV_LAYERS", [uv.name for uv in body.data.uv_layers])
tree = bpy.data.node_groups["HeroHairTree"]
gen = tree.nodes["Group"]
uv_input = gen.inputs["Surface UV Map"]
print("UV_INPUT_TYPE", uv_input.type, "default", uv_input.default_value)
