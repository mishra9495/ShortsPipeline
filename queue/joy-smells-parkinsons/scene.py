"""joy-smells-parkinsons: "She could smell Parkinson's disease before doctors could" (Joy Milne, Perth, Scotland).
Sources: University of Manchester news (2022-09-07) "'Sniffing out' Parkinson's: Three-minute skin swab breakthrough";
ACS Central Science 2019 (sebum biomarkers); Parkinson's UK; ZME Science (T-shirt test, 8-month follow-up).

Run (daily_render.ps1): blender -b --python scene.py -- <ROOT>/blend/<slug>.blend vo=<wav> beats=<json> fps=30
Optional: stills=1,200 pct=100 samples=128 device=gpu|cpu root=<ROOT>

v3 toolkit (kit.py models, actor.py acting on mixamorig bones, shot.py moving cameras). No captions, no on-screen text.
Cast: her = blend/char_heroine.blend. One actor. Sets: HOME, LAB (T-shirt counter + swab machine), SCENT (skin + sebum beads),
DOTS (flip cards, then 20 dots). Set changes are HARD CUTS (whoosh + exposure spike). SYNC with mix.py.
"""

import json
import math
import os
import random
import subprocess
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

# ---------------------------------------------------------------- character (female lead is mandatory)
HEROINE = os.path.join(ROOT, "blend", "char_heroine.blend")
if not os.path.exists(HEROINE) and bpy.app.binary_path:
    print("Building female lead:", HEROINE)
    r = subprocess.run([bpy.app.binary_path, "-b", "--python", os.path.join(SCRIPTS, "build_character.py"), "--", HEROINE,
                        os.path.join(SCRIPTS, "preset_heroine.json")], capture_output=True, text=True, timeout=1800)
    print("HEROINE build exit", r.returncode, *(r.stdout + r.stderr).strip().splitlines()[-8:], sep="\n  ")
if not os.path.exists(HEROINE):
    raise SystemExit("Error: female lead blend/char_heroine.blend could not be built; refusing to substitute a man")
print("CHAR", HEROINE)
bpy.ops.wm.open_mainfile(filepath=HEROINE)

import actor as A  # noqa: E402
import kit as K  # noqa: E402
import shot as S  # noqa: E402

scene = bpy.context.scene
K.init(scene, seed=71)
random.seed(71)
CAST = K.coll("Cast")
him = A.Actor.from_scene("Her")
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
SLO_A, SLO_B = B[4], at(4, 0.62)                  # slow-mo: the one healthy shirt blooms amber (money moment)
ACT_A, ACT_B = SLO_A, SLO_A + (SLO_B - SLO_A) * 0.4
HIT_F = 0.45
HIT = SLO_A + HIT_F * (SLO_B - SLO_A)
HIT_ACT = ACT_A + HIT_F * (ACT_B - ACT_A)
FLIP0 = B[5] + 0.15                               # cards start flipping
WISP_ON = (0.0, at(1, 0.30))                      # wisps around her at the hook
WISP2 = B[9]                                      # wisps return in the closer
print("TIMELINE", [round(b, 2) for b in B], "END", END, "HIT", round(HIT, 2))


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


# ---------------------------------------------------------------- measure her (rest pose, rig-local)
rig = him.rig
REST_HIPS = him.hips0.copy()
X0 = him.x0
OFF = Vector((X0, REST_HIPS.y, 0))
V = Vector

# ---------------------------------------------------------------- sets
HOMEP, LABP, DOTSP, SCENTP = V((0, 0, 0)), V((40, 0, 0)), V((80, 0, 0)), V((120, 0, 0))
HOME, LAB, DOTS, SCENT, WISP = K.coll("SetHome"), K.coll("SetLab"), K.coll("SetDots"), K.coll("SetScent"), K.coll("Wisps")
P_HOME = HOMEP + V((-0.9, 1.2, 0))
P_LAB = LABP + V((-0.45, 2.45, 0))

K.room(HOME, origin=HOMEP + V((0, 1.0, 0)), size=(6.0, 5.2, 2.8), floor_mat=K.floorboards(), wall_color=(0.88, 0.80, 0.68),
       name="HomeRoom", openings=[(1.9, 1.5, 1.44, 1.44)])
K.window(HOME, HOMEP + V((1.9, 3.57, 1.5)), size=(1.3, 1.3), curtains=True, sky=(1.0, 0.93, 0.78), sky_strength=4.0)
for k in range(5):
    K.picture_frame(HOME, HOMEP + V((-2.15 + 0.44 * k, 3.55, 1.62 + 0.05 * (k % 2))), (0.30, 0.38), name=f"Pic{k}", seed=21 + k)
