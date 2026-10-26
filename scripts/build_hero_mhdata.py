"""Build the hero (same spec as build_character.py) from MakeHuman data, without MPFB.

Run: blender -b --python build_hero_mhdata.py -- <makehuman-data/package dir> <out.blend>
     (or with the `bpy` pip module: python build_hero_mhdata.py -- <dir> <out.blend>)

Source data: the `makehuman-data` npm package (MakeHuman base mesh, targets, proxies and skins,
exported to three.js JSON). Everything MPFB does for our hero is reproduced here:
  - macro + face targets applied to the base mesh (targets.bin, dense int16, 1e-3 units)
  - proxies (eyes, eyebrows, eyelashes, teeth, tongue, hair, clothes, shoes) fitted to the
    morphed base through their ref-vertex weights + offsets, body skin hidden under clothes
  - the MakeHuman default skeleton (163 bones incl. jaw/eye/face bones) built from the joint
    vertex groups of the morphed mesh, with the base and proxy skin weights
  - facial expression units (caucasian) as shape keys on the body and on every face proxy,
    so brows/lashes follow the face
MakeHuman space is Y-up, decimetres, facing +Z; Blender space here is Z-up, metres, facing -Y.
"""
import json
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
PKG, OUT = argv[0], argv[1]
DATA = os.path.join(PKG, "public", "data")

HERO = {
    # macro sliders, same values as build_character.py
    "gender": 1.0, "age": 0.5, "muscle": 0.62, "weight": 0.52, "height": 0.55, "proportions": 0.6,
    "skin": "skins/young_caucasian_male/textures/young_lightskinned_male_diffuse.png",
    "eye_texture": "brownlight_eye.png",
    "proxies": ["eyes/HighPolyEyes", "eyebrows/eyebrow001", "eyelashes/Eyelashes01", "teeth/Teeth_Base",
                "tongue/tongue01", "hair/short02", "clothes/male_casualsuit05", "clothes/shoes02"],
    # stylized-realism face, same intent as build_character.py (target names differ in this data)
    "targets": {
        "eyes/l-eye-size-big": 0.35, "eyes/r-eye-size-big": 0.35,
        "nose/nose-scale-vert-incr": 0.25, "nose/nose-scale-horiz-incr": 0.2,
        "nose/nose-point-width-more": 0.3,
        "chin/chin-prominent-more": 0.35, "chin/chin-width-max": 0.25,
        "cheek/l-cheek-bones-out": 0.3, "cheek/r-cheek-bones-out": 0.3,
        "mouth/mouth-lowerlip-volume-inflate": 0.25,
        "eyebrows/eyebrows-trans-vert-less": 0.2, "head/head-square": 0.3,
    },
}

bpy.ops.wm.read_factory_settings(use_empty=True)


# ---------------------------------------------------------------- three.js JSON helpers
def load_threejs(path):
    d = json.load(open(path))
    verts = np.array(d["vertices"], np.float64).reshape(-1, 3)
    uvs = np.array(d["uvs"][0], np.float64).reshape(-1, 2) if d["uvs"] and d["uvs"][0] else None
    f, i = d["faces"], 0
    faces, fuvs, fmat = [], [], []
    while i < len(f):
        t = f[i]; i += 1
        n = 4 if t & 1 else 3
        faces.append(tuple(f[i:i + n])); i += n
        mat = 0
        if t & 2:
            mat = f[i]; i += 1
        if t & 4:
            i += 1
        if t & 8:
            fuvs.append(tuple(f[i:i + n])); i += n
        else:
            fuvs.append(None)
        if t & 16:
            i += 1
        if t & 32:
            i += n
        if t & 64:
            i += 1
        if t & 128:
            i += n
        fmat.append(mat)
    return d, verts, faces, fuvs, fmat, uvs


def to_blender(v):
    """MakeHuman (x, y-up, z-forward, dm) -> Blender (x, z-up, -y forward, m)."""
    return np.stack([v[:, 0], -v[:, 2], v[:, 1]], 1) * 0.1


