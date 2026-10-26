"""Short: "Her brain was leaking out of her nose, and doctors blamed allergies" (Nebraska Medicine, 2018).

Run (daily_render.ps1):  blender -b --python scene.py -- <ROOT>/blend/<slug>.blend [vo=..] [beats=..]
                          [stills=1,200] [pct=100] [samples=96] [device=gpu|cpu] [root=..] [char=..]
With no vo=/beats= the narration is found from the output path: <ROOT>/audio/<slug>_beats.json
(align_narration.py) or <slug>_vo.json (tts.py), and <slug>_vo_final.wav or <slug>_vo.wav.

The script opens the hero .blend itself. It prefers blend/char_heroine.blend (a female lead for this
story); if that is missing it tries to build it once with scripts/build_character.py +
scripts/preset_heroine.json in a child Blender process, and falls back to blend/char_hero.blend.

One continuous timeline cut to the narration's 10 beats:
  home (living room), car (2013 crash), lab (fluid test) and X-ray anatomy (brain, CSF, skull-base
  hole, nasal airway, drip, bacteria, endoscopic fat-graft repair), toggled per shot.
Cue fractions marked SYNC must match mix.py.
"""
import json
import math
import os
import random
import subprocess
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

# ---------------------------------------------------------------- arguments + paths
argv = sys.argv[sys.argv.index("--") + 1:]
OUT = os.path.abspath(argv[0])
opts = dict(kv.split("=", 1) for kv in argv[1:] if "=" in kv)
known = {"vo", "beats", "stills", "pct", "samples", "device", "root", "char", "build_heroine"}
if set(opts) - known or any("=" not in a for a in argv[1:]):
    raise SystemExit(f"usage: <out.blend> [{'=.. ['.join(sorted(known))}=..]; got {argv[1:]}")
SLUG = os.path.splitext(os.path.basename(OUT))[0]
ROOT = opts.get("root") or os.path.dirname(os.path.dirname(OUT))
SCRIPTS = os.path.join(ROOT, "scripts")
AUDIO = os.path.join(ROOT, "audio")
STILLS = [int(f) for f in opts["stills"].split(",")] if opts.get("stills") else []
PCT = int(opts.get("pct", 100))
SAMPLES = int(opts.get("samples", 96))
DEVICE = opts.get("device", "gpu").lower()


def first_existing(*paths):
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None


BEATS_JSON = opts.get("beats") or first_existing(os.path.join(AUDIO, f"{SLUG}_beats.json"),
                                                 os.path.join(AUDIO, f"{SLUG}_vo.json"))
VO_WAV = opts.get("vo") or first_existing(os.path.join(AUDIO, f"{SLUG}_vo_final.wav"),
                                          os.path.join(AUDIO, f"{SLUG}_vo.wav"))
if not BEATS_JSON or not os.path.exists(BEATS_JSON):
    raise SystemExit(f"Error: no narration timing json found for {SLUG} in {AUDIO}")
print(f"ARGS out={OUT} beats={BEATS_JSON} vo={VO_WAV} stills={STILLS} pct={PCT} samples={SAMPLES} device={DEVICE}")
if PCT != 100:
    print(f"!! WARNING: resolution_percentage={PCT}, NOT a full-resolution render")

# ---------------------------------------------------------------- character
HERO_BLEND = os.path.join(ROOT, "blend", "char_hero.blend")
HEROINE_BLEND = os.path.join(ROOT, "blend", "char_heroine.blend")
CHAR = opts.get("char")
if not CHAR:
    preset = os.path.join(SCRIPTS, "preset_heroine.json")
    builder = os.path.join(SCRIPTS, "build_character.py")
    if (not os.path.exists(HEROINE_BLEND) and opts.get("build_heroine", "1") == "1" and bpy.app.binary_path
            and os.path.exists(preset) and os.path.exists(builder)):
        print("Building female lead (one-time):", HEROINE_BLEND)
        try:
            r = subprocess.run([bpy.app.binary_path, "-b", "--python", builder, "--", HEROINE_BLEND, preset],
                               capture_output=True, text=True, timeout=1200)
            tail = (r.stdout + r.stderr).strip().splitlines()[-6:]
            print("HEROINE build exit", r.returncode, *tail, sep="\n  ")
        except Exception as exc:  # never let the optional build kill the night's render
            print("WARN heroine build failed:", exc)
    CHAR = HEROINE_BLEND if os.path.exists(HEROINE_BLEND) else HERO_BLEND
print("CHAR", CHAR)
bpy.ops.wm.open_mainfile(filepath=CHAR)

sys.path.append(SCRIPTS)
try:
    import pipeline as P  # noqa: E402
except Exception as exc:
    print("WARN pipeline.py not importable:", exc)
    P = None

FPS = 30
META = json.load(open(BEATS_JSON, encoding="utf-8"))


def fr(t):
    return int(round(t * FPS)) + 1


BEAT = [fr(b["start"]) for b in META["beats"]]
assert len(BEAT) == 10, f"expected 10 narration beats, got {len(BEAT)}"
END = fr(META["duration"]) + 36
BEAT_END = BEAT[1:] + [END]
FRAMES = range(1, END + 1)


def at_beat(i, frac):
    return int(round(BEAT[i] + frac * (BEAT_END[i] - BEAT[i])))


# SYNC with mix.py
IMPACT_F, MUCUS_F, CRACK_F, SEAL_F = 0.62, 0.55, 0.40, 0.72
H1, H2 = at_beat(0, 0.30), at_beat(0, 0.66)          # hook: nose ECU -> X-ray -> home mid
IMP = at_beat(1, IMPACT_F)
MUCUS = at_beat(3, MUCUS_F)
CRACK = at_beat(5, CRACK_F)
SEAL = at_beat(8, SEAL_F)
random.seed(23)

scene = bpy.context.scene
scene.frame_start, scene.frame_end = 1, END
scene.render.fps = FPS


def setup_render_fallback():
    scene.render.engine = "CYCLES"
    c = scene.cycles
    c.samples = SAMPLES
    c.use_adaptive_sampling = True
    c.use_denoising = True
    try:
        c.denoiser = "OPENIMAGEDENOISE"
    except TypeError:
        pass
    c.max_bounces, c.diffuse_bounces, c.glossy_bounces, c.transmission_bounces = 6, 2, 2, 4
    scene.render.resolution_x, scene.render.resolution_y = 1080, 1920
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.5
    scene.render.image_settings.file_format = "PNG"


if DEVICE == "gpu" and P is not None:
    try:
        P.setup_render(scene, samples=SAMPLES)
    except Exception as exc:
        print("WARN setup_render failed, using CPU-safe settings:", exc)
        setup_render_fallback()
else:
    setup_render_fallback()
    scene.cycles.device = "CPU"
scene.render.resolution_percentage = PCT
scene.render.use_persistent_data = True
scene.cycles.transparent_max_bounces = 32
scene.view_settings.exposure = -0.2
bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"

MX = "mixamorig:"
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
# everything that came with the character file gets the X-ray look (hair may not be parented to the rig)
hero_objs = [o for o in bpy.data.objects if o.type in ("MESH", "CURVES", "CURVE") and o is not rig]
body = bpy.data.objects.get("Hero.body") or max(
    (o for o in hero_objs if o.type == "MESH"), key=lambda o: len(o.data.vertices))
face_meshes = [o for o in hero_objs if o.type == "MESH" and o.data.shape_keys]
print("HERO_OBJS", sorted(o.name for o in hero_objs))
for pb in rig.pose.bones:
    pb.rotation_mode = "QUATERNION"
    pb.rotation_quaternion = (1, 0, 0, 0)
print("RIG", rig.name, "BODY", body.name, "FACE_MESHES", [o.name for o in face_meshes])

# skin look (same tuning as the sneeze short), only if the MPFB skin group is present
try:
    grp = next(n for n in body.material_slots[0].material.node_tree.nodes if n.type == "GROUP")
    for name, val in {"Roughness": 0.48, "Pore strength": 0.35, "SSS strength": 0.32,
                      "SSS radius scale": 0.08, "Contrast": 0.08, "colorMixInStrength": 0.09}.items():
        if name in grp.inputs:
            grp.inputs[name].default_value = val
except Exception as exc:
    print("WARN skin tweak skipped:", exc)


# ---------------------------------------------------------------- generic helpers
def fcurves_of(idb):
    act = idb.animation_data.action
    if hasattr(act, "fcurves"):
        return act.fcurves
    from bpy_extras import anim_utils
    return anim_utils.action_get_channelbag_for_slot(act, idb.animation_data.action_slot).fcurves


def bake(idb, path, values, index=None, frames=FRAMES, interp="LINEAR"):
    """One key per frame straight into an fcurve (fast). index=None for scalar properties."""
    frames = list(frames)
    before = set()
    if idb.animation_data and idb.animation_data.action:
        before = {(c.data_path, c.array_index) for c in fcurves_of(idb)}
    if index is None:
        idb.keyframe_insert(data_path=path, frame=frames[0])
    else:
        idb.keyframe_insert(data_path=path, index=index, frame=frames[0])
    fcs = fcurves_of(idb)
    fc = fcs.find(path, index=index or 0)
    if fc is None:   # Blender may store a by-name socket path by index; take the curve just created
        fc = next(c for c in fcs if (c.data_path, c.array_index) not in before)
    fc.keyframe_points.clear()
    fc.keyframe_points.add(len(values))
    fc.keyframe_points.foreach_set("co", [c for f, v in zip(frames, values) for c in (f, float(v))])
    fc.keyframe_points.foreach_set("interpolation", [{"CONSTANT": 0, "LINEAR": 1}[interp]] * len(values))
    fc.update()
    return fc


