"""Short: "This man could hear his own eyeballs moving" (superior canal dehiscence, Stephen Mabbutt).

Run: blender -b --python scene.py -- <out.blend> [stills=1,2] [pct=100] [samples=40] [assets=<dir>]
assets dir must hold: char_hero_mh.blend (scripts/build_hero_mhdata.py) and anatomy.blend
(open-anatomy-3d male model, meshopt-decoded and imported). Narration timing: vo.json next to
this file. One continuous timeline; sets sit far apart in one scene and the hero rig teleports
between them on constant keys at each cut; X-ray shots are the same sets with scene["xray"]=1.
"""
import json
import math
import os
import random
import sys

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(HERE, "..", "..", "scripts"))
import pipeline as P  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
OUT = argv[0]
opts = dict(kv.split("=", 1) for kv in argv[1:] if "=" in kv)
unknown = set(opts) - {"stills", "pct", "samples", "assets"}
if unknown or any("=" not in a for a in argv[1:]):
    raise SystemExit(f"usage: <out.blend> [stills=1,2] [pct=100] [samples=40] [assets=dir]; got {argv[1:]}")
STILLS = [int(f) for f in opts["stills"].split(",")] if opts.get("stills") else []
PCT = int(opts.get("pct", 100))
SAMPLES = int(opts.get("samples", 28))
ASSETS = opts.get("assets", os.path.join(HERE, "..", "..", "blend"))
print(f"ARGS out={OUT} stills={STILLS} pct={PCT} samples={SAMPLES} assets={ASSETS}")

FPS = 30
VO = json.load(open(os.path.join(HERE, "vo.json")))


def fr(t):
    return int(round(t * FPS)) + 1


BEAT = [fr(b["start"]) for b in VO["beats"]]          # 1, 65, 131, 200, 290, 363, 434
VO_END = fr(VO["duration"])
END = VO_END + 42
FRAMES = range(1, END + 1)
random.seed(7)

# ---------------------------------------------------------------- shot plan (frame where each starts)
SH = {
    "bed_cu": 1,
    "xray_head": 31,
    "eye_a": BEAT[1],
    "sand": BEAT[1] + 22,
    "eye_b": BEAT[1] + 44,
    "xray_heart": BEAT[2],
    "chew": BEAT[2] + 30,
    "ct": BEAT[3],
    "xray_dive": BEAT[3] + 39,
    "ear_flow": BEAT[4],
    "or": BEAT[5],
    "seal": BEAT[5] + 30,
    "morning": BEAT[6],
}
ORDER = sorted(SH, key=SH.get)


def shot_at(f):
    cur = ORDER[0]
    for k in ORDER:
        if SH[k] <= f:
            cur = k
    return cur


def shot_range(k):
    i = ORDER.index(k)
    return SH[k], (SH[ORDER[i + 1]] - 1 if i + 1 < len(ORDER) else END)


XRAY_SHOTS = {"xray_head", "xray_heart", "xray_dive", "ear_flow", "seal"}
POSE_OF = {"bed_cu": "lie", "xray_head": "lie", "eye_a": "lie", "sand": "lie", "eye_b": "lie",
           "xray_heart": "lie", "chew": "sit", "ct": "ct", "xray_dive": "ct", "ear_flow": "ct",
           "or": "side", "seal": "side", "morning": "sit"}

# ---------------------------------------------------------------- open hero, scene setup
bpy.ops.wm.open_mainfile(filepath=os.path.join(ASSETS, "char_hero_mh.blend"))
scene = bpy.context.scene
scene.frame_start, scene.frame_end = 1, END
P.setup_render(scene, samples=SAMPLES)
scene.render.resolution_percentage = PCT
scene.render.use_persistent_data = True
scene.cycles.transparent_max_bounces = 16
scene.cycles.adaptive_threshold = 0.035
scene.cycles.max_bounces = 5
scene.cycles.diffuse_bounces = 2
scene.cycles.glossy_bounces = 2
scene.cycles.transmission_bounces = 2
scene.cycles.use_denoising = True
scene.cycles.denoising_input_passes = "RGB_ALBEDO_NORMAL"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.exposure = 0.0
scene.render.motion_blur_shutter = 0.4

rig = bpy.data.objects["HeroRig"]
body = bpy.data.objects["Hero.body"]
hero_objs = [o for o in bpy.data.objects if o.name.startswith("Hero.")]
keyed_meshes = [o for o in hero_objs if o.type == "MESH" and o.data.shape_keys]
for pb in rig.pose.bones:
    pb.rotation_mode = "QUATERNION"


# ---------------------------------------------------------------- generic helpers
def fcurves_of(idb):
    act = idb.animation_data.action
    if hasattr(act, "fcurves"):
        return act.fcurves
    from bpy_extras import anim_utils
    return anim_utils.action_get_channelbag_for_slot(act, idb.animation_data.action_slot).fcurves


def bake(idb, path, values, index=None, frames=FRAMES, interp="LINEAR"):
    """One value per frame written straight into an fcurve."""
    before = set()
    if idb.animation_data and idb.animation_data.action:
        before = {(c.data_path, c.array_index) for c in fcurves_of(idb)}
    if index is None:
        idb.keyframe_insert(data_path=path, frame=frames[0])
    else:
        idb.keyframe_insert(data_path=path, index=index, frame=frames[0])
    fc = fcurves_of(idb).find(path, index=index or 0)
    if fc is None:  # Blender stored the path in another spelling (e.g. inputs[27] for inputs["Name"])
        fc = next(c for c in fcurves_of(idb) if (c.data_path, c.array_index) not in before)
    fc.keyframe_points.clear()
    fc.keyframe_points.add(len(values))
    fc.keyframe_points.foreach_set("co", [c for f, v in zip(frames, values) for c in (f, v)])
    fc.keyframe_points.foreach_set("interpolation", [{"CONSTANT": 0, "LINEAR": 1}[interp]] * len(values))
    fc.update()
    return fc


def bake_vec(idb, path, vecs, n=3, interp="LINEAR", frames=FRAMES):
    for i in range(n):
        bake(idb, path, [v[i] for v in vecs], index=i, interp=interp, frames=frames)


def ramp(f, a, b):
    if b == a:
        return 1.0 if f >= a else 0.0
    x = min(max((f - a) / (b - a), 0.0), 1.0)
    return x * x * (3 - 2 * x)


def env(f, a, b, c, d):
    return ramp(f, a, b) * (1 - ramp(f, c, d))


def spike(f, at, rise=3, decay=10):
    if f < at - rise:
        return 0.0
    if f < at:
        return ramp(f, at - rise, at)
    return math.exp(-(f - at) / decay)


def wobble(f, seed, speed=1.0, freqs=(0.23, 0.51, 0.87)):
    return sum(math.sin(f / FPS * 2 * math.pi * fq * speed + seed * 1.7 + i) / (i + 1)
               for i, fq in enumerate(freqs)) / 1.83


def new_coll(name):
    c = bpy.data.collections.new(name)
    scene.collection.children.link(c)
    return c


def link(obj, coll):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def principled(name, color, rough=0.5, metal=0.0, **kw):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    for k, v in kw.items():
        b.inputs[k].default_value = v
    return m


