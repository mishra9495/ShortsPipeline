"""cholesterol-through-skin: "A man ate so much cheese and butter his cholesterol tried to escape
through his skin" (JAMA Cardiology case report, Jan 2025 -- carnivore-diet xanthoma, cholesterol > 1000 mg/dL).

Run (daily_render.ps1): blender -b --python scene.py -- <ROOT>/blend/<slug>.blend vo=<wav> beats=<json> fps=30
Optional: stills=1,200 pct=100 samples=128 device=gpu|cpu root=<ROOT>

v3 toolkit: every model is built in Blender from code (scripts/kit.py), the character acts
procedurally on the mixamorig bones (scripts/actor.py) and every camera is a moving spline that is
already in motion on the cut (scripts/shot.py). No captions, no on-screen text (owner's rule).
Timing comes only from the beats JSON.

Cast: him = blend/char_hero.blend (opened as the main file). One character, one actor.
Sets: HOME (a dressed dining-nook corner -- he eats at the table), LAB (a small neutral tabletop,
far away, for the blood-vial insert) and XRAY (a void anatomy stage, also far away, for the
vessel/plaque macro reveal). Transitions between sets are HARD CUTS (whoosh SFX + a brief exposure
spike), not camera plunges, because the sets are not spatially coincident with the live character.
SYNC constants below must match mix.py.
"""
import json
import math
import os
import random
import sys
import warnings

import bpy
from mathutils import Quaternion, Vector

warnings.filterwarnings("ignore", category=DeprecationWarning)

# ---------------------------------------------------------------- arguments
argv = sys.argv[sys.argv.index("--") + 1:]
OUT = os.path.abspath(argv[0])
opts = dict(kv.split("=", 1) for kv in argv[1:] if "=" in kv)
SLUG = os.path.splitext(os.path.basename(OUT))[0]
ROOT = opts.get("root") or os.path.dirname(os.path.dirname(OUT))
SCRIPTS = os.path.join(ROOT, "scripts")
AUDIO = os.path.join(ROOT, "audio")
FPS = int(opts.get("fps", 30))
PCT = int(opts.get("pct", 100))
SAMPLES = int(opts.get("samples", 128))       # final quality: 2x the usual, tighter noise threshold below
DEVICE = opts.get("device", "gpu").lower()
STILLS = [int(f) for f in opts["stills"].split(",")] if opts.get("stills") else []
BEATS_JSON = opts.get("beats") or os.path.join(AUDIO, f"{SLUG}_vo.json")
VO_WAV = opts.get("vo") or os.path.join(AUDIO, f"{SLUG}_vo.wav")
if not os.path.exists(BEATS_JSON):
    raise SystemExit(f"Error: narration timing {BEATS_JSON} missing")
print(f"ARGS out={OUT} fps={FPS} pct={PCT} samples={SAMPLES} device={DEVICE} beats={BEATS_JSON}")
sys.path.insert(0, SCRIPTS)

# ---------------------------------------------------------------- character
HERO = os.path.join(ROOT, "blend", "char_hero.blend")
if not os.path.exists(HERO):
    raise SystemExit(f"Error: {HERO} missing")
print("CHAR", HERO)
bpy.ops.wm.open_mainfile(filepath=HERO)

import actor as A  # noqa: E402
import kit as K  # noqa: E402
import shot as S  # noqa: E402

scene = bpy.context.scene
K.init(scene, seed=31)
random.seed(31)
CAST = K.coll("Cast")
him = A.Actor.from_scene("Him")
him.measure()
him.setup_ik(CAST)
# seated with forearms on a table: elbows drop down and back (kit's default pole sits out to the side and gives
# a chicken-wing elbow when the hand target is low and close)
for side, sx in (("Left", 1), ("Right", -1)):
    bpy.data.objects[f"{him.name}.Pole_{side}"].location = (him.x0 + 0.28 * sx, him.hips0.y + 0.45, him.hips0.z + 0.12)
print("CAST", him.rig.name, "height", round(him.top, 3))

# ---------------------------------------------------------------- timeline (seconds)
META = json.load(open(BEATS_JSON, encoding="utf-8"))
B = [float(b["start"]) for b in META["beats"]]
assert len(B) == 10, f"expected 10 beats, got {len(B)}"
NARR = float(META["duration"])
DUR = NARR + 36.0 / FPS
BE = B[1:] + [NARR]


def at(i, frac):
    return B[i] + frac * (BE[i] - B[i])


def F(t):
    return int(round(t * FPS)) + 1


END = F(DUR)
FRAMES = range(1, END + 1)
T = [(f - 1) / FPS for f in FRAMES]

# SYNC with mix.py
GROW_A, GROW_B = B[6] + 0.15, B[7] + 0.9        # plaque grows along the vessel wall
ERUPT = at(8, 0.45)                              # the money-moment burst
SLO_A, SLO_B = at(8, 0.15), B[9] - 0.05          # screen-time slow-mo window around the burst
ACT_A, ACT_B = SLO_A, SLO_A + (SLO_B - SLO_A) * 0.4
print("TIMELINE", [round(b, 2) for b in B], "END", END, "ERUPT", round(ERUPT, 2))

S.setup_render(scene, fps=FPS, end=END, pct=PCT, samples=SAMPLES, device=DEVICE)
scene.cycles.adaptive_threshold = 0.015 if SAMPLES >= 96 else 0.03   # cleaner skin, glass and dark X-ray gradients


def bake(idb, path, values, index=None, interp="LINEAR"):
    return A.bake(idb, path, values, FRAMES, index=index, interp=interp)


def bake_vec(idb, path, vecs, n=3, interp="LINEAR"):
    A.bake_vec(idb, path, vecs, FRAMES, n=n, interp=interp)


