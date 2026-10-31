"""hiccups-68-years: "Charles Osborne hiccuped for sixty-eight years straight" (Iowa farmhand, hiccups from 1922 to 1990,
Guinness record; Smithsonian Magazine "The Curious Case of Charles Osborne": fall on a Nebraska farm in 1922, burst vessel in
the brain, theory that the brain-stem inhibitor of the hiccup reflex was damaged, 20-40 diaphragm spasms a minute, ~430 million
hiccups, married twice, eight children, stopped suddenly in 1990, died 1991 aged 97).

Run (daily_render.ps1): blender -b --python scene.py -- <ROOT>/blend/<slug>.blend vo=<wav> beats=<json> fps=30
Optional: stills=1,200 pct=100 samples=128 device=gpu|cpu root=<ROOT>

v3 toolkit: every model is built in Blender from code (scripts/kit.py), he acts procedurally on the mixamorig bones
(scripts/actor.py) and every camera is a moving spline that is already in motion on the cut (scripts/shot.py).
No captions, no on-screen text (owner's rule). Timing comes only from the beats JSON. SYNC constants must match mix.py.

Cast: him = blend/char_hero.blend. One actor. Sets: HOME, BARN, BRAIN, CHEST, TALLY. Set changes are HARD CUTS.
"""
import json
import math
import os
import random
import sys
import warnings

import bpy
import bmesh  # noqa: E402  (after bpy: the bpy module provides it)
from mathutils import Euler, Matrix, Vector

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
SAMPLES = int(opts.get("samples", 128))
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
K.init(scene, seed=61)
random.seed(61)
CAST = K.coll("Cast")
him = A.Actor.from_scene("Him")
him.measure()
him.setup_ik(CAST)
print("CAST", him.rig.name, "height", round(him.top, 3))

# ---------------------------------------------------------------- timeline (seconds)
META = json.load(open(BEATS_JSON, encoding="utf-8"))
B = [float(b["start"]) for b in META["beats"]]
assert len(B) == 10, f"expected 10 beats, got {len(B)}"
NARR = float(META["duration"])
DUR = NARR + 36.0 / FPS                      # the template's +36 frame tail (mix.py: TAIL)
BE = B[1:] + [NARR]


def at(i, frac):
    return B[i] + frac * (BE[i] - B[i])


def F(t):
    return int(round(t * FPS)) + 1


END = F(DUR)
FRAMES = range(1, END + 1)
T = [(f - 1) / FPS for f in FRAMES]

# SYNC with mix.py
SLIP, IMP = at(2, 0.36), at(2, 0.52)              # he slips, then hits the barn floor
HIC1 = at(2, 0.78)                                # the first hiccup (on the floor)
HIC_GAP = 1.5                                     # seconds between hiccups (real: 1.5-3 s)
HIC_END = at(8, 0.40)                             # the last hiccup (1990)
HOOK_HICS = [0.30 + HIC_GAP * k for k in range(8) if 0.30 + HIC_GAP * k < B[1] - 0.2]
HICS = HOOK_HICS + [HIC1 + HIC_GAP * k for k in range(40) if HIC1 + HIC_GAP * k <= HIC_END + 1e-6]
BURST = at(3, 0.66)                               # the vessel in his brain bursts
DAM = at(4, 0.30)                                 # the "off switch" is damaged
DEAD = at(4, 0.62)                                # ... and is dead
SLO_A, SLO_B = B[5], at(5, 0.66)                  # slow-mo window: the diaphragm snap (money moment)
ACT_A, ACT_B = SLO_A, SLO_A + (SLO_B - SLO_A) * 0.4
HIT_F = 0.42
HIT = SLO_A + HIT_F * (SLO_B - SLO_A)             # screen time of the hiccup
HIT_ACT = ACT_A + HIT_F * (ACT_B - ACT_A)         # the same moment in action time
TALLY_A, TALLY_B = B[6], at(6, 0.55)
RELIEF = at(8, 0.55)
SMILE = at(9, 0.50)
print("TIMELINE", [round(b, 2) for b in B], "END", END, "HIT", round(HIT, 2), "HICS", len(HICS))

S.setup_render(scene, fps=FPS, end=END, pct=PCT, samples=SAMPLES, device=DEVICE)
scene.cycles.adaptive_threshold = 0.015 if SAMPLES >= 96 else 0.03

def bake(idb, path, values, index=None, interp="LINEAR"):
    return A.bake(idb, path, values, FRAMES, index=index, interp=interp)


def bake_vec(idb, path, vecs, n=3, interp="LINEAR"):
    A.bake_vec(idb, path, vecs, FRAMES, n=n, interp=interp)


ramp, env, spike, smooth, wobble = A.ramp, A.env, A.spike, A.smooth, A.wobble
warp = A.timewarp(SLO_A, SLO_B, ACT_A, ACT_B)


def xglow(name, color, strength, blend=0.3, core=0.03):
    """Rim-glow X-ray shell: emissive at grazing angles, see-through face-on."""
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
    em.name = "Emission"
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = strength
    tr = N.new("ShaderNodeBsdfTransparent")
    mx = N.new("ShaderNodeMixShader")
    L.new(mr.outputs[0], mx.inputs[0])
    L.new(tr.outputs[0], mx.inputs[1])
    L.new(em.outputs[0], mx.inputs[2])
    L.new(mx.outputs[0], out.inputs["Surface"])
    return m


def glowy(name, color, rough=0.4, sss=0.3, emit=0.0):
    """Principled with its own (bakeable) base colour and emission, never shared through kit's cache."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Subsurface Weight"].default_value = sss
    b.inputs["Subsurface Scale"].default_value = 0.01
    b.inputs["Emission Color"].default_value = (*color, 1)
    b.inputs["Emission Strength"].default_value = emit
    return m


BSDF = 'nodes["Principled BSDF"].inputs'

ramp, env, spike, smooth, wobble = A.ramp, A.env, A.spike, A.smooth, A.wobble
warp = A.timewarp(SLO_A, SLO_B, ACT_A, ACT_B)


def xglow(name, color, strength, blend=0.3, core=0.03):
    """Rim-glow X-ray shell: emissive at grazing angles, see-through face-on."""
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
    em.name = "Emission"
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = strength
    tr = N.new("ShaderNodeBsdfTransparent")
    mx = N.new("ShaderNodeMixShader")
    L.new(mr.outputs[0], mx.inputs[0])
    L.new(tr.outputs[0], mx.inputs[1])
    L.new(em.outputs[0], mx.inputs[2])
    L.new(mx.outputs[0], out.inputs["Surface"])
    return m


def glowy(name, color, rough=0.4, sss=0.3, emit=0.0):
    """Principled with its own (bakeable) base colour and emission, never shared through kit's cache."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Subsurface Weight"].default_value = sss
    b.inputs["Subsurface Scale"].default_value = 0.01
    b.inputs["Emission Color"].default_value = (*color, 1)
    b.inputs["Emission Strength"].default_value = emit
    return m


def hidden_from_rays(o):
    o.visible_diffuse = o.visible_glossy = o.visible_transmission = False