def emission(name, color, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value = (*color, 1)
    e.inputs["Strength"].default_value = strength
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(e.outputs[0], o.inputs[0])
    return m


def box(name, loc, size, mat, coll, bevel=0.01, rot=(0, 0, 0), segs=3):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        m = o.modifiers.new("bevel", "BEVEL")
        m.width, m.segments, m.limit_method = bevel, segs, "NONE"
    o.data.materials.append(mat)
    for p in o.data.polygons:
        p.use_smooth = True
    return link(o, coll)


def scene_driver(idb, path, index=-1, expr="var"):
    d = idb.driver_add(path, index) if index >= 0 else idb.driver_add(path)
    drv = d.driver
    drv.type = "SCRIPTED"
    v = drv.variables.new()
    v.name = "var"
    v.targets[0].id_type = "SCENE"
    v.targets[0].id = scene
    v.targets[0].data_path = '["xray"]'
    drv.expression = expr
    return d


def show_only_in(objs, shots):
    """Key hide_render so these objects render only during the given shots."""
    keys = sorted({1} | {shot_range(s)[0] for s in SH} | {shot_range(s)[1] + 1 for s in SH})
    for o in objs:
        for f in keys:
            o.hide_render = shot_at(min(f, END)) not in shots
            o.keyframe_insert("hide_render", frame=f)
        o.hide_render = shot_at(1) not in shots


# ---------------------------------------------------------------- hero look polish
def mat_bsdf(m):
    return next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


skin_m = body.active_material
sb = mat_bsdf(skin_m)
# warm the very pale default texture a touch and give it a stylized-realism sheen (Zack D look)
snt = skin_m.node_tree
tex = sb.inputs["Base Color"].links[0].from_node
hsv = snt.nodes.new("ShaderNodeHueSaturation")
hsv.inputs["Saturation"].default_value = 1.18
hsv.inputs["Value"].default_value = 0.86
mixc = snt.nodes.new("ShaderNodeMixRGB")
mixc.blend_type = "MULTIPLY"
mixc.inputs[0].default_value = 0.35
mixc.inputs[2].default_value = (1.0, 0.78, 0.66, 1)
snt.links.new(tex.outputs["Color"], hsv.inputs["Color"])
snt.links.new(hsv.outputs[0], mixc.inputs[1])
snt.links.new(mixc.outputs[0], sb.inputs["Base Color"])
sb.inputs["Subsurface Weight"].default_value = 0.3
sb.inputs["Roughness"].default_value = 0.52
sb.inputs["Coat Weight"].default_value = 0.08
sb.inputs["Coat Roughness"].default_value = 0.35

hair_cap = bpy.data.objects["Hero.short02"]
hb = mat_bsdf(hair_cap.active_material)
hnt = hair_cap.active_material.node_tree
htex = hb.inputs["Base Color"].links[0].from_node
hdark = hnt.nodes.new("ShaderNodeMixRGB")
hdark.blend_type = "MULTIPLY"
hdark.inputs[0].default_value = 1.0
hdark.inputs[2].default_value = (0.42, 0.3, 0.22, 1)
hnt.links.new(htex.outputs["Color"], hdark.inputs[1])
hnt.links.new(hdark.outputs[0], hb.inputs["Base Color"])
hb.inputs["Roughness"].default_value = 0.62
hb.inputs["Coat Weight"].default_value = 0.0
hb.inputs["Sheen Weight"].default_value = 0.4
hb.inputs["Sheen Tint"].default_value = (0.9, 0.75, 0.6, 1)

# smooth the low-poly MakeHuman meshes so close-ups have clean silhouettes (after the armature)
for nm, lv in (("Hero.body", 2), ("Hero.short02", 2), ("Hero.male_casualsuit05", 1), ("Hero.shoes02", 1),
               ("Hero.HighPolyEyes", 1), ("Hero.Teeth_Base", 1)):
    o = bpy.data.objects.get(nm)
    if o:
        sub = o.modifiers.new("Smooth", "SUBSURF")
        sub.levels = 0
        sub.render_levels = lv
        sub.quality = 2
eye_m = bpy.data.objects["Hero.HighPolyEyes"].active_material
eye_b = mat_bsdf(eye_m)
eye_b.inputs["Roughness"].default_value = 0.15
eye_tex = eye_b.inputs["Base Color"].links[0].from_node
eye_m.node_tree.links.new(eye_tex.outputs["Alpha"], eye_b.inputs["Alpha"])

# ---------------------------------------------------------------- X-ray switch on every hero material
scene["xray"] = 0.0


def xray_group():
    ng = bpy.data.node_groups.new("XRayShell", "ShaderNodeTree")
    ng.interface.new_socket("Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
    N, Lk = ng.nodes, ng.links
    o = N.new("NodeGroupOutput")
    lw = N.new("ShaderNodeLayerWeight"); lw.inputs["Blend"].default_value = 0.3
    rmp = N.new("ShaderNodeMapRange"); rmp.inputs[1].default_value = 0.1; rmp.inputs[2].default_value = 0.95
    Lk.new(lw.outputs["Facing"], rmp.inputs[0])
    pw = N.new("ShaderNodeMath"); pw.operation = "POWER"; pw.inputs[1].default_value = 1.8
    Lk.new(rmp.outputs[0], pw.inputs[0])
    em = N.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (0.35, 0.75, 1.0, 1)
    em.inputs["Strength"].default_value = 1.3
    tr = N.new("ShaderNodeBsdfTransparent")
    mx = N.new("ShaderNodeMixShader")
    k = N.new("ShaderNodeMath"); k.operation = "MULTIPLY"; k.inputs[1].default_value = 0.32
    Lk.new(pw.outputs[0], k.inputs[0])
    fade = N.new("ShaderNodeAttribute"); fade.attribute_type = "VIEW_LAYER"; fade.attribute_name = "shell_fade"
    kf = N.new("ShaderNodeMath"); kf.operation = "MULTIPLY"
    Lk.new(k.outputs[0], kf.inputs[0]); Lk.new(fade.outputs["Fac"], kf.inputs[1])
    Lk.new(kf.outputs[0], mx.inputs[0]); Lk.new(tr.outputs[0], mx.inputs[1]); Lk.new(em.outputs[0], mx.inputs[2])
    Lk.new(mx.outputs[0], o.inputs[0])
    return ng


XG = xray_group()
done = set()
for o in hero_objs:
    for slot in o.material_slots:
        m = slot.material
        if not m or m.name in done:
            continue
        done.add(m.name)
        nt = m.node_tree
        outn = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
        src = outn.inputs["Surface"].links[0].from_socket
        hide = any(k in m.name for k in ("hair", "eyebrows", "eyelashes", "short02", "teeth", "tongue", "eyes"))
        if hide:  # these vanish in X-ray (the anatomy supplies real eyes/teeth)
            g = nt.nodes.new("ShaderNodeBsdfTransparent")
        else:
            g = nt.nodes.new("ShaderNodeGroup"); g.node_tree = XG
        mx = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(src, mx.inputs[1]); nt.links.new(g.outputs[0], mx.inputs[2])
        nt.links.new(mx.outputs[0], outn.inputs["Surface"])
        scene_driver(mx.inputs[0], "default_value")
print("XRAY_MATS", sorted(done))

# ---------------------------------------------------------------- posing helpers (armature space, standing frame)
REST = {pb.name: pb.bone.matrix_local.to_quaternion() for pb in rig.pose.bones}
X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))


def bq(name, axis, deg):
    r = REST[name]
    return r.inverted() @ Quaternion(axis, math.radians(deg)) @ r


def bone_dir(name):
    b = rig.data.bones[name]
    return (b.tail_local - b.head_local).normalized()


def aim_chain(chain):
    out, parent_delta = {}, Quaternion()
    for name, target in chain:
        c = bone_dir(name).rotation_difference(parent_delta.inverted() @ Vector(target).normalized())
        r = REST[name]
        out[name] = r.inverted() @ c @ r
        parent_delta = parent_delta @ c
    return out


def limb_pose(kind):
    """Static body pose per set: arms/legs aimed in armature space."""
    p = {}
    for side, sx in (("L", 1), ("R", -1)):
        if kind in ("lie", "ct", "side"):
            arm = [(f"upperarm01.{side}", (0.18 * sx, 0.02, -1)), (f"upperarm02.{side}", (0.18 * sx, 0.02, -1)),
                   (f"lowerarm01.{side}", (0.1 * sx, -0.22, -1)), (f"lowerarm02.{side}", (0.1 * sx, -0.22, -1))]
            leg = [(f"upperleg01.{side}", (0.05 * sx, 0.0, -1)), (f"upperleg02.{side}", (0.05 * sx, 0.0, -1)),
                   (f"lowerleg01.{side}", (0.03 * sx, 0.02, -1)), (f"lowerleg02.{side}", (0.03 * sx, 0.02, -1)),
                   (f"foot.{side}", (0.12 * sx, -0.55, -0.35))]
        else:  # sitting up in bed, legs straight out under the blanket, hands on lap
            arm = [(f"upperarm01.{side}", (0.16 * sx, -0.3, -1)), (f"upperarm02.{side}", (0.16 * sx, -0.3, -1)),
                   (f"lowerarm01.{side}", (-0.22 * sx, -1, -0.32)), (f"lowerarm02.{side}", (-0.22 * sx, -1, -0.32))]
            leg = [(f"upperleg01.{side}", (0.06 * sx, -1, -0.24)), (f"upperleg02.{side}", (0.06 * sx, -1, -0.24)),
                   (f"lowerleg01.{side}", (0.02 * sx, -1, -0.26)), (f"lowerleg02.{side}", (0.02 * sx, -1, -0.26)),
                   (f"foot.{side}", (0.1 * sx, -0.2, 1))]
        p.update(aim_chain(arm))
        p.update(aim_chain(leg))
    return p


LIMBS = {k: limb_pose(k) for k in ("lie", "sit")}
LIMBS["ct"] = LIMBS["side"] = LIMBS["lie"]

# rig object placement per pose (set origins chosen below)
BED = Vector((0, 0, 0))
CT = Vector((60, 0, 0))
OR = Vector((90, 0, 0))
MACRO = Vector((30, 0, 0))
MATTRESS_TOP = 0.56
LIE_ROT = (math.radians(-90), 0, 0)
PLACE = {
    "lie": (BED + Vector((0, -0.78, MATTRESS_TOP + 0.085)), LIE_ROT),
    "sit": (BED + Vector((0, 0.62, MATTRESS_TOP - 0.83)), (math.radians(-12), 0, 0)),
    "ct": (CT + Vector((0, -0.95, 0.98)), LIE_ROT),
    "side": (OR + Vector((0, -0.9, 1.02)), LIE_ROT),
}


# ---------------------------------------------------------------- acting curves
def glances(f):
    """Eye yaw (deg, + = his left) and pitch; quick saccades with holds, per shot."""
    s = shot_at(f)
    if s in ("bed_cu", "xray_head"):
        keys = [(1, 0), (9, 0), (12, 26), (22, 26), (25, -24), (38, -24), (41, 22), (52, 22), (55, -10)]
    elif s == "eye_a":
        a = SH["eye_a"]
        keys = [(a, -20), (a + 6, -20), (a + 10, 30), (a + 22, 30)]
    elif s in ("sand", "eye_b"):
        a = SH["eye_b"]
        keys = [(a, 30), (a + 4, 30), (a + 9, -30), (a + 22, -30)]
    elif s == "morning":
        a = SH["morning"]
        keys = [(a, 0), (a + 8, 0), (a + 12, 28), (a + 22, 28), (a + 26, -26), (a + 36, -26), (a + 40, 0)]
    else:
        keys = [(1, 0)]
    yaw = keys[0][1]
    for (f0, v0), (f1, v1) in zip(keys, keys[1:]):
        if f >= f0:
            yaw = v0 + (v1 - v0) * ramp(f, f0, f1)
    return yaw


SACCADES = [1 + 12, 1 + 25, 1 + 41, SH["eye_a"] + 10, SH["eye_b"] + 9]  # each one "scrapes"
CHEWS = [SH["chew"] + 4 + 9 * i for i in range(4)]
HEARTBEATS = [SH["xray_heart"] + 2 + 13 * i for i in range(3)]
BLINKS = [5, 60, SH["morning"] + 4, SH["morning"] + 50, SH["morning"] + 80]


def curves(f):
    s = shot_at(f)
    c = {}
    c["yaw"] = glances(f)
    c["wince"] = max([spike(f, sc, rise=2, decay=14) for sc in SACCADES[3:]] +
                     [env(f, SH["chew"] + 3, SH["chew"] + 8, SH["ct"] - 6, SH["ct"])], default=0)
    c["chew"] = sum(max(0, math.sin(math.pi * (f - c0) / 9)) for c0 in CHEWS if c0 <= f < c0 + 9) if s == "chew" else 0
    c["blink"] = max((env(f, b - 1, b + 1, b + 3, b + 6) for b in BLINKS), default=0)
    c["smile"] = ramp(f, BEAT[6] + 30, BEAT[6] + 40) if s == "morning" else 0
    c["calm"] = 1.0 if s == "morning" else 0.0
    c["turn"] = 1.0 if POSE_OF[s] == "side" else 0.0
    c["breath"] = math.sin(f / FPS * 2 * math.pi / 3.6)
    return c


