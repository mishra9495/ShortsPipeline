"""Short: "This man held in a sneeze and tore a hole in his windpipe" (BMJ Case Reports 2023).

Run: blender -b blend/char_hero.blend --python scene_sneeze.py -- <out.blend> [still_frames] [pct] [samples]
One continuous timeline cut to the voice-over (audio/vo_sneeze.json): car interior on a moving
country road, plus X-ray anatomy shots (translucent body, windpipe, lungs) toggled by scene["xray"].
"""
import json
import math
import random
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.append(r"D:\ShortsPipeline\scripts")
import pipeline as P  # noqa: E402

# Named args only. The old positional form (out, stills, pct, samples) silently mis-assigned
# everything when a shell dropped an empty "" stills argument -- that shipped a whole 1156-frame
# render at resolution_percentage=96 (1036x1843) instead of 100 (1080x1920).
argv = sys.argv[sys.argv.index("--") + 1:]
OUT = argv[0]
opts = dict(kv.split("=", 1) for kv in argv[1:] if "=" in kv)
unknown = set(opts) - {"stills", "pct", "samples"}
if unknown or any("=" not in a for a in argv[1:]):
    raise SystemExit(f"usage: <out.blend> [stills=1,2] [pct=100] [samples=96]; got {argv[1:]}")
STILLS = [int(f) for f in opts["stills"].split(",")] if opts.get("stills") else []
PCT = int(opts.get("pct", 100))
SAMPLES = int(opts.get("samples", 96))
if PCT != 100:
    print(f"!! WARNING: resolution_percentage={PCT}, NOT a full-resolution render")
print(f"ARGS out={OUT} stills={STILLS} pct={PCT} samples={SAMPLES}")

FPS = 30
VO = json.load(open(r"D:\ShortsPipeline\audio\vo_sneeze.json"))


def fr(t):
    return int(round(t * FPS)) + 1


BEAT = [fr(b["start"]) for b in VO["beats"]]   # 1,110,180,265,301,487,558,673,788,919
END = fr(VO["duration"]) + 36
FRAMES = range(1, END + 1)

# Every other hand-authored constant in this file (acting-curve timings, bubble/crackle
# timing, camera cuts) was originally tuned by eye against the Kokoro narration's beat
# timing below. When the narration audio changes (different TTS, different pacing), those
# absolute frame numbers go stale even though BEAT/END (derived from vo_sneeze.json) update
# automatically. rmap() re-times any such legacy constant by piecewise-linear interpolation
# between the ORIGINAL beat boundaries and the CURRENT ones, so a retime only needs a new
# vo_sneeze.json, not a line-by-line rewrite.
OLD_BEAT = [1, 110, 180, 265, 301, 487, 558, 673, 788, 919]
OLD_END = 1053


def rmap(f):
    old_pts = OLD_BEAT + [OLD_END]
    new_pts = BEAT + [END]
    if f <= old_pts[0]:
        i = 0
    elif f >= old_pts[-1]:
        i = len(old_pts) - 2
    else:
        i = next(k for k in range(len(old_pts) - 1) if old_pts[k] <= f <= old_pts[k + 1])
    a, b, na, nb = old_pts[i], old_pts[i + 1], new_pts[i], new_pts[i + 1]
    t = 0.0 if b == a else (f - a) / (b - a)
    return int(round(na + t * (nb - na)))


XRAY = [(rmap(54), BEAT[1] - 1), (BEAT[4], BEAT[6] - 1), (BEAT[7], rmap(865))]
TEAR_HOOK, TEAR = rmap(62), BEAT[5] + 10    # tear rips open (hook flash-forward, story)
JOLT_HOOK, JOLT = rmap(26), BEAT[3] + 8     # suppressed-sneeze jolt
SNEEZE = rmap(978)                          # final, free sneeze
random.seed(11)

scene = bpy.context.scene
scene.frame_start, scene.frame_end = 1, END
P.setup_render(scene, samples=SAMPLES)
scene.render.resolution_percentage = PCT
scene.render.use_persistent_data = True
scene.cycles.transparent_max_bounces = 32
scene.view_settings.exposure = -0.35
bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"

MX = "mixamorig:"
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
body = bpy.data.objects["Hero.body"]
hero_objs = [o for o in bpy.data.objects if o.parent == rig]
face_meshes = [o for o in hero_objs if o.type == "MESH" and o.data.shape_keys]
for pb in rig.pose.bones:
    pb.rotation_mode = "QUATERNION"

# ---------------------------------------------------------------- skin look
grp = next(n for n in body.material_slots[0].material.node_tree.nodes if n.type == "GROUP")
for name, val in {"Roughness": 0.48, "Pore strength": 0.35, "SSS strength": 0.32,
                  "SSS radius scale": 0.08, "Contrast": 0.08, "colorMixInStrength": 0.09}.items():
    if name in grp.inputs:
        grp.inputs[name].default_value = val


# ---------------------------------------------------------------- animation helpers
def fcurves_of(idb):
    act = idb.animation_data.action
    if hasattr(act, "fcurves"):
        return act.fcurves
    from bpy_extras import anim_utils
    return anim_utils.action_get_channelbag_for_slot(act, idb.animation_data.action_slot).fcurves


def bake(idb, path, values, index=None, frames=FRAMES, interp="LINEAR"):
    """Write one value per frame straight into an fcurve (fast; no per-key operator calls).
    index=None for scalar properties, 0..n for one component of an array property."""
    if index is None:
        idb.keyframe_insert(data_path=path, frame=frames[0])
    else:
        idb.keyframe_insert(data_path=path, index=index, frame=frames[0])
    fc = fcurves_of(idb).find(path, index=index or 0)
    fc.keyframe_points.clear()
    fc.keyframe_points.add(len(values))
    fc.keyframe_points.foreach_set("co", [c for f, v in zip(frames, values) for c in (f, v)])
    fc.keyframe_points.foreach_set("interpolation", [{"CONSTANT": 0, "LINEAR": 1}[interp]] * len(values))
    fc.update()
    return fc


def bake_vec(idb, path, vecs, n=3):
    for i in range(n):
        bake(idb, path, [v[i] for v in vecs], index=i)


def ramp(f, a, b):
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


def in_xray(f):
    return any(a <= f <= b for a, b in XRAY)


def link(obj, coll=None):
    (coll or scene.collection).objects.link(obj)
    return obj


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
    tex = nt.nodes.new("ShaderNodeTexNoise"); tex.inputs["Scale"].default_value = scale
    tex.inputs["Detail"].default_value = detail
    bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = strength
    nt.links.new(tex.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])
    return m


def color_variation(m, a, b, scale=4.0):
    nt = m.node_tree
    tex = nt.nodes.new("ShaderNodeTexNoise"); tex.inputs["Scale"].default_value = scale
    tex.inputs["Detail"].default_value = 8
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"
    mix.inputs["A"].default_value = (*a, 1); mix.inputs["B"].default_value = (*b, 1)
    nt.links.new(tex.outputs["Fac"], mix.inputs["Factor"])
    nt.links.new(mix.outputs["Result"], nt.nodes["Principled BSDF"].inputs["Base Color"])


def distance_haze(mat, haze=(0.62, 0.72, 0.85), near=30, far=260, amount=0.55):
    nt = mat.node_tree
    out = nt.nodes["Material Output"]
    shader = out.inputs["Surface"].links[0].from_socket
    cam = nt.nodes.new("ShaderNodeCameraData")
    mr = nt.nodes.new("ShaderNodeMapRange"); mr.inputs[1].default_value = near; mr.inputs[2].default_value = far
    mr.inputs[4].default_value = amount
    nt.links.new(cam.outputs["View Distance"], mr.inputs[0])
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (*haze, 1)
    em.inputs["Strength"].default_value = 0.9
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(mr.outputs[0], mix.inputs[0]); nt.links.new(shader, mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2]); nt.links.new(mix.outputs[0], out.inputs["Surface"])


def box(name, loc, size, mat, coll, bevel=0.02, rot=(0, 0, 0), segs=3):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        bv = o.modifiers.new("Bevel", "BEVEL"); bv.width = bevel; bv.segments = segs
        bpy.ops.object.shade_smooth()
    o.data.materials.append(mat)
    move_to(o, coll)
    return o


def move_to(o, coll):
    for c in list(o.users_collection):
        c.objects.unlink(o)
    coll.objects.link(o)


def new_coll(name):
    c = bpy.data.collections.new(name)
    scene.collection.children.link(c)
    return c


def scene_driver(idb, path, index=-1, scale=1.0, offset=0.0):
    """Drive any property from scene["xray"] (0 = normal film, 1 = X-ray look)."""
    fc = idb.driver_add(path, index) if index >= 0 else idb.driver_add(path)
    d = fc.driver
    d.type = "SCRIPTED"
    v = d.variables.new(); v.name = "x"; v.type = "SINGLE_PROP"
    v.targets[0].id_type = "SCENE"; v.targets[0].id = scene; v.targets[0].data_path = '["xray"]'
    d.expression = f"x*{scale}+{offset}"
    return fc


