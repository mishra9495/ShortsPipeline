"""Test scene: frozen lake hook shot (0-5.5 s of the 'fall through ice' script).

Run: blender -b blend/char_hero.blend --python scene_ice_test.py -- <out.blend> [still_frames]
Builds environment, lighting, idle body animation, facial animation, ice-crack VFX,
3 cut cameras, snowfall; saves the .blend; optionally renders listed stills.
"""
import math
import random
import sys

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

sys.path.append(r"D:\ShortsPipeline\scripts")
import pipeline as P  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
OUT = argv[0]
STILLS = [int(f) for f in argv[1].split(",")] if len(argv) > 1 else []

FPS = 30
END = 165
CRACK_START, CRACK_END = 58, 112      # crack spreads under "the cold water isn't what kills you first"
LOOK_DOWN, GASP = 112, 130            # reaction on "It's your own breathing."
random.seed(7)

scene = bpy.context.scene
scene.frame_start, scene.frame_end = 1, END
P.setup_render(scene, samples=96)
scene.render.use_persistent_data = True
scene.view_settings.exposure = -0.3

rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
body = bpy.data.objects["Hero.body"]
face_meshes = [o for o in bpy.data.objects if o.type == "MESH" and o.data.shape_keys
               and "eyeBlinkLeft" in o.data.shape_keys.key_blocks]
print("BONES", [b.name.replace("mixamorig:", "") for b in rig.data.bones])
print("FACE_MESHES", [o.name for o in face_meshes])

# ---------------------------------------------------------------- skin look
grp = next(n for n in body.material_slots[0].material.node_tree.nodes if n.type == "GROUP")
for name, val in {"Roughness": 0.5, "Pore strength": 0.35, "SSS strength": 0.32,
                  "SSS radius scale": 0.08, "Contrast": 0.08, "colorMixInStrength": 0.09}.items():
    if name in grp.inputs:
        grp.inputs[name].default_value = val


# ---------------------------------------------------------------- materials
def principled(name, color, rough, **kw):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    for k, v in kw.items():
        b.inputs[k].default_value = v
    return m