ROT, SHAPES, RIGLOC, RIGROT = {}, {}, [], []
for f in FRAMES:
    s = shot_at(f)
    pose = POSE_OF[s]
    c = curves(f)
    loc, rot = PLACE[pose]
    dz = 0.0
    if s == "ct":  # table slides the patient into the gantry
        loc = loc + Vector((0, 0.9 * ramp(f, SH["ct"] + 4, SH["xray_dive"] - 2), 0))
    if s in ("xray_dive", "ear_flow"):
        loc = loc + Vector((0, 0.9, 0))
    RIGLOC.append(loc + Vector((0, 0, dz)))
    RIGROT.append(rot)
    br = c["breath"]
    poses = {
        "spine03": [(X, 1.2 * br * (0.4 if pose != "sit" else 1))],
        "spine02": [(X, 0.8 * br)],
        "neck01": [(X, (8 if pose == "sit" else -4)), (Z, 1.2 * wobble(f, 2))],
        "neck02": [(Z, 35 * c["turn"])],
        "neck03": [(Z, 35 * c["turn"])],
        "head": [(X, (4 if pose == "sit" else 7) + 3 * c["wince"] + 0.8 * wobble(f, 5, 0.6)),
                 (Z, 10 * c["turn"] + 1.5 * wobble(f, 4, 0.5) * (1 - c["turn"])),
                 (Y, -4 * c["wince"])],
        "jaw": [(X, 13 * c["chew"] + 1.5 * c["wince"])],
        "eye.L": [(Z, c["yaw"]), (X, -2)],
        "eye.R": [(Z, c["yaw"]), (X, -2)],
    }
    for name, rots in poses.items():
        q = Quaternion()
        for axis, deg in rots:
            q = q @ bq(name, axis, deg)
        ROT.setdefault(name, []).append(q)
    for name, q in LIMBS[pose].items():
        ROT.setdefault(name, []).append(q)
    k = {}
    w, bl, sm = c["wince"], c["blink"], c["smile"]
    for side in ("left", "right"):
        k[f"eye-{side}-closure"] = min(1, bl + 0.12 * w + 0.15 * sm)
        k[f"eye-{side}-slit"] = 0.25 * w + 0.3 * sm
        k[f"eyebrows-{side}-down"] = 0.75 * w
        k[f"eyebrows-{side}-inner-up"] = 0.35 * w * (1 - c["chew"])
        k[f"nose-{side}-elevation"] = 0.5 * w
    k["mouth-corner-puller"] = 0.85 * sm
    k["mouth-upward-retraction"] = 0.25 * sm + 0.35 * w
    k["mouth-compression"] = 0.4 * w * (1 - c["chew"])
    k["mouth-open"] = 0.0
    for kk, vv in k.items():
        SHAPES.setdefault(kk, []).append(max(0.0, min(1.0, vv)))

for name, qs in ROT.items():
    for i in range(1, len(qs)):
        if qs[i].dot(qs[i - 1]) < 0:
            qs[i] = -qs[i]
    path = f'pose.bones["{name}"].rotation_quaternion'
    for i in range(4):
        bake(rig, path, [q[i] for q in qs], index=i)
bake_vec(rig, "location", RIGLOC, interp="CONSTANT")
bake_vec(rig, "rotation_euler", RIGROT, interp="CONSTANT")
for o in keyed_meshes:
    kb = o.data.shape_keys.key_blocks
    for name, vals in SHAPES.items():
        if name in kb:
            bake(o.data.shape_keys, f'key_blocks["{name}"].value', vals)


def pose_frame(f):
    scene.frame_set(f)
    bpy.context.view_layer.update()


def bone_world(name, f, tail=False):
    pose_frame(f)
    pb = rig.pose.bones[name]
    return rig.matrix_world @ (pb.tail if tail else pb.head)


def eye_center_world(f, side="L"):
    pose_frame(f)
    pb = rig.pose.bones[f"eye.{side}"]
    return rig.matrix_world @ pb.head


# ---------------------------------------------------------------- anatomy (aligned to the hero's eyes, rides the head bone)
ANAT_PARTS = ["skull", "mandible", "teeth", "eye_l", "eye_r", "brain", "cerebellum", "brainstem",
              "spine_cervical", "arteries_head", "carotid_l", "carotid_r", "trachea",
              "heart", "aorta", "lung_l", "lung_r", "ribs_l", "ribs_r", "sternum", "spine_thoracic",
              "clavicle_l", "clavicle_r", "coronary_arteries"]
with bpy.data.libraries.load(os.path.join(ASSETS, "anatomy.blend")) as (src, dst):
    dst.objects = [n for n in ANAT_PARTS if n in src.objects]
ANAT = new_coll("Anatomy")
anat = {}
for o in bpy.data.objects:
    if o.name in ANAT_PARTS and o.type == "MESH" and o.library is None and o.name not in [h.name for h in hero_objs]:
        o.parent = None
        ANAT.objects.link(o)
        anat[o.name] = o
print("ANATOMY", sorted(anat))


def centroid(o):
    v = np.array([vv.co[:] for vv in o.data.vertices])
    return Matrix(o.matrix_world) @ Vector(v.mean(0))


# rest-pose hero eye centers (armature space == world here: rig at origin before keys)
rig.data.pose_position = "REST"
scene.frame_set(1)
rig_mw_saved = rig.matrix_world.copy()
hero_eye = [rig.data.bones["eye.L"].head_local.copy(), rig.data.bones["eye.R"].head_local.copy()]
rig.data.pose_position = "POSE"
a_eye = [centroid(anat["eye_l"]), centroid(anat["eye_r"])]
s_head = (hero_eye[0] - hero_eye[1]).length / (a_eye[0] - a_eye[1]).length
mid_h = (hero_eye[0] + hero_eye[1]) / 2
mid_a = (a_eye[0] + a_eye[1]) / 2
HEAD_FIT = Matrix.Translation(mid_h) @ Matrix.Scale(s_head * 1.0, 4) @ Matrix.Translation(-mid_a)
# torso parts: own fit, anchored at the collarbones and scaled by overall height
chest_h = rig.data.bones["spine02"].head_local
neck_h = rig.data.bones["neck01"].head_local
hero_clav = sum(((rig.data.bones[f"clavicle.{sd}"].head_local + rig.data.bones[f"clavicle.{sd}"].tail_local) / 2
                 for sd in ("L", "R")), Vector()) / 2
a_clav = (centroid(anat["clavicle_l"]) + centroid(anat["clavicle_r"])) / 2
s_torso = 1.80 / 1.719
TORSO_FIT = Matrix.Translation(hero_clav) @ Matrix.Scale(s_torso, 4) @ Matrix.Translation(-a_clav)
HEAD_PARTS = {"skull", "mandible", "teeth", "eye_l", "eye_r", "brain", "cerebellum", "brainstem", "arteries_head"}
print("FIT head", round(s_head, 3), "torso", round(s_torso, 3))


def parent_rest(obj, bone, fit):
    """Place obj with fit (rest-pose armature space), then ride the bone."""
    obj.matrix_world = fit @ obj.matrix_world
    b = rig.data.bones[bone]
    obj.parent, obj.parent_type, obj.parent_bone = rig, "BONE", bone
    rest = b.matrix_local @ Matrix.Translation((0, b.length, 0))
    obj.matrix_parent_inverse = rest.inverted()


for n, o in anat.items():
    if n in HEAD_PARTS:
        parent_rest(o, "jaw" if n in ("mandible", "teeth") else "head", HEAD_FIT)
    elif n in ("spine_cervical", "carotid_l", "carotid_r", "trachea"):
        parent_rest(o, "neck02", HEAD_FIT)
    else:
        parent_rest(o, "spine01", TORSO_FIT)


def xray_mat(name, color, strength, alpha, core=(1, 1, 1), fades=True):
    """Glowing translucent X-ray organ: fresnel rim glow + faint core."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    lw = nt.nodes.new("ShaderNodeLayerWeight"); lw.inputs["Blend"].default_value = 0.45
    ramp_ = nt.nodes.new("ShaderNodeMapRange"); ramp_.inputs[1].default_value = 0.0; ramp_.inputs[2].default_value = 1.0
    ramp_.inputs[3].default_value = alpha * 0.35; ramp_.inputs[4].default_value = alpha
    nt.links.new(lw.outputs["Facing"], ramp_.inputs[0])
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = strength
    em.name = "Glow"
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    fac = ramp_.outputs[0]
    if fades:
        fade = nt.nodes.new("ShaderNodeAttribute"); fade.attribute_type = "VIEW_LAYER"; fade.attribute_name = "shell_fade"
        kf = nt.nodes.new("ShaderNodeMath"); kf.operation = "MULTIPLY"
        nt.links.new(fac, kf.inputs[0]); nt.links.new(fade.outputs["Fac"], kf.inputs[1])
        fac = kf.outputs[0]
    nt.links.new(fac, mx.inputs[0]); nt.links.new(tr.outputs[0], mx.inputs[1]); nt.links.new(em.outputs[0], mx.inputs[2])
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(mx.outputs[0], o.inputs[0])
    return m


M_BONE = xray_mat("XBone", (0.85, 0.92, 1.0), 1.4, 0.42)
M_EYE = xray_mat("XEye", (0.9, 0.97, 1.0), 2.2, 0.6)
M_BRAIN = xray_mat("XBrain", (1.0, 0.55, 0.75), 0.8, 0.16)
M_ART = xray_mat("XArtery", (1.0, 0.18, 0.12), 2.5, 0.7)
M_HEART = xray_mat("XHeart", (1.0, 0.12, 0.08), 4.0, 0.9)
M_LUNG = xray_mat("XLung", (1.0, 0.6, 0.7), 0.6, 0.12)
for n, o in anat.items():
    o.data.materials.clear()
    o.data.materials.append({"eye_l": M_EYE, "eye_r": M_EYE, "brain": M_BRAIN, "cerebellum": M_BRAIN,
                             "brainstem": M_BRAIN, "arteries_head": M_ART, "carotid_l": M_ART,
                             "carotid_r": M_ART, "heart": M_HEART, "aorta": M_ART, "coronary_arteries": M_ART,
                             "lung_l": M_LUNG, "lung_r": M_LUNG, "trachea": M_LUNG}.get(n, M_BONE))
    for p in o.data.polygons:
        p.use_smooth = True

if "heart" in anat:
    hrt = anat["heart"]
    s0 = hrt.scale.copy()
    beat = [1 + 0.12 * max((spike(f, h, rise=2, decay=5) for h in HEARTBEATS), default=0)
            + 0.07 * max((spike(f, h + 5, rise=2, decay=4) for h in HEARTBEATS), default=0) for f in FRAMES]
    bake_vec(hrt, "scale", [s0 * b_ for b_ in beat])
    bake(M_HEART.node_tree, 'nodes["Glow"].inputs[1].default_value', [4.0 * (0.7 + 2.0 * (b_ - 1) / 0.12) for b_ in beat])

# ---------------------------------------------------------------- inner ear (left side), built in rest space, rides the head
EAR = new_coll("InnerEar")
# location: medial to the left ear canal, behind/below the eye (rest-pose armature space)
EAR_C = Vector((hero_eye[0].x + 0.016, hero_eye[0].y + 0.085, hero_eye[0].z - 0.028))
EAR_S = 1.35  # drawn ~35% oversize so it reads on a phone screen (noted in metadata)
def solid_glow(name, base, glow, strength, rough=0.35):
    """Solid, glossy organ that also glows (keyable "Glow" emission node) - reads in a dark void."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*base, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Subsurface Weight"].default_value = 0.4
    bsdf.inputs["Subsurface Radius"].default_value = (1.0, 0.5, 0.3)
    bsdf.inputs["Subsurface Scale"].default_value = 0.002
    bsdf.inputs["Coat Weight"].default_value = 0.5
    em = nt.nodes.new("ShaderNodeEmission"); em.name = "Glow"
    em.inputs["Color"].default_value = (*glow, 1); em.inputs["Strength"].default_value = strength
    lw = nt.nodes.new("ShaderNodeLayerWeight"); lw.inputs["Blend"].default_value = 0.35
    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = 1.0
    add = nt.nodes.new("ShaderNodeAddShader")
    out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    nt.links.new(bsdf.outputs[0], add.inputs[0]); nt.links.new(em.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs["Surface"])
    return m