# ---------------------------------------------------------------- car rig: everything inside the car rides on it
car_root = bpy.data.objects.new("CarRig", None); link(car_root)
rig.parent = car_root
CAR = new_coll("Car")
WORLD = new_coll("Scenery")

# materials
dash_mat = add_noise_bump(principled("DashPlastic", (0.035, 0.035, 0.038), 0.55), scale=220, strength=0.08)
trim_mat = principled("TrimGrey", (0.12, 0.12, 0.125), 0.45)
seat_mat = add_noise_bump(principled("SeatFabric", (0.04, 0.042, 0.05), 0.9, **{"Sheen Weight": 0.12}), scale=400, strength=0.25)
roof_mat = add_noise_bump(principled("Headliner", (0.42, 0.41, 0.39), 0.95), scale=300, strength=0.12)
wheel_mat = add_noise_bump(principled("WheelLeather", (0.02, 0.02, 0.02), 0.42), scale=500, strength=0.2)
chrome_mat = principled("Chrome", (0.8, 0.8, 0.82), 0.12, **{"Metallic": 1.0})
paint_mat = principled("CarPaint", (0.32, 0.04, 0.04), 0.22, **{"Coat Weight": 1.0, "Coat Roughness": 0.03})

glass = bpy.data.materials.new("Glass")
glass.use_nodes = True
gnt = glass.node_tree
gnt.nodes.clear()
g_out = gnt.nodes.new("ShaderNodeOutputMaterial")
g_tr = gnt.nodes.new("ShaderNodeBsdfTransparent"); g_tr.inputs[0].default_value = (0.88, 0.92, 0.9, 1)
g_gl = gnt.nodes.new("ShaderNodeBsdfGlossy"); g_gl.inputs["Roughness"].default_value = 0.03
g_lw = gnt.nodes.new("ShaderNodeLayerWeight"); g_lw.inputs["Blend"].default_value = 0.12
g_mx = gnt.nodes.new("ShaderNodeMixShader")
gnt.links.new(g_lw.outputs["Fresnel"], g_mx.inputs[0])
gnt.links.new(g_tr.outputs[0], g_mx.inputs[1]); gnt.links.new(g_gl.outputs[0], g_mx.inputs[2])
gnt.links.new(g_mx.outputs[0], g_out.inputs["Surface"])

FLOOR_Z = 0.40
CX = 0.38                                   # car centerline (driver sits at x=0, UK right-hand drive)
box("Floor", (CX, -0.2, FLOOR_Z - 0.02), (1.75, 2.2, 0.04), seat_mat, CAR, bevel=0)
for sx, nm in ((0.0, "Driver"), (0.76, "Pass")):
    box(f"{nm}Cushion", (sx, -0.13, 0.86), (0.52, 0.55, 0.13), seat_mat, CAR, bevel=0.05)
    box(f"{nm}Base", (sx, -0.1, 0.64), (0.46, 0.5, 0.32), trim_mat, CAR, bevel=0.03)
    box(f"{nm}Back", (sx, 0.22, 1.27), (0.52, 0.13, 0.72), seat_mat, CAR, bevel=0.05, rot=(math.radians(-14), 0, 0))
    box(f"{nm}Headrest", (sx, 0.31, 1.78), (0.27, 0.1, 0.19), seat_mat, CAR, bevel=0.04, rot=(math.radians(-8), 0, 0))
# dashboard: lower box, sloped top, instrument hood over the driver, centre console
box("DashLower", (CX, -0.82, 0.92), (1.8, 0.42, 0.42), dash_mat, CAR, bevel=0.05)
box("DashTop", (CX, -0.74, 1.13), (1.8, 0.5, 0.12), dash_mat, CAR, bevel=0.05, rot=(math.radians(-8), 0, 0))
box("Binnacle", (0.0, -0.6, 1.2), (0.36, 0.2, 0.1), dash_mat, CAR, bevel=0.04, rot=(math.radians(-15), 0, 0))
box("Console", (CX, -0.45, 0.62), (0.22, 0.75, 0.36), dash_mat, CAR, bevel=0.03)
box("ScreenBezel", (CX, -0.7, 1.12), (0.24, 0.03, 0.14), trim_mat, CAR, bevel=0.01, rot=(math.radians(-20), 0, 0))
scr = principled("Screen", (0.01, 0.01, 0.012), 0.2, **{"Emission Color": (0.15, 0.35, 0.6, 1), "Emission Strength": 0.6})
box("Screen", (CX, -0.715, 1.12), (0.21, 0.01, 0.12), scr, CAR, bevel=0, rot=(math.radians(-20), 0, 0))
# shell: roof, doors, pillars, windscreen
ROOF_Z = 1.93
box("Roof", (CX, 0.25, ROOF_Z), (1.75, 1.45, 0.04), roof_mat, CAR, bevel=0.01)
for side, x in (("R", -0.5), ("L", 1.26)):
    box(f"Door{side}", (x, -0.15, 0.85), (0.08, 1.3, 0.9), trim_mat, CAR, bevel=0.03)
    box(f"DoorTop{side}", (x, -0.15, 1.31), (0.11, 1.3, 0.05), dash_mat, CAR, bevel=0.02)
    box(f"BPillar{side}", (x, 0.52, 1.6), (0.08, 0.12, 0.64), roof_mat, CAR, bevel=0.02)
    win = box(f"Window{side}", (x, -0.15, 1.62), (0.01, 1.3, 0.6), glass, CAR, bevel=0)
    # A-pillar along the windscreen edge
    bpy.ops.mesh.primitive_cylinder_add(radius=0.035, depth=0.86, location=(x + (0.02 if side == "R" else -0.02), -0.76, 1.53),
                                        rotation=(math.radians(-50), 0, 0))
    ap = bpy.context.active_object; ap.name = f"APillar{side}"; ap.data.materials.append(roof_mat); move_to(ap, CAR)
ws = box("Windscreen", (CX, -0.77, 1.54), (1.76, 0.01, 0.86), glass, CAR, bevel=0, rot=(math.radians(-50), 0, 0))
box("RearWindow", (CX, 1.05, 1.5), (1.75, 0.01, 0.7), glass, CAR, bevel=0, rot=(math.radians(25), 0, 0))
box("Hood", (CX, -1.75, 1.08), (1.8, 1.5, 0.05), paint_mat, CAR, bevel=0.04, rot=(math.radians(4), 0, 0))
box("Mirror", (CX - 0.05, -0.5, 1.82), (0.24, 0.03, 0.07), trim_mat, CAR, bevel=0.015)
box("MirrorStem", (CX - 0.05, -0.47, 1.88), (0.02, 0.02, 0.08), trim_mat, CAR, bevel=0.005)
box("Visor", (0.0, -0.42, 1.89), (0.42, 0.18, 0.025), roof_mat, CAR, bevel=0.01, rot=(math.radians(-10), 0, 0))

# steering wheel on a tilted pivot; WHEEL_* are reused analytically for the hand IK targets
WHEEL_C = Vector((0.0, -0.30, 1.17))  # within reach of the reclined driver's IK arms
WHEEL_TILT = math.radians(68)
WHEEL_R = 0.18
pivot = bpy.data.objects.new("WheelPivot", None); link(pivot, CAR)
pivot.location = WHEEL_C; pivot.rotation_euler = (WHEEL_TILT, 0, 0)
spin = bpy.data.objects.new("WheelSpin", None); link(spin, CAR); spin.parent = pivot
bpy.ops.mesh.primitive_torus_add(major_radius=WHEEL_R, minor_radius=0.016, major_segments=64, minor_segments=16)
rim = bpy.context.active_object; rim.name = "WheelRim"; rim.data.materials.append(wheel_mat); move_to(rim, CAR)
bpy.ops.object.shade_smooth()
rim.parent = spin
bpy.ops.mesh.primitive_cylinder_add(radius=0.055, depth=0.05, location=(0, 0, -0.02))
hub = bpy.context.active_object; hub.name = "WheelHub"; hub.data.materials.append(wheel_mat); move_to(hub, CAR); hub.parent = spin
bpy.ops.object.shade_smooth()
for a in (0, 180, 270):
    bpy.ops.mesh.primitive_cylinder_add(radius=0.012, depth=WHEEL_R, location=(0, 0, -0.01))
    sp = bpy.context.active_object; sp.name = f"Spoke{a}"; sp.data.materials.append(trim_mat); move_to(sp, CAR)
    sp.rotation_euler = (0, math.radians(90), math.radians(a))
    sp.location = (math.cos(math.radians(a)) * WHEEL_R / 2, math.sin(math.radians(a)) * WHEEL_R / 2, -0.01)
    sp.parent = spin
