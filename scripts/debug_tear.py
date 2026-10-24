import bpy
m = bpy.data.materials["TracheaWall"]
nt = m.node_tree
print("ANIM", nt.animation_data, nt.animation_data.action if nt.animation_data else None)
for f in (60, 70, 100, 497, 505, 520, 700, 850):
    bpy.context.scene.frame_set(f)
    print("F", f, "tear", round(nt.nodes["TearOpen"].outputs[0].default_value, 3),
          "press", round(nt.nodes["Pressure"].outputs[0].default_value, 3),
          "trachea_hide", bpy.data.objects["Trachea"].hide_render)