M_CANAL = solid_glow("XCanal", (1.0, 0.72, 0.45), (1.0, 0.62, 0.2), 1.2)
M_CANAL_HOT = xray_mat("XCanalHot", (1.0, 0.85, 0.4), 6.0, 0.95, fades=False)
M_SHELL = solid_glow("XShell", (0.93, 0.9, 0.82), (0.9, 0.92, 1.0), 0.25, rough=0.55)
M_HOLE = emission("XHole", (1.0, 0.08, 0.05), 12.0)
M_PATCH = principled("BonePatch", (0.93, 0.88, 0.76), 0.55, **{"Subsurface Weight": 0.3, "Emission Color": (1, 0.95, 0.85, 1), "Emission Strength": 1.2})


def tube_arc(name, radius, tube, start_deg, end_deg, mat, n=48):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = tube
    cu.bevel_resolution = 4
    sp = cu.splines.new("POLY")
    sp.points.add(n)
    for i in range(n + 1):
        a = math.radians(start_deg + (end_deg - start_deg) * i / n)
        sp.points[i].co = (radius * math.cos(a), 0, radius * math.sin(a), 1)
    o = bpy.data.objects.new(name, cu)
    cu.materials.append(mat)
    EAR.objects.link(o)
    return o


ear_root = bpy.data.objects.new("EarRoot", None)
EAR.objects.link(ear_root)
r = 0.0034
sup = tube_arc("CanalSuperior", r, 0.00045, -20, 200, M_CANAL)        # vertical, ~45 deg to sagittal
sup.rotation_euler = (0, 0, math.radians(-45)); sup.location = (0, 0, 0.0028)
post = tube_arc("CanalPosterior", r, 0.00045, -200, 20, M_CANAL)      # vertical, perpendicular to superior
post.rotation_euler = (0, 0, math.radians(45)); post.location = (0, 0.002, -0.0005)
lat = tube_arc("CanalLateral", r * 0.85, 0.00042, -110, 150, M_CANAL)  # near-horizontal
lat.rotation_euler = (math.radians(90 - 30), 0, 0); lat.location = (0.0012, -0.0006, 0)
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.0019, location=(0, 0, 0))
vest = bpy.context.active_object; vest.name = "Vestibule"; vest.scale = (1, 1.3, 0.9)
vest.data.materials.append(M_CANAL); link(vest, EAR)
for p in vest.data.polygons:
    p.use_smooth = True
# cochlea: 2.5-turn tapering spiral, anterior-medial of the vestibule
cu = bpy.data.curves.new("Cochlea", "CURVE"); cu.dimensions = "3D"; cu.bevel_depth = 0.0007; cu.bevel_resolution = 4
sp = cu.splines.new("POLY"); NS = 120; sp.points.add(NS)
for i in range(NS + 1):
    t = i / NS
    a = t * 2.5 * 2 * math.pi
    rr = 0.0036 * (1 - 0.72 * t)
    sp.points[i].co = (rr * math.cos(a), rr * math.sin(a), 0.0016 * t, 1)
    sp.points[i].radius = 1 - 0.6 * t
coch = bpy.data.objects.new("Cochlea", cu); cu.materials.append(M_CANAL); EAR.objects.link(coch)
coch.location = (-0.0045, -0.0068, -0.0022); coch.rotation_euler = (math.radians(70), math.radians(20), 0)
# bone roof over the top of the superior canal, with the dehiscence (gap) near its apex
roof_l = tube_arc("RoofA", r + 0.0011, 0.00055, 20, 78, M_SHELL)
roof_r = tube_arc("RoofB", r + 0.0011, 0.00055, 102, 160, M_SHELL)
for o in (roof_l, roof_r):
    o.rotation_euler = sup.rotation_euler; o.location = sup.location
    o.data.bevel_depth = 0.0007
hole_dir = Matrix.Rotation(math.radians(-45), 3, "Z") @ Vector((0, 0, r + 0.0011))
bpy.ops.mesh.primitive_torus_add(major_radius=0.0013, minor_radius=0.00022, location=hole_dir + Vector((0, 0, 0.0028)))
hole = bpy.context.active_object; hole.name = "HoleRim"; hole.data.materials.append(M_HOLE); link(hole, EAR)
hole.rotation_euler = (0, 0, 0)
HOLE_LOCAL = hole.location.copy()
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.0014, location=HOLE_LOCAL)
patch = bpy.context.active_object; patch.name = "BonePatch"; patch.scale = (1.0, 1.0, 0.4)
patch.data.materials.append(M_PATCH); link(patch, EAR)
for p in patch.data.polygons:
    p.use_smooth = True
for o in (sup, post, lat, vest, coch, roof_l, roof_r, hole, patch):
    o.parent = ear_root
ear_root.location = EAR_C
ear_root.scale = (EAR_S,) * 3
ear_root.rotation_euler = (0, 0, math.radians(15))
bpy.context.view_layer.update()
b = rig.data.bones["head"]
ear_root.parent, ear_root.parent_type, ear_root.parent_bone = rig, "BONE", "head"
ear_root.matrix_parent_inverse = (b.matrix_local @ Matrix.Translation((0, b.length, 0))).inverted()

# hole/patch animation: rim pulses red until sealed; the patch flies in during "seal"
SEAL = SH["seal"] + 14
hole_glow = [12.0 * (0.65 + 0.35 * math.sin(f * 0.5)) * (1 - ramp(f, SEAL, SEAL + 6)) for f in FRAMES]
bake(M_HOLE.node_tree, 'nodes["Emission"].inputs[1].default_value', hole_glow)
bake_vec(hole, "scale", [(1, 1, 1) if f < SEAL + 4 else (0.001, 0.001, 0.001) for f in FRAMES], interp="CONSTANT")
pa = SH["seal"]
patch_off = [Vector((0.0, -0.004, 0.012)) * (1 - ramp(f, pa + 2, SEAL)) for f in FRAMES]
bake_vec(patch, "location", [HOLE_LOCAL + v + Vector((0, 0, 0.0004)) for v in patch_off])
canal_hot = [ramp(f, SH["ear_flow"] + 10, SH["ear_flow"] + 40) * (1 - ramp(f, SEAL, SEAL + 12)) for f in FRAMES]
for mm in (M_CANAL,):
    g = mm.node_tree.nodes["Glow"]
    bake(mm.node_tree, 'nodes["Glow"].inputs[0].default_value',
         [1.0 for _ in FRAMES], index=0)
    bake(mm.node_tree, 'nodes["Glow"].inputs[0].default_value',
         [0.62 - 0.45 * h + 0.25 * ramp(f, SEAL, SEAL + 12) for f, h in zip(FRAMES, canal_hot)], index=1)
    bake(mm.node_tree, 'nodes["Glow"].inputs[0].default_value',
         [0.2 - 0.15 * h + 0.75 * ramp(f, SEAL, SEAL + 12) for f, h in zip(FRAMES, canal_hot)], index=2)
    bake(mm.node_tree, 'nodes["Glow"].inputs[1].default_value',
         [1.2 + 5.0 * h * (0.7 + 0.3 * math.sin(f * 0.9)) for f, h in zip(FRAMES, canal_hot)])

# ---------------------------------------------------------------- sound visualisation: rings + travelling pulses
FX = new_coll("SoundFX")


def ring_mat(name, color):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = 3.0
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    oi = nt.nodes.new("ShaderNodeObjectInfo")
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(oi.outputs["Color"], sep.inputs[0])
    mx = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(sep.outputs[0], mx.inputs[0])       # object color R = opacity
    nt.links.new(tr.outputs[0], mx.inputs[1]); nt.links.new(em.outputs[0], mx.inputs[2])
    o = nt.nodes.new("ShaderNodeOutputMaterial"); nt.links.new(mx.outputs[0], o.inputs[0])
    return m


M_RING_SCRATCH = ring_mat("RingScratch", (0.55, 0.9, 1.0))
M_RING_LOUD = ring_mat("RingLoud", (1.0, 0.55, 0.15))
M_RING_HEART = ring_mat("RingHeart", (1.0, 0.18, 0.12))


def ear_world_and_normal(f, side="L"):
    """Outer-ear position and outward normal for frame f (from the posed head bone)."""
    pose_frame(f)
    pb = rig.pose.bones["head"]
    m = rig.matrix_world @ pb.matrix
    sx = 1 if side == "L" else -1
    p = m @ (pb.bone.matrix_local.inverted() @ Vector((sx * 0.083, hero_eye[0].y + 0.085, hero_eye[0].z - 0.02)))
    n = (m.to_3x3() @ (pb.bone.matrix_local.to_3x3().inverted() @ Vector((sx, 0, 0)))).normalized()
    return p, n


def burst(at, mat, count=3, spacing=3, life=16, size=(0.03, 0.16), side="L", thick=0.0005, seed=0):
    """Expanding concentric rings leaving the ear, each fading out."""
    p, n = ear_world_and_normal(at, side)
    rot = n.to_track_quat("Z", "Y").to_euler()
    for i in range(count):
        t0 = at + i * spacing
        bpy.ops.mesh.primitive_torus_add(major_radius=1.0, minor_radius=thick / size[1] * 4, major_segments=96, minor_segments=6,
                                         location=p + n * 0.01, rotation=rot)
        o = bpy.context.active_object
        o.name = f"Ring_{mat.name}_{at}_{i}"
        o.data.materials.append(mat)
        link(o, FX)
        cut = shot_range(shot_at(at))[1]
        fs = range(max(1, t0 - 1), min(END, t0 + life) + 1)
        sc, col, loc = [], [], []
        for f in fs:
            x = min(max((f - t0) / life, 0), 1)
            rr = size[0] + (size[1] - size[0]) * (1 - (1 - x) ** 2)
            sc.append((rr, rr, rr))
            col.append((0.0 if f < t0 else (1 - x) ** 1.5, 0, 0, 1))
            loc.append(p + n * (0.01 + 0.05 * x))
        bake_vec(o, "scale", sc, frames=fs)
        bake_vec(o, "color", col, n=4, frames=fs)
        bake_vec(o, "location", loc, frames=fs)
        o.hide_render = True
        for f, hv in ((1, True), (max(1, t0 - 1), False), (min(END, t0 + life + 1, cut + 1), True)):
            o.hide_render = hv
            o.keyframe_insert("hide_render", frame=f)