BSDF = 'nodes["Principled BSDF"].inputs'

# ---------------------------------------------------------------- sets
HOMEP, BARNP, TALLYP = Vector((0, 0, 0)), Vector((40, 0, 0)), Vector((80, 0, 0))
CHESTP, BRAINP = Vector((0, 0, -60)), Vector((0, 0, -120))
HOME, BARN, CHEST, BRAIN, TALLY = (K.coll("SetHome"), K.coll("SetBarn"), K.coll("SetChest"), K.coll("SetBrain"),
                                   K.coll("SetTally"))

# HOME: a sunny living room, eight photo frames (his eight children) on the back wall, window on the right.
K.room(HOME, origin=HOMEP + Vector((0, 1.0, 0)), size=(6.0, 5.2, 2.8), floor_mat=K.floorboards(),
       wall_color=(0.88, 0.80, 0.68), name="HomeRoom", openings=[(1.9, 1.5, 1.44, 1.44)])
K.window(HOME, HOMEP + Vector((1.9, 3.57, 1.5)), size=(1.3, 1.3), curtains=True, sky=(1.0, 0.93, 0.78), sky_strength=4.0)
P_HOME = HOMEP + Vector((-0.6, 1.2, 0))                          # where he stands (feet)
FRAME_X = [-2.65 + 0.47 * k for k in range(8)]
for k, fx in enumerate(FRAME_X):
    K.picture_frame(HOME, HOMEP + Vector((fx, 3.55, 1.62 + 0.05 * (k % 2))), (0.30, 0.38), name=f"Kid{k}", seed=21 + k)
K.rug(HOME, P_HOME + Vector((0.3, 0.2, 0.0)), size=(2.8, 2.0), name="HomeRug")
K.floor_lamp(HOME, HOMEP + Vector((2.9, 2.6, 0)))
K.potted_plant(HOME, HOMEP + Vector((-2.7, 0.2, 0)), h=1.3, seed=4)
K.sofa(HOME, HOMEP + Vector((0.6, 3.0, 0)), width=1.9)
K.mug(HOME, HOMEP + Vector((1.2, 0.2, 0.0)), color=(0.9, 0.9, 0.92))

# BARN: a 1922 wooden barn: plank walls and floor, hay bales, a hanging lantern, a hog.
barn_wall = K.wood("BarnPlank", (0.42, 0.25, 0.12), (0.20, 0.10, 0.04), rough=0.7, scale=2.0)
K.room(BARN, origin=BARNP + Vector((0, 1.0, 0)), size=(7.0, 5.2, 3.2), floor_mat=K.wood("BarnFloor", (0.50, 0.36, 0.20), (0.25, 0.15, 0.07), rough=0.8),
       wall_color=(0.55, 0.38, 0.22), name="BarnRoom", openings=[(-2.2, 1.7, 1.0, 1.0)])
K.window(BARN, BARNP + Vector((-2.2, 3.57, 1.7)), size=(0.9, 0.9), curtains=False, sky=(1.0, 0.85, 0.55), sky_strength=5.0)
hay_m = K.fabric("Hay", (0.80, 0.62, 0.22), rough=0.95, sheen=0.1, weave=1400, bump=0.9)
for k, (hx, hy, hz, rz_) in enumerate(((1.9, 3.0, 0.0, 0.1), (2.7, 2.9, 0.0, -0.05), (2.3, 2.9, 0.46, 0.08), (-3.0, 2.6, 0.0, 0.2),
                                       (-1.2, 3.1, 0.0, 0.0), (-1.2, 3.1, 0.46, 0.15), (3.0, 1.0, 0.0, 0.3))):
    K.cushion(f"HayBale{k}", BARN, (0.95, 0.5, 0.46), BARNP + Vector((hx, hy, hz + 0.23)), hay_m, puff=0.12, rot=(0, 0, rz_), seed=k)
for k in range(26):                                              # loose straw on the floor
    rr = random.Random(k)
    K.cyl(f"Straw{k}", BARN, 0.004, 0.5, BARNP + Vector((rr.uniform(-2.2, 2.2), rr.uniform(-0.2, 2.8), 0.006)), hay_m,
          rot=(math.radians(90), 0, rr.uniform(0, 3.1)), verts=6)
K.rbox("BarnBeam", BARN, (7.0, 0.22, 0.22), BARNP + Vector((0, 1.4, 2.7)), K.wood("BeamWood", (0.35, 0.2, 0.1), (0.15, 0.07, 0.03)), bevel=0.02)
lantern_m = glowy("Lantern", (1.0, 0.65, 0.25), rough=0.3, sss=0.0, emit=14.0)
K.cyl("LanternRod", BARN, 0.006, 0.5, BARNP + Vector((0.2, 1.4, 2.4)), K.metal("LanternMetal", (0.05, 0.05, 0.05), 0.4), verts=8)
K.sphere("Lantern", BARN, 0.07, BARNP + Vector((0.2, 1.4, 2.12)), lantern_m, scale=(1, 1, 1.25), subdiv=3)
P_BARN = BARNP + Vector((-0.55, 0.9, 0))                         # where he stands (feet); he faces +X, toward the hog
PIG = BARNP + Vector((0.28, 0.9, 0))                             # the hog's centre (it faces -Y, toward the camera)
pig_m = K.plastic("HogSkin", (0.90, 0.56, 0.52), 0.55, sss=0.35)
pig_dark = K.plastic("HogDark", (0.12, 0.07, 0.07), 0.4)
pig_ear = K.plastic("HogEar", (0.82, 0.46, 0.43), 0.6, sss=0.3)
HOG_BODY = K.sphere("HogBody", BARN, 1.0, PIG + Vector((0, 0.05, 0.52)), pig_m, scale=(0.31, 0.66, 0.35), subdiv=4)
K.sphere("HogHam", BARN, 1.0, PIG + Vector((0, 0.44, 0.50)), pig_m, scale=(0.30, 0.30, 0.34), subdiv=4)
K.sphere("HogHead", BARN, 1.0, PIG + Vector((0, -0.66, 0.50)), pig_m, scale=(0.20, 0.24, 0.19), subdiv=4)
K.cyl("HogSnout", BARN, 0.085, 0.14, PIG + Vector((0, -0.88, 0.45)), pig_m, rot=(math.radians(90), 0, 0), verts=24)
for sx in (-1, 1):
    K.sphere("HogNostril", BARN, 0.013, PIG + Vector((sx * 0.03, -0.955, 0.455)), pig_dark, subdiv=2)
    K.sphere("HogEye", BARN, 0.018, PIG + Vector((sx * 0.14, -0.77, 0.56)), pig_dark, subdiv=2)
    e_ = K.sphere("HogEar", BARN, 1.0, PIG + Vector((sx * 0.15, -0.60, 0.69)), pig_ear, scale=(0.09, 0.035, 0.11), subdiv=3)
    e_.rotation_euler = (math.radians(-10), sx * math.radians(35), sx * math.radians(25))
    for sy in (-1, 1):
        K.cyl("HogLeg", BARN, 0.065, 0.32, PIG + Vector((sx * 0.17, sy * 0.40 + 0.05, 0.17)), pig_m, verts=16)
        K.cyl("HogHoof", BARN, 0.06, 0.05, PIG + Vector((sx * 0.17, sy * 0.40 + 0.05, 0.025)), pig_dark, verts=16)