def ice_material():
    m = bpy.data.materials.new("LakeIce")
    m.use_nodes = True
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    bsdf = N["Principled BSDF"]
    tc = N.new("ShaderNodeTexCoord")

    # wind-blown snow streaks vs. clear black ice (stretched noise = drift direction)
    stretch = N.new("ShaderNodeMapping"); stretch.inputs["Scale"].default_value = (0.35, 1.0, 1.0)
    stretch.inputs["Rotation"].default_value = (0, 0, 0.5)
    L.new(tc.outputs["Object"], stretch.inputs["Vector"])
    drift = N.new("ShaderNodeTexNoise"); drift.inputs["Scale"].default_value = 0.22
    drift.inputs["Detail"].default_value = 10; drift.inputs["Roughness"].default_value = 0.68
    L.new(stretch.outputs["Vector"], drift.inputs["Vector"])
    # keep a clear patch under the character so the crack reads
    dist = N.new("ShaderNodeVectorMath"); dist.operation = "LENGTH"
    L.new(tc.outputs["Object"], dist.inputs[0])
    clear = N.new("ShaderNodeMapRange"); clear.inputs[1].default_value = 1.2; clear.inputs[2].default_value = 4.0
    L.new(dist.outputs["Value"], clear.inputs[0])
    snowy = N.new("ShaderNodeMath"); snowy.operation = "MULTIPLY"
    L.new(drift.outputs["Fac"], snowy.inputs[0]); L.new(clear.outputs[0], snowy.inputs[1])
    snow_mask = N.new("ShaderNodeMapRange"); snow_mask.inputs[1].default_value = 0.5; snow_mask.inputs[2].default_value = 0.62
    L.new(snowy.outputs[0], snow_mask.inputs[0])

    # trapped bubbles + streaks inside the ice
    bub = N.new("ShaderNodeTexVoronoi"); bub.inputs["Scale"].default_value = 38
    bub.feature = "F1"
    L.new(tc.outputs["Object"], bub.inputs["Vector"])
    bub_m = N.new("ShaderNodeMapRange"); bub_m.inputs[1].default_value = 0.06; bub_m.inputs[2].default_value = 0.0
    L.new(bub.outputs["Distance"], bub_m.inputs[0])

    # impact fracture: voronoi in polar space (angle, log radius) gives long radial
    # cracks with rings that tighten toward the impact point, like real stressed ice
    sep = N.new("ShaderNodeSeparateXYZ"); L.new(tc.outputs["Object"], sep.inputs[0])
    ang = N.new("ShaderNodeMath"); ang.operation = "ARCTAN2"
    L.new(sep.outputs["Y"], ang.inputs[0]); L.new(sep.outputs["X"], ang.inputs[1])
    ang_s = N.new("ShaderNodeMath"); ang_s.operation = "MULTIPLY"; ang_s.inputs[1].default_value = 2.4
    L.new(ang.outputs[0], ang_s.inputs[0])
    rlen = N.new("ShaderNodeMath"); rlen.operation = "ADD"; rlen.inputs[1].default_value = 0.08
    L.new(dist.outputs["Value"], rlen.inputs[0])
    logr = N.new("ShaderNodeMath"); logr.operation = "LOGARITHM"; logr.inputs[1].default_value = 2.718
    L.new(rlen.outputs[0], logr.inputs[0])
    logr_s = N.new("ShaderNodeMath"); logr_s.operation = "MULTIPLY"; logr_s.inputs[1].default_value = 1.1
    L.new(logr.outputs[0], logr_s.inputs[0])
    polar = N.new("ShaderNodeCombineXYZ")
    L.new(ang_s.outputs[0], polar.inputs["X"]); L.new(logr_s.outputs[0], polar.inputs["Y"])
    warp = N.new("ShaderNodeTexNoise"); warp.inputs["Scale"].default_value = 3.0; warp.inputs["Detail"].default_value = 4
    L.new(tc.outputs["Object"], warp.inputs["Vector"])
    mixv = N.new("ShaderNodeMix"); mixv.data_type = "VECTOR"; mixv.inputs["Factor"].default_value = 0.09
    L.new(polar.outputs[0], mixv.inputs["A"]); L.new(warp.outputs["Color"], mixv.inputs["B"])
    vor = N.new("ShaderNodeTexVoronoi"); vor.feature = "DISTANCE_TO_EDGE"; vor.inputs["Scale"].default_value = 1.6
    L.new(mixv.outputs["Result"], vor.inputs["Vector"])
    # secondary hairline fractures in world space, only near the impact (see inside2)
    mixw = N.new("ShaderNodeMix"); mixw.data_type = "VECTOR"; mixw.inputs["Factor"].default_value = 0.15
    L.new(tc.outputs["Object"], mixw.inputs["A"]); L.new(warp.outputs["Color"], mixw.inputs["B"])
    vor2 = N.new("ShaderNodeTexVoronoi"); vor2.feature = "DISTANCE_TO_EDGE"; vor2.inputs["Scale"].default_value = 9
    L.new(mixw.outputs["Result"], vor2.inputs["Vector"])
    line1 = N.new("ShaderNodeMapRange"); line1.inputs[1].default_value = 0.022; line1.inputs[2].default_value = 0.0
    L.new(vor.outputs["Distance"], line1.inputs[0])
    line2 = N.new("ShaderNodeMapRange"); line2.inputs[1].default_value = 0.006; line2.inputs[2].default_value = 0.0
    L.new(vor2.outputs["Distance"], line2.inputs[0])
    radius = N.new("ShaderNodeValue"); radius.name = "CrackRadius"; radius.outputs[0].default_value = 0.0
    edge_noise = N.new("ShaderNodeTexNoise"); edge_noise.inputs["Scale"].default_value = 3
    L.new(tc.outputs["Object"], edge_noise.inputs["Vector"])
    jitter = N.new("ShaderNodeMath"); jitter.operation = "MULTIPLY_ADD"
    L.new(edge_noise.outputs["Fac"], jitter.inputs[0]); jitter.inputs[1].default_value = 0.6
    L.new(dist.outputs["Value"], jitter.inputs[2])
    inside = N.new("ShaderNodeMath"); inside.operation = "LESS_THAN"
    L.new(jitter.outputs[0], inside.inputs[0]); L.new(radius.outputs[0], inside.inputs[1])
    inner = N.new("ShaderNodeMath"); inner.operation = "MULTIPLY"; inner.inputs[1].default_value = 0.0
    fine_r = N.new("ShaderNodeMath"); fine_r.operation = "MULTIPLY"; fine_r.inputs[1].default_value = 0.3
    L.new(radius.outputs[0], fine_r.inputs[0])
    inside2 = N.new("ShaderNodeMath"); inside2.operation = "LESS_THAN"
    L.new(jitter.outputs[0], inside2.inputs[0]); L.new(fine_r.outputs[0], inside2.inputs[1])
    c1 = N.new("ShaderNodeMath"); c1.operation = "MULTIPLY"
    L.new(line1.outputs[0], c1.inputs[0]); L.new(inside.outputs[0], c1.inputs[1])
    c2 = N.new("ShaderNodeMath"); c2.operation = "MULTIPLY"
    L.new(line2.outputs[0], c2.inputs[0]); L.new(inside2.outputs[0], c2.inputs[1])
    crack = N.new("ShaderNodeMath"); crack.operation = "MAXIMUM"; crack.use_clamp = True
    L.new(c1.outputs[0], crack.inputs[0]); L.new(c2.outputs[0], crack.inputs[1])

    # color: deep blue-black ice -> bubbles -> white cracks -> snow
    ice_col = N.new("ShaderNodeMix"); ice_col.data_type = "RGBA"
    ice_col.inputs["A"].default_value = (0.012, 0.035, 0.05, 1)
    ice_col.inputs["B"].default_value = (0.45, 0.6, 0.68, 1)
    L.new(bub_m.outputs[0], ice_col.inputs["Factor"])
    crack_col = N.new("ShaderNodeMix"); crack_col.data_type = "RGBA"
    crack_col.inputs["B"].default_value = (0.85, 0.93, 1.0, 1)
    L.new(ice_col.outputs["Result"], crack_col.inputs["A"]); L.new(crack.outputs[0], crack_col.inputs["Factor"])
    snow_col = N.new("ShaderNodeMix"); snow_col.data_type = "RGBA"
    snow_col.inputs["B"].default_value = (0.82, 0.86, 0.92, 1)
    L.new(crack_col.outputs["Result"], snow_col.inputs["A"]); L.new(snow_mask.outputs[0], snow_col.inputs["Factor"])
    L.new(snow_col.outputs["Result"], bsdf.inputs["Base Color"])

    rough = N.new("ShaderNodeMapRange"); rough.inputs[3].default_value = 0.13; rough.inputs[4].default_value = 0.75
    L.new(snow_mask.outputs[0], rough.inputs[0]); L.new(rough.outputs[0], bsdf.inputs["Roughness"])
    bsdf.inputs["Subsurface Weight"].default_value = 0.0
    L.new(snow_mask.outputs[0], bsdf.inputs["Subsurface Weight"])
    bsdf.inputs["Subsurface Radius"].default_value = (0.5, 0.6, 0.8)
    bsdf.inputs["Subsurface Scale"].default_value = 0.05

    # surface relief: wind-polished ripples + crack grooves
    rip = N.new("ShaderNodeTexNoise"); rip.inputs["Scale"].default_value = 1.6; rip.inputs["Detail"].default_value = 8
    L.new(tc.outputs["Object"], rip.inputs["Vector"])
    hsum = N.new("ShaderNodeMath"); hsum.operation = "MULTIPLY_ADD"; hsum.inputs[1].default_value = -0.6
    L.new(crack.outputs[0], hsum.inputs[0]); L.new(rip.outputs["Fac"], hsum.inputs[2])
    bump = N.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.25; bump.inputs["Distance"].default_value = 0.02
    L.new(hsum.outputs[0], bump.inputs["Height"]); L.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m, radius