ramp, env, spike, smooth, wobble = A.ramp, A.env, A.spike, A.smooth, A.wobble
warp = A.timewarp(SLO_A, SLO_B, ACT_A, ACT_B)

# ---------------------------------------------------------------- seat him (one static root -- never moves sets)
SEAT_HOME = Vector((0.0, 0.35, 0.48))
rig_loc = SEAT_HOME - him.hips0
him.rig.location = rig_loc
him.rig.rotation_euler = (0, 0, 0)


def to_local(world_pt):
    return Vector(world_pt) - rig_loc


legs_sit = him.seated_legs()

# ---------------------------------------------------------------- HOME: dining nook
HOME = K.coll("Home")
ROOM_ORIGIN = Vector((0.0, 1.0, 0.0))
ROOM_SIZE = (4.0, 3.4, 2.6)
WIN_SIZE = (1.1, 1.2)
WIN_LOC = (ROOM_ORIGIN.x, ROOM_ORIGIN.y + ROOM_SIZE[1] / 2, 1.4)
K.room(HOME, origin=ROOM_ORIGIN, size=ROOM_SIZE, wall_color=(0.80, 0.72, 0.60), name="Kitchen",
       openings=[(0.0, 1.4, WIN_SIZE[0] + 0.14, WIN_SIZE[1] + 0.14)])
K.window(HOME, WIN_LOC, size=WIN_SIZE, sky=(0.76, 0.85, 1.0), sky_strength=2.8)

TABLE = Vector((0.0, -0.25, 0.0))
TOP_Z = 0.74
wood_m = K.wood("TableWood", (0.42, 0.26, 0.14), (0.22, 0.12, 0.06), rough=0.38)
leg_m = K.metal("TableLeg", (0.08, 0.08, 0.09), 0.35)
K.rbox("TableTop", HOME, (1.15, 0.78, 0.035), (TABLE.x, TABLE.y, TOP_Z - 0.0175), wood_m, bevel=0.006)
for sx in (-1, 1):
    for sy in (-1, 1):
        K.rbox("TableLeg", HOME, (0.05, 0.05, TOP_Z - 0.035), (TABLE.x + sx * 0.5, TABLE.y + sy * 0.32, (TOP_Z - 0.035) / 2),
               leg_m, bevel=0.006)
chair_m = K.fabric("ChairFabric", (0.30, 0.20, 0.14))
K.cushion("ChairSeat", HOME, (0.42, 0.42, 0.08), (TABLE.x, SEAT_HOME.y + 0.03, SEAT_HOME.z - 0.08), chair_m, puff=0.25)
K.cushion("ChairBack", HOME, (0.42, 0.08, 0.46), (TABLE.x, SEAT_HOME.y + 0.24, SEAT_HOME.z + 0.24), chair_m, puff=0.25,
          rot=(math.radians(-8), 0, 0))
for sx in (-1, 1):
    for sy in (-1, 1):
        K.rbox("ChairLeg", HOME, (0.03, 0.03, SEAT_HOME.z - 0.14), (TABLE.x + sx * 0.17, SEAT_HOME.y + 0.17 + sy * 0.1,
               (SEAT_HOME.z - 0.14) / 2), leg_m, bevel=0.004)
K.rug(HOME, (TABLE.x, TABLE.y + 0.3, 0.0), (2.2, 1.8), main=(0.35, 0.22, 0.16), border=(0.14, 0.10, 0.08),
      field=(0.70, 0.62, 0.52))
K.picture_frame(HOME, (-1.1, ROOM_ORIGIN.y + ROOM_SIZE[1] / 2 - 0.02, 1.55), (0.55, 0.42), seed=4)
K.potted_plant(HOME, (1.55, 0.6, 0.0), h=1.1, seed=6)

# food on the table (the hero props for beats 2-3)
cheese_m = K.plastic("Cheese", (0.92, 0.72, 0.22), 0.45)
rind_m = K.plastic("CheeseRind", (0.85, 0.80, 0.70), 0.55)
butter_m = K.plastic("Butter", (0.95, 0.86, 0.52), 0.30)
plate_m = K.ceramic("Plate", (0.95, 0.95, 0.93))
steak_m = K.plastic("Steak", (0.30, 0.10, 0.06), 0.42, coat=0.25, sss=0.2)
# all food sits on his LEFT (+X, the eating hand's side); his right hand rests empty on the -X side of the table
CHEESE_C = TABLE + Vector((0.36, 0.06, TOP_Z + 0.035))
K.cyl("CheeseWheel", HOME, 0.095, 0.07, CHEESE_C, cheese_m, verts=40, bevel=0.006)
K.rbox("CheeseWedge", HOME, (0.05, 0.09, 0.07), CHEESE_C + Vector((-0.13, -0.07, 0.0)), rind_m, bevel=0.006)
PLATE_C = TABLE + Vector((0.06, 0.02, TOP_Z + 0.006))
K.cyl("Plate", HOME, 0.14, 0.012, PLATE_C, plate_m, verts=40, bevel=0.003)
steak = K.sphere("Steak", HOME, 0.07, PLATE_C + Vector((0.0, 0.0, 0.016)), steak_m, scale=(1.0, 0.70, 0.22), subdiv=4)
sear_tex = bpy.data.textures.new("SteakSear", "CLOUDS")
sear_tex.noise_scale = 0.03
sd = steak.modifiers.new("Sear", "DISPLACE")
sd.texture, sd.texture_coords, sd.strength = sear_tex, "GLOBAL", 0.006
fat_m = K.plastic("SteakFat", (0.92, 0.85, 0.72), 0.5, sss=0.3)
K.tube("SteakFatRim", HOME, [PLATE_C + Vector((-0.06, 0.035, 0.022)), PLATE_C + Vector((0.0, 0.05, 0.024)),
                              PLATE_C + Vector((0.06, 0.035, 0.022))], 0.007, fat_m, res=4)
