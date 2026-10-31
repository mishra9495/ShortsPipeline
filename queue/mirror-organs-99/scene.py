"""mirror-organs-99: "She lived ninety-nine years with her organs on the wrong side" (Rose Marie Bentley, 1918-2017).
Source: OHSU news release "Body donor's rare anatomy offers valuable lessons" (2019-04-08; found by first-year medical
students in a gross anatomy class in 2018): situs inversus with levocardia, liver/stomach/other abdominal organs
transposed right to left, heart on the normal (left) side, about 1 in 22,000 births, oldest known patient (99).

Run (daily_render.ps1): blender -b --python scene.py -- <ROOT>/blend/<slug>.blend vo=<wav> beats=<json> fps=30
Optional: stills=1,200 pct=100 samples=128 device=gpu|cpu root=<ROOT>

v3 toolkit: every model is built in Blender from code (scripts/kit.py), she acts procedurally on the mixamorig bones
(scripts/actor.py) and every camera is a moving spline that is already in motion on the cut (scripts/shot.py).
No captions, no on-screen text (owner's rule). Timing comes only from the beats JSON.

Cast: her = blend/char_heroine.blend (female lead; never replaced by the male hero). One actor.
Sets: HOME (sunny living room, five photo frames on the wall), LAB (anatomy lab: steel table under a sheet, lamp, bench
with a skull, instrument tray), ORGAN (her torso organs on her rig in a dark void; the X-ray body shell is hidden),
GRID (22,000 glowing dots, one amber). Set changes are HARD CUTS (whoosh + exposure spike). SYNC with mix.py.
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
SWIM = at(1, 0.50)                                # "loved swimming": she mimes a stroke
SLO_A, SLO_B = B[5], at(5, 0.62)                  # screen-time slow-mo window: liver and stomach swap sides (money moment)
ACT_A, ACT_B = SLO_A, SLO_A + (SLO_B - SLO_A) * 0.4
HIT_F = 0.45                                      # fraction of the slow-mo window where the organs cross
HIT = SLO_A + HIT_F * (SLO_B - SLO_A)
HIT_ACT = ACT_A + HIT_F * (ACT_B - ACT_A)
WRONG = at(4, 0.62)                               # "the blood vessels looked wrong": the vessels flash amber
AMBER = at(7, 0.55)                               # the one amber dot among the 22,000
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


# ---------------------------------------------------------------- measure her torso (rest pose, rig-local) to place organs
rig = him.rig
rig.data.pose_position = "REST"
bpy.context.view_layer.update()
_ev = him.body.evaluated_get(bpy.context.evaluated_depsgraph_get())
_me = _ev.to_mesh()
_inv = rig.matrix_world.inverted()
VERTS = [_inv @ (him.body.matrix_world @ v.co) for v in _me.vertices]
_ev.to_mesh_clear()
rig.data.pose_position = "POSE"
REST_HIPS = him.hips0.copy()
SH_L, SH_R = him.bone_rest_head("LeftArm"), him.bone_rest_head("RightArm")
Z0 = REST_HIPS.z
TZ = max(0.4, SH_L.z - Z0)                                    # hips to shoulder joints
WX = 0.85 * abs(SH_L.x - him.x0)                              # torso half width
mid_ = []
for _hw in (0.05, 0.10, 0.20, 0.40):                          # widen the midline band until the mesh is found (heroine rig differs)
    for _z0, _z1 in ((0.6, 0.9), (0.4, 1.0), (0.0, 1.2)):
        mid_ = [v for v in VERTS if abs(v.x - him.x0) < _hw and Z0 + _z0 * TZ < v.z < Z0 + _z1 * TZ]
        if len(mid_) >= 6:
            break
    if len(mid_) >= 6:
        break
if not mid_:
    print("TORSO WARN: no body vertices near the torso; using bone-based depth", len(VERTS), tuple(him.hips0), SH_L[:])
    mid_ = [Vector((him.x0, him.hips0.y - 0.10, Z0 + 0.7 * TZ)), Vector((him.x0, him.hips0.y + 0.10, Z0 + 0.7 * TZ))]
YF, YB = min(v.y for v in mid_), max(v.y for v in mid_)       # chest front / back
YC, DY = (YF + YB) / 2, (YB - YF) / 2
X0 = him.x0
SC = TZ / 0.52
OC = Vector((X0, YC, Z0 + 0.55 * TZ))                         # centre of the torso organs (rest, rig-local)
print("TORSO", "TZ", round(TZ, 3), "WX", round(WX, 3), "YC", round(YC, 3), "DY", round(DY, 3), "OC", tuple(round(c, 3) for c in OC))


def R(dx, dy, tz):
    """Rest-space point: dx metres from the body midline (+X = her LEFT), dy metres from the chest centre (-Y = front)."""
    return Vector((X0 + dx, YC + dy, Z0 + tz * TZ))


# ---------------------------------------------------------------- sets
HOMEP, LABP, GRIDP, ORGP = Vector((0, 0, 0)), Vector((40, 0, 0)), Vector((80, 0, 0)), Vector((0, 0, -60))
HOME, LAB, GRID, ORGS = K.coll("SetHome"), K.coll("SetLab"), K.coll("SetGrid"), K.coll("SetOrgan")

# HOME: a sunny living room. Five photo frames (her five children) on the back wall; the window is on the right.
K.room(HOME, origin=HOMEP + Vector((0, 1.0, 0)), size=(6.0, 5.2, 2.8), floor_mat=K.floorboards(),
       wall_color=(0.88, 0.80, 0.68), name="HomeRoom", openings=[(1.9, 1.5, 1.44, 1.44)])
K.window(HOME, HOMEP + Vector((1.9, 3.57, 1.5)), size=(1.3, 1.3), curtains=True, sky=(1.0, 0.93, 0.78), sky_strength=4.0)
P_HOME = HOMEP + Vector((-0.9, 1.2, 0))                         # where she stands (feet)
for k in range(5):
    K.picture_frame(HOME, HOMEP + Vector((-2.15 + 0.44 * k, 3.55, 1.62 + 0.05 * (k % 2))), (0.30, 0.38), name=f"Kid{k}", seed=11 + k)
K.rug(HOME, P_HOME + Vector((0.3, 0.2, 0.0)), size=(2.8, 2.0), name="HomeRug")
K.floor_lamp(HOME, HOMEP + Vector((-2.55, 2.9, 0)))
K.potted_plant(HOME, HOMEP + Vector((2.55, 2.7, 0)), h=1.3, seed=4)
K.bookshelf(HOME, HOMEP + Vector((0.55, 3.28, 0)), w=0.9, h=1.7, seed=8)
K.mug(HOME, HOMEP + Vector((1.2, 0.2, 0.0)), color=(0.9, 0.9, 0.92))

# LAB: an anatomy lab. A body under a sheet on a steel table (nothing shown), lamp, bench with a skull, tray.
LAB_FLOOR = K.paint("LabFloor", (0.52, 0.58, 0.58), 0.25)
K.room(LAB, origin=LABP + Vector((0, 1.0, 0)), size=(6.0, 5.2, 2.8), floor_mat=LAB_FLOOR, wall_color=(0.72, 0.80, 0.78), name="LabRoom")
tbl = K.or_table(LAB, LABP + Vector((0.0, 1.5, 0)), name="LabTable")
tbl.rotation_euler = (0, 0, math.pi / 2)
sheet_m = K.fabric("LabSheet", (0.80, 0.86, 0.88), weave=600)
K.cushion("SheetBody", LAB, (1.62, 0.40, 0.13), LABP + Vector((0.0, 1.5, 1.025)), sheet_m, puff=0.5)
K.sphere("SheetHead", LAB, 0.095, LABP + Vector((-0.78, 1.5, 1.05)), sheet_m, scale=(1.0, 0.9, 0.8), subdiv=4)
K.sphere("SheetFeet", LAB, 0.07, LABP + Vector((0.8, 1.5, 1.04)), sheet_m, scale=(1.2, 1.3, 0.8), subdiv=4)
K.surgical_lamp(LAB, LABP + Vector((0.2, 1.5, 1.85)), name="LabLamp")
K.lab_bench(LAB, LABP + Vector((-1.7, 3.1, 0)), name="LabBench")
SKULL_C = LABP + Vector((-2.15, 3.05, 1.02))
K.skull(LAB, SKULL_C, name="LabSkull")
K.instrument_tray(LAB, LABP + Vector((1.15, 0.85, 0)), name="LabTray", rot=math.radians(-20))
K.potted_plant(LAB, LABP + Vector((2.5, 2.7, 0)), h=1.1, seed=2)
TABLE_C = LABP + Vector((0.0, 1.5, 1.05))
TRAY_C = LABP + Vector((1.15, 0.85, 1.02))

# GRID: 22,000 glowing dots (one per 22,000 births) on a dark mirror floor, and one amber dot.
COLS, ROWS, STEP = 200, 110, 0.05
GEM_RC = (44, 108)
dots_me = bpy.data.meshes.new("Dots22k")
_bm = bmesh.new()
_h = 0.013
for r_ in range(ROWS):
    for c_ in range(COLS):
        if (r_, c_) == GEM_RC:
            continue
        cx, cy = (c_ - COLS / 2 + 0.5) * STEP, r_ * STEP
        vs = [_bm.verts.new((cx + sx * _h, cy + sy * _h, sz * _h + _h)) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
        _bm.faces.new((vs[0], vs[1], vs[3], vs[2]))
        _bm.faces.new((vs[4], vs[6], vs[7], vs[5]))
        _bm.faces.new((vs[0], vs[4], vs[5], vs[1]))
        _bm.faces.new((vs[2], vs[3], vs[7], vs[6]))
        _bm.faces.new((vs[0], vs[2], vs[6], vs[4]))
        _bm.faces.new((vs[1], vs[5], vs[7], vs[3]))
_bm.to_mesh(dots_me)
_bm.free()
dots_m = glowy("DotsCold", (0.55, 0.78, 1.0), rough=0.3, sss=0.0, emit=1.6)
dots = bpy.data.objects.new("Dots22k", dots_me)
GRID.objects.link(dots)
dots.data.materials.append(dots_m)
dots.location = GRIDP
K.plane("GridFloor", GRID, (30, 30), GRIDP + Vector((0, 3, 0)), K.plastic("GridFloorM", (0.01, 0.012, 0.02), 0.08, coat=0.5))
gem_m = glowy("GemAmber", (1.0, 0.55, 0.08), rough=0.2, sss=0.0, emit=0.0)
GEM_P = GRIDP + Vector(((GEM_RC[1] - COLS / 2 + 0.5) * STEP, GEM_RC[0] * STEP, _h))
gem = K.rbox("GemAmber", GRID, (0.052, 0.052, 0.052), GEM_P + Vector((0, 0, 0.012)), gem_m, bevel=0.006)

# ---------------------------------------------------------------- ORGANS: parented to her spine, so they ride her body
ORG = bpy.data.objects.new("Organs", None)
CAST.objects.link(ORG)
him.parent_to_bone(ORG, "Spine1")
ORGS_ALL = []


def org(o):
    o.parent = ORG
    ORGS_ALL.append(o)
    return o


organ_defs = {
    "liver": glowy("Liver", (0.52, 0.12, 0.08), rough=0.35, sss=0.3, emit=0.55),
    "stomach": glowy("Stomach", (0.90, 0.42, 0.44), rough=0.35, sss=0.3, emit=0.55),
    "spleen": glowy("Spleen", (0.45, 0.06, 0.16), rough=0.35, sss=0.2, emit=0.5),
    "heart": glowy("Heart", (0.85, 0.07, 0.09), rough=0.3, sss=0.3, emit=0.9),
    "gut": glowy("Bowel", (0.95, 0.52, 0.46), rough=0.4, sss=0.3, emit=0.45),
    "bone": glowy("RibBone", (0.95, 0.90, 0.78), rough=0.45, sss=0.0, emit=0.30),
}
lung_m = xglow("Lung", (0.95, 0.55, 0.65), 1.7, blend=0.35, core=0.0)
aorta_m = glowy("Aorta", (0.9, 0.12, 0.1), rough=0.25, sss=0.0, emit=1.0)
vena_m = glowy("Vena", (0.12, 0.22, 0.95), rough=0.25, sss=0.0, emit=1.0)

# lungs (translucent rim-glow shells) + ribs + spine
for sx in (-1, 1):
    org(K.sphere(f"Lung{sx}", ORGS, 1.0, R(sx * 0.62 * WX, 0.0, 0.82), lung_m, scale=(0.060 * SC * WX / 0.15, 0.062 * SC, 0.115 * SC), subdiv=4))
for k in range(7):
    z_ = 0.60 + 0.055 * k
    ax = WX * (0.78 + 0.06 * math.sin(math.pi * k / 7))
    ay = DY * 0.86
    for sx in (-1, 1):
        pts = []
        for j in range(9):
            th = 0.12 + 1.95 * j / 8
            pts.append(Vector((X0 + sx * ax * math.sin(th), YC + (ay) * math.cos(th), Z0 + (z_ - 0.03 * math.sin(th)) * TZ)))
        org(K.tube(f"Rib{k}{sx}", ORGS, pts, 0.0045, organ_defs["bone"], res=3))
for k in range(13):
    org(K.cyl(f"Vert{k}", ORGS, 0.019, 0.03, R(0, DY * 0.72, 0.06 + 0.075 * k), organ_defs["bone"], verts=14))

# the heart stays on her LEFT (+X) where it belongs (levocardia); vessels run beside the spine
HEART_REL = R(0.045 * SC, -0.012, 0.80)
heart = K.sphere("Heart", ORGS, 1.0, HEART_REL, organ_defs["heart"], scale=(0.047 * SC, 0.040 * SC, 0.056 * SC), subdiv=4)
heart.rotation_euler = (0, math.radians(18), math.radians(-18))
org(heart)
AORTA = [R(0.030, -0.005, 0.86), R(0.025, 0.000, 0.95), R(0.050, 0.015, 1.01), R(0.085, 0.040, 0.95), R(0.075, 0.060, 0.72),
         R(0.050, 0.066, 0.42), R(0.040, 0.066, 0.10)]
VENA = [R(-0.030, 0.060, 0.10), R(-0.036, 0.052, 0.45), R(-0.032, 0.040, 0.74), R(-0.012, 0.010, 0.84)]
aorta = org(K.tube("Aorta", ORGS, AORTA, 0.0105, aorta_m, res=8))
vena = org(K.tube("Vena", ORGS, VENA, 0.0095, vena_m, res=8))
BEADS = [org(K.sphere(f"Bead{k}", ORGS, 0.0075, HEART_REL, glowy("Bead", (1.0, 0.75, 0.3), emit=5.0), subdiv=2)) for k in range(16)]

# liver + stomach + spleen: HERS are mirrored; NORMAL is what the slow-mo starts from
LIVER_N, LIVER_M = R(-0.062 * SC, -0.012, 0.52), R(0.062 * SC, -0.012, 0.52)
STOM_N, STOM_M = R(0.052 * SC, -0.010, 0.47), R(-0.052 * SC, -0.010, 0.47)
SPLN_N, SPLN_M = R(0.098 * SC, 0.030, 0.55), R(-0.098 * SC, 0.030, 0.55)
liver = org(K.sphere("Liver", ORGS, 1.0, LIVER_M, organ_defs["liver"], scale=(0.100 * SC, 0.056 * SC, 0.050 * SC), subdiv=4))
liver_lobe = K.sphere("LiverLobe", ORGS, 1.0, (-0.72, 0.0, -0.15), organ_defs["liver"], scale=(0.55, 0.78, 0.8), subdiv=3)
liver_lobe.parent = liver
stom = org(K.sphere("Stomach", ORGS, 1.0, STOM_M, organ_defs["stomach"], scale=(0.040 * SC, 0.034 * SC, 0.060 * SC), subdiv=4))
stom_bulb = K.sphere("StomachBulb", ORGS, 1.0, (-0.9, 0.0, -0.55), organ_defs["stomach"], scale=(0.7, 0.8, 0.45), subdiv=3)
stom_bulb.parent = stom
spln = org(K.sphere("Spleen", ORGS, 1.0, SPLN_M, organ_defs["spleen"], scale=(0.020 * SC, 0.020 * SC, 0.040 * SC), subdiv=3))
# bowel coil in the lower belly
gut_pts = []
for k in range(14):
    row, col = divmod(k, 5)
    xs = (col - 2) * 0.034 * SC * (1 if row % 2 == 0 else -1)
    gut_pts.append(R(xs, -0.012 + 0.006 * math.sin(k), 0.30 - 0.07 * row))
org(K.tube("Bowel", ORGS, gut_pts, 0.013 * SC, organ_defs["gut"], res=6))
for o in ORGS_ALL:
    o.visible_shadow = False
print("ORGANS", len(ORGS_ALL))

# ---------------------------------------------------------------- shots (start, camera, set)
SHOTS = [
    (0.0, "XThumb", "home"),
    (at(0, 0.50), "HomeWide", "home"),
    (B[1], "Photos", "home"),
    (SWIM, "SwimMed", "home"),
    (B[2], "WindowSun", "home"),
    (at(2, 0.50), "LabTable", "lab"),
    (B[3], "LabTray", "lab"),
    (B[4], "HeartOrbit", "organ"),
    (at(4, 0.45), "VesselMacro", "organ"),
    (SLO_A, "SwapSlomo", "organ"),
    (SLO_B, "MirrorCU", "organ"),
    (B[6], "HeartBeat", "organ"),
    (at(6, 0.50), "BodyXFull", "home"),
    (B[7], "GridRise", "grid"),
    (at(7, 0.50), "OneAmber", "grid"),
    (B[8], "HeartPulse", "organ"),
    (at(8, 0.50), "HomeOrbit", "home"),
    (B[9], "LabLamp", "lab"),
    (at(9, 0.42), "Closer", "home"),
]
XSPEC = {"XThumb": "out", "BodyXFull": "in", "Closer": "in"}      # shots where her body is an X-ray shell in the HOME set


def shot_at(t):
    return max((s for s in SHOTS if s[0] <= t + 1e-6), key=lambda s: s[0])


SH = [shot_at(t) for t in T]
SET_OF = [s[2] for s in SH]
SHOT_END = {s[1]: (SHOTS[k + 1][0] if k + 1 < len(SHOTS) else DUR) for k, s in enumerate(SHOTS)}
OFF = Vector((X0, REST_HIPS.y, 0))


def him_root(s):
    """(location, euler) of her rig object. HOME: standing on her mark. ORGAN: organs centred on ORGP. Else parked far away."""
    if s[2] == "home":
        return P_HOME - OFF, (0, 0, 0)
    if s[2] == "organ":
        return ORGP - OC, (0, 0, 0)
    return Vector((0, 0, -300)), (0, 0, 0)

# ---------------------------------------------------------------- performance
BLINKS = [1.0 + 2.9 * k for k in range(60) if 1.0 + 2.9 * k < DUR]


def channels(t):
    ch = {}
    smile_a = 0.55 * ramp(t, B[1] + 0.1, B[1] + 0.7)
    ch["wist"] = env(t, B[2] - 0.05, B[2] + 0.5, BE[2] - 0.2, BE[2] + 0.25)           # "she died in 2017": a quiet look down
    ch["pride"] = ramp(t, B[8] - 0.1, B[8] + 0.9)
    ch["smile"] = max(smile_a * (1 - ch["wist"]), ch["pride"])
    ch["swim"] = env(t, SWIM - 0.12, SWIM + 0.25, BE[1] - 0.25, BE[1])               # mimes a swimming stroke
    ch["blink"] = max((env(t, b_ - 0.03, b_, b_ + 0.05, b_ + 0.12) for b_ in BLINKS), default=0.0)
    return ch


legs_stand = him.standing_legs()
SIDE_L = REST_HIPS + Vector((0.22, 0.02, -0.12))
SIDE_R = REST_HIPS + Vector((-0.22, 0.02, -0.12))
face_pt = him.anchor("Face", "Head", Vector((him.x0, him.nose.y + 0.05, him.nose.z - 0.01)), CAST)
eyes_mid = him.anchor("Eyes", "Head", (him.eye_l + him.eye_r) / 2, CAST)
chest_pt = him.anchor("Chest", "Spine2", him.bone_rest_head("Spine2"), CAST)
torso_pt = him.anchor("Torso", "Spine1", OC, CAST)

for i, t in enumerate(T):
    s = SH[i]
    ch = channels(t)
    br = math.sin(t * 2 * math.pi / 3.6)
    sw = ch["swim"]
    phi = (t - SWIM) / 0.95 * 2 * math.pi
    spec = {
        "Hips": [(A.Z, 0.6 * wobble(t, 1))],
        "Spine": [(A.X, 0.6 * br + 3 * ch["wist"]), (A.Z, 0.8 * wobble(t, 2)), (A.Y, 7 * sw * math.sin(phi))],
        "Spine1": [(A.X, 0.7 * br + 2 * ch["wist"])],
        "Spine2": [(A.X, 1.5 + 0.6 * br)],
        "Neck": [(A.X, 4 * ch["wist"]), (A.Z, 1.2 * wobble(t, 4))],
        "Head": [(A.X, 1.0 * wobble(t, 7, 0.6) + 9 * ch["wist"] - 2 * ch["pride"]), (A.Z, 1.6 * wobble(t, 5, 0.5)),
                 (A.Y, 1.0 * wobble(t, 6) + 3 * ch["pride"] * wobble(t, 8, 0.7))],
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
        sh[f"eyeBlink{side}"] = min(1.0, ch["blink"] + 0.30 * ch["wist"] + 0.12 * ch["smile"])
        sh[f"eyeWide{side}"] = 0.0
        sh[f"browDown{side}"] = 0.0
        sh[f"eyeSquint{side}"] = 0.35 * ch["smile"]
        sh[f"mouthFrown{side}"] = 0.18 * ch["wist"]
        sh[f"mouthSmile{side}"] = 0.9 * ch["smile"]
        sh[f"cheekSquint{side}"] = 0.4 * ch["smile"]
        sh[f"mouthPress{side}"] = 0.15 * ch["wist"]
    sh["browInnerUp"] = 0.55 * ch["wist"] + 0.15 * ch["pride"]
    sh["jawOpen"] = 0.04 * ch["smile"]
    ikl = SIDE_L + Vector((0, 0, 0.004 * br))
    ikr = SIDE_R + Vector((0, 0, 0.004 * br))
    if sw > 0.001:
        R_ = 0.44
        cr, cl = SH_R + Vector((-0.04, -0.06, -0.02)), SH_L + Vector((0.04, -0.06, -0.02))
        pr = cr + Vector((0, -R_ * math.sin(phi), -R_ * math.cos(phi)))
        pl = cl + Vector((0, -R_ * math.sin(phi + math.pi), -R_ * math.cos(phi + math.pi)))
        ikr, ikl = ikr.lerp(pr, sw), ikl.lerp(pl, sw)
    him.record(rots, sh, ikl, ikr, aim=(0.0, 0.0), follow={}, root=him_root(s))
him.bake(FRAMES)
for fc in A.fcurves_of(him.rig):
    if fc.data_path in ("location", "rotation_euler"):
        fc.keyframe_points.foreach_set("interpolation", [0] * len(fc.keyframe_points))   # teleports are cuts

# ---------------------------------------------------------------- X-ray look on her body (driven by scene["xray"]) + organ visibility
TA = [warp(t) for t in T]


def xray_on(i):
    s = SH[i]
    mode = XSPEC.get(s[1])
    t = T[i]
    if mode == "out":                                        # frame 1 is already X-ray (thumbnail); fades back to a clothed woman
        return 1.0 - ramp(t, SHOT_END[s[1]] - 0.45, SHOT_END[s[1]] - 0.05)
    if mode == "in":
        return ramp(t, s[0] + 0.05, s[0] + 0.35)
    return 0.0


XON = [xray_on(i) for i in range(len(T))]


# ---------------------------------------------------------------- organ animation
def mirror(t):
    """1 = HER anatomy (liver on her left); the slow-mo starts from normal anatomy (0) and swaps."""
    if t < SLO_A or t >= SLO_B:
        return 1.0
    return smooth(ramp((t - SLO_A) / (SLO_B - SLO_A), 0.18, 0.72))


MIR = [mirror(t) for t in T]


def beat_pulse(ta):
    return max(0.0, math.sin(2 * math.pi * 1.25 * ta)) ** 6


# liver / stomach / spleen: slide across, passing one in front of the other
lv_l, lv_r, st_l, st_r, sp_l, sp_r = [], [], [], [], [], []
for i, t in enumerate(T):
    m = MIR[i]
    arc = math.sin(math.pi * m) if 0.0 < m < 1.0 else 0.0
    lv_l.append(LIVER_N.lerp(LIVER_M, m) + Vector((0, -0.045 * arc, 0.012 * arc)))
    lv_r.append((0, 0, 0.25 * (1 - 2 * m) + math.pi * m))
    st_l.append(STOM_N.lerp(STOM_M, m) + Vector((0, 0.040 * arc, -0.010 * arc)))
    st_r.append((0, 0, math.radians(-12) * (1 - 2 * m) + math.pi * m))
    sp_l.append(SPLN_N.lerp(SPLN_M, m) + Vector((0, 0.02 * arc, 0)))
    sp_r.append((0, 0, 0))
bake_vec(liver, "location", lv_l)
bake_vec(liver, "rotation_euler", lv_r)
bake_vec(stom, "location", st_l)
bake_vec(stom, "rotation_euler", st_r)
bake_vec(spln, "location", sp_l)
# heart beat + breathing lungs
hs = heart.scale.copy()
bake_vec(heart, "scale", [tuple(v * (1 + 0.11 * beat_pulse(TA[i])) for v in hs) for i in range(len(T))])
for o in ORGS_ALL:
    if o.name.startswith("Lung"):
        sc = o.scale.copy()
        bake_vec(o, "scale", [(sc.x * (1 + 0.025 * math.sin(2 * math.pi * 0.28 * t)), sc.y, sc.z * (1 + 0.03 * math.sin(2 * math.pi * 0.28 * t))) for t in T])
# blood beads flow down the aorta (and a pulse of amber through the vessels at "wrong")
poly = AORTA


def on_poly(u):
    x = u * (len(poly) - 1)
    j = min(len(poly) - 2, int(x))
    return poly[j].lerp(poly[j + 1], x - j)


for k, b_ in enumerate(BEADS):
    ph = k / len(BEADS)
    locs = [on_poly((ph + 0.30 * TA[i]) % 1.0) for i in range(len(T))]
    bake_vec(b_, "location", locs)
WR = [spike(t, WRONG, 0.08, 0.5) for t in T]                   # vessels flash amber when the students notice
for mat, base in ((aorta_m, (0.9, 0.12, 0.1)), (vena_m, (0.12, 0.22, 0.95))):
    cols = [tuple(base[c] + (a - base[c]) * min(1.0, w) for c, a in enumerate((1.0, 0.72, 0.1))) + (1,) for w in WR]
    bake_vec(mat.node_tree, BSDF + '["Base Color"].default_value', cols, n=4)
    bake_vec(mat.node_tree, BSDF + '["Emission Color"].default_value', cols, n=4)
    bake(mat.node_tree, BSDF + '["Emission Strength"].default_value', [1.0 + 3.5 * w for w in WR])
# the amber dot among the 22,000: rises and starts to glow
GU = [ramp(t, AMBER - 0.35, AMBER + 0.45) for t in T]
bake(gem_m.node_tree, BSDF + '["Emission Strength"].default_value', [1.0 + 9.0 * u * (0.85 + 0.15 * math.sin(2 * math.pi * 1.6 * t)) for u, t in zip(GU, T)])
bake_vec(gem, "scale", [(1 + 1.2 * u,) * 3 for u in GU])
bake(dots_m.node_tree, BSDF + '["Emission Strength"].default_value', [1.3 + 0.35 * math.sin(2 * math.pi * 0.45 * t) for t in T])

# ---------------------------------------------------------------- X-ray shader on her body
scene["xray"] = 0.0


def xray_group():
    ng = bpy.data.node_groups.new("XRayShell", "ShaderNodeTree")
    ng.interface.new_socket("Shader", in_out="OUTPUT", socket_type="NodeSocketShader")
    N, L = ng.nodes, ng.links
    o = N.new("NodeGroupOutput")
    lw = N.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.35
    rm = N.new("ShaderNodeMapRange")
    rm.inputs[1].default_value, rm.inputs[2].default_value = 0.15, 0.9
    L.new(lw.outputs["Facing"], rm.inputs[0])
    pw = N.new("ShaderNodeMath")
    pw.operation = "POWER"
    pw.inputs[1].default_value = 1.6
    L.new(rm.outputs[0], pw.inputs[0])
    em = N.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.32, 0.72, 1.0, 1)
    em.inputs["Strength"].default_value = 2.0
    tr = N.new("ShaderNodeBsdfTransparent")
    mx = N.new("ShaderNodeMixShader")
    k = N.new("ShaderNodeMath")
    k.operation = "MULTIPLY"
    k.inputs[1].default_value = 0.5
    L.new(pw.outputs[0], k.inputs[0])
    L.new(k.outputs[0], mx.inputs[0])
    L.new(tr.outputs[0], mx.inputs[1])
    L.new(em.outputs[0], mx.inputs[2])
    L.new(mx.outputs[0], o.inputs[0])
    return ng


XG = xray_group()
done = set()
for o in him.objs:
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
        fc = mx.inputs[0].driver_add("default_value")
        fc.driver.type = "SCRIPTED"
        v = fc.driver.variables.new()
        v.name = "x"
        v.targets[0].id_type = "SCENE"
        v.targets[0].id = scene
        v.targets[0].data_path = '["xray"]'
        fc.driver.expression = "x"
bake(scene, '["xray"]', XON)


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


ORG_ALL = list(ORG.children_recursive)
for name, coll in (("home", HOME), ("lab", LAB), ("grid", GRID)):
    key_vis([o for o in coll.all_objects if not o.hide_render], lambda i, name=name: SET_OF[i] == name)
key_vis([o for o in rig.children_recursive if o.type in ("MESH", "CURVES", "CURVE") and o not in ORG_ALL],
        lambda i: SET_OF[i] == "home")
key_vis(ORG_ALL, lambda i: SET_OF[i] == "organ" or (SET_OF[i] == "home" and XON[i] > 0.02))

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
WCOL = {"home": ((0.78, 0.84, 0.92), 0.35), "lab": ((0.30, 0.34, 0.36), 0.15), "organ": ((0.020, 0.005, 0.008), 1.0),
        "grid": ((0.004, 0.007, 0.016), 1.0)}
cols = [WCOL[s] for s in SET_OF]
bake_vec(wnt, 'nodes["Background"].inputs[0].default_value', [(*c_, 1) for c_, _ in cols], n=4, interp="CONSTANT")
bake(wnt, 'nodes["Background"].inputs[1].default_value', [s_ for _, s_ in cols], interp="CONSTANT")
SET_CUTS = [s[0] for k, s in enumerate(SHOTS) if k and SHOTS[k - 1][2] != s[2]]
bake(scene, "view_settings.exposure", [-0.35 + 0.8 * sum(spike(t, c_, 0.005, 0.05) for c_ in SET_CUTS) + 0.7 * spike(t, HIT, 0.02, 0.12)
                                       + 0.4 * spike(t, AMBER, 0.02, 0.15) for t in T])

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
sun = bpy.data.lights.new("Sun", "SUN")
sun.energy, sun.angle, sun.color = 0.5, math.radians(3), (1.0, 0.93, 0.80)
sun_o = bpy.data.objects.new("Sun", sun)
HOME.objects.link(sun_o)
sun_o.rotation_euler = Euler((math.radians(60), 0, math.radians(-25)))
OCW = ORGP
GC = GRIDP + Vector((0.4, 2.2, 0.0))
LIGHTS = {
    "home": [sun_o,
             _light("AREA", "HomeKey", HOME, HEAD_H + Vector((1.5, -2.2, 0.8)), HEAD_H, 330, 1.6, (1.0, 0.93, 0.82)),
             _light("AREA", "HomeFill", HOME, HEAD_H + Vector((-1.9, -2.0, 0.2)), HEAD_H, 120, 2.0, (0.80, 0.88, 1.0)),
             _light("AREA", "HomeRim", HOME, HEAD_H + Vector((0.8, 1.6, 0.9)), HEAD_H, 200, 0.8, (1.0, 0.90, 0.75)),
             _light("AREA", "HomeWindow", HOME, HOMEP + Vector((1.9, 3.3, 1.6)), HEAD_H, 300, 1.3, (1.0, 0.94, 0.82))],
    "lab": [_light("AREA", "LabKey", LAB, LABP + Vector((0.5, -0.6, 2.5)), TABLE_C, 380, 1.4, (0.90, 0.97, 1.0)),
            _light("AREA", "LabFill", LAB, LABP + Vector((-2.0, -0.5, 1.8)), TABLE_C, 110, 2.0, (0.80, 0.90, 1.0)),
            _light("AREA", "LabBack", LAB, LABP + Vector((-1.6, 2.7, 2.4)), SKULL_C, 140, 1.0, (0.90, 0.97, 1.0))],
    "organ": [_light("AREA", "OKey", ORGS, OCW + Vector((0.5, -0.9, 0.6)), OCW, 30, 0.8, (1.0, 0.88, 0.78)),
              _light("AREA", "OFill", ORGS, OCW + Vector((-0.8, -0.7, 0.1)), OCW, 12, 1.0, (0.55, 0.70, 1.0)),
              _light("AREA", "ORim", ORGS, OCW + Vector((0.0, 0.7, 0.6)), OCW, 14, 0.6, (1.0, 0.6, 0.6))],
    "grid": [_light("AREA", "GKey", GRID, GC + Vector((0.8, -1.8, 1.8)), GC, 90, 1.5, (0.75, 0.88, 1.0)),
             _light("AREA", "GRim", GRID, GC + Vector((-0.6, 2.2, 1.0)), GC, 60, 1.0, (1.0, 0.7, 0.4))],
}
BASE = {l.name: l.data.energy for ls in LIGHTS.values() for l in ls}
for set_name, ls in LIGHTS.items():
    for l in ls:
        vals = []
        for i, t in enumerate(T):
            e = BASE[l.name] * (SET_OF[i] == set_name)
            if l.name == "OKey":
                e *= 1 + 1.5 * spike(TA[i], HIT_ACT + 0.03, 0.03, 0.3) if SLO_A <= t < SLO_B + 0.3 else 1
            vals.append(e)
        bake(l.data, "energy", vals)

# ---------------------------------------------------------------- cameras (v3: moving splines, DOF from subject size)
cams = S.Cameras(scene, T, F, CAST)


def span(name):
    i = next(k for k, s in enumerate(SHOTS) if s[1] == name)
    return SHOTS[i][0], (SHOTS[i + 1][0] if i + 1 < len(SHOTS) else DUR)


def Wo(p):                                     # organ-set world position of a rest-space point
    return ORGP + (Vector(p) - OC)


def Wh(p):                                     # home-set world position of a rest-space point (she stands on her mark)
    return P_HOME - OFF + Vector(p)


HW = Wo(HEART_REL)
AW = Wo(R(0, -0.01, 0.50))
TC = Wh(OC)                                    # torso centre, standing at home
FC = Wh(Vector((X0, him.nose.y, him.nose.z)))  # her face, standing at home
V = Vector

a, b = span("XThumb")
cams.cam("XThumb", a, b, keys=[(a, TC + V((0.30, -1.95, 0.34))), (b, TC + V((0.16, -1.45, 0.30)))], lens=42, aim=TC + V((0, 0, 0.10)),
         depth=0.7, shift_y=-0.04, shake=0.0010)
a, b = span("HomeWide")
cams.cam("HomeWide", a, b, keys=[(a, TC + V((1.8, -3.5, 0.15))), (b, TC + V((1.3, -3.0, 0.10)))], lens=28, aim=TC + V((-0.3, 0.6, 0.15)),
         depth=2.0, shift_y=0.02, shake=0.0010)
a, b = span("Photos")
PH = HOMEP + V((-1.27, 3.55, 1.66))
cams.cam("Photos", a, b, keys=[(a, PH + V((-1.2, -2.2, 0.05))), (b, PH + V((0.9, -2.0, 0.10)))], lens=50, aim=PH + V((0.2, 0, 0)),
         depth=0.5, shake=0.0010)
a, b = span("SwimMed")
cams.cam("SwimMed", a, b, keys=[(a, TC + V((-0.9, -2.6, 0.45))), (b, TC + V((-0.4, -2.2, 0.50)))], lens=35, aim=TC + V((0, 0, 0.30)),
         depth=0.9, shift_y=-0.02, shake=0.0010)
a, b = span("WindowSun")
cams.cam("WindowSun", a, b, keys=[(a, FC + V((-0.95, -1.45, 0.06))), (b, FC + V((-0.55, -1.00, 0.04)))], lens=50, aim=FC,
         focus=face_pt, depth=0.2, shift_y=-0.05, shake=0.0010)
a, b = span("LabTable")
cams.cam("LabTable", a, b, keys=[(a, TABLE_C + V((-1.6, -2.3, 0.45))), (b, TABLE_C + V((-1.0, -2.0, 0.55)))], lens=32, aim=TABLE_C + V((0.2, 0, 0.1)),
         depth=1.0, shake=0.0010)
a, b = span("LabTray")
cams.cam("LabTray", a, b, keys=[(a, TRAY_C + V((0.55, -0.75, 0.30))), (b, TRAY_C + V((0.20, -0.45, 0.14)))], lens=60, aim=TRAY_C + V((0, 0, 0.02)),
         depth=0.15, shake=0.0008)
a, b = span("HeartOrbit")
cams.cam("HeartOrbit", a, b, path=S.orbit(HW, 0.46, -38, 12, 0.05, 0.07), lens=40, aim=HW, depth=0.25, shake=0.0004)
a, b = span("VesselMacro")
VW = Wo(AORTA[2])
cams.cam("VesselMacro", a, b, keys=[(a, VW + V((0.16, -0.44, 0.07))), (b, VW + V((0.07, -0.30, 0.04)))], lens=60, aim=VW, depth=0.08, shake=0.0003)
a, b = span("SwapSlomo")
cams.cam("SwapSlomo", a, b, keys=[(a, AW + V((-0.10, -0.64, 0.10))), (b, AW + V((0.04, -0.46, 0.03)))], lens=38, aim=AW, depth=0.3,
         shake=0.0003, kicks=[(HIT, 0.008, 0.3)], ease="cine")
a, b = span("MirrorCU")
cams.cam("MirrorCU", a, b, path=S.orbit(AW, 0.62, 24, -14, 0.07, 0.12), lens=40, aim=AW, depth=0.3, shake=0.0004)
a, b = span("HeartBeat")
cams.cam("HeartBeat", a, b, keys=[(a, HW + V((-0.05, -0.34, 0.03))), (b, HW + V((0.03, -0.20, 0.02)))], lens=60, aim=HW, depth=0.1, shake=0.0003)
a, b = span("BodyXFull")
cams.cam("BodyXFull", a, b, keys=[(a, TC + V((-0.55, -2.5, 0.10))), (b, TC + V((-0.30, -2.0, 0.12)))], lens=42, aim=TC + V((0, 0, 0.05)),
         depth=0.7, shift_y=-0.04, shake=0.0008)
a, b = span("GridRise")
cams.cam("GridRise", a, b, keys=[(a, GRIDP + V((-1.4, -0.15, 0.07))), (b, GRIDP + V((-0.8, -0.9, 1.7)))], lens=32, aim=GRIDP + V((0.2, 2.4, 0.0)),
         depth=3.0, shake=0.0006, ease="cine")
a, b = span("OneAmber")
cams.cam("OneAmber", a, b, keys=[(a, GEM_P + V((0.55, -1.0, 0.55))), (b, GEM_P + V((0.20, -0.45, 0.14)))], lens=50, aim=GEM_P,
         depth=0.25, shake=0.0004, ease="cine")
a, b = span("HeartPulse")
cams.cam("HeartPulse", a, b, path=S.orbit(HW, 0.55, 30, -12, -0.08, 0.10), lens=45, aim=HW, depth=0.25, shake=0.0004)
a, b = span("HomeOrbit")
cams.cam("HomeOrbit", a, b, path=S.orbit(TC + V((0, 0, 0.35)), 1.9, -30, 12, 0.02, 0.0), lens=38, aim=TC + V((0, 0, 0.45)), focus=chest_pt,
         depth=0.8, shift_y=-0.03, shake=0.0008)
a, b = span("LabLamp")
LC = LABP + V((0.1, 1.5, 1.35))
cams.cam("LabLamp", a, b, path=S.orbit(LC, 2.3, -55, -18, 0.0, 0.5), lens=32, aim=LC + V((0, 0, 0.15)), depth=1.2, shake=0.0008)
a, b = span("Closer")
cams.cam("Closer", a, b, keys=[(a, TC + V((0.20, -1.75, 0.25))), (b, TC + V((0.05, -0.95, 0.20)))], lens=50, aim=TC + V((0, 0, 0.10)),
         depth=0.5, shift_y=-0.04, shake=0.0008, ease="cine")

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