def distance_haze(mat, haze=(0.62, 0.7, 0.8), near=25, far=140):
    """Fake aerial perspective: blend toward sky color with camera distance (cheap, no volumes)."""
    nt = mat.node_tree
    out = nt.nodes["Material Output"]
    shader = out.inputs["Surface"].links[0].from_socket
    cam = nt.nodes.new("ShaderNodeCameraData")
    mr = nt.nodes.new("ShaderNodeMapRange"); mr.inputs[1].default_value = near; mr.inputs[2].default_value = far
    mr.inputs[4].default_value = 0.6
    nt.links.new(cam.outputs["View Distance"], mr.inputs[0])
    em = nt.nodes.new("ShaderNodeBackground"); em.inputs["Color"].default_value = (*haze, 1)
    em.inputs["Strength"].default_value = 0.55
    em_bsdf = nt.nodes.new("ShaderNodeEmission"); em_bsdf.inputs["Color"].default_value = (*haze, 1)
    em_bsdf.inputs["Strength"].default_value = 0.55
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(mr.outputs[0], mix.inputs[0]); nt.links.new(shader, mix.inputs[1])
    nt.links.new(em_bsdf.outputs[0], mix.inputs[2]); nt.links.new(mix.outputs[0], out.inputs["Surface"])
    nt.nodes.remove(em)


