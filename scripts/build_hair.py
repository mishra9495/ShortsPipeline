"""Replace the hero's low-poly cap hair with real strand-based Hair Curves, grown from the
scalp with Blender's built-in procedural hair geometry-nodes library (clump, frizz, curl for
natural variation) and a hair-strand Principled BSDF (hair BSDF) material.

Run: blender -b blend/char_hero.blend --python build_hair.py -- <out.blend>
"""
import sys

import bpy

OUT = sys.argv[sys.argv.index("--") + 1]
NODE_LIB = r"C:\Program Files\Blender Foundation\Blender 5.2\5.2\datafiles\assets\nodes\procedural_hair_node_assets.blend"
NODE_NAMES = ["Generate Hair Curves", "Interpolate Hair Curves", "Clump Hair Curves",
              "Frizz Hair Curves", "Curl Hair Curves", "Set Hair Curve Profile", "Smooth Hair Curves",
              "Shrinkwrap Hair Curves", "Rotate Hair Curves"]

with bpy.data.libraries.load(NODE_LIB) as (src, dst):
    dst.node_groups = [n for n in NODE_NAMES if n in src.node_groups]

body = bpy.data.objects["Hero.body"]
old_hair = bpy.data.objects.get("Hero.short02")
if old_hair:
    bpy.data.objects.remove(old_hair, do_unlink=True)

# Extract a dedicated scalp-only mesh from MPFB's "helper-hair" vertex group, rather than
# feeding a live vertex-group attribute into the hair-generation node tree: a Density Mask
# attribute lookup against the body mesh did not survive evaluation reliably (0 curves out),
# while growing hair from an actual small scalp mesh works and is simpler to reason about.
dup = body.copy()
dup.data = body.data.copy()
dup.name = "Hero.scalp"
bpy.context.scene.collection.objects.link(dup)
vg = dup.vertex_groups.get("helper-hair")
if vg is None:
    raise RuntimeError("Hero.body has no 'helper-hair' vertex group to build the scalp mesh from")
bpy.context.view_layer.objects.active = dup
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="DESELECT")
bpy.ops.object.mode_set(mode="OBJECT")
dup.vertex_groups.active_index = vg.index
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.object.vertex_group_set_active(group="helper-hair")
bpy.ops.object.vertex_group_select()
bpy.ops.mesh.select_all(action="INVERT")
bpy.ops.mesh.delete(type="VERT")
bpy.ops.object.mode_set(mode="OBJECT")
dup.modifiers.clear()
print("SCALP_VERTS", len(dup.data.vertices))
dup.hide_render = True
dup.hide_viewport = True
scalp_obj = dup


def hair_material():
    m = bpy.data.materials.new("HeroHair")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    bsdf = nt.nodes.new("ShaderNodeBsdfHairPrincipled")
    # Melanin parametrization is the physically-robust path for Cycles hair; direct "Color" mode
    # has to invert reflectance into absorption and renders chalky/blown-out on thin, undersampled
    # strands (confirmed by a debug render: even dark input colors came back near-pure-white).
    bsdf.parametrization = "MELANIN"
    bsdf.inputs["Melanin"].default_value = 0.75  # dark brown
    bsdf.inputs["Melanin Redness"].default_value = 0.15
    bsdf.inputs["Roughness"].default_value = 0.25
    bsdf.inputs["Radial Roughness"].default_value = 0.35
    bsdf.inputs["IOR"].default_value = 1.55
    bsdf.inputs["Random Color"].default_value = 0.1
    curveinfo = nt.nodes.new("ShaderNodeHairInfo")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.65, 0.65, 0.65, 1)  # roots: less melanin-shift -> darker
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (0.9, 0.9, 0.9, 1)  # tips slightly lighter
    nt.links.new(curveinfo.outputs["Intercept"], ramp.inputs["Fac"])
    melanin_mul = nt.nodes.new("ShaderNodeMath")
    melanin_mul.operation = "MULTIPLY"
    melanin_mul.inputs[1].default_value = 0.75
    nt.links.new(ramp.outputs["Color"], melanin_mul.inputs[0])
    nt.links.new(melanin_mul.outputs[0], bsdf.inputs["Melanin"])
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
    return m


mat = hair_material()
hair_data = bpy.data.hair_curves.new("HeroHairCurves")
hair_obj = bpy.data.objects.new("Hero.hair", hair_data)
bpy.context.scene.collection.objects.link(hair_obj)
hair_obj.parent = body  # parented for convenience; curve surface-attachment (below) handles deform
hair_data.materials.append(mat)

geo = hair_obj.modifiers.new("HairGen", "NODES")
tree = bpy.data.node_groups.new("HeroHairTree", "GeometryNodeTree")
geo.node_group = tree
tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
out_node = tree.nodes.new("NodeGroupOutput")

