"""Procedural modelling kit: everything is built inside Blender from code (no downloaded assets).

    import kit as K
    K.init(scene)                       # once, after the character .blend is open
    sofa = K.sofa(K.coll("Home"), loc=(0, 0.3, 0), color=(0.08, 0.22, 0.25))

Every builder returns a root Empty (or the object) so it can be moved/parented as one piece.
Units are metres; +Y is "back" (characters face -Y), Z is up.
Materials are fully procedural (wood grain, woven fabric, clear-coat car paint, ...).
"""
import math
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

SCENE = None
RNG = random.Random(7)


def init(scene, seed=7):
    global SCENE, RNG
    SCENE = scene
    RNG = random.Random(seed)


def coll(name):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        SCENE.collection.children.link(c)
    return c


def _link(o, c):
    for uc in list(o.users_collection):
        uc.objects.unlink(o)
    c.objects.link(o)
    return o


def empty(name, c, loc=(0, 0, 0), rot=(0, 0, 0)):
    e = bpy.data.objects.new(name, None)
    c.objects.link(e)
    e.location = loc
    e.rotation_euler = rot
    e.empty_display_size = 0.2
    return e


def parent(children, root):
    for o in children:
        o.parent = root
    return root


# =============================================================== materials
_MATS = {}


def _new_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    return m, m.node_tree.nodes, m.node_tree.links, m.node_tree.nodes["Principled BSDF"]


def _coord(N, mapping_scale=(1, 1, 1), space="Object"):
    tc = N.new("ShaderNodeTexCoord")
    mp = N.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = mapping_scale
    N.id_data.links.new(tc.outputs[space], mp.inputs["Vector"])
    return mp


def _bump(N, L, b, height_socket, strength=0.2, distance=0.01):
    bp = N.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value = strength
    bp.inputs["Distance"].default_value = distance
    L.new(height_socket, bp.inputs["Height"])
    L.new(bp.outputs["Normal"], b.inputs["Normal"])
    return bp


def _ramp(N, a, b, pos=(0.0, 1.0)):
    r = N.new("ShaderNodeValToRGB")
    r.color_ramp.elements[0].position = pos[0]
    r.color_ramp.elements[0].color = (*a, 1)
    r.color_ramp.elements[1].position = pos[1]
    r.color_ramp.elements[1].color = (*b, 1)
    return r


def mat_cached(key, fn):
    if key not in _MATS:
        _MATS[key] = fn()
    return _MATS[key]