for sc_ in SACCADES[:3]:
    if sc_ < SH["xray_head"]:
        burst(sc_, M_RING_SCRATCH, count=3, spacing=3, life=18, size=(0.012, 0.075))
for sc_ in SACCADES[3:]:
    burst(sc_, M_RING_SCRATCH, count=3, spacing=2, life=16, size=(0.012, 0.07))
for c0 in CHEWS:
    burst(c0 + 3, M_RING_LOUD, count=2, spacing=3, life=14, size=(0.008, 0.055), thick=0.0005)


def pulse_path(name, pts, color, coll, t_on, t_off, speed=1.4, width=0.0015, waves=3.0):
    """Glowing tube along pts with bright pulses travelling from the first point to the last."""
    cu = bpy.data.curves.new(name, "CURVE"); cu.dimensions = "3D"
    cu.bevel_depth = width; cu.bevel_resolution = 3; cu.use_fill_caps = True
    sp = cu.splines.new("NURBS"); sp.points.add(len(pts) - 1)
    for i, p_ in enumerate(pts):
        sp.points[i].co = (*p_, 1)
        sp.points[i].radius = 1.0 - 0.8 * i / (len(pts) - 1)  # thin where it enters the inner ear
    sp.use_endpoint_u = True; sp.order_u = 3
    o = bpy.data.objects.new(name, cu); coll.objects.link(o)
    m = bpy.data.materials.new(name + "Mat"); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sepx = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sepx.inputs[0])  # generated X runs along a curve
    phase = nt.nodes.new("ShaderNodeValue"); phase.name = "Phase"
    sub = nt.nodes.new("ShaderNodeMath"); sub.operation = "SUBTRACT"
    nt.links.new(sepx.outputs[0], sub.inputs[0]); nt.links.new(phase.outputs[0], sub.inputs[1])
    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = waves
    nt.links.new(sub.outputs[0], mul.inputs[0])
    fr_ = nt.nodes.new("ShaderNodeMath"); fr_.operation = "FRACT"
    nt.links.new(mul.outputs[0], fr_.inputs[0])
    pw = nt.nodes.new("ShaderNodeMath"); pw.operation = "POWER"; pw.inputs[1].default_value = 6.0
    nt.links.new(fr_.outputs[0], pw.inputs[0])
    gain = nt.nodes.new("ShaderNodeMath"); gain.operation = "MULTIPLY_ADD"
    gain.inputs[1].default_value = 25.0; gain.inputs[2].default_value = 0.15
    nt.links.new(pw.outputs[0], gain.inputs[0])
    vis = nt.nodes.new("ShaderNodeValue"); vis.name = "Vis"
    g2 = nt.nodes.new("ShaderNodeMath"); g2.operation = "MULTIPLY"
    nt.links.new(gain.outputs[0], g2.inputs[0]); nt.links.new(vis.outputs[0], g2.inputs[1])
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (*color, 1)
    nt.links.new(g2.outputs[0], em.inputs["Strength"])
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mx = nt.nodes.new("ShaderNodeMixShader")
    clamp = nt.nodes.new("ShaderNodeMath"); clamp.operation = "MINIMUM"; clamp.inputs[1].default_value = 1.0
    nt.links.new(g2.outputs[0], clamp.inputs[0])
    nt.links.new(clamp.outputs[0], mx.inputs[0]); nt.links.new(tr.outputs[0], mx.inputs[1]); nt.links.new(em.outputs[0], mx.inputs[2])
    out = nt.nodes.new("ShaderNodeOutputMaterial"); nt.links.new(mx.outputs[0], out.inputs[0])
    cu.materials.append(m)
    bake(nt, 'nodes["Phase"].outputs[0].default_value', [speed * (f - t_on) / FPS for f in FRAMES])
    bake(nt, 'nodes["Vis"].outputs[0].default_value', [env(f, t_on, t_on + 5, t_off - 5, t_off) for f in FRAMES])
    return o


# ---------------------------------------------------------------- bedroom set (night + morning)
SET_BED = new_coll("SetBedroom")
M_WALL = principled("Wall", (0.42, 0.47, 0.55), 0.85)
M_WOOD = principled("WoodDark", (0.23, 0.13, 0.07), 0.45)
M_SHEET = principled("Sheet", (0.78, 0.8, 0.84), 0.8, **{"Sheen Weight": 0.6})
M_BLANKET = principled("Blanket", (0.16, 0.24, 0.42), 0.85, **{"Sheen Weight": 0.8, "Sheen Tint": (0.7, 0.8, 1, 1)})
M_PILLOW = principled("Pillow", (0.86, 0.87, 0.9), 0.75, **{"Sheen Weight": 0.5})
M_LAMPSHADE = principled("Lampshade", (1.0, 0.86, 0.62), 0.6, **{"Transmission Weight": 0.6, "Emission Color": (1.0, 0.7, 0.4, 1), "Emission Strength": 0.0})
M_FLOOR = principled("Floor", (0.3, 0.2, 0.13), 0.4)

box("Mattress", BED + Vector((0, 0.15, MATTRESS_TOP - 0.13)), (1.5, 2.1, 0.26), M_SHEET, SET_BED, bevel=0.06, segs=5)
box("BedFrame", BED + Vector((0, 0.15, 0.2)), (1.6, 2.2, 0.22), M_WOOD, SET_BED, bevel=0.02)
box("Headboard", BED + Vector((0, 1.27, 0.95)), (1.66, 0.08, 1.0), M_WOOD, SET_BED, bevel=0.03)
box("WallBack", BED + Vector((0, 1.45, 1.5)), (8, 0.1, 3.0), M_WALL, SET_BED, bevel=0)
box("WallSide", BED + Vector((-2.2, 0, 1.5)), (0.1, 6, 3.0), M_WALL, SET_BED, bevel=0)
box("FloorBed", BED + Vector((0, 0, -0.01)), (10, 10, 0.02), M_FLOOR, SET_BED, bevel=0)
box("Nightstand", BED + Vector((1.15, 0.95, 0.3)), (0.5, 0.45, 0.6), M_WOOD, SET_BED, bevel=0.015)
bpy.ops.mesh.primitive_cylinder_add(radius=0.13, depth=0.22, location=BED + Vector((1.15, 0.95, 0.95)))
shade = link(bpy.context.active_object, SET_BED); shade.name = "Lampshade"; shade.data.materials.append(M_LAMPSHADE)
for name, loc, size in (("PillowA", (0, 1.0, MATTRESS_TOP + 0.08), (0.72, 0.42, 0.16)),):
    bpy.ops.mesh.primitive_cube_add(size=1, location=BED + Vector(loc))
    pil = bpy.context.active_object; pil.name = name; pil.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    sub = pil.modifiers.new("sub", "SUBSURF"); sub.levels = sub.render_levels = 3
    cast = pil.modifiers.new("cast", "CAST"); cast.factor = 0.35
    pil.data.materials.append(M_PILLOW); link(pil, SET_BED)
    for p in pil.data.polygons:
        p.use_smooth = True
PILLOW = bpy.data.objects["PillowA"]
# window with moonlight / sunlight behind the bed (left wall)
box("WindowFrame", BED + Vector((-2.14, 0.1, 1.6)), (0.06, 1.2, 1.2), principled("WinFrame", (0.9, 0.9, 0.9), 0.4), SET_BED, bevel=0.01)
M_WINDOW = emission("WindowGlow", (0.45, 0.6, 1.0), 2.5)
box("WindowPane", BED + Vector((-2.1, 0.1, 1.6)), (0.02, 1.08, 1.08), M_WINDOW, SET_BED, bevel=0)


def drape_blanket(name, pose_key, frame, y0, y1, x_half=0.8, top_z=MATTRESS_TOP, max_h=9.0):
    """Blanket mesh 'dropped' on the posed hero + mattress (ray-cast drape, smoothed, wrinkled)."""
    pose_frame(frame)
    dg = bpy.context.evaluated_depsgraph_get()
    trees = []
    for o in [body, bpy.data.objects["Hero.male_casualsuit05"], bpy.data.objects["Hero.shoes02"]]:
        oe = o.evaluated_get(dg)
        me_ = oe.to_mesh()
        mw = oe.matrix_world
        trees.append(BVHTree.FromPolygons([mw @ v.co for v in me_.vertices], [tuple(p.vertices) for p in me_.polygons]))
        oe.to_mesh_clear()
    nx, ny = 80, int(80 * (y1 - y0) / (2 * x_half))
    xs = np.linspace(-x_half, x_half, nx)
    ys = np.linspace(y0, y1, ny)
    Zg = np.zeros((ny, nx))
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            wx, wy = BED.x + x, BED.y + y
            h = top_z + 0.012
            for t in trees:
                hit = t.ray_cast(Vector((wx, wy, top_z + max_h)), Vector((0, 0, -1)))
                if hit[0] is not None and hit[0].z < top_z + max_h:
                    h = max(h, hit[0].z + 0.02)
            edge = max(0.0, abs(x) - 0.72)
            Zg[j, i] = h - edge * 3.0
    Zg0 = Zg.copy()
    for _ in range(4):  # dilate: the cloth rests on the highest points nearby (bridges the legs)
        Zp = np.pad(Zg, 1, mode="edge")
        Zg = np.maximum.reduce([Zp[1:-1, 1:-1], Zp[:-2, 1:-1], Zp[2:, 1:-1], Zp[1:-1, :-2], Zp[1:-1, 2:]])
    for _ in range(18):  # then relax into smooth folds, never sinking into the body
        Zp = np.pad(Zg, 1, mode="edge")
        avg = (Zp[:-2, 1:-1] + Zp[2:, 1:-1] + Zp[1:-1, :-2] + Zp[1:-1, 2:]) / 4
        Zg = np.maximum(Zg0 + 0.008, 0.4 * Zg + 0.6 * avg)
    verts = [(BED.x + x, BED.y + y, Zg[j, i]) for j, y in enumerate(ys) for i, x in enumerate(xs)]
    faces = [(j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i) for j in range(ny - 1) for i in range(nx - 1)]
    me = bpy.data.meshes.new(name); me.from_pydata(verts, [], faces); me.update()
    o = bpy.data.objects.new(name, me); SET_BED.objects.link(o)
    for p in me.polygons:
        p.use_smooth = True
    sol = o.modifiers.new("thick", "SOLIDIFY"); sol.thickness = 0.02
    tx = bpy.data.textures.new(name + "Wrinkle", "CLOUDS"); tx.noise_scale = 0.12
    dsp = o.modifiers.new("wrinkle", "DISPLACE"); dsp.texture = tx; dsp.strength = 0.012
    sub = o.modifiers.new("sub", "SUBSURF"); sub.levels = 1; sub.render_levels = 2
    me.materials.append(M_BLANKET)
    return [o]


