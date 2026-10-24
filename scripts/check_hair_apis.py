import bpy
mat = bpy.data.materials.new("T")
mat.use_nodes = True
mat.node_tree.nodes.clear()
bsdf = mat.node_tree.nodes.new("ShaderNodeBsdfHairPrincipled")
print("HAIR_BSDF_PARAMETRIZATION", bsdf.parametrization, bsdf.bl_rna.properties["parametrization"].enum_items.keys())
print("HAIR_BSDF_INPUTS", [i.name for i in bsdf.inputs])

NODE_LIB = r"C:\Program Files\Blender Foundation\Blender 5.2\5.2\datafiles\assets\nodes\procedural_hair_node_assets.blend"
with bpy.data.libraries.load(NODE_LIB) as (src, dst):
    dst.node_groups = ["Rotate Hair Curves", "Shrinkwrap Hair Curves", "Straighten Hair Curves"]
for name in ("Rotate Hair Curves", "Shrinkwrap Hair Curves", "Straighten Hair Curves"):
    ng = bpy.data.node_groups[name]
    print(name, [(i.name, i.socket_type) for i in ng.interface.items_tree if getattr(i, "in_out", None) == "INPUT"])