BUTTER_C = TABLE + Vector((0.24, -0.20, TOP_Z + 0.006))
K.cyl("ButterDish", HOME, 0.065, 0.012, BUTTER_C, plate_m, verts=32, bevel=0.003)
K.rbox("ButterStick", HOME, (0.085, 0.034, 0.034), BUTTER_C + Vector((0.0, 0.0, 0.025)), butter_m, bevel=0.004)
steel_m = K.metal("Cutlery", (0.82, 0.82, 0.85), 0.25)
K.rbox("Fork", HOME, (0.012, 0.16, 0.004), PLATE_C + Vector((-0.17, -0.02, 0.0)), steel_m, bevel=0.002)
K.rbox("Knife", HOME, (0.012, 0.16, 0.004), PLATE_C + Vector((0.17, -0.02, 0.0)), steel_m, bevel=0.002)
FOOD_C = (CHEESE_C + PLATE_C + BUTTER_C) / 3

# his right hand (palm, resting on the table edge -- the hook/closer hero shot) and left hand (eats)
RIGHT_WORLD = TABLE + Vector((-0.22, 0.25, TOP_Z + 0.04))
LEFT_REST_WORLD = TABLE + Vector((0.22, 0.24, TOP_Z + 0.07))
RIGHT_LOCAL = to_local(RIGHT_WORLD)
LEFT_REST_LOCAL = to_local(LEFT_REST_WORLD)
LEFT_MOUTH_LOCAL = him.mouth + Vector((0.04, -0.13, -0.08))     # wrist target: the hand then reaches the lips

# palm_pt rides on the hand bone (middle of the hand); the nodules are placed on the real skin surface after the
# performance is baked (ray cast from the camera side), so they sit on any hand shape instead of inside it
palm_pt = him.anchor("PalmPt", "RightHand", him.bone_rest_head("RightHand").lerp(him.bone_rest_tail("RightHand"), 0.5), CAST)
nodule_m = K.plastic("Xanthoma", (0.95, 0.70, 0.28), 0.38, sss=0.45)
nodule_m.node_tree.nodes["Principled BSDF"].inputs["Coat Weight"].default_value = 0.35   # waxy sheen
CAM_SIDE = Vector((0.45, -0.75, 0.48)).normalized()      # where the hook/shock/closer cameras look from

# ---------------------------------------------------------------- LAB: a small neutral tabletop, far away
LABP = Vector((10.0, 0.0, 0.92))
LAB = K.coll("Lab")
slab_m = K.plastic("LabSlab", (0.05, 0.05, 0.055), 0.35)
K.rbox("LabSlab", LAB, (0.5, 0.4, 0.04), LABP + Vector((0, 0, -0.02)), slab_m, bevel=0.01)
VIAL = LABP + Vector((0.0, 0.0, 0.09))


