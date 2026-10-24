import bpy
body = bpy.data.objects["Hero.body"]
print("MW", body.matrix_world)
deps = bpy.context.evaluated_depsgraph_get()
m = body.evaluated_get(deps).to_mesh()
xs = [v.co for v in m.vertices]
print("N", len(xs), "MIN", [min(c[i] for c in xs) for i in range(3)], "MAX", [max(c[i] for c in xs) for i in range(3)])
mid = [c for c in xs if abs(c.x) < 0.012]
print("MID", len(mid), sorted(round(c.z, 2) for c in mid)[::max(1, len(mid) // 40)])