# ---------------------------------------------------------------- environment
def link(obj):
    scene.collection.objects.link(obj)
    return obj


bpy.ops.mesh.primitive_plane_add(size=400, location=(0, 0, 0))
lake = bpy.context.active_object; lake.name = "LakeIce"
ice_mat, crack_radius = ice_material()
lake.data.materials.append(ice_mat)

# snowy shoreline hills (ring) and pine tree line
bpy.ops.mesh.primitive_circle_add(vertices=256, radius=110, fill_type="NOTHING")
shore = bpy.context.active_object; shore.name = "Shore"
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.extrude_region_move(TRANSFORM_OT_translate={"value": (0, 0, 0)})
bpy.ops.transform.resize(value=(1.9, 1.9, 1))
bpy.ops.object.mode_set(mode="OBJECT")
for v in shore.data.vertices:
    r = Vector((v.co.x, v.co.y)).length
    if r > 120:
        v.co.z = 6 + 10 * random.random()
sub = shore.modifiers.new("Sub", "SUBSURF"); sub.levels = sub.render_levels = 2
snow_mat = principled("Snow", (0.8, 0.84, 0.9), 0.7, **{"Subsurface Weight": 0.3})
shore.data.materials.append(snow_mat)
distance_haze(snow_mat)

pine_mat = principled("PineNeedles", (0.03, 0.07, 0.045), 0.8)
pnt = pine_mat.node_tree
geo = pnt.nodes.new("ShaderNodeNewGeometry")
sep = pnt.nodes.new("ShaderNodeSeparateXYZ"); pnt.links.new(geo.outputs["Normal"], sep.inputs[0])
up = pnt.nodes.new("ShaderNodeMapRange"); up.inputs[1].default_value = 0.6; up.inputs[2].default_value = 0.85
pnt.links.new(sep.outputs["Z"], up.inputs[0])
pmix = pnt.nodes.new("ShaderNodeMix"); pmix.data_type = "RGBA"
pmix.inputs["A"].default_value = (0.03, 0.07, 0.045, 1); pmix.inputs["B"].default_value = (0.78, 0.82, 0.88, 1)
pnt.links.new(up.outputs[0], pmix.inputs["Factor"])
pnt.links.new(pmix.outputs["Result"], pnt.nodes["Principled BSDF"].inputs["Base Color"])
distance_haze(pine_mat)

tiers = []
for i, (r, h, z) in enumerate([(2.2, 3.2, 1.2), (1.7, 2.8, 3.0), (1.1, 2.4, 4.6), (0.6, 1.8, 6.0)]):
    bpy.ops.mesh.primitive_cone_add(vertices=10, radius1=r, depth=h, location=(0, 0, z))
    tiers.append(bpy.context.active_object)
bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.25, depth=1.2, location=(0, 0, 0.3))
tiers.append(bpy.context.active_object)
for t in tiers:
    t.select_set(True)
bpy.context.view_layer.objects.active = tiers[0]
bpy.ops.object.join()
pine = bpy.context.active_object; pine.name = "PineProto"
pine.data.materials.append(pine_mat)
pine.location = (0, 0, -100)
for i in range(420):
    a = random.uniform(0, 2 * math.pi)
    r = random.uniform(118, 175)
    p = bpy.data.objects.new(f"Pine{i}", pine.data)
    s = random.uniform(1.4, 2.6)
    p.scale = (s, s, s * random.uniform(0.9, 1.3))
    p.location = (r * math.cos(a), r * math.sin(a), 5 + (r - 118) * 0.12)
    p.rotation_euler.z = random.uniform(0, 6.28)
    link(p)