lie_f = SH["bed_cu"] + 2
sit_f = SH["morning"] + 2
BLANKET_LIE = drape_blanket("BlanketLie", "lie", lie_f, -1.0, 0.42)
BLANKET_SIT = drape_blanket("BlanketSit", "sit", sit_f, -1.0, 0.36, max_h=0.2)  # legs only, not the hands on the lap
LIE_SHOTS = {s for s, p in POSE_OF.items() if p == "lie"}
SIT_SHOTS = {s for s, p in POSE_OF.items() if p == "sit"}
BED_SHOTS = LIE_SHOTS | SIT_SHOTS
show_only_in(BLANKET_LIE, LIE_SHOTS - XRAY_SHOTS)
show_only_in(BLANKET_SIT, SIT_SHOTS)
show_only_in([o for o in SET_BED.objects if o not in BLANKET_LIE + BLANKET_SIT], BED_SHOTS - XRAY_SHOTS)

# bedroom lights: night (moon + warm lamp) and morning (sun through window)
moon = P.area_light("MoonKey", BED + Vector((-1.6, 0.4, 2.2)), BED + Vector((0, 0.6, 0.7)), 90, 1.2, (0.42, 0.58, 1.0))
lamp = bpy.data.lights.new("LampWarm", "POINT"); lamp.energy = 40; lamp.color = (1.0, 0.62, 0.32); lamp.shadow_soft_size = 0.08
lamp_o = bpy.data.objects.new("LampWarm", lamp); scene.collection.objects.link(lamp_o); lamp_o.location = BED + Vector((1.15, 0.95, 0.95))
fill_n = P.area_light("NightFill", BED + Vector((0.9, -1.4, 1.5)), BED + Vector((0, 0.7, 0.75)), 25, 2.0, (0.6, 0.7, 1.0))
sun = P.sun_light("MorningSun", (math.radians(60), 0, math.radians(-100)), 0.0, (1.0, 0.84, 0.64), angle=0.03)
win_key = P.area_light("WindowKey", BED + Vector((-1.9, 0.0, 1.7)), BED + Vector((0, 0.55, 1.05)), 0, 1.2, (1.0, 0.86, 0.66))
morn_fill = P.area_light("MorningFill", BED + Vector((1.2, -1.6, 1.8)), BED + Vector((0, 0.7, 0.9)), 0, 2.5, (1.0, 0.95, 0.9))
night = [0.0 if shot_at(f) == "morning" else 1.0 for f in FRAMES]
day = [1 - n for n in night]
bake(moon.data, "energy", [55 * n for n in night], interp="CONSTANT")
bake(lamp, "energy", [22 * n for n in night], interp="CONSTANT")
bake(fill_n.data, "energy", [6 * n for n in night], interp="CONSTANT")
bake(sun.data, "energy", [4.0 * d for d in day], interp="CONSTANT")
bake(win_key.data, "energy", [380 * d for d in day], interp="CONSTANT")
bake(morn_fill.data, "energy", [70 * d for d in day], interp="CONSTANT")
bake(M_WINDOW.node_tree, 'nodes["Emission"].inputs[0].default_value', [0.45 + 0.55 * d for d in day], index=0)
bake(M_WINDOW.node_tree, 'nodes["Emission"].inputs[0].default_value', [0.6 + 0.3 * d for d in day], index=1)
bake(M_WINDOW.node_tree, 'nodes["Emission"].inputs[0].default_value', [1.0 - 0.25 * d for d in day], index=2)
bake(M_WINDOW.node_tree, 'nodes["Emission"].inputs[1].default_value', [2.5 + 9 * d for d in day])
bake(mat_bsdf(M_LAMPSHADE).id_data, 'nodes["Principled BSDF"].inputs["Emission Strength"].default_value', [3.0 * n for n in night])

# ---------------------------------------------------------------- macro set: sandpaper on wood
SET_MACRO = new_coll("SetMacro")
M_PLANK = principled("Plank", (0.55, 0.36, 0.2), 0.6)
wnt = M_PLANK.node_tree
wv = wnt.nodes.new("ShaderNodeTexWave"); wv.wave_type = "BANDS"; wv.inputs["Scale"].default_value = 3.0
wv.inputs["Distortion"].default_value = 8.0; wv.inputs["Detail"].default_value = 6
wtc = wnt.nodes.new("ShaderNodeTexCoord"); wmap = wnt.nodes.new("ShaderNodeMapping"); wmap.inputs["Scale"].default_value = (1, 12, 1)
wnt.links.new(wtc.outputs["Object"], wmap.inputs[0]); wnt.links.new(wmap.outputs[0], wv.inputs[0])
wr = wnt.nodes.new("ShaderNodeValToRGB")
wr.color_ramp.elements[0].color = (0.32, 0.18, 0.08, 1); wr.color_ramp.elements[1].color = (0.7, 0.48, 0.28, 1)
wnt.links.new(wv.outputs["Fac"], wr.inputs[0]); wnt.links.new(wr.outputs[0], mat_bsdf(M_PLANK).inputs["Base Color"])
M_GRIT = principled("Sandpaper", (0.62, 0.42, 0.22), 0.95)
gnt = M_GRIT.node_tree
gnz = gnt.nodes.new("ShaderNodeTexNoise"); gnz.inputs["Scale"].default_value = 900; gnz.inputs["Detail"].default_value = 2
gbump = gnt.nodes.new("ShaderNodeBump"); gbump.inputs["Strength"].default_value = 0.9
gnt.links.new(gnz.outputs["Fac"], gbump.inputs["Height"]); gnt.links.new(gbump.outputs["Normal"], mat_bsdf(M_GRIT).inputs["Normal"])
M_BLOCK = principled("SandBlock", (0.85, 0.2, 0.12), 0.5)
plank = box("Plank", MACRO + Vector((0, 0, -0.02)), (0.6, 0.18, 0.04), M_PLANK, SET_MACRO, bevel=0.003)
blk = box("SandBlock", MACRO + Vector((0, 0, 0.022)), (0.11, 0.07, 0.035), M_BLOCK, SET_MACRO, bevel=0.006)
grit = box("Grit", MACRO + Vector((0, 0, 0.0035)), (0.11, 0.07, 0.003), M_GRIT, SET_MACRO, bevel=0.0005)
grit.parent = blk
grit.matrix_parent_inverse = blk.matrix_world.inverted()
sa = SH["sand"]
blk_x = [0.06 * math.sin(2 * math.pi * (f - sa) / 13) for f in FRAMES]
bake_vec(blk, "location", [MACRO + Vector((x, 0, 0.022)) for x in blk_x])
# dust: a particle emitter on the plank under the block
dust_src = box("DustSrc", MACRO + Vector((0, 0, 0.001)), (0.14, 0.06, 0.001), M_PLANK, SET_MACRO, bevel=0)
dust_src.hide_render = True
ps = dust_src.modifiers.new("dust", "PARTICLE_SYSTEM").particle_system
pset = ps.settings
pset.count = 1400; pset.frame_start = sa; pset.frame_end = SH["eye_b"]; pset.lifetime = 22
pset.normal_factor = 0.25; pset.factor_random = 0.25; pset.effector_weights.gravity = 0.15
pset.render_type = "OBJECT"; pset.particle_size = 0.0009; pset.size_random = 0.7
bpy.ops.mesh.primitive_ico_sphere_add(radius=1, subdivisions=1, location=MACRO + Vector((0, 0, -5)))
mote = link(bpy.context.active_object, SET_MACRO); mote.name = "DustMote"
mote.data.materials.append(principled("Dust", (0.85, 0.7, 0.5), 0.9))
pset.instance_object = mote
dust_src.show_instancer_for_render = False
P.area_light("MacroKey", MACRO + Vector((0.25, -0.25, 0.3)), MACRO, 6, 0.25, (1.0, 0.9, 0.78))
P.area_light("MacroRim", MACRO + Vector((-0.3, 0.3, 0.2)), MACRO, 5, 0.2, (0.7, 0.85, 1.0))
box("MacroBG", MACRO + Vector((0, 0.6, 0.2)), (2, 0.05, 1.2), principled("MacroBGMat", (0.08, 0.06, 0.05), 0.9), SET_MACRO, bevel=0)

# ---------------------------------------------------------------- CT scanner set
SET_CT = new_coll("SetCT")
M_PLASTIC = principled("CTPlastic", (0.92, 0.93, 0.95), 0.25, **{"Coat Weight": 0.6})
M_CT_LED = emission("CTLed", (0.25, 0.65, 1.0), 9.0)
bpy.ops.mesh.primitive_cylinder_add(radius=1.05, depth=0.75, vertices=96, location=CT + Vector((0, 0.35, 1.05)), rotation=(math.radians(90), 0, 0))
gantry = link(bpy.context.active_object, SET_CT); gantry.name = "Gantry"
bpy.ops.mesh.primitive_cylinder_add(radius=0.38, depth=1.0, vertices=96, location=CT + Vector((0, 0.35, 1.05)), rotation=(math.radians(90), 0, 0))
cutter = bpy.context.active_object
bo = gantry.modifiers.new("bore", "BOOLEAN"); bo.object = cutter; bo.operation = "DIFFERENCE"
cutter.hide_render = True; cutter.hide_viewport = True
bv = gantry.modifiers.new("bevel", "BEVEL"); bv.width = 0.03; bv.segments = 4; bv.limit_method = "ANGLE"
gantry.data.materials.append(M_PLASTIC)
bpy.ops.mesh.primitive_torus_add(major_radius=0.4, minor_radius=0.012, major_segments=96, location=CT + Vector((0, -0.03, 1.05)), rotation=(math.radians(90), 0, 0))
led = link(bpy.context.active_object, SET_CT); led.name = "CTLedRing"; led.data.materials.append(M_CT_LED)
box("CTTable", CT + Vector((0, -0.5, 0.88)), (0.55, 2.2, 0.08), M_PLASTIC, SET_CT, bevel=0.03)
box("CTBase", CT + Vector((0, -0.9, 0.42)), (0.45, 0.9, 0.84), M_PLASTIC, SET_CT, bevel=0.04)
box("CTFloor", CT + Vector((0, 0, -0.01)), (12, 12, 0.02), principled("CTFloorMat", (0.75, 0.78, 0.8), 0.3), SET_CT, bevel=0)
box("CTWall", CT + Vector((0, 2.5, 1.5)), (12, 0.1, 3), principled("CTWallMat", (0.62, 0.72, 0.8), 0.7), SET_CT, bevel=0)
P.area_light("CTKey", CT + Vector((1.6, -2.0, 2.6)), CT + Vector((0, 0, 1.0)), 650, 2.5, (0.9, 0.95, 1.0))
P.area_light("CTTop", CT + Vector((0, -0.5, 3.0)), CT + Vector((0, -0.5, 1.0)), 450, 3.0, (0.85, 0.92, 1.0))
# the table slides with the patient
tbl = bpy.data.objects["CTTable"]
bake_vec(tbl, "location", [CT + Vector((0, -0.5 + (r_.y - PLACE["ct"][0].y), 0.88)) for r_ in RIGLOC])