def bake_vec(idb, path, vecs, n=3, interp="LINEAR"):
    for i in range(n):
        bake(idb, path, [v[i] for v in vecs], index=i, interp=interp)


def ramp(f, a, b):
    if b == a:
        return 1.0 if f >= b else 0.0
    x = min(max((f - a) / (b - a), 0.0), 1.0)
    return x * x * (3 - 2 * x)


def env(f, a, b, c, d):
    return ramp(f, a, b) * (1 - ramp(f, c, d))


def spike(f, at, rise=3, decay=10):
    x = f - at
    if x < -rise:
        return 0.0
    if x < 0:
        return ramp(x, -rise, 0)
    return math.exp(-x / decay)


def wobble(f, seed, speed=1.0, freqs=(0.23, 0.51, 0.87)):
    t = f / FPS * speed
    return sum(math.sin(t * q * 2 * math.pi + seed * (i + 1.7)) / (i + 1) for i, q in enumerate(freqs))


def new_coll(name):
    c = bpy.data.collections.new(name)
    scene.collection.children.link(c)
    return c


def move_to(o, coll):
    for c in list(o.users_collection):
        c.objects.unlink(o)
    coll.objects.link(o)
    return o


def principled(name, color, rough, **kw):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    for k, v in kw.items():
        b.inputs[k].default_value = v
    return m


def add_noise_bump(m, scale=60, strength=0.15, detail=6):
    nt = m.node_tree
    tex = nt.nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = scale
    tex.inputs["Detail"].default_value = detail
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    nt.links.new(tex.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])
    return m