def make_mesh(name, verts_b, faces, fuvs, uvs, keep_faces=None):
    if keep_faces is not None:
        faces = [f for f, k in zip(faces, keep_faces) if k]
        fuvs = [u for u, k in zip(fuvs, keep_faces) if k]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts_b.tolist(), [], faces)
    me.update()
    if uvs is not None and fuvs and fuvs[0] is not None:
        layer = me.uv_layers.new(name="UVMap")
        flat = [uvs[k] for fu in fuvs for k in fu]
        layer.data.foreach_set("uv", np.array(flat, np.float32).ravel())
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


# ---------------------------------------------------------------- base mesh + targets
base_d, base_v, base_f, base_fuv, base_fmat, base_uv = load_threejs(os.path.join(DATA, "models", "human_full_size.json"))
NV = len(base_v)
tlist = sorted(json.load(open(os.path.join(PKG, "src", "json", "targets", "target-list.json")))["targets"])
TMAT = np.memmap(os.path.join(DATA, "targets", "targets.bin"), dtype=np.int16, mode="r", shape=(len(tlist), NV * 3))
TIDX = {t.replace("data/targets/", "").replace(".target", ""): i for i, t in enumerate(tlist)}


def target(name):
    return TMAT[TIDX[name]].astype(np.float64).reshape(-1, 3) * 1e-3


def cats(v, names, points):
    """Linear weights of value v over category anchor points, MakeHuman macro style."""
    w = {n: 0.0 for n in names}
    for k in range(len(points) - 1):
        a, b = points[k], points[k + 1]
        if a <= v <= b:
            t = (v - a) / (b - a)
            w[names[k]] += 1 - t
            w[names[k + 1]] += t
            break
    return w


H = HERO
gw = {"male": H["gender"], "female": 1 - H["gender"]}
aw = cats(H["age"], ["baby", "child", "young", "old"], [0.0, 0.1875, 0.5, 1.0])
mw = cats(H["muscle"], ["minmuscle", "averagemuscle", "maxmuscle"], [0.0, 0.5, 1.0])
ww = cats(H["weight"], ["minweight", "averageweight", "maxweight"], [0.0, 0.5, 1.0])
hw = {"minheight": max(0.0, 0.5 - H["height"]) * 2, "maxheight": max(0.0, H["height"] - 0.5) * 2}
pw = {"uncommonproportions": max(0.0, 0.5 - H["proportions"]) * 2, "idealproportions": max(0.0, H["proportions"] - 0.5) * 2}

coords = base_v.copy()
applied = []
for g, gv in gw.items():
    for a, av in aw.items():
        if gv * av == 0:
            continue
        for race in ("african", "asian", "caucasian"):  # MakeHuman/MPFB default: equal ethnic mix
            key = f"macrodetails/{race}-{g}-{a}"
            if key in TIDX:
                coords += target(key) * gv * av / 3
        for m, mv in mw.items():
            for w, wv in ww.items():
                base_w = gv * av * mv * wv
                if base_w == 0:
                    continue
                key = f"macrodetails/universal-{g}-{a}-{m}-{w}"
                if key in TIDX:
                    coords += target(key) * base_w
                    applied.append((key, round(base_w, 3)))
                for h, hv in hw.items():
                    k2 = f"macrodetails/height/{g}-{a}-{m}-{w}-{h}"
                    if hv and k2 in TIDX:
                        coords += target(k2) * base_w * hv
                for p, pv in pw.items():
                    k2 = f"macrodetails/proportions/{g}-{a}-{m}-{w}-{p}"
                    if pv and k2 in TIDX:
                        coords += target(k2) * base_w * pv
for name, val in H["targets"].items():
    coords += target(name) * val
print("MACRO", applied)

EXPR = {t.split("/")[-1]: target(t) for t in TIDX if t.startswith("expression/units/caucasian/")}
print("EXPRESSIONS", sorted(EXPR))

# ---------------------------------------------------------------- body
mat_names = [m.get("DbgName", "") for m in base_d["materials"]]
body_mat = mat_names.index("body")
keep = np.array([m == body_mat for m in base_fmat])
body_vert_used = np.zeros(NV, bool)
for f, k in zip(base_f, keep):
    if k:
        body_vert_used[list(f)] = True