K.rug(HOME, P_HOME + V((0.3, 0.2, 0.0)), size=(2.8, 2.0), name="HomeRug")
K.floor_lamp(HOME, HOMEP + V((-2.55, 2.9, 0)))
K.potted_plant(HOME, HOMEP + V((2.55, 2.7, 0)), h=1.3, seed=4)
K.bookshelf(HOME, HOMEP + V((0.55, 3.28, 0)), w=0.9, h=1.7, seed=8)
K.mug(HOME, HOMEP + V((1.2, 0.2, 0.0)), color=(0.9, 0.9, 0.92))

# LAB: counter with twelve T-shirts (two rows of six), a swab machine on the right
LAB_FLOOR = K.paint("LabFloor", (0.52, 0.58, 0.58), 0.25)
K.room(LAB, origin=LABP + V((0, 1.0, 0)), size=(7.0, 5.2, 2.8), floor_mat=LAB_FLOOR, wall_color=(0.72, 0.80, 0.78), name="LabRoom")
COUNTER = K.rbox("Counter", LAB, (3.6, 0.80, 0.90), LABP + V((0.2, 1.5, 0.45)), K.paint("CounterTop", (0.22, 0.25, 0.30), 0.35), bevel=0.01)
CT = 0.90                                                     # counter top height
SHIRT_COLS = [(0.35, 0.45, 0.70), (0.25, 0.55, 0.60), (0.70, 0.55, 0.25), (0.35, 0.55, 0.35), (0.60, 0.30, 0.35), (0.45, 0.40, 0.65)]
AMBER_I = 8                                                   # which shirt is the healthy person who later got Parkinson's
SHIRTS, SHIRT_MATS = [], []
for n in range(12):
    r_, c_ = divmod(n, 6)
    pos = LABP + V((-1.4 + 0.42 * c_, 1.34 + 0.30 * r_, CT + 0.012))
    col = SHIRT_COLS[(n * 5) % 6]
    m = glowy(f"Shirt{n}", col, rough=0.9, sss=0.0, emit=0.0)
    SHIRT_MATS.append(m)
    body = K.cushion(f"ShirtB{n}", LAB, (0.24, 0.30, 0.03), pos, m, puff=0.45, seed=n)
    sl = K.cushion(f"ShirtL{n}", LAB, (0.10, 0.12, 0.028), pos + V((-0.15, 0.0, 0.0)), m, puff=0.45, rot=(0, 0, math.radians(30)), seed=n + 20)
    sr = K.cushion(f"ShirtR{n}", LAB, (0.10, 0.12, 0.028), pos + V((0.15, 0.0, 0.0)), m, puff=0.45, rot=(0, 0, math.radians(-30)), seed=n + 40)
    SHIRTS.append((body, sl, sr, pos))
SHIRT_C = SHIRTS[AMBER_I][3]
MACH_P = LABP + V((1.55, 1.5, CT))
K.rbox("MachBody", LAB, (0.60, 0.46, 0.34), MACH_P + V((0, 0, 0.17)), K.plastic("MachM", (0.85, 0.87, 0.90), 0.3, coat=0.3), bevel=0.02)
K.rbox("MachScreenFrame", LAB, (0.46, 0.02, 0.24), MACH_P + V((0, -0.235, 0.19)), K.plastic("MachFrame", (0.03, 0.03, 0.04), 0.2), bevel=0.005)
BARS = []
bar_m = glowy("MachBar", (0.25, 0.95, 0.55), rough=0.3, sss=0.0, emit=3.0)
for k in range(8):
    BARS.append(K.rbox(f"Bar{k}", LAB, (0.034, 0.012, 0.10), MACH_P + V((-0.17 + 0.048 * k, -0.252, 0.12)), bar_m, bevel=0.003))
K.rbox("SwabHolder", LAB, (0.05, 0.05, 0.10), MACH_P + V((0.42, -0.1, 0.05)), K.plastic("HolderM", (0.2, 0.22, 0.26), 0.4), bevel=0.01)
K.surgical_lamp(LAB, LABP + V((0.0, 1.5, 1.9)), name="LabLamp")
K.lab_bench(LAB, LABP + V((-2.6, 3.1, 0)), name="LabBench")
K.potted_plant(LAB, LABP + V((3.0, 2.7, 0)), h=1.1, seed=2)