def thin_glass(name):
    """Thin-walled glass: transparent + Fresnel gloss. Real refractive glass around liquids renders their layers as
    dark smears at these sample counts; a thin tube wall barely bends light anyway."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links
    N.clear()
    out, tr, gl = N.new("ShaderNodeOutputMaterial"), N.new("ShaderNodeBsdfTransparent"), N.new("ShaderNodeBsdfGlossy")
    gl.inputs["Roughness"].default_value = 0.03
    fr = N.new("ShaderNodeFresnel")
    fr.inputs["IOR"].default_value = 1.5
    mx = N.new("ShaderNodeMixShader")
    L.new(fr.outputs[0], mx.inputs[0])
    L.new(tr.outputs[0], mx.inputs[1])
    L.new(gl.outputs[0], mx.inputs[2])
    L.new(mx.outputs[0], out.inputs["Surface"])
    return m


vial_glass = thin_glass("VialGlass")
# a hollow tube (thin wall) so the contents read through the glass instead of through a solid glass block
K.lathe("Vial", LAB, [(0.0, -0.045), (0.013, -0.045), (0.016, -0.040), (0.016, 0.045)], VIAL, vial_glass, steps=48,
        thickness=0.0012, subsurf=1)
serum_m = K.plastic("LipemicSerum", (0.22, 0.008, 0.008), 0.2, sss=0.3)
K.cyl("Serum", LAB, 0.0145, 0.050, VIAL + Vector((0, 0, -0.018)), serum_m, verts=40)
# lipemic blood: a thick, milky fat layer floating on the serum (the true sign of extreme blood fats)
cream_m = K.plastic("LipemicCream", (0.96, 0.90, 0.68), 0.45, sss=0.5)
cream = K.cyl("CreamLayer", LAB, 0.0145, 0.024, VIAL + Vector((0, 0, 0.019)), cream_m, verts=40, bevel=0.002)
cap_m = K.plastic("VialCap", (0.80, 0.58, 0.12), 0.35)          # gold top: the serum tube a lipid panel is drawn into
K.cyl("VialCap", LAB, 0.0165, 0.016, VIAL + Vector((0, 0, 0.053)), cap_m, verts=40, bevel=0.002)
glove_m = K.plastic("Glove", (0.70, 0.85, 0.72), 0.5)
K.sphere("GloveHint", LAB, 0.05, VIAL + Vector((0.0, 0.22, -0.08)), glove_m, scale=(1.0, 1.4, 0.7), subdiv=2)

# ---------------------------------------------------------------- XRAY: void anatomy stage, far away
ANATP = Vector((20.0, 0.0, 1.0))
ANAT = K.coll("Anat")


def xglow(name, color, strength, blend=0.3, core=0.03):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links
    N.clear()
    out = N.new("ShaderNodeOutputMaterial")
    lw = N.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = blend
    mr = N.new("ShaderNodeMapRange")
    mr.inputs[1].default_value, mr.inputs[2].default_value, mr.inputs[3].default_value = 0.1, 0.95, core
    L.new(lw.outputs["Facing"], mr.inputs[0])
    em = N.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = strength
    tr = N.new("ShaderNodeBsdfTransparent")
    mx = N.new("ShaderNodeMixShader")
    L.new(mr.outputs[0], mx.inputs[0])
    L.new(tr.outputs[0], mx.inputs[1])
    L.new(em.outputs[0], mx.inputs[2])
    L.new(mx.outputs[0], out.inputs["Surface"])
    return m


VESSEL_PTS = [ANATP + Vector((-0.09, 0.015, -0.01)), ANATP + Vector((-0.02, -0.01, 0.005)),
              ANATP + Vector((0.05, 0.02, -0.005)), ANATP + Vector((0.11, -0.01, 0.01))]
wall_m = xglow("VesselWall", (1.0, 0.30, 0.22), 1.6, blend=0.3, core=0.04)
blood_m = xglow("VesselPlasma", (0.95, 0.10, 0.06), 1.2, blend=0.4, core=0.10)     # see-through plasma, cells inside
rbc_m = K.plastic("RedCell", (0.55, 0.02, 0.02), 0.35, sss=0.5)
rbc_bsdf = rbc_m.node_tree.nodes["Principled BSDF"]
rbc_bsdf.inputs["Emission Color"].default_value = (0.9, 0.05, 0.03, 1)
rbc_bsdf.inputs["Emission Strength"].default_value = 0.6
wall = K.tube("VesselWall", ANAT, VESSEL_PTS, 0.021, wall_m, res=12)
blood = K.tube("VesselBlood", ANAT, VESSEL_PTS, 0.0135, blood_m, res=10)
for o in (wall, blood):          # X-ray shells glow for the camera only; lighting what's inside washes it to cream
    o.visible_diffuse = o.visible_glossy = o.visible_transmission = False
# plaque: waxy yellow crusts hugging the inside of the wall (flattened along the radius), lumpy surface
plaque_m = K.plastic("Plaque", (0.95, 0.55, 0.05), 0.45, sss=0.25)
plaque_bsdf = plaque_m.node_tree.nodes["Principled BSDF"]
plaque_bsdf.inputs["Emission Color"].default_value = (1.0, 0.55, 0.04, 1)
plaque_bsdf.inputs["Emission Strength"].default_value = 0.4
lump_tex = bpy.data.textures.new("PlaqueLumps", "CLOUDS")
lump_tex.noise_scale = 0.004


def lumpy(o, amount):
    dp = o.modifiers.new("Lumps", "DISPLACE")
    dp.texture = lump_tex
    dp.texture_coords = "GLOBAL"
    dp.strength = amount
    return o


def vessel_point(u):
    """Catmull-Rom through VESSEL_PTS, u in 0..1."""
    pts = [VESSEL_PTS[0]] + VESSEL_PTS + [VESSEL_PTS[-1]]
    n = len(VESSEL_PTS) - 1
    u = min(max(u, 0.0), 1.0) * n
    i = min(int(u), n - 1)
    t = u - i
    p0, p1, p2, p3 = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
    return 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)


PLAQUE = []
rng2 = random.Random(5)
# crusts hug the inner wall (radius 0.0155 of a 0.021 wall), flattened along the radius and stretched along the vessel;
# kept off the camera-facing (-Y) side so the narrowing lumen and the red cells stay visible through the X-ray wall
for i in range(22):
    u = 0.06 + 0.88 * (i + rng2.uniform(0.1, 0.9)) / 22
    centre = vessel_point(u)
    ang = rng2.uniform(-1.9, 1.9)
    radial = Vector((0.0, math.cos(ang), math.sin(ang)))
    size = rng2.uniform(0.0035, 0.0055)
    o = K.sphere(f"PlaqueCell{i}", ANAT, size, centre + radial * 0.0155, plaque_m, scale=(2.2, 1.4, 0.6), subdiv=4)
    o.rotation_euler = radial.to_track_quat("Z", "X").to_euler()
    lumpy(o, 0.0010)
    start = GROW_A + rng2.uniform(0.0, (GROW_B - GROW_A) * 0.75)
    PLAQUE.append((o, start, GROW_A, GROW_B))
# the eruption cell: the biggest, facing the camera side (the +Y offset so it faces -Y-ish toward the orbit cameras)
erupt_centre = VESSEL_PTS[1].lerp(VESSEL_PTS[2], 0.4) + Vector((0.0, -0.017, 0.0))
erupt_cell = lumpy(K.sphere("EruptCell", ANAT, 0.0065, erupt_centre, plaque_m, scale=(1.3, 0.85, 1.15), subdiv=4), 0.0014)
flash_m = K.emissive("EruptFlash", (1.0, 0.95, 0.65), 0.0)
flash = K.sphere("EruptFlash", ANAT, 0.006, erupt_centre + Vector((0, -0.006, 0)), flash_m, subdiv=3)


# red blood cells: biconcave discs tumbling down the lumen (constant motion in every X-ray frame)
RBC_PROFILE = [(0.0, 0.0007), (0.0018, 0.0011), (0.0032, 0.0010), (0.0040, 0.0), (0.0032, -0.0010), (0.0018, -0.0011),
               (0.0, -0.0007)]
RBCS = []
rng4 = random.Random(21)
for k in range(26):
    o = K.lathe(f"RedCell{k}", ANAT, RBC_PROFILE, ANATP, rbc_m, steps=24, subsurf=1)
    RBCS.append((o, rng4.random(), rng4.uniform(0.55, 1.0), rng4.uniform(0, 2 * math.pi), rng4.uniform(0.15, 0.9),
                 Vector((rng4.uniform(-1, 1), rng4.uniform(-1, 1), rng4.uniform(-1, 1))).normalized(), rng4.uniform(1.5, 4.0)))
ejecta_m = K.plastic("Ejecta", (0.95, 0.82, 0.25), 0.4)
ejecta = K.shards(ANAT, 7, ejecta_m, erupt_centre, size=(0.0015, 0.004), seed=2, name="Ejecta", spread=0.004)

# ---------------------------------------------------------------- subsurface depth to real scale
# kit.plastic(sss=...) keeps Blender's default 5 cm scatter, which turns these millimetre props translucent grey/tan
for m_, sc_ in ((nodule_m, 0.0015), (plaque_m, 0.0015), (cream_m, 0.003), (serum_m, 0.003), (rbc_m, 0.0008),
                (steak_m, 0.003), (fat_m, 0.002)):
    m_.node_tree.nodes["Principled BSDF"].inputs["Subsurface Scale"].default_value = sc_

# ---------------------------------------------------------------- shots (names, start times, set)
SHOTS = [
    (0.0, "PalmHookECU", "home"),
    (at(0, 0.55), "PalmHookOrbit", "home"),
    (B[1], "KitchenWide", "home"),
    (B[2], "FoodInsertCU", "home"),
    (B[3], "FaceMedium", "home"),
    (B[4], "PalmShockECU", "home"),
    (B[5], "VialInsert", "lab"),
    (B[6], "VesselOrbit", "xray"),
    (B[7], "PlaqueOrbit", "xray"),
    (B[8], "EruptBuildCU", "xray"),
    (at(8, 0.45), "EruptSlomo", "xray"),
    (B[9], "CloserPull", "home"),
]


def shot_at(t):
    return max((s for s in SHOTS if s[0] <= t + 1e-6), key=lambda s: s[0])


SH = [shot_at(t) for t in T]
SET_OF = [s[2] for s in SH]

# ---------------------------------------------------------------- performance (channels, 0..1 envelopes over time)
BLINKS = [1.0 + 2.9 * k for k in range(60) if 1.0 + 2.9 * k < DUR]
BITES = [B[1] + 0.7 + 2.3 * k for k in range(20) if B[1] + 0.7 + 2.3 * k < B[3] + 0.6]


def channels(t):
    ch = {}
    ch["eat"] = max((env(t, bt - 0.6, bt - 0.12, bt + 0.2, bt + 0.75) for bt in BITES), default=0.0)   # food up to the mouth
    ch["chew"] = (max((env(t, bt, bt + 0.2, bt + 1.4, bt + 1.8) for bt in BITES), default=0.0)
                  * (0.5 + 0.5 * math.sin(2 * math.pi * 3.0 * t)))
    ch["smile"] = max(env(t, B[3] - 0.1, B[3] + 0.3, B[4] + 0.05, B[4] + 0.4), 0.75 * ramp(t, B[9] + 0.35, B[9] + 0.9))
    ch["shock"] = env(t, B[4] + 0.05, B[4] + 0.35, B[5] - 0.25, B[5])
    ch["blink"] = max((env(t, b_ - 0.03, b_, b_ + 0.05, b_ + 0.12) for b_ in BLINKS), default=0.0)
    return ch


THIGH_L = him.hips0.lerp(him.bone_rest_head("LeftLeg"), 0.6) + Vector((0.03, -0.22, 0.07))
THIGH_R = him.hips0.lerp(him.bone_rest_head("RightLeg"), 0.6) + Vector((-0.03, -0.22, 0.07))
for i, t in enumerate(T):
    ch = channels(t)
    br = math.sin(t * 2 * math.pi / 3.6)
    rots = {}
    spec = {
        "Hips": [(A.Z, 0.4 * wobble(t, 1))],
        "Spine": [(A.X, -6 + 0.5 * br), (A.Z, 0.6 * wobble(t, 2))],
        "Spine1": [(A.X, -2 + 0.6 * br - 2 * ch["smile"])],
        "Spine2": [(A.X, 2 + 0.6 * br)],
        "Neck": [(A.X, 4 - 9 * ch["shock"] + 0.3 * wobble(t, 4)), (A.Z, 1.2 * wobble(t, 5))],
        "Head": [(A.X, 2 - 13 * ch["shock"] + 1.0 * wobble(t, 7, 0.6)),
                 (A.Z, 2.0 * wobble(t, 6, 0.5) - 5 * ch["shock"]), (A.Y, 1.0 * wobble(t, 8))],
        "LeftShoulder": [(A.Y, 3 * ch["eat"])],
        "RightShoulder": [(A.Y, -1.0)],
    }
    for bone, axes in spec.items():
        if him.has(bone):
            q = A.Quaternion()
            for axis, deg in axes:
                q = q @ him.q(bone, axis, deg)
            rots[bone] = q
    for bone, q in legs_sit.items():
        rots[bone] = q
    for bone in him.fingers():
        j = int(bone[-1])
        if bone.startswith("Right"):
            curl = {1: 6, 2: 10, 3: 8}[j]
        else:
            curl = {1: 22, 2: 34, 3: 26}[j]
            curl += 14 * ch["eat"]
        rots[bone] = A.Quaternion((1, 0, 0), math.radians(curl))
    sh = {}
    for side in ("Left", "Right"):
        sh[f"eyeBlink{side}"] = min(1.0, ch["blink"])
        sh[f"mouthSmile{side}"] = 0.8 * ch["smile"]
    sh["browInnerUp"] = 0.6 * ch["shock"]
    sh["jawOpen"] = 0.12 * ch["chew"] + 0.10 * spike(t, max([bt for bt in BITES if bt <= t + 0.1], default=-9), 0.1, 0.15) + 0.18 * ch["shock"]
    ikl = LEFT_REST_LOCAL.lerp(LEFT_MOUTH_LOCAL, ch["eat"])
    ikr = RIGHT_LOCAL + Vector((0.0, 0.002 * wobble(t, 15, 0.4), 0.0))
    him.record(rots, sh, ikl, ikr, aim=(0.0, 0.0))
him.bake(FRAMES)
for fc in A.fcurves_of(him.rig):
    fc.update()

# ---------------------------------------------------------------- xanthoma nodules on the skin that faces the camera
# His right hand never leaves the table, so one ray cast at the hook's mid-frame finds the skin; the nodules are then
# parented to palm_pt (keeping their world transform) and ride along with the tiny idle wobble.
scene.frame_set(F(at(0, 0.3)))
dg = bpy.context.evaluated_depsgraph_get()
HAND_C = palm_pt.matrix_world.translation.copy()
inv = him.body.matrix_world.inverted()


def skin_hit(origin_w, target_w):
    o_l, t_l = inv @ origin_w, inv @ target_w
    ok, loc, nrm, _ = him.body.ray_cast(o_l, (t_l - o_l).normalized(), depsgraph=dg)
    if not ok:
        return None, None
    mw3 = him.body.matrix_world.to_3x3()
    return him.body.matrix_world @ loc, (mw3.inverted().transposed() @ nrm).normalized()


SKIN, SKIN_N = skin_hit(HAND_C + CAM_SIDE * 0.25, HAND_C)
if SKIN is None:
    print("WARN nodules: ray missed the hand, placing them at the bone")
    SKIN, SKIN_N = HAND_C + CAM_SIDE * 0.02, CAM_SIDE.copy()
side_a = SKIN_N.cross(Vector((0, 0, 1)))
side_a = side_a.normalized() if side_a.length > 1e-4 else Vector((1, 0, 0))
side_b = SKIN_N.cross(side_a).normalized()
NODULES = []
rng = random.Random(9)
for i, (u, v_, r) in enumerate(((0.0, 0.0, 0.0062), (0.011, 0.006, 0.0048), (-0.009, 0.008, 0.0042),
                                (0.004, -0.011, 0.0052), (-0.012, -0.006, 0.0036))):
    guess = SKIN + side_a * u + side_b * v_
    p, n = skin_hit(guess + SKIN_N * 0.05, guess - SKIN_N * 0.02)
    p, n = (p, n) if p is not None else (guess, SKIN_N)
    o = lumpy(K.sphere(f"Nodule{i}", CAST, r, p + n * r * 0.15, nodule_m, scale=(1.0, 0.85, 0.45), subdiv=4), r * 0.18)
    o.rotation_euler = n.to_track_quat("Z", "Y").to_euler()
    o.parent = palm_pt
    o.matrix_parent_inverse = palm_pt.matrix_world.inverted()
    NODULES.append(o)
nod_c = K.empty("NoduleC", CAST, SKIN)
nod_c.parent = palm_pt
nod_c.matrix_parent_inverse = palm_pt.matrix_world.inverted()
print("NODULES on skin at", tuple(round(c, 3) for c in SKIN), "normal", tuple(round(c, 2) for c in SKIN_N))

# ---------------------------------------------------------------- vessel process animation (plaque growth + burst)
for o, start, ga, gb in PLAQUE:
    end = min(gb, start + 0.9)
    s0 = o.scale.copy()
    vals = [ramp(t, start, end) for t in T]
    bake_vec(o, "scale", [(s0.x * v, s0.y * v, s0.z * (0.4 + 0.6 * v) * v) for v in vals])
LUMEN = [0.0135 - 0.0095 * ramp(t, GROW_A, GROW_B) for t in T]
bake(blood.data, "bevel_depth", LUMEN)
for o, ph, spd, ang, rr, axis, spin in RBCS:
    u, locs, rots, scl = ph, [], [], []
    for i, t in enumerate(T):
        lum = LUMEN[i]
        u = (u + spd * 0.18 * (0.35 + 0.65 * lum / 0.0135) / FPS) % 1.0       # cells slow and bunch as it narrows
        c = vessel_point(u)
        a_ = ang + 0.6 * t
        locs.append(c + Vector((0.0, math.cos(a_), math.sin(a_))) * (lum - 0.004) * rr)
        rots.append(Quaternion(axis, spin * t).to_euler())
        edge = smooth(min(u, 1 - u) / 0.07)
        scl.append(edge * (0.7 + 0.3 * lum / 0.0135))
    bake_vec(o, "location", locs)
    bake_vec(o, "rotation_euler", rots)
    bake_vec(o, "scale", [(v, v, v) for v in scl])

burst = [ramp(warp(t), ACT_A, ACT_A + (ACT_B - ACT_A) * 0.5) * (1 - ramp(warp(t), ACT_A + (ACT_B - ACT_A) * 0.7, ACT_B))
         + ramp(warp(t), ACT_A + (ACT_B - ACT_A) * 0.7, ACT_B) for t in T]
erupt_scale = [1.0 + 0.6 * b for b in burst]
es0 = erupt_cell.scale.copy()
bake_vec(erupt_cell, "scale", [(es0.x * v, es0.y * v, es0.z * v) for v in erupt_scale])
out_dir = Vector((0.0, -1.0, 0.0))     # straight out through the wall, toward the cameras
bake_vec(erupt_cell, "location", [erupt_centre + out_dir * (0.011 * b) for b in burst])
flash_vals = [spike(warp(t), ACT_A + (ACT_B - ACT_A) * 0.45, 0.04, 0.12) for t in T]
bake_vec(flash, "scale", [(min(1.0, 4 * v),) * 3 for v in flash_vals])
bake(flash.data.materials[0].node_tree, 'nodes["Principled BSDF"].inputs["Emission Strength"].default_value',
     [40.0 * v for v in flash_vals])
for k, o in enumerate(ejecta):
    rng3 = random.Random(100 + k)
    d = Vector((rng3.uniform(-1, 1), rng3.uniform(0.3, 1), rng3.uniform(-0.3, 0.6))).normalized()
    sp = rng3.uniform(0.02, 0.05)
    base = o.location.copy()
    locs, scl = [], []
    for t in T:
        age = warp(t) - (ACT_A + (ACT_B - ACT_A) * 0.45)
        if age < 0:
            locs.append(base)
            scl.append(0.0)
        else:
            locs.append(erupt_centre + d * sp * min(1.0, age * 6) - Vector((0, 0, 4.5 * age * age)))
            scl.append(1.0 * math.exp(-age * 2.0))
    bake_vec(o, "location", locs)
    bake_vec(o, "scale", [(v, v, v) for v in scl])

# ---------------------------------------------------------------- visibility per set
def key_vis(objs, fn):
    for o in objs:
        prev = None
        for i in range(len(T)):
            v = bool(fn(i))
            if v != prev:
                o.hide_render = not v
                o.keyframe_insert("hide_render", frame=i + 1)
                prev = v


for name, coll in (("home", HOME), ("lab", LAB), ("xray", ANAT)):
    key_vis([o for o in coll.all_objects if not o.hide_render], lambda i, name=name: SET_OF[i] == name)
key_vis([*NODULES], lambda i: SET_OF[i] == "home")

# ---------------------------------------------------------------- world + lights per set
world = bpy.data.worlds.new("ShortWorld")
scene.world = world
world.use_nodes = True
wnt = world.node_tree
wnt.nodes.clear()
wbg = wnt.nodes.new("ShaderNodeBackground")
wbg.name = "Background"
wout = wnt.nodes.new("ShaderNodeOutputWorld")
wnt.links.new(wbg.outputs[0], wout.inputs[0])
WCOL = {"home": ((0.62, 0.56, 0.47), 0.35), "lab": ((0.22, 0.23, 0.26), 0.18), "xray": ((0.07, 0.01, 0.01), 1.0)}
cols = [WCOL[s] for s in SET_OF]
bake_vec(wnt, 'nodes["Background"].inputs[0].default_value', [(*c_, 1) for c_, _ in cols], n=4, interp="CONSTANT")
bake(wnt, 'nodes["Background"].inputs[1].default_value', [s_ for _, s_ in cols], interp="CONSTANT")
bake(scene, "view_settings.exposure", [-0.35 + 0.8 * spike(t, B[6], 0.01, 0.06) + 0.5 * spike(t, ERUPT, 0.02, 0.1)
                                       for t in T])


def _area(name, coll, loc, target, energy, size, color):
    d = bpy.data.lights.new(name, "AREA")
    d.energy, d.size, d.color = energy, size, color
    o = bpy.data.objects.new(name, d)
    coll.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


HEAD_HOME = SEAT_HOME + Vector((0, -0.05, 0.56))
LIGHTS = {
    "home": [_area("HomeKey", HOME, HEAD_HOME + Vector((1.2, -1.4, 1.0)), HEAD_HOME, 300, 1.4, (1.0, 0.90, 0.80)),
             _area("HomeFill", HOME, HEAD_HOME + Vector((-1.5, -1.1, 0.2)), HEAD_HOME, 80, 2.0, (0.84, 0.90, 1.0)),
             _area("HomeRim", HOME, HEAD_HOME + Vector((-0.6, 1.2, 0.9)), HEAD_HOME, 200, 0.8, (0.92, 0.95, 1.0)),
             _area("WindowSpill", HOME, Vector(WIN_LOC) + Vector((0, 0.3, 0)), HEAD_HOME, 220, 1.2, (0.85, 0.92, 1.0))],
    "lab": [_area("LabKey", LAB, VIAL + Vector((0.3, -0.35, 0.4)), VIAL, 90, 0.4, (1.0, 0.98, 0.95)),
            _area("LabFill", LAB, VIAL + Vector((-0.35, -0.2, 0.25)), VIAL, 45, 0.7, (0.82, 0.90, 1.0))],
    "xray": [_area("XKey", ANAT, ANATP + Vector((0.08, -0.06, 0.07)), ANATP, 0.25, 0.06, (1.0, 0.85, 0.82)),
             _area("XFill", ANAT, ANATP + Vector((-0.06, 0.05, -0.03)), ANATP, 0.10, 0.08, (0.55, 0.65, 1.0))],
}
BASE = {l.name: l.data.energy for ls in LIGHTS.values() for l in ls}
for set_name, ls in LIGHTS.items():
    for l in ls:
        bake(l.data, "energy", [BASE[l.name] * (SET_OF[i] == set_name) for i in range(len(T))])

# ---------------------------------------------------------------- cameras (v3: moving splines, DOF from subject size)
cams = S.Cameras(scene, T, F, CAST)


def span(name):
    i = next(k for k, s in enumerate(SHOTS) if s[1] == name)
    return SHOTS[i][0], (SHOTS[i + 1][0] if i + 1 < len(SHOTS) else DUR)


def mid(name):
    a, b = span(name)
    return (a + b) / 2


W = cams.world_at
# Hand shots: the camera sits on the CAM_SIDE ray from the nodules (the side the ray cast found skin on), far enough
# that the whole hand (~10 cm) fits the 9:16 frame at 85 mm; it pushes in over the shot.
a, b = span("PalmHookECU")
N0 = W(nod_c, mid("PalmHookECU"))
side_x = CAM_SIDE.cross(Vector((0, 0, 1))).normalized()
cams.cam("PalmHookECU", a, b, keys=[(a, N0 + CAM_SIDE * 0.30), (b, N0 + CAM_SIDE * 0.22)],
         lens=85, aim=nod_c, depth=0.04, shake=0.0006, ease="cine")
a, b = span("PalmHookOrbit")
N1 = W(nod_c, mid("PalmHookOrbit"))
cams.cam("PalmHookOrbit", a, b, keys=[(a, N1 + CAM_SIDE * 0.21 + side_x * 0.06), (b, N1 + CAM_SIDE * 0.17 - side_x * 0.05)],
         lens=85, aim=nod_c, depth=0.035, shake=0.0006)
a, b = span("KitchenWide")
TC = TABLE + Vector((0, 0.15, TOP_Z + 0.15))
cams.cam("KitchenWide", a, b, keys=[(a, TC + Vector((0.75, -1.85, 0.35))), (b, TC + Vector((0.50, -1.45, 0.25)))],
         lens=32, aim=TC, focus=TC, depth=0.9, shift_y=-0.04, shake=0.001)
a, b = span("FoodInsertCU")
cams.cam("FoodInsertCU", a, b, path=S.orbit(FOOD_C, 0.42, 10, 32, 0.20, 0.14), lens=50,
         aim=FOOD_C + Vector((0, 0, 0.02)), depth=0.3, shake=0.0008)
a, b = span("FaceMedium")
face_pt = him.anchor("Face", "Head", Vector((him.x0, him.nose.y + 0.05, him.nose.z - 0.01)), CAST)
FC = W(face_pt, mid("FaceMedium"))
cams.cam("FaceMedium", a, b, path=S.orbit(FC, 0.85, 14, -6, 0.02, 0.0), lens=50, aim=face_pt,
         depth=0.25, shift_y=-0.08, shake=0.0008)
a, b = span("PalmShockECU")
N2 = W(nod_c, mid("PalmShockECU"))
cams.cam("PalmShockECU", a, b, keys=[(a, N2 + CAM_SIDE * 0.26 - side_x * 0.05), (b, N2 + CAM_SIDE * 0.16 - side_x * 0.02)],
         lens=85, aim=nod_c, depth=0.035, shake=0.0006, ease="cine")
a, b = span("VialInsert")
VC = VIAL + Vector((0, 0, 0.01))
cams.cam("VialInsert", a, b, keys=[(a, VC + Vector((0.10, -0.30, 0.05))), (b, VC + Vector((0.06, -0.22, 0.03)))],
         lens=85, aim=VC, depth=0.08, shake=0.0005)
VMID = (VESSEL_PTS[0] + VESSEL_PTS[-1]) / 2
a, b = span("VesselOrbit")
cams.cam("VesselOrbit", a, b, path=S.orbit(VMID, 0.36, -30, 5, 0.06, 0.03), lens=60, aim=VMID, depth=0.12,
         shake=0.0003)
a, b = span("PlaqueOrbit")
cams.cam("PlaqueOrbit", a, b, path=S.orbit(erupt_centre, 0.20, -18, 22, 0.05, 0.02, r1=0.15), lens=70,
         aim=erupt_centre, depth=0.06, shake=0.0003)
a, b = span("EruptBuildCU")
cams.cam("EruptBuildCU", a, b, keys=[(a, erupt_centre + Vector((0.05, -0.13, 0.05))), (b, erupt_centre + Vector((0.035, -0.095, 0.035)))],
         lens=85, aim=erupt_centre, depth=0.04, shake=0.0004)
a, b = span("EruptSlomo")
cams.cam("EruptSlomo", a, b, keys=[(a, erupt_centre + Vector((0.03, -0.09, 0.03))), (b, erupt_centre + Vector((0.025, -0.075, 0.025)))],
         lens=85, aim=erupt_centre, depth=0.035, shake=0.0002, ease="cine")
a, b = span("CloserPull")
N3 = W(nod_c, mid("CloserPull"))
cams.cam("CloserPull", a, b, keys=[(a, N3 + CAM_SIDE * 0.22), (b, N3 + CAM_SIDE * 0.55 + Vector((0, 0, 0.12)))],
         lens=65, aim=nod_c, focus=nod_c, depth=0.08, shift_y=-0.05, shake=0.0008, ease="cine")

cams.markers(SHOTS)
S.check_shots(SHOTS, DUR)


def gaze_target(t):
    s = shot_at(t)
    if s[2] == "home" and B[1] <= t < B[4]:
        return CHEESE_C
    if s[2] == "home" and t >= B[4]:
        return W(palm_pt, t)
    return None


him.bake_gaze(FRAMES, T, gaze_target, CAST, seed=11)

if VO_WAV and os.path.exists(VO_WAV):
    scene.sequence_editor_create()
    seq = scene.sequence_editor
    strips = seq.strips if hasattr(seq, "strips") else seq.sequences
    strips.new_sound("VO", VO_WAV, channel=1, frame_start=1)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("SAVED", OUT, "END", END, "FPS", FPS, "SHOTS", [(round(s[0], 2), s[1]) for s in SHOTS])

for f in STILLS:
    scene.frame_set(f)
    marks = [m for m in scene.timeline_markers if m.frame <= f]
    scene.camera = max(marks, key=lambda m: m.frame).camera
    scene.render.filepath = OUT.replace(".blend", f"_f{f:05d}.png")
    bpy.ops.render.render(write_still=True)
    print("RENDERED", scene.render.filepath)