bpy.ops.mesh.primitive_cylinder_add(radius=0.035, depth=0.35, location=(0, 0, -0.2))
col = bpy.context.active_object; col.name = "Column"; col.data.materials.append(dash_mat); move_to(col, CAR); col.parent = pivot
for o in CAR.objects:
    if o.parent is None:
        o.parent = car_root


def wheel_point(angle_deg, steer_deg):
    """World (car-space) point on the rim at clock angle (0 = driver's 3 o'clock, CCW)."""
    q = Quaternion((1, 0, 0), WHEEL_TILT)
    a = math.radians(angle_deg + steer_deg)
    return WHEEL_C + q @ Vector((WHEEL_R * math.cos(a), WHEEL_R * math.sin(a), 0))


# ---------------------------------------------------------------- scenery (moves past the car)
scen = bpy.data.objects.new("SceneryMover", None); link(scen, WORLD)
SPEED = 13.0  # m/s (~47 km/h country lane)
ROAD_X = CX - 1.6
asphalt = principled("Asphalt", (0.06, 0.06, 0.062), 0.75)
color_variation(asphalt, (0.045, 0.045, 0.048), (0.09, 0.09, 0.09), scale=0.6)
add_noise_bump(asphalt, scale=90, strength=0.3)
line_mat = principled("RoadLine", (0.85, 0.85, 0.8), 0.5)
grass = principled("Grass", (0.1, 0.2, 0.04), 0.85)
color_variation(grass, (0.07, 0.16, 0.03), (0.2, 0.28, 0.07), scale=0.15)
add_noise_bump(grass, scale=40, strength=0.4)
distance_haze(grass)
leaf = principled("Leaves", (0.05, 0.13, 0.03), 0.7, **{"Subsurface Weight": 0.15})
color_variation(leaf, (0.03, 0.09, 0.02), (0.14, 0.24, 0.05), scale=2.5)
add_noise_bump(leaf, scale=12, strength=0.6)
distance_haze(leaf)
bark = principled("Bark", (0.07, 0.05, 0.035), 0.9)
wood = principled("PoleWood", (0.16, 0.11, 0.07), 0.8)

Y0, Y1 = -900.0, 200.0                       # scenery span; car covers ~SPEED*35 s = 455 m
L = Y1 - Y0
bpy.ops.mesh.primitive_plane_add(size=1, location=(ROAD_X, (Y0 + Y1) / 2, 0.0))
road = bpy.context.active_object; road.name = "Road"; road.scale = (7.0, L, 1)
road.data.materials.append(asphalt); move_to(road, WORLD)
bpy.ops.mesh.primitive_plane_add(size=1, location=(ROAD_X, (Y0 + Y1) / 2, -0.03))
fld = bpy.context.active_object; fld.name = "Fields"; fld.scale = (1400, L + 600, 1)
fld.data.materials.append(grass); move_to(fld, WORLD)
for x in (ROAD_X - 3.35, ROAD_X + 3.35):
    bpy.ops.mesh.primitive_plane_add(size=1, location=(x, (Y0 + Y1) / 2, 0.005))
    e = bpy.context.active_object; e.name = "EdgeLine"; e.scale = (0.1, L, 1)
    e.data.materials.append(line_mat); move_to(e, WORLD)
bpy.ops.mesh.primitive_plane_add(size=1, location=(ROAD_X, 0, 0.005))
dash = bpy.context.active_object; dash.name = "CentreDash"; dash.scale = (0.1, 3.0, 1)
dash.data.materials.append(line_mat); move_to(dash, WORLD)
arr = dash.modifiers.new("Arr", "ARRAY"); arr.count = int(L / 9); arr.relative_offset_displace = (0, 3.0, 0)
dash.location.y = Y0

# hedgerows: long noisy boxes either side of the lane (big near-field motion cue)
for i, x in enumerate((ROAD_X - 4.6, ROAD_X + 4.4)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, (Y0 + Y1) / 2, 0.9))
    h = bpy.context.active_object; h.name = f"Hedge{i}"; h.scale = (1.4, L, 1.8)
    bpy.ops.object.transform_apply(scale=True)
    rm = h.modifiers.new("Rm", "REMESH"); rm.mode = "VOXEL"; rm.voxel_size = 0.35
    tex = bpy.data.textures.new(f"HedgeTex{i}", "CLOUDS"); tex.noise_scale = 1.2
    dp = h.modifiers.new("Disp", "DISPLACE"); dp.texture = tex; dp.strength = 0.9; dp.mid_level = 0.5
    h.data.materials.append(leaf); move_to(h, WORLD)
    bpy.ops.object.shade_smooth()

# tree variants, instanced along both sides
tree_protos = []
for v in range(3):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, radius=1.0, location=(0, 0, 0))
    can = bpy.context.active_object
    can.scale = (2.4 + v * 0.5, 2.4 + v * 0.4, 2.0 + v * 0.6)
    tex = bpy.data.textures.new(f"TreeTex{v}", "CLOUDS"); tex.noise_scale = 0.7 + 0.2 * v
    dp = can.modifiers.new("Disp", "DISPLACE"); dp.texture = tex; dp.strength = 1.1
    bpy.context.view_layer.objects.active = can
    bpy.ops.object.modifier_apply(modifier="Disp")
    bpy.ops.object.transform_apply(scale=True)
    can.location = (0, 0, 4.4 + v * 0.8)
    can.data.materials.append(leaf)
    bpy.ops.object.shade_smooth()
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.22, depth=4.6, location=(0, 0, 2.3))
    trunk = bpy.context.active_object; trunk.data.materials.append(bark)
    can.select_set(True); trunk.select_set(True); bpy.context.view_layer.objects.active = can
    bpy.ops.object.join()
    can.name = f"TreeProto{v}"; can.location = (0, 0, -500)
    move_to(can, WORLD)
    tree_protos.append(can)
scenery_objs = [road, fld, dash] + [o for o in WORLD.objects if o.name.startswith(("EdgeLine", "Hedge"))]
y = Y0
while y < Y1:
    for side in (-1, 1):
        if random.random() < 0.55:
            proto = random.choice(tree_protos)
            t = bpy.data.objects.new("Tree", proto.data); link(t, WORLD)
            d = random.uniform(7, 16) if random.random() < 0.6 else random.uniform(16, 80)
            t.location = (ROAD_X + side * (3.5 + d), y + random.uniform(-3, 3), 0)
            s = random.uniform(0.8, 1.35); t.scale = (s, s, s * random.uniform(0.9, 1.2))
            t.rotation_euler.z = random.uniform(0, 6.28)
            scenery_objs.append(t)
    y += random.uniform(5, 11)
# telegraph poles on the driver's side every ~45 m
bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=0.13, depth=8.5, location=(0, 0, 4.25))
pole = bpy.context.active_object; pole.name = "PoleProto"; pole.data.materials.append(wood); pole.location.z = -500
move_to(pole, WORLD)
for i, py in enumerate(range(int(Y0), int(Y1), 45)):
    p = bpy.data.objects.new(f"Pole{i}", pole.data); link(p, WORLD)
    p.location = (ROAD_X - 6.0, py, 0); scenery_objs.append(p)
for o in WORLD.objects:
    if o is not scen and o.parent is None:
        o.parent = scen
bake(scen, "location", [SPEED * (f - 1) / FPS for f in FRAMES], index=1)

# ---------------------------------------------------------------- lighting + world (sky <-> X-ray void)
scene["xray"] = 0.0
P.sky_world(scene, sun_elev=math.radians(38), sun_rot=math.radians(-60), strength=0.9)
wnt = scene.world.node_tree
bg = next(n for n in wnt.nodes if n.type == "BACKGROUND")
wout = next(n for n in wnt.nodes if n.type == "OUTPUT_WORLD")
void = wnt.nodes.new("ShaderNodeBackground"); void.inputs["Color"].default_value = (0.004, 0.012, 0.03, 1)
void.inputs["Strength"].default_value = 1.0
wmix = wnt.nodes.new("ShaderNodeMixShader")
wnt.links.new(bg.outputs[0], wmix.inputs[1]); wnt.links.new(void.outputs[0], wmix.inputs[2])
wnt.links.new(wmix.outputs[0], wout.inputs[0])
scene_driver(wmix.inputs[0], "default_value")

sun = P.sun_light("Sun", (math.radians(52), 0, math.radians(32)), 4.5, (1.0, 0.9, 0.78), angle=0.02)
face_key = P.area_light("CabinKey", (0.55, -0.62, 1.78), (0, 0.0, 1.64), 14, 0.6, (1.0, 0.95, 0.9))
dash_bounce = P.area_light("DashBounce", (0.1, -0.62, 1.2), (0, 0.0, 1.55), 10, 0.8, (0.9, 0.95, 1.0))
rim_l = P.area_light("RimDriverWin", (-0.45, 0.25, 1.75), (0, 0.0, 1.62), 25, 0.5, (0.85, 0.92, 1.0))
for l in (face_key, dash_bounce, rim_l):
    l.parent = car_root