# ---------------------------------------------------------------- lighting
P.sky_world(scene, sun_elev=math.radians(13), sun_rot=math.radians(150), strength=0.45)
sun = P.sun_light("Sun", Euler((math.radians(77), 0, math.radians(150))), 3.2, (1.0, 0.82, 0.62), angle=0.03)
face_key = P.area_light("FaceKey", (-1.2, -1.6, 2.0), (0, 0, 1.6), 60, 1.2, (0.82, 0.9, 1.0))
bounce = P.area_light("IceBounce", (0, -0.9, 0.05), (0, 0, 1.6), 25, 2.0, (0.75, 0.85, 1.0))

# ---------------------------------------------------------------- snowfall
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=0.008, location=(0, 0, -50))
flake = bpy.context.active_object; flake.name = "Flake"
flake.data.materials.append(principled("Flake", (1, 1, 1), 0.5, **{"Emission Color": (0.9, 0.95, 1, 1), "Emission Strength": 0.4}))
bpy.ops.mesh.primitive_plane_add(size=16, location=(0, -3, 6))
emit = bpy.context.active_object; emit.name = "SnowEmitter"
ps = emit.modifiers.new("Snow", "PARTICLE_SYSTEM").particle_system.settings
ps.count, ps.frame_start, ps.frame_end, ps.lifetime = 6000, -250, END, 400
ps.normal_factor = -0.15
ps.effector_weights.gravity = 0.04
ps.brownian_factor = 0.35
ps.render_type = "OBJECT"; ps.instance_object = flake
ps.particle_size, ps.size_random = 1.0, 0.6
emit.show_instancer_for_render = False

# ---------------------------------------------------------------- body animation
ARM_REST = {pb.name: pb.bone.matrix_local.to_quaternion() for pb in rig.pose.bones}


def bone_dir(name):
    b = rig.data.bones["mixamorig:" + name]
    return (b.tail_local - b.head_local).normalized()


def aim_chain(chain):
    """chain: [(bone, target_dir)] parent->child. Returns {bone: local quaternion}."""
    out, parent_delta = {}, Quaternion()
    for name, target in chain:
        rest_dir = bone_dir(name)
        c = rest_dir.rotation_difference(parent_delta.inverted() @ Vector(target).normalized())
        r = ARM_REST["mixamorig:" + name]
        out[name] = r.inverted() @ c @ r
        parent_delta = parent_delta @ c
    return out


def arm_local(axis, deg, name):
    r = ARM_REST["mixamorig:" + name]
    return r.inverted() @ Quaternion(axis, math.radians(deg)) @ r


base = {}
for side, sx in (("Left", 1), ("Right", -1)):
    base.update(aim_chain([(f"{side}Arm", (0.17 * sx, 0.03, -1)),
                           (f"{side}ForeArm", (0.06 * sx, -0.32, -1)),
                           (f"{side}Hand", (0.02 * sx, -0.22, -1))]))
fingers = [b.name.replace("mixamorig:", "") for b in rig.data.bones
           if any(k in b.name for k in ("Index", "Middle", "Ring", "Pinky")) and not b.name.endswith("4")]


def smooth(t, a, b):
    x = min(max((t - a) / (b - a), 0), 1)
    return x * x * (3 - 2 * x)


def wobble(t, seed, freqs=(0.23, 0.51, 0.87)):
    return sum(math.sin(t * f * 2 * math.pi + seed * (i + 1.7)) / (i + 1) for i, f in enumerate(freqs))


X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))
for pb in rig.pose.bones:
    pb.rotation_mode = "QUATERNION"

