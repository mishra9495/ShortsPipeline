"""Minimal isolated test: grow hair curves off a plain UV sphere, no masking, to find the
simplest working node hookup for 'Generate Hair Curves' before layering complexity back on."""
import bpy

NODE_LIB = r"C:\Program Files\Blender Foundation\Blender 5.2\5.2\datafiles\assets\nodes\procedural_hair_node_assets.blend"
with bpy.data.libraries.load(NODE_LIB) as (src, dst):
    dst.node_groups = ["Generate Hair Curves"]

bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5)
sphere = bpy.context.active_object
sphere.data.uv_layers.new(name="UVMap")
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.uv.smart_project()
bpy.ops.object.mode_set(mode="OBJECT")

hair_data = bpy.data.hair_curves.new("TestHair")
hair_obj = bpy.data.objects.new("TestHairObj", hair_data)
bpy.context.scene.collection.objects.link(hair_obj)

geo = hair_obj.modifiers.new("HairGen", "NODES")
tree = bpy.data.node_groups.new("TestHairTree", "GeometryNodeTree")
geo.node_group = tree
tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
out_node = tree.nodes.new("NodeGroupOutput")

obj_info = tree.nodes.new("GeometryNodeObjectInfo")
obj_info.inputs["Object"].default_value = sphere
obj_info.transform_space = "RELATIVE"

gen = tree.nodes.new("GeometryNodeGroup")
gen.node_tree = bpy.data.node_groups["Generate Hair Curves"]
tree.links.new(obj_info.outputs["Geometry"], gen.inputs["Hair Surface"])
gen.inputs["Surface"].default_value = sphere
uv_attr = tree.nodes.new("GeometryNodeInputNamedAttribute")
uv_attr.data_type = "FLOAT_VECTOR"
uv_attr.inputs["Name"].default_value = "UVMap"
tree.links.new(uv_attr.outputs["Attribute"], gen.inputs["Surface UV Map"])
gen.inputs["Hair Length"].default_value = 0.1
gen.inputs["Density"].default_value = 500.0
tree.links.new(gen.outputs["Curves"], out_node.inputs[0])

# enumerate the Surface Source menu options
menu_sock = gen.inputs["Surface Source"]
print("SURFACE_SOURCE_ITEMS", [e.identifier for e in menu_sock.bl_rna.properties["default_value"].enum_items] if hasattr(menu_sock.bl_rna.properties["default_value"], "enum_items") else "n/a")

bpy.context.view_layer.update()
deps = bpy.context.evaluated_depsgraph_get()
eh = hair_obj.evaluated_get(deps)
print("CURVES_COUNT (Attached+Surface+UV)", len(eh.data.curves))

for src_mode in ("Input", "Object", "Attached"):
    try:
        gen.inputs["Surface Source"].default_value = src_mode
        bpy.context.view_layer.update()
        deps = bpy.context.evaluated_depsgraph_get()
        eh = hair_obj.evaluated_get(deps)
        print("MODE", src_mode, "CURVES_COUNT", len(eh.data.curves))
    except Exception as e:
        print("MODE", src_mode, "ERROR", e)
