import bpy

body = bpy.data.objects["Hero.body"]
keys = [k.name for k in body.data.shape_keys.key_blocks]
print("KEYS", keys[-60:])
for slot in body.material_slots:
    m = slot.material
    print("MAT", m.name)
    for n in m.node_tree.nodes:
        extra = ""
        if n.type == "GROUP":
            extra = f" group={n.node_tree.name} inputs=" + str([(i.name, getattr(i, 'default_value', None) if not hasattr(getattr(i, 'default_value', None), '__len__') else tuple(i.default_value)) for i in n.inputs if not i.is_linked])
        if n.type == "BSDF_PRINCIPLED":
            extra = " " + str({i.name: (i.default_value if not hasattr(i.default_value, '__len__') else tuple(i.default_value)) for i in n.inputs if not i.is_linked and hasattr(i, 'default_value') and i.name in ('Roughness', 'Subsurface Weight', 'Subsurface Radius', 'Subsurface Scale', 'Coat Weight', 'Specular IOR Level')})
        if n.type == "TEX_IMAGE" and n.image:
            extra = f" img={n.image.name} {tuple(n.image.size)}"
        print("  NODE", n.type, n.name, extra)