obj_info = tree.nodes.new("GeometryNodeObjectInfo")
obj_info.inputs["Object"].default_value = scalp_obj
obj_info.transform_space = "RELATIVE"

gen = tree.nodes.new("GeometryNodeGroup")
gen.node_tree = bpy.data.node_groups["Generate Hair Curves"]
tree.links.new(obj_info.outputs["Geometry"], gen.inputs["Hair Surface"])
gen.inputs["Surface"].default_value = scalp_obj
uv_attr = tree.nodes.new("GeometryNodeInputNamedAttribute")
uv_attr.data_type = "FLOAT_VECTOR"
uv_attr.inputs["Name"].default_value = body.data.uv_layers[0].name if body.data.uv_layers else "UVMap"
tree.links.new(uv_attr.outputs["Attribute"], gen.inputs["Surface UV Map"])
gen.inputs["Surface Source"].default_value = "Object"  # 'Attached' needs a prior bake; this is first generation
gen.inputs["Hair Length"].default_value = 0.05  # short men's cut; grown-out "sea urchin" look at longer lengths
gen.inputs["Control Points"].default_value = 6
gen.inputs["Density"].default_value = 1400.0
gen.inputs["Attach to Surface"].default_value = True

interp = tree.nodes.new("GeometryNodeGroup")
interp.node_tree = bpy.data.node_groups["Interpolate Hair Curves"]
interp.inputs["Interpolation Guides"].default_value = 4
interp.inputs["Density"].default_value = 24000.0
tree.links.new(gen.outputs["Curves"], interp.inputs["Geometry"])

clump = tree.nodes.new("GeometryNodeGroup")
clump.node_tree = bpy.data.node_groups["Clump Hair Curves"]
clump.inputs["Factor"].default_value = 0.55
clump.inputs["Tip Spread"].default_value = 0.05
tree.links.new(interp.outputs[0], clump.inputs["Geometry"])

frizz = tree.nodes.new("GeometryNodeGroup")
frizz.node_tree = bpy.data.node_groups["Frizz Hair Curves"]
frizz.inputs["Factor"].default_value = 0.08
frizz.inputs["Distance"].default_value = 0.01
tree.links.new(clump.outputs[0], frizz.inputs["Geometry"])

profile = tree.nodes.new("GeometryNodeGroup")
profile.node_tree = bpy.data.node_groups["Set Hair Curve Profile"]
profile.inputs["Radius"].default_value = 0.0006
profile.inputs["Factor Min"].default_value = 0.3
tree.links.new(frizz.outputs[0], profile.inputs["Geometry"])

# Strands grow straight out along the scalp's surface normal, which on a round head means
# "in every direction" (a "sea urchin"). A real short haircut is combed backward from the
# crown: bend each strand, root-locked, toward -Y (the character faces -Y) and slightly down,
# so it lies against the head instead of standing straight up off the normal.
comb = tree.nodes.new("GeometryNodeGroup")
comb.node_tree = bpy.data.node_groups["Rotate Hair Curves"]
comb.inputs["Factor"].default_value = 1.0
comb.inputs["Axis"].default_value = (1, 0, 0)
comb.inputs["Angle"].default_value = 1.9  # ~109 deg: tips swept back past horizontal
comb.inputs["Random Offset"].default_value = 0.35
comb.inputs["Lock Ends"].default_value = False  # False = lock ROOT end, rotate the rest (combing)
tree.links.new(profile.outputs[0], comb.inputs["Geometry"])

wrap = tree.nodes.new("GeometryNodeGroup")
wrap.node_tree = bpy.data.node_groups["Shrinkwrap Hair Curves"]
wrap.inputs["Surface Input Type"].default_value = "Object"
wrap.inputs[2].default_value = scalp_obj  # the Object-typed "Surface" socket (2nd of 2 same-name sockets)
wrap.inputs["Factor"].default_value = 0.35
wrap.inputs["Offset Distance"].default_value = 0.01
wrap.inputs["Above Surface"].default_value = 0.004
wrap.inputs["Lock Roots"].default_value = True
tree.links.new(comb.outputs[0], wrap.inputs["Geometry"])

set_mat = tree.nodes.new("GeometryNodeSetMaterial")
set_mat.inputs["Material"].default_value = mat
tree.links.new(wrap.outputs[0], set_mat.inputs["Geometry"])
tree.links.new(set_mat.outputs[0], out_node.inputs[0])

print("HAIR_OBJ", hair_obj.name, "modifier_tree_nodes", [n.name for n in tree.nodes])
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("SAVED", OUT)