# ---------------------------------------------------------------- X-ray look on every hero material
def xray_group():
    ng = bpy.data.node_groups.new("XRayShell", "ShaderNodeTree")
    ng.interface.new_socket("Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
    N, Lk = ng.nodes, ng.links
    o = N.new("NodeGroupOutput")
    lw = N.new("ShaderNodeLayerWeight"); lw.inputs["Blend"].default_value = 0.35
    rmp = N.new("ShaderNodeMapRange"); rmp.inputs[1].default_value = 0.15; rmp.inputs[2].default_value = 0.9
    Lk.new(lw.outputs["Facing"], rmp.inputs[0])
    pw = N.new("ShaderNodeMath"); pw.operation = "POWER"; pw.inputs[1].default_value = 1.6
    Lk.new(rmp.outputs[0], pw.inputs[0])
    em = N.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (0.32, 0.72, 1.0, 1)
    em.inputs["Strength"].default_value = 2.2
    tr = N.new("ShaderNodeBsdfTransparent")
    mx = N.new("ShaderNodeMixShader")
    k = N.new("ShaderNodeMath"); k.operation = "MULTIPLY"; k.inputs[1].default_value = 0.55
    Lk.new(pw.outputs[0], k.inputs[0])
    Lk.new(k.outputs[0], mx.inputs[0]); Lk.new(tr.outputs[0], mx.inputs[1]); Lk.new(em.outputs[0], mx.inputs[2])
    Lk.new(mx.outputs[0], o.inputs[0])
    return ng


XG = xray_group()
done = set()
for o in hero_objs:
    for slot in o.material_slots:
        m = slot.material
        if not m or m.name in done or not m.use_nodes:
            continue
        done.add(m.name)
        nt = m.node_tree
        outn = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None)
        if outn is None or not outn.inputs["Surface"].links:
            continue
        src = outn.inputs["Surface"].links[0].from_socket
        g = nt.nodes.new("ShaderNodeGroup"); g.node_tree = XG
        mx = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(src, mx.inputs[1]); nt.links.new(g.outputs[0], mx.inputs[2])
        nt.links.new(mx.outputs[0], outn.inputs["Surface"])
        scene_driver(mx.inputs[0], "default_value")
        if m.blend_method != "OPAQUE" or True:
            pass
print("XRAY_MATS", sorted(done))


# ---------------------------------------------------------------- anatomy (built in REST pose, ridden on bones)
def parent_rest(obj, bone):
    """Parent to a bone so the object sits at its current world spot when the rig is in REST pose."""
    b = rig.data.bones[MX + bone]
    obj.parent, obj.parent_type, obj.parent_bone = rig, "BONE", MX + bone
    rest = rig.matrix_world @ b.matrix_local @ Matrix.Translation((0, b.length, 0))
    obj.matrix_parent_inverse = rest.inverted()


rig.data.pose_position = "REST"
bpy.context.view_layer.update()
deps = bpy.context.evaluated_depsgraph_get()
# MPFB deletes skin hidden under clothing, so sample the neck from body + suit together
mid = []
for o in (body, bpy.data.objects["Hero.male_casualsuit05"]):
    em = o.evaluated_get(deps).to_mesh()
    mid += [o.matrix_world @ v.co for v in em.vertices if abs(v.co.x) < 0.015]
    o.evaluated_get(deps).to_mesh_clear()
neck_front = min(v.y for v in mid if 1.50 < v.z < 1.55)
neck_back = max(v.y for v in mid if 1.50 < v.z < 1.55)
chest_front = min(v.y for v in mid if 1.30 < v.z < 1.36)
nose_tip = min(mid, key=lambda c: c.y if 1.62 < c.z < 1.72 else 9)
rig.data.pose_position = "POSE"
print("ANAT neck_front", neck_front, "neck_back", neck_back, "chest_front", chest_front, "nose", tuple(nose_tip))

ANAT = new_coll("Anatomy")
TR_TOP, TR_BOT = 1.515, 1.37
TR_Y = neck_front + 0.024
TR_R = 0.0105
TR_MID = Vector((0, TR_Y, (TR_TOP + TR_BOT) / 2))
TEAR_DIR = Vector((0.62, -0.78, 0)).normalized()
TEAR_POS = TR_MID + TEAR_DIR * TR_R + Vector((0, 0, 0.018))


def flesh(name, color, sss=0.5, alpha=None, emit=0.0):
    m = principled(name, color, 0.38, **{"Subsurface Weight": sss, "Subsurface Scale": 0.01,
                                         "Coat Weight": 0.5, "Coat Roughness": 0.15})
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Subsurface Radius"].default_value = (1.0, 0.3, 0.2)
    if emit:
        b.inputs["Emission Color"].default_value = (*color, 1)
        b.inputs["Emission Strength"].default_value = emit
    if alpha is not None:
        b.inputs["Alpha"].default_value = alpha
    return m


def trachea_material():
    m = flesh("TracheaWall", (0.62, 0.2, 0.2), sss=0.6, alpha=0.62, emit=0.0)
    nt = m.node_tree; N, Lk = nt.nodes, nt.links
    b = N["Principled BSDF"]
    tc = N.new("ShaderNodeTexCoord")
    # tear: jagged vertical slit around TEAR_POS (object space), opening with TearOpen
    center = N.new("ShaderNodeVectorMath"); center.operation = "SUBTRACT"
    center.inputs[1].default_value = TEAR_POS - TR_MID
    Lk.new(tc.outputs["Object"], center.inputs[0])
    sq = N.new("ShaderNodeMapping"); sq.inputs["Scale"].default_value = (1.0, 1.0, 0.28)
    Lk.new(center.outputs[0], sq.inputs["Vector"])
    ln = N.new("ShaderNodeVectorMath"); ln.operation = "LENGTH"; Lk.new(sq.outputs[0], ln.inputs[0])
    ln_out = ln.outputs["Value"]  # LENGTH writes the scalar socket; outputs[0] (Vector) stays zero
    jag = N.new("ShaderNodeTexNoise"); jag.inputs["Scale"].default_value = 900; jag.inputs["Detail"].default_value = 3
    Lk.new(tc.outputs["Object"], jag.inputs["Vector"])
    jj = N.new("ShaderNodeMath"); jj.operation = "MULTIPLY_ADD"; jj.inputs[1].default_value = 0.0025
    Lk.new(jag.outputs["Fac"], jj.inputs[0]); Lk.new(ln_out, jj.inputs[2])
    tear = N.new("ShaderNodeValue"); tear.name = "TearOpen"; tear.outputs[0].default_value = 0.0
    tscale = N.new("ShaderNodeMath"); tscale.operation = "MULTIPLY"; tscale.inputs[1].default_value = 0.0034
    Lk.new(tear.outputs[0], tscale.inputs[0])
    hole = N.new("ShaderNodeMath"); hole.operation = "LESS_THAN"
    Lk.new(jj.outputs[0], hole.inputs[0]); Lk.new(tscale.outputs[0], hole.inputs[1])
    rimw = N.new("ShaderNodeMath"); rimw.operation = "MULTIPLY"; rimw.inputs[1].default_value = 1.9
    Lk.new(tscale.outputs[0], rimw.inputs[0])
    rim = N.new("ShaderNodeMath"); rim.operation = "LESS_THAN"
    Lk.new(jj.outputs[0], rim.inputs[0]); Lk.new(rimw.outputs[0], rim.inputs[1])
    # pressure: whole wall flushes red/glows
    press = N.new("ShaderNodeValue"); press.name = "Pressure"; press.outputs[0].default_value = 0.0
    em_col = N.new("ShaderNodeMix"); em_col.data_type = "RGBA"
    em_col.inputs["A"].default_value = (1.0, 0.18, 0.08, 1); em_col.inputs["B"].default_value = (0.02, 0.0, 0.0, 1)
    Lk.new(hole.outputs[0], em_col.inputs["Factor"])
    em_str = N.new("ShaderNodeMath"); em_str.operation = "MULTIPLY_ADD"; em_str.inputs[1].default_value = 6.0
    Lk.new(rim.outputs[0], em_str.inputs[0]); Lk.new(press.outputs[0], em_str.inputs[2])
    Lk.new(em_col.outputs["Result"], b.inputs["Emission Color"])
    Lk.new(em_str.outputs[0], b.inputs["Emission Strength"])
    # the hole itself is see-through dark
    alpha = N.new("ShaderNodeMix"); alpha.data_type = "FLOAT"
    alpha.inputs["A"].default_value = 0.62; alpha.inputs["B"].default_value = 0.15
    Lk.new(hole.outputs[0], alpha.inputs["Factor"]); Lk.new(alpha.outputs["Result"], b.inputs["Alpha"])
    return m, tear, press