B = to_blender(coords)
GROUND = B[body_vert_used, 2].min()
OFFS = np.array([0, 0, -GROUND])


def place(v_mh):
    return to_blender(v_mh) + OFFS


# skin under clothes: union of the clothes' deleteVerts
proxy_data = []
hidden = np.zeros(NV, bool)
for rel in H["proxies"]:
    folder = os.path.join(DATA, "proxies", rel)
    fn = next(f for f in os.listdir(folder) if f.endswith(".json"))
    pd = load_threejs(os.path.join(folder, fn))
    proxy_data.append((rel, folder, pd))
    dv = pd[0]["metadata"].get("deleteVerts")
    if dv and rel.startswith("clothes/"):
        hidden |= np.array(dv, bool)
keep_body = keep & np.array([not hidden[list(f)].all() for f in base_f])
body = make_mesh("Hero.body", place(coords), base_f, base_fuv, base_uv, keep_body)


def fit_proxy(pd, base_coords):
    d = pd[0]
    ref = np.array(d["ref_vIdxs"]); w = np.array(d["weights"]); off = np.array(d["offsets"])
    return (base_coords[ref] * w[:, :, None]).sum(1) + off


proxies = {}
for rel, folder, pd in proxy_data:
    d, pv, pf, pfuv, pfmat, puv = pd
    name = "Hero." + os.path.basename(rel)
    ob = make_mesh(name, place(fit_proxy(pd, coords)), pf, pfuv, puv)
    proxies[rel] = (ob, pd, folder)

# ---------------------------------------------------------------- shape keys (body + face proxies)
FACE_PROXIES = [r for r in proxies if r.split("/")[0] in ("eyebrows", "eyelashes", "teeth", "tongue")]


def add_keys(ob, compute):
    ob.shape_key_add(name="Basis", from_mix=False)
    for nm, delta in EXPR.items():
        new = compute(coords + delta)
        if new is None:
            continue
        k = ob.shape_key_add(name=nm, from_mix=False)
        k.value = 0.0  # Blender 5 creates new keys at 1.0
        k.data.foreach_set("co", new.astype(np.float32).ravel())


add_keys(body, lambda c: place(c))
for rel in FACE_PROXIES:
    ob, pd, _ = proxies[rel]
    add_keys(ob, lambda c, pd=pd: place(fit_proxy(pd, c)))

# ---------------------------------------------------------------- skeleton
jp = base_d["metadata"]["joint_pos_idxs"]
bones = base_d["bones"]
bnames = [b["name"] for b in bones]
real = [n[:-len("____head")] for n in bnames if n.endswith("____head")]


def parent_of(n):
    p = bones[bnames.index(n + "____head")]["parent"]
    if p < 0:
        return None
    pn = bnames[p]
    return pn[:-len("____head")] if pn.endswith("____head") else pn


arm_data = bpy.data.armatures.new("HeroRig")
rig = bpy.data.objects.new("HeroRig", arm_data)
bpy.context.scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
eb = arm_data.edit_bones
P = place(coords)
for n in real:
    b = eb.new(n)
    b.head = Vector(P[jp[n + "____head"]].mean(0))
    b.tail = Vector(P[jp[n + "____tail"]].mean(0))
    if (b.tail - b.head).length < 1e-4:
        b.tail = b.head + Vector((0, 0, 0.01))
    d = (b.tail - b.head).normalized()
    b.align_roll(Vector((0, 0, 1)) if abs(d.y) > 0.85 else Vector((0, -1, 0)))
for n in real:
    p = parent_of(n)
    if p:
        eb[n].parent = eb[p]
bpy.ops.object.mode_set(mode="OBJECT")
for pb in rig.pose.bones:
    pb.rotation_mode = "QUATERNION"


def skin(ob, d, nv):
    si = np.array(d["skinIndices"]).reshape(nv, -1); sw = np.array(d["skinWeights"]).reshape(nv, -1)
    groups = {}
    for vi in range(nv):
        for j in range(si.shape[1]):
            if sw[vi, j] > 0:
                n = bnames[si[vi, j]]
                n = n[:-len("____head")] if n.endswith("____head") else n
                groups.setdefault(n, []).append((vi, float(sw[vi, j])))
    for n, lst in groups.items():
        vg = ob.vertex_groups.new(name=n)
        for vi, w in lst:
            vg.add([vi], w, "REPLACE")
    ob.parent = rig
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = rig


