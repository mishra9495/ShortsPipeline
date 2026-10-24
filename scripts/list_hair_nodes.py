import bpy

path = r"C:\Program Files\Blender Foundation\Blender 5.2\5.2\datafiles\assets\nodes\procedural_hair_node_assets.blend"
with bpy.data.libraries.load(path) as (src, dst):
    names = list(src.node_groups)
print("HAIRNODES", names)
dst_names = ["Generate Hair Curves", "Interpolate Hair Curves", "Clump Hair Curves", "Frizz Hair Curves",
             "Set Hair Curve Profile", "Smooth Hair Curves", "Curl Hair Curves", "Trim Hair Curves"]
with bpy.data.libraries.load(path) as (src, dst):
    dst.node_groups = [n for n in dst_names if n in src.node_groups]
for ng in bpy.data.node_groups:
    if ng.name in dst_names:
        print("NG", ng.name, [(i.name, i.socket_type) for i in ng.interface.items_tree
                              if getattr(i, "in_out", None) == "INPUT"])
