import bpy
import inspect
print([n for n in dir(bpy.types.Bone) if "convert" in n.lower() or "space" in n.lower()])
print([n for n in dir(bpy.types.PoseBone) if "convert" in n.lower() or "space" in n.lower()])
arm = bpy.data.armatures.new("A")
obj = bpy.data.objects.new("O", arm)
bpy.context.collection.objects.link(obj)
bpy.context.view_layer.objects.active = obj
bpy.ops.object.mode_set(mode="EDIT")
b = arm.edit_bones.new("Test")
b.head, b.tail = (0, 0, 0), (0, 1, 0)
bpy.ops.object.mode_set(mode="OBJECT")
fn = bpy.types.Object.bl_rna.functions["convert_space"]
for p in fn.parameters:
    print("PARAM", p.identifier, getattr(p, "enum_items", None) and [e.identifier for e in p.enum_items])