def edge_glow(name, color, strength=2.5, core=0.0, blend=0.35, value_name=None):
    """X-ray style shell: bright at grazing angles, see-through face-on. Optional Value node
    (value_name) multiplies the strength so it can be animated."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    N, Lk = nt.nodes, nt.links
    N.clear()
    out = N.new("ShaderNodeOutputMaterial")
    lw = N.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = blend
    mr = N.new("ShaderNodeMapRange")
    mr.inputs[1].default_value = 0.1
    mr.inputs[2].default_value = 0.95
    mr.inputs[3].default_value = core
    Lk.new(lw.outputs["Facing"], mr.inputs[0])
    em = N.new("ShaderNodeEmission")
    em.name = "Glow"
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = strength
    if value_name:
        v = N.new("ShaderNodeValue")
        v.name = value_name
        v.outputs[0].default_value = 1.0
        mul = N.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = strength
        Lk.new(v.outputs[0], mul.inputs[0])
        Lk.new(mul.outputs[0], em.inputs["Strength"])
    tr = N.new("ShaderNodeBsdfTransparent")
    mx = N.new("ShaderNodeMixShader")
    Lk.new(mr.outputs[0], mx.inputs[0])
    Lk.new(tr.outputs[0], mx.inputs[1])
    Lk.new(em.outputs[0], mx.inputs[2])
    Lk.new(mx.outputs[0], out.inputs["Surface"])
    return m


def glow(name, color, strength=4.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.name = "Glow"
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    return m


def glass_mat(name, tint=(0.95, 0.97, 1.0), rough=0.02):
    return principled(name, tint, rough, **{"Transmission Weight": 1.0, "IOR": 1.45})


def box(name, loc, size, mat, coll, bevel=0.01, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        bv = o.modifiers.new("Bevel", "BEVEL")
        bv.width = bevel
        bv.segments = 3
        bpy.ops.object.shade_smooth()
    o.data.materials.append(mat)
    return move_to(o, coll)


def cyl(name, loc, r, depth, mat, coll, rot=(0, 0, 0), verts=32, smooth=True):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    if smooth:
        bpy.ops.object.shade_smooth()
    o.data.materials.append(mat)
    return move_to(o, coll)


def blob(name, loc, radius, mat, coll, scale=(1, 1, 1), noise_scale=0.6, strength=0.25, subdiv=3):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdiv, radius=radius, location=loc)
    o = bpy.context.active_object
    o.name = name
    o.scale = scale
    if strength:
        tex = bpy.data.textures.new(name + "Tex", "CLOUDS")
        tex.noise_scale = noise_scale
        dp = o.modifiers.new("Disp", "DISPLACE")
        dp.texture = tex
        dp.strength = radius * strength
    bpy.ops.object.shade_smooth()
    o.data.materials.append(mat)
    return move_to(o, coll)


def text(name, body_txt, loc, size, mat, coll, rot=(math.pi / 2, 0, 0), extrude=0.0):
    cu = bpy.data.curves.new(name, type="FONT")
    cu.body = body_txt
    cu.size = size
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.extrude = extrude
    o = bpy.data.objects.new(name, cu)
    coll.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    o.data.materials.append(mat)
    return o


def area_light(name, loc, target, energy, size, color=(1, 1, 1), coll=None):
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.size = size
    data.color = color
    o = bpy.data.objects.new(name, data)
    (coll or scene.collection).objects.link(o)
    o.location = loc
    look_at(o, target)
    return o


def look_at(obj, target):
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def visible_during(objs, ranges):
    """Key hide_render so objs render only inside the (a, b) frame ranges (inclusive)."""
    inside = lambda f: any(a <= f <= b for a, b in ranges)  # noqa: E731
    keys = sorted({1} | {a for a, b in ranges} | {b + 1 for a, b in ranges})
    for o in objs:
        for f in keys:
            o.hide_render = not inside(f)
            o.keyframe_insert("hide_render", frame=f)
        o.hide_render = not inside(1)


def key_visibility(objs, fn):
    """Key hide_render only where fn(frame) -> bool (visible) changes."""
    for o in objs:
        prev = None
        for f in FRAMES:
            v = bool(fn(f))
            if v != prev:
                o.hide_render = not v
                o.keyframe_insert("hide_render", frame=f)
                prev = v
        o.hide_render = not bool(fn(1))


# ---------------------------------------------------------------- measure the hero (rest pose)
def bone_world_head(name):
    return rig.matrix_world @ rig.data.bones[MX + name].head_local


def parent_rest(obj, bone):
    """Parent to a bone so the object sits at its current world spot when the rig is in REST pose.
    Afterwards obj.matrix_basis is expressed in rest-pose world coordinates."""
    b = rig.data.bones[MX + bone]
    obj.parent, obj.parent_type, obj.parent_bone = rig, "BONE", MX + bone
    rest = rig.matrix_world @ b.matrix_local @ Matrix.Translation((0, b.length, 0))
    obj.matrix_parent_inverse = rest.inverted()


rig.data.pose_position = "REST"
bpy.context.view_layer.update()
deps = bpy.context.evaluated_depsgraph_get()
em = body.evaluated_get(deps).to_mesh()
verts = [body.matrix_world @ v.co for v in em.vertices]
body.evaluated_get(deps).to_mesh_clear()
HEAD0 = bone_world_head("Head")
head_vs = [v for v in verts if v.z > HEAD0.z - 0.06 and abs(v.x - HEAD0.x) < 0.13]
TOP = max(v.z for v in head_vs)
mid = [v for v in head_vs if abs(v.x - HEAD0.x) < 0.015]
nose_band = [v for v in mid if TOP - 0.21 < v.z < TOP - 0.09] or mid
NOSE = min(nose_band, key=lambda v: v.y).copy()
BACK_Y = max(v.y for v in mid if v.z > TOP - 0.16)
X0 = HEAD0.x
print("HEAD top", round(TOP, 3), "nose", tuple(round(c, 3) for c in NOSE), "back_y", round(BACK_Y, 3))

# anatomy anchors (rest pose, metres)
head_len = BACK_Y - NOSE.y
BR_RY = min(0.085, max(0.06, head_len * 0.36))
BR_RX, BR_RZ = BR_RY * 0.80, BR_RY * 0.66
BR_C = Vector((X0, NOSE.y + head_len * 0.56, TOP - 0.03 - BR_RZ))
HOLE = Vector((X0, NOSE.y + head_len * 0.30, NOSE.z + 0.045))
if BR_C.z - BR_RZ * 0.9 < HOLE.z + 0.004:     # brain must sit on the skull base above the hole
    BR_C.z = HOLE.z + 0.004 + BR_RZ * 0.9
NOSTRIL = Vector((X0 + 0.006, NOSE.y + 0.014, NOSE.z - 0.02))
PATH = [HOLE + Vector((0, 0.002, 0.006)), HOLE,
        Vector((X0, HOLE.y - 0.010, HOLE.z - 0.022)),
        Vector((X0 + 0.003, NOSE.y + 0.032, NOSE.z - 0.008)),
        NOSTRIL]


def path_point(u):
    """Catmull-Rom through PATH, u in 0..1 (0 = just above the hole, 1 = nostril)."""
    pts = [PATH[0]] + PATH + [PATH[-1]]
    n = len(PATH) - 1
    u = min(max(u, 0.0), 1.0) * n
    i = min(int(u), n - 1)
    t = u - i
    p0, p1, p2, p3 = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
    return 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                  + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t)


def path_tangent(u):
    a, b = path_point(max(0, u - 0.02)), path_point(min(1, u + 0.02))
    return (b - a).normalized()


rig.data.pose_position = "POSE"

# ---------------------------------------------------------------- seated pose basics
REST = {pb.name: pb.bone.matrix_local.to_quaternion() for pb in rig.pose.bones}
X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))


def has(name):
    return MX + name in rig.pose.bones


def bq(name, axis, deg):
    r = REST[MX + name]
    return r.inverted() @ Quaternion(axis, math.radians(deg)) @ r


def bone_dir(name):
    b = rig.data.bones[MX + name]
    return (b.tail_local - b.head_local).normalized()


def aim_chain(chain):
    out, parent_delta = {}, Quaternion()
    for name, target in chain:
        c = bone_dir(name).rotation_difference(parent_delta.inverted() @ Vector(target).normalized())
        r = REST[MX + name]
        out[name] = r.inverted() @ c @ r
        parent_delta = parent_delta @ c
    return out


LEGS = {}
for side, sx in (("Left", 1), ("Right", -1)):
    LEGS.update(aim_chain([(f"{side}UpLeg", (0.14 * sx, -1, -0.06)), (f"{side}Leg", (0.05 * sx, -0.35, -1)),
                           (f"{side}Foot", (0.03 * sx, -1, -0.7))]))
for name, q in LEGS.items():
    rig.pose.bones[MX + name].rotation_quaternion = q
bpy.context.view_layer.update()


def pose_world(name, tail=False):
    pb = rig.pose.bones[MX + name]
    return rig.matrix_world @ (pb.tail if tail else pb.head)


HIPS = pose_world("Hips")
KNEE_L, KNEE_R = pose_world("LeftLeg"), pose_world("RightLeg")
ANKLE = pose_world("LeftFoot")
TOE = pose_world("LeftFoot", tail=True)
FLOOR_Z = min(ANKLE.z - 0.07, TOE.z - 0.02)
SEAT_Z = HIPS.z - 0.08
THIGH_L = HIPS.lerp(KNEE_L, 0.62) + Vector((0.03, 0, 0.07))
THIGH_R = HIPS.lerp(KNEE_R, 0.62) + Vector((-0.03, 0, 0.07))
print("SEAT", round(SEAT_Z, 3), "FLOOR", round(FLOOR_Z, 3), "HIPS", tuple(round(c, 3) for c in HIPS))

# ---------------------------------------------------------------- sets
HOME, CAR, LAB, ANAT = new_coll("Home"), new_coll("Car"), new_coll("Lab"), new_coll("Anatomy")
HX, HY = HIPS.x, HIPS.y

# home: living room
floor_mat = add_noise_bump(principled("WoodFloor", (0.28, 0.17, 0.09), 0.45), scale=8, strength=0.15)
wall_mat = add_noise_bump(principled("Wall", (0.78, 0.70, 0.60), 0.9), scale=40, strength=0.05)
couch_mat = add_noise_bump(principled("CouchFabric", (0.10, 0.30, 0.33), 0.85, **{"Sheen Weight": 0.3}),
                           scale=300, strength=0.2)
wood_mat = principled("TableWood", (0.20, 0.11, 0.05), 0.35)
paper_mat = principled("Tissue", (0.92, 0.92, 0.9), 0.8, **{"Subsurface Weight": 0.2})
box_mat = principled("TissueBox", (0.75, 0.25, 0.35), 0.5)
win_mat = glow("WindowLight", (0.85, 0.92, 1.0), 3.0)
cal_mat = principled("CalendarPaper", (0.95, 0.95, 0.93), 0.7)
ink_mat = principled("Ink", (0.75, 0.05, 0.05), 0.5)
dark_ink = principled("DarkInk", (0.03, 0.03, 0.04), 0.5)

box("Floor", (HX, HY - 1.0, FLOOR_Z - 0.02), (8, 8, 0.04), floor_mat, HOME, bevel=0)
box("BackWall", (HX, HY + 0.95, FLOOR_Z + 1.5), (8, 0.1, 3.0), wall_mat, HOME, bevel=0)
box("SideWall", (HX - 2.2, HY - 1.0, FLOOR_Z + 1.5), (0.1, 8, 3.0), wall_mat, HOME, bevel=0)
box("Window", (HX - 2.14, HY - 0.4, FLOOR_Z + 1.55), (0.02, 1.3, 1.1), win_mat, HOME, bevel=0)
box("CouchSeat", (HX, HY + 0.05, SEAT_Z - 0.11), (1.9, 0.75, 0.22), couch_mat, HOME, bevel=0.06)
box("CouchBase", (HX, HY + 0.05, (SEAT_Z - 0.22 + FLOOR_Z) / 2), (1.9, 0.72, SEAT_Z - 0.22 - FLOOR_Z),
    couch_mat, HOME, bevel=0.03)
box("CouchBack", (HX, HY + 0.40, SEAT_Z + 0.30), (1.9, 0.22, 0.75), couch_mat, HOME, bevel=0.08,
    rot=(math.radians(-10), 0, 0))
for sx in (-1, 1):
    box(f"CouchArm{sx}", (HX + 0.95 * sx, HY + 0.05, SEAT_Z + 0.08), (0.2, 0.75, 0.42), couch_mat, HOME, bevel=0.07)
TABLE = Vector((HX + 1.35, HY - 0.05, SEAT_Z + 0.08))
box("SideTable", (TABLE.x, TABLE.y, (TABLE.z + FLOOR_Z) / 2), (0.5, 0.5, TABLE.z - FLOOR_Z), wood_mat, HOME, bevel=0.01)
box("TissueBox", (TABLE.x - 0.1, TABLE.y + 0.1, TABLE.z + 0.06), (0.24, 0.13, 0.12), box_mat, HOME)
blob("TissueTop", (TABLE.x - 0.1, TABLE.y + 0.1, TABLE.z + 0.14), 0.04, paper_mat, HOME, scale=(1, 0.6, 1.2))
# measuring glass (beat 7) on a coffee table in front of the couch + "1/2 PINT" line
CT = Vector((HX + 0.2, HY - 0.8, SEAT_Z - 0.14))
box("CoffeeTable", CT + Vector((0, 0, -0.02)), (0.9, 0.45, 0.04), wood_mat, HOME, bevel=0.01)
for lx in (-0.4, 0.4):
    for ly in (-0.18, 0.18):
        box(f"CTLeg{lx}{ly}", (CT.x + lx, CT.y + ly, (CT.z - 0.04 + FLOOR_Z) / 2), (0.04, 0.04, CT.z - 0.04 - FLOOR_Z),
            wood_mat, HOME, bevel=0)
GLASS = Vector((CT.x + 0.12, CT.y - 0.05, CT.z))
cyl("MeasureGlass", GLASS + Vector((0, 0, 0.085)), 0.045, 0.17, glass_mat("Glass"), HOME, verts=48)
liquid_mat = principled("CSFLiquid", (0.75, 0.9, 1.0), 0.02, **{"Transmission Weight": 0.9,
                                                                "Emission Color": (0.4, 0.75, 1.0, 1),
                                                                "Emission Strength": 0.4})
liquid = cyl("GlassLiquid", GLASS + Vector((0, 0, 0.002)), 0.041, 0.002, liquid_mat, HOME, verts=48)
liquid.data.transform(Matrix.Translation((0, 0, 0.001)))   # origin at the bottom so scale-z fills upward
liquid.location = GLASS + Vector((0, 0, 0.003))
LIQ_FULL = 0.11 / 0.002
line_mat = glow("PintLine", (1.0, 0.25, 0.15), 6.0)
cyl("PintLine", GLASS + Vector((0, 0, 0.113)), 0.0465, 0.003, line_mat, HOME, verts=48)
pint_label = text("PintLabel", "1/2 PINT", GLASS + Vector((0, -0.06, 0.135)), 0.028, line_mat, HOME)
# tissue pile (grows during "years")
pile = []
for i in range(14):
    a = random.uniform(0, 6.28)
    p = Vector((TABLE.x + math.cos(a) * random.uniform(0, 0.16), TABLE.y + math.sin(a) * random.uniform(0, 0.12) - 0.02,
                TABLE.z + 0.03 + 0.012 * (i // 5)))
    if i >= 9:
        p = Vector((HX + random.uniform(0.5, 1.1), HY - random.uniform(0.35, 0.75), FLOOR_Z + 0.025))
    pile.append(blob(f"UsedTissue{i}", p, 0.035, paper_mat, HOME, scale=(1, 1, 0.7), strength=0.5))
# calendar on the back wall: year flips 2013 -> 2018 during "years"
CAL = Vector((HX + 0.75, HY + 0.88, SEAT_Z + 1.05))
box("Calendar", CAL, (0.42, 0.01, 0.5), cal_mat, HOME, bevel=0)
box("CalendarBar", CAL + Vector((0, -0.006, 0.19)), (0.42, 0.005, 0.1), ink_mat, HOME, bevel=0)
years = {y: text(f"Year{y}", str(y), CAL + Vector((0, -0.012, -0.03)), 0.11, dark_ink, HOME) for y in range(2013, 2019)}

# car (crash): seat, dashboard (placed after the lurch is measured), pillars, night streaks
seat_mat = add_noise_bump(principled("CarSeat", (0.05, 0.05, 0.06), 0.9), scale=400, strength=0.25)
dash_mat = add_noise_bump(principled("DashPlastic", (0.035, 0.035, 0.04), 0.55), scale=220, strength=0.08)
box("CarSeat", (HX, HY + 0.03, SEAT_Z - 0.08), (0.55, 0.6, 0.16), seat_mat, CAR, bevel=0.05)
box("CarSeatBack", (HX, HY + 0.36, SEAT_Z + 0.35), (0.55, 0.14, 0.8), seat_mat, CAR, bevel=0.05,
    rot=(math.radians(-12), 0, 0))
box("CarHeadrest", (HX, HY + 0.45, SEAT_Z + 0.85), (0.28, 0.1, 0.2), seat_mat, CAR, bevel=0.04)
box("CarFloor", (HX, HY - 0.4, FLOOR_Z - 0.02), (2.2, 2.4, 0.04), seat_mat, CAR, bevel=0)
box("CarRoof", (HX, HY - 0.1, TOP + 0.22), (2.0, 1.8, 0.04), seat_mat, CAR, bevel=0)
streak_mats = [glow("StreakA", (1.0, 0.55, 0.2), 12), glow("StreakB", (0.8, 0.9, 1.0), 10)]
streak_root = bpy.data.objects.new("StreakRoot", None)
CAR.objects.link(streak_root)
for i in range(26):
    o = box(f"Streak{i}", (HX - 2.0 - random.uniform(0, 3), HY + random.uniform(-14, 14), FLOOR_Z + random.uniform(0.6, 2.6)),
            (0.03, random.uniform(0.6, 2.2), 0.03), random.choice(streak_mats), CAR, bevel=0)
    o.parent = streak_root
bake(streak_root, "location", [((f * 0.55) % 28.0) - 14 for f in FRAMES], index=1)

# lab (fluid test), far away from the other sets
LABP = Vector((40.0, 0.0, 1.0))
counter_mat = principled("Counter", (0.85, 0.87, 0.9), 0.25)
lightbox_mat = glow("LightBox", (0.85, 0.93, 1.0), 1.1)
cap_mat = principled("VialCap", (0.05, 0.25, 0.8), 0.35)
box("LabCounter", LABP + Vector((0, 0.05, -0.06)), (1.2, 0.6, 0.04), counter_mat, LAB, bevel=0.005)
box("LabLightbox", LABP + Vector((0, 0.32, 0.2)), (1.0, 0.02, 0.6), lightbox_mat, LAB, bevel=0)
vial_root = bpy.data.objects.new("VialRoot", None)
LAB.objects.link(vial_root)
vial_root.location = LABP
for o in (cyl("Vial", (0, 0, 0.035), 0.012, 0.07, glass_mat("VialGlass"), LAB, verts=48),
          cyl("VialFluid", (0, 0, 0.022), 0.0105, 0.044, liquid_mat, LAB, verts=48),
          cyl("VialCap", (0, 0, 0.074), 0.013, 0.012, cap_mat, LAB, verts=48)):
    o.parent = vial_root
strip_mat = principled("TestPad", (0.95, 0.95, 0.85), 0.6, **{"Emission Color": (0.1, 1.0, 0.35, 1),
                                                               "Emission Strength": 0.0})
strip_root = bpy.data.objects.new("StripRoot", None)
LAB.objects.link(strip_root)
strip_root.location = LABP + Vector((0.035, -0.005, 0.0))
box("TestStrip", (0, 0, 0.03), (0.006, 0.0015, 0.06), principled("StripPlastic", (0.95, 0.95, 0.95), 0.4), LAB,
    bevel=0).parent = strip_root
box("TestPad", (0, -0.001, 0.012), (0.0062, 0.0016, 0.01), strip_mat, LAB, bevel=0).parent = strip_root
vial_lift = [LABP.z - 0.09 * (1 - ramp(f, BEAT[3], BEAT[3] + 14)) for f in FRAMES]
bake(vial_root, "location", vial_lift, index=2)
bake(vial_root, "rotation_euler", [0.25 * math.sin(f / 40) for f in FRAMES], index=2)
bake(strip_root, "location", vial_lift, index=2)
bake(strip_mat.node_tree, 'nodes["Principled BSDF"].inputs[0].default_value',
     [0.95 - 0.85 * ramp(f, MUCUS - 4, MUCUS + 6) for f in FRAMES], index=0)
bake(strip_mat.node_tree, 'nodes["Principled BSDF"].inputs[0].default_value',
     [0.95 - 0.1 * ramp(f, MUCUS - 4, MUCUS + 6) for f in FRAMES], index=1)
bake(strip_mat.node_tree, 'nodes["Principled BSDF"].inputs[0].default_value',
     [0.85 - 0.6 * ramp(f, MUCUS - 4, MUCUS + 6) for f in FRAMES], index=2)
bake(strip_mat.node_tree, f'nodes["Principled BSDF"].inputs["Emission Strength"].default_value',
     [3.0 * ramp(f, MUCUS - 4, MUCUS + 6) for f in FRAMES])
not_mucus = text("NotMucus", "NOT MUCUS", LABP + Vector((0.012, -0.03, 0.098)), 0.012,
                 glow("NotMucusInk", (1.0, 0.2, 0.15), 8.0), LAB)
visible_during([not_mucus], [(MUCUS, BEAT[4] - 1)])

# ---------------------------------------------------------------- X-ray look on every hero material
def xray_group():
    ng = bpy.data.node_groups.new("XRayShell", "ShaderNodeTree")
    ng.interface.new_socket("Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
    N, Lk = ng.nodes, ng.links
    o = N.new("NodeGroupOutput")
    lw = N.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.35
    rmp = N.new("ShaderNodeMapRange")
    rmp.inputs[1].default_value = 0.15
    rmp.inputs[2].default_value = 0.9
    Lk.new(lw.outputs["Facing"], rmp.inputs[0])
    pw = N.new("ShaderNodeMath")
    pw.operation = "POWER"
    pw.inputs[1].default_value = 1.6
    Lk.new(rmp.outputs[0], pw.inputs[0])
    emn = N.new("ShaderNodeEmission")
    emn.inputs["Color"].default_value = (0.32, 0.72, 1.0, 1)
    emn.inputs["Strength"].default_value = 2.0
    tr = N.new("ShaderNodeBsdfTransparent")
    mx = N.new("ShaderNodeMixShader")
    k = N.new("ShaderNodeMath")
    k.operation = "MULTIPLY"
    k.inputs[1].default_value = 0.5
    Lk.new(pw.outputs[0], k.inputs[0])
    Lk.new(k.outputs[0], mx.inputs[0])
    Lk.new(tr.outputs[0], mx.inputs[1])
    Lk.new(emn.outputs[0], mx.inputs[2])
    Lk.new(mx.outputs[0], o.inputs[0])
    return ng


def scene_driver(socket_owner, path, scale=1.0, offset=0.0):
    fc = socket_owner.driver_add(path)
    d = fc.driver
    d.type = "SCRIPTED"
    v = d.variables.new()
    v.name = "x"
    v.type = "SINGLE_PROP"
    v.targets[0].id_type = "SCENE"
    v.targets[0].id = scene
    v.targets[0].data_path = '["xray"]'
    d.expression = f"x*{scale}+{offset}"
    return fc


scene["xray"] = 0.0
XG = xray_group()
done = set()
for o in hero_objs:
    for slot in getattr(o, "material_slots", []):
        m = slot.material
        if not m or m.name in done or not m.use_nodes:
            continue
        done.add(m.name)
        nt = m.node_tree
        outn = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None)
        if outn is None or not outn.inputs["Surface"].links:
            continue
        src = outn.inputs["Surface"].links[0].from_socket
        g = nt.nodes.new("ShaderNodeGroup")
        g.node_tree = XG
        mx = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(src, mx.inputs[1])
        nt.links.new(g.outputs[0], mx.inputs[2])
        nt.links.new(mx.outputs[0], outn.inputs["Surface"])
        scene_driver(mx.inputs[0], "default_value")
print("XRAY_MATS", len(done))

# ---------------------------------------------------------------- anatomy (built in rest pose, ridden on the Head bone)
ANAT_OBJS = []
skull_mat = edge_glow("SkullXRay", (0.95, 0.93, 0.85), strength=1.1, core=0.0, blend=0.12)
csf_mat = edge_glow("CSFGlow", (0.25, 0.75, 1.0), strength=2.6, core=0.03, blend=0.2, value_name="Pulse")
# alarm: CSF shell shifts from blue to red while the bacteria get in
csf_nt = csf_mat.node_tree
alarm = csf_nt.nodes.new("ShaderNodeValue")
alarm.name = "Alarm"
alarm.outputs[0].default_value = 0.0
cmix = csf_nt.nodes.new("ShaderNodeMix")
cmix.data_type = "RGBA"
cmix.inputs["A"].default_value = (0.25, 0.75, 1.0, 1)
cmix.inputs["B"].default_value = (1.0, 0.12, 0.08, 1)
csf_nt.links.new(alarm.outputs[0], cmix.inputs["Factor"])
csf_nt.links.new(cmix.outputs["Result"], csf_nt.nodes["Glow"].inputs["Color"])
brain_mat = principled("Brain", (0.86, 0.55, 0.58), 0.45, **{"Subsurface Weight": 0.4,
                                                              "Emission Color": (0.9, 0.5, 0.55, 1),
                                                              "Emission Strength": 0.35})
add_noise_bump(brain_mat, scale=90, strength=0.9, detail=4)
plate_mat = principled("SkullBase", (0.92, 0.88, 0.78), 0.5, **{"Emission Color": (0.9, 0.87, 0.8, 1),
                                                                 "Emission Strength": 0.5})
airway_mat = edge_glow("Airway", (1.0, 0.55, 0.6), strength=2.0, core=0.08, blend=0.3)
ring_mat = glow("HoleRing", (1.0, 0.15, 0.08), 0.0)
ring_nt = ring_mat.node_tree
bake(ring_nt, 'nodes["Glow"].inputs[1].default_value',
     [8.0 * max(spike(f, IMP + 2, 1, 30), env(f, CRACK - 2, CRACK + 3, 99998, 99999)) for f in FRAMES])
bake_vec(ring_nt, 'nodes["Glow"].inputs[0].default_value',
         [(1.0, 0.15, 0.08, 1) if f < SEAL else (0.2, 1.0, 0.35, 1) for f in FRAMES], n=4, interp="CONSTANT")

for name, scale_k, mat in (("Skull", 1.16, skull_mat), ("CSF", 1.07, csf_mat)):
    o = blob(name, BR_C, 1.0, mat, ANAT, scale=(BR_RX * scale_k, BR_RY * scale_k, BR_RZ * scale_k * 1.08),
             strength=0.0, subdiv=5)
    ANAT_OBJS.append(o)
for sx in (-1, 1):   # two hemispheres with a midline groove
    o = blob(f"Brain{sx}", BR_C + Vector((sx * BR_RX * 0.49, 0, 0)), 1.0, brain_mat, ANAT,
             scale=(BR_RX * 0.53, BR_RY * 0.98, BR_RZ * 0.97), noise_scale=0.18, strength=0.05, subdiv=5)
    ANAT_OBJS.append(o)
ANAT_OBJS.append(blob("Cerebellum", BR_C + Vector((0, BR_RY * 0.62, -BR_RZ * 0.72)), 1.0, brain_mat, ANAT,
                      scale=(BR_RX * 0.62, BR_RY * 0.34, BR_RZ * 0.38), noise_scale=0.12, strength=0.05, subdiv=4))
ANAT_OBJS.append(cyl("BrainStem", BR_C + Vector((0, BR_RY * 0.3, -BR_RZ * 1.15)), BR_RX * 0.22, BR_RZ * 1.2,
                     brain_mat, ANAT, rot=(math.radians(-12), 0, 0)))
plate = cyl("SkullBasePlate", HOLE, 0.026, 0.003, plate_mat, ANAT, rot=(math.radians(-8), 0, 0))
ANAT_OBJS.append(plate)
ANAT_OBJS.append(cyl("Hole", HOLE + Vector((0, 0, 0.0002)), 0.0042, 0.0036, glow("HoleDark", (0.0, 0.0, 0.0), 0.0),
                     ANAT, rot=(math.radians(-8), 0, 0)))
bpy.ops.mesh.primitive_torus_add(major_radius=0.0052, minor_radius=0.0009, location=HOLE,
                                 rotation=(math.radians(-8), 0, 0))
ring = bpy.context.active_object
ring.name = "HoleRing"
ring.data.materials.append(ring_mat)
move_to(ring, ANAT)
ANAT_OBJS.append(ring)
cracks = []
for k, a in enumerate((20, 140, 250)):
    d = Vector((math.cos(math.radians(a)), math.sin(math.radians(a)), 0))
    c = cyl(f"Crack{k}", HOLE + d * 0.009, 0.0006, 0.010, ring_mat, ANAT,
            rot=(0, math.radians(90), math.radians(a)), verts=8)
    cracks.append(c)
    ANAT_OBJS.append(c)
# nasal airway tube along the leak path
cu = bpy.data.curves.new("AirwayCurve", "CURVE")
cu.dimensions = "3D"
cu.bevel_depth = 0.0055
cu.bevel_resolution = 4
sp = cu.splines.new("POLY")
pts = [path_point(i / 24) for i in range(25)] + [NOSTRIL + Vector((0, -0.003, -0.006))]
sp.points.add(len(pts) - 1)
for i, p in enumerate(pts):
    sp.points[i].co = (*p, 1)
airway = bpy.data.objects.new("Airway", cu)
ANAT.objects.link(airway)
airway.data.materials.append(airway_mat)
ANAT_OBJS.append(airway)
# labels (face +X, the side the X-ray cameras look from)
side_rot = (math.pi / 2, 0, math.pi / 2)
lab_csf = text("LabelCSF", "CSF", BR_C + Vector((BR_RX * 1.3, -BR_RY * 0.55, BR_RZ * 0.2)), 0.02,
               glow("LabelBlue", (0.5, 0.85, 1.0), 6), ANAT, rot=side_rot)
lab_hole = text("LabelHole", "HOLE", HOLE + Vector((0.012, -0.008, -0.018)), 0.009,
                glow("LabelRed", (1.0, 0.25, 0.15), 8), ANAT, rot=side_rot)
lab_men = text("LabelMeningitis", "MENINGITIS\nRISK", path_point(0.5) + Vector((0.015, 0.02, -0.012)), 0.006,
               glow("LabelRed2", (1.0, 0.2, 0.12), 8), ANAT, rot=side_rot)
lab_seal = text("LabelSealed", "SEALED", HOLE + Vector((0.012, -0.008, -0.02)), 0.010,
                glow("LabelGreen", (0.25, 1.0, 0.4), 8), ANAT, rot=side_rot)
for o in (lab_csf, lab_hole, lab_men, lab_seal):
    ANAT_OBJS.append(o)

# particles: CSF drips (hole -> nostril -> fall), bacteria (nostril -> hole -> brain), scope + fat graft
drip_mat = glow("DripGlow", (0.35, 0.8, 1.0), 7.0)
bact_mat = principled("Bacteria", (0.2, 0.9, 0.2), 0.4, **{"Emission Color": (0.25, 1.0, 0.3, 1),
                                                           "Emission Strength": 2.5})
fat_mat = principled("FatGraft", (1.0, 0.82, 0.3), 0.45, **{"Subsurface Weight": 0.5,
                                                            "Emission Color": (1.0, 0.8, 0.3, 1),
                                                            "Emission Strength": 0.8})
scope_mat = principled("Endoscope", (0.15, 0.15, 0.17), 0.25, **{"Metallic": 1.0})
tip_mat = glow("ScopeLight", (1.0, 1.0, 0.95), 25)

bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1.0, location=(0, 0, -50))
proto = bpy.context.active_object
bpy.ops.object.shade_smooth()
drip_mesh = proto.data.copy()
drip_mesh.materials.append(drip_mat)
bpy.data.objects.remove(proto)

LEAK_RANGES = [(H1, H2 - 1), (IMP + 2, IMP + 9), (BEAT[4], SEAL + 4)]   # drips flow in these windows
particles = []   # (obj, locs, scales) in rest-pose world space


def make_drips():
    TRAVEL, FALL = 42, 16
    t0 = 1
    while t0 < END:
        if any(a - TRAVEL <= t0 <= b for a, b in LEAK_RANGES) and t0 < SEAL - 8:
            o = bpy.data.objects.new("Drip", drip_mesh)
            ANAT.objects.link(o)
            born = t0 + random.uniform(0, 2)
            r = random.uniform(0.0011, 0.0019)
            jit = Vector((random.uniform(-0.0008, 0.0008), random.uniform(-0.0008, 0.0008), 0))
            locs, scales = [], []
            for f in FRAMES:
                age = f - born
                if age < 0 or age > TRAVEL + FALL:
                    locs.append(PATH[0])
                    scales.append(0.0)
                elif age <= TRAVEL:
                    locs.append(path_point(age / TRAVEL) + jit)
                    scales.append(r * min(1.0, age / 4))
                else:
                    tf = (age - TRAVEL) / FPS
                    locs.append(NOSTRIL + jit + Vector((0, -0.01 * tf, -4.9 * tf * tf)))
                    scales.append(r * (1 - (age - TRAVEL) / FALL))
            particles.append((o, locs, scales))
        t0 += 4


def make_bacteria(n=34):
    for i in range(n):
        o = blob(f"Bacterium{i}", (0, 0, -50), 1.0, bact_mat, ANAT, scale=(1, 1, 1), noise_scale=0.5, strength=0.35,
                 subdiv=2)
        born = BEAT[7] + random.uniform(0, (BEAT[8] - BEAT[7]) * 0.45)
        dur = random.uniform(40, 60)
        spread = Vector((random.uniform(-1, 1) * BR_RX * 0.7, random.uniform(-0.6, 0.6) * BR_RY, 0))
        r = random.uniform(0.0016, 0.0028)
        seed = random.uniform(0, 10)
        locs, scales = [], []
        for f in FRAMES:
            age = f - born
            if age < 0 or f >= BEAT[8]:
                locs.append(NOSTRIL)
                scales.append(0.0)
                continue
            u = min(1.0, age / dur)
            if u < 1.0:
                p = path_point(1 - u)                       # crawl up from the nostril to the hole
            else:
                k = min(1.0, (age - dur) / 30)              # then fan out under the brain
                p = PATH[0] + (spread + Vector((0, 0, 0.004))) * k
            p = p + Vector((0.0012 * math.sin(f * 0.7 + seed), 0.0012 * math.cos(f * 0.9 + seed), 0))
            locs.append(p)
            scales.append(r * min(1.0, age / 6) * (1 + 0.12 * math.sin(f * 1.3 + seed)))
        particles.append((o, locs, scales))


make_drips()
make_bacteria()

scope = cyl("Endoscope", (0, 0, 0), 0.0032, 0.09, scope_mat, ANAT, verts=16)
scope.data.transform(Matrix.Translation((0, 0, -0.045)))     # origin at the tip, body trails behind (-Z)
scope_tip = blob("ScopeTip", (0, 0, 0), 0.0022, tip_mat, ANAT, strength=0.0, subdiv=2)
scope_tip.parent = scope
fat = blob("FatGraft", (0, 0, 0), 1.0, fat_mat, ANAT, scale=(1, 1, 0.75), noise_scale=0.5, strength=0.3, subdiv=3)
S_IN, S_OUT = BEAT[8] + 6, SEAL - 2


def scope_u(f):
    """Scope tip position along the path: 1 = below the nostril ... 0.06 = at the hole."""
    go = ramp(f, S_IN, S_OUT)
    back = ramp(f, SEAL + 8, SEAL + 30)
    return 1.15 - 1.09 * go + 1.1 * back


scope_loc, scope_rot, scope_scale, fat_loc, fat_scale = [], [], [], [], []
for f in FRAMES:
    u = scope_u(f)
    tip = path_point(u) if u <= 1 else NOSTRIL + (NOSTRIL - path_point(0.95)).normalized() * 0.03 * (u - 1) / 0.15
    tan = path_tangent(min(u, 0.99))
    q = Vector((0, 0, 1)).rotation_difference(-tan)           # local +Z points up the airway
    on = BEAT[8] <= f < BEAT[9]
    scope_loc.append(tip)
    scope_rot.append(q)
    scope_scale.append(1.0 if on else 0.0)
    if f < SEAL:
        fat_loc.append(tip + (-tan) * 0.004)
        fat_scale.append(0.0036 if on else 0.0)
    else:
        k = ramp(f, SEAL, SEAL + 6)
        fat_loc.append(HOLE + Vector((0, 0, -0.0012 * k)))
        fat_scale.append(0.0036 + 0.0024 * k)
for o in ANAT.objects:
    if o.parent is None:
        parent_rest(o, "Head")          # matrix_basis is now rest-pose world space (see parent_rest)
for o, locs, scales in particles:
    bake_vec(o, "location", locs)
    bake_vec(o, "scale", [(s, s, s) for s in scales])
bake_vec(scope, "location", scope_loc)
scope.rotation_mode = "QUATERNION"
bake_vec(scope, "rotation_quaternion", scope_rot, n=4)
bake_vec(scope, "scale", [(s, s, s) for s in scope_scale])
bake_vec(fat, "location", fat_loc)
bake_vec(fat, "scale", [(s, s, s * 0.75) for s in fat_scale])
for c in cracks:
    k = [max(ramp(f, IMP + 1, IMP + 4), ramp(f, CRACK - 3, CRACK + 6)) for f in FRAMES]
    bake_vec(c, "scale", [(1, 1, max(0.001, v)) for v in k])
bake(csf_nt, 'nodes["Pulse"].outputs[0].default_value',
     [0.75 + 0.25 * math.sin(f / FPS * 2 * math.pi / 1.1) + 0.6 * env(f, BEAT[4], BEAT[4] + 10, BEAT[5] - 6, BEAT[5])
      for f in FRAMES])
bake(csf_nt, 'nodes["Alarm"].outputs[0].default_value',
     [ramp(f, at_beat(7, 0.55), at_beat(7, 0.85)) * (1 - ramp(f, BEAT[8], BEAT[8] + 6)) for f in FRAMES])
print("ANATOMY objects", len(ANAT.objects), "particles", len(particles))

# ---------------------------------------------------------------- IK arms + props on the hands
for side in ("Left", "Right"):
    t = bpy.data.objects.new(f"IK_{side}", None)
    scene.collection.objects.link(t)
    c = rig.pose.bones[MX + side + "ForeArm"].constraints.new("IK")
    c.name = "IK"
    c.target = t
    c.chain_count = 2
    c.use_tail = True
    pole = bpy.data.objects.new(f"Pole_{side}", None)
    scene.collection.objects.link(pole)
    sx = 1 if side == "Left" else -1
    pole.location = (HX + 0.6 * sx, HY + 0.35, HIPS.z + 0.15)
    c.pole_target = pole
    c.pole_angle = math.radians(-90)


def bone_empty(name, bone, world_pos):
    e = bpy.data.objects.new(name, None)
    scene.collection.objects.link(e)
    e.location = world_pos
    parent_rest(e, bone)
    return e


nose_anchor = bone_empty("NoseAnchor", "Head", Vector((X0 - 0.03, NOSE.y - 0.075, NOSE.z - 0.055)))
hand_aim = bone_empty("HandAimPt", "Head", Vector((X0, NOSE.y + 0.01, NOSE.z + 0.02)))
dt = rig.pose.bones[MX + "RightHand"].constraints.new("DAMPED_TRACK")
dt.name = "DT"
dt.target = hand_aim
dt.track_axis = "TRACK_Y"
dt.influence = 0.0
nostril_pt = bone_empty("NostrilPt", "Head", NOSTRIL + Vector((0, -0.002, -0.004)))
face_aim = bone_empty("FaceAim", "Head", Vector((X0, NOSE.y + 0.06, NOSE.z - 0.02)))
eye_focus = bone_empty("EyeFocus", "Head", Vector((X0 + 0.03, NOSE.y + 0.02, NOSE.z + 0.04)))
head_ctr = bone_empty("HeadCenter", "Head", BR_C + Vector((0, -0.03, -0.02)))
hole_aim = bone_empty("HoleAim", "Head", HOLE.copy())
path_mid = bone_empty("PathMid", "Head", path_point(0.5))
hand_r = rig.data.bones[MX + "RightHand"]
palm_rest = rig.matrix_world @ (hand_r.tail_local + Vector((0, 0, -0.03)))
tissue = blob("HandTissue", palm_rest, 0.04, paper_mat, scene.collection, scale=(1, 1, 0.8), strength=0.5)
parent_rest(tissue, "RightHand")

# ---------------------------------------------------------------- shots
# (start frame, camera name, set) -- set in home/car/lab/xray; cameras are created below
SHOTS = [(1, "CamNose", "home"), (H1, "CamXSide", "xray"), (H2, "CamHomeMid", "home"),
         (BEAT[1], "CamCar", "car"), (IMP + 2, "CamXCrash", "xray"), (IMP + 9, "CamCarFront", "car"),
         (BEAT[2], "CamHomeWide", "home"), (BEAT[3], "CamLab", "lab"), (BEAT[4], "CamXOrbit", "xray"),
         (BEAT[5], "CamXHole", "xray"), (BEAT[6], "CamHomeGlass", "home"), (BEAT[7], "CamXBact", "xray"),
         (BEAT[8], "CamXSurg", "xray"), (BEAT[9], "CamHomeFront", "home")]


def shot_at(f):
    return max((s for s in SHOTS if s[0] <= f), key=lambda s: s[0])


def set_ranges(name):
    out = []
    for i, (a, _, s) in enumerate(SHOTS):
        b = SHOTS[i + 1][0] - 1 if i + 1 < len(SHOTS) else END
        if s == name:
            out.append((a, b))
    return out


# ---------------------------------------------------------------- performance
FINGERS = [b.name[len(MX):] for b in rig.data.bones if "Hand" in b.name and b.name[-1] in "123"]
BLINKS = [f for f in range(20, END, 1) if (f * 7919) % 97 == 0][:40]
WIPES = [(H2 + 2, BEAT[1] - 3)] + [(at_beat(2, a), at_beat(2, a) + 16) for a in (0.08, 0.42, 0.72)] \
    + [(at_beat(6, 0.70), BEAT[7] - 2)]
SNIFFS = [at_beat(0, 0.12), at_beat(0, 0.9), at_beat(2, 0.3), at_beat(2, 0.62), at_beat(6, 0.2)]


def curves(f):
    c = {}
    c["wipe"] = max((env(f, a, a + 7, b - 7, b) for a, b in WIPES), default=0.0)
    c["sniff"] = max((spike(f, s, 3, 6) for s in SNIFFS), default=0.0)
    c["worry"] = max(env(f, 1, 2, BEAT[1] - 4, BEAT[1]), env(f, BEAT[2], BEAT[2] + 6, BEAT[3] - 6, BEAT[3]),
                     env(f, BEAT[6], BEAT[6] + 6, BEAT[7] - 6, BEAT[7]))
    c["lean"] = env(f, at_beat(6, 0.15), at_beat(6, 0.45), BEAT[7] - 8, BEAT[7] + 4)
    c["whip"] = spike(f, IMP - 5, 3, 3)
    c["lurch"] = env(f, IMP - 4, IMP, IMP + 3, IMP + 16)
    c["daze"] = env(f, IMP + 8, IMP + 16, BEAT[2] - 6, BEAT[2])
    c["wince"] = max(spike(f, IMP, 2, 14), spike(f, CRACK, 2, 10) * 0.0)
    c["relief"] = ramp(f, BEAT[9] + 4, BEAT[9] + 20)
    c["nod"] = spike(f, at_beat(9, 0.8), 4, 8)
    c["blink"] = max((env(f, b - 1, b + 1, b + 3, b + 6) for b in BLINKS), default=0.0)
    c["tired"] = env(f, BEAT[2], BEAT[2] + 8, BEAT[3] - 8, BEAT[3])
    return c


ROT, SHAPES = {}, {}
for f in FRAMES:
    c = curves(f)
    breath = math.sin(f / FPS * 2 * math.pi / 3.6)
    fwd = 26 * c["lurch"] - 9 * c["whip"] + 10 * c["lean"] + 6 * c["wipe"]
    poses = {
        "Hips": [(Z, 0.5 * wobble(f, 1))],
        "Spine": [(X, -9 + 0.4 * breath + 0.45 * fwd), (Z, 0.8 * wobble(f, 2))],
        "Spine1": [(X, -3 + 0.6 * breath + 0.35 * fwd - 2 * c["relief"])],
        "Spine2": [(X, 2 + 0.6 * breath + 0.2 * fwd)],
        "Neck": [(X, 4 + 0.25 * fwd + 4 * c["tired"] + 3 * c["nod"]), (Z, 1.5 * wobble(f, 4))],
        "Head": [(X, 1 + 0.35 * fwd + 7 * c["daze"] - 4 * c["sniff"] + 6 * c["tired"] + 6 * c["nod"]
                  + 1.0 * wobble(f, 7, 0.6)),
                 (Z, 2.0 * wobble(f, 5, 0.5) - 6 * c["daze"]),
                 (Y, 1.2 * wobble(f, 6) + 9 * c["daze"] + 4 * c["worry"])],
        "LeftShoulder": [(Y, 3 * c["sniff"] + 4 * c["lurch"])],
        "RightShoulder": [(Y, -3 * c["sniff"] - 4 * c["lurch"])],
    }
    for name, rots in poses.items():
        if not has(name):
            continue
        q = Quaternion()
        for axis, deg in rots:
            q = q @ bq(name, axis, deg)
        ROT.setdefault(name, []).append(q)
    for name, q in LEGS.items():
        ROT.setdefault(name, []).append(q)
    for name in FINGERS:
        joint = int(name[-1])
        curl = {1: 25, 2: 35, 3: 25}[joint] if "Thumb" not in name else {1: 8, 2: 15, 3: 10}[joint]
        if name.startswith("Right"):
            curl += 30 * c["wipe"]
        ROT.setdefault(name, []).append(Quaternion((1, 0, 0), math.radians(curl)))
    s = {}
    for side in ("Left", "Right"):
        s[f"eyeBlink{side}"] = min(1, c["blink"] + 0.9 * c["wince"] + 0.35 * c["daze"] + 0.25 * c["tired"]
                                   + 0.2 * c["relief"])
        s[f"eyeSquint{side}"] = min(1, 0.5 * c["sniff"] + 0.5 * c["wince"] + 0.35 * c["relief"])
        s[f"eyeWide{side}"] = 0.5 * c["whip"]
        s[f"browDown{side}"] = min(1, 0.6 * c["wince"] + 0.25 * c["sniff"])
        s[f"noseSneer{side}"] = min(1, 0.8 * c["sniff"] + 0.4 * c["wipe"])
        s[f"mouthFrown{side}"] = 0.35 * c["worry"] + 0.2 * c["tired"]
        s[f"mouthStretch{side}"] = 0.4 * c["wince"]
        s[f"mouthSmile{side}"] = 0.65 * c["relief"]
        s[f"cheekSquint{side}"] = 0.4 * c["relief"]
    s["browInnerUp"] = min(1, 0.6 * c["worry"] + 0.4 * c["tired"] + 0.3 * c["daze"])
    s["jawOpen"] = 0.25 * c["whip"] + 0.2 * c["daze"] + 0.15 * c["wince"]
    for k, v in s.items():
        SHAPES.setdefault(k, []).append(max(0.0, min(1.0, v)))

for name, qs in ROT.items():
    for i in range(1, len(qs)):
        if qs[i].dot(qs[i - 1]) < 0:
            qs[i] = -qs[i]
    path = f'pose.bones["{MX}{name}"].rotation_quaternion'
    for i in range(4):
        bake(rig, path, [q[i] for q in qs], index=i)
for o in face_meshes:
    kb = o.data.shape_keys.key_blocks
    for name, vals in SHAPES.items():
        if name in kb:
            bake(o.data.shape_keys, f'key_blocks["{name}"].value', vals)

# per-frame evaluation: IK targets, tissue, the real (home) nose drip, the dashboard spot
ikL, ikR = bpy.data.objects["IK_Left"], bpy.data.objects["IK_Right"]
locL, locR, nostril_w, tis_scale = [], [], [], []
crash_nose = None
for f in FRAMES:
    scene.frame_set(f)
    c = curves(f)
    nose = nose_anchor.matrix_world.translation.copy()
    w = c["wipe"]
    arc = 4 * w * (1 - w)
    locR.append(THIGH_R.lerp(nose, w) + Vector((0.02, -0.12, 0.05)) * arc)
    locL.append(THIGH_L + Vector((0, -0.12 * c["lurch"], 0.04 * c["lurch"])))
    nostril_w.append(nostril_pt.matrix_world.translation.copy())
    tis_scale.append(1.0 if w > 0.05 else 0.0)
    if f == IMP:
        crash_nose = nostril_w[-1].copy()
bake_vec(ikL, "location", locL)
bake_vec(ikR, "location", locR)
bake(rig, f'pose.bones["{MX}RightHand"].constraints["DT"].influence', [min(1.0, 1.4 * curves(f)["wipe"]) for f in FRAMES])
bake_vec(tissue, "scale", [(s, s, s * 0.8) for s in tis_scale], interp="CONSTANT")

# visible water drop at the nostril in home shots: swells, falls, repeats (faster when leaning)
drop_mat = principled("Droplet", (0.9, 0.95, 1.0), 0.02, **{"Transmission Weight": 1.0, "IOR": 1.33})
drop = blob("NoseDrop", (0, 0, 0), 1.0, drop_mat, HOME, strength=0.0, subdiv=3)
d_loc, d_scale = [], []
phase, fall_from, falling = 0.0, None, 0
for f in FRAMES:
    c = curves(f)
    rate = (1 / 34) * (1 + 1.5 * c["lean"])
    if falling:
        falling += 1
        t = falling / FPS
        d_loc.append(fall_from + Vector((0, -0.02 * t, -4.9 * t * t)))
        d_scale.append(0.0035)
        if falling > 12:
            falling, phase = 0, 0.0
        continue
    phase += rate
    n = nostril_w[f - 1]
    hidden = c["wipe"] > 0.05 or f >= BEAT[9]
    if phase >= 1.0 and not hidden:
        falling, fall_from = 1, n.copy()
    d_loc.append(n + Vector((0, 0, -0.002 * min(phase, 1))))
    d_scale.append(0.0 if hidden else 0.0012 + 0.0024 * min(phase, 1))
bake_vec(drop, "location", d_loc)
bake_vec(drop, "scale", [(s, s, s * 1.2) for s in d_scale])

# dashboard sits where the face lands at the impact frame
cn = crash_nose or NOSTRIL
box("Dashboard", (HX, cn.y - 0.2, cn.z - 0.11), (0.8, 0.4, 0.18), dash_mat, CAR, bevel=0.04)
box("DashLower", (HX, cn.y - 0.32, (cn.z - 0.2 + FLOOR_Z) / 2), (0.8, 0.3, cn.z - 0.2 - FLOOR_Z), dash_mat, CAR, bevel=0.03)
for sx in (-1, 1):
    box(f"APillar{sx}", (HX + 0.42 * sx, cn.y - 0.3, cn.z + 0.3), (0.06, 0.06, 0.75), dash_mat, CAR, bevel=0.02,
        rot=(math.radians(-35), 0, 0))
gauge = glow("DashGlow", (1.0, 0.55, 0.2), 4.0)
box("Gauges", (HX, cn.y - 0.13, cn.z - 0.015), (0.3, 0.02, 0.04), gauge, CAR, bevel=0)

# calendar flip, tissue pile, measuring glass, window day/night
flip = [2013 + min(5, int(6 * ramp(f, BEAT[2] + 4, BEAT[3] - 6))) if f >= BEAT[2] else 2018 for f in FRAMES]
for i, o in enumerate(pile):
    t_in = BEAT[2] + (i + 1) * (BEAT[3] - BEAT[2] - 8) / (len(pile) + 1)
    bake_vec(o, "scale", [(k, k, k * 0.7) for k in (ramp(f, t_in, t_in + 4) for f in FRAMES)])
bake(liquid, "scale", [1 + (LIQ_FULL - 1) * ramp(f, BEAT[6] + 4, at_beat(6, 0.82)) for f in FRAMES], index=2)

# ---------------------------------------------------------------- lights + world, keyed per set
world = bpy.data.worlds.new("ShortWorld")
scene.world = world
world.use_nodes = True
wnt = world.node_tree
wnt.nodes.clear()
wbg = wnt.nodes.new("ShaderNodeBackground")
wbg.name = "Background"
wout = wnt.nodes.new("ShaderNodeOutputWorld")
wnt.links.new(wbg.outputs[0], wout.inputs[0])
WORLD_COL = {"home": ((0.55, 0.48, 0.40), 0.35), "car": ((0.01, 0.015, 0.04), 1.0),
             "lab": ((0.6, 0.7, 0.8), 0.12), "xray": ((0.004, 0.012, 0.03), 1.0)}
cols = [WORLD_COL[shot_at(f)[2]] for f in FRAMES]
bake_vec(wnt, 'nodes["Background"].inputs[0].default_value', [(*c, 1) for c, _ in cols], n=4, interp="CONSTANT")
bake(wnt, 'nodes["Background"].inputs[1].default_value', [s for _, s in cols], interp="CONSTANT")

F0 = Vector((X0, NOSE.y, NOSE.z))
LIGHTS = {
    "home": [area_light("HomeKey", F0 + Vector((1.2, -1.4, 0.9)), F0, 260, 1.2, (1.0, 0.93, 0.84)),
             area_light("HomeFill", F0 + Vector((-1.4, -1.0, 0.2)), F0, 70, 2.0, (0.85, 0.9, 1.0)),
             area_light("HomeRim", F0 + Vector((-0.6, 1.2, 0.8)), F0, 180, 0.8, (0.9, 0.95, 1.0)),
             area_light("WindowSpill", Vector((HX - 2.0, HY - 0.4, FLOOR_Z + 1.6)), F0, 220, 1.2, (0.85, 0.92, 1.0))],
    "car": [area_light("DashUp", F0 + Vector((0.0, -0.45, -0.25)), F0, 14, 0.4, (1.0, 0.6, 0.3)),
            area_light("CarRim", F0 + Vector((-0.9, 0.3, 0.3)), F0, 40, 0.5, (0.6, 0.7, 1.0)),
            area_light("CarSide", F0 + Vector((1.0, -0.2, 0.2)), F0, 25, 0.6, (0.8, 0.85, 1.0))],
    "lab": [area_light("LabKey", LABP + Vector((0.3, -0.4, 0.4)), LABP, 60, 0.5, (1.0, 0.97, 0.94))],
    "xray": [area_light("XKey", F0 + Vector((0.6, -0.5, 0.5)), BR_C, 12, 0.8, (1.0, 0.92, 0.88)),
             area_light("XFill", F0 + Vector((0.5, 0.4, -0.2)), BR_C, 6, 1.0, (0.5, 0.7, 1.0))],
}
BASE = {l.name: l.data.energy for ls in LIGHTS.values() for l in ls}
for set_name, ls in LIGHTS.items():
    for l in ls:
        vals = []
        for f in FRAMES:
            on = shot_at(f)[2] == set_name
            e = BASE[l.name] * on
            if l.name in ("WindowSpill",):     # time-lapse: day/night sweeps during "years"
                cyc = 0.5 + 0.5 * math.cos(2 * math.pi * 3 * ramp(f, BEAT[2], BEAT[3]))
                e *= 0.15 + 0.85 * cyc if BEAT[2] <= f < BEAT[3] else 1.0
            if l.name == "CarSide":            # impact flash
                e *= 1 + 30 * spike(f, IMP, 1, 3)
            vals.append(e)
        bake(l.data, "energy", vals)
bake(win_mat.node_tree, 'nodes["Glow"].inputs[1].default_value',
     [3.0 * ((0.1 + 0.9 * (0.5 + 0.5 * math.cos(2 * math.pi * 3 * ramp(f, BEAT[2], BEAT[3]))))
             if BEAT[2] <= f < BEAT[3] else 1.0) for f in FRAMES])
bake(scene, '["xray"]', [1.0 if shot_at(f)[2] == "xray" else 0.0 for f in FRAMES], interp="CONSTANT")

SET_OF = [shot_at(f)[2] for f in FRAMES]


def in_set(name):
    return lambda f: SET_OF[f - 1] == name


def both(a, b):
    return lambda f: a(f) and b(f)


def between(a, b):
    return lambda f: a <= f <= b


special = {o.name for o in list(years.values()) + [pint_label, lab_csf, lab_hole, lab_men, lab_seal]}
key_visibility([o for o in HOME.objects if o.name not in special], in_set("home"))
key_visibility(list(CAR.objects), in_set("car"))
key_visibility([o for o in ANAT.objects if o.name not in special], in_set("xray"))
for y, o in years.items():
    key_visibility([o], both(in_set("home"), lambda f, y=y: flip[f - 1] == y))
key_visibility([pint_label], both(in_set("home"), between(at_beat(6, 0.82), BEAT[7] - 1)))
key_visibility([lab_csf], both(in_set("xray"), between(BEAT[4] + 8, BEAT[5] - 1)))
key_visibility([lab_hole], both(in_set("xray"), between(CRACK + 4, BEAT[6] - 1)))
key_visibility([lab_men], both(in_set("xray"), between(at_beat(7, 0.55), BEAT[8] - 1)))
key_visibility([lab_seal], both(in_set("xray"), between(SEAL + 6, BEAT[9] - 1)))
key_visibility([tissue], lambda f: SET_OF[f - 1] in ("home", "car"))


# ---------------------------------------------------------------- cameras
def fcurve_bezier(obj):
    for fc in fcurves_of(obj):
        if fc.data_path == "location":
            fc.keyframe_points.foreach_set("interpolation", [2] * len(fc.keyframe_points))


def cam(name, keys, lens, fstop, aim_obj, focus_obj=None):
    data = bpy.data.cameras.new(name)
    data.lens = lens
    data.sensor_width = 36
    data.dof.use_dof = True
    data.dof.aperture_fstop = fstop
    data.dof.focus_object = focus_obj or aim_obj
    data.clip_start = 0.01
    c = bpy.data.objects.new(name, data)
    scene.collection.objects.link(c)
    trk = c.constraints.new("TRACK_TO")
    trk.target = aim_obj
    trk.track_axis, trk.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"
    for f, loc in keys:
        c.location = loc
        c.keyframe_insert("location", frame=f)
    fcurve_bezier(c)
    return c


def static_aim(name, pos):
    e = bpy.data.objects.new(name, None)
    scene.collection.objects.link(e)
    e.location = pos
    return e


scene.frame_set(BEAT[0] + 5)
F = face_aim.matrix_world.translation.copy()
HC = head_ctr.matrix_world.translation.copy()
HO = hole_aim.matrix_world.translation.copy()
PM = path_mid.matrix_world.translation.copy()
NO = nostril_pt.matrix_world.translation.copy()
scene.frame_set(IMP + 4)
HC_IMP = head_ctr.matrix_world.translation.copy()


def orbit(center, radius, deg, dz=0.0):
    a = math.radians(deg)
    return center + Vector((radius * math.sin(a), -radius * math.cos(a), dz))


cams = {}
cams["CamNose"] = cam("CamNose", [(1, NO + Vector((0.07, -0.20, -0.005))), (H1, NO + Vector((0.05, -0.15, -0.004)))],
                      65, 2.8, nostril_pt)
cams["CamXSide"] = cam("CamXSide", [(H1, HC + Vector((0.62, -0.07, 0.02))), (H2, HC + Vector((0.55, -0.06, 0.02)))],
                       50, 8.0, head_ctr)
cams["CamHomeMid"] = cam("CamHomeMid", [(H2, F + Vector((0.35, -1.0, -0.12))), (BEAT[1], F + Vector((0.3, -0.85, -0.1)))],
                         40, 2.8, static_aim("HomeMidAim", F + Vector((0.02, 0, -0.14))), eye_focus)
cams["CamCar"] = cam("CamCar", [(BEAT[1], F + Vector((1.15, 0.05, 0.02))), (IMP + 2, F + Vector((1.0, 0.0, 0.0)))],
                     30, 4.0, static_aim("CarAim", F + Vector((0, -0.2, -0.12))), face_aim)
cams["CamXCrash"] = cam("CamXCrash", [(IMP + 2, HC_IMP + Vector((0.62, -0.05, 0.02))), (IMP + 9, HC_IMP + Vector((0.57, -0.05, 0.02)))],
                        50, 8.0, head_ctr)
cams["CamCarFront"] = cam("CamCarFront", [(IMP + 9, F + Vector((0.28, -1.1, -0.04))), (BEAT[2], F + Vector((0.24, -0.9, -0.04)))],
                          35, 2.8, static_aim("CarFrontAim", F + Vector((0, 0, -0.08))), eye_focus)
cams["CamHomeWide"] = cam("CamHomeWide", [(BEAT[2], Vector((HX + 1.7, HY - 3.6, F.z - 0.05))),
                                          (BEAT[3], Vector((HX + 1.5, HY - 3.2, F.z - 0.08)))],
                          24, 5.6, static_aim("HomeWideAim", Vector((HX + 0.45, HY + 0.1, SEAT_Z + 0.35))), face_aim)
cams["CamLab"] = cam("CamLab", [(BEAT[3], LABP + Vector((0.08, -0.36, 0.06))), (MUCUS, LABP + Vector((0.06, -0.28, 0.05))),
                                (BEAT[4], LABP + Vector((0.04, -0.2, 0.045)))],
                     60, 3.5, static_aim("LabAim", LABP + Vector((0.012, 0, 0.04))))
cams["CamXOrbit"] = cam("CamXOrbit", [(BEAT[4] + i * (BEAT[5] - BEAT[4]) // 4, orbit(HC, 0.62 - 0.02 * i, 30 + 15 * i, 0.06 - 0.015 * i))
                                      for i in range(5)], 50, 8.0, head_ctr)
cams["CamXHole"] = cam("CamXHole", [(BEAT[5], HO + Vector((0.30, -0.03, 0.03))), (CRACK, HO + Vector((0.16, -0.02, 0.015))),
                                    (BEAT[6], HO + Vector((0.11, -0.02, 0.01)))], 50, 5.6, hole_aim)
cams["CamHomeGlass"] = cam("CamHomeGlass", [(BEAT[6], GLASS + Vector((0.3, -0.62, 0.2))),
                                            (BEAT[7], GLASS + Vector((0.25, -0.52, 0.18)))],
                           28, 5.6, static_aim("GlassAim", GLASS.lerp(F, 0.42)), eye_focus)
cams["CamXBact"] = cam("CamXBact", [(BEAT[7], PM + Vector((0.22, -0.06, -0.03))), (BEAT[8], PM + Vector((0.15, -0.04, 0.0)))],
                       50, 5.6, path_mid)
cams["CamXSurg"] = cam("CamXSurg", [(BEAT[8], PM + Vector((0.28, -0.05, -0.02))), (SEAL - 6, PM + Vector((0.22, -0.04, -0.01))),
                                    (BEAT[9], HO + Vector((0.13, -0.02, 0.0)))], 50, 5.6, path_mid)
cams["CamHomeFront"] = cam("CamHomeFront", [(BEAT[9], F + Vector((0.06, -1.15, -0.06))), (END, F + Vector((0.03, -0.8, -0.04)))],
                           40, 2.8, static_aim("HomeFrontAim", F + Vector((0, 0, -0.1))), eye_focus)
for f, name, _ in SHOTS:
    scene.timeline_markers.new(name, frame=f).camera = cams[name]
scene.camera = cams[SHOTS[0][1]]

# narration on the sequencer (preview only; the pipeline muxes the final mix with ffmpeg)
if VO_WAV and os.path.exists(VO_WAV):
    scene.sequence_editor_create()
    seq = scene.sequence_editor
    strips = seq.strips if hasattr(seq, "strips") else seq.sequences
    strips.new_sound("VO", VO_WAV, channel=1, frame_start=1)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("SAVED", OUT, "END", END, "BEATS", BEAT, "IMP", IMP, "MUCUS", MUCUS, "CRACK", CRACK, "SEAL", SEAL)

for f in STILLS:
    scene.frame_set(f)
    scene.camera = cams[shot_at(f)[1]]
    scene.render.filepath = OUT.replace(".blend", f"_f{f:04d}.png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", scene.render.filepath)