ANAT_OBJS = []
tr_mat, tear_val, press_val = trachea_material()
ring_mat = flesh("Cartilage", (0.86, 0.72, 0.66), sss=0.4, alpha=0.9)
air_mat = principled("AirFlow", (0, 0, 0), 0.5)
ant = air_mat.node_tree
ab = ant.nodes["Principled BSDF"]
atc = ant.nodes.new("ShaderNodeTexCoord")
amap = ant.nodes.new("ShaderNodeMapping"); amap.name = "AirMap"; amap.inputs["Scale"].default_value = (90, 90, 25)
ant.links.new(atc.outputs["Object"], amap.inputs["Vector"])
anoise = ant.nodes.new("ShaderNodeTexNoise"); anoise.inputs["Detail"].default_value = 4
ant.links.new(amap.outputs[0], anoise.inputs["Vector"])
aval = ant.nodes.new("ShaderNodeValue"); aval.name = "AirFlowStrength"; aval.outputs[0].default_value = 0
amul = ant.nodes.new("ShaderNodeMath"); amul.operation = "MULTIPLY"
ant.links.new(anoise.outputs["Fac"], amul.inputs[0]); ant.links.new(aval.outputs[0], amul.inputs[1])
ab.inputs["Emission Color"].default_value = (0.35, 0.8, 1.0, 1)
ant.links.new(amul.outputs[0], ab.inputs["Emission Strength"])
ab.inputs["Alpha"].default_value = 0.0
aalpha = ant.nodes.new("ShaderNodeMath"); aalpha.operation = "MULTIPLY"; aalpha.inputs[1].default_value = 0.25
ant.links.new(amul.outputs[0], aalpha.inputs[0]); ant.links.new(aalpha.outputs[0], ab.inputs["Alpha"])

bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=TR_R, depth=TR_TOP - TR_BOT, location=TR_MID, end_fill_type="NOTHING")
trachea = bpy.context.active_object; trachea.name = "Trachea"
sub = trachea.modifiers.new("Sub", "SUBSURF"); sub.levels = sub.render_levels = 2
bpy.ops.object.shade_smooth()
trachea.data.materials.append(tr_mat); move_to(trachea, ANAT)
ANAT_OBJS.append(trachea)
for i in range(13):
    z = TR_BOT + 0.006 + i * (TR_TOP - TR_BOT - 0.012) / 12
    bpy.ops.mesh.primitive_torus_add(major_radius=TR_R + 0.0008, minor_radius=0.0022, major_segments=40, minor_segments=8,
                                     location=(0, TR_Y, z))
    rg = bpy.context.active_object; rg.name = f"TrRing{i}"; rg.scale = (1, 1, 0.75)
    rg.data.materials.append(ring_mat); move_to(rg, ANAT); bpy.ops.object.shade_smooth()
    rg.parent = trachea; rg.matrix_parent_inverse = trachea.matrix_world.inverted()
bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=TR_R * 0.72, depth=TR_TOP - TR_BOT, location=TR_MID)
air = bpy.context.active_object; air.name = "AirColumn"; air.data.materials.append(air_mat); move_to(air, ANAT)
air.parent = trachea; air.matrix_parent_inverse = trachea.matrix_world.inverted()
# larynx (Adam's apple) cap
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.014, location=(0, TR_Y - 0.002, TR_TOP + 0.008))
lar = bpy.context.active_object; lar.name = "Larynx"; lar.scale = (1.15, 0.8, 0.9)
lar.data.materials.append(ring_mat); move_to(lar, ANAT); bpy.ops.object.shade_smooth(); ANAT_OBJS.append(lar)
# bronchi + lungs
lung_mat = flesh("Lung", (0.78, 0.32, 0.34), sss=0.7, alpha=0.82)
add_noise_bump(lung_mat, scale=140, strength=0.35)
lungs = []
for sx in (1, -1):
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.0075, depth=0.06,
                                        location=(0.022 * sx, TR_Y + 0.004, TR_BOT - 0.022),
                                        rotation=(0, math.radians(-38 * sx), 0))
    br = bpy.context.active_object; br.name = f"Bronchus{sx}"; br.data.materials.append(ring_mat)
    move_to(br, ANAT); bpy.ops.object.shade_smooth(); ANAT_OBJS.append(br)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=32, radius=1, location=(0.082 * sx, TR_Y + 0.03, 1.25))
    lu = bpy.context.active_object; lu.name = f"Lung{sx}"; lu.scale = (0.062, 0.07, 0.135)
    bpy.ops.object.transform_apply(scale=True)
    lt = bpy.data.textures.new(f"LungTex{sx}", "CLOUDS"); lt.noise_scale = 0.05
    dp = lu.modifiers.new("Disp", "DISPLACE"); dp.texture = lt; dp.strength = 0.012
    bpy.ops.object.shade_smooth()
    lu.data.materials.append(lung_mat); move_to(lu, ANAT); ANAT_OBJS.append(lu); lungs.append(lu)
# cervical / thoracic spine behind the windpipe for anatomical context
bone_mat = flesh("Bone", (0.85, 0.82, 0.74), sss=0.2, alpha=0.85)
spine_y = neck_back - 0.045
for i in range(11):
    z = 1.56 - i * 0.026
    bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.017, depth=0.017, location=(0, spine_y + i * 0.0012, z))
    vb = bpy.context.active_object; vb.name = f"Vert{i}"; vb.data.materials.append(bone_mat)
    bv = vb.modifiers.new("Bevel", "BEVEL"); bv.width = 0.004; bv.segments = 3
    move_to(vb, ANAT); bpy.ops.object.shade_smooth(); ANAT_OBJS.append(vb)

# air-jet particles (out of the tear) and trapped air bubbles under the skin
jet_mat = principled("AirJet", (0.4, 0.85, 1.0), 0.4, **{"Emission Color": (0.45, 0.85, 1.0, 1), "Emission Strength": 6.0})
bub_mat = bpy.data.materials.new("Bubble"); bub_mat.use_nodes = True
bnt = bub_mat.node_tree; bnt.nodes.clear()
bo = bnt.nodes.new("ShaderNodeOutputMaterial")
blw = bnt.nodes.new("ShaderNodeLayerWeight"); blw.inputs["Blend"].default_value = 0.3
bem = bnt.nodes.new("ShaderNodeEmission"); bem.inputs["Color"].default_value = (0.75, 0.92, 1.0, 1); bem.inputs["Strength"].default_value = 4
btr = bnt.nodes.new("ShaderNodeBsdfTransparent")
bmx = bnt.nodes.new("ShaderNodeMixShader")
bnt.links.new(blw.outputs["Facing"], bmx.inputs[0]); bnt.links.new(btr.outputs[0], bmx.inputs[1])
bnt.links.new(bem.outputs[0], bmx.inputs[2]); bnt.links.new(bmx.outputs[0], bo.inputs["Surface"])
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1.0, location=(0, 0, -50))
dot = bpy.context.active_object; dot.name = "DotProto"; move_to(dot, ANAT); bpy.ops.object.shade_smooth()
dot_mesh_jet = dot.data.copy(); dot_mesh_jet.materials.append(jet_mat)
dot_mesh_bub = dot.data.copy(); dot_mesh_bub.materials.append(bub_mat)
bpy.data.objects.remove(dot)

particles = []   # (obj, [loc per frame], [scale per frame])


def make_jet(t0, n=36):
    for i in range(n):
        o = bpy.data.objects.new("Jet", dot_mesh_jet); link(o, ANAT)
        born = t0 + random.uniform(0, 14)
        d = (TEAR_DIR + Vector((random.uniform(-0.6, 0.6), random.uniform(-0.3, 0.3), random.uniform(-0.6, 0.6)))).normalized()
        speed = random.uniform(0.0025, 0.0045)
        r = random.uniform(0.0007, 0.0016)
        locs, scales = [], []
        for f in FRAMES:
            age = f - born
            if age < 0:
                locs.append(TEAR_POS); scales.append(0.0)
                continue
            dist = speed * 9 * (1 - math.exp(-age / 9))
            locs.append(TEAR_POS + d * dist)
            scales.append(r * max(0.0, 1 - age / 26))
        particles.append((o, locs, scales))


def make_bubbles(n=160):
    for i in range(n):
        o = bpy.data.objects.new("Bubble", dot_mesh_bub); link(o, ANAT)
        born = TEAR + random.uniform(4, 190)
        gone = random.uniform(rmap(800), rmap(858))
        a = random.uniform(-2.4, 2.4)
        rad = random.uniform(0.016, 0.045)
        p = Vector((math.sin(a) * rad, TR_Y + 0.006 - math.cos(a) * rad * 0.9, random.uniform(1.37, 1.53)))
        r = random.uniform(0.0012, 0.0034)
        locs, scales = [], []
        for f in FRAMES:
            grow = ramp(f, born, born + 8) * (1 - ramp(f, gone, gone + 4))
            jit = 0.0006 * env(f, rmap(690), rmap(700), rmap(760), rmap(770)) * math.sin(f * 2.1 + i)   # "crackle" when pressed
            locs.append(p + Vector((jit, 0, 0)))
            scales.append(r * grow)
        particles.append((o, locs, scales))