K.tube("HogTail", BARN, [PIG + Vector((0, 0.70, 0.66)), PIG + Vector((0.04, 0.78, 0.70)), PIG + Vector((-0.03, 0.82, 0.62)),
                          PIG + Vector((0.03, 0.80, 0.58))], 0.014, pig_m)
K.rbox("Bucket", BARN, (0.30, 0.30, 0.28), BARNP + Vector((-1.9, 1.0, 0.14)), K.metal("BucketMetal", (0.45, 0.47, 0.5), 0.45), bevel=0.04)

# CHEST: an X-ray rib cage (camera side open): lungs, trachea, vocal cords, the diaphragm dome, a spine.
lung_m = glowy("Lung", (0.92, 0.50, 0.55), rough=0.5, sss=0.4, emit=0.5)
LUNGS = [K.sphere(f"Lung{sx}", CHEST, 1.0, CHESTP + Vector((sx * 0.165, 0.0, 0.08)), lung_m, scale=(0.14, 0.12, 0.23), subdiv=4) for sx in (-1, 1)]
tr_m = K.plastic("Trachea", (0.82, 0.62, 0.62), 0.35, sss=0.3)
K.tube("Trachea", CHEST, [CHESTP + Vector((0, 0.0, 0.42)), CHESTP + Vector((0, 0.0, 0.2))], 0.026, tr_m, res=12)
for sx in (-1, 1):
    K.tube(f"Bronchus{sx}", CHEST, [CHESTP + Vector((0, 0.0, 0.2)), CHESTP + Vector((sx * 0.07, 0.0, 0.14)), CHESTP + Vector((sx * 0.12, 0.0, 0.10))],
           0.016, tr_m, res=10)
for k in range(8):
    K.tube(f"TrachRing{k}", CHEST, [CHESTP + Vector((-0.026, 0.0, 0.25 + 0.025 * k)), CHESTP + Vector((0.0, -0.026, 0.25 + 0.025 * k)),
                                      CHESTP + Vector((0.026, 0.0, 0.25 + 0.025 * k))], 0.004, tr_m, res=4)
VC = CHESTP + Vector((0, 0.0, 0.44))                              # the vocal cords (larynx), schematic and enlarged
cord_m = glowy("Cord", (0.85, 0.36, 0.40), rough=0.35, sss=0.4, emit=0.3)
CORDS = [K.sphere(f"Cord{sx}", CHEST, 1.0, VC + Vector((sx * 0.026, 0, 0)), cord_m, scale=(0.018, 0.034, 0.010), subdiv=3) for sx in (-1, 1)]
larynx_m = K.plastic("Larynx", (0.75, 0.55, 0.56), 0.4, sss=0.3)
flash_m = glowy("CordFlash", (0.0, 0.0, 0.0), emit=0.0)
flash_m.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (1.0, 0.97, 0.9, 1)
FLASH = K.sphere("CordFlash", CHEST, 0.02, VC + Vector((0, -0.01, 0.0)), flash_m, subdiv=3)
hidden_from_rays(FLASH)
dia_m = glowy("Diaphragm", (0.72, 0.12, 0.12), rough=0.45, sss=0.35, emit=0.15)
DIA = K.lathe("Diaphragm", CHEST, [(0.0, 0.14), (0.08, 0.135), (0.17, 0.115), (0.26, 0.07), (0.34, 0.0)], CHESTP + Vector((0, 0.0, -0.16)), dia_m,
              thickness=0.014)
DIA_Z0 = DIA.location.z
bone_m = K.bone_mat()
RIBS = []
for k in range(8):
    z = 0.32 - 0.058 * k
    rx = 0.22 + 0.07 * math.sin(math.pi * min(1.0, (k + 1.5) / 7.5)) * 1.1
    ry = 0.15 + 0.03 * math.sin(math.pi * min(1.0, (k + 1.5) / 7.5))
    pts = [CHESTP + Vector((rx * math.cos(math.radians(a)), 0.03 + ry * math.sin(math.radians(a)), z - 0.015 * (1 - math.sin(math.radians(a))))) for a in range(-30, 211, 20)]
    RIBS.append(K.tube(f"Rib{k}", CHEST, pts, 0.0085, bone_m, res=6))
for k in range(14):
    K.sphere(f"Vertebra{k}", CHEST, 1.0, CHESTP + Vector((0, 0.19, 0.38 - 0.052 * k)), bone_m, scale=(0.03, 0.026, 0.021), subdiv=3)
chest_shell = K.sphere("ChestShell", CHEST, 1.0, CHESTP + Vector((0, 0.04, 0.12)), xglow("ChestGlow", (0.3, 0.6, 1.0), 1.4, blend=0.35, core=0.0),
                       scale=(0.40, 0.26, 0.46), subdiv=4)
hidden_from_rays(chest_shell)
AIR_M = glowy("Air", (0.7, 0.9, 1.0), rough=0.1, sss=0.0, emit=6.0)
AIR = [K.sphere(f"Air{k}", CHEST, 1.0, CHESTP, AIR_M, scale=(0.008,) * 3, subdiv=2) for k in range(28)]
CHC = CHESTP + Vector((0.0, 0.0, 0.14))

# BRAIN: an X-ray brain, the brain stem with a vessel that bursts and an amber "off switch" nucleus.
BR_SIZE = (0.15, 0.19, 0.125)
brain_parts = K.brain(BRAIN, BRAINP, size=BR_SIZE, name="Brain", subdiv=5)
brain_shell = K.sphere("BrainShell", BRAIN, 1.0, BRAINP + Vector((0, 0.03, -0.04)), xglow("BrainGlow", (0.35, 0.65, 1.0), 1.6, blend=0.3, core=0.0),
                       scale=(0.17, 0.23, 0.20), subdiv=4)
hidden_from_rays(brain_shell)
STEM = BRAINP + Vector((0, 0.058, -0.15))                         # on the brain stem (front surface is y~STEM.y-0.03)
blood_m = glowy("Blood", (0.70, 0.03, 0.03), rough=0.3, sss=0.2, emit=1.0)
VESSEL_PTS = [STEM + Vector((0.02, -0.036, 0.10)), STEM + Vector((-0.012, -0.040, 0.04)), STEM + Vector((0.012, -0.040, -0.02)), STEM + Vector((-0.005, -0.038, -0.07))]
K.tube("Vessel", BRAIN, VESSEL_PTS, 0.0045, blood_m, res=8)
BURST_P = STEM + Vector((0.012, -0.045, -0.02))
CLOUD = K.sphere("BloodCloud", BRAIN, 1.0, BURST_P, xglow("BloodCloud", (1.0, 0.08, 0.05), 5.0, blend=0.2, core=0.25), subdiv=3)
hidden_from_rays(CLOUD)
DROPS = []
rngd = random.Random(7)
for k in range(46):
    d_ = Vector((rngd.uniform(-1, 1), rngd.uniform(-1.2, -0.2), rngd.uniform(-0.5, 1)))
    DROPS.append((K.sphere(f"Drop{k}", BRAIN, 1.0, BURST_P, blood_m, subdiv=2), d_.normalized() * rngd.uniform(0.03, 0.10), rngd.uniform(0.003, 0.007)))