for f in range(1, END + 1, 2):
    t = f / FPS
    look = smooth(f, LOOK_DOWN, LOOK_DOWN + 14)
    gasp = smooth(f, GASP, GASP + 5) * (1 - 0.35 * smooth(f, GASP + 12, GASP + 30))
    breath = math.sin(t * 2 * math.pi / 3.6)
    poses = {
        "Hips": [(Y, 0.8 * wobble(t, 1)), (Z, 1.2 * wobble(t, 2))],
        "Spine": [(X, 0.6 * breath + 3 * look), (Y, -0.5 * wobble(t, 1))],
        "Spine1": [(X, 0.5 * breath - 5 * gasp + 2 * look)],
        "Spine2": [(X, 0.6 * breath - 6 * gasp)],
        "Neck": [(X, 4 + 9 * look - 6 * gasp), (Z, 1.5 * wobble(t, 4))],
        "Head": [(X, -2 + 16 * look - 4 * gasp), (Z, 2.5 * wobble(t, 5) * (1 - look)), (Y, 1.5 * wobble(t, 6))],
        "LeftShoulder": [(Y, 4 * gasp), (X, 0.6 * breath)],
        "RightShoulder": [(Y, -4 * gasp), (X, 0.6 * breath)],
    }
    for name, rots in poses.items():
        q = Quaternion()
        for axis, deg in rots:
            q = q @ arm_local(axis, deg, name)
        pb = rig.pose.bones["mixamorig:" + name]
        pb.rotation_quaternion = q
        pb.keyframe_insert("rotation_quaternion", frame=f)
    for name, q in base.items():
        pb = rig.pose.bones["mixamorig:" + name]
        sway = arm_local(X, 2.0 * wobble(t, 9 if "Left" in name else 11) + (8 * gasp if "Fore" in name else 0), name)
        pb.rotation_quaternion = q @ sway
        pb.keyframe_insert("rotation_quaternion", frame=f)
    for name in fingers:
        pb = rig.pose.bones["mixamorig:" + name]
        curl = 14 + (18 if name.endswith(("2", "3")) else 0) + 10 * gasp
        pb.rotation_quaternion = Quaternion(Vector((1, 0, 0)), math.radians(curl))
        pb.keyframe_insert("rotation_quaternion", frame=f)

# ---------------------------------------------------------------- facial animation (ARKit units)
face_keys = {}


def face(name, frames_vals):
    for o in face_meshes:
        kb = o.data.shape_keys.key_blocks.get(name)
        if not kb:
            continue
        for fr, v in frames_vals:
            kb.value = v
            kb.keyframe_insert("value", frame=fr)


for blink in (22, 84, 121):
    for side in ("Left", "Right"):
        face(f"eyeBlink{side}", [(blink - 1, 0), (blink + 2, 1), (blink + 6, 0)])
for side in ("Left", "Right"):
    face(f"eyeLookDown{side}", [(LOOK_DOWN, 0), (LOOK_DOWN + 8, 0.7), (GASP + 2, 0.5)])
    face(f"eyeWide{side}", [(GASP - 1, 0), (GASP + 3, 0.9), (END, 0.75)])
    face(f"browOuterUp{side}", [(GASP - 1, 0), (GASP + 4, 0.7), (END, 0.55)])
    face(f"mouthStretch{side}", [(GASP - 1, 0), (GASP + 4, 0.35), (END, 0.25)])
    face(f"mouthFrown{side}", [(1, 0.08), (LOOK_DOWN, 0.08), (LOOK_DOWN + 10, 0.3)])
face("browInnerUp", [(LOOK_DOWN, 0), (LOOK_DOWN + 10, 0.35), (GASP + 4, 0.95), (END, 0.8)])
face("jawOpen", [(GASP - 1, 0.0), (GASP + 3, 0.45), (GASP + 16, 0.32), (END, 0.28)])
face("mouthFunnel", [(GASP - 1, 0), (GASP + 4, 0.25), (END, 0.15)])

# ---------------------------------------------------------------- crack VFX keyframes
crack_radius.outputs[0].default_value = 0.0
crack_radius.outputs[0].keyframe_insert("default_value", frame=CRACK_START)
for fr, r in ((CRACK_START + 6, 0.5), (CRACK_START + 14, 0.7), (CRACK_START + 26, 1.6), (CRACK_START + 34, 1.8), (CRACK_END, 3.4)):
    crack_radius.outputs[0].default_value = r
    crack_radius.outputs[0].keyframe_insert("default_value", frame=fr)