# ---------------------------------------------------------------- operating room set
SET_OR = new_coll("SetOR")
M_DRAPE = principled("Drape", (0.14, 0.42, 0.42), 0.8, **{"Sheen Weight": 0.5})
box("ORTable", OR + Vector((0, -0.4, 0.88)), (0.6, 2.2, 0.12), M_DRAPE, SET_OR, bevel=0.03)
box("ORFloor", OR + Vector((0, 0, -0.01)), (12, 12, 0.02), principled("ORFloorMat", (0.35, 0.45, 0.45), 0.3), SET_OR, bevel=0)
box("ORWall", OR + Vector((0, 2.6, 1.5)), (12, 0.1, 3), principled("ORWallMat", (0.25, 0.4, 0.42), 0.8), SET_OR, bevel=0)
bpy.ops.mesh.primitive_cylinder_add(radius=0.33, depth=0.1, vertices=64, location=OR + Vector((0.15, 0.6, 2.05)), rotation=(math.radians(-25), 0, 0))
olamp = link(bpy.context.active_object, SET_OR); olamp.name = "ORLampHousing"; olamp.data.materials.append(principled("ORHousing", (0.85, 0.87, 0.9), 0.3))
M_OR_LED = emission("ORLed", (1.0, 0.98, 0.95), 0.0)
bpy.ops.mesh.primitive_cylinder_add(radius=0.29, depth=0.01, vertices=64, location=OR + Vector((0.15, 0.585, 2.0)), rotation=(math.radians(-25), 0, 0))
oled = link(bpy.context.active_object, SET_OR); oled.name = "ORLampFace"; oled.data.materials.append(M_OR_LED)
or_spot = bpy.data.lights.new("ORSpot", "SPOT"); or_spot.spot_size = math.radians(45); or_spot.spot_blend = 0.6
or_spot.shadow_soft_size = 0.25; or_spot.color = (1.0, 0.98, 0.95)
or_spot_o = bpy.data.objects.new("ORSpot", or_spot); scene.collection.objects.link(or_spot_o)
or_spot_o.location = OR + Vector((0.15, 0.55, 1.95)); P.look_at(or_spot_o, OR + Vector((0, 0.75, 1.0)))
oa = SH["or"]
lamp_on = [ramp(f, oa + 3, oa + 7) for f in FRAMES]
bake(or_spot, "energy", [900 * v for v in lamp_on])
bake(M_OR_LED.node_tree, 'nodes["Emission"].inputs[1].default_value', [14 * v for v in lamp_on])
P.area_light("ORFill", OR + Vector((-1.5, -1.5, 2.0)), OR + Vector((0, 0.5, 1.0)), 120, 2.0, (0.7, 0.9, 0.95))
tray = box("ORTray", OR + Vector((0.75, 0.2, 1.1)), (0.45, 0.32, 0.02), principled("Steel", (0.8, 0.82, 0.85), 0.2, 1.0), SET_OR, bevel=0.005)
for i in range(4):
    box(f"Instrument{i}", OR + Vector((0.62 + 0.08 * i, 0.2, 1.12)), (0.012, 0.22, 0.006), principled(f"Steel{i}", (0.85, 0.87, 0.9), 0.15, 1.0), SET_OR, bevel=0.002)

show_only_in(list(SET_MACRO.objects), {"sand"})
show_only_in(list(SET_CT.objects), {"ct"})
show_only_in(list(SET_OR.objects), {"or"})
show_only_in([o for o in ANAT.objects if o.name not in ("brain", "cerebellum", "brainstem")], XRAY_SHOTS)
show_only_in([anat[n] for n in ("brain", "cerebellum", "brainstem") if n in anat], {"xray_head"})
show_only_in([o for o in EAR.objects if o.type != "EMPTY" and o.name != "BonePatch"], {"xray_head", "xray_dive", "ear_flow", "seal"})
show_only_in([patch], {"seal"})
# the hero is not in the macro shot
show_only_in([o for o in hero_objs if o.type == "MESH"], set(SH) - {"sand"})

# pulses: eyes -> ear (xray_head), heart -> ear (xray_heart), everything -> hole (ear_flow)
XP = new_coll("Pulses")
rig.data.pose_position = "REST"
bpy.context.view_layer.update()
EL, ER = hero_eye
ear_pt = EAR_C + Matrix.Rotation(math.radians(15), 3, "Z") @ (HOLE_LOCAL * EAR_S)
PULSES = []
for nm, pts, col, shots in [
    ("PulseEyeL", [EL + Vector((0, 0.012, 0)), EL + Vector((0.012, 0.04, 0.004)), ear_pt], (0.55, 0.9, 1.0), ("xray_head",)),
    ("PulseEyeR", [ER + Vector((0, 0.012, 0)), ER + Vector((0.02, 0.06, 0.02)), (EL + ear_pt) / 2 + Vector((0, 0.02, 0.03)), ear_pt], (0.55, 0.9, 1.0), ("xray_head",)),
    ("PulseHeart", [Vector((0.02, chest_h.y - 0.02, chest_h.z - 0.02)), Vector((0.03, neck_h.y + 0.01, neck_h.z)),
                    Vector((0.035, hero_eye[0].y + 0.11, hero_eye[0].z - 0.09)), ear_pt], (1.0, 0.2, 0.12), ("xray_heart",)),
]:
    on = min(shot_range(s)[0] for s in shots)
    off = max(shot_range(s)[1] for s in shots) + 1
    wdt = 0.00035 if nm.startswith("Flow") else (0.0012 if "Eye" in nm else 0.0018)
    o = pulse_path(nm, [tuple(p_) for p_ in pts], col, XP, on + 2, off, speed=1.2 if not nm.startswith("Flow") else 0.8, width=wdt)
    b = rig.data.bones["head"]
    o.parent, o.parent_type, o.parent_bone = rig, "BONE", "head"
    o.matrix_parent_inverse = (b.matrix_local @ Matrix.Translation((0, b.length, 0))).inverted()
    show_only_in([o], set(shots))
    PULSES.append(o)
rig.data.pose_position = "POSE"

# ---------------------------------------------------------------- world: night sky / X-ray void / interiors
world = bpy.data.worlds.new("World"); scene.world = world
world.use_nodes = True
wn = world.node_tree; wn.nodes.clear()
bg = wn.nodes.new("ShaderNodeBackground"); bg.inputs["Color"].default_value = (0.02, 0.025, 0.045, 1)
wout = wn.nodes.new("ShaderNodeOutputWorld"); wn.links.new(bg.outputs[0], wout.inputs[0])
bake(wn, 'nodes["Background"].inputs[1].default_value',
     [0.6 if shot_at(f) == "morning" else (1.0 if shot_at(f) in XRAY_SHOTS else 0.35) for f in FRAMES], interp="CONSTANT")
for i, (ln, xr, dy, ct, orr) in enumerate([(0.02, 0.003, 0.55, 0.6, 0.15), (0.025, 0.01, 0.6, 0.65, 0.2), (0.045, 0.03, 0.7, 0.7, 0.2)]):
    vals = []
    for f in FRAMES:
        s = shot_at(f)
        vals.append(xr if s in XRAY_SHOTS else dy if s == "morning" else ct if s == "ct" else orr if s == "or" else ln)
    bake(wn, 'nodes["Background"].inputs[0].default_value', vals, index=i, interp="CONSTANT")
bake(scene, '["xray"]', [1.0 if shot_at(f) in XRAY_SHOTS else 0.0 for f in FRAMES], interp="CONSTANT")
scene["shell_fade"] = 1.0  # read by the shaders' View Layer attribute lookup (falls back to scene props)
da, db_ = shot_range("xray_dive")


def shell_fade(f):
    s_ = shot_at(f)
    if s_ == "xray_dive":
        return 1.0 - ramp(f, da + 12, da + 30)
    if s_ in ("ear_flow", "seal"):
        return 0.0
    return 1.0


bake(scene, '["shell_fade"]', [shell_fade(f) for f in FRAMES])
# Fully faded shells must leave the scene, not just go transparent: every ray in the inner-ear
# close-ups would otherwise pass through a dozen invisible layers (skin, suit, skull, vessels),
# hit transparent_max_bounces and come back black (blotches in the void).
GONE = [shell_fade(f) < 0.02 and shot_at(f) in XRAY_SHOTS for f in FRAMES]
shell_objs = [o for o in hero_objs if o.type == "MESH"] + list(ANAT.objects)
keys = [1] + [f for f, g0, g1 in zip(FRAMES[1:], GONE[:-1], GONE[1:]) if g0 != g1]
for o in shell_objs:
    vis = {}
    if o.animation_data and o.animation_data.action:
        for fc in fcurves_of(o):
            if fc.data_path == "hide_render":
                vis = {int(k.co[0]): k.co[1] for k in fc.keyframe_points}
    base = (lambda f, v=vis: bool(max(((kf, val) for kf, val in v.items() if kf <= f), default=(0, o.hide_render))[1])) if vis else (lambda f: o.hide_render)
    for f in sorted(set(keys) | set(vis)):
        o.hide_render = base(f) or GONE[min(f, END) - 1]
        o.keyframe_insert("hide_render", frame=f)
print("SHELL_GONE frames", sum(GONE))
# X-ray key: a soft blue rim so the shell reads
xr_rim = P.area_light("XrayRim", Vector((0.6, 1.5, 2.2)), Vector((0, 0, 0.8)), 0, 2.0, (0.5, 0.7, 1.0))

# ---------------------------------------------------------------- cameras
CAM_COLL = new_coll("Cameras")