sw_m = glowy("OffSwitch", (1.0, 0.62, 0.12), rough=0.3, sss=0.0, emit=5.0)
SWITCH_P = STEM + Vector((-0.002, -0.034, 0.045))
SWITCH = K.sphere("Switch", BRAIN, 0.014, SWITCH_P, sw_m, scale=(1.0, 0.6, 1.0), subdiv=3)
nerve_m = glowy("Nerve", (0.9, 0.85, 0.7), rough=0.3, sss=0.0, emit=0.4)
NERVE_PTS = [SWITCH_P, SWITCH_P + Vector((0.02, -0.004, -0.06)), SWITCH_P + Vector((-0.01, -0.004, -0.12)), SWITCH_P + Vector((0.0, -0.004, -0.20))]
K.tube("Nerve", BRAIN, NERVE_PTS, 0.0025, nerve_m, res=6)
SIG_M = glowy("Signal", (1.0, 0.72, 0.2), rough=0.2, sss=0.0, emit=10.0)
SIGS = [K.sphere(f"Sig{k}", BRAIN, 0.0042, SWITCH_P, SIG_M, subdiv=2) for k in range(10)]
BRC = STEM + Vector((0, -0.02, 0.02))

# TALLY: a wall of dots, one pop per hiccup (schematic: stands for ~430 million)
TCOLS, TROWS = 18, 26
dot_m = glowy("TallyDot", (1.0, 0.78, 0.35), rough=0.2, sss=0.0, emit=7.0)
TDOTS = []
for r_ in range(TROWS):
    for c_ in range(TCOLS):
        p = TALLYP + Vector(((c_ - (TCOLS - 1) / 2) * 0.11, 0.0, (r_ - (TROWS - 1) / 2) * 0.11))
        o = K.sphere(f"Dot{r_}_{c_}", TALLY, 0.03, p, dot_m, subdiv=2)
        o.scale = (0, 0, 0)
        TDOTS.append((o, r_ * TCOLS + c_))
TC = TALLYP

SEAT_UNUSED = None

# ---------------------------------------------------------------- shots (start, camera, set, pose)
SHOTS = [
    (0.0, "HookFace", "home", "home"),
    (at(0, 0.55), "HookWide", "home", "home"),
    (B[1], "BarnWide", "barn", "barn"),
    (at(1, 0.50), "PigCU", "barn", "barn"),
    (B[2], "LiftMed", "barn", "barn"),
    (at(2, 0.34), "FallLow", "barn", "barn"),
    (B[3], "BrainOrbit", "brain", "barn"),
    (at(3, 0.50), "BurstMacro", "brain", "barn"),
    (B[4], "OffSwitch", "brain", "home"),
    (at(4, 0.52), "SignalLost", "brain", "home"),
    (SLO_A, "HicSlomo", "chest", "home"),
    (SLO_B, "CordsCU", "chest", "home"),
    (TALLY_A, "TallyFly", "tally", "home"),
    (TALLY_B, "WearyFace", "home", "home"),
    (B[7], "FamilyWide", "home", "home"),
    (at(7, 0.50), "FramesTruck", "home", "home"),
    (B[8], "LastHicFace", "home", "home"),
    (at(8, 0.50), "ChestCalm", "chest", "home"),
    (B[9], "HomeOrbit", "home", "home"),
    (at(9, 0.42), "Closer", "home", "home"),
]


def shot_at(t):
    return max((s for s in SHOTS if s[0] <= t + 1e-6), key=lambda s: s[0])


SH = [shot_at(t) for t in T]
SET_OF = [s[2] for s in SH]
REST_HIPS = him.hips0.copy()


def fall_theta(t):
    u = max(0.0, min(1.0, (t - SLIP) / (IMP - SLIP)))
    bounce = 0.035 * spike(t, IMP + 0.0, 0.001, 0.12) * math.sin(14 * (t - IMP)) if t >= IMP else 0.0
    return -math.radians(88) * (u * u) + bounce, 0.11 * u


def him_root(s, t):
    """(location, euler) of his rig object so that his feet pivot on the floor mark of the set he is in."""
    if s[2] == "barn":
        th, lift = fall_theta(t)
        rz = math.pi / 2
        P = P_BARN
    else:
        th, lift, rz, P = 0.0, 0.0, 0.0, P_HOME
    R = Euler((th, 0, rz), "XYZ").to_matrix()
    off = R @ Vector((him.x0, REST_HIPS.y, 0))
    return P - off + Vector((0, 0, lift)), (th, 0, rz)


# ---------------------------------------------------------------- performance
BLINKS = [1.0 + 2.9 * k for k in range(60) if 1.0 + 2.9 * k < DUR]


def hic_ch(t):
    return sum(spike(t, h, 0.04, 0.20) for h in HICS)


def channels(t):
    ch = {}
    ch["hic"] = hic_ch(t)
    ch["lift"] = env(t, B[2] - 0.05, B[2] + 0.30, SLIP - 0.02, SLIP + 0.04)          # bends to the hog and strains
    ch["fall"] = env(t, SLIP - 0.02, SLIP + 0.06, IMP, IMP + 0.10)                   # arms fling up while slipping
    ch["lying"] = ramp(t, IMP, IMP + 0.2)
    ch["weary"] = env(t, TALLY_B, TALLY_B + 0.4, B[7] - 0.05, B[7] + 0.15)
    ch["happy"] = env(t, B[7] + 0.2, B[7] + 0.7, B[8] - 0.1, B[8] + 0.1)
    ch["calm"] = ramp(t, HIC_END + 0.2, HIC_END + 0.8)
    ch["surprise"] = env(t, HIC_END + 0.15, HIC_END + 0.4, HIC_END + 1.0, HIC_END + 1.5)
    ch["smile"] = max(0.55 * ch["calm"], ramp(t, SMILE - 0.3, SMILE + 0.3))
    ch["blink"] = max((env(t, b_ - 0.03, b_, b_ + 0.05, b_ + 0.12) for b_ in BLINKS), default=0.0)
    return ch


