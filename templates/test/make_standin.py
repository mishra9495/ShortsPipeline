"""Stand-in hero: Mixamo-named T-pose rig facing -Y + a crude skinned body with a nose,
ARKit shape keys and an MPFB-like skin group, saved as <root>/blend/char_hero.blend."""
import sys, math
import bpy, bmesh
from mathutils import Vector
OUT = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.read_factory_settings(use_empty=True)
MX = "mixamorig:"
B = {  # name: (head, tail, parent)
 "Hips": ((0,0,0.95),(0,0,1.05),None), "Spine": ((0,0,1.05),(0,0,1.17),"Hips"),
 "Spine1": ((0,0,1.17),(0,0,1.29),"Spine"), "Spine2": ((0,0,1.29),(0,0,1.42),"Spine1"),
 "Neck": ((0,0,1.42),(0,0,1.52),"Spine2"), "Head": ((0,0,1.52),(0,0,1.70),"Neck"),
}
for s, sx in (("Left",1),("Right",-1)):
    B.update({
     f"{s}Shoulder": ((0.02*sx,0,1.40),(0.17*sx,0,1.40),"Spine2"),
     f"{s}Arm": ((0.17*sx,0,1.40),(0.45*sx,0,1.40),f"{s}Shoulder"),
     f"{s}ForeArm": ((0.45*sx,0,1.40),(0.70*sx,0,1.40),f"{s}Arm"),
     f"{s}Hand": ((0.70*sx,0,1.40),(0.80*sx,0,1.40),f"{s}ForeArm"),
     f"{s}UpLeg": ((0.1*sx,0,0.95),(0.1*sx,0,0.52),"Hips"),
     f"{s}Leg": ((0.1*sx,0,0.52),(0.1*sx,0,0.1),f"{s}UpLeg"),
     f"{s}Foot": ((0.1*sx,0,0.1),(0.1*sx,-0.13,0.03),f"{s}Leg"),
    })
    for fi, fy in (("Thumb", -0.03), ("Index", -0.015), ("Middle", 0.0)):
        prev = f"{s}Hand"
        for j in (1,2,3):
            x0 = (0.80 + 0.025*(j-1))*sx
            B[f"{s}Hand{fi}{j}"] = ((x0,fy,1.40),(x0+0.025*sx,fy,1.40),prev)
            prev = f"{s}Hand{fi}{j}"
arm = bpy.data.armatures.new("HeroRig")
rig = bpy.data.objects.new("Hero", arm)
bpy.context.scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
for n,(h,t,p) in B.items():
    eb = arm.edit_bones.new(MX+n); eb.head=h; eb.tail=t
for n,(h,t,p) in B.items():
    if p: arm.edit_bones[MX+n].parent = arm.edit_bones[MX+p]; arm.edit_bones[MX+n].use_connect = False
bpy.ops.object.mode_set(mode="OBJECT")
# body: one capsule per main bone + head with nose
parts = []
def capsule(bone, r):
    h, t, _ = B[bone]; h, t = Vector(h), Vector(t)
    d = t - h
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=r, depth=d.length, location=(h+t)/2)
    o = bpy.context.active_object
    o.rotation_euler = d.to_track_quat("Z","Y").to_euler()
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    vg = o.vertex_groups.new(name=MX+bone); vg.add(list(range(len(o.data.vertices))), 1.0, "REPLACE")
    parts.append(o)
for b, r in (("Hips",0.15),("Spine",0.14),("Spine1",0.15),("Spine2",0.16),("Neck",0.05)):
    capsule(b, r)
for s in ("Left","Right"):
    for b, r in (("Arm",0.045),("ForeArm",0.04),("Hand",0.035),("UpLeg",0.075),("Leg",0.055),("Foot",0.045)):
        capsule(s+b, r)
bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=24, radius=1, location=(0,0.01,1.63))
hd = bpy.context.active_object; hd.scale = (0.08,0.105,0.12)
bpy.ops.object.transform_apply(scale=True)
bpy.ops.mesh.primitive_cone_add(vertices=12, radius1=0.016, radius2=0.002, depth=0.035, location=(0,-0.105,1.60), rotation=(math.radians(90),0,0))
nose = bpy.context.active_object
for o in (hd, nose):
    vg = o.vertex_groups.new(name=MX+"Head"); vg.add(list(range(len(o.data.vertices))), 1.0, "REPLACE"); parts.append(o)
bpy.ops.object.select_all(action="DESELECT")
for o in parts: o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.join()
body = bpy.context.active_object; body.name = "Hero.body"
bpy.ops.object.shade_smooth()
body.parent = rig
mod = body.modifiers.new("Armature","ARMATURE"); mod.object = rig
# skin material with an MPFB-like group node
m = bpy.data.materials.new("HeroSkin"); m.use_nodes = True
ng = bpy.data.node_groups.new("SkinGroup","ShaderNodeTree")
ng.interface.new_socket("Roughness", in_out="INPUT", socket_type="NodeSocketFloat")
ng.interface.new_socket("BSDF", in_out="OUTPUT", socket_type="NodeSocketShader")
gi = ng.nodes.new("NodeGroupInput"); go = ng.nodes.new("NodeGroupOutput"); pb = ng.nodes.new("ShaderNodeBsdfPrincipled")
pb.inputs["Base Color"].default_value = (0.8,0.55,0.45,1)
ng.links.new(gi.outputs[0], pb.inputs["Roughness"]); ng.links.new(pb.outputs[0], go.inputs[0])
nt = m.node_tree; out = nt.nodes["Material Output"]; nt.nodes.remove(nt.nodes["Principled BSDF"])
g = nt.nodes.new("ShaderNodeGroup"); g.node_tree = ng; nt.links.new(g.outputs[0], out.inputs["Surface"])
body.data.materials.append(m)
body.shape_key_add(name="Basis")
for k in ("eyeBlinkLeft","eyeBlinkRight","noseSneerLeft","noseSneerRight","mouthSmileLeft","mouthSmileRight","jawOpen","browInnerUp"):
    body.shape_key_add(name=k)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("STANDIN SAVED", OUT, len(body.data.vertices))