# SCENT: a dark void, a skin patch with rising sebum beads, and a swab
skin_m = glowy("SkinPatch", (0.80, 0.55, 0.45), rough=0.45, sss=0.5, emit=0.0)
SK = K.cushion("SkinPatch", SCENT, (1.4, 0.9, 0.08), SCENTP + V((0, 2.0, 0.04)), skin_m, puff=0.25, seed=3)
K.plane("ScentFloor", SCENT, (20, 20), SCENTP + V((0, 3, 0)), K.plastic("ScentFloorM", (0.01, 0.012, 0.02), 0.08, coat=0.5))
bead_m = glowy("Sebum", (1.0, 0.70, 0.22), rough=0.2, sss=0.0, emit=3.5)
SEB = []
random.seed(5)
for k in range(46):
    o = K.sphere(f"Seb{k}", SCENT, random.uniform(0.010, 0.022), SCENTP + V((0, 2.0, 0.1)), bead_m, subdiv=2)
    SEB.append((o, random.uniform(-0.62, 0.62), random.uniform(-0.38, 0.38), random.random(), random.uniform(0.7, 1.3)))
swab_m = K.plastic("SwabStick", (0.88, 0.88, 0.90), 0.5)
swab = K.cyl("SwabStick", SCENT, 0.006, 0.22, SCENTP + V((0, 2.0, 0.2)), swab_m, verts=12)
swab_tip = K.sphere("SwabTip", SCENT, 0.016, V((0, 0, -0.11)), K.fabric("SwabCotton", (0.95, 0.95, 0.92)), scale=(1, 1, 1.4), subdiv=3)
swab_tip.parent = swab

# DOTS: eight flip cards, then 20 dots (19 green, one red = 95 percent)
dark_m = K.plastic("DotsFloorM", (0.01, 0.012, 0.02), 0.08, coat=0.5)
K.plane("DotsFloor", DOTS, (30, 30), DOTSP + V((0, 3, 0)), dark_m)
CARDS = []
for k in range(8):
    last = k == 7
    cm = glowy(f"Card{k}", (1.0, 0.55, 0.1) if last else (0.85, 0.9, 0.95), rough=0.35, sss=0.0, emit=0.3)
    piv = bpy.data.objects.new(f"CardPiv{k}", None)
    DOTS.objects.link(piv)
    piv.location = DOTSP + V((-0.9 + 0.257 * k, 1.6, 0.18))
    c_ = K.rbox(f"Card{k}", DOTS, (0.20, 0.012, 0.30), V((0, 0, 0)), cm, bevel=0.004)
    c_.parent = piv
    CARDS.append((piv, cm, last))
dot_g = glowy("DotGreen", (0.15, 0.95, 0.45), rough=0.25, sss=0.0, emit=2.5)
dot_r = glowy("DotRed", (1.0, 0.18, 0.12), rough=0.25, sss=0.0, emit=0.0)
DOTSL = []
for n in range(20):
    r_, c_ = divmod(n, 5)
    p = DOTSP + V((-0.24 + 0.12 * c_, 4.6, 0.72 + 0.12 * (3 - r_) - 0.18))
    red = n == 13
    DOTSL.append((K.sphere(f"Dot{n}", DOTS, 0.045, p, dot_r if red else dot_g, subdiv=3), red, p))
RED_P = next(p for _, red, p in DOTSL if red)

# ---------------------------------------------------------------- shots (start, camera, set)
SHOTS = [
    (0.0, "NoseThumb", "home"),
    (at(0, 0.45), "HomeWide", "home"),
    (B[1], "FaceWin", "home"),
    (at(1, 0.50), "HomeOrbit", "home"),
    (B[2], "ScentMacro", "scent"),
    (at(2, 0.50), "ScentPull", "scent"),
    (B[3], "ShirtRow", "lab"),
    (at(3, 0.50), "SniffMed", "lab"),
    (SLO_A, "AmberSlomo", "lab"),
    (SLO_B, "SniffWide", "lab"),
    (B[5], "CardsFlip", "dots"),
    (at(5, 0.55), "CardAmber", "dots"),
    (B[6], "SebumMacro", "scent"),
    (at(6, 0.50), "SebumTop", "scent"),
    (B[7], "SwabCU", "scent"),
    (at(7, 0.50), "MachineCU", "lab"),
    (B[8], "DotsPush", "dots"),
    (at(8, 0.55), "OneRed", "dots"),
    (B[9], "HomeClose", "home"),
    (at(9, 0.45), "Closer", "home"),
]


def shot_at(t):
    return max((s for s in SHOTS if s[0] <= t + 1e-6), key=lambda s: s[0])


SH = [shot_at(t) for t in T]
SET_OF = [s[2] for s in SH]
SHOT_END = {s[1]: (SHOTS[k + 1][0] if k + 1 < len(SHOTS) else DUR) for k, s in enumerate(SHOTS)}


def him_root(s):
    if s[2] == "home":
        return P_HOME - OFF, (0, 0, 0)
    if s[2] == "lab":
        return P_LAB - OFF, (0, 0, 0)
    return V((0, 0, -300)), (0, 0, 0)


# ---------------------------------------------------------------- performance
BLINKS = [1.0 + 2.9 * k for k in range(60) if 1.0 + 2.9 * k < DUR]
SNIFF = (B[3] + 0.5, BE[4] + 0.3)                  # she leans over the shirts