legs_stand = him.standing_legs()
MOUTH = him.mouth.copy()
SIDE_L = REST_HIPS + Vector((0.22, 0.02, -0.12))
SIDE_R = REST_HIPS + Vector((-0.22, 0.02, -0.12))
HOGL = Vector((him.x0 + 0.17, REST_HIPS.y - 0.50, REST_HIPS.z - 0.42))                # hands on the hog's flank (rig-local)
HOGR = Vector((him.x0 - 0.17, REST_HIPS.y - 0.50, REST_HIPS.z - 0.40))
FLING_L = Vector((him.x0 + 0.42, REST_HIPS.y - 0.05, REST_HIPS.z + 0.72))
FLING_R = Vector((him.x0 - 0.42, REST_HIPS.y - 0.05, REST_HIPS.z + 0.72))
face_pt = him.anchor("Face", "Head", Vector((him.x0, him.nose.y + 0.05, him.nose.z - 0.01)), CAST)
eyes_mid = him.anchor("Eyes", "Head", (him.eye_l + him.eye_r) / 2, CAST)
chest_pt = him.anchor("Chest", "Spine2", him.bone_rest_head("Spine2"), CAST)

for i, t in enumerate(T):
    s = SH[i]
    ch = channels(t)
    br = math.sin(t * 2 * math.pi / 3.6)
    hic, lift, fall, lying = ch["hic"], ch["lift"], ch["fall"], ch["lying"]
    in_barn = s[2] == "barn"
    wary = ch["weary"]
    spec = {
        "Hips": [(A.Z, 0.6 * wobble(t, 1))],
        "Spine": [(A.X, 0.6 * br + 26 * lift - 10 * fall - 2.5 * hic), (A.Z, 0.8 * wobble(t, 2))],
        "Spine1": [(A.X, 0.7 * br + 14 * lift - 6 * fall - 2.0 * hic + 3 * wary)],
        "Spine2": [(A.X, 1.5 + 0.6 * br + 6 * lift - 2.5 * hic)],
        "Neck": [(A.X, -4 * lift + 5 * fall - 3 * hic + 4 * wary - 3 * ch["surprise"]), (A.Z, 1.2 * wobble(t, 4))],
        "Head": [(A.X, 1.0 * wobble(t, 7, 0.6) - 8 * hic + 5 * wary + 8 * fall - 3 * ch["surprise"]),
                 (A.Z, 1.6 * wobble(t, 5, 0.5) + 3 * ch["surprise"] * math.sin(6 * t)),
                 (A.Y, 1.0 * wobble(t, 6) + 1.5 * hic * math.sin(37 * t))],
        "LeftShoulder": [(A.Y, 7 * hic + 6 * fall)],
        "RightShoulder": [(A.Y, -7 * hic - 6 * fall)],
    }
    rots = {}
    for bone, axes in spec.items():
        if him.has(bone):
            q = A.Quaternion()
            for axis, deg in axes:
                q = q @ him.q(bone, axis, deg)
            rots[bone] = q
    rots.update(legs_stand)
    for bone in him.fingers():
        j = int(bone[-1])
        curl = ({1: 22, 2: 30, 3: 22} if "Thumb" not in bone else {1: 8, 2: 14, 3: 10})[j]
        curl += 40 * lift                                              # grips the hog
        rots[bone] = A.Quaternion((1, 0, 0), math.radians(curl))
    sh = {}
    for side in ("Left", "Right"):
        sh[f"eyeBlink{side}"] = min(1.0, ch["blink"] + 0.55 * hic + 0.15 * ch["smile"])
        sh[f"eyeWide{side}"] = 0.35 * hic + 0.7 * fall + 0.7 * ch["surprise"]
        sh[f"browDown{side}"] = 0.45 * lift + 0.15 * wary
        sh[f"eyeSquint{side}"] = 0.3 * lift + 0.3 * ch["smile"] + 0.2 * ch["happy"]
        sh[f"mouthFrown{side}"] = 0.25 * wary + 0.2 * lift
        sh[f"mouthSmile{side}"] = 0.8 * ch["smile"] + 0.6 * ch["happy"] * (1 - 0.6 * hic)
        sh[f"cheekSquint{side}"] = 0.4 * ch["smile"] + 0.3 * ch["happy"]
        sh[f"mouthPress{side}"] = 0.4 * lift
    sh["browInnerUp"] = 0.4 * hic + 0.8 * fall + 0.6 * ch["surprise"] + 0.2 * wary
    sh["cheekPuff"] = 0.3 * lift
    sh["mouthPucker"] = 0.3 * hic
    sh["jawOpen"] = 0.22 * hic + 0.5 * fall + 0.25 * ch["surprise"]
    ikl, ikr = SIDE_L + Vector((0, 0, 0.004 * br + 0.012 * hic)), SIDE_R + Vector((0, 0, 0.004 * br + 0.012 * hic))
    if lift > 0.001:
        ikl, ikr = ikl.lerp(HOGL, lift), ikr.lerp(HOGR, lift)
    if fall > 0.001:
        ikl, ikr = ikl.lerp(FLING_L, fall), ikr.lerp(FLING_R, fall)
    him.record(rots, sh, ikl, ikr, aim=(0.0, 0.0), follow={}, root=him_root(s, t))
him.bake(FRAMES)
for fc in A.fcurves_of(him.rig):
    if fc.data_path in ("location", "rotation_euler"):
        fc.keyframe_points.foreach_set("interpolation", [0] * len(fc.keyframe_points))   # teleports are cuts

# ---------------------------------------------------------------- the chest: the diaphragm snap, air, vocal cords
TA = [warp(t) for t in T]
CH_HICS = [h for h in HICS if not (SLO_A - 0.3 < h < SLO_B + 0.1)] + [HIT_ACT]


def snap_at(ta):
    return min(1.0, sum(spike(ta, h, 0.035, 0.26) for h in CH_HICS if h <= HIC_END + 1e-6 or h == HIT_ACT))


SNAP = [snap_at(TA[i]) for i in range(len(T))]
bake_vec(DIA, "scale", [(1.0, 1.0, 1.0 - 0.72 * v) for v in SNAP])
bake(DIA, "location", [DIA_Z0 - 0.06 * v for v in SNAP], index=2)
bake(dia_m.node_tree, BSDF + '["Emission Strength"].default_value', [0.15 + 3.5 * v for v in SNAP])
for k_, lg in enumerate(LUNGS):
    p0 = lg.location.copy()
    bake_vec(lg, "scale", [(0.14 * (1 + 0.04 * math.sin(t * 2 * math.pi / 3.8)), 0.12, 0.23 * (1 + 0.04 * math.sin(t * 2 * math.pi / 3.8) + 0.14 * SNAP[i]))
                           for i, t in enumerate(T)])
    bake(lg, "location", [p0.z - 0.04 * SNAP[i] for i in range(len(T))], index=2)
