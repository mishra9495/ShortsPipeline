import bpy
scene = bpy.context.scene
m = bpy.data.materials["TracheaWall"]
nt = m.node_tree
for n in nt.nodes:
    if n.type == "MIX":
        print("MIXNODE", n.name, n.data_type, [(s.name, s.type, s.enabled) for s in n.inputs], [(s.name, s.type, s.enabled, bool(s.links)) for s in n.outputs])
    if n.type == "MATH" and n.operation == "MULTIPLY" and abs(n.inputs[1].default_value - 0.0034) < 1e-6:
        n.inputs[1].default_value = float(__import__("sys").argv[-1])
scene.frame_set(520)
scene.camera = bpy.data.objects["CamXClose"]
scene.render.resolution_percentage = 30
scene.cycles.samples = 16
scene.render.filepath = r"D:\ShortsPipeline\renders\test_sneeze\dbg_tear.png"
bpy.ops.render.render(write_still=True)
