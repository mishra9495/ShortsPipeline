"""Short: "Doctors put this man's tooth inside his eye, to cure his blindness" (OOKP, Vancouver 2025).

Run (daily_render.ps1):  blender -b --python scene.py -- <ROOT>/blend/<slug>.blend [vo=..] [beats=..]
                          [stills=1,200] [pct=100] [samples=64] [device=gpu|cpu] [root=..] [char=..]
Built from templates/scene_template.py (same contract). Male lead: blend/char_hero.blend.
Sets: dark studio (hook), room (ibuprofen reaction, failed transplants, ending), lab macro (tooth -> block
-> lens) and X-ray anatomy (jaw/canine, cheek implant + vessels, move into the eye, immune cells).
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
SAMPLES = int(opts.get("samples", 64))   # + OptiX denoise; keeps ~1300 frames inside the nightly window
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

# ---------------------------------------------------------------- character (male lead)
HERO_BLEND = os.path.join(ROOT, "blend", "char_hero.blend")
CHAR = opts.get("char") or HERO_BLEND
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

# anatomy anchors (rest pose, metres): eyes, cornea, dental arch, cheek
head_len = BACK_Y - NOSE.y


def eye_centers():
    """Left/right eyeball centre + radius from the MPFB eye mesh; estimated from the nose if absent."""
    eyes = [o for o in bpy.data.objects if o.type == "MESH" and o.name.lower().endswith(("high-poly", "low-poly"))]
    if eyes:
        e = eyes[0]
        ev = e.evaluated_get(deps).to_mesh()
        pts = [e.matrix_world @ v.co for v in ev.vertices]
        e.evaluated_get(deps).to_mesh_clear()
        out = []
        for side in (1, -1):
            s = [p for p in pts if (p.x - X0) * side > 0]
            if not s:
                break
            lo = Vector((min(p.x for p in s), min(p.y for p in s), min(p.z for p in s)))
            hi = Vector((max(p.x for p in s), max(p.y for p in s), max(p.z for p in s)))
            out.append(((lo + hi) / 2, max(hi - lo) / 2))
        if len(out) == 2:
            return out
    est = []
    for side in (1, -1):
        est.append((Vector((X0 + 0.032 * side, NOSE.y + 0.034, NOSE.z + 0.036)), 0.012))
    return est


(EYE_L, EYE_RAD), (EYE_R, _) = eye_centers()
CORNEA_L = EYE_L + Vector((0, -EYE_RAD * 0.98, 0))
CORNEA_R = EYE_R + Vector((0, -EYE_RAD * 0.98, 0))
TEETH_Z = NOSE.z - 0.05
ARCH_C = Vector((X0, NOSE.y + 0.018, TEETH_Z))
TEETH = []          # (angle_deg, position) upper arch, +x = his left
for a in (-92, -78, -62, -45, -28, -10, 10, 28, 45, 62, 78, 92):
    r = math.radians(a)
    TEETH.append((a, ARCH_C + Vector((0.027 * math.sin(r), 0.036 * (1 - math.cos(r)), 0))))
CANINE = next(p for a, p in TEETH if a == 45)
CHEEK = Vector((X0 + 0.05, NOSE.y + 0.045, NOSE.z - 0.012))
MOUTH = Vector((X0, NOSE.y + 0.012, NOSE.z - 0.045))
print("EYES", tuple(round(c, 3) for c in EYE_L), round(EYE_RAD, 4), "CANINE", tuple(round(c, 3) for c in CANINE))
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
ROOM, DARK, LAB, ANAT, HEADP = new_coll("Room"), new_coll("Dark"), new_coll("Lab"), new_coll("Anatomy"), new_coll("HeadProps")
HX, HY = HIPS.x, HIPS.y
floor_mat = add_noise_bump(principled("Floor", (0.30, 0.30, 0.32), 0.5), scale=8, strength=0.1)
wall_mat = add_noise_bump(principled("Wall", (0.72, 0.76, 0.78), 0.9), scale=40, strength=0.05)
chair_mat = add_noise_bump(principled("Chair", (0.12, 0.16, 0.22), 0.7), scale=300, strength=0.15)
wood_mat = principled("Wood", (0.25, 0.14, 0.07), 0.4)
win_mat = glow("WindowLight", (0.9, 0.95, 1.0), 3.0)
panel_mat = principled("Panel", (0.03, 0.035, 0.04), 0.3)
red_ink = glow("RedInk", (1.0, 0.15, 0.1), 6.0)
white_ink = glow("WhiteInk", (0.95, 0.97, 1.0), 4.0)

box("Floor", (HX, HY - 1.0, FLOOR_Z - 0.02), (8, 8, 0.04), floor_mat, ROOM, bevel=0)
box("BackWall", (HX, HY + 0.95, FLOOR_Z + 1.5), (8, 0.1, 3.0), wall_mat, ROOM, bevel=0)
box("SideWall", (HX - 2.2, HY - 1.0, FLOOR_Z + 1.5), (0.1, 8, 3.0), wall_mat, ROOM, bevel=0)
box("Window", (HX - 2.14, HY - 0.4, FLOOR_Z + 1.55), (0.02, 1.3, 1.1), win_mat, ROOM, bevel=0)
box("ChairSeat", (HX, HY + 0.02, SEAT_Z - 0.06), (0.6, 0.6, 0.12), chair_mat, ROOM, bevel=0.03)
box("ChairBack", (HX, HY + 0.34, SEAT_Z + 0.35), (0.6, 0.1, 0.75), chair_mat, ROOM, bevel=0.03,
    rot=(math.radians(-8), 0, 0))
for lx in (-0.26, 0.26):
    for ly in (-0.24, 0.26):
        box(f"ChairLeg{lx}{ly}", (HX + lx, HY + ly, (SEAT_Z - 0.12 + FLOOR_Z) / 2), (0.04, 0.04, SEAT_Z - 0.12 - FLOOR_Z),
            wood_mat, ROOM, bevel=0)
# transplant counter on the back wall (beat 3)
DISP = Vector((HX + 0.95, HY + 0.88, SEAT_Z + 0.95))
box("Display", DISP, (0.75, 0.02, 0.55), panel_mat, ROOM, bevel=0.01)
txt_head = text("DispHead", "CORNEA TRANSPLANTS", DISP + Vector((0, -0.015, 0.19)), 0.055, white_ink, ROOM)
counts = {n: text(f"Count{n}", f"#{n}", DISP + Vector((-0.12, -0.015, -0.03)), 0.2, white_ink, ROOM) for n in range(1, 13)}
failed = text("DispFailed", "FAILED", DISP + Vector((0.18, -0.015, -0.03)), 0.075, red_ink, ROOM)
years = text("DispYears", "20 YEARS", DISP + Vector((0, -0.015, -0.2)), 0.07, red_ink, ROOM)
# pill (beat 2) rides in the right hand
pill_mat = principled("Pill", (0.95, 0.55, 0.15), 0.3, **{"Coat Weight": 0.6})
bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.005, depth=0.014, location=(0, 0, 0))
pill = bpy.context.active_object
pill.name = "Pill"
for zz in (0.007, -0.007):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=0.005, location=(0, 0, zz))
    cap = bpy.context.active_object
    cap.select_set(True)
pill.select_set(True)
bpy.context.view_layer.objects.active = pill
bpy.ops.object.join()
bpy.ops.object.shade_smooth()
pill.data.materials.append(pill_mat)
move_to(pill, scene.collection)

# dark studio (hook): just a black backdrop, lit by rim lights
box("DarkFloor", (HX, HY - 1.0, FLOOR_Z - 0.02), (8, 8, 0.04), principled("DarkFloorMat", (0.02, 0.02, 0.025), 0.4), DARK,
    bevel=0)

# lab macro (beat 5): tooth -> block, drill, lens
LABP = Vector((40.0, 0.0, 1.0))
tray_mat = principled("Tray", (0.75, 0.77, 0.8), 0.18, **{"Metallic": 1.0})
tooth_mat = principled("Tooth", (0.95, 0.93, 0.86), 0.25, **{"Subsurface Weight": 0.3, "Coat Weight": 0.6})
bone_mat = principled("Bone", (0.88, 0.8, 0.62), 0.6)
steel = principled("Steel", (0.6, 0.62, 0.65), 0.15, **{"Metallic": 1.0})
acrylic = principled("Acrylic", (0.9, 0.97, 1.0), 0.0, **{"Transmission Weight": 1.0, "IOR": 1.49,
                                                          "Emission Color": (0.7, 0.9, 1.0, 1), "Emission Strength": 0.0})
box("Tray", LABP + Vector((0, 0, -0.004)), (0.3, 0.2, 0.008), tray_mat, LAB, bevel=0.003)
box("LabBack", LABP + Vector((0, 0.25, 0.1)), (1.0, 0.02, 0.5), glow("LabGlow", (0.45, 0.55, 0.7), 0.25), LAB, bevel=0)
turn = bpy.data.objects.new("Turntable", None)
LAB.objects.link(turn)
turn.location = LABP
lab_tooth = blob("LabTooth", (0, 0, 0.011), 0.011, tooth_mat, LAB, scale=(0.7, 0.6, 1.4), noise_scale=0.3, strength=0.12)
lab_root = cyl("LabRoot", (0, 0, -0.004), 0.004, 0.02, tooth_mat, LAB, rot=(0, 0, 0))
lab_block = box("LabBlock", (0, 0, 0.009), (0.016, 0.012, 0.018), tooth_mat, LAB, bevel=0.0015)
lab_lens = cyl("LabLens", (0, 0, 0.009), 0.0035, 0.024, acrylic, LAB, rot=(math.radians(90), 0, 0), verts=32)
drill = cyl("Drill", (0, 0, 0.07), 0.0012, 0.06, steel, LAB, rot=(math.radians(90), 0, 0), verts=12)
for o in (lab_tooth, lab_root, lab_block, lab_lens, drill):
    o.parent = turn
chips = []
for i in range(14):
    c = blob(f"Chip{i}", (0, 0, 0.012), 0.0012, tooth_mat, LAB, strength=0.4, subdiv=1)
    c.parent = turn
    chips.append((c, Vector((random.uniform(-1, 1), random.uniform(-1, 1), random.uniform(0.3, 1.2))).normalized()))
mm_label = text("Label4mm", "4 mm", LABP + Vector((0.0, -0.014, 0.028)), 0.006, glow("LabelInk", (1.0, 0.85, 0.2), 6), LAB)

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

# ---------------------------------------------------------------- story timing (SYNC with mix.py)
PILL_F, CLOUD_F, EXTRACT_F, SHAVE_F, DRILL_F, LENS_F, SEAT_F, FOCUS_F, GLINT_F = \
    0.18, 0.60, 0.55, 0.15, 0.40, 0.70, 0.70, 0.35, 0.60
H1, H2 = at_beat(0, 0.35), at_beat(0, 0.70)        # hook: eye ECU -> X-ray -> face
CLOUD = at_beat(1, CLOUD_F)
SEAT = at_beat(6, SEAT_F)
FOCUS = at_beat(8, FOCUS_F)
GLINT = at_beat(9, GLINT_F)
T_COUNT = [BEAT[2] + 2 + int(n * (BEAT[3] - BEAT[2] - 10) / 12) for n in range(12)]   # transplant #1..#12
random.seed(31)

# ---------------------------------------------------------------- anatomy (X-ray only) + head props (always)
bonew = edge_glow("SkullXRay", (0.95, 0.93, 0.85), strength=1.0, core=0.0, blend=0.12)
eyeglow = edge_glow("EyeXRay", (0.7, 0.9, 1.0), strength=2.2, core=0.05, blend=0.25)
tooth_x = principled("ToothXRay", (0.95, 0.93, 0.86), 0.3, **{"Emission Color": (0.95, 0.93, 0.86, 1),
                                                                "Emission Strength": 0.6})
canine_mat = principled("Canine", (1.0, 0.85, 0.3), 0.3, **{"Emission Color": (1.0, 0.8, 0.2, 1),
                                                             "Emission Strength": 0.0})
vessel_mat = glow("Vessel", (1.0, 0.1, 0.08), 6.0)
cell_mat = principled("ImmuneCell", (0.2, 0.9, 0.3), 0.4, **{"Emission Color": (0.25, 1.0, 0.35, 1),
                                                              "Emission Strength": 2.5})
ANAT_OBJS = []
ANAT_OBJS.append(blob("SkullShell", Vector((X0, NOSE.y + head_len * 0.5, NOSE.z + 0.03)), 1.0, bonew, ANAT,
                      scale=(0.075, head_len * 0.52, 0.115), strength=0.0, subdiv=5))
for nm, c in (("EyeballL", EYE_L), ("EyeballR", EYE_R)):
    ANAT_OBJS.append(blob(nm, c, EYE_RAD, eyeglow, ANAT, strength=0.0, subdiv=4))
teeth = []
for a, p in TEETH:
    if a == 45:
        continue
    w = 0.0032 if abs(a) < 35 else 0.0042
    teeth.append(blob(f"Tooth{a}", p, 1.0, tooth_x, ANAT, scale=(w, 0.003, 0.006), noise_scale=0.3, strength=0.1, subdiv=3))
canine_root = bpy.data.objects.new("CanineRoot", None)
ANAT.objects.link(canine_root)
canine_root.location = CANINE
canine = blob("Canine", (0, 0, 0), 1.0, canine_mat, ANAT, scale=(0.0038, 0.0034, 0.0085), noise_scale=0.3, strength=0.1)
sliver = box("BoneSliver", (0, 0, 0.0085), (0.007, 0.004, 0.003), canine_mat, ANAT, bevel=0.0008)
canine.parent = canine_root
sliver.parent = canine_root
cu = bpy.data.curves.new("ArchCurve", "CURVE")
cu.dimensions = "3D"
cu.bevel_depth = 0.004
sp = cu.splines.new("POLY")
sp.points.add(len(TEETH) - 1)
for i, (a, p) in enumerate(TEETH):
    sp.points[i].co = (*(p + Vector((0, 0.002, 0.008))), 1)
arch = bpy.data.objects.new("Maxilla", cu)
ANAT.objects.link(arch)
arch.data.materials.append(bonew)
vessels = []
for k in range(9):
    a = 2 * math.pi * k / 9
    start = CHEEK + Vector((0.016 * math.cos(a) * 0.6, 0.016 * math.sin(a), 0.014 * math.sin(a * 2 + 1)))
    vc = bpy.data.curves.new(f"VesselCurve{k}", "CURVE")
    vc.dimensions = "3D"
    vc.bevel_depth = 0.0006
    s2 = vc.splines.new("POLY")
    pts = [start.lerp(CHEEK, t) + Vector((0.002 * math.sin(t * 9 + k), 0.002 * math.cos(t * 7 + k), 0.0015 * math.sin(t * 5 + k)))
           for t in [i / 10 for i in range(11)]]
    s2.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        s2.points[i].co = (*p, 1)
    vo = bpy.data.objects.new(f"Vessel{k}", vc)
    ANAT.objects.link(vo)
    vo.data.materials.append(vessel_mat)
    vessels.append(vo)
cells = []
for i in range(16):
    cells.append(blob(f"Cell{i}", (0, 0, 0), 1.0, cell_mat, ANAT, noise_scale=0.5, strength=0.35, subdiv=2))
side_rot = (math.pi / 2, 0, math.pi / 2 - 0.6)          # labels face the 3/4 front-left X-ray cameras
lab_tooth_l = text("LabelTooth", "TOOTH", CORNEA_L + Vector((0.02, -0.01, 0.022)), 0.008, glow("LblY", (1.0, 0.85, 0.2), 8), ANAT, rot=side_rot)
lab_canine = text("LabelCanine", "CANINE", CANINE + Vector((0.016, -0.012, 0.016)), 0.006, glow("LblY2", (1.0, 0.85, 0.2), 8), ANAT, rot=side_rot)
lab_months = text("LabelMonths", "~3 MONTHS", CHEEK + Vector((0.02, -0.02, 0.022)), 0.007, glow("LblR", (1.0, 0.3, 0.2), 8), ANAT, rot=side_rot)
lab_self = text("LabelSelf", "SELF", CORNEA_L + Vector((0.02, -0.01, 0.02)), 0.009, glow("LblG", (0.3, 1.0, 0.45), 8), ANAT, rot=side_rot)

# head props: the tooth-lens implant, mucosa over the treated eye, cloudy corneas, sunglasses, glint
implant = bpy.data.objects.new("Implant", None)
HEADP.objects.link(implant)
blk = box("ImplantBlock", (0, 0, 0), (0.008, 0.005, 0.008), tooth_mat, HEADP, bevel=0.001)
lens = cyl("ImplantLens", (0, -0.004, 0), 0.0019, 0.01, acrylic, HEADP, rot=(math.radians(90), 0, 0), verts=24)
lens_cap = cyl("ImplantLensFace", (0, -0.0091, 0), 0.0019, 0.0004, glow("LensDark", (0.02, 0.03, 0.05), 0.5), HEADP,
               rot=(math.radians(90), 0, 0), verts=24)
for o in (blk, lens, lens_cap):
    o.parent = implant
mucosa_mat = principled("Mucosa", (0.75, 0.33, 0.33), 0.35, **{"Subsurface Weight": 0.6, "Coat Weight": 0.8})
mucosa = blob("Mucosa", CORNEA_L + Vector((0, 0.001, 0)), 1.0, mucosa_mat, HEADP, scale=(EYE_RAD * 0.95, 0.0035, EYE_RAD * 0.85),
              strength=0.0, subdiv=4)
cloud_mat = principled("CloudyCornea", (0.92, 0.93, 0.95), 0.4, **{"Subsurface Weight": 0.5})
cloud_l = blob("CloudL", CORNEA_L + Vector((0, -0.0008, 0)), 1.0, cloud_mat, HEADP, scale=(EYE_RAD * 0.62, 0.0022, EYE_RAD * 0.62),
               strength=0.0, subdiv=4)
cloud_r = blob("CloudR", CORNEA_R + Vector((0, -0.0008, 0)), 1.0, cloud_mat, HEADP, scale=(EYE_RAD * 0.62, 0.0022, EYE_RAD * 0.62),
               strength=0.0, subdiv=4)
shades = bpy.data.objects.new("Sunglasses", None)
HEADP.objects.link(shades)
shade_mat = principled("ShadeLens", (0.01, 0.01, 0.012), 0.05, **{"Coat Weight": 1.0})
frame_mat = principled("ShadeFrame", (0.02, 0.02, 0.02), 0.3)
eye_mid = (EYE_L + EYE_R) / 2
for nm, ex in (("L", EYE_L.x - eye_mid.x), ("R", EYE_R.x - eye_mid.x)):
    o = blob(f"ShadeLens{nm}", (ex, 0, 0), 1.0, shade_mat, HEADP, scale=(0.026, 0.003, 0.02), strength=0.0, subdiv=3)
    o.parent = shades
o = box("ShadeBridge", (0, 0, 0.012), (abs(EYE_L.x - EYE_R.x) + 0.06, 0.004, 0.004), frame_mat, HEADP, bevel=0.001)
o.parent = shades
glint = bpy.data.objects.new("Glint", None)
HEADP.objects.link(glint)
for k, rz in enumerate((0, 90, 45, 135)):
    o = box(f"GlintRay{k}", (0, 0, 0), (0.03 if k < 2 else 0.016, 0.0006, 0.0012), glow(f"GlintMat{k}", (1, 1, 1), 30), HEADP,
            bevel=0, rot=(math.radians(90), math.radians(rz), 0))
    o.parent = glint

for coll in (ANAT, HEADP):
    for o in coll.objects:
        if o.parent is None:
            parent_rest(o, "Head")          # matrix_basis = rest-pose world coordinates

# per-frame motion of head-space objects (rest-pose world coordinates)
CORNEA_SEAT = CORNEA_L + Vector((0, -0.0032, 0))


def vis(on):
    return 1.0 if on else 0.0


imp_loc, imp_s = [], []
for f in FRAMES:
    if f < BEAT[1]:
        imp_loc.append(CORNEA_SEAT); imp_s.append(1.0)
    elif f < BEAT[5]:
        imp_loc.append(CHEEK); imp_s.append(0.0)
    elif f < BEAT[6] + 2:
        imp_loc.append(CHEEK); imp_s.append(1.0)
    else:
        k = ramp(f, BEAT[6] + 2, SEAT)
        arc = Vector((0.006, -0.012, 0)) * 4 * k * (1 - k)
        imp_loc.append(CHEEK.lerp(CORNEA_SEAT, k) + arc); imp_s.append(1.0)
bake_vec(implant, "location", imp_loc)
bake_vec(implant, "scale", [(s, s, s) for s in imp_s], interp="CONSTANT")
mz = [vis(f < BEAT[1] or f >= SEAT) for f in FRAMES]
bake_vec(mucosa, "scale", [(EYE_RAD * 0.95 * m, 0.0035 * m, EYE_RAD * 0.85 * m) for m in mz])
peel = [ramp(f, at_beat(6, 0.3), at_beat(6, 0.55)) for f in FRAMES]
cl = [vis(f >= CLOUD) * (1 - p) * ramp(f, CLOUD, CLOUD + 10) for f, p in zip(FRAMES, peel)]
bake_vec(cloud_l, "scale", [(EYE_RAD * 0.62 * c, 0.0022 * max(c, 0.01), EYE_RAD * 0.62 * c) for c in cl])
bake_vec(cloud_l, "location", [CORNEA_L + Vector((0.012 * p, -0.0008 - 0.01 * p, -0.006 * p)) for p in peel])
cr = [vis(f < BEAT[1] or f >= CLOUD) * (1.0 if f >= BEAT[1] else 1.0) * (ramp(f, CLOUD, CLOUD + 10) if f >= BEAT[1] else 1.0)
      for f in FRAMES]
bake_vec(cloud_r, "scale", [(EYE_RAD * 0.62 * c, 0.0022 * max(c, 0.01), EYE_RAD * 0.62 * c) for c in cr])
# transplants: each one clears the corneas for a moment, then they cloud over again
clear = [max((env(f, t, t + 2, t + 5, t + 9) for t in T_COUNT), default=0.0) for f in FRAMES]
bake(cloud_mat.node_tree, 'nodes["Principled BSDF"].inputs["Alpha"].default_value', [1 - 0.9 * c for c in clear])
SH_UP = Vector((0, 0.012, 0.06))
shade_pos = eye_mid + Vector((0, -EYE_RAD - 0.012, 0))
bake_vec(shades, "location", [shade_pos + SH_UP * (1 - ramp(f, at_beat(9, 0.05), at_beat(9, 0.2))) for f in FRAMES])
bake_vec(shades, "scale", [(s, s, s) for s in (vis(f >= BEAT[9]) for f in FRAMES)], interp="CONSTANT")
glint.location = MOUTH + Vector((0.014, -0.012, 0.004))
bake_vec(glint, "scale", [(g, g, g) for g in (spike(f, GLINT, 2, 6) for f in FRAMES)])
bake(glint, "rotation_euler", [0.05 * f for f in FRAMES], index=1)
# canine: highlight, then lifts out with its bone sliver
EXT = at_beat(3, EXTRACT_F)
bake(canine_mat.node_tree, 'nodes["Principled BSDF"].inputs["Emission Strength"].default_value',
     [3.0 * ramp(f, BEAT[3] + 4, BEAT[3] + 14) for f in FRAMES])
bake_vec(canine_root, "location", [CANINE + Vector((0.004, -0.02, -0.03)) * ramp(f, EXT - 6, at_beat(3, 0.85)) for f in FRAMES])
bake(canine_root, "rotation_euler", [0.6 * ramp(f, EXT - 6, at_beat(3, 0.85)) for f in FRAMES], index=1)
for k, vo in enumerate(vessels):
    a = at_beat(5, 0.2) + k * 2
    bake(vo.data, "bevel_factor_end", [ramp(f, a, a + int(0.55 * (BEAT[6] - BEAT[5]))) for f in FRAMES])
# immune cells approach the implant, "sniff", and back off
for i, c in enumerate(cells):
    d = Vector((random.uniform(0.2, 1.0), random.uniform(-1, -0.2), random.uniform(-1, 1))).normalized()
    far = CORNEA_SEAT + d * random.uniform(0.03, 0.05)
    near = CORNEA_SEAT + d * random.uniform(0.008, 0.012)
    r = random.uniform(0.0016, 0.0026)
    seed = random.uniform(0, 9)
    t_in, t_out = at_beat(7, random.uniform(0.0, 0.2)), at_beat(7, random.uniform(0.55, 0.7))
    locs, sc = [], []
    for f in FRAMES:
        k = ramp(f, t_in, t_in + 22) * (1 - ramp(f, t_out, t_out + 20))
        p = far.lerp(near, k) + Vector((0.0008 * math.sin(f * 0.8 + seed), 0.0008 * math.cos(f * 0.6 + seed), 0))
        locs.append(p)
        sc.append(r * vis(BEAT[7] <= f < BEAT[8]))
    bake_vec(c, "location", locs)
    bake_vec(c, "scale", [(s, s, s) for s in sc])

# lab macro animation (local to the turntable)
SH0, SH1 = at_beat(4, SHAVE_F) - 4, at_beat(4, SHAVE_F) + 18
DR0, DR1 = at_beat(4, DRILL_F) - 4, at_beat(4, DRILL_F) + 14
LE0, LE1 = at_beat(4, LENS_F) - 8, at_beat(4, LENS_F)
bake(turn, "rotation_euler", [0.6 * ramp(f, BEAT[4], BEAT[5]) - 0.3 for f in FRAMES], index=2)
for o in (lab_tooth, lab_root):
    s0 = tuple(o.scale)
    bake_vec(o, "scale", [tuple(v * (1 - ramp(f, SH0, SH1)) for v in s0) for f in FRAMES])
bake_vec(lab_block, "scale", [(k, k, k) for k in (ramp(f, SH0 + 4, SH1) for f in FRAMES)])
bake(drill, "location", [0.07 - 0.05 * env(f, DR0, DR0 + 8, DR1, DR1 + 8) for f in FRAMES], index=2)
bake(drill, "rotation_euler", [0.9 * f for f in FRAMES], index=2)
bake(lab_lens, "location", [-0.035 * (1 - ramp(f, LE0, LE1)) for f in FRAMES], index=1)
bake_vec(lab_lens, "scale", [(k, k, k) for k in (vis(f >= LE0 - 2) for f in FRAMES)], interp="CONSTANT")
bake(acrylic.node_tree, 'nodes["Principled BSDF"].inputs["Emission Strength"].default_value',
     [4.0 * spike(f, LE1 + 2, 2, 6) for f in FRAMES])
for c, d in chips:
    locs, sc = [], []
    for f in FRAMES:
        age = (f - SH0) / FPS
        on = SH0 <= f <= SH1 + 10
        p = Vector((0, 0, 0.012)) + d * 0.08 * max(age, 0) + Vector((0, 0, -0.2 * max(age, 0) ** 2))
        locs.append(p if on else Vector((0, 0, 0.012)))
        sc.append(1.0 if on else 0.0)
    bake_vec(c, "location", locs)
    bake_vec(c, "scale", [(s, s, s) for s in sc], interp="CONSTANT")
print("ANATOMY", len(ANAT.objects), "HEADPROPS", len(HEADP.objects))

# ---------------------------------------------------------------- IK arms
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


mouth_anchor = bone_empty("MouthAnchor", "Head", Vector((X0 - 0.03, NOSE.y - 0.07, NOSE.z - 0.085)))
hand_aim = bone_empty("HandAimPt", "Head", MOUTH + Vector((0, 0.01, 0.0)))
dt = rig.pose.bones[MX + "RightHand"].constraints.new("DAMPED_TRACK")
dt.name = "DT"
dt.target = hand_aim
dt.track_axis = "TRACK_Y"
dt.influence = 0.0
face_aim = bone_empty("FaceAim", "Head", Vector((X0, NOSE.y + 0.06, NOSE.z - 0.02)))
eye_focus = bone_empty("EyeFocus", "Head", Vector((X0 + 0.03, NOSE.y + 0.02, NOSE.z + 0.04)))
eye_l_aim = bone_empty("EyeLAim", "Head", CORNEA_L.copy())
canine_aim = bone_empty("CanineAim", "Head", CANINE + Vector((0.0, -0.01, -0.012)))
cheek_aim = bone_empty("CheekAim", "Head", CHEEK.copy())
move_aim = bone_empty("MoveAim", "Head", CHEEK.copy())
bake_vec(move_aim, "location", [CHEEK.lerp(CORNEA_L, ramp(f, BEAT[6], SEAT - 6)) for f in FRAMES])
hand_r = rig.data.bones[MX + "RightHand"]
pill.location = rig.matrix_world @ (hand_r.tail_local + Vector((0, 0, -0.02)))
parent_rest(pill, "RightHand")

# ---------------------------------------------------------------- shots: (start, camera, set)
SHOTS = [(1, "CamEyeECU", "dark"), (H1, "CamXFace", "xray"), (H2, "CamFaceDark", "dark"),
         (BEAT[1], "CamRoomMid", "room"), (BEAT[2], "CamRoomWide", "room"), (BEAT[3], "CamXJaw", "xray"),
         (BEAT[4], "CamLab", "lab"), (BEAT[5], "CamXCheek", "xray"), (BEAT[6], "CamXEye", "xray"),
         (BEAT[7], "CamXImmune", "xray"), (BEAT[8], "CamFaceRack", "room"), (BEAT[9], "CamFront", "room")]


def shot_at(f):
    return max((s for s in SHOTS if s[0] <= f), key=lambda s: s[0])


# ---------------------------------------------------------------- performance
FINGERS = [b.name[len(MX):] for b in rig.data.bones if "Hand" in b.name and b.name[-1] in "123"]
BLINKS = [f for f in range(20, END) if (f * 7919) % 97 == 0][:40]
P0, P1 = at_beat(1, PILL_F) - 14, at_beat(1, PILL_F) + 10


def curves(f):
    c = {}
    c["turn"] = 1 - ramp(f, 1, 40)
    c["pill"] = env(f, P0, P0 + 10, P1, P1 + 10)
    c["sway"] = env(f, at_beat(1, 0.42), at_beat(1, 0.5), at_beat(1, 0.85), BEAT[2])
    c["blind"] = env(f, CLOUD, CLOUD + 10, BEAT[3] - 6, BEAT[3])
    c["tired"] = env(f, BEAT[2], BEAT[2] + 8, BEAT[3] - 8, BEAT[3])
    c["lift"] = ramp(f, FOCUS - 4, FOCUS + 12) * (1 - ramp(f, BEAT[9] - 4, BEAT[9] + 6))
    c["smile"] = max(ramp(f, FOCUS + 4, FOCUS + 18), 0.0)
    c["nod"] = spike(f, at_beat(9, 0.82), 4, 8)
    c["blink"] = max((env(f, b - 1, b + 1, b + 3, b + 6) for b in BLINKS), default=0.0)
    c["rash"] = ramp(f, at_beat(1, 0.33), at_beat(1, 0.55)) * (1 - 0.8 * ramp(f, BEAT[2], BEAT[3]))
    return c


ROT, SHAPES = {}, {}
for f in FRAMES:
    c = curves(f)
    breath = math.sin(f / FPS * 2 * math.pi / 3.6)
    sw = c["sway"] * math.sin(f * 0.22) * 6
    poses = {
        "Hips": [(Z, 0.5 * wobble(f, 1))],
        "Spine": [(X, -8 + 0.4 * breath + 3 * c["tired"]), (Z, 0.8 * wobble(f, 2) + sw * 0.4)],
        "Spine1": [(X, -3 + 0.6 * breath + 3 * c["pill"] - 2 * c["lift"]), (Y, sw * 0.3)],
        "Spine2": [(X, 2 + 0.6 * breath)],
        "Neck": [(X, 4 + 4 * c["blind"] + 3 * c["tired"] - 5 * c["lift"] + 3 * c["nod"]), (Z, 1.5 * wobble(f, 4))],
        "Head": [(X, 1 + 5 * c["blind"] + 4 * c["tired"] - 6 * c["lift"] + 6 * c["nod"] - 6 * c["pill"]
                  + 1.0 * wobble(f, 7, 0.6)),
                 (Z, 2.0 * wobble(f, 5, 0.5) + 22 * c["turn"] + sw),
                 (Y, 1.2 * wobble(f, 6) + 3 * c["blind"])],
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
            curl += 35 * c["pill"]
        ROT.setdefault(name, []).append(Quaternion((1, 0, 0), math.radians(curl)))
    s = {}
    for side in ("Left", "Right"):
        s[f"eyeBlink{side}"] = min(1, c["blink"] + 0.25 * c["tired"] + 0.15 * c["smile"])
        s[f"eyeSquint{side}"] = min(1, 0.4 * c["blind"] + 0.35 * c["smile"])
        s[f"browDown{side}"] = 0.3 * c["blind"]
        s[f"mouthFrown{side}"] = 0.35 * c["blind"] + 0.2 * c["tired"]
        s[f"mouthSmile{side}"] = 0.7 * c["smile"]
        s[f"cheekSquint{side}"] = 0.4 * c["smile"]
    s["browInnerUp"] = min(1, 0.6 * c["blind"] + 0.4 * c["tired"] + 0.3 * c["lift"])
    s["jawOpen"] = 0.2 * c["pill"] + 0.1 * c["lift"] * (1 - c["smile"])
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

# rash: red blotches mixed into the skin material (before the X-ray mix)
try:
    for slot in body.material_slots:
        m = slot.material
        nt = m.node_tree
        outn = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output)
        xmix = outn.inputs["Surface"].links[0].from_node        # X-ray mix added earlier
        src_link = xmix.inputs[1].links[0]
        src = src_link.from_socket
        red = nt.nodes.new("ShaderNodeBsdfPrincipled")
        red.inputs["Base Color"].default_value = (0.65, 0.08, 0.07, 1)
        red.inputs["Roughness"].default_value = 0.5
        tc = nt.nodes.new("ShaderNodeTexCoord")
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 45
        nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs[1].default_value = 0.52
        mr.inputs[2].default_value = 0.62
        nt.links.new(nz.outputs["Fac"], mr.inputs[0])
        rv = nt.nodes.new("ShaderNodeValue")
        rv.name = "Rash"
        mul = nt.nodes.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        nt.links.new(mr.outputs[0], mul.inputs[0])
        nt.links.new(rv.outputs[0], mul.inputs[1])
        rmix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(mul.outputs[0], rmix.inputs[0])
        nt.links.new(src, rmix.inputs[1])
        nt.links.new(red.outputs[0], rmix.inputs[2])
        nt.links.new(rmix.outputs[0], xmix.inputs[1])
        bake(nt, 'nodes["Rash"].outputs[0].default_value', [0.8 * curves(f)["rash"] for f in FRAMES])
        break
except Exception as exc:
    print("WARN rash skipped:", exc)

# IK targets (hands on thighs; right hand brings the pill to the mouth)
ikL, ikR = bpy.data.objects["IK_Left"], bpy.data.objects["IK_Right"]
locL, locR = [], []
for f in FRAMES:
    scene.frame_set(f)
    c = curves(f)
    mouth = mouth_anchor.matrix_world.translation.copy()
    p = c["pill"]
    locR.append(THIGH_R.lerp(mouth, p) + Vector((0.02, -0.12, 0.05)) * 4 * p * (1 - p))
    locL.append(THIGH_L.copy())
bake_vec(ikL, "location", locL)
bake_vec(ikR, "location", locR)
bake(rig, f'pose.bones["{MX}RightHand"].constraints["DT"].influence', [min(1.0, 1.4 * curves(f)["pill"]) for f in FRAMES])
bake_vec(pill, "scale", [(s, s, s) for s in (vis(BEAT[1] <= f < P1 + 6) for f in FRAMES)], interp="CONSTANT")

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
SET_OF = [shot_at(f)[2] for f in FRAMES]
DAY = [ramp(f, BEAT[8], BEAT[8] + 10) for f in FRAMES]          # warm, bright ending


def world_col(f):
    s = SET_OF[f - 1]
    if s == "room":
        d = DAY[f - 1]
        return Vector((0.55, 0.6, 0.66)).lerp(Vector((0.85, 0.7, 0.5)), d), 0.25 + 0.25 * d
    return {"dark": (Vector((0.003, 0.004, 0.008)), 1.0), "lab": (Vector((0.6, 0.7, 0.8)), 0.04),
            "xray": (Vector((0.004, 0.012, 0.03)), 1.0)}[s]


cols = [world_col(f) for f in FRAMES]
bake_vec(wnt, 'nodes["Background"].inputs[0].default_value', [(*c, 1) for c, _ in cols], n=4)
bake(wnt, 'nodes["Background"].inputs[1].default_value', [s for _, s in cols])

F0 = Vector((X0, NOSE.y, NOSE.z))
LIGHTS = {
    "room": [area_light("RoomKey", F0 + Vector((1.2, -1.4, 0.9)), F0, 240, 1.2, (1.0, 0.95, 0.88)),
             area_light("RoomFill", F0 + Vector((-1.4, -1.0, 0.2)), F0, 60, 2.0, (0.85, 0.9, 1.0)),
             area_light("RoomRim", F0 + Vector((-0.6, 1.2, 0.8)), F0, 160, 0.8, (0.9, 0.95, 1.0)),
             area_light("WindowSpill", Vector((HX - 2.0, HY - 0.4, FLOOR_Z + 1.6)), F0, 200, 1.2, (0.85, 0.92, 1.0))],
    "dark": [area_light("DarkRimL", F0 + Vector((0.9, 0.6, 0.4)), F0, 120, 0.5, (0.6, 0.8, 1.0)),
             area_light("DarkRimR", F0 + Vector((-0.9, 0.6, 0.4)), F0, 120, 0.5, (0.6, 0.8, 1.0)),
             area_light("DarkKey", F0 + Vector((0.4, -0.9, -0.2)), F0, 25, 0.6, (0.9, 0.95, 1.0))],
    "lab": [area_light("LabKey", LABP + Vector((0.2, -0.3, 0.3)), LABP, 9, 0.4, (1.0, 0.97, 0.94)),
            area_light("LabRim", LABP + Vector((-0.2, 0.2, 0.2)), LABP, 7, 0.3, (0.8, 0.9, 1.0))],
    "xray": [area_light("XKey", F0 + Vector((0.6, -0.5, 0.5)), F0, 12, 0.8, (1.0, 0.92, 0.88)),
             area_light("XFill", F0 + Vector((0.5, 0.4, -0.2)), F0, 6, 1.0, (0.5, 0.7, 1.0))],
}
BASE = {l.name: l.data.energy for ls in LIGHTS.values() for l in ls}
for set_name, ls in LIGHTS.items():
    for l in ls:
        vals = []
        for f in FRAMES:
            e = BASE[l.name] * (SET_OF[f - 1] == set_name)
            if set_name == "room":
                cold = 1.0 if BEAT[1] <= f < BEAT[3] else 0.0
                e *= (0.8 if cold else 1.0) + 0.5 * DAY[f - 1]
            vals.append(e)
        bake(l.data, "energy", vals)
for l in LIGHTS["room"]:
    bake_vec(l.data, "color", [tuple(Vector(l.data.color).lerp(Vector((1.0, 0.85, 0.65)), 0.6 * d)) for d in DAY])
bake(scene, '["xray"]', [1.0 if s == "xray" else 0.0 for s in SET_OF], interp="CONSTANT")


def in_set(*names):
    return lambda f: SET_OF[f - 1] in names


def both(a, b):
    return lambda f: a(f) and b(f)


def between(a, b):
    return lambda f: a <= f <= b


special = {o.name for o in (txt_head, failed, years, lab_tooth_l, lab_canine, lab_months, lab_self, mm_label)} | \
    {o.name for o in counts.values()}
key_visibility([o for o in ROOM.objects if o.name not in special], in_set("room"))
key_visibility(list(DARK.objects), in_set("dark"))
key_visibility([o for o in ANAT.objects if o.name not in special and o not in vessels and o not in (canine, sliver)], in_set("xray"))
key_visibility([canine, sliver], both(in_set("xray"), lambda f: f < BEAT[4]))
key_visibility(vessels, both(in_set("xray"), between(BEAT[5], at_beat(6, 0.25))))
key_visibility(list(HEADP.objects), in_set("room", "dark", "xray"))
for n, o in counts.items():
    t0 = T_COUNT[n - 1]
    t1 = T_COUNT[n] - 1 if n < 12 else END
    key_visibility([o], both(in_set("room"), between(t0, t1)))
key_visibility([txt_head], in_set("room"))
key_visibility([failed], both(in_set("room"), lambda f: f >= T_COUNT[0] + 6))
key_visibility([years], both(in_set("room"), between(T_COUNT[-1] + 4, BEAT[3])))
key_visibility([lab_tooth_l], both(in_set("xray"), between(H1 + 4, H2)))
key_visibility([lab_canine], both(in_set("xray"), between(BEAT[3] + 10, BEAT[4])))
key_visibility([lab_months], both(in_set("xray"), between(at_beat(5, 0.45), BEAT[6])))
key_visibility([lab_self], both(in_set("xray"), between(at_beat(7, 0.55), BEAT[8])))
key_visibility([mm_label], between(LE1 + 4, BEAT[5]))
key_visibility([pill], in_set("room"))


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
    data.clip_start = 0.005
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


scene.frame_set(BEAT[0] + 45)
F = face_aim.matrix_world.translation.copy()
EL = eye_l_aim.matrix_world.translation.copy()
CA = canine_aim.matrix_world.translation.copy()
CH = cheek_aim.matrix_world.translation.copy()
cams = {}
cams["CamEyeECU"] = cam("CamEyeECU", [(1, EL + Vector((0.025, -0.085, 0.004))), (H1, EL + Vector((0.06, -0.2, 0.01)))],
                        60, 2.8, eye_l_aim)
cams["CamXFace"] = cam("CamXFace", [(H1, EL + Vector((0.2, -0.3, 0.03))), (H2, EL + Vector((0.16, -0.25, 0.025)))],
                       50, 8.0, eye_l_aim)
cams["CamFaceDark"] = cam("CamFaceDark", [(H2, F + Vector((0.14, -0.6, -0.03))), (BEAT[1], F + Vector((0.11, -0.48, -0.02)))],
                          50, 2.8, static_aim("FaceDarkAim", F + Vector((0, 0, -0.04))), eye_focus)
cams["CamRoomMid"] = cam("CamRoomMid", [(BEAT[1], F + Vector((0.32, -0.95, -0.15))), (BEAT[2], F + Vector((0.26, -0.78, -0.12)))],
                         40, 2.8, static_aim("RoomMidAim", F + Vector((0.0, 0, -0.14))), eye_focus)
cams["CamRoomWide"] = cam("CamRoomWide", [(BEAT[2], Vector((HX + 1.1, HY - 2.9, F.z - 0.15))),
                                          (BEAT[3], Vector((HX + 1.0, HY - 2.6, F.z - 0.15)))],
                          26, 5.6, static_aim("RoomWideAim", Vector((HX + 0.5, HY + 0.3, SEAT_Z + 0.55))), face_aim)
cams["CamXJaw"] = cam("CamXJaw", [(BEAT[3], CA + Vector((0.17, -0.2, -0.03))), (BEAT[4], CA + Vector((0.12, -0.15, -0.02)))],
                      50, 5.6, canine_aim)
cams["CamLab"] = cam("CamLab", [(BEAT[4], LABP + Vector((0.05, -0.14, 0.07))), (BEAT[5], LABP + Vector((0.035, -0.1, 0.05)))],
                     70, 11.0, static_aim("LabAim", LABP + Vector((0, 0, 0.016))))
cams["CamXCheek"] = cam("CamXCheek", [(BEAT[5], CH + Vector((0.22, -0.26, 0.03))), (BEAT[6], CH + Vector((0.16, -0.19, 0.02)))],
                        50, 5.6, cheek_aim)
cams["CamXEye"] = cam("CamXEye", [(BEAT[6], CH + Vector((0.2, -0.24, 0.03))), (SEAT - 6, EL + Vector((0.13, -0.17, 0.02))),
                                  (BEAT[7], EL + Vector((0.11, -0.14, 0.02)))], 50, 5.6, move_aim)
cams["CamXImmune"] = cam("CamXImmune", [(BEAT[7], EL + Vector((0.16, -0.19, 0.04))), (BEAT[8], EL + Vector((0.13, -0.15, 0.03)))],
                         50, 5.6, eye_l_aim)
cams["CamFaceRack"] = cam("CamFaceRack", [(BEAT[8], F + Vector((0.06, -0.5, -0.01))), (BEAT[9], F + Vector((0.05, -0.42, -0.01)))],
                          50, 2.0, static_aim("RackAim", F + Vector((0, 0, -0.02))))
# rack focus: the focus target slides from just in front of the lens onto the eyes
rack_t = static_aim("RackFocus", F + Vector((0.055, -0.36, -0.01)))
cl_ = rack_t.constraints.new("COPY_LOCATION")
cl_.target = eye_focus
bake(rack_t, 'constraints["Copy Location"].influence', [ramp(f, FOCUS - 6, FOCUS + 6) for f in FRAMES])
cams["CamFaceRack"].data.dof.focus_object = rack_t
cams["CamFront"] = cam("CamFront", [(BEAT[9], F + Vector((0.05, -0.45, -0.02))), (END, F + Vector((0.08, -0.95, -0.12)))],
                       40, 2.8, static_aim("FrontAim", F + Vector((0, 0, -0.06))), eye_focus)
for f, name, _ in SHOTS:
    scene.timeline_markers.new(name, frame=f).camera = cams[name]
scene.camera = cams[SHOTS[0][1]]

if VO_WAV and os.path.exists(VO_WAV):
    scene.sequence_editor_create()
    seq = scene.sequence_editor
    strips = seq.strips if hasattr(seq, "strips") else seq.sequences
    strips.new_sound("VO", VO_WAV, channel=1, frame_start=1)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("SAVED", OUT, "END", END, "BEATS", BEAT, "SEAT", SEAT, "FOCUS", FOCUS)

for f in STILLS:
    scene.frame_set(f)
    scene.camera = cams[shot_at(f)[1]]
    scene.render.filepath = OUT.replace(".blend", f"_f{f:04d}.png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", scene.render.filepath)