make_jet(TEAR_HOOK)
make_jet(TEAR)
make_bubbles()
for o in ANAT.objects:
    if o.parent is None:
        parent_rest(o, "Spine2")
for o, locs, scales in particles:
    # particle coordinates are rest-pose; convert them into the bone-parented local space
    inv = o.matrix_parent_inverse
    bake_vec(o, "location", [inv @ v for v in locs])
    bake_vec(o, "scale", [(s, s, s) for s in scales])
    o.matrix_parent_inverse = Matrix.Identity(4)

organ_key = P.area_light("OrganKey", (0.5, -0.9, 1.7), (0, TR_Y, 1.42), 0, 0.8, (1.0, 0.92, 0.88))
organ_fill = P.area_light("OrganFill", (-0.5, -0.6, 1.3), (0, TR_Y, 1.4), 0, 1.0, (0.5, 0.7, 1.0))
for l, e in ((organ_key, 14), (organ_fill, 6)):
    l.parent = car_root
    scene_driver(l.data, "energy", scale=e)
for l, e in ((face_key, 14), (dash_bounce, 10), (rim_l, 25)):
    scene_driver(l.data, "energy", scale=-e, offset=e)
scene_driver(sun.data, "energy", scale=-4.5, offset=4.5)

# ---------------------------------------------------------------- rig setup: IK hands on the wheel, neck swell
for side in ("Left", "Right"):
    t = bpy.data.objects.new(f"IK_{side}", None); link(t, CAR); t.parent = car_root
    c = rig.pose.bones[MX + side + "ForeArm"].constraints.new("IK")
    c.name = "IK"; c.target = t; c.chain_count = 2; c.use_tail = True
    pole = bpy.data.objects.new(f"Pole_{side}", None); link(pole, CAR); pole.parent = car_root
    sx = 1 if side == "Left" else -1
    pole.location = (0.55 * sx, 0.25, 0.85)
    c.pole_target = pole; c.pole_angle = math.radians(-90 if side == "Left" else -90)
aim = bpy.data.objects.new("AimR", None); link(aim, CAR); aim.parent = car_root
dt = rig.pose.bones[MX + "RightHand"].constraints.new("DAMPED_TRACK")
dt.name = "DT"; dt.target = aim; dt.track_axis = "TRACK_Y"; dt.influence = 0
rig.data.bones[MX + "Head"].inherit_scale = "NONE"

# ---------------------------------------------------------------- performance
REST = {pb.name: pb.bone.matrix_local.to_quaternion() for pb in rig.pose.bones}
X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))


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
    LEGS.update(aim_chain([(f"{side}UpLeg", (0.12 * sx, -1, -0.08)), (f"{side}Leg", (0.04 * sx, -0.42, -1)),
                           (f"{side}Foot", (0.02 * sx, -1, -0.75))]))
FINGERS = [b.name[len(MX):] for b in rig.data.bones if "Hand" in b.name and b.name[-1] in "123"]
BLINKS = [rmap(f) for f in (60, 128, 200, 330, 520, 610, 700, 845, 890, 945, 1030)]


def curves(f):
    """All high-level acting channels for frame f, 0..1."""
    hook = 1.0 if f < BEAT[1] else 0.0
    c = {}
    c["pinch"] = max(hook, env(f, rmap(186), rmap(205), rmap(562), rmap(580)))
    c["neckhand"] = env(f, rmap(568), rmap(592), rmap(868), rmap(892))
    c["strain"] = max(hook, env(f, rmap(214), rmap(232), rmap(548), rmap(566)))
    c["jolt"] = spike(f, JOLT_HOOK) * hook + spike(f, JOLT) * (1 - hook)
    c["twitch"] = env(f, rmap(136), rmap(141), rmap(168), rmap(176)) * (0.55 + 0.45 * math.sin(f * 1.4))
    c["inhale"] = env(f, rmap(150), rmap(166), rmap(186), rmap(200)) + env(f, SNEEZE - 40, SNEEZE - 10, SNEEZE - 2, SNEEZE + 1)
    c["sneeze"] = spike(f, SNEEZE, rise=2, decay=9)
    c["pain"] = max(env(f, rmap(34), rmap(40), BEAT[1] - 1, BEAT[1]) * hook,
                    env(f, TEAR - 4, TEAR + 4, rmap(862), rmap(882)))
    c["swell"] = env(f, TEAR + 6, TEAR + 110, rmap(850), rmap(905))
    c["turn"] = env(f, rmap(622), rmap(640), rmap(646), rmap(664))
    c["ouch"] = spike(f, rmap(641), rise=2, decay=8)
    c["relief"] = env(f, rmap(872), rmap(892), rmap(930), rmap(945)) + env(f, rmap(1000), rmap(1016), 99999, 100000)
    c["tremble"] = c["strain"] * (0.6 + 0.4 * math.sin(f * 0.21))
    c["blink"] = max((env(f, b - 1, b + 1, b + 3, b + 6) for b in BLINKS), default=0)
    c["steer"] = 3.5 * math.sin(f / FPS * 2 * math.pi / 7.0) + 1.5 * wobble(f, 3, 0.3)
    return c


ROT = {}      # bone -> list of quaternions
SHAPES = {}   # shape key -> list of values
SCALE_NECK = []
for f in FRAMES:
    c = curves(f)
    breath = math.sin(f / FPS * 2 * math.pi / 3.8)
    tr = c["tremble"]
    jit = lambda s: 0.7 * tr * math.sin(f * 2.9 + s)  # noqa: E731
    lean = 7 * c["jolt"] + 9 * c["sneeze"]
    poses = {
        "Hips": [(Z, 0.6 * wobble(f, 1))],
        "Spine": [(X, -7 + 0.4 * breath + 2 * lean / 7), (Z, 0.8 * wobble(f, 2))],
        "Spine1": [(X, -3 + 0.6 * breath + lean + 2 * c["pain"] - 2 * c["inhale"])],
        "Spine2": [(X, 2 + 0.7 * breath + lean - 3 * c["inhale"])],
        "Neck": [(X, 5 + 0.5 * lean - 4 * c["inhale"] + 4 * c["pain"] + jit(1)),
                 (Z, 1.5 * wobble(f, 4) + 7 * c["turn"])],
        "Head": [(X, 1 + 1.2 * lean - 9 * c["inhale"] - 3 * c["strain"] + jit(2) + 1.2 * wobble(f, 7, 0.6)),
                 (Z, 2.0 * wobble(f, 5, 0.5) * (1 - c["strain"]) + 16 * c["turn"] - 6 * c["ouch"] + jit(3)),
                 (Y, 1.2 * wobble(f, 6) - 5 * c["pain"] * (1 - c["neckhand"] * 0.5))],
        "LeftShoulder": [(Y, 3 * c["jolt"] + 5 * c["pain"] + 3 * c["inhale"]), (X, 0.5 * breath)],
        "RightShoulder": [(Y, -3 * c["jolt"] - 5 * c["pain"] - 3 * c["inhale"]), (X, 0.5 * breath)],
    }
    for name, rots in poses.items():
        q = Quaternion()
        for axis, deg in rots:
            q = q @ bq(name, axis, deg)
        ROT.setdefault(name, []).append(q)
    for name, q in LEGS.items():
        ROT.setdefault(name, []).append(q)
    # fingers: wheel grip / pinch / flat on neck
    p, n = c["pinch"], c["neckhand"]
    for name in FINGERS:
        joint = int(name[-1])
        grip = {1: 52, 2: 70, 3: 48}[joint]
        if "Thumb" in name:
            grip = {1: 10, 2: 25, 3: 20}[joint]
        if name.startswith("Right"):
            if "Index" in name:
                pinch = {1: 18, 2: 32, 3: 20}[joint]
            elif "Thumb" in name:
                pinch = {1: 15, 2: 20, 3: 12}[joint]
            else:
                pinch = {1: 70, 2: 85, 3: 55}[joint]
            flat = 15
            curl = grip * (1 - p - n) + pinch * p + flat * n
        else:
            curl = grip
        ROT.setdefault(name, []).append(Quaternion((1, 0, 0), math.radians(curl)))
    SCALE_NECK.append(1 + 0.16 * c["swell"])

    s = {}
    strain, pain, inh, snz, rel = c["strain"], c["pain"], c["inhale"], c["sneeze"], c["relief"]
    joltf = c["jolt"]
    for side in ("Left", "Right"):
        s[f"eyeBlink{side}"] = min(1, c["blink"] + 0.55 * strain + 0.45 * inh + 1.0 * snz - 0.5 * joltf + 0.25 * pain)
        s[f"eyeSquint{side}"] = min(1, 0.8 * strain + 0.6 * pain + 0.3 * c["twitch"] + 0.3 * rel)
        s[f"eyeWide{side}"] = max(0, 0.9 * joltf * (1 - snz))
        s[f"browDown{side}"] = min(1, 0.75 * strain + 0.5 * pain + 0.7 * snz)
        s[f"browOuterUp{side}"] = 0.5 * inh + 0.4 * joltf
        s[f"noseSneer{side}"] = min(1, 0.45 * strain + 0.8 * c["twitch"] + 0.5 * inh + 0.8 * snz + 0.2 * pain)
        s[f"mouthPress{side}"] = 0.7 * strain * (1 - pain * 0.4)
        s[f"mouthStretch{side}"] = 0.55 * pain + 0.4 * snz
        s[f"mouthFrown{side}"] = 0.35 * pain + 0.1 * strain
        s[f"mouthUpperUp{side}"] = 0.25 * pain + 0.3 * c["twitch"] + 0.3 * snz
        s[f"mouthSmile{side}"] = 0.6 * rel
        s[f"cheekSquint{side}"] = 0.4 * rel + 0.3 * strain
    s["browInnerUp"] = min(1, 0.55 * pain + 0.5 * inh + 0.15 * rel)
    s["cheekPuff"] = min(1, 0.85 * strain + 0.3 * joltf)
    s["mouthRollLower"] = 0.35 * strain
    s["mouthRollUpper"] = 0.25 * strain
    s["mouthClose"] = 0.0
    s["jawOpen"] = max(0, 0.3 * inh + 0.55 * snz + 0.06 * pain - 0.0)
    s["mouthFunnel"] = 0.15 * inh
    for k, v in s.items():
        SHAPES.setdefault(k, []).append(max(0.0, min(1.0, v)))