def cam(name, keys, lens, fstop, aim_fn, shake=0.0, up_fn=None):
    """keys: [(frame, world_pos)]; aim_fn(frame) -> world target; up_fn(frame) -> world up (default +Z)."""
    c = P.add_camera(scene, name, keys[0][1], aim_fn(keys[0][0]), lens=lens, fstop=fstop)
    c.data.clip_start = 0.002
    c.data.clip_end = 60
    link(c, CAM_COLL)
    k0, k1 = keys[0][0], keys[-1][0]
    fs = range(k0, k1 + 1)
    locs, rots, foc = [], [], []
    prev = None
    for f in fs:
        pos = keys[0][1]
        for (fa, pa), (fb, pb_) in zip(keys, keys[1:]):
            if f >= fa:
                pos = pa.lerp(pb_, ramp(f, fa, fb))
        pos = pos + Vector((wobble(f, 11, 0.7), wobble(f, 12, 0.6), wobble(f, 13, 0.5))) * shake
        tgt = aim_fn(f)
        fwd = (tgt - pos).normalized()
        up = up_fn(f) if up_fn else Vector((0, 0, 1))
        right = fwd.cross(up).normalized()
        up2 = right.cross(fwd)
        rm = Matrix((right, up2, -fwd)).transposed()
        e = rm.to_euler("XYZ", prev) if prev else rm.to_euler("XYZ")
        prev = e
        locs.append(pos); rots.append(e); foc.append((tgt - pos).length)
    bake_vec(c, "location", locs, frames=fs)
    bake_vec(c, "rotation_euler", rots, frames=fs)
    bake(c.data, "dof.focus_distance", foc, frames=fs)
    return c


# precompute the head's rest->world matrix per frame: head shots are framed in head space
# (standing frame: his front -Y, up +Z, his left +X), so they read the same in every pose
HM, CHEST = {}, {}
for f in FRAMES:
    scene.frame_set(f)
    hb_ = rig.pose.bones["head"]
    HM[f] = rig.matrix_world @ hb_.matrix @ hb_.bone.matrix_local.inverted()
    sp_ = rig.pose.bones["spine01"]
    CHEST[f] = rig.matrix_world @ sp_.matrix @ sp_.bone.matrix_local.inverted() @ Vector((0.02, chest_h.y - 0.01, chest_h.z))
FACE_R = Vector((0, hero_eye[0].y + 0.02, hero_eye[0].z - 0.02))


def inflow_rings():
    """Inner-ear close-up: sound rings from the body shrinking into the hole (alternating sources)."""
    fa, fb = shot_range("ear_flow")
    mats = [M_RING_HEART, M_RING_SCRATCH, M_RING_LOUD]
    life = 16
    for k, t0 in enumerate(range(fa + 6, fb - 6, 6)):
        bpy.ops.mesh.primitive_torus_add(major_radius=1.0, minor_radius=0.05, major_segments=96, minor_segments=6)
        o = bpy.context.active_object
        o.name = f"Inflow_{k}"
        o.data.materials.append(mats[k % 3])
        link(o, FX)
        fs = range(t0, min(END, t0 + life) + 1)
        sc, col, loc, rot = [], [], [], []
        for f in fs:
            x = min(max((f - t0) / life, 0), 1)
            rr = 0.012 * (1 - x) ** 1.3 + 0.0008
            m3 = HM[f].to_3x3()
            n = (m3 @ Vector((1, 0, 0))).normalized()
            sc.append((rr, rr, rr))
            col.append((min(1.0, 3 * x) * (1 - x) ** 0.5, 0, 0, 1))
            loc.append(HM[f] @ ear_pt + n * 0.0015)
            rot.append(n.to_track_quat("Z", "Y").to_euler())
        bake_vec(o, "scale", sc, frames=fs)
        bake_vec(o, "color", col, n=4, frames=fs)
        bake_vec(o, "location", loc, frames=fs)
        bake_vec(o, "rotation_euler", rot, frames=fs)
        for f, hv in ((1, True), (t0, False), (min(END, t0 + life + 1, fb + 1), True)):
            o.hide_render = hv
            o.keyframe_insert("hide_render", frame=f)
EYE_R = hero_eye[0]
EAR_R = ear_pt


def hs(base, d=(0, 0, 0)):
    """Head-space point: frame -> world position of rest point base + offset d."""
    return lambda f: HM[f] @ (base + Vector(d))


def hcam(name, keys, lens, fstop, aim, shake=0.0):
    """keys: [(frame, base, offset)] all in head space; aim: head-space function."""
    return cam(name, [(f, HM[f] @ (bs + Vector(d))) for f, bs, d in keys], lens, fstop, aim, shake,
               up_fn=lambda f: (HM[f].to_3x3() @ Vector((0, 0, 1))).normalized())


inflow_rings()
cams = {}
a, b_ = shot_range("bed_cu")
cams["bed_cu"] = hcam("CamBedCU", [(a, FACE_R, (0.2, -0.36, 0.1)), (b_, FACE_R, (0.15, -0.27, 0.075))], 45, 2.8,
                      hs(FACE_R, (0.015, 0.0, 0.0)), shake=0.0015)
a, b_ = shot_range("xray_head")
cams["xray_head"] = hcam("CamXHead", [(a, FACE_R, (0.24, -0.3, 0.08)), (b_, FACE_R, (0.19, -0.23, 0.06))], 45, 5.6,
                         hs(FACE_R, (0.03, 0.04, 0.0)), shake=0.001)
a, b_ = shot_range("eye_a")
cams["eye_a"] = hcam("CamEyeA", [(a, EYE_R, (0.012, -0.1, 0.012)), (b_, EYE_R, (0.01, -0.085, 0.01))], 85, 11,
                     hs(EYE_R, (0.0, -0.012, 0.0)), shake=0.0003)
a, b_ = shot_range("sand")
cams["sand"] = cam("CamSand", [(a, MACRO + Vector((0.16, -0.2, 0.09))), (b_, MACRO + Vector((0.12, -0.17, 0.075)))], 60, 8,
                   lambda f: MACRO + Vector((0, 0, 0.012)), shake=0.0008)
a, b_ = shot_range("eye_b")
cams["eye_b"] = hcam("CamEyeB", [(a, EYE_R, (-0.014, -0.095, 0.014)), (b_, EYE_R, (-0.012, -0.08, 0.012))], 85, 11,
                     hs(EYE_R, (0.0, -0.012, 0.0)), shake=0.0003)
a, b_ = shot_range("xray_heart")
cams["xray_heart"] = cam("CamXHeart", [(a, CHEST[a] + Vector((0.55, -0.15, 0.55))), (b_, CHEST[b_] + Vector((0.42, -0.1, 0.62)))], 35, 8,
                         lambda f: CHEST[f] + Vector((0, 0.2, 0.0)), shake=0.0015)
a, b_ = shot_range("chew")
cams["chew"] = hcam("CamChew", [(a, FACE_R, (0.34, -0.2, 0.02)), (b_, FACE_R, (0.28, -0.15, 0.015))], 50, 2.8,
                    hs(FACE_R, (0.045, 0.045, -0.02)), shake=0.0015)
a, b_ = shot_range("ct")
cams["ct"] = cam("CamCT", [(a, CT + Vector((1.6, -2.3, 1.25))), (b_, CT + Vector((1.25, -1.8, 1.2)))], 32, 8,
                 lambda f: CT + Vector((0, -0.1, 1.0)), shake=0.001)
a, b_ = shot_range("xray_dive")
cams["xray_dive"] = hcam("CamXDive", [(a, EAR_R, (0.3, -0.06, 0.05)), (a + 24, EAR_R, (0.075, -0.015, 0.012)),
                                      (b_, EAR_R, (0.03, -0.006, 0.006))], 40, 8, hs(EAR_R), shake=0.0003)
a, b_ = shot_range("ear_flow")
cams["ear_flow"] = hcam("CamEarFlow", [(a, EAR_C, (0.042, 0.004, 0.01)), (a + 40, EAR_C, (0.052, 0.002, 0.014)),
                                       (b_, EAR_C, (0.1, -0.03, 0.035))], 40, 11, hs(EAR_C, (0, 0, 0.002)), shake=0.0003)
a, b_ = shot_range("or")
cams["or"] = hcam("CamOR", [(a, EAR_R, (0.42, -0.2, 0.16)), (b_, EAR_R, (0.3, -0.14, 0.11))], 35, 4,
                  hs((EAR_R + FACE_R) / 2), shake=0.001)
a, b_ = shot_range("seal")
cams["seal"] = hcam("CamSeal", [(a, EAR_R, (0.046, 0.004, 0.022)), (b_, EAR_R, (0.038, 0.003, 0.018))], 50, 11,
                    hs(EAR_R, (0, 0, -0.002)), shake=0.0002)
a, b_ = shot_range("morning")
cams["morning"] = hcam("CamMorning", [(a, FACE_R, (0.3, -0.55, 0.04)), (b_, FACE_R, (0.19, -0.36, 0.03))], 45, 2.8,
                       hs(FACE_R, (0.02, 0.0, -0.03)), shake=0.0012)
for k in ("xray_dive", "ear_flow", "seal"):  # millimetre-scale shots: everything sharp
    cams[k].data.dof.use_dof = False
# the inner ear needs its own light once the skull is gone
ear_key = bpy.data.lights.new("EarKey", "POINT"); ear_key.energy = 0.0; ear_key.shadow_soft_size = 0.01
ear_key_o = bpy.data.objects.new("EarKey", ear_key); scene.collection.objects.link(ear_key_o)
bake_vec(ear_key_o, "location", [HM[f] @ (EAR_R + Vector((0.02, -0.03, 0.03))) for f in FRAMES])
bake(ear_key, "energy", [0.35 if shot_at(f) in ("xray_dive", "ear_flow", "seal") else 0.0 for f in FRAMES], interp="CONSTANT")
for k in ORDER:
    scene.timeline_markers.new(k, frame=SH[k]).camera = cams[k]
scene.camera = cams["bed_cu"]

scene.sequence_editor_create()
seq = scene.sequence_editor
strips = seq.strips if hasattr(seq, "strips") else seq.sequences
strips.new_sound("VO", os.path.join(HERE, "vo.wav"), channel=1, frame_start=1)
scene.frame_set(1)
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("SAVED", OUT, "END", END, "SHOTS", {k: shot_range(k) for k in ORDER})

for f in STILLS:
    scene.frame_set(f)
    scene.camera = cams[shot_at(f)]
    scene.render.filepath = OUT.replace(".blend", f"_f{f:04d}.png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", scene.render.filepath, shot_at(f))
