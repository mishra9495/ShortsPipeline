import bpy
m = bpy.data.materials["TracheaWall"]
nt = m.node_tree
b = nt.nodes["Principled BSDF"]
for s in b.inputs:
    if s.links:
        print("LINK", s.name, "<-", s.links[0].from_node.name, s.links[0].from_socket.name)
out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
print("OUT", [(s.name, s.links[0].from_node.name if s.links else None) for s in out.inputs])
print("OUTPUTS", [(n.name, n.is_active_output, n.target) for n in nt.nodes if n.type == "OUTPUT_MATERIAL"])
print("TRACHEA_MATS", [s.material.name for s in bpy.data.objects["Trachea"].material_slots])
print("TRACHEA_VIS", bpy.data.objects["Trachea"].visible_camera, bpy.data.objects["Trachea"].hide_viewport)