for name, qs in ROT.items():
    for i in range(1, len(qs)):
        if qs[i].dot(qs[i - 1]) < 0:
            qs[i] = -qs[i]
    path = f'pose.bones["{MX}{name}"].rotation_quaternion'
    for i in range(4):
        bake(rig, path, [q[i] for q in qs], index=i)
for i in (0, 2):
    bake(rig, f'pose.bones["{MX}Neck"].scale', SCALE_NECK, index=i)
for o in face_meshes:
    key = o.data.shape_keys
    for name, vals in SHAPES.items():
        if name in key.key_blocks:
            bake(key, f'key_blocks["{name}"].value', vals)

# xray switch, organ shader values, organ motion
xr = [1.0 if in_xray(f) else 0.0 for f in FRAMES]
bake(scene, '["xray"]', xr, interp="CONSTANT")
bake(tr_mat.node_tree, f'nodes["{tear_val.name}"].outputs[0].default_value',
     [ramp(f, TEAR_HOOK, TEAR_HOOK + 6) * (1 if f < BEAT[1] else 0)
      + ramp(f, TEAR, TEAR + 5) * (1 - ramp(f, rmap(800), rmap(860))) for f in FRAMES])
press = [ramp(f, rmap(330), rmap(470)) * (1 - ramp(f, TEAR + 2, TEAR + 30)) + 0.6 * (1 if f < BEAT[1] else 0) * (1 - ramp(f, TEAR_HOOK, TEAR_HOOK + 20))
         for f in FRAMES]
bake(tr_mat.node_tree, f'nodes["{press_val.name}"].outputs[0].default_value', [3.0 * p for p in press])
airflow = [ramp(f, rmap(305), rmap(320)) * (1 - ramp(f, TEAR + 15, TEAR + 40)) + (1 if f < BEAT[1] else 0) * (1 - ramp(f, TEAR_HOOK + 5, TEAR_HOOK + 30))
           for f in FRAMES]
bake(air_mat.node_tree, 'nodes["AirFlowStrength"].outputs[0].default_value', [5 * a for a in airflow])
bake(air_mat.node_tree, 'nodes["AirMap"].inputs[1].default_value', [-0.9 * f for f in FRAMES], index=2)  # flows up
bulge = [1 + 0.22 * p * (1 + 0.15 * math.sin(f * 1.7)) for f, p in zip(FRAMES, press)]
bake_vec(trachea, "scale", [(b, b, 1) for b in bulge])
for lu in lungs:
    sq = [1 - 0.18 * spike(f, rmap(306), rise=4, decay=40) - 0.12 * spike(f, JOLT_HOOK, rise=3, decay=30) * (1 if f < BEAT[1] else 0)
          + 0.03 * math.sin(f / FPS * 2 * math.pi / 3.8) for f in FRAMES]
    bake_vec(lu, "scale", [(s, s, s) for s in sq])
# steering wheel turns gently with the road
steer = [curves(f)["steer"] for f in FRAMES]
bake(spin, "rotation_euler", [math.radians(s) for s in steer], index=2)
# car vibration: tiny bounce and roll, cameras ride the car
bake(car_root, "location", [0.0015 * math.sin(f * 1.9) * (0.5 + 0.5 * math.sin(f * 0.13)) for f in FRAMES], index=2)
bake(car_root, "rotation_euler", [math.radians(0.12 * wobble(f, 8, 1.5)) for f in FRAMES], index=1)
for o in [o for o in CAR.objects] + scenery_objs:
    for f in sorted({1} | {a for a, b in XRAY} | {b + 1 for a, b in XRAY}):
        o.hide_render = in_xray(f)
        o.keyframe_insert("hide_render", frame=f)
    o.hide_render = False
for o in ANAT.objects:  # anatomy only exists in X-ray shots (it would poke through clothes otherwise)
    for f in sorted({1} | {a for a, b in XRAY} | {b + 1 for a, b in XRAY}):
        o.hide_render = not in_xray(f)
        o.keyframe_insert("hide_render", frame=f)


# ---------------------------------------------------------------- IK targets need the live head pose
def bone_empty(name, bone, world_pos):
    e = bpy.data.objects.new(name, None); link(e)
    e.location = world_pos
    parent_rest(e, bone)
    return e


HEAD_REST = rig.data.bones[MX + "Head"].head_local
nose_anchor = bone_empty("NoseAnchor", "Head", Vector((-0.03, nose_tip.y - 0.085, nose_tip.z - 0.06)))  # wrist spot
nose_aimpt = bone_empty("NoseAimPt", "Head", Vector((0.0, nose_tip.y + 0.01, nose_tip.z + 0.03)))
# clutching the front of the throat reads from either side of the car
neck_anchor = bone_empty("NeckAnchor", "Neck", Vector((0.01, neck_front - 0.05, 1.41)))
neck_aimpt = bone_empty("NeckAimPt", "Neck", Vector((0.03, neck_front + 0.03, 1.55)))
eye_focus = bone_empty("EyeFocus", "Head", Vector((0.03, nose_tip.y + 0.02, nose_tip.z + 0.04)))
mouth_pt = bone_empty("MouthPt", "Head", Vector((0.0, nose_tip.y + 0.012, nose_tip.z - 0.042)))
face_aim = bone_empty("FaceAim", "Head", Vector((0.0, nose_tip.y + 0.06, nose_tip.z + 0.01)))
# aiming below the nose puts the eyes on the upper third instead of leaving dead headliner above
face_aim_low = bone_empty("FaceAimLow", "Head", Vector((0.0, nose_tip.y + 0.06, nose_tip.z - 0.075)))
tear_focus = bone_empty("TearFocus", "Spine2", TEAR_POS)
neck_aim = bone_empty("NeckXAim", "Spine2", TR_MID + Vector((0, 0, 0.0)))
torso_aim = bone_empty("TorsoXAim", "Spine2", Vector((0, TR_Y + 0.02, 1.40)))

ikL = bpy.data.objects["IK_Left"]; ikR = bpy.data.objects["IK_Right"]
locL, locR, locAim, inflDT = [], [], [], []
scene.frame_set(120)
SHOULDER_L = car_root.matrix_world.inverted() @ (rig.matrix_world @ rig.pose.bones[MX + "LeftArm"].head)
SHOULDER_R = car_root.matrix_world.inverted() @ (rig.matrix_world @ rig.pose.bones[MX + "RightArm"].head)
for f in FRAMES:
    scene.frame_set(f)
    c = curves(f)
    st = steer[f - 1]
    # wrist sits back along the forearm line from the rim so the palm crosses it and the
    # curled fingers wrap it (+X = driver's left)
    rL, rR = wheel_point(10, st), wheel_point(170, st)
    gL = rL - (rL - SHOULDER_L).normalized() * 0.075
    gR = rR - (rR - SHOULDER_R).normalized() * 0.075
    to_car = car_root.matrix_world.inverted()
    nose = to_car @ nose_anchor.matrix_world.translation
    neck = to_car @ neck_anchor.matrix_world.translation
    p, n = c["pinch"], c["neckhand"]
    w = max(0.0, 1 - p - n)
    pos = gR * w + nose * p + neck * n
    arc = 4 * (p * (1 - p) + n * (1 - n))
    pos += Vector((0.0, -0.07, 0.03)) * arc
    locL.append(gL); locR.append(pos)
    aimp = (to_car @ nose_aimpt.matrix_world.translation) * p + (to_car @ neck_aimpt.matrix_world.translation) * n \
        + (gR + Vector((0, -0.05, 0.12))) * w
    locAim.append(aimp)
    inflDT.append(min(1.0, p + n))