bake(lung_m.node_tree, BSDF + '["Emission Strength"].default_value', [0.5 + 2.2 * SNAP[i] for i in range(len(T))])
AIRPATH = [VC + Vector((0, -0.01, 0.06)), CHESTP + Vector((0, -0.01, 0.34)), CHESTP + Vector((0, -0.01, 0.2)), CHESTP + Vector((0, -0.01, 0.12))]
for k_, o in enumerate(AIR):
    sx = -1 if k_ % 2 else 1
    ph = (k_ // 2) / (len(AIR) // 2)
    locs, scl = [], []
    for i, t in enumerate(T):
        ta = TA[i]
        best = 0.0
        pos = AIRPATH[0]
        for h in CH_HICS:
            u = (ta - (h - 0.20 + 0.12 * ph)) / 0.26
            if 0.0 <= u <= 1.0:
                best = math.sin(math.pi * u) ** 0.5
                if u < 0.45:
                    a_, b_, w = AIRPATH[0], AIRPATH[1], u / 0.45
                elif u < 0.7:
                    a_, b_, w = AIRPATH[1], AIRPATH[2], (u - 0.45) / 0.25
                else:
                    a_, b_, w = AIRPATH[2], CHESTP + Vector((sx * 0.14, -0.02, 0.06 + 0.05 * (k_ % 3))), (u - 0.7) / 0.3
                pos = a_.lerp(b_, w) + Vector((0.012 * math.sin(9 * ta + k_), 0, 0.0))
                break
        locs.append(pos)
        scl.append(best)
    bake_vec(o, "location", locs)
    bake_vec(o, "scale", [(0.008 * v,) * 3 for v in scl])
CLOSE = [min(1.0, sum(spike(TA[i], h + 0.025, 0.02, 0.10) for h in CH_HICS if h <= HIC_END + 1e-6 or h == HIT_ACT)) for i in range(len(T))]
for k_, c in enumerate(CORDS):
    sx = 1 if k_ else -1
    bake(c, "location", [VC.x + sx * (0.034 * (1 - CLOSE[i]) + 0.004) for i in range(len(T))], index=0)
bake(FLASH.data.materials[0].node_tree, BSDF + '["Emission Strength"].default_value', [25.0 * CLOSE[i] ** 3 for i in range(len(T))])
bake_vec(FLASH, "scale", [(0.02 + 0.8 * CLOSE[i] ** 2,) * 3 for i in range(len(T))])

# ---------------------------------------------------------------- the brain: the vessel bursts, the off switch dies
def along(pts, u):
    u = max(0.0, min(1.0, u)) * (len(pts) - 1)
    i0 = min(int(u), len(pts) - 2)
    return pts[i0].lerp(pts[i0 + 1], u - i0)


bake(blood_m.node_tree, BSDF + '["Emission Strength"].default_value',
     [1.0 + 0.6 * math.sin(2 * math.pi * 1.3 * t) * (t < BURST) + 4.0 * spike(t, BURST, 0.03, 0.5) for t in T])
bake_vec(CLOUD, "scale", [(0.001 + 0.045 * smooth((t - BURST) / 1.1),) * 3 if t >= BURST else (0.0,) * 3 for t in T])
bake(CLOUD.data.materials[0].node_tree, 'nodes["Emission"].inputs["Strength"].default_value',
     [0.0 if t < BURST else 5.0 * math.exp(-(t - BURST) / 0.9) + 0.6 for t in T])
for o, vel, sz in DROPS:
    locs, scl = [], []
    for t in T:
        u = max(0.0, t - BURST)
        locs.append(BURST_P + vel * (1 - math.exp(-u * 2.2)) / 2.2 * 2.2 + Vector((0, 0, -0.01 * u * u)))
        scl.append(sz * smooth(u / 0.05) * (1 - ramp(u, 1.0, 1.6)) if t >= BURST else 0.0)
    bake_vec(o, "location", locs)
    bake_vec(o, "scale", [(v,) * 3 for v in scl])


def sw_level(t):
    """Brightness of the amber off-switch: steady, then damaged flicker, then dead."""
    if t < DAM:
        return 1.0
    if t < DEAD:
        u = (t - DAM) / (DEAD - DAM)
        return max(0.0, (1 - u) * (0.55 + 0.45 * math.sin(2 * math.pi * (5 + 8 * u) * (t - DAM))))
    return 0.0


SWL = [sw_level(t) for t in T]
bake(sw_m.node_tree, BSDF + '["Emission Strength"].default_value', [0.3 + 6.0 * v * (0.9 + 0.1 * math.sin(2 * math.pi * 2.2 * t)) for v, t in zip(SWL, T)])
bake_vec(sw_m.node_tree, BSDF + '["Base Color"].default_value',
         [tuple(g + (a - g) * min(1.0, v * 1.5) for g, a in zip((0.28, 0.27, 0.27), (1.0, 0.62, 0.12))) + (1,) for v in SWL], n=4)
bake_vec(sw_m.node_tree, BSDF + '["Emission Color"].default_value',
         [tuple(g + (a - g) * min(1.0, v * 1.5) for g, a in zip((0.28, 0.27, 0.27), (1.0, 0.62, 0.12))) + (1,) for v in SWL], n=4)
bake_vec(SWITCH, "scale", [(1.0 + 0.10 * math.sin(2 * math.pi * 1.8 * t) * (t < DAM) - 0.15 * ramp(t, DAM, DEAD),
                            0.6, 1.0 + 0.10 * math.sin(2 * math.pi * 1.8 * t) * (t < DAM) - 0.15 * ramp(t, DAM, DEAD)) for t in T])
for k_, o in enumerate(SIGS):
    locs, scl = [], []
    for t in T:
        u = ((t * 0.9) + k_ / len(SIGS)) % 1.0
        on = 1.0 if (t >= B[4] - 0.2 and t < DAM - 0.05 and t > B[4] - 0.2) else 0.0
        locs.append(along(NERVE_PTS, u))
        scl.append(on * smooth(min(u, 1 - u) / 0.12))
    bake_vec(o, "location", locs)
    bake_vec(o, "scale", [(v, v, v) for v in scl])

# ---------------------------------------------------------------- the tally wall: one dot per hiccup
ta0, ta1 = F(TALLY_A) - 2, min(END, F(TALLY_B) + 4)
TF = list(range(ta0, ta1 + 1))
NDOTS = len(TDOTS)
for o, idx in TDOTS:
    tp = TALLY_A + 0.10 + (TALLY_B - TALLY_A - 0.55) * ((idx * 0.618) % 1.0) ** 0.8
    vals = []
    for f in TF:
        t = (f - 1) / FPS
        vals.append(smooth((t - tp) / 0.10) * (1 + 0.8 * spike(t, tp + 0.10, 0.001, 0.12)))
    A.bake_vec(o, "scale", [(v, v, v) for v in vals], TF)

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


for name, coll in (("home", HOME), ("barn", BARN), ("chest", CHEST), ("brain", BRAIN), ("tally", TALLY)):
    key_vis([o for o in coll.all_objects if not o.hide_render], lambda i, name=name: SET_OF[i] == name)
key_vis([o for o in him.rig.children_recursive if o.type in ("MESH", "CURVES", "CURVE")], lambda i: SET_OF[i] in ("home", "barn"))

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
WCOL = {"home": ((0.66, 0.74, 0.80), 0.30), "barn": ((0.20, 0.13, 0.07), 0.45), "chest": ((0.008, 0.012, 0.03), 1.0),
        "brain": ((0.012, 0.010, 0.030), 1.0), "tally": ((0.004, 0.004, 0.012), 1.0)}
cols = [WCOL[s] for s in SET_OF]
bake_vec(wnt, 'nodes["Background"].inputs[0].default_value', [(*c_, 1) for c_, _ in cols], n=4, interp="CONSTANT")
bake(wnt, 'nodes["Background"].inputs[1].default_value', [s_ for _, s_ in cols], interp="CONSTANT")
CUTS = [s[0] for k, s in enumerate(SHOTS) if k and SHOTS[k - 1][2] != s[2]]
bake(scene, "view_settings.exposure", [-0.2 + 0.8 * sum(spike(t, c, 0.005, 0.05) for c in CUTS) + 0.5 * spike(t, HIT, 0.02, 0.12)
                                       + 0.4 * spike(t, BURST, 0.02, 0.10) + 0.5 * spike(t, IMP, 0.01, 0.08) for t in T])


def _light(kind, name, coll, loc, target, energy, size, color):
    d = bpy.data.lights.new(name, kind)
    d.energy, d.color = energy, color
    if kind == "AREA":
        d.size = size
    elif kind == "SPOT":
        d.spot_size, d.spot_blend, d.shadow_soft_size = math.radians(55), 0.5, size
    else:
        d.shadow_soft_size = size
    o = bpy.data.objects.new(name, d)
    coll.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


HEAD_H = P_HOME + Vector((0, 0, 1.6))
HEAD_B = P_BARN + Vector((0.3, 0, 1.2))
LIGHTS = {
    "home": [_light("AREA", "HomeKey", HOME, HEAD_H + Vector((1.4, -1.5, 1.2)), HEAD_H, 320, 1.5, (1.0, 0.93, 0.80)),
             _light("AREA", "HomeFill", HOME, HEAD_H + Vector((-1.8, -1.5, 0.6)), HEAD_H, 120, 2.0, (0.85, 0.90, 1.0)),
             _light("AREA", "HomeRim", HOME, HEAD_H + Vector((-0.6, 1.4, 1.0)), HEAD_H, 190, 0.8, (1.0, 0.92, 0.80)),
             _light("AREA", "HomeWindow", HOME, HOMEP + Vector((1.9, 3.4, 1.6)), HEAD_H, 260, 1.3, (1.0, 0.92, 0.75))],
    "barn": [_light("POINT", "LanternLight", BARN, BARNP + Vector((0.2, 1.3, 2.05)), HEAD_B, 420, 0.1, (1.0, 0.62, 0.28)),
             _light("AREA", "BarnKey", BARN, HEAD_B + Vector((1.3, -2.0, 0.8)), HEAD_B, 380, 1.5, (1.0, 0.80, 0.55)),
             _light("AREA", "BarnFill", BARN, HEAD_B + Vector((-2.0, -1.8, 0.2)), HEAD_B, 130, 2.0, (0.65, 0.75, 1.0)),
             _light("AREA", "BarnWindow", BARN, BARNP + Vector((-2.2, 3.3, 1.8)), HEAD_B, 300, 1.0, (1.0, 0.85, 0.55)),
             _light("AREA", "BarnRim", BARN, HEAD_B + Vector((-0.5, 1.6, 0.8)), HEAD_B, 160, 0.8, (1.0, 0.75, 0.45))],
    "chest": [_light("AREA", "CKey", CHEST, CHC + Vector((0.5, -0.8, 0.6)), CHC, 26, 0.8, (1.0, 0.88, 0.80)),
              _light("AREA", "CFill", CHEST, CHC + Vector((-0.8, -0.7, 0.1)), CHC, 10, 1.0, (0.55, 0.70, 1.0)),
              _light("AREA", "CRim", CHEST, CHC + Vector((0.0, 0.7, 0.6)), CHC, 14, 0.6, (1.0, 0.6, 0.6))],
    "brain": [_light("AREA", "BKey", BRAIN, BRC + Vector((0.5, -0.7, 0.3)), BRC, 22, 0.6, (1.0, 0.88, 0.80)),
              _light("AREA", "BFill", BRAIN, BRC + Vector((-0.7, -0.6, 0.1)), BRC, 8, 1.0, (0.55, 0.70, 1.0)),
              _light("AREA", "BRim", BRAIN, BRC + Vector((0.0, 0.6, 0.5)), BRC, 12, 0.6, (0.9, 0.6, 1.0))],
    "tally": [_light("AREA", "TKey", TALLY, TC + Vector((0.3, -1.2, 0.4)), TC, 6, 1.0, (1.0, 0.85, 0.7))],
}
BASE = {l.name: l.data.energy for ls in LIGHTS.values() for l in ls}
for set_name, ls in LIGHTS.items():
    for l in ls:
        vals = []
        for i, t in enumerate(T):
            e = BASE[l.name] * (SET_OF[i] == set_name)
            if l.name == "CKey":
                e *= 1 + 1.5 * SNAP[i]
            elif l.name == "BKey":
                e *= 1 + 2.0 * spike(t, BURST, 0.03, 0.4) + 0.6 * SWL[i]
            elif l.name == "LanternLight":
                e *= 0.92 + 0.08 * math.sin(11 * t) * math.sin(4.3 * t)
            vals.append(e)
        bake(l.data, "energy", vals)

# ---------------------------------------------------------------- cameras (v3: moving splines, DOF from subject size)
cams = S.Cameras(scene, T, F, CAST)


def span(name):
    i = next(k for k, s in enumerate(SHOTS) if s[1] == name)
    return SHOTS[i][0], (SHOTS[i + 1][0] if i + 1 < len(SHOTS) else DUR)


def mid(name):
    a, b = span(name)
    return (a + b) / 2


def hic_kicks(a, b, amp=0.0045):
    return [(h, amp, 0.16) for h in HICS if a <= h <= b]


W = cams.world_at
# beat 1 hook (frame 1 = thumbnail): face, mid-hiccup
a, b = span("HookFace")
F0 = W(face_pt, mid("HookFace"))
cams.cam("HookFace", a, b, keys=[(a, F0 + Vector((0.34, -0.92, -0.03))), (b, F0 + Vector((0.22, -0.68, -0.02)))],
         lens=50, aim=face_pt, focus=eyes_mid, depth=0.18, shift_y=-0.06, shake=0.0012, ease="cine", kicks=hic_kicks(a, b))
a, b = span("HookWide")
C1 = W(chest_pt, mid("HookWide"))
cams.cam("HookWide", a, b, keys=[(a, C1 + Vector((1.5, -3.2, 0.25))), (b, C1 + Vector((1.1, -2.6, 0.15)))], lens=28, aim=C1 + Vector((0, 0, 0.1)),
         focus=chest_pt, depth=1.2, shake=0.001, kicks=hic_kicks(a, b))
# beat 2: the barn and the hog
a, b = span("BarnWide")
BM = BARNP + Vector((0.2, 0.9, 0.85))
cams.cam("BarnWide", a, b, keys=[(a, BM + Vector((2.4, -4.6, 0.25))), (b, BM + Vector((1.5, -3.7, 0.15)))], lens=28, aim=BM, depth=2.5, shake=0.001)
a, b = span("PigCU")
PM = PIG + Vector((0, -0.7, 0.5))
cams.cam("PigCU", a, b, keys=[(a, PM + Vector((0.75, -1.3, 0.10))), (b, PM + Vector((0.42, -0.85, 0.05)))], lens=50, aim=PM, depth=0.4, shake=0.001)
# beat 3: he strains at the hog, slips, crashes
a, b = span("LiftMed")
LM = BARNP + Vector((-0.1, 0.9, 0.95))
cams.cam("LiftMed", a, b, keys=[(a, LM + Vector((0.7, -2.4, 0.0))), (b, LM + Vector((0.3, -1.9, -0.05)))], lens=45, aim=LM, depth=0.9, shake=0.0012)
a, b = span("FallLow")
FM = BARNP + Vector((-1.2, 0.9, 0.35))
cams.cam("FallLow", a, b, keys=[(a, FM + Vector((1.3, -1.9, 0.0))), (b, FM + Vector((0.5, -1.35, -0.02)))], lens=24, aim=FM, depth=1.6, shake=0.0015,
         kicks=[(IMP, 0.022, 0.25)] + hic_kicks(a, b, 0.006))
# beat 4: the brain, the vessel
a, b = span("BrainOrbit")
cams.cam("BrainOrbit", a, b, path=S.orbit(BRAINP + Vector((0, 0.03, -0.05)), 0.62, -22, 22, 0.05, 0.0), lens=40, aim=BRAINP + Vector((0, 0.03, -0.06)),
         depth=0.3, shake=0.0004)
a, b = span("BurstMacro")
cams.cam("BurstMacro", a, b, keys=[(a, BURST_P + Vector((0.16, -0.30, 0.04))), (b, BURST_P + Vector((0.10, -0.20, 0.02)))], lens=70, aim=BURST_P,
         depth=0.05, shake=0.0003, kicks=[(BURST, 0.006, 0.25)])
# beat 5: the off switch dies
a, b = span("OffSwitch")
cams.cam("OffSwitch", a, b, keys=[(a, SWITCH_P + Vector((-0.12, -0.26, 0.03))), (b, SWITCH_P + Vector((-0.07, -0.18, 0.0)))], lens=75,
         aim=SWITCH_P + Vector((0, 0, -0.02)), depth=0.05, shake=0.0003)
a, b = span("SignalLost")
cams.cam("SignalLost", a, b, path=S.orbit(SWITCH_P + Vector((0, 0, -0.05)), 0.22, 20, -8, 0.0, 0.02), lens=60, aim=SWITCH_P + Vector((0, 0, -0.04)),
         depth=0.1, shake=0.0003)
# beat 6 MONEY MOMENT: the snap, slow motion
a, b = span("HicSlomo")
cams.cam("HicSlomo", a, b, keys=[(a, CHC + Vector((0.20, -0.95, 0.10))), (b, CHC + Vector((0.06, -0.62, 0.0)))], lens=35, aim=CHESTP + Vector((0, 0, 0.12)),
         depth=0.5, shake=0.0003, kicks=[(HIT, 0.010, 0.3)], ease="cine")
a, b = span("CordsCU")
cams.cam("CordsCU", a, b, keys=[(a, VC + Vector((0.07, -0.20, 0.02))), (b, VC + Vector((0.03, -0.13, 0.01)))], lens=85, aim=VC, depth=0.04, shake=0.0002,
         kicks=[(h, 0.003, 0.12) for h in HICS if a <= h <= b])
# beat 7: the tally
a, b = span("TallyFly")
cams.cam("TallyFly", a, b, keys=[(a, TC + Vector((0.5, -1.35, -0.55))), (b, TC + Vector((-0.1, -0.55, 0.45)))], lens=32, aim=TC + Vector((0, 0, 0.0)),
         depth=0.4, shake=0.0004, ease="cine")
a, b = span("WearyFace")
F5 = W(face_pt, mid("WearyFace"))
cams.cam("WearyFace", a, b, keys=[(a, F5 + Vector((-0.32, -0.88, 0.0))), (b, F5 + Vector((-0.20, -0.62, 0.0)))], lens=55, aim=face_pt, focus=eyes_mid,
         depth=0.18, shift_y=-0.05, shake=0.001, kicks=hic_kicks(a, b))
# beat 8: the family
a, b = span("FamilyWide")
C6 = W(chest_pt, mid("FamilyWide"))
cams.cam("FamilyWide", a, b, path=S.orbit(C6, 2.1, -30, 6, 0.2, 0.05, 1.7), lens=28, aim=C6 + Vector((0, 0.6, 0.3)), focus=chest_pt, depth=1.4,
         shake=0.0008, kicks=hic_kicks(a, b))
a, b = span("FramesTruck")
FT = HOMEP + Vector((0, 3.45, 1.6))
cams.cam("FramesTruck", a, b, keys=[(a, FT + Vector((-1.9, -2.3, 0.0))), (b, FT + Vector((0.2, -2.1, 0.05)))], lens=50, aim=FT + Vector((-1.2, 0, 0)),
         depth=1.0, shake=0.0006)
# beat 9: the last hiccup, then calm
a, b = span("LastHicFace")
F7 = W(face_pt, mid("LastHicFace"))
cams.cam("LastHicFace", a, b, keys=[(a, F7 + Vector((0.30, -0.86, -0.02))), (b, F7 + Vector((0.16, -0.58, -0.02)))], lens=55, aim=face_pt,
         focus=eyes_mid, depth=0.16, shift_y=-0.05, shake=0.001, kicks=hic_kicks(a, b, 0.006))
a, b = span("ChestCalm")
cams.cam("ChestCalm", a, b, keys=[(a, CHC + Vector((-0.30, -0.95, -0.02))), (b, CHC + Vector((-0.12, -0.70, 0.02)))], lens=35,
         aim=CHESTP + Vector((0, 0, 0.12)), depth=0.5, shake=0.0003)
# beat 10
a, b = span("HomeOrbit")
C8 = W(chest_pt, mid("HomeOrbit"))
cams.cam("HomeOrbit", a, b, path=S.orbit(C8, 1.9, -30, 10, 0.15, 0.05), lens=35, aim=C8 + Vector((0, 0, 0.1)), focus=chest_pt, depth=0.9, shake=0.0008)
a, b = span("Closer")
F9 = W(face_pt, mid("Closer"))
cams.cam("Closer", a, b, keys=[(a, F9 + Vector((0.12, -1.05, 0.02))), (b, F9 + Vector((0.05, -0.52, 0.0)))], lens=55, aim=face_pt,
         focus=eyes_mid, depth=0.12, shift_y=-0.06, shake=0.0008, ease="cine")

cams.markers(SHOTS)
S.check_shots(SHOTS, DUR)


def gaze_target(t):
    s = shot_at(t)
    if s[2] == "barn" and t < IMP:
        return Vector(HOG_BODY.location) + Vector((0, -0.2, 0.2))
    return None


him.bake_gaze(FRAMES, T, gaze_target, CAST, seed=23)

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