def wood(name="Wood", light=(0.42, 0.25, 0.12), dark=(0.20, 0.10, 0.04), rough=0.42, scale=1.0, coat=0.25):
    """Straight-grain wood running along the object's local X axis."""
    def make():
        m, N, L, b = _new_mat(name)
        mp = _coord(N, (scale * 0.6, scale * 1.0, scale * 1.0))
        warp = N.new("ShaderNodeTexNoise")
        warp.inputs["Scale"].default_value = 1.6
        warp.inputs["Detail"].default_value = 3
        L.new(mp.outputs[0], warp.inputs["Vector"])
        mixv = N.new("ShaderNodeMix")
        mixv.data_type = "VECTOR"
        mixv.inputs["Factor"].default_value = 0.18
        L.new(mp.outputs[0], mixv.inputs["A"])
        L.new(warp.outputs["Color"], mixv.inputs["B"])
        wv = N.new("ShaderNodeTexWave")
        wv.wave_type = "BANDS"
        wv.bands_direction = "Y"
        wv.inputs["Scale"].default_value = 38.0
        wv.inputs["Distortion"].default_value = 7.0
        wv.inputs["Detail"].default_value = 3
        wv.inputs["Detail Scale"].default_value = 1.5
        L.new(mixv.outputs["Result"], wv.inputs["Vector"])
        mid = tuple(0.5 * (a + b) for a, b in zip(dark, light))
        rp = _ramp(N, mid, light, (0.0, 1.0))
        e = rp.color_ramp.elements.new(0.08)
        e.color = (*dark, 1)
        L.new(wv.outputs["Fac"], rp.inputs["Fac"])
        pores = N.new("ShaderNodeTexNoise")
        pores.inputs["Scale"].default_value = 220
        pores.inputs["Detail"].default_value = 2
        L.new(_coord(N, (scale * 0.15, scale * 3.0, scale * 3.0)).outputs[0], pores.inputs["Vector"])
        dk = N.new("ShaderNodeMix")
        dk.data_type = "RGBA"
        dk.blend_type = "MULTIPLY"
        dk.inputs["Factor"].default_value = 0.25
        L.new(rp.outputs["Color"], dk.inputs["A"])
        L.new(pores.outputs["Color"], dk.inputs["B"])
        L.new(dk.outputs["Result"], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = rough
        b.inputs["Coat Weight"].default_value = coat
        b.inputs["Coat Roughness"].default_value = 0.08
        _bump(N, L, b, pores.outputs["Fac"], 0.06, 0.001)
        return m
    return mat_cached(("wood", name), make)


def fabric(name, color, rough=0.85, sheen=0.6, weave=420.0, bump=0.35):
    def make():
        m, N, L, b = _new_mat(name)
        mp = _coord(N, (weave, weave, weave))
        w1 = N.new("ShaderNodeTexWave")
        w1.wave_type = "BANDS"
        w1.bands_direction = "X"
        w1.inputs["Scale"].default_value = 1.0
        w2 = N.new("ShaderNodeTexWave")
        w2.wave_type = "BANDS"
        w2.bands_direction = "Y"
        w2.inputs["Scale"].default_value = 1.0
        L.new(mp.outputs[0], w1.inputs["Vector"])
        L.new(mp.outputs[0], w2.inputs["Vector"])
        mx = N.new("ShaderNodeMath")
        mx.operation = "MULTIPLY"
        L.new(w1.outputs["Fac"], mx.inputs[0])
        L.new(w2.outputs["Fac"], mx.inputs[1])
        nz = N.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 8
        nz.inputs["Detail"].default_value = 4
        L.new(_coord(N).outputs[0], nz.inputs["Vector"])
        tint = N.new("ShaderNodeMix")
        tint.data_type = "RGBA"
        tint.blend_type = "MULTIPLY"
        tint.inputs["Factor"].default_value = 0.25
        tint.inputs["A"].default_value = (*color, 1)
        L.new(nz.outputs["Color"], tint.inputs["B"])
        L.new(tint.outputs["Result"], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = rough
        b.inputs["Sheen Weight"].default_value = sheen
        b.inputs["Sheen Roughness"].default_value = 0.4
        _bump(N, L, b, mx.outputs[0], bump, 0.0015)
        return m
    return mat_cached(("fabric", name), make)


def paint(name, color, rough=0.9, bump=0.03):
    """Matte wall paint with very subtle roller texture."""
    def make():
        m, N, L, b = _new_mat(name)
        nz = N.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 140
        nz.inputs["Detail"].default_value = 8
        L.new(_coord(N).outputs[0], nz.inputs["Vector"])
        b.inputs["Base Color"].default_value = (*color, 1)
        b.inputs["Roughness"].default_value = rough
        _bump(N, L, b, nz.outputs["Fac"], bump, 0.002)
        return m
    return mat_cached(("paint", name), make)


def plastic(name, color, rough=0.35, coat=0.0, sss=0.0):
    def make():
        m, N, L, b = _new_mat(name)
        b.inputs["Base Color"].default_value = (*color, 1)
        b.inputs["Roughness"].default_value = rough
        b.inputs["Coat Weight"].default_value = coat
        if sss:
            b.inputs["Subsurface Weight"].default_value = sss
        return m
    return mat_cached(("plastic", name), make)


def metal(name, color=(0.8, 0.8, 0.82), rough=0.25, brushed=False):
    def make():
        m, N, L, b = _new_mat(name)
        b.inputs["Base Color"].default_value = (*color, 1)
        b.inputs["Metallic"].default_value = 1.0
        b.inputs["Roughness"].default_value = rough
        if brushed:
            nz = N.new("ShaderNodeTexNoise")
            nz.inputs["Scale"].default_value = 2.0
            nz.inputs["Detail"].default_value = 10
            L.new(_coord(N, (1, 1, 400)).outputs[0], nz.inputs["Vector"])
            mr = N.new("ShaderNodeMapRange")
            mr.inputs[3].default_value = rough * 0.6
            mr.inputs[4].default_value = rough * 1.4
            L.new(nz.outputs["Fac"], mr.inputs[0])
            L.new(mr.outputs[0], b.inputs["Roughness"])
        return m
    return mat_cached(("metal", name), make)


def glass(name="Glass", tint=(0.96, 0.98, 1.0), rough=0.0, ior=1.45):
    def make():
        m, N, L, b = _new_mat(name)
        b.inputs["Base Color"].default_value = (*tint, 1)
        b.inputs["Transmission Weight"].default_value = 1.0
        b.inputs["Roughness"].default_value = rough
        b.inputs["IOR"].default_value = ior
        return m
    return mat_cached(("glass", name), make)


def car_paint(name, color, flake=0.25):
    def make():
        m, N, L, b = _new_mat(name)
        vor = N.new("ShaderNodeTexVoronoi")
        vor.inputs["Scale"].default_value = 3000
        L.new(_coord(N).outputs[0], vor.inputs["Vector"])
        mx = N.new("ShaderNodeMix")
        mx.data_type = "RGBA"
        mx.inputs["Factor"].default_value = flake * 0.3
        mx.inputs["A"].default_value = (*color, 1)
        L.new(vor.outputs["Color"], mx.inputs["B"])
        L.new(mx.outputs["Result"], b.inputs["Base Color"])
        b.inputs["Metallic"].default_value = 0.15
        b.inputs["Roughness"].default_value = 0.28
        b.inputs["Coat Weight"].default_value = 1.0
        b.inputs["Coat Roughness"].default_value = 0.02
        return m
    return mat_cached(("carpaint", name), make)


def rubber(name="Rubber", color=(0.025, 0.025, 0.027)):
    def make():
        m, N, L, b = _new_mat(name)
        nz = N.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 300
        L.new(_coord(N).outputs[0], nz.inputs["Vector"])
        b.inputs["Base Color"].default_value = (*color, 1)
        b.inputs["Roughness"].default_value = 0.78
        _bump(N, L, b, nz.outputs["Fac"], 0.15, 0.001)
        return m
    return mat_cached(("rubber", name), make)


def emissive(name, color, strength=5.0):
    def make():
        m, N, L, b = _new_mat(name)
        b.inputs["Base Color"].default_value = (*color, 1)
        b.inputs["Emission Color"].default_value = (*color, 1)
        b.inputs["Emission Strength"].default_value = strength
        return m
    return mat_cached(("emit", name), make)


def leaf(name="Leaf", a=(0.05, 0.16, 0.03), c=(0.16, 0.30, 0.06)):
    def make():
        m, N, L, b = _new_mat(name)
        nz = N.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 3
        L.new(_coord(N, space="Generated").outputs[0], nz.inputs["Vector"])
        rp = _ramp(N, a, c)
        L.new(nz.outputs["Fac"], rp.inputs["Fac"])
        L.new(rp.outputs["Color"], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = 0.55
        b.inputs["Subsurface Weight"].default_value = 0.25
        b.inputs["Coat Weight"].default_value = 0.2
        return m
    return mat_cached(("leaf", name), make)


def ceramic(name, color, rough=0.12):
    return plastic(name, color, rough=rough, coat=0.6)


# =============================================================== mesh helpers
def _finish(o, c, mat=None, smooth=True, bevel=0.0, segments=3, subsurf=0):
    _link(o, c)
    if mat is not None:
        o.data.materials.append(mat)
    if bevel:
        bv = o.modifiers.new("Bevel", "BEVEL")
        bv.width = bevel
        bv.segments = segments
        bv.limit_method = "ANGLE"
        bv.harden_normals = False
    if subsurf:
        ss = o.modifiers.new("Subsurf", "SUBSURF")
        ss.levels = ss.render_levels = subsurf
    if smooth:
        for p in o.data.polygons:
            p.use_smooth = True
        if bevel and not subsurf:
            wn = o.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
            wn.keep_sharp = True
    return o


def rbox(name, c, size, loc=(0, 0, 0), mat=None, bevel=0.01, segments=3, rot=(0, 0, 0), subsurf=0):
    """Box with rounded edges (true geometry), size = full dimensions."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    o.location = loc
    o.rotation_euler = rot
    return _finish(o, c, mat, bevel=bevel, segments=segments, subsurf=subsurf)


def cushion(name, c, size, loc=(0, 0, 0), mat=None, puff=0.25, rot=(0, 0, 0), seed=0):
    """Soft upholstered block: subdivided box, rounded and slightly puffed, with crease wrinkles."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges, cuts=6, use_grid_fill=True)
    sx, sy, sz = size
    for v in bm.verts:
        p = v.co * 2.0                                    # -1..1
        bulge = (1 - p.x * p.x) * (1 - p.y * p.y)
        v.co = Vector((p.x * sx / 2, p.y * sy / 2, p.z * sz / 2 * (1 + puff * bulge * 0.6)))
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    o.location = loc
    o.rotation_euler = rot
    _finish(o, c, mat, subsurf=2)
    tex = bpy.data.textures.new(name + "Wrinkle", "CLOUDS")
    tex.noise_scale = 0.12
    dp = o.modifiers.new("Wrinkle", "DISPLACE")
    dp.texture = tex
    dp.strength = min(size) * 0.025
    dp.texture_coords = "OBJECT"
    return o


def lathe(name, c, profile, loc=(0, 0, 0), mat=None, steps=48, rot=(0, 0, 0), thickness=0.0, subsurf=1):
    """Revolve a 2D profile [(radius, z), ...] around Z (lamps, vases, mugs, wheels, glasses)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    rings = []
    for i in range(steps):
        a = 2 * math.pi * i / steps
        ring = [bm.verts.new((r * math.cos(a), r * math.sin(a), z)) for r, z in profile]
        rings.append(ring)
    for i in range(steps):
        r0, r1 = rings[i], rings[(i + 1) % steps]
        for j in range(len(profile) - 1):
            bm.faces.new((r0[j], r1[j], r1[j + 1], r0[j + 1]))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    o.location = loc
    o.rotation_euler = rot
    _finish(o, c, mat, subsurf=subsurf)
    if thickness:
        so = o.modifiers.new("Solid", "SOLIDIFY")
        so.thickness = thickness
        o.modifiers.move(len(o.modifiers) - 1, 0)
    return o


def tube(name, c, pts, radius, mat=None, res=6, caps=True):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = res
    cu.use_fill_caps = caps
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(pts) - 1)
    for bp, p in zip(sp.bezier_points, pts):
        bp.co = p
        bp.handle_left_type = bp.handle_right_type = "AUTO"
    o = bpy.data.objects.new(name, cu)
    c.objects.link(o)
    if mat:
        o.data.materials.append(mat)
    return o


def cyl(name, c, r, depth, loc=(0, 0, 0), mat=None, rot=(0, 0, 0), verts=32, bevel=0.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=r, radius2=r, depth=depth)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    o.location = loc
    o.rotation_euler = rot
    return _finish(o, c, mat, bevel=bevel)


def sphere(name, c, r, loc=(0, 0, 0), mat=None, scale=(1, 1, 1), subdiv=4):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=r)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    o.location = loc
    o.scale = scale
    return _finish(o, c, mat)


def plane(name, c, size, loc=(0, 0, 0), mat=None, rot=(0, 0, 0)):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
    bmesh.ops.scale(bm, vec=Vector((size[0], size[1], 1)), verts=bm.verts)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    o.location = loc
    o.rotation_euler = rot
    return _finish(o, c, mat, smooth=False)


# =============================================================== furniture & props
def sofa(c, loc=(0, 0, 0), width=2.0, seat_h=0.44, color=(0.07, 0.20, 0.23), name="Sofa"):
    """Three-seat sofa. loc = floor point under the middle of the seat front edge (+Y = back)."""
    root = empty(name, c, loc)
    fab = fabric(name + "Fabric", color)
    leg = wood("SofaLegWood", (0.35, 0.2, 0.09), (0.15, 0.07, 0.03))
    depth, arm_w = 0.9, 0.16
    parts = []
    base_h = seat_h - 0.16
    parts.append(rbox("SofaBase", c, (width, depth, base_h - 0.12), (0, depth / 2, 0.12 + (base_h - 0.12) / 2), fab, bevel=0.03))
    parts.append(rbox("SofaBack", c, (width, 0.2, 0.52), (0, depth - 0.1, base_h + 0.26), fab, bevel=0.05))
    for sx in (-1, 1):
        parts.append(cushion(f"SofaArm{sx}", c, (arm_w, depth, 0.36), (sx * (width / 2 - arm_w / 2), depth / 2, base_h + 0.06), fab, puff=0.15))
    n = 3
    inner = width - 2 * arm_w
    for i in range(n):
        x = -inner / 2 + inner * (i + 0.5) / n
        parts.append(cushion(f"SofaSeat{i}", c, (inner / n - 0.01, depth - 0.24, 0.17), (x, (depth - 0.24) / 2 + 0.02, base_h + 0.085), fab, puff=0.35))
        parts.append(cushion(f"SofaBackCushion{i}", c, (inner / n - 0.02, 0.2, 0.42), (x, depth - 0.3, base_h + 0.36), fab, puff=0.45,
                             rot=(math.radians(-10), 0, 0)))
    for sx in (-1, 1):
        for sy in (0.08, depth - 0.08):
            parts.append(lathe("SofaLeg", c, [(0.0, 0.0), (0.018, 0.0), (0.024, 0.11), (0.03, 0.12), (0.0, 0.12)],
                               (sx * (width / 2 - 0.07), sy, 0), leg, steps=16, subsurf=0))
    # a throw pillow for life
    parts.append(cushion("ThrowPillow", c, (0.36, 0.14, 0.34), (-inner / 2 + 0.25, depth - 0.42, base_h + 0.33),
                         fabric(name + "Pillow", (0.75, 0.55, 0.25), weave=380), puff=0.9, rot=(math.radians(-18), math.radians(8), math.radians(14))))
    return parent(parts, root)


def coffee_table(c, loc=(0, 0, 0), size=(1.1, 0.6), h=0.42, name="CoffeeTable"):
    root = empty(name, c, loc)
    top = wood("WalnutTop", (0.40, 0.22, 0.10), (0.16, 0.08, 0.03), rough=0.3, coat=0.5)
    blk = metal("BlackSteel", (0.03, 0.03, 0.03), rough=0.45)
    parts = [rbox("CTTop", c, (size[0], size[1], 0.035), (0, 0, h - 0.0175), top, bevel=0.008)]
    parts.append(rbox("CTShelf", c, (size[0] - 0.12, size[1] - 0.12, 0.02), (0, 0, 0.12), top, bevel=0.005))
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(rbox("CTLeg", c, (0.035, 0.035, h - 0.035), (sx * (size[0] / 2 - 0.05), sy * (size[1] / 2 - 0.05), (h - 0.035) / 2), blk, bevel=0.004))
    # books on the shelf
    x = -size[0] / 2 + 0.12
    for i, (w, col) in enumerate(((0.28, (0.6, 0.1, 0.08)), (0.25, (0.08, 0.18, 0.35)), (0.22, (0.85, 0.8, 0.7)))):
        parts.append(rbox(f"ShelfBook{i}", c, (w, 0.2, 0.03), (x + 0.15, 0.0, 0.145 + 0.032 * i), plastic(f"BookCover{i}", col, 0.6), bevel=0.003,
                          rot=(0, 0, math.radians(RNG.uniform(-8, 8)))))
    return parent(parts, root)


def tv_unit(c, loc=(0, 0, 0), screen_w=1.25, name="TV", screen_mat=None):
    """Low TV cabinet with a wall-ready flat TV on a stand. loc = floor centre, TV faces -Y."""
    root = empty(name, c, loc)
    cab = wood("OakCabinet", (0.62, 0.45, 0.28), (0.40, 0.26, 0.13), rough=0.4)
    blk = plastic("TVBlack", (0.012, 0.012, 0.014), 0.25, coat=0.3)
    parts = [rbox("TVCabinet", c, (1.8, 0.42, 0.45), (0, 0, 0.27), cab, bevel=0.006)]
    for i in range(3):
        x = -0.6 + 0.6 * i
        parts.append(rbox(f"TVDoorGap{i}", c, (0.58, 0.004, 0.36), (x, -0.211, 0.27), plastic("Gap", (0.05, 0.035, 0.02), 0.6), bevel=0))
        parts.append(rbox(f"TVHandle{i}", c, (0.14, 0.015, 0.012), (x, -0.222, 0.4), metal("Brass", (0.75, 0.55, 0.25), 0.3), bevel=0.003))
    for sx in (-1, 1):
        parts.append(rbox("TVCabLeg", c, (0.03, 0.03, 0.05), (sx * 0.85, 0, 0.025), blk, bevel=0.003))
    sh = screen_w * 9 / 16
    z0 = 0.49 + 0.12
    parts.append(rbox("TVPanel", c, (screen_w + 0.02, 0.035, sh + 0.02), (0, -0.02, z0 + sh / 2), blk, bevel=0.004))
    scr = plane("TVScreen", c, (screen_w, sh), (0, -0.0385, z0 + sh / 2), screen_mat or tv_screen_mat(),
                rot=(math.radians(90), 0, 0))
    parts.append(scr)
    parts.append(rbox("TVNeck", c, (0.06, 0.04, 0.12), (0, 0.0, 0.55), blk, bevel=0.005))
    parts.append(rbox("TVFoot", c, (0.35, 0.22, 0.012), (0, 0.0, 0.497), blk, bevel=0.004))
    parts.append(rbox("Soundbar", c, (0.8, 0.08, 0.06), (0, -0.12, 0.53), fabric("SoundbarMesh", (0.03, 0.03, 0.035), weave=900), bevel=0.02))
    return parent(parts, root)


def tv_screen_mat():
    """Glossy screen showing a soft, moving abstract 'show' (emissive gradient + noise)."""
    def make():
        m, N, L, b = _new_mat("TVScreenMat")
        tc = N.new("ShaderNodeTexCoord")
        nz = N.new("ShaderNodeTexNoise")
        nz.name = "ShowNoise"
        nz.inputs["Scale"].default_value = 2.2
        nz.inputs["Detail"].default_value = 2
        L.new(tc.outputs["Generated"], nz.inputs["Vector"])
        rp = N.new("ShaderNodeValToRGB")
        cr = rp.color_ramp
        cr.elements[0].color = (0.05, 0.12, 0.35, 1)
        cr.elements[1].color = (0.95, 0.55, 0.25, 1)
        e = cr.elements.new(0.5)
        e.color = (0.25, 0.6, 0.8, 1)
        L.new(nz.outputs["Fac"], rp.inputs["Fac"])
        b.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1)
        b.inputs["Roughness"].default_value = 0.05
        b.inputs["Coat Weight"].default_value = 1.0
        L.new(rp.outputs["Color"], b.inputs["Emission Color"])
        b.inputs["Emission Strength"].default_value = 1.6
        return m
    return mat_cached(("tvscreen",), make)


def rug(c, loc=(0, 0, 0), size=(2.4, 1.7), name="Rug", main=(0.55, 0.16, 0.12), border=(0.12, 0.10, 0.18), field=(0.80, 0.72, 0.60)):
    """Wool rug: field colour with a soft woven pattern and a darker border band."""
    def make():
        m, N, L, b = _new_mat("RugMat")
        tc = N.new("ShaderNodeTexCoord")
        sep = N.new("ShaderNodeSeparateXYZ")
        L.new(tc.outputs["Generated"], sep.inputs[0])
        def edge(axis):
            sub = N.new("ShaderNodeMath"); sub.operation = "SUBTRACT"; sub.inputs[1].default_value = 0.5
            L.new(sep.outputs[axis], sub.inputs[0])
            ab = N.new("ShaderNodeMath"); ab.operation = "ABSOLUTE"
            L.new(sub.outputs[0], ab.inputs[0])
            return ab
        mx = N.new("ShaderNodeMath"); mx.operation = "MAXIMUM"
        L.new(edge(0).outputs[0], mx.inputs[0]); L.new(edge(1).outputs[0], mx.inputs[1])
        band = N.new("ShaderNodeMath"); band.operation = "GREATER_THAN"; band.inputs[1].default_value = 0.42
        L.new(mx.outputs[0], band.inputs[0])
        vor = N.new("ShaderNodeTexVoronoi"); vor.inputs["Scale"].default_value = 7
        vor.feature = "DISTANCE_TO_EDGE"
        L.new(tc.outputs["Generated"], vor.inputs["Vector"])
        motif = _ramp(N, main, field, (0.02, 0.09))
        L.new(vor.outputs["Distance"], motif.inputs["Fac"])
        col = N.new("ShaderNodeMix"); col.data_type = "RGBA"
        col.inputs["B"].default_value = (*border, 1)
        L.new(band.outputs[0], col.inputs["Factor"]); L.new(motif.outputs["Color"], col.inputs["A"])
        L.new(col.outputs["Result"], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = 0.95
        b.inputs["Sheen Weight"].default_value = 0.8
        nz = N.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 900
        L.new(_coord(N).outputs[0], nz.inputs["Vector"])
        _bump(N, L, b, nz.outputs["Fac"], 0.5, 0.002)
        return m
    return rbox(name, c, (size[0], size[1], 0.012), (loc[0], loc[1], loc[2] + 0.006), mat_cached(("rug", name), make), bevel=0.004)


def floor_lamp(c, loc=(0, 0, 0), name="FloorLamp", on=True):
    root = empty(name, c, loc)
    blk = metal("LampBlack", (0.02, 0.02, 0.02), 0.35)
    shade = fabric("LampShade", (0.92, 0.88, 0.78), rough=0.9, sheen=0.2)
    parts = [lathe("LampBase", c, [(0, 0), (0.15, 0), (0.15, 0.015), (0.04, 0.03), (0, 0.03)], (0, 0, 0), blk, subsurf=0),
             cyl("LampPole", c, 0.012, 1.4, (0, 0, 0.73), blk, verts=16),
             lathe("LampShadeMesh", c, [(0.23, 0.0), (0.16, 0.30)], (0, 0, 1.38), shade, thickness=0.004, subsurf=0)]
    if on:
        bulb = sphere("LampBulb", c, 0.05, (0, 0, 1.5), emissive("WarmBulb", (1.0, 0.75, 0.45), 40))
        parts.append(bulb)
        ld = bpy.data.lights.new(name + "Light", "POINT")
        ld.energy = 60
        ld.color = (1.0, 0.78, 0.55)
        ld.shadow_soft_size = 0.15
        lo = bpy.data.objects.new(name + "Light", ld)
        c.objects.link(lo)
        lo.location = (0, 0, 1.5)
        parts.append(lo)
    return parent(parts, root)


def potted_plant(c, loc=(0, 0, 0), h=1.1, name="Plant", seed=3):
    """Monstera-ish plant: ceramic pot, soil and curved leaves on stems."""
    rng = random.Random(seed)
    root = empty(name, c, loc)
    pot = ceramic("PotCeramic", (0.85, 0.83, 0.78))
    parts = [lathe("Pot", c, [(0.0, 0.0), (0.13, 0.0), (0.17, 0.32), (0.175, 0.34), (0.16, 0.34), (0.0, 0.34)], (0, 0, 0), pot, subsurf=1),
             cyl("Soil", c, 0.155, 0.01, (0, 0, 0.325), plastic("Soil", (0.06, 0.04, 0.025), 0.95))]
    lm = leaf()
    stem_m = leaf("Stem", (0.12, 0.22, 0.05), (0.18, 0.3, 0.08))
    for i in range(11):
        a = rng.uniform(0, 2 * math.pi)
        tilt = rng.uniform(0.35, 1.0)
        L_ = h * rng.uniform(0.55, 1.0)
        tip = Vector((math.cos(a) * tilt * L_ * 0.55, math.sin(a) * tilt * L_ * 0.55, 0.33 + L_ * (1 - 0.35 * tilt)))
        mid = Vector((tip.x * 0.4, tip.y * 0.4, 0.33 + (tip.z - 0.33) * 0.75))
        parts.append(tube(f"Stem{i}", c, [Vector((0, 0, 0.32)), mid, tip], 0.006, stem_m, res=2))
        parts.append(_leaf_mesh(f"Leaf{i}", c, tip, a, rng.uniform(0.24, 0.36), lm, rng))
    return parent(parts, root)


def _leaf_mesh(name, c, at, heading, size, mat, rng):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    nu, nv = 10, 6
    grid = []
    for i in range(nu + 1):
        u = i / nu
        width = math.sin(math.pi * u) ** 0.7 * 1.1
        row = []
        for j in range(nv + 1):
            v = (j / nv - 0.5) * 2
            x = u * size
            y = v * width * size * 0.5
            z = -0.25 * size * u * u + 0.05 * size * (1 - v * v)
            row.append(bm.verts.new((x, y, z)))
        grid.append(row)
    for i in range(nu):
        for j in range(nv):
            bm.faces.new((grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]))
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    o.location = at
    o.rotation_euler = (rng.uniform(-0.3, 0.3), rng.uniform(-0.6, -0.1), heading)
    _finish(o, c, mat, subsurf=1)
    so = o.modifiers.new("Solid", "SOLIDIFY")
    so.thickness = 0.002
    return o


def bookshelf(c, loc=(0, 0, 0), w=0.9, h=1.8, name="Bookshelf", seed=5):
    rng = random.Random(seed)
    root = empty(name, c, loc)
    wd = wood("ShelfWood", (0.78, 0.62, 0.45), (0.55, 0.40, 0.26), rough=0.5)
    d = 0.32
    parts = [rbox("ShelfSideL", c, (0.025, d, h), (-w / 2, 0, h / 2), wd, bevel=0.003),
             rbox("ShelfSideR", c, (0.025, d, h), (w / 2, 0, h / 2), wd, bevel=0.003),
             rbox("ShelfBack", c, (w, 0.01, h), (0, d / 2 - 0.005, h / 2), wd, bevel=0)]
    levels = 5
    cols = [(0.55, 0.08, 0.06), (0.08, 0.2, 0.4), (0.85, 0.78, 0.6), (0.1, 0.3, 0.15), (0.9, 0.5, 0.1), (0.2, 0.2, 0.22), (0.6, 0.6, 0.65)]
    for k in range(levels + 1):
        z = 0.04 + k * (h - 0.06) / levels
        parts.append(rbox(f"Shelf{k}", c, (w - 0.02, d - 0.02, 0.022), (0, 0, z), wd, bevel=0.003))
        if k == levels:
            continue
        x = -w / 2 + 0.03
        gap = (h - 0.06) / levels
        while x < w / 2 - 0.08:
            if rng.random() < 0.12:
                x += 0.08
                continue
            bw = rng.uniform(0.02, 0.045)
            bh = gap * rng.uniform(0.6, 0.85)
            lean = math.radians(rng.choice((0, 0, 0, 6, -4)))
            parts.append(rbox("Book", c, (bw, rng.uniform(0.18, 0.24), bh), (x + bw / 2, -0.02, z + 0.011 + bh / 2),
                              plastic(f"Book{rng.randrange(len(cols))}", rng.choice(cols), 0.55), bevel=0.002, rot=(0, lean, 0)))
            x += bw + 0.002
    return parent(parts, root)


def picture_frame(c, loc, size=(0.6, 0.8), name="Art", seed=1, rot=(0, 0, 0)):
    root = empty(name, c, loc, rot)
    frm = wood("FrameWood", (0.1, 0.07, 0.05), (0.05, 0.03, 0.02), rough=0.35)

    def make():
        m, N, L, b = _new_mat(f"ArtPaint{seed}")
        tc = N.new("ShaderNodeTexCoord")
        vor = N.new("ShaderNodeTexVoronoi")
        vor.inputs["Scale"].default_value = 2.5 + seed
        nz = N.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 3
        L.new(tc.outputs["Generated"], nz.inputs["Vector"])
        L.new(nz.outputs["Color"], vor.inputs["Vector"])
        rp = N.new("ShaderNodeValToRGB")
        cr = rp.color_ramp
        cr.elements[0].color = (0.9, 0.85, 0.75, 1)
        cr.elements[1].color = (0.15, 0.25, 0.3, 1)
        e = cr.elements.new(0.45)
        e.color = (0.85, 0.45, 0.2, 1)
        L.new(vor.outputs["Distance"], rp.inputs["Fac"])
        L.new(rp.outputs["Color"], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = 0.7
        return m
    parts = [rbox("ArtFrame", c, (size[0], 0.03, size[1]), (0, 0, 0), frm, bevel=0.006),
             plane("ArtCanvas", c, (size[0] - 0.08, size[1] - 0.08), (0, -0.016, 0), mat_cached(("art", seed), make),
                   rot=(math.radians(90), 0, 0))]
    return parent(parts, root)


def window(c, loc, size=(1.4, 1.5), name="Window", sky=(0.75, 0.85, 1.0), sky_strength=3.0, curtains=True, rot=(0, 0, 0)):
    """Wall window facing -Y (rotate for side walls): frame, mullions, glass, bright sky card and curtains."""
    root = empty(name, c, loc, rot)
    wf = paint("WindowFrame", (0.92, 0.92, 0.9), rough=0.4)
    W, H = size
    parts = []
    for sx in (-1, 1):
        parts.append(rbox("WinJamb", c, (0.06, 0.12, H + 0.12), (sx * (W / 2 + 0.03), 0, 0), wf, bevel=0.004))
    for sz in (-1, 1):
        parts.append(rbox("WinHead", c, (W + 0.12, 0.12, 0.06), (0, 0, sz * (H / 2 + 0.03)), wf, bevel=0.004))
    parts.append(rbox("WinMullion", c, (0.04, 0.08, H), (0, 0, 0), wf, bevel=0.003))
    parts.append(rbox("WinTransom", c, (W, 0.08, 0.04), (0, 0, H * 0.15), wf, bevel=0.003))
    parts.append(rbox("WinSill", c, (W + 0.25, 0.2, 0.035), (0, -0.07, -H / 2 - 0.07), wf, bevel=0.006))
    parts.append(plane("WinGlass", c, (W, H), (0, 0.0, 0), glass("WinGlassMat", rough=0.02), rot=(math.radians(90), 0, 0)))
    parts.append(plane("WinSky", c, (W * 3, H * 2.5), (0, 1.5, 0.3), emissive("SkyCard", sky, sky_strength), rot=(math.radians(90), 0, 0)))
    if curtains:
        cm = fabric("Curtain", (0.82, 0.78, 0.68), rough=0.9, sheen=0.4, weave=600, bump=0.2)
        for sx in (-1, 1):
            parts.append(_curtain(f"Curtain{sx}", c, (sx * (W / 2 + 0.22), -0.12, 0.08), 0.45, H + 0.45, cm))
        parts.append(cyl("CurtainRod", c, 0.012, W + 0.9, (0, -0.12, H / 2 + 0.28), metal("RodMetal", (0.2, 0.2, 0.2), 0.3),
                         rot=(0, math.radians(90), 0)))
    return parent(parts, root)


def _curtain(name, c, loc, w, h, mat):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    nu, nv = 40, 24
    grid = []
    for i in range(nu + 1):
        u = i / nu
        row = []
        for j in range(nv + 1):
            v = j / nv
            x = (u - 0.5) * w
            y = 0.035 * math.sin(u * math.pi * 9) * (0.6 + 0.4 * v)
            z = (v - 0.5) * h
            row.append(bm.verts.new((x, y, z)))
        grid.append(row)
    for i in range(nu):
        for j in range(nv):
            bm.faces.new((grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]))
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    o.location = loc
    _finish(o, c, mat, subsurf=1)
    so = o.modifiers.new("Solid", "SOLIDIFY")
    so.thickness = 0.004
    return o


def room(c, origin=(0, 0, 0), size=(5.0, 5.0, 2.7), floor_mat=None, wall_color=(0.80, 0.74, 0.66), name="Room",
         open_side="-Y"):
    """Floor, ceiling, 3 walls (the camera side stays open), skirting boards, ceiling light."""
    ox, oy, oz = origin
    W, D, H = size
    root = empty(name, c, origin)
    fm = floor_mat or floorboards()
    wm = paint(name + "Wall", wall_color)
    sk = paint(name + "Skirting", (0.93, 0.93, 0.9), rough=0.35)
    parts = [plane("Floor", c, (W, D), (0, 0, 0), fm),
             plane("Ceiling", c, (W, D), (0, 0, H), paint(name + "Ceiling", (0.93, 0.93, 0.92)), rot=(math.pi, 0, 0)),
             rbox("WallBack", c, (W, 0.12, H), (0, D / 2 + 0.06, H / 2), wm, bevel=0),
             rbox("WallLeft", c, (0.12, D, H), (-W / 2 - 0.06, 0, H / 2), wm, bevel=0),
             rbox("WallRight", c, (0.12, D, H), (W / 2 + 0.06, 0, H / 2), wm, bevel=0),
             rbox("SkirtBack", c, (W, 0.02, 0.1), (0, D / 2 - 0.01, 0.05), sk, bevel=0.003),
             rbox("SkirtLeft", c, (0.02, D, 0.1), (-W / 2 + 0.01, 0, 0.05), sk, bevel=0.003),
             rbox("SkirtRight", c, (0.02, D, 0.1), (W / 2 - 0.01, 0, 0.05), sk, bevel=0.003),
             lathe("CeilingLight", c, [(0.0, 0.0), (0.25, 0.0), (0.22, -0.06), (0.0, -0.07)], (0, 0, H), emissive("CeilLight", (1.0, 0.92, 0.82), 6))]
    return parent(parts, root)


def floorboards(name="Floorboards"):
    def make():
        m, N, L, b = _new_mat(name)
        mp = _coord(N, (1, 1, 1), space="Object")
        brick = N.new("ShaderNodeTexBrick")
        brick.offset = 0.5
        brick.squash_frequency = 1
        brick.inputs["Scale"].default_value = 1.0
        brick.inputs["Mortar Size"].default_value = 0.004
        brick.inputs["Brick Width"].default_value = 1.2
        brick.inputs["Row Height"].default_value = 0.14
        brick.inputs["Color1"].default_value = (0.30, 0.16, 0.07, 1)
        brick.inputs["Color2"].default_value = (0.22, 0.11, 0.045, 1)
        brick.inputs["Mortar"].default_value = (0.08, 0.05, 0.03, 1)
        L.new(mp.outputs[0], brick.inputs["Vector"])
        wv = N.new("ShaderNodeTexWave")
        wv.inputs["Scale"].default_value = 30
        wv.inputs["Distortion"].default_value = 3
        wv.bands_direction = "Y"
        L.new(mp.outputs[0], wv.inputs["Vector"])
        mix = N.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.blend_type = "MULTIPLY"
        mix.inputs["Factor"].default_value = 0.22
        L.new(brick.outputs["Color"], mix.inputs["A"])
        L.new(wv.outputs["Color"], mix.inputs["B"])
        L.new(mix.outputs["Result"], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = 0.35
        b.inputs["Coat Weight"].default_value = 0.4
        b.inputs["Coat Roughness"].default_value = 0.15
        inv = N.new("ShaderNodeMath")
        inv.operation = "SUBTRACT"
        inv.inputs[0].default_value = 1.0
        L.new(brick.outputs["Fac"], inv.inputs[1])
        _bump(N, L, b, inv.outputs[0], 0.4, 0.002)
        return m
    return mat_cached(("floor", name), make)


def tissue_box(c, loc, name="TissueBox", rot=(0, 0, 0)):
    root = empty(name, c, loc, rot)
    parts = [rbox("TBox", c, (0.24, 0.12, 0.1), (0, 0, 0.05), plastic("TBoxCard", (0.35, 0.55, 0.7), 0.6), bevel=0.004),
             cushion("TBoxTissue", c, (0.08, 0.05, 0.09), (0, 0, 0.13), plastic("Tissue", (0.95, 0.95, 0.94), 0.8, sss=0.3), puff=0.6,
                     rot=(0, math.radians(12), 0))]
    return parent(parts, root)


def mug(c, loc, color=(0.85, 0.3, 0.2), name="Mug"):
    root = empty(name, c, loc)
    cm = ceramic(name + "Glaze", color)
    parts = [lathe("MugBody", c, [(0.0, 0.0), (0.04, 0.0), (0.042, 0.095), (0.038, 0.095), (0.036, 0.008), (0.0, 0.008)], (0, 0, 0), cm),
             tube("MugHandle", c, [Vector((0.04, 0, 0.075)), Vector((0.065, 0, 0.06)), Vector((0.065, 0, 0.03)), Vector((0.04, 0, 0.02))], 0.007, cm)]
    return parent(parts, root)


def measuring_jug(c, loc, name="Jug"):
    """Clear measuring jug with graduations; returns (root, liquid) — scale liquid.z 0..1 to fill."""
    root = empty(name, c, loc)
    prof = [(0.0, 0.0), (0.055, 0.0), (0.062, 0.17), (0.064, 0.175), (0.06, 0.175), (0.052, 0.006), (0.0, 0.006)]
    parts = [lathe("JugGlass", c, prof, (0, 0, 0), glass("JugGlass", rough=0.03))]
    tickm = plastic("JugTicks", (0.85, 0.15, 0.1), 0.4)
    for k in range(1, 6):
        z = 0.025 + k * 0.028
        parts.append(rbox(f"JugTick{k}", c, (0.018 if k % 2 else 0.03, 0.001, 0.002), (0, -0.0565 - 0.0002 * k, z), tickm, bevel=0))
    parts.append(tube("JugHandle", c, [Vector((0.06, 0, 0.15)), Vector((0.1, 0, 0.13)), Vector((0.1, 0, 0.05)), Vector((0.058, 0, 0.03))], 0.009,
                      glass("JugGlass")))
    liq = lathe("JugLiquid", c, [(0.0, 0.0), (0.05, 0.0), (0.0552, 1.0), (0.0, 1.0)], (0, 0, 0.007),
                plastic("ClearFluid", (0.8, 0.92, 1.0), 0.02), subsurf=0)
    lm = liq.data.materials[0]
    lm.node_tree.nodes["Principled BSDF"].inputs["Transmission Weight"].default_value = 0.95
    liq.scale = (1, 1, 0.001)
    parts.append(liq)
    return parent(parts, root), liq


# =============================================================== outdoors
def asphalt():
    def make():
        m, N, L, b = _new_mat("Asphalt")
        nz = N.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 60
        nz.inputs["Detail"].default_value = 10
        L.new(_coord(N).outputs[0], nz.inputs["Vector"])
        rp = _ramp(N, (0.035, 0.035, 0.037), (0.11, 0.11, 0.11))
        L.new(nz.outputs["Fac"], rp.inputs["Fac"])
        L.new(rp.outputs["Color"], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = 0.8
        _bump(N, L, b, nz.outputs["Fac"], 0.35, 0.004)
        return m
    return mat_cached(("asphalt",), make)


def grass():
    def make():
        m, N, L, b = _new_mat("Grass")
        nz = N.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 0.4
        nz.inputs["Detail"].default_value = 8
        L.new(_coord(N).outputs[0], nz.inputs["Vector"])
        rp = _ramp(N, (0.05, 0.12, 0.025), (0.18, 0.27, 0.07))
        L.new(nz.outputs["Fac"], rp.inputs["Fac"])
        L.new(rp.outputs["Color"], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = 0.9
        n2 = N.new("ShaderNodeTexNoise")
        n2.inputs["Scale"].default_value = 400
        L.new(_coord(N).outputs[0], n2.inputs["Vector"])
        _bump(N, L, b, n2.outputs["Fac"], 0.6, 0.01)
        return m
    return mat_cached(("grass",), make)


def tree(c, loc, h=7.0, name="Tree", seed=1, autumn=0.0):
    """Branching tree: tapered trunk + recursive branches (curves) + clustered leaf canopies."""
    rng = random.Random(seed)
    root = empty(name, c, loc)
    bark = mat_cached(("bark",), lambda: _bark())
    parts = []
    lm = leaf(f"TreeLeaf{int(autumn * 10)}", (0.05 + 0.25 * autumn, 0.13, 0.03), (0.15 + 0.5 * autumn, 0.28 - 0.05 * autumn, 0.06))

    def branch(p0, d, length, radius, depth):
        p1 = p0 + d * length * 0.5 + Vector((rng.uniform(-0.1, 0.1), rng.uniform(-0.1, 0.1), 0)) * length
        p2 = p0 + d * length
        o = tube("Branch", c, [p0, p1, p2], radius, bark, res=3)
        o.data.bevel_factor_mapping_end = "SPLINE"
        o.data.taper_radius_mode = "MULTIPLY"
        parts.append(o)
        if depth <= 1:
            for k in range(2 if depth == 1 else 3):
                cpos = p0.lerp(p2, rng.uniform(0.6, 1.0)) + Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.3, 0.6))) * length * 0.35
                canopy = sphere("Canopy", c, length * rng.uniform(0.45, 0.65), cpos, lm, scale=(1, 1, 0.75), subdiv=3)
                tex = bpy.data.textures.new("CanopyTex", "VORONOI")
                tex.noise_scale = 0.25
                dp = canopy.modifiers.new("Disp", "DISPLACE")
                dp.texture = tex
                dp.strength = length * 0.3
                parts.append(canopy)
        if depth == 0 or radius < 0.015:
            return
        for k in range(rng.choice((2, 3))):
            nd = (d + Vector((rng.uniform(-0.9, 0.9), rng.uniform(-0.9, 0.9), rng.uniform(0.1, 0.6)))).normalized()
            branch(p2, nd, length * rng.uniform(0.55, 0.75), radius * 0.6, depth - 1)

    branch(Vector((0, 0, 0)), Vector((0, 0, 1)), h * 0.4, h * 0.028, 4)
    return parent(parts, root)


def _bark():
    m, N, L, b = _new_mat("Bark")
    wv = N.new("ShaderNodeTexWave")
    wv.bands_direction = "Z"
    wv.inputs["Scale"].default_value = 6
    wv.inputs["Distortion"].default_value = 12
    wv.inputs["Detail"].default_value = 6
    L.new(_coord(N, (4, 4, 0.6)).outputs[0], wv.inputs["Vector"])
    rp = _ramp(N, (0.05, 0.035, 0.025), (0.22, 0.17, 0.12))
    L.new(wv.outputs["Fac"], rp.inputs["Fac"])
    L.new(rp.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.9
    _bump(N, L, b, wv.outputs["Fac"], 0.8, 0.01)
    return m


def street_lamp(c, loc, name="StreetLamp", rot=0.0):
    root = empty(name, c, loc, (0, 0, rot))
    pm = metal("LampPost", (0.05, 0.06, 0.06), 0.45)
    parts = [cyl("PostBase", c, 0.12, 0.4, (0, 0, 0.2), pm, verts=16, bevel=0.01),
             cyl("Post", c, 0.06, 6.0, (0, 0, 3.2), pm, verts=16),
             tube("PostArm", c, [Vector((0, 0, 6.0)), Vector((0, 0, 6.5)), Vector((0.6, 0, 6.6)), Vector((1.3, 0, 6.5))], 0.04, pm),
             rbox("LampHead", c, (0.55, 0.22, 0.1), (1.35, 0, 6.45), pm, bevel=0.03),
             rbox("LampLens", c, (0.48, 0.18, 0.02), (1.35, 0, 6.39), emissive("StreetLED", (1.0, 0.85, 0.65), 25), bevel=0.005)]
    return parent(parts, root)


def road(c, length=200.0, lanes=2, name="Road", y0=-100.0):
    lw = 3.5
    W = lanes * lw
    root = empty(name, c)
    line = plastic("RoadPaint", (0.9, 0.9, 0.85), 0.5)
    parts = [plane("RoadSurface", c, (W, length), (0, y0 + length / 2, 0), asphalt()),
             plane("Verge", c, (120, length + 40), (0, y0 + length / 2, -0.03), grass())]
    for sx in (-1, 1):
        parts.append(rbox("Kerb", c, (0.18, length, 0.15), (sx * (W / 2 + 0.09), y0 + length / 2, 0.075), paint("Kerb", (0.6, 0.6, 0.58), 0.8), bevel=0.01))
        parts.append(plane("Pavement", c, (2.2, length), (sx * (W / 2 + 1.28), y0 + length / 2, 0.15), paint("Pavement", (0.45, 0.45, 0.44), 0.85)))
        parts.append(plane("EdgeLine", c, (0.12, length), (sx * (W / 2 - 0.25), y0 + length / 2, 0.003), line))
    dash = plane("CentreDash", c, (0.12, 3.0), (0, y0 + 1.5, 0.003), line)
    ar = dash.modifiers.new("Array", "ARRAY")
    ar.count = int(length / 9)
    ar.use_relative_offset = False
    ar.use_constant_offset = True
    ar.constant_offset_displace = (0, 9.0, 0)
    parts.append(dash)
    return parent(parts, root)


# =============================================================== vehicle
def _sedan_profile(y):
    """Side/plan profile of a modern sedan at length position y (front = -2.25, rear = +2.25).
    Returns (z_bottom, z_belt, z_top, half_width_body, half_width_top, has_cabin)."""
    def lerp_pts(pts, y):
        """Monotone cubic (Fritsch-Carlson) interpolation: smooth, no ripples, no overshoot."""
        xs, vs = [p[0] for p in pts], [p[1] for p in pts]
        if y <= xs[0]:
            return vs[0]
        if y >= xs[-1]:
            return vs[-1]
        n = len(xs)
        d = [(vs[k + 1] - vs[k]) / (xs[k + 1] - xs[k]) for k in range(n - 1)]
        m = [d[0]] + [0.0 if d[k - 1] * d[k] <= 0 else (d[k - 1] + d[k]) / 2 for k in range(1, n - 1)] + [d[-1]]
        for k in range(n - 1):
            if d[k] == 0:
                m[k] = m[k + 1] = 0.0
        k = max(i for i in range(n - 1) if xs[i] <= y)
        h = xs[k + 1] - xs[k]
        t = (y - xs[k]) / h
        h00, h10, h01, h11 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t, -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
        return h00 * vs[k] + h10 * h * m[k] + h01 * vs[k + 1] + h11 * h * m[k + 1]
    zb = lerp_pts([(-2.25, 0.36), (-2.05, 0.24), (-1.6, 0.2), (1.6, 0.2), (2.05, 0.26), (2.25, 0.42)], y)
    belt = lerp_pts([(-2.25, 0.66), (-2.0, 0.78), (-1.3, 0.86), (-0.85, 0.92), (0.9, 0.97), (1.6, 1.0), (2.1, 1.0), (2.25, 0.9)], y)
    top = lerp_pts([(-2.25, 0.66), (-2.0, 0.79), (-1.3, 0.88), (-0.85, 0.95), (-0.15, 1.41), (0.95, 1.44), (1.6, 1.08),
                    (2.1, 1.02), (2.25, 0.9)], y)
    hw = lerp_pts([(-2.25, 0.62), (-2.0, 0.82), (-1.4, 0.9), (1.5, 0.91), (2.05, 0.86), (2.25, 0.7)], y)
    htop = lerp_pts([(-0.85, 0.82), (-0.15, 0.66), (0.95, 0.67), (1.6, 0.78)], y)
    cabin = -0.86 < y < 1.62
    arch = 0.0
    for wy in (-1.38, 1.42):
        dy = abs(y - wy)
        if dy < 0.44:
            arch = max(arch, 0.335 + math.sqrt(0.44 ** 2 - dy ** 2) * 0.93 - zb)
    return zb, belt, max(top, belt), hw, htop, cabin, arch


def car(c, loc=(0, 0, 0), color=(0.12, 0.003, 0.003), name="Car", rot=0.0, interior=True):
    """Modern sedan: one smooth lofted shell (paint, glass, lights, grille as material zones),
    boolean-cut wheel arches, five-spoke wheels, mirrors, handles. Faces -Y. Returns the root Empty."""
    root = empty(name, c, loc, (0, 0, rot))
    paint_m = car_paint(name + "Paint", color)
    glass_m = glass(name + "Tint", (0.12, 0.14, 0.16), rough=0.0, ior=1.5)
    trim = plastic(name + "Trim", (0.012, 0.012, 0.014), 0.45)
    head = emissive(name + "Headlight", (1.0, 0.97, 0.92), 2.5)
    tail = emissive(name + "Taillight", (0.9, 0.02, 0.01), 3.0)
    chrome = metal(name + "Chrome", (0.9, 0.9, 0.92), 0.08)
    mats = [paint_m, glass_m, trim, head, tail, chrome]
    NS, NV = 110, 14                        # sections along the car, vertices per half-section
    me = bpy.data.meshes.new(name + "ShellMesh")
    bm = bmesh.new()
    rings = []
    for i in range(NS + 1):
        y = -2.25 + 4.5 * i / NS
        zb, belt, top, hw, htop, cabin, arch = _sedan_profile(y)
        za = zb + arch                                   # side skirt height (raised over the wheels)
        half = [(0.0, zb), (hw * 0.62, zb), (hw * 0.86, za), (hw * 0.97, za + 0.05), (hw, max(za + 0.1, zb + 0.22)), (hw * 1.0, belt - 0.22),
                (hw * 0.985, belt - 0.06), (hw * 0.95, belt), (hw * 0.86, belt + 0.015)]
        if cabin and top > belt + 0.05:
            g = [(htop * 1.04, belt + 0.03), (htop * 1.0, belt + (top - belt) * 0.45), (htop * 0.9, top - 0.05),
                 (htop * 0.6, top - 0.005), (0.0, top)]
        else:
            g = [(hw * 0.8, top + 0.004), (hw * 0.6, top + 0.012), (hw * 0.35, top + 0.018), (hw * 0.15, top + 0.02), (0.0, top + 0.02)]
        half = half + g
        sec = half[:-1] + [half[-1]] + [(-x, z) for x, z in reversed(half[1:-1])]
        rings.append([bm.verts.new((x, y, z)) for x, z in sec])
    n = len(rings[0])
    for i in range(NS):
        a, b = rings[i], rings[i + 1]
        for j in range(n):
            bm.faces.new((a[j], b[j], b[(j + 1) % n], a[(j + 1) % n]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    # material zones by face centre
    for f in bm.faces:
        cx, cy, cz = f.calc_center_median()
        zb, belt, top, hw, htop, cabin, arch = _sedan_profile(cy)
        ax = abs(cx)
        idx = 0
        if cabin and cz > belt + 0.035 and cz < top - 0.025 and top > belt + 0.1:
            pillar = abs(cy - 0.42) < 0.05 or cy < -0.8 or (cy > 1.5)
            if not (pillar and ax > htop * 0.7):
                idx = 1
        if cabin and cz >= top - 0.025 and (cy < -0.2 or cy > 1.0) and top > belt + 0.1:
            idx = 1                                           # windscreen / rear screen
        if cy < -2.08 and cz < 0.55 and ax < 0.5:
            idx = 2                                           # grille / lower intake
        if cz < zb + 0.07 or (arch > 0.02 and ax > hw * 0.8 and cz < zb + arch + 0.03):
            idx = 2                                           # sill / underside / arch lip
        if idx == 0 and ax > hw * 0.9 and cz < belt - 0.05 and (abs(cy + 0.18) < 0.012 or abs(cy - 1.0) < 0.012):
            idx = 2                                           # door shut lines
        f.material_index = idx
    bm.to_mesh(me)
    bm.free()
    shell = bpy.data.objects.new(name + "Body", me)
    for m in mats:
        me.materials.append(m)
    _link(shell, c)
    for p in me.polygons:
        p.use_smooth = True
    ss = shell.modifiers.new("Subsurf", "SUBSURF")
    ss.levels = ss.render_levels = 2
    parts = [shell]
    WHEELS = {"FL": (-0.8, -1.38), "FR": (0.8, -1.38), "RL": (-0.8, 1.42), "RR": (0.8, 1.42)}
    for key, (x, y) in WHEELS.items():           # dark wheel-well liners
        parts.append(cyl("ArchLiner", c, 0.4, 0.32, (x * 0.93, y, 0.36), plastic("Liner", (0.008, 0.008, 0.009), 0.9),
                         rot=(0, math.radians(90), 0), verts=48))
    tire_m, rim_m = rubber(), metal(name + "Rim", (0.62, 0.64, 0.68), 0.22)
    for key, (x, y) in WHEELS.items():
        sx = 1 if x > 0 else -1
        w = empty(name + "Wheel" + key, c, (x, y, 0.335))
        tire = lathe("Tire", c, [(0.215, -0.105), (0.29, -0.112), (0.328, -0.09), (0.336, -0.03), (0.336, 0.03), (0.328, 0.09),
                                 (0.29, 0.112), (0.215, 0.105)], (0, 0, 0), tire_m, steps=56, rot=(0, math.radians(90), 0))
        rim = lathe("Rim", c, [(0.0, 0.04 * sx), (0.07, 0.05 * sx), (0.205, 0.035 * sx), (0.22, 0.0), (0.205, -0.07 * sx), (0.0, -0.07 * sx)],
                    (0, 0, 0), rim_m, steps=48, rot=(0, math.radians(90), 0))
        hub = cyl("Hub", c, 0.055, 0.02, (sx * 0.06, 0, 0), chrome, rot=(0, math.radians(90), 0), verts=24)
        spokes = [rbox("Spoke", c, (0.025, 0.045, 0.32), (sx * 0.045, math.sin(a) * 0.12, math.cos(a) * 0.12), rim_m, bevel=0.012,
                       rot=(-a, 0, 0)) for a in (2 * math.pi * k / 5 for k in range(5))]
        disc = cyl("BrakeDisc", c, 0.17, 0.02, (-sx * 0.02, 0, 0), metal("Disc", (0.35, 0.35, 0.36), 0.4, brushed=True), rot=(0, math.radians(90), 0))
        parent([tire, rim, hub, disc] + spokes, w)
        w.parent = root
    for sx in (-1, 1):
        _, belt, _, hw, _, _, _ = _sedan_profile(-0.75)
        parts.append(cushion("Mirror", c, (0.2, 0.09, 0.11), (sx * (hw + 0.1), -0.72, belt + 0.06), paint_m, puff=0.3))
        parts.append(rbox("MirrorArm", c, (0.1, 0.04, 0.03), (sx * (hw + 0.02), -0.7, belt + 0.03), trim, bevel=0.01))
        for y in (-0.05, 1.1):
            _, belt, _, hw, _, _, _ = _sedan_profile(y)
            parts.append(rbox("DoorHandle", c, (0.02, 0.17, 0.028), (sx * (hw + 0.005), y, belt - 0.1), chrome, bevel=0.009))
    for sx in (-1, 1):                          # sculpted lamp units sitting on the shell
        zb, belt, top, hw, _, _, _ = _sedan_profile(-2.08)
        hl = cushion("Headlight", c, (0.44, 0.14, 0.09), (sx * 0.58, -2.1, belt - 0.07), glass(name + "LensGlass", (0.95, 0.97, 1.0)), puff=0.2,
                     rot=(math.radians(-12), 0, math.radians(sx * -14)))
        parts.append(hl)
        parts.append(cushion("HeadlightLED", c, (0.36, 0.06, 0.045), (sx * 0.58, -2.085, belt - 0.075), head, puff=0.2,
                             rot=(math.radians(-12), 0, math.radians(sx * -14))))
        zb, belt, top, hw, _, _, _ = _sedan_profile(2.17)
        parts.append(cushion("Taillight", c, (0.42, 0.08, 0.075), (sx * 0.56, 2.2, belt - 0.07), tail, puff=0.2,
                             rot=(0, 0, math.radians(sx * 10))))
    _, _, _, hwf, _, _, _ = _sedan_profile(-2.2)
    parts.append(rbox("PlateF", c, (0.52, 0.012, 0.12), (0, -2.255, 0.42), plastic("Plate", (0.95, 0.95, 0.92), 0.4), bevel=0.006))
    parts.append(rbox("PlateR", c, (0.52, 0.012, 0.12), (0, 2.262, 0.62), plastic("Plate", (0.95, 0.95, 0.92), 0.4), bevel=0.006))
    if interior:
        parts += _car_interior(c, name, trim)
    parent(parts, root)
    return root


def _car_interior(c, name, trim):
    seat = fabric(name + "SeatFabric", (0.05, 0.05, 0.06), weave=500)
    dash_m = plastic(name + "Dash", (0.03, 0.03, 0.033), 0.6)
    p = []
    for sx in (-0.42, 0.42):
        p.append(cushion("SeatBase", c, (0.5, 0.52, 0.14), (sx, 0.2, 0.52), seat, puff=0.4))
        p.append(cushion("SeatBack", c, (0.5, 0.14, 0.62), (sx, 0.52, 0.9), seat, puff=0.5, rot=(math.radians(-14), 0, 0)))
        p.append(cushion("Headrest", c, (0.26, 0.1, 0.18), (sx, 0.6, 1.3), seat, puff=0.5))
    p.append(cushion("RearBench", c, (1.4, 0.5, 0.16), (0, 1.25, 0.5), seat, puff=0.3))
    p.append(cushion("RearBack", c, (1.4, 0.14, 0.55), (0, 1.55, 0.85), seat, puff=0.4, rot=(math.radians(-12), 0, 0)))
    p.append(rbox("Dashboard", c, (1.62, 0.5, 0.26), (0, -0.62, 0.82), dash_m, bevel=0.06, subsurf=1))
    p.append(rbox("Console", c, (0.22, 0.7, 0.22), (0, -0.2, 0.5), dash_m, bevel=0.03))
    p.append(rbox("Screen", c, (0.26, 0.02, 0.16), (0, -0.46, 0.97), emissive(name + "Infotainment", (0.2, 0.45, 0.8), 1.5), bevel=0.01,
                  rot=(math.radians(-15), 0, 0)))
    p.append(rbox("Gauges", c, (0.36, 0.06, 0.12), (-0.42, -0.5, 0.97), emissive(name + "Cluster", (0.9, 0.55, 0.2), 0.8), bevel=0.02))
    # steering wheel
    sw = empty(name + "SteeringWheel", c, (-0.42, -0.36, 0.93), (math.radians(64), 0, 0))
    rim = lathe("SWRim", c, [(0.17, -0.016), (0.185, 0.0), (0.17, 0.016), (0.155, 0.0)], (0, 0, 0), plastic("SWLeather", (0.02, 0.02, 0.02), 0.45),
                steps=48, subsurf=1)
    hub = cyl("SWHub", c, 0.055, 0.05, (0, 0, -0.01), dash_m, verts=24, bevel=0.01)
    spk = [rbox("SWSpoke", c, (0.16, 0.035, 0.02), (math.cos(a) * 0.08, math.sin(a) * 0.08, 0), dash_m, bevel=0.008, rot=(0, 0, a))
           for a in (0, math.pi, -math.pi / 2)]
    parent([rim, hub] + spk, sw)
    p.append(sw)
    p.append(cyl("Column", c, 0.035, 0.3, (-0.42, -0.5, 0.86), dash_m, rot=(math.radians(64), 0, 0)))
    p.append(rbox("RearMirror", c, (0.24, 0.04, 0.07), (0, -0.08, 1.3), trim, bevel=0.015))
    return p


# =============================================================== clinic / lab / OR
def desk(c, loc, name="Desk", rot=0.0):
    root = empty(name, c, loc, (0, 0, rot))
    top = wood("DeskWood", (0.85, 0.75, 0.6), (0.7, 0.58, 0.42), rough=0.4)
    leg = metal("DeskLeg", (0.85, 0.85, 0.87), 0.3)
    parts = [rbox("DeskTop", c, (1.5, 0.75, 0.035), (0, 0, 0.74), top, bevel=0.006)]
    for sx in (-1, 1):
        parts.append(rbox("DeskLeg", c, (0.05, 0.65, 0.72), (sx * 0.7, 0, 0.36), leg, bevel=0.01))
    parts.append(rbox("Monitor", c, (0.6, 0.03, 0.36), (0.3, 0.2, 1.05), plastic("MonBlack", (0.02, 0.02, 0.02), 0.3), bevel=0.008))
    parts.append(plane("MonitorScreen", c, (0.57, 0.33), (0.3, 0.184, 1.05), emissive("MonScreen", (0.75, 0.85, 0.95), 1.2), rot=(math.radians(90), 0, 0)))
    parts.append(rbox("MonStand", c, (0.05, 0.05, 0.18), (0.3, 0.22, 0.84), plastic("MonBlack", (0.02, 0.02, 0.02), 0.3), bevel=0.005))
    parts.append(rbox("Keyboard", c, (0.42, 0.14, 0.015), (0.25, -0.1, 0.765), plastic("KB", (0.9, 0.9, 0.9), 0.4), bevel=0.004))
    return parent(parts, root)


def lab_bench(c, loc, name="LabBench"):
    root = empty(name, c, loc)
    epoxy = plastic("Epoxy", (0.08, 0.09, 0.1), 0.25, coat=0.4)
    cab = paint("LabCabinet", (0.85, 0.88, 0.9), rough=0.35)
    parts = [rbox("BenchTop", c, (2.4, 0.75, 0.04), (0, 0, 0.92), epoxy, bevel=0.006),
             rbox("BenchCab", c, (2.4, 0.7, 0.86), (0, 0.02, 0.45), cab, bevel=0.004),
             rbox("BenchShelf", c, (2.4, 0.3, 0.025), (0, 0.25, 1.45), cab, bevel=0.003)]
    for i in range(4):
        parts.append(rbox("CabHandle", c, (0.12, 0.02, 0.012), (-0.9 + 0.6 * i, -0.34, 0.8), metal("Steel", (0.8, 0.8, 0.82), 0.25), bevel=0.004))
    # microscope
    ms = empty("Microscope", c, (0.7, 0.05, 0.94))
    mw = plastic("MicroWhite", (0.92, 0.92, 0.9), 0.3)
    mb = metal("MicroBlack", (0.03, 0.03, 0.03), 0.3)
    mparts = [rbox("MBase", c, (0.2, 0.26, 0.04), (0, 0, 0.02), mw, bevel=0.015),
              tube("MArm", c, [Vector((0, 0.1, 0.03)), Vector((0, 0.12, 0.2)), Vector((0, 0.05, 0.34))], 0.025, mw),
              cyl("MTube", c, 0.022, 0.18, (0, 0.02, 0.36), mb, rot=(math.radians(25), 0, 0)),
              cyl("MStage", c, 0.08, 0.012, (0, -0.02, 0.15), mb),
              cyl("MObjective", c, 0.012, 0.06, (0, -0.02, 0.21), metal("MChrome", (0.9, 0.9, 0.9), 0.1))]
    parent(mparts, ms)
    ms.parent = root
    # rack of tubes
    for i in range(6):
        parts.append(cyl("RackTube", c, 0.008, 0.1, (-0.6 + i * 0.03, -0.1, 0.99), glass("TubeGlass")))
    parts.append(rbox("Rack", c, (0.22, 0.05, 0.03), (-0.525, -0.1, 0.96), plastic("RackBlue", (0.1, 0.35, 0.8), 0.4), bevel=0.004))
    return parent(parts, root)


def or_table(c, loc, name="ORTable"):
    root = empty(name, c, loc)
    st = metal("ORSteel", (0.75, 0.77, 0.8), 0.3, brushed=True)
    pad = plastic("ORPad", (0.12, 0.3, 0.38), 0.6)
    parts = [rbox("ORTop", c, (0.6, 2.0, 0.09), (0, 0, 0.9), pad, bevel=0.03, subsurf=1),
             rbox("ORFrame", c, (0.55, 1.9, 0.04), (0, 0, 0.84), st, bevel=0.01),
             cyl("ORColumn", c, 0.12, 0.7, (0, 0.2, 0.45), st, verts=24),
             rbox("ORBase", c, (0.55, 0.9, 0.08), (0, 0.2, 0.05), st, bevel=0.02)]
    return parent(parts, root)


def surgical_lamp(c, loc, name="SurgLamp"):
    root = empty(name, c, loc)
    wm = plastic("SLWhite", (0.92, 0.93, 0.95), 0.3)
    parts = [lathe("SLDome", c, [(0.0, 0.0), (0.33, -0.02), (0.36, -0.1), (0.34, -0.12), (0.0, -0.08)], (0, 0, 0), wm),
             tube("SLArm", c, [Vector((0, 0, 0)), Vector((0, 0, 0.5)), Vector((0.4, 0, 0.9)), Vector((1.0, 0, 1.0))], 0.03, wm)]
    for k in range(7):
        a = 2 * math.pi * k / 7
        r = 0.0 if k == 0 else 0.18
        parts.append(cyl("SLLed", c, 0.06, 0.01, (r * math.cos(a), r * math.sin(a), -0.115), emissive("SLLight", (1.0, 0.98, 0.95), 30)))
    sl = bpy.data.lights.new(name + "Spot", "SPOT")
    sl.energy = 900
    sl.spot_size = math.radians(45)
    sl.spot_blend = 0.6
    sl.shadow_soft_size = 0.3
    so = bpy.data.objects.new(name + "Spot", sl)
    c.objects.link(so)
    so.location = (0, 0, -0.15)
    parts.append(so)
    return parent(parts, root)


def vital_monitor(c, loc, name="VitalMonitor", rot=0.0):
    root = empty(name, c, loc, (0, 0, rot))
    parts = [rbox("VMBody", c, (0.42, 0.12, 0.32), (0, 0, 0), plastic("VMShell", (0.85, 0.86, 0.88), 0.35), bevel=0.015),
             plane("VMScreen", c, (0.36, 0.25), (0, -0.0605, 0.01), _vitals_mat(), rot=(math.radians(90), 0, 0)),
             cyl("VMPole", c, 0.02, 1.4, (0, 0.05, -0.85), metal("VMPoleM", (0.8, 0.8, 0.82), 0.3), verts=12)]
    return parent(parts, root)


def _vitals_mat():
    def make():
        m, N, L, b = _new_mat("Vitals")
        tc = N.new("ShaderNodeTexCoord")
        wv = N.new("ShaderNodeTexWave")
        wv.name = "Trace"
        wv.bands_direction = "X"
        wv.inputs["Scale"].default_value = 6
        wv.inputs["Distortion"].default_value = 3
        L.new(tc.outputs["Generated"], wv.inputs["Vector"])
        rp = N.new("ShaderNodeValToRGB")
        rp.color_ramp.elements[0].position = 0.92
        rp.color_ramp.elements[0].color = (0, 0.02, 0.01, 1)
        rp.color_ramp.elements[1].color = (0.2, 1.0, 0.4, 1)
        L.new(wv.outputs["Fac"], rp.inputs["Fac"])
        L.new(rp.outputs["Color"], b.inputs["Emission Color"])
        b.inputs["Base Color"].default_value = (0, 0, 0, 1)
        b.inputs["Emission Strength"].default_value = 3
        return m
    return mat_cached(("vitals",), make)


# =============================================================== anatomy
def brain(c, center, size=(0.066, 0.085, 0.056), name="Brain", mat=None, subdiv=6):
    """Cerebrum (two folded hemispheres), cerebellum and brain stem. Folds are real geometry: vertices are pushed
    in along their normal where a warped noise field crosses zero, which draws gyri/sulci lines."""
    from mathutils import noise
    rx, ry, rz = size
    m = mat or brain_mat()
    parts = []

    def folded(nm, ctr, rad, freq, depth, seed, flat_side=0):
        me = bpy.data.meshes.new(nm)
        bm = bmesh.new()
        bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=1.0)
        off = Vector((seed * 13.1, seed * 7.7, seed * 3.3))
        for v in bm.verts:
            p = v.co.copy()
            if flat_side and p.x * flat_side < 0:          # flatten the medial face of a hemisphere
                p.x *= 0.3
            if p.z < 0:                                    # flatter underside
                p.z *= 0.72
            p.x *= 1.0 - 0.18 * max(0.0, -p.y)             # narrower frontal lobe
            if p.z < -0.1 and -0.3 < p.y < 0.5:            # temporal lobe bulge
                p.x *= 1.06
            warp = noise.noise_vector(p * 1.1 + off) * 0.6
            val = noise.noise(p * freq + warp + off)
            groove = 1.0 - min(1.0, abs(val) / 0.13)          # sulci along the zero-crossing lines
            groove = groove * groove * (3 - 2 * groove)
            fine = noise.noise(p * freq * 2.3 + off) * 0.08
            n = p.normalized()
            p = p - n * (depth * groove) + n * depth * fine
            v.co = Vector((p.x * rad[0], p.y * rad[1], p.z * rad[2]))
        bm.to_mesh(me)
        bm.free()
        o = bpy.data.objects.new(nm, me)
        o.location = ctr
        _finish(o, c, m, subsurf=1)
        return o
    gap = rx * 0.04
    for sx in (-1, 1):
        parts.append(folded(f"{name}Hemi{sx}", center + Vector((sx * (rx * 0.5 + gap / 2), 0, 0)), (rx * 0.5, ry, rz),
                            freq=5.8, depth=0.11, seed=sx + 2, flat_side=sx))
    parts.append(folded(f"{name}Cerebellum", center + Vector((0, ry * 0.62, -rz * 0.72)), (rx * 0.62, ry * 0.32, rz * 0.36),
                        freq=9.0, depth=0.05, seed=5))
    stem = tube(f"{name}Stem", c, [center + Vector((0, ry * 0.25, -rz * 0.5)), center + Vector((0, ry * 0.32, -rz * 1.0)),
                                   center + Vector((0, ry * 0.36, -rz * 1.7))], rx * 0.16, m, res=6)
    parts.append(stem)
    return parts


def brain_mat():
    def make():
        m, N, L, b = _new_mat("BrainTissue")
        nz = N.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 80
        L.new(_coord(N).outputs[0], nz.inputs["Vector"])
        rp = _ramp(N, (0.55, 0.25, 0.27), (0.78, 0.45, 0.46))
        L.new(nz.outputs["Fac"], rp.inputs["Fac"])
        L.new(rp.outputs["Color"], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = 0.35
        b.inputs["Subsurface Weight"].default_value = 0.5
        b.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.25)
        b.inputs["Subsurface Scale"].default_value = 0.004
        b.inputs["Coat Weight"].default_value = 0.6
        b.inputs["Coat Roughness"].default_value = 0.15
        return m
    return mat_cached(("brain",), make)