# ---------------------------------------------------------------- cameras
def anim_cam(name, keys, lens, fstop, focus_obj=None, shake=0.15):
    cam = P.add_camera(scene, name, keys[0][1], keys[0][2], lens, fstop=fstop)
    target = bpy.data.objects.new(name + "_aim", None); link(target)
    tr = cam.constraints.new("TRACK_TO"); tr.target = target
    tr.track_axis, tr.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"
    cam.data.dof.focus_object = focus_obj or target
    for fr, loc, aim in keys:
        cam.location = loc; cam.keyframe_insert("location", frame=fr)
        target.location = aim; target.keyframe_insert("location", frame=fr)
    for i, fc in enumerate(fcurves_of(target)):  # subtle handheld drift
        n = fc.modifiers.new("NOISE"); n.scale = 40; n.strength = shake * 0.08; n.phase = 10 * i
    return cam


def fcurves_of(obj):
    act = obj.animation_data.action
    if hasattr(act, "fcurves"):
        return list(act.fcurves)
    from bpy_extras import anim_utils
    return list(anim_utils.action_get_channelbag_for_slot(act, obj.animation_data.action_slot).fcurves)


def bone_follower(name, bone, world_pos, frame):
    """Empty that rides on a bone, placed at world_pos as of `frame` (for focus / aim)."""
    e = bpy.data.objects.new(name, None); link(e)
    e.parent, e.parent_type, e.parent_bone = rig, "BONE", "mixamorig:" + bone
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    e.matrix_world = Matrix.Translation(world_pos)
    return e


head_pos = rig.matrix_world @ rig.data.bones["mixamorig:Head"].head_local + Vector((0, -0.02, 0.07))
# Wide shot: 24mm was too wide-angle for a vertical frame at this distance, leaving him small
# under a lot of dead sky. Longer lens + closer + aiming higher (near collarbone, not waist)
# fills the frame properly while keeping the full-body establishing read.
camA = anim_cam("CamA_wide", [(1, (1.0, -2.55, 0.62), (0.08, 0, 1.3)), (60, (0.78, -2.05, 0.72), (0.04, 0, 1.32))], 35, 5.0)
camB = anim_cam("CamB_crack", [(58, (0.55, -1.25, 0.42), (0.05, -0.2, 0.02)), (118, (0.85, -1.75, 0.72), (0.0, -0.1, 0.0))], 26, 4.0)

# Face shot: aim and focus both ride on the Head bone via BONE parenting, so they track the
# character's live, animated head position (the look-down + gasp) every frame -- a target
# keyframed from the pre-animation rest head position (the original approach) drifts out of
# both frame and focus the moment the head actually moves.
cam_aim = bone_follower("CamC_aim", "Head", head_pos + Vector((0, 0, -0.06)), 119)
cam_focus = bone_follower("EyeFocus", "Head", head_pos + Vector((0.02, -0.1, -0.02)), 119)
camC = P.add_camera(scene, "CamC_face", head_pos + Vector((0.32, -0.95, -0.12)), head_pos + Vector((0, 0, -0.06)), 55, fstop=4.0)
tr = camC.constraints.new("TRACK_TO"); tr.target = cam_aim
tr.track_axis, tr.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"
camC.data.dof.focus_object = cam_focus
for fr, loc in ((119, head_pos + Vector((0.32, -0.95, -0.12))), (GASP, head_pos + Vector((0.26, -0.78, -0.12))),
                (GASP + 5, head_pos + Vector((0.2, -0.6, -0.1))), (END, head_pos + Vector((0.18, -0.55, -0.1)))):
    camC.location = loc
    camC.keyframe_insert("location", frame=fr)
for i, fc in enumerate(fcurves_of(camC)):
    n = fc.modifiers.new("NOISE"); n.scale = 40; n.strength = 0.008; n.phase = 10 * i

for fr, cam in ((1, camA), (58, camB), (119, camC)):
    scene.timeline_markers.new(cam.name, frame=fr).camera = cam
scene.camera = camA

# ---------------------------------------------------------------- audio for preview + save
scene.sequence_editor_create()
seq = scene.sequence_editor
strips = seq.strips if hasattr(seq, "strips") else seq.sequences
strips.new_sound("VO", r"D:\ShortsPipeline\audio\vo_michael_125.wav", channel=1, frame_start=1)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("SAVED", OUT)

for f in STILLS:
    scene.frame_set(f)
    scene.render.filepath = OUT.replace(".blend", f"_f{f:03d}.png").replace("\\blend\\", "\\renders\\")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", scene.render.filepath)