def channels(t):
    ch = {}
    ch["smile"] = max(0.5 * ramp(t, B[1] + 0.1, B[1] + 0.8) * (1 - ramp(t, B[3], B[3] + 0.3)), ramp(t, B[9] - 0.1, B[9] + 0.8))
    ch["sniff"] = env(t, SNIFF[0], SNIFF[0] + 0.5, SNIFF[1] - 0.4, SNIFF[1])
    ch["amaze"] = env(t, SLO_A + 0.2, SLO_A + 0.5, BE[4] + 0.2, BE[4] + 0.5)
    ch["blink"] = max((env(t, b_ - 0.03, b_, b_ + 0.05, b_ + 0.12) for b_ in BLINKS), default=0.0)
    return ch


legs_stand = him.standing_legs()
SIDE_L = REST_HIPS + V((0.22, 0.02, -0.12))
SIDE_R = REST_HIPS + V((-0.22, 0.02, -0.12))
face_pt = him.anchor("Face", "Head", V((him.x0, him.nose.y + 0.05, him.nose.z - 0.01)), CAST)
eyes_mid = him.anchor("Eyes", "Head", (him.eye_l + him.eye_r) / 2, CAST)

for i, t in enumerate(T):
    s = SH[i]
    ch = channels(t)
    br = math.sin(t * 2 * math.pi / 3.6)
    spec = {
        "Hips": [(A.Z, 0.6 * wobble(t, 1))],
        "Spine": [(A.X, 0.6 * br + 13 * ch["sniff"]), (A.Z, 0.8 * wobble(t, 2))],
        "Spine1": [(A.X, 0.7 * br + 6 * ch["sniff"])],
        "Spine2": [(A.X, 1.5 + 0.6 * br + 3 * ch["sniff"])],
        "Neck": [(A.X, 5 * ch["sniff"]), (A.Z, 1.2 * wobble(t, 4))],
        "Head": [(A.X, 1.0 * wobble(t, 7, 0.6) + 8 * ch["sniff"] - 3 * ch["amaze"]), (A.Z, 1.6 * wobble(t, 5, 0.5)),
                 (A.Y, 1.0 * wobble(t, 6) + 2 * ch["smile"] * wobble(t, 8, 0.7))],
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
        rots[bone] = A.Quaternion((1, 0, 0), math.radians(curl))
    sh = {}
    for side in ("Left", "Right"):
        sh[f"eyeBlink{side}"] = min(1.0, ch["blink"] + 0.35 * ch["sniff"] + 0.12 * ch["smile"])
        sh[f"eyeWide{side}"] = 0.5 * ch["amaze"]
        sh[f"browDown{side}"] = 0.0
        sh[f"eyeSquint{side}"] = 0.3 * ch["smile"]
        sh[f"mouthFrown{side}"] = 0.0
        sh[f"mouthSmile{side}"] = 0.9 * ch["smile"] + 0.2 * ch["amaze"]
        sh[f"cheekSquint{side}"] = 0.4 * ch["smile"]
        sh[f"mouthPress{side}"] = 0.0
    sh["browInnerUp"] = 0.4 * ch["amaze"] + 0.2 * ch["sniff"]
    sh["jawOpen"] = 0.04 * ch["smile"] + 0.10 * ch["amaze"]
    ikl = SIDE_L + V((0, 0, 0.004 * br))
    ikr = SIDE_R + V((0, 0, 0.004 * br))
    him.record(rots, sh, ikl, ikr, aim=(0.0, 0.0), follow={}, root=him_root(s))
him.bake(FRAMES)
for fc in A.fcurves_of(him.rig):
    if fc.data_path in ("location", "rotation_euler"):
        fc.keyframe_points.foreach_set("interpolation", [0] * len(fc.keyframe_points))   # teleports are cuts

TA = [warp(t) for t in T]


def Wh(p):
    return P_HOME - OFF + V(p)


FC = Wh(V((X0, him.nose.y, him.nose.z)))
NOSE_H = Wh(V((X0, him.nose.y - 0.01, him.nose.z - 0.01)))
TC = Wh(V((X0, REST_HIPS.y, REST_HIPS.z + 0.35)))
FCL = P_LAB - OFF + V((X0, him.nose.y, him.nose.z))               # her face in the lab
LF = P_LAB - OFF

# ---------------------------------------------------------------- wisps of scent curling to her nose (home set)
wisp_m = glowy("Wisp", (1.0, 0.72, 0.30), rough=0.3, sss=0.0, emit=2.5)
WSRC = P_HOME + V((1.25, -0.25, 1.15))
WP = []
for w in range(3):
    pts = []
    for j in range(10):
        u = j / 9
        base = WSRC.lerp(NOSE_H + V((0, -0.02, 0)), u)
        amp = 0.16 * math.sin(math.pi * u) * (1 - 0.15 * w)
        pts.append(base + V((amp * math.sin(5 * u + w * 2.1), 0.0, amp * math.cos(4 * u + w * 1.3) + 0.06 * math.sin(math.pi * u))))
    WP.append(pts)
    K.tube(f"Wisp{w}", WISP, pts, 0.0048, wisp_m, res=5)
WBEADS = []
for w in range(3):
    for k in range(6):
        WBEADS.append((K.sphere(f"WBead{w}_{k}", WISP, 0.013, NOSE_H, wisp_m, subdiv=2), w, k / 6.0))


def wisp_strength(t):
    a = env(t, WISP_ON[0], WISP_ON[0] + 0.01, WISP_ON[1] - 0.2, WISP_ON[1])
    b = env(t, WISP2, WISP2 + 0.5, DUR, DUR + 1)
    return max(a, 0.9 * b)


WS = [wisp_strength(t) for t in T]
bake(wisp_m.node_tree, BSDF + '["Emission Strength"].default_value', [0.1 + 2.8 * w for w in WS])


def on_path(pts, u):
    x = u * (len(pts) - 1)
    j = min(len(pts) - 2, int(x))
    return pts[j].lerp(pts[j + 1], x - j)


for o, w, ph in WBEADS:
    bake_vec(o, "location", [on_path(WP[w], (ph + 0.35 * t) % 1.0) for t in T])
    bake_vec(o, "scale", [(max(0.05, min(1.0, 2 * WS[i])),) * 3 for i in range(len(T))])

# ---------------------------------------------------------------- shirt flag, cards, dots, bars, swab, sebum
SH_GLOW = [ramp(t, SLO_A + (SLO_B - SLO_A) * 0.12, SLO_A + (SLO_B - SLO_A) * 0.55) for t in T]
AMB = (1.0, 0.55, 0.08)
m = SHIRT_MATS[AMBER_I]
base = SHIRT_COLS[(AMBER_I * 5) % 6]
cols = [tuple(base[c] + (AMB[c] - base[c]) * min(1.0, g) for c in range(3)) + (1,) for g in SH_GLOW]
bake_vec(m.node_tree, BSDF + '["Base Color"].default_value', cols, n=4)
bake_vec(m.node_tree, BSDF + '["Emission Color"].default_value', cols, n=4)
bake(m.node_tree, BSDF + '["Emission Strength"].default_value', [4.0 * g * (0.85 + 0.15 * math.sin(2 * math.pi * 1.5 * t)) for g, t in zip(SH_GLOW, T)])
# the amber shirt lifts a little off the counter as it blooms
for part in SHIRTS[AMBER_I][:3]:
    p0 = part.location.copy()
    bake_vec(part, "location", [p0 + V((0, 0, 0.05 * min(1.0, g))) for g in SH_GLOW])

for k, (piv, cm, last) in enumerate(CARDS):
    t0 = FLIP0 + 0.17 * k
    rz = [math.pi * smooth(ramp(t, t0, t0 + 0.24)) for t in T]
    bake_vec(piv, "rotation_euler", [(0, 0, a_) for a_ in rz])
    if last:
        gl = [ramp(t, t0 + 0.2, t0 + 0.6) for t in T]
        bake(cm.node_tree, BSDF + '["Emission Strength"].default_value', [0.3 + 5.0 * g for g in gl])
        bake_vec(cm.node_tree, BSDF + '["Emission Color"].default_value', [(1.0, 0.55, 0.08, 1)] * len(T), n=4)

DOTS_T = B[8] + 0.2
for n, (o, red, p) in enumerate(DOTSL):
    t0 = DOTS_T + 0.045 * n
    bake_vec(o, "scale", [(0.001 + smooth(ramp(t, t0, t0 + 0.18)) * (1 + 0.18 * spike(t, t0 + 0.2, 0.02, 0.15)),) * 3 for t in T])
RED_T = at(8, 0.60)
bake(dot_r.node_tree, BSDF + '["Emission Strength"].default_value', [0.3 + 7.0 * ramp(t, RED_T, RED_T + 0.4) for t in T])
bake_vec(DOTSL[13][0], "scale", [(0.001 + smooth(ramp(t, DOTS_T + 0.6, DOTS_T + 0.8)) * (1 + 0.8 * ramp(t, RED_T, RED_T + 0.5)),) * 3 for t in T])

MACH_T = (B[7] + (BE[7] - B[7]) * 0.50, BE[7] + 0.4)
for k, b_ in enumerate(BARS):
    zs = []
    for t in T:
        u = ramp(t, MACH_T[0], MACH_T[0] + 0.9)
        h = 0.2 + 0.8 * abs(math.sin(7 * t + k * 1.7)) * (1 - u * (k != 4)) + 0.9 * u * (k == 4 or k == 5)
        zs.append(max(0.15, h))
    bake_vec(b_, "scale", [(1.0, 1.0, z_ * (1.0 if MACH_T[0] - 0.1 < t else 0.15)) for z_, t in zip(zs, T)])

# swab strokes across the skin
sw0, sw1 = B[7], at(7, 0.5)
SWP = SCENTP + V((0, 2.0, 0.2))
bake_vec(swab, "location", [SWP + V((0.45 * math.sin(2 * math.pi * 1.1 * (t - sw0)) * smooth(ramp(t, sw0, sw0 + 0.3)), 0.12 * math.sin(2 * math.pi * 2.2 * t), 0.0))
                            for t in T])
bake_vec(swab, "rotation_euler", [(math.radians(14), math.radians(22), 0) for _ in T])
for o, ax, ay, ph, spd in SEB:
    locs, scs = [], []
    for t in T:
        u = (ph + 0.22 * spd * t) % 1.0
        locs.append(SCENTP + V((ax + 0.06 * math.sin(3 * t * spd + ph * 9) * u, 2.0 + ay + 0.05 * math.cos(2.4 * t * spd + ph * 7) * u, 0.09 + 0.55 * u)))
        scs.append(math.sin(math.pi * u) ** 0.5 + 0.02)
    bake_vec(o, "location", locs)
    bake_vec(o, "scale", [(s_,) * 3 for s_ in scs])
bake(bead_m.node_tree, BSDF + '["Emission Strength"].default_value', [2.5 + 1.2 * math.sin(2 * math.pi * 0.7 * t) for t in T])

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


for name, coll in (("home", HOME), ("lab", LAB), ("dots", DOTS), ("scent", SCENT)):
    key_vis([o for o in coll.all_objects if not o.hide_render and o.type != "EMPTY"], lambda i, name=name: SET_OF[i] == name)
key_vis([o for o in rig.children_recursive if o.type in ("MESH", "CURVES", "CURVE")], lambda i: SET_OF[i] in ("home", "lab"))
key_vis([o for o in WISP.all_objects], lambda i: SET_OF[i] == "home" and WS[i] > 0.02)

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
WCOL = {"home": ((0.78, 0.84, 0.92), 0.35), "lab": ((0.30, 0.34, 0.36), 0.15), "scent": ((0.010, 0.006, 0.004), 1.0),
        "dots": ((0.004, 0.007, 0.016), 1.0)}
cols = [WCOL[s] for s in SET_OF]
bake_vec(wnt, 'nodes["Background"].inputs[0].default_value', [(*c_, 1) for c_, _ in cols], n=4, interp="CONSTANT")
bake(wnt, 'nodes["Background"].inputs[1].default_value', [s_ for _, s_ in cols], interp="CONSTANT")
SET_CUTS = [s[0] for k, s in enumerate(SHOTS) if k and SHOTS[k - 1][2] != s[2]]
bake(scene, "view_settings.exposure", [-0.35 + 0.8 * sum(spike(t, c_, 0.005, 0.05) for c_ in SET_CUTS) + 0.7 * spike(t, HIT, 0.02, 0.12)
                                       + 0.4 * spike(t, RED_T, 0.02, 0.15) for t in T])


def _light(kind, name, coll, loc, target, energy, size, color):
    d = bpy.data.lights.new(name, kind)
    d.energy, d.color = energy, color
    if kind == "AREA":
        d.size = size
    else:
        d.shadow_soft_size = size
    o = bpy.data.objects.new(name, d)
    coll.objects.link(o)
    o.location = loc
    o.rotation_euler = (V(target) - V(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


HEAD_H = P_HOME + V((0, 0, 1.6))
HEAD_L = P_LAB + V((0, 0, 1.45))
sun = bpy.data.lights.new("Sun", "SUN")
sun.energy, sun.angle, sun.color = 0.5, math.radians(3), (1.0, 0.93, 0.80)
sun_o = bpy.data.objects.new("Sun", sun)
HOME.objects.link(sun_o)
sun_o.rotation_euler = Euler((math.radians(60), 0, math.radians(-25)))
SKC = SCENTP + V((0, 2.0, 0.3))
DC = DOTSP + V((0, 3.0, 0.5))
LIGHTS = {
    "home": [sun_o,
             _light("AREA", "HomeKey", HOME, HEAD_H + V((1.5, -2.2, 0.8)), HEAD_H, 330, 1.6, (1.0, 0.93, 0.82)),
             _light("AREA", "HomeFill", HOME, HEAD_H + V((-1.9, -2.0, 0.2)), HEAD_H, 120, 2.0, (0.80, 0.88, 1.0)),
             _light("AREA", "HomeRim", HOME, HEAD_H + V((0.8, 1.6, 0.9)), HEAD_H, 200, 0.8, (1.0, 0.90, 0.75)),
             _light("AREA", "HomeWindow", HOME, HOMEP + V((1.9, 3.3, 1.6)), HEAD_H, 300, 1.3, (1.0, 0.94, 0.82))],
    "lab": [_light("AREA", "LabKey", LAB, LABP + V((0.0, 0.4, 2.5)), SHIRT_C, 200, 1.6, (0.90, 0.97, 1.0)),
            _light("AREA", "LabFill", LAB, LABP + V((-2.2, -0.5, 1.8)), SHIRT_C, 140, 2.0, (0.80, 0.90, 1.0)),
            _light("AREA", "LabFace", LAB, HEAD_L + V((0.8, -2.0, 0.5)), HEAD_L, 200, 1.2, (1.0, 0.95, 0.9)),
            _light("AREA", "LabBack", LAB, LABP + V((-1.6, 3.5, 2.4)), HEAD_L, 140, 1.0, (0.90, 0.97, 1.0))],
    "scent": [_light("AREA", "SKey", SCENT, SKC + V((0.8, -1.2, 1.4)), SKC, 70, 1.2, (1.0, 0.88, 0.78)),
              _light("AREA", "SRim", SCENT, SKC + V((-0.8, 1.2, 1.0)), SKC, 40, 0.8, (1.0, 0.7, 0.4))],
    "dots": [_light("AREA", "DKey", DOTS, DC + V((0.8, -1.8, 1.8)), DC, 90, 1.5, (0.75, 0.88, 1.0)),
             _light("AREA", "DRim", DOTS, DC + V((-0.6, 2.2, 1.0)), DC, 60, 1.0, (1.0, 0.7, 0.4))],
}
BASE = {l.name: l.data.energy for ls in LIGHTS.values() for l in ls}
for set_name, ls in LIGHTS.items():
    for l in ls:
        bake(l.data, "energy", [BASE[l.name] * (SET_OF[i] == set_name) for i in range(len(T))])

# ---------------------------------------------------------------- cameras
cams = S.Cameras(scene, T, F, CAST)


def span(name):
    i = next(k for k, s in enumerate(SHOTS) if s[1] == name)
    return SHOTS[i][0], (SHOTS[i + 1][0] if i + 1 < len(SHOTS) else DUR)


SK_P = SCENTP + V((0, 2.0, 0.1))
DC0 = DOTSP + V((0, 1.6, 0.25))
GRID_C = DOTSP + V((0, 4.6, 0.72))
MC = MACH_P + V((0, -0.2, 0.2))

a, b = span("NoseThumb")
cams.cam("NoseThumb", a, b, keys=[(a, FC + V((0.35, -1.0, 0.04))), (b, FC + V((0.15, -0.72, 0.02)))], lens=50, aim=FC, focus=face_pt,
         depth=0.25, shift_y=-0.05, shake=0.0010)
a, b = span("HomeWide")
cams.cam("HomeWide", a, b, keys=[(a, TC + V((1.8, -3.5, 0.45))), (b, TC + V((1.3, -3.0, 0.40)))], lens=28, aim=TC + V((-0.3, 0.6, 0.35)),
         depth=2.0, shift_y=0.02, shake=0.0010)
a, b = span("FaceWin")
cams.cam("FaceWin", a, b, keys=[(a, FC + V((-0.95, -1.45, 0.06))), (b, FC + V((-0.55, -1.00, 0.04)))], lens=50, aim=FC, focus=face_pt,
         depth=0.2, shift_y=-0.05, shake=0.0010)
a, b = span("HomeOrbit")
cams.cam("HomeOrbit", a, b, path=S.orbit(TC + V((0, 0, 0.35)), 1.9, -30, 12, 0.02, 0.0), lens=38, aim=TC + V((0, 0, 0.55)), depth=0.8,
         shift_y=-0.03, shake=0.0008)
a, b = span("ScentMacro")
cams.cam("ScentMacro", a, b, keys=[(a, SK_P + V((-0.5, -0.9, 0.18))), (b, SK_P + V((-0.2, -0.55, 0.22)))], lens=55, aim=SK_P + V((0, 0, 0.18)),
         depth=0.2, shake=0.0004)
a, b = span("ScentPull")
cams.cam("ScentPull", a, b, keys=[(a, SK_P + V((0.35, -0.55, 0.10))), (b, SK_P + V((0.7, -1.3, 0.55)))], lens=45, aim=SK_P + V((0, 0, 0.30)),
         depth=0.5, shake=0.0004, ease="cine")
a, b = span("ShirtRow")
cams.cam("ShirtRow", a, b, keys=[(a, LABP + V((-1.7, 0.30, CT + 0.95))), (b, LABP + V((0.3, 0.30, CT + 0.90)))], lens=40,
         aim=LABP + V((-0.4, 1.5, CT)), depth=0.9, shake=0.0008)
a, b = span("SniffMed")
cams.cam("SniffMed", a, b, keys=[(a, FCL + V((-0.55, -1.7, -0.25))), (b, FCL + V((-0.30, -1.2, -0.30)))], lens=45, aim=FCL + V((0, 0, -0.35)),
         focus=face_pt, depth=0.5, shift_y=-0.02, shake=0.0008)
a, b = span("AmberSlomo")
cams.cam("AmberSlomo", a, b, keys=[(a, SHIRT_C + V((-0.35, -0.80, 0.60))), (b, SHIRT_C + V((-0.08, -0.55, 0.42)))], lens=50,
         aim=SHIRT_C, depth=0.3, shake=0.0003, kicks=[(HIT, 0.008, 0.3)], ease="cine")
a, b = span("SniffWide")
cams.cam("SniffWide", a, b, keys=[(a, LABP + V((0.9, -0.4, 1.35))), (b, LABP + V((0.45, 0.0, 1.30)))], lens=32,
         aim=LABP + V((-0.45, 2.0, 1.1)), depth=1.5, shake=0.0008)
a, b = span("CardsFlip")
cams.cam("CardsFlip", a, b, keys=[(a, DC0 + V((-1.6, -0.9, 0.30))), (b, DC0 + V((0.3, -1.1, 0.30)))], lens=40, aim=DC0 + V((0.1, 0, 0.02)),
         depth=0.8, shake=0.0006)
a, b = span("CardAmber")
CA = DOTSP + V((-0.9 + 0.257 * 7, 1.6, 0.18))
cams.cam("CardAmber", a, b, keys=[(a, CA + V((0.0, -1.2, 0.2))), (b, CA + V((0.0, -0.55, 0.12)))], lens=55, aim=CA + V((0, 0, 0.02)),
         depth=0.3, shake=0.0004, ease="cine")
a, b = span("SebumMacro")
cams.cam("SebumMacro", a, b, path=S.orbit(SK_P + V((0, 0, 0.25)), 0.55, -35, 10, 0.0, 0.1), lens=55, aim=SK_P + V((0, 0, 0.25)), depth=0.2,
         shake=0.0004)
a, b = span("SebumTop")
cams.cam("SebumTop", a, b, keys=[(a, SK_P + V((0.1, -0.25, 0.9))), (b, SK_P + V((0.3, -0.7, 1.25)))], lens=40, aim=SK_P + V((0, 0, 0.2)),
         depth=0.5, shake=0.0004)
a, b = span("SwabCU")
cams.cam("SwabCU", a, b, keys=[(a, SWP + V((-0.35, -0.55, 0.0))), (b, SWP + V((0.10, -0.42, -0.02)))], lens=60, aim=SWP + V((0, 0, -0.08)),
         depth=0.2, shake=0.0004)
a, b = span("MachineCU")
cams.cam("MachineCU", a, b, keys=[(a, MC + V((0.35, -0.85, 0.15))), (b, MC + V((0.10, -0.50, 0.05)))], lens=50, aim=MC,
         depth=0.25, shake=0.0004)
a, b = span("DotsPush")
cams.cam("DotsPush", a, b, keys=[(a, GRID_C + V((-0.9, -2.4, 0.15))), (b, GRID_C + V((-0.4, -1.6, 0.05)))], lens=42, aim=GRID_C,
         depth=0.9, shake=0.0006)
a, b = span("OneRed")
cams.cam("OneRed", a, b, keys=[(a, RED_P + V((0.45, -1.2, 0.2))), (b, RED_P + V((0.12, -0.45, 0.06)))], lens=55, aim=RED_P,
         depth=0.25, shake=0.0004, ease="cine")
a, b = span("HomeClose")
cams.cam("HomeClose", a, b, keys=[(a, FC + V((0.5, -1.5, 0.05))), (b, FC + V((0.2, -0.85, 0.03)))], lens=50, aim=FC, focus=face_pt,
         depth=0.25, shift_y=-0.05, shake=0.0008)
a, b = span("Closer")
cams.cam("Closer", a, b, path=S.orbit(TC + V((0, 0, 0.35)), 1.5, 35, 8, -0.02, 0.0), lens=40, aim=TC + V((0, 0, 0.5)), depth=0.8,
         shift_y=-0.03, shake=0.0008)

cams.markers(SHOTS)
S.check_shots(SHOTS, DUR)


def gaze_target(t):
    return None


him.bake_gaze(FRAMES, T, gaze_target, CAST, seed=17)

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