skin(body, base_d, NV)
for rel, (ob, pd, _) in proxies.items():
    skin(ob, pd[0], len(pd[1]))

# drop helper/hidden verts from the body now that indices no longer matter
bpy.context.view_layer.objects.active = body
body.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="DESELECT")
bpy.ops.mesh.select_loose()
bpy.ops.mesh.delete(type="VERT")
bpy.ops.object.mode_set(mode="OBJECT")


# ---------------------------------------------------------------- materials
def img(path, non_color=False):
    im = bpy.data.images.load(path, check_existing=True)
    if non_color:
        im.colorspace_settings.name = "Non-Color"
    return im


def principled(name, tex=None, alpha=False, rough=0.5, normal=None, sss=0.0, coat=0.0, spec=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Specular IOR Level"].default_value = spec
    if tex:
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = img(tex)
        nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
        if alpha:
            nt.links.new(t.outputs["Alpha"], bsdf.inputs["Alpha"])
            if hasattr(m, "surface_render_method"):
                m.surface_render_method = "DITHERED"
    if normal:
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = img(normal, True)
        nm = nt.nodes.new("ShaderNodeNormalMap"); nm.inputs["Strength"].default_value = 0.8
        nt.links.new(t.outputs["Color"], nm.inputs["Color"]); nt.links.new(nm.outputs[0], bsdf.inputs["Normal"])
    if sss:
        bsdf.inputs["Subsurface Weight"].default_value = sss
        bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.35, 0.2)
        bsdf.inputs["Subsurface Scale"].default_value = 0.012
    if coat:
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Coat Roughness"].default_value = 0.02
        bsdf.inputs["Coat IOR"].default_value = 1.376
    return m, nt, bsdf


skin_m, snt, sbsdf = principled("Hero.skin", os.path.join(DATA, H["skin"]), rough=0.48, sss=0.25)
# micro pores so close-ups don't look like plastic
bump = snt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.12; bump.inputs["Distance"].default_value = 0.0004
noise = snt.nodes.new("ShaderNodeTexNoise"); noise.inputs["Scale"].default_value = 1400; noise.inputs["Detail"].default_value = 4
snt.links.new(noise.outputs["Fac"], bump.inputs["Height"]); snt.links.new(bump.outputs["Normal"], sbsdf.inputs["Normal"])
body.data.materials.append(skin_m)

for rel, (ob, pd, folder) in proxies.items():
    kind = rel.split("/")[0]
    mats = pd[0]["materials"]
    mdef = mats[0]
    tex = mdef.get("mapDiffuse")
    if kind == "eyes":
        tex = "textures/" + H["eye_texture"]
    texp = os.path.join(folder, tex) if tex else None
    nrm = os.path.join(folder, mdef["mapNormal"]) if mdef.get("mapNormal") else None
    if kind == "eyes":
        m = principled("Hero.eyes", texp, rough=0.25, coat=1.0)[0]
    elif kind in ("hair", "eyebrows", "eyelashes"):
        m = principled(f"Hero.{kind}", texp, alpha=True, rough=0.45 if kind == "hair" else 0.6, spec=0.35)[0]
    elif kind in ("teeth", "tongue"):
        m = principled(f"Hero.{kind}", texp, rough=0.25 if kind == "teeth" else 0.4, sss=0.1)[0]
    else:
        m = principled("Hero." + os.path.basename(rel), texp, rough=0.75, normal=nrm, spec=0.3)[0]
    ob.data.materials.append(m)

# ---------------------------------------------------------------- report + save
heights = [(rig.matrix_world @ b.head_local).z for b in rig.data.bones]
print("HERO verts", len(body.data.vertices), "keys", len(body.data.shape_keys.key_blocks), "bones", len(rig.data.bones),
      "height", round(max(v.co.z for v in body.data.vertices), 3))
print("OBJECTS", sorted(o.name for o in bpy.data.objects))
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("SAVED", OUT)