# sneeze spray: ballistic droplets from the mouth at the moment of the free sneeze
scene.frame_set(SNEEZE)
to_car = car_root.matrix_world.inverted()
mouth = to_car @ mouth_pt.matrix_world.translation
snz_dir = (mouth - to_car @ (rig.matrix_world @ rig.pose.bones[MX + "Head"].head)).normalized()
snz_dir = (snz_dir + Vector((0, -1.2, 0))).normalized()
spray_mat = principled("Spray", (0.9, 0.95, 1.0), 0.05, **{"Transmission Weight": 0.6,
                                                            "Emission Color": (0.85, 0.92, 1.0, 1), "Emission Strength": 0.6})
spray_mesh = dot_mesh_jet.copy(); spray_mesh.materials.clear(); spray_mesh.materials.append(spray_mat)
for i in range(110):
    o = bpy.data.objects.new("Spray", spray_mesh); link(o); o.parent = car_root
    v = (snz_dir + Vector([random.gauss(0, 0.28) for _ in range(3)])).normalized() * random.uniform(2.0, 4.5)
    r = random.uniform(0.0008, 0.0028)
    t0 = SNEEZE - 1 + random.uniform(0, 3)
    locs, scales = [], []
    for f in FRAMES:
        age = max(0.0, (f - t0) / FPS)
        p = mouth + v * age + Vector((0, 0, -4.9 * age * age))
        p.y = max(p.y, -0.6)          # splat on the windscreen / dash
        locs.append(p)
        scales.append(r * (1 if t0 <= f <= t0 + 22 else 0) * (1 - ramp(f, t0 + 14, t0 + 22)))
    bake_vec(o, "location", locs)
    bake_vec(o, "scale", [(s, s, s) for s in scales])
bake_vec(ikL, "location", locL)
bake_vec(ikR, "location", locR)
bake_vec(aim, "location", locAim)
bake(rig, f'pose.bones["{MX}RightHand"].constraints["DT"].influence', inflDT)


# ---------------------------------------------------------------- cameras (all ride the car)
def cam(name, keys, lens, fstop, aim_obj, focus_obj=None, shake=0.0):
    # shake kept as a param for compatibility; locked cameras read far more smooth/cinematic
    # than the earlier handheld-noise attempt, which produced visible high-frequency jitter.
    c = P.add_camera(scene, name, keys[0][1], aim_obj.matrix_world.translation, lens, fstop=fstop)
    c.parent = car_root
    trk = c.constraints.new("TRACK_TO"); trk.target = aim_obj
    trk.track_axis, trk.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"
    c.data.dof.focus_object = focus_obj or aim_obj
    for fr_, loc in keys:
        c.location = loc
        c.keyframe_insert("location", frame=fr_)
    for i, fc in enumerate(fcurves_of(c)):
        fc.keyframe_points.foreach_set("interpolation", [2] * len(fc.keyframe_points))
    return c


scene.frame_set(120)
H = rig.matrix_world @ rig.pose.bones[MX + "Head"].head
F = face_aim.matrix_world.translation.copy()
T = neck_aim.matrix_world.translation.copy()
TP = tear_focus.matrix_world.translation.copy()
print("H", tuple(H), "FACE", tuple(F), "TRACHEA", tuple(T))

cam_hook = cam("CamHook", [(1, F + Vector((0.36, -0.56, 0.06))), (rmap(53), F + Vector((0.3, -0.46, 0.05)))], 40, 2.8, face_aim_low, eye_focus)
rear_aim = bpy.data.objects.new("RearAim", None); link(rear_aim); rear_aim.parent = car_root
rear_aim.location = (-1.1, -5.0, 1.15)
cam_rear = cam("CamRear", [(BEAT[1], Vector((CX + 0.05, 0.78, 1.7))), (rmap(139), Vector((CX + 0.05, 0.68, 1.68)))], 20, 5.6,
               rear_aim, face_aim, shake=0.003)
cam_face = cam("CamFace", [(rmap(140), F + Vector((0.52, -0.5, 0.08))), (rmap(179), F + Vector((0.45, -0.44, 0.07))),
                           (rmap(558), F + Vector((0.5, -0.5, 0.07))), (rmap(614), F + Vector((0.42, -0.42, 0.05))),
                           (rmap(866), F + Vector((0.5, -0.48, 0.08))), (rmap(918), F + Vector((0.44, -0.42, 0.07))),
                           (rmap(996), F + Vector((0.46, -0.46, 0.08))), (END, F + Vector((0.4, -0.4, 0.07)))],
               38, 2.8, face_aim_low, eye_focus)
wide_aim = bpy.data.objects.new("WideAim", None); link(wide_aim); wide_aim.parent = car_root
wide_aim.location = H + Vector((0, -0.22, -0.22))
cam_wide = cam("CamWide", [(180, H + Vector((0.8, -0.35, -0.12))), (rmap(264), H + Vector((0.72, -0.3, -0.1))),
                           (rmap(615), H + Vector((0.78, -0.33, -0.1))), (rmap(672), H + Vector((0.72, -0.3, -0.1))),
                           (rmap(919), H + Vector((0.8, -0.36, -0.1))), (rmap(995), H + Vector((0.74, -0.32, -0.1)))],
               24, 4.0, wide_aim, face_aim)
cam_ecu = cam("CamECU", [(265, F + Vector((0.17, -0.4, 0.03))), (rmap(300), F + Vector((0.14, -0.33, 0.03)))], 50, 2.8, face_aim, eye_focus)
cam_xt = cam("CamXTorso", [(BEAT[4], T + Vector((0.42, -0.95, -0.02))), (rmap(399), T + Vector((0.34, -0.78, 0.0)))], 40, 8.0,
             bpy.data.objects["TorsoXAim"], neck_aim, shake=0.002)
cam_xn = cam("CamXNeck", [(rmap(54), T + Vector((0.2, -0.36, 0.03))), (rmap(109), T + Vector((0.15, -0.28, 0.02))),
                          (rmap(400), T + Vector((0.22, -0.4, 0.03))), (rmap(486), T + Vector((0.17, -0.31, 0.02))),
                          (rmap(673), T + Vector((0.22, -0.4, 0.04))), (rmap(787), T + Vector((0.17, -0.32, 0.03)))],
             50, 5.6, neck_aim, neck_aim, shake=0.002)
cam_xc = cam("CamXClose", [(rmap(487), TP + Vector((0.09, -0.15, 0.01))), (rmap(557), TP + Vector((0.07, -0.11, 0.01))),
                           (rmap(788), TP + Vector((0.09, -0.15, 0.01))), (rmap(865), TP + Vector((0.07, -0.12, 0.01)))],
             50, 4.0, tear_focus, tear_focus, shake=0.0015)

def _r(f):
    return int(round(rmap(f)))


CUTS = [(1, cam_hook), (_r(54), cam_xn), (BEAT[1], cam_rear), (_r(140), cam_face), (180, cam_wide), (_r(265), cam_ecu),
        (BEAT[4], cam_xt), (_r(400), cam_xn), (BEAT[5], cam_xc), (BEAT[6], cam_face), (_r(615), cam_wide),
        (BEAT[7], cam_xn), (BEAT[8], cam_xc), (_r(866), cam_face), (BEAT[9], cam_wide), (_r(996), cam_face)]
for f, c in CUTS:
    scene.timeline_markers.new(c.name, frame=f).camera = c
scene.camera = cam_hook

scene.sequence_editor_create()
seq = scene.sequence_editor
strips = seq.strips if hasattr(seq, "strips") else seq.sequences
strips.new_sound("VO", r"D:\ShortsPipeline\audio\vo_sneeze.wav", channel=1, frame_start=1)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("SAVED", OUT, "END", END)

for f in STILLS:
    scene.frame_set(f)
    cur = max((m for m in scene.timeline_markers if m.frame <= f), key=lambda m: m.frame)
    scene.camera = cur.camera
    scene.render.filepath = OUT.replace(".blend", f"_f{f:04d}.png").replace("\\blend\\", "\\renders\\test_sneeze\\")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", scene.render.filepath)
