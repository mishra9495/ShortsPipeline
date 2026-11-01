"""titanium-heart-100-days: "This man lived over a hundred days with a titanium heart" (BiVACOR Total Artificial Heart:
implanted 22 Nov 2024 at St Vincent's Hospital Sydney, one moving part, a magnetically levitated rotor, no valves or
bearings to wear out, replaces both ventricles; first patient discharged with it (Feb 2025), donor heart in March 2025;
inventor Daniel Timms began after his father died of heart failure. Sources: CNN via KRDO 2025-03-12, ZME Science).

Run (daily_render.ps1): blender -b --python scene.py -- <ROOT>/blend/<slug>.blend vo=<wav> beats=<json> fps=30
Optional: stills=1,200 pct=100 samples=128 device=gpu|cpu root=<ROOT>

v3 toolkit: every model is built in Blender from code (scripts/kit.py), he acts procedurally on the mixamorig bones
(scripts/actor.py) and every camera is a moving spline that is already in motion on the cut (scripts/shot.py).
No captions, no on-screen text (owner's rule). Timing comes only from the beats JSON. SYNC constants must match mix.py.

Cast: him = blend/char_hero.blend. One actor. Sets: WARD, OR, EXIT (hospital doors), WORKSHOP (the inventor's bench,
props only), DEVICE (macro of the titanium heart, glass cutaway) and XRAY (his body as a glowing shell, the hearts inside).
Set changes are HARD CUTS.
"""
import json
import math
import os
import random
import sys
import warnings

import bpy
from mathutils import Euler, Vector

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
K.init(scene, seed=71)
random.seed(71)
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
SWAP = at(2, 0.72)                     # the failing heart lifts out, the titanium heart slides in
SLO_A, SLO_B = B[4], at(4, 0.80)       # slow-mo window: the rotor floating on its magnets (money moment)
ACT_A, ACT_B = SLO_A, SLO_A + (SLO_B - SLO_A) * 0.4
MAG = at(4, 0.18)                      # the magnet rings flare on
DOORS = at(6, 0.10)                    # the hospital doors slide open
COOLER_A, COOLER_B = B[7], at(7, 0.34)  # the donor-heart cooler rolls in
DONOR = at(7, 0.70)                    # the donor heart takes the titanium heart's place
print("TIMELINE", [round(b, 2) for b in B], "END", END, "SWAP", round(SWAP, 2), "DONOR", round(DONOR, 2))

S.setup_render(scene, fps=FPS, end=END, pct=PCT, samples=SAMPLES, device=DEVICE)
scene.cycles.adaptive_threshold = 0.015 if SAMPLES >= 96 else 0.03


def bake(idb, path, values, index=None, interp="LINEAR"):
    return A.bake(idb, path, values, FRAMES, index=index, interp=interp)


def bake_vec(idb, path, vecs, n=3, interp="LINEAR"):
    A.bake_vec(idb, path, vecs, FRAMES, n=n, interp=interp)


ramp, env, spike, smooth, wobble = A.ramp, A.env, A.spike, A.smooth, A.wobble
warp = A.timewarp(SLO_A, SLO_B, ACT_A, ACT_B)
TA = [warp(t) for t in T]                                    # action time (slow inside the money moment)


def glowy(name, color, rough=0.4, sss=0.3, emit=0.0, metallic=0.0):
    """Principled with its own (bakeable) base colour and emission, never shared through kit's cache."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Subsurface Weight"].default_value = sss
    b.inputs["Subsurface Scale"].default_value = 0.01
    b.inputs["Emission Color"].default_value = (*color, 1)
    b.inputs["Emission Strength"].default_value = emit
    return m


BSDF = 'nodes["Principled BSDF"].inputs'


def hidden_from_rays(o):
    o.visible_diffuse = o.visible_glossy = o.visible_transmission = False


# ---------------------------------------------------------------- measure his torso (rest pose, rig-local) to place organs
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
SH_L = him.bone_rest_head("LeftArm")
Z0 = REST_HIPS.z
TZ = max(0.4, SH_L.z - Z0)                                    # hips to shoulder joints
WX = max(0.10, 0.85 * abs(SH_L.x - him.x0))                   # torso half width
mid_ = []
for _hw in (0.05, 0.10, 0.20, 0.40):                          # widen the midline band until the mesh is found
    for _z0, _z1 in ((0.6, 0.9), (0.4, 1.0), (0.0, 1.2)):
        mid_ = [v for v in VERTS if abs(v.x - him.x0) < _hw and Z0 + _z0 * TZ < v.z < Z0 + _z1 * TZ]
        if len(mid_) >= 6:
            break
    if len(mid_) >= 6:
        break
if not mid_:
    print("TORSO WARN: no body vertices near the torso; using bone-based depth")
    mid_ = [Vector((him.x0, him.hips0.y - 0.10, Z0 + 0.7 * TZ)), Vector((him.x0, him.hips0.y + 0.10, Z0 + 0.7 * TZ))]
YF, YB = min(v.y for v in mid_), max(v.y for v in mid_)       # chest front / back
YC, DY = (YF + YB) / 2, max(0.06, (YB - YF) / 2)
X0 = him.x0
SC = TZ / 0.52                                                # 1.0 on an average adult torso
print("TORSO", "TZ", round(TZ, 3), "WX", round(WX, 3), "YC", round(YC, 3), "DY", round(DY, 3))


def R(dx, dy, tz):
    """Rest-space point: dx metres from the midline (+X = his LEFT), dy metres from the chest centre (-Y = front)."""
    return Vector((X0 + dx, YC + dy, Z0 + tz * TZ))


HEART = R(0.018 * SC, -0.30 * DY, 0.66)                       # heart centre: left of the midline, toward the front


# ---------------------------------------------------------------- the titanium heart (built once per set)
def build_device(c, name, glass_front, loc, scale=1.0, tint=(0.60, 0.58, 0.55), xray=False):
    """BiVACOR-style total artificial heart: a 70 mm titanium drum with ONE moving part, a rotor whose vanes push blood
    left (body) and right (lungs), held floating by magnet rings. Local Z = rotor axis (front); outlets point local +Y
    (up once the root is turned), inlets local -Z (back). Returns a dict of parts."""
    root = K.empty(name, c, loc, (math.radians(90), 0, 0))
    if xray:      # inside the dark X-ray void a real metal mirrors only black: a lit, faintly glowing titanium reads instead
        ti = glowy(name + "Ti", (0.80, 0.80, 0.83), rough=0.32, sss=0.0, emit=0.35, metallic=0.55)
        ti_hi = glowy(name + "TiPolish", (0.92, 0.92, 0.95), rough=0.2, sss=0.0, emit=0.6, metallic=0.5)
    else:
        ti = K.metal(name + "Ti", tint, 0.24, brushed=True)
        ti_hi = K.metal(name + "TiPolish", (0.78, 0.77, 0.74), 0.08)
    graft = K.fabric(name + "Graft", (0.90, 0.90, 0.86), rough=0.8, sheen=0.4, weave=900, bump=0.5)
    parts = [K.lathe(name + "Back", c, [(0.0, -0.025), (0.024, -0.025), (0.032, -0.021), (0.035, -0.013), (0.0355, 0.004)], (0, 0, 0), ti,
                     steps=64, thickness=0.0018)]
    front_prof = [(0.0355, 0.004), (0.0355, 0.011), (0.032, 0.017), (0.012, 0.0195), (0.0, 0.0195)]
    if glass_front:
        gl = K.plastic(name + "Clear", (0.92, 0.96, 1.0), 0.04, coat=0.6)
        gl.node_tree.nodes["Principled BSDF"].inputs["Transmission Weight"].default_value = 0.92
        gl.node_tree.nodes["Principled BSDF"].inputs["IOR"].default_value = 1.45
        front = K.lathe(name + "Front", c, front_prof, (0, 0, 0), gl, steps=64, thickness=0.0012)
        K.lathe(name + "Seam", c, [(0.0352, 0.0025), (0.0372, 0.004), (0.0352, 0.0055)], (0, 0, 0), ti_hi, steps=64)
    else:
        front = K.lathe(name + "Front", c, front_prof, (0, 0, 0), ti, steps=64, thickness=0.0018)
    parts.append(front)
    parts.append(K.lathe(name + "Band", c, [(0.0356, 0.0018), (0.0375, 0.0028), (0.0375, 0.0052), (0.0356, 0.0062)], (0, 0, 0), ti_hi, steps=64))
    for k in range(10):                                             # bolt heads round the seam (wear details)
        a = 2 * math.pi * k / 10
        parts.append(K.cyl(name + "Bolt", c, 0.0018, 0.0012, (0.0377 * math.cos(a), 0.0377 * math.sin(a), 0.004), ti_hi,
                           rot=(0, math.radians(90), a), verts=12))
    ports = {}
    for sx, key in ((-1, "inR"), (1, "inL")):                       # inflow cuffs at the back (atria)
        p = Vector((sx * 0.015, -0.004, -0.026))
        parts.append(K.cyl(name + "Inlet", c, 0.0085, 0.016, p + Vector((0, 0, -0.008)), ti, verts=32, bevel=0.0008))
        parts.append(K.lathe(name + "Cuff", c, [(0.0086, -0.034), (0.0115, -0.032), (0.0118, -0.026), (0.0086, -0.024)], (sx * 0.015, -0.004, 0), graft,
                             steps=32))
        ports[key] = p + Vector((0, 0, -0.03))
    for sx, key in ((1, "outL"), (-1, "outR")):                     # outflow grafts on top (aorta / pulmonary artery)
        p = Vector((sx * 0.016, 0.032, -0.004))
        parts.append(K.cyl(name + "Outlet", c, 0.0072, 0.016, p + Vector((0, 0.004, 0)), ti, rot=(math.radians(90), 0, 0), verts=32, bevel=0.0008))
        parts.append(K.tube(name + "Graft", c, [p + Vector((0, 0.011, 0)), p + Vector((sx * 0.003, 0.026, -0.002)),
                                                 p + Vector((sx * 0.010, 0.040, -0.008))], 0.0068, graft, res=8))
        ports[key] = p + Vector((sx * 0.010, 0.040, -0.008))
    rotor = K.empty(name + "Rotor", c, (0, 0, 0))
    rp = [K.cyl(name + "Disc", c, 0.0255, 0.0045, (0, 0, 0), ti_hi, verts=64, bevel=0.0007),
          K.cyl(name + "Hub", c, 0.0075, 0.013, (0, 0, 0), ti_hi, verts=32, bevel=0.0015)]
    for side in (-1, 1):                                            # swept vanes on both faces: left pump / right pump
        for k in range(7):
            a = 2 * math.pi * k / 7 + (0.2 if side > 0 else 0.0)
            r = 0.0155
            rp.append(K.rbox(name + "Vane", c, (0.017, 0.0024, 0.0042), (r * math.cos(a), r * math.sin(a), side * 0.0042), ti_hi,
                             bevel=0.0007, segments=2, rot=(0, 0, a + side * 0.45)))
    K.parent(rp, rotor)
    parts.append(rotor)
    mag_m = glowy(name + "Magnet", (0.25, 0.85, 1.0), rough=0.3, sss=0.0, emit=3.0)
    rings = []
    for z in (-0.0095, 0.0095):                                     # magnet bearing rings above and below the rotor rim
        rings.append(K.lathe(name + "MagRing", c, [(0.0262, z - 0.0011), (0.0300, z - 0.0011), (0.0300, z + 0.0011), (0.0262, z + 0.0011),
                                                   (0.0262, z - 0.0011)], (0, 0, 0), mag_m, steps=64, subsurf=0))
    parts += rings
    gap_m = glowy(name + "Gap", (0.4, 0.9, 1.0), rough=0.2, sss=0.0, emit=0.0)
    gap = K.lathe(name + "GapGlow", c, [(0.0258, -0.0006), (0.0264, 0.0), (0.0258, 0.0006), (0.0252, 0.0)], (0, 0, 0), gap_m, steps=64, subsurf=0)
    hidden_from_rays(gap)
    parts.append(gap)
    K.parent(parts, root)
    root.scale = (scale, scale, scale)
    return {"root": root, "rotor": rotor, "mag": mag_m, "gap": gap_m, "ports": ports, "parts": parts}


# ---------------------------------------------------------------- sets
WARDP, ORP, EXITP, WKP = Vector((0, 0, 0)), Vector((40, 0, 0)), Vector((80, 0, 0)), Vector((120, 0, 0))
DEVP = Vector((0, 0, -60))
FAR = Vector((0, 0, -200))
WARD, OR, EXIT, WK, DEV = K.coll("SetWard"), K.coll("SetOR"), K.coll("SetExit"), K.coll("SetWorkshop"), K.coll("SetDevice")

# WARD: a cardiac ward corner: bed, monitor, IV pole, privacy curtain, window. He stands beside the bed.
K.room(WARD, origin=WARDP + Vector((0, 0.8, 0)), size=(5.6, 5.0, 2.8), floor_mat=K.paint("WardFloor", (0.62, 0.66, 0.66), 0.3),
       wall_color=(0.80, 0.86, 0.86), name="WardRoom", openings=[(-1.6, 1.5, 1.44, 1.44)])
K.window(WARD, WARDP + Vector((-1.6, 3.37, 1.5)), size=(1.3, 1.3), curtains=False, sky=(0.85, 0.92, 1.0), sky_strength=3.2)
P_WARD = WARDP + Vector((-0.35, 0.45, 0))
BED = WARDP + Vector((0.75, 1.3, 0))
bed_st = K.metal("BedSteel", (0.80, 0.81, 0.84), 0.25, brushed=True)
sheet = K.fabric("BedSheet", (0.90, 0.93, 0.95), weave=700)
blanket = K.fabric("Blanket", (0.35, 0.55, 0.70), weave=500)
K.rbox("BedFrame", WARD, (0.95, 2.05, 0.08), BED + Vector((0, 0, 0.52)), bed_st, bevel=0.015)
K.cushion("Mattress", WARD, (0.9, 1.95, 0.16), BED + Vector((0, 0, 0.64)), sheet, puff=0.3)
K.cushion("Blanket", WARD, (0.94, 1.1, 0.05), BED + Vector((0, -0.35, 0.735)), blanket, puff=0.5, seed=3)
K.cushion("Pillow", WARD, (0.6, 0.38, 0.13), BED + Vector((0, 0.72, 0.79)), sheet, puff=0.8, seed=5)
for sy in (-0.95, 0.95):
    K.rbox("BedBoard", WARD, (0.95, 0.04, 0.45), BED + Vector((0, sy, 0.75)), K.plastic("BedBoardM", (0.82, 0.84, 0.86), 0.35), bevel=0.015)
    for sx in (-0.42, 0.42):
        K.cyl("BedLeg", WARD, 0.02, 0.48, BED + Vector((sx, sy * 0.93, 0.26)), bed_st, verts=12)
        K.sphere("BedWheel", WARD, 0.04, BED + Vector((sx, sy * 0.93, 0.04)), K.rubber("BedWheelM"), subdiv=2)
K.rbox("BedRail", WARD, (0.03, 0.9, 0.03), BED + Vector((-0.47, 0.25, 0.86)), bed_st, bevel=0.01)
K.vital_monitor(WARD, BED + Vector((0.75, 0.9, 1.45)), rot=math.radians(-25))
K.iv_pole(WARD, BED + Vector((-0.65, 1.0, 0)))
K._curtain("PrivacyCurtain", WARD, BED + Vector((1.25, -0.2, 1.3)), 1.5, 2.3, K.fabric("CurtainBlue", (0.42, 0.62, 0.72), weave=500))
K.potted_plant(WARD, WARDP + Vector((-2.4, 2.6, 0)), h=1.0, seed=6)
K.picture_frame(WARD, WARDP + Vector((0.2, 3.36, 1.65)), (0.7, 0.5), seed=9)

# OR: table, lamp, monitor, tray, IV pole. He lies on the table, head toward +Y.
K.room(OR, origin=ORP + Vector((0, 0.8, 0)), size=(6.0, 6.0, 3.0), floor_mat=K.paint("ORFloor", (0.52, 0.66, 0.64), 0.3),
       wall_color=(0.64, 0.78, 0.76), name="ORRoom")
TABLE = ORP + Vector((0, 0.9, 0))
K.or_table(OR, TABLE)
K.surgical_lamp(OR, ORP + Vector((0.1, 1.2, 2.35)))
K.vital_monitor(OR, ORP + Vector((1.1, 2.4, 1.45)), rot=math.radians(-30))
K.instrument_tray(OR, ORP + Vector((0.9, 0.2, 0.0)), rot=math.radians(20))
K.iv_pole(OR, ORP + Vector((-0.8, 2.0, 0.0)))
K.cushion("Drape", OR, (0.7, 1.1, 0.10), ORP + Vector((0, 0.35, 1.03)), K.fabric("Drape", (0.12, 0.40, 0.45), weave=300), puff=0.4)
# the donor-heart cooler on a steel trolley (rolls in during beat 8)
cooler = K.empty("CoolerTrolley", OR, ORP + Vector((-2.2, -0.2, 0)))
cst = K.metal("TrolleySteel", (0.80, 0.81, 0.84), 0.22, brushed=True)
cw = K.plastic("CoolerWhite", (0.93, 0.94, 0.95), 0.35, coat=0.2)
cb = K.plastic("CoolerBlue", (0.08, 0.30, 0.65), 0.3, coat=0.3)
cparts = [K.rbox("TrolleyTop", OR, (0.62, 0.44, 0.03), (0, 0, 0.84), cst, bevel=0.01),
          K.rbox("TrolleyShelf", OR, (0.62, 0.44, 0.02), (0, 0, 0.22), cst, bevel=0.008),
          K.rbox("CoolerBody", OR, (0.44, 0.32, 0.30), (0, 0, 1.005), cw, bevel=0.03),
          K.rbox("CoolerLid", OR, (0.46, 0.34, 0.05), (0, 0, 1.18), cb, bevel=0.02),
          K.tube("CoolerHandle", OR, [Vector((-0.12, 0, 1.205)), Vector((-0.08, 0, 1.26)), Vector((0.08, 0, 1.26)), Vector((0.12, 0, 1.205))], 0.009, cb)]
for sx in (-1, 1):
    cparts.append(K.rbox("CoolerLatch", OR, (0.02, 0.06, 0.05), (sx * 0.225, 0, 1.13), cb, bevel=0.006))
    for sy in (-1, 1):
        cparts.append(K.cyl("TrolleyLeg", OR, 0.013, 0.78, (sx * 0.28, sy * 0.19, 0.45), cst, verts=12))
        cparts.append(K.sphere("TrolleyWheel", OR, 0.035, (sx * 0.28, sy * 0.19, 0.036), K.rubber("TrolleyWheelM"), subdiv=2))
K.parent(cparts, cooler)
COOL_A, COOL_B = ORP + Vector((-1.40, -0.25, 0)), ORP + Vector((-0.78, -0.15, 0))

# EXIT: the hospital lobby, big glass doors in the back wall open onto a sunny forecourt with trees.
K.room(EXIT, origin=EXITP + Vector((0, 0.6, 0)), size=(6.4, 5.0, 3.0), floor_mat=K.paint("LobbyFloor", (0.78, 0.76, 0.72), 0.18),
       wall_color=(0.86, 0.84, 0.80), name="Lobby", openings=[(0.0, 1.27, 2.5, 2.52)])
DOOR_Y = EXITP.y + 0.6 + 2.5 + 0.06
K.rbox("LobbyFront", EXIT, (6.4, 0.12, 3.0), EXITP + Vector((0, 0.6 - 2.5 - 0.06, 1.5)), K.paint("LobbyFrontWall", (0.80, 0.78, 0.74)), bevel=0)
door_fr = K.metal("DoorFrame", (0.55, 0.57, 0.60), 0.3, brushed=True)
door_gl = K.glass("DoorGlass", (0.90, 0.96, 1.0), rough=0.02)
DOORS_L, DOORS_R = [], []
for sx, lst in ((-1, DOORS_L), (1, DOORS_R)):
    d = K.empty("DoorLeaf", EXIT, EXITP + Vector((sx * 0.6, DOOR_Y - 0.12, 0)))
    K.parent([K.rbox("DoorStileA", EXIT, (0.05, 0.05, 2.45), (-0.575, 0, 1.225), door_fr, bevel=0.008),
              K.rbox("DoorStileB", EXIT, (0.05, 0.05, 2.45), (0.575, 0, 1.225), door_fr, bevel=0.008),
              K.rbox("DoorRailT", EXIT, (1.2, 0.05, 0.06), (0, 0, 2.42), door_fr, bevel=0.008),
              K.rbox("DoorRailB", EXIT, (1.2, 0.05, 0.10), (0, 0, 0.05), door_fr, bevel=0.008),
              K.plane("DoorPane", EXIT, (1.12, 2.32), (0, 0, 1.23), door_gl, rot=(math.radians(90), 0, 0))], d)
    lst.append(d)
K.rbox("DoorHeader", EXIT, (2.7, 0.3, 0.18), EXITP + Vector((0, DOOR_Y - 0.15, 2.6)), door_fr, bevel=0.01)
out_ground = K.plane("Forecourt", EXIT, (40, 30), EXITP + Vector((0, DOOR_Y + 15, -0.002)), K.asphalt())
K.plane("Lawn", EXIT, (40, 12), EXITP + Vector((0, DOOR_Y + 10, 0.002)), K.grass())
for k, (tx, ty) in enumerate(((-4.0, 7.0), (3.5, 9.0), (-1.0, 12.0), (6.0, 6.0))):
    K.tree(EXIT, EXITP + Vector((tx, DOOR_Y + ty, 0)), h=6.0, seed=31 + k)
K.plane("SkyCard", EXIT, (60, 30), EXITP + Vector((0, DOOR_Y + 22, 10)), K.emissive("ForecourtSky", (0.80, 0.90, 1.0), 2.5), rot=(math.radians(90), 0, 0))
K.potted_plant(EXIT, EXITP + Vector((-2.2, 2.6, 0)), h=1.4, seed=12)
K.potted_plant(EXIT, EXITP + Vector((2.3, 2.6, 0)), h=1.2, seed=13)
bench_w = K.wood("BenchWood", (0.55, 0.36, 0.2), (0.3, 0.18, 0.08), rough=0.5)
K.rbox("LobbyBench", EXIT, (1.4, 0.45, 0.06), EXITP + Vector((-2.2, -0.6, 0.45)), bench_w, bevel=0.01)
for sx in (-0.6, 0.6):
    K.rbox("BenchLeg", EXIT, (0.05, 0.4, 0.42), EXITP + Vector((-2.2 + sx, -0.6, 0.21)), door_fr, bevel=0.008)
P_EXIT = EXITP + Vector((0.0, 1.35, 0))                           # he stands facing the doors (+Y)

# WORKSHOP: the inventor's bench (props only): pump prototypes, copper pipe, tools, a framed photo, a warm lamp.
K.room(WK, origin=WKP + Vector((0, 0.6, 0)), size=(5.0, 4.4, 2.7), floor_mat=K.paint("GarageFloor", (0.40, 0.40, 0.42), 0.6),
       wall_color=(0.42, 0.48, 0.52), name="Garage")
BENCH = WKP + Vector((0, 2.35, 0))
bwood = K.wood("WorkbenchTop", (0.62, 0.45, 0.28), (0.38, 0.25, 0.13), rough=0.55, scale=1.5)
K.rbox("WorkbenchTop", WK, (1.8, 0.7, 0.05), BENCH + Vector((0, 0, 0.9)), bwood, bevel=0.008)
for sx in (-0.85, 0.85):
    for sy in (-0.3, 0.3):
        K.rbox("BenchPost", WK, (0.07, 0.07, 0.88), BENCH + Vector((sx, sy, 0.44)), bwood, bevel=0.006)
K.rbox("Pegboard", WK, (1.8, 0.02, 0.9), BENCH + Vector((0, 0.37, 1.5)), K.paint("Pegboard", (0.62, 0.52, 0.38), 0.8), bevel=0.003)
TOP = BENCH.z + 0.925
copper = K.metal("Copper", (0.85, 0.45, 0.28), 0.3)
K.tube("CopperPipe", WK, [BENCH + Vector((-0.75, -0.05, 0.94)), BENCH + Vector((-0.45, -0.1, 0.94)), BENCH + Vector((-0.35, 0.05, 1.05)),
                          BENCH + Vector((-0.2, 0.15, 0.94))], 0.011, copper, res=8)
for k in range(3):                                                # old pump prototypes (brass housings, impellers)
    pc = BENCH + Vector((0.45 + 0.2 * k, 0.12, TOP + 0.04))
    K.lathe(f"Proto{k}", WK, [(0.0, -0.04), (0.04, -0.04), (0.045, -0.02), (0.045, 0.03), (0.02, 0.045), (0.0, 0.045)], pc,
            K.metal(f"Brass{k}", (0.78, 0.6, 0.3), 0.35), steps=32)
    K.cyl(f"ProtoPort{k}", WK, 0.012, 0.05, pc + Vector((0.05, 0, 0)), copper, rot=(0, math.radians(90), 0), verts=16)
wrench_m = K.metal("Wrench", (0.7, 0.7, 0.72), 0.3)
K.rbox("Wrench", WK, (0.2, 0.025, 0.008), BENCH + Vector((0.15, -0.22, TOP + 0.004)), wrench_m, bevel=0.003, rot=(0, 0, 0.4))
for k in range(5):
    K.cyl("PegTool", WK, 0.012, 0.22, BENCH + Vector((-0.6 + 0.3 * k, 0.33, 1.6)), K.plastic(f"ToolGrip{k}", ((0.7, 0.1, 0.1), (0.1, 0.3, 0.7), (0.9, 0.6, 0.1), (0.1, 0.1, 0.1), (0.2, 0.5, 0.2))[k], 0.4),
          verts=16)
PHOTO = BENCH + Vector((-0.55, 0.2, TOP + 0.13))
K.picture_frame(WK, PHOTO, (0.18, 0.24), name="DadPhoto", seed=4, rot=(math.radians(-12), 0, math.radians(18)))
K.cyl("LampBase", WK, 0.06, 0.02, BENCH + Vector((-0.8, 0.15, TOP + 0.01)), K.metal("LampBlack", (0.05, 0.05, 0.05), 0.4), verts=24)
K.tube("LampArm", WK, [BENCH + Vector((-0.8, 0.15, TOP)), BENCH + Vector((-0.78, 0.1, TOP + 0.35)), BENCH + Vector((-0.6, -0.02, TOP + 0.45))], 0.008,
       K.metal("LampBlack", (0.05, 0.05, 0.05), 0.4))
K.lathe("LampShade", WK, [(0.0, 0.0), (0.03, 0.0), (0.08, -0.09), (0.0, -0.06)], BENCH + Vector((-0.58, -0.04, TOP + 0.47)),
        K.metal("LampShadeM", (0.6, 0.15, 0.1), 0.4), rot=(math.radians(-25), math.radians(20), 0))
WKDEV = build_device(WK, "ProtoHeart", True, BENCH + Vector((0.0, -0.02, TOP + 0.06)), scale=1.6, tint=(0.70, 0.70, 0.72))
K.rbox("ProtoStand", WK, (0.09, 0.09, 0.012), BENCH + Vector((0.0, -0.02, TOP + 0.006)), wrench_m, bevel=0.003)

# DEVICE: the titanium heart alone in a deep-blue void, glass front so the floating rotor shows (artistic cutaway).
MDEV = build_device(DEV, "TiHeart", True, DEVP, scale=1.0)
DC = DEVP.copy()


def dev_local(d, p):
    """device-local point -> world (before any baked motion of the root)"""
    return d["root"].matrix_world @ Vector(p)


# blood in the macro: two streams spiral round the rotor, red to the body (left outlet), plum to the lungs (right)
BLOOD_BODY = glowy("BloodBody", (0.80, 0.05, 0.04), rough=0.25, sss=0.2, emit=1.6)
BLOOD_LUNG = glowy("BloodLung", (0.38, 0.06, 0.30), rough=0.25, sss=0.2, emit=1.6)
CELLS = []
for k in range(44):
    side = 1 if k % 2 else -1
    o = K.sphere(f"Cell{k}", DEV, 1.0, (0, 0, 0), BLOOD_BODY if side > 0 else BLOOD_LUNG, scale=(0.0016, 0.0016, 0.0011), subdiv=2)
    o.parent = MDEV["root"]
    CELLS.append((o, side, (k // 2) / 22.0, random.uniform(0.85, 1.15)))

# ---------------------------------------------------------------- X-ray anatomy (rig-local rest space, parented to Spine2)
ANAT = K.coll("Anatomy")
bone_m = K.bone_mat()
for k in range(8):                                                # rib cage, open at the front so the hearts show
    z = 0.86 - 0.055 * k
    rx = WX * (0.70 + 0.22 * math.sin(math.pi * min(1.0, (k + 1.5) / 7.5)))
    ry = DY * 0.88
    pts = [R(rx * math.cos(math.radians(a)), ry * math.sin(math.radians(a)) + 0.1 * DY, z - 0.02 * (1 - math.sin(math.radians(a))))
           for a in range(-25, 206, 20)]
    K.tube(f"Rib{k}", ANAT, pts, 0.0075 * SC, bone_m, res=6)
for k in range(13):
    K.sphere(f"Vertebra{k}", ANAT, 1.0, R(0, DY * 0.78, 0.92 - 0.06 * k), bone_m, scale=(0.022 * SC, 0.02 * SC, 0.017 * SC), subdiv=3)
K.tube("Clavicles", ANAT, [R(-WX * 0.8, -0.2 * DY, 0.97), R(0, -0.55 * DY, 0.93), R(WX * 0.8, -0.2 * DY, 0.97)], 0.007 * SC, bone_m)
lung_m = glowy("Lung", (0.92, 0.50, 0.55), rough=0.5, sss=0.4, emit=0.35)
LUNGS = [K.sphere(f"Lung{sx}", ANAT, 1.0, R(sx * WX * 0.60, 0.22 * DY, 0.68), lung_m, scale=(WX * 0.30, DY * 0.55, TZ * 0.22), subdiv=4) for sx in (-1, 1)]
vein_m = glowy("VenaCava", (0.20, 0.25, 0.75), rough=0.3, sss=0.2, emit=0.8)
aorta_m = glowy("Aorta", (0.85, 0.08, 0.06), rough=0.3, sss=0.2, emit=0.9)
pulm_m = glowy("PulmArtery", (0.45, 0.10, 0.45), rough=0.3, sss=0.2, emit=0.9)
AORTA = [HEART + Vector((0.012 * SC, 0.0, 0.05 * SC)), HEART + Vector((0.0, 0.01, 0.12 * SC)), HEART + Vector((-0.025 * SC, 0.04 * SC, 0.14 * SC)),
         HEART + Vector((-0.03 * SC, 0.08 * SC, 0.09 * SC)), R(0.0, DY * 0.55, 0.40), R(0.0, DY * 0.55, 0.12)]
PULM_L = [HEART + Vector((-0.012 * SC, -0.005, 0.05 * SC)), HEART + Vector((-0.01 * SC, 0.0, 0.10 * SC)), R(WX * 0.25, 0.05 * DY, 0.80), R(WX * 0.45, 0.1 * DY, 0.72)]
PULM_R = [HEART + Vector((-0.012 * SC, -0.005, 0.05 * SC)), HEART + Vector((-0.02 * SC, 0.0, 0.10 * SC)), R(-WX * 0.25, 0.05 * DY, 0.80), R(-WX * 0.45, 0.1 * DY, 0.72)]
K.tube("AortaX", ANAT, AORTA, 0.011 * SC, aorta_m, res=8)
K.tube("PulmLX", ANAT, PULM_L, 0.009 * SC, pulm_m, res=8)
K.tube("PulmRX", ANAT, PULM_R, 0.009 * SC, pulm_m, res=8)
K.tube("VenaCavaX", ANAT, [R(-0.02 * SC, 0.1 * DY, 0.98), HEART + Vector((-0.03 * SC, 0.03 * SC, 0.02 * SC)), R(-0.02 * SC, 0.25 * DY, 0.38)], 0.010 * SC, vein_m, res=8)
# the failing heart (dull, weak, irregular) and the donor heart (rosy, strong)
sick_m = glowy("SickHeart", (0.42, 0.10, 0.09), rough=0.45, sss=0.4, emit=0.25)
donor_m = glowy("DonorHeart", (0.85, 0.16, 0.13), rough=0.4, sss=0.4, emit=1.0)


def organic_heart(name, mat):
    root = K.empty(name, ANAT, HEART, (math.radians(-10), math.radians(-25), math.radians(-20)))
    s = SC
    parts = [K.sphere(name + "Vent", ANAT, 1.0, (0, 0, -0.008 * s), mat, scale=(0.048 * s, 0.040 * s, 0.056 * s), subdiv=4),
             K.sphere(name + "Apex", ANAT, 1.0, (0.012 * s, -0.004 * s, -0.045 * s), mat, scale=(0.028 * s, 0.026 * s, 0.03 * s), subdiv=3),
             K.sphere(name + "AtrL", ANAT, 1.0, (0.025 * s, 0.012 * s, 0.035 * s), mat, scale=(0.022 * s, 0.02 * s, 0.018 * s), subdiv=3),
             K.sphere(name + "AtrR", ANAT, 1.0, (-0.028 * s, 0.008 * s, 0.032 * s), mat, scale=(0.024 * s, 0.022 * s, 0.02 * s), subdiv=3)]
    vm = glowy(name + "Vessel", (0.9, 0.75, 0.3), rough=0.3, sss=0.0, emit=0.6)
    parts.append(K.tube(name + "Coronary", ANAT, [Vector((0.02 * s, -0.04 * s, 0.02 * s)), Vector((0.005 * s, -0.042 * s, -0.01 * s)),
                                                   Vector((0.012 * s, -0.03 * s, -0.05 * s))], 0.0018 * s, vm))
    K.parent(parts, root)
    return root


SICK = organic_heart("SickHeart", sick_m)
DONOR_H = organic_heart("DonorHeart", donor_m)
XDEV = build_device(ANAT, "XHeart", False, HEART, scale=SC * 1.45, xray=True)   # enlarged ~40% so it reads (artistic)
X_FLOW = []                                                       # blood dots streaming out of whichever heart is in
for k in range(30):
    path = (AORTA, PULM_L, PULM_R)[k % 3]
    o = K.sphere(f"Flow{k}", ANAT, 1.0, HEART, BLOOD_BODY if k % 3 == 0 else BLOOD_LUNG, scale=(0.004 * SC,) * 3, subdiv=2)
    X_FLOW.append((o, path, (k // 3) / 10.0))
xray_lights_anchor = HEART.copy()
XRAY_LIGHTS = []
for nm, off, en, sz, col in (("XKey", (0.5, -0.7, 0.4), 14, 0.8, (1.0, 0.92, 0.88)), ("XFill", (-0.6, -0.5, 0.0), 6, 1.0, (0.5, 0.7, 1.0)),
                             ("XRim", (0.0, 0.7, 0.5), 9, 0.6, (0.7, 0.85, 1.0))):
    d = bpy.data.lights.new(nm, "AREA")
    d.energy, d.size, d.color = en, sz, col
    lo = bpy.data.objects.new(nm, d)
    ANAT.objects.link(lo)
    lo.location = xray_lights_anchor + Vector(off)
    lo.rotation_euler = (-Vector(off)).to_track_quat("-Z", "Y").to_euler()
    XRAY_LIGHTS.append(lo)
for o in list(ANAT.objects):
    if o.parent is None:
        him.parent_to_bone(o, "Spine2")                            # basis = rig-local rest coordinates
# the controller bag at his left hip with the driveline into his belly (ward + exit only)
bag_m = K.fabric("BagFabric", (0.10, 0.12, 0.16), weave=500)
BAG = K.cushion("ControllerBag", CAST, (0.06, 0.16, 0.20), R(WX * 1.05, 0.0, 0.05), bag_m, puff=0.4)
STRAP = K.tube("BagStrap", CAST, [R(WX * 1.08, 0.0, 0.16), R(WX * 1.0, -0.35 * DY, 0.6), R(WX * 0.55, -0.9 * DY, 0.98), R(-WX * 0.4, -0.95 * DY, 1.0),
                                  R(-WX * 0.9, 0.0, 0.98)], 0.006, K.fabric("StrapFabric", (0.05, 0.05, 0.06), weave=800))
CABLE = K.tube("Driveline", CAST, [R(WX * 0.98, -0.5 * DY, 0.08), R(WX * 0.6, -1.08 * DY, 0.16), R(WX * 0.2, -1.1 * DY, 0.30)], 0.0035,
               K.plastic("DrivelineM", (0.9, 0.9, 0.88), 0.4))
for o in (BAG, STRAP, CABLE):
    him.parent_to_bone(o, "Spine")

# ---------------------------------------------------------------- X-ray look on his materials (driven by scene["xray"])
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

# ---------------------------------------------------------------- shots (start, camera, set, pose)
SHOTS = [
    (0.0, "HookX", "xray", "stand"),
    (at(0, 0.52), "HookFace", "ward", "stand"),
    (B[1], "WardWide", "ward", "stand"),
    (at(1, 0.50), "SickX", "xray", "stand"),
    (B[2], "ORWide", "or", "lie"),
    (at(2, 0.42), "SwapX", "xray", "stand"),
    (B[3], "DeviceOrbit", "device", "none"),
    (at(3, 0.50), "RotorMacro", "device", "none"),
    (SLO_A, "FloatSlomo", "device", "none"),
    (B[5], "FlowX", "xray", "stand"),
    (at(5, 0.50), "FlowMacro", "device", "none"),
    (B[6], "ExitWide", "exit", "exit"),
    (at(6, 0.50), "ExitFace", "exit", "exit"),
    (B[7], "CoolerCU", "or", "lie"),
    (at(7, 0.55), "DonorX", "xray", "stand"),
    (B[8], "WorkshopWide", "workshop", "none"),
    (at(8, 0.50), "ProtoMacro", "workshop", "none"),
    (B[9], "DeviceHero", "device", "none"),
    (at(9, 0.48), "CloserX", "xray", "stand"),
]


def shot_at(t):
    return max((s for s in SHOTS if s[0] <= t + 1e-6), key=lambda s: s[0])


SH = [shot_at(t) for t in T]
SET_OF = [s[2] for s in SH]
XRAY = [1.0 if s == "xray" else 0.0 for s in SET_OF]


def him_root(s, t):
    """(location, euler) of his rig object."""
    pose = s[3]
    if pose == "lie":                      # on his back on the OR table, head toward +Y, face up
        return Vector((TABLE.x - him.x0, TABLE.y - 0.92, 0.945 + 0.12)), (math.radians(-90), 0, 0)
    if pose == "none":
        return FAR, (0, 0, 0)
    if pose == "exit":
        rz, P = math.pi, P_EXIT
    else:
        rz, P = 0.0, P_WARD
    Rm = Euler((0, 0, rz), "XYZ").to_matrix()
    return P - Rm @ Vector((him.x0, REST_HIPS.y, 0)), (0, 0, rz)


# ---------------------------------------------------------------- performance
BLINKS = [1.1 + 3.0 * k for k in range(40) if 1.1 + 3.0 * k < DUR]


def channels(t):
    ch = {}
    ch["clutch"] = max(env(t, -1, 0, at(0, 0.9), B[1] + 0.2) * (1 if t >= at(0, 0.52) - 0.3 else 0.0),
                       env(t, B[1] - 0.1, B[1] + 0.3, B[2] - 0.2, B[2]))                    # hand on his failing heart
    ch["weak"] = env(t, B[1] - 0.1, B[1] + 0.3, B[2] - 0.1, B[2])                          # short of breath, slumped
    ch["gasp"] = sum(spike(t, B[1] + 0.35 + 0.95 * k, 0.15, 0.5) for k in range(3)) * ch["weak"]
    ch["wonder"] = env(t, at(0, 0.52), at(0, 0.62), B[1] - 0.1, B[1])                       # looks down at his chest
    ch["sedated"] = 1.0 if SH[F(t) - 1][3] == "lie" else 0.0
    ch["breathe"] = env(t, DOORS - 0.1, DOORS + 0.6, B[7] - 0.3, B[7])                      # deep breath of fresh air
    ch["smile"] = max(ramp(t, DOORS + 0.2, DOORS + 0.9) * (1 if B[6] <= t < B[7] else 0), 0.5 * ramp(t, B[9], B[9] + 0.5))
    ch["blink"] = max((env(t, b_ - 0.03, b_, b_ + 0.05, b_ + 0.12) for b_ in BLINKS), default=0.0)
    return ch


legs_stand = him.standing_legs()
SIDE_L = REST_HIPS + Vector((0.22, 0.02, -0.12))
SIDE_R = REST_HIPS + Vector((-0.22, 0.02, -0.12))
CLUTCH_R = Vector((X0 - 0.06 * SC, YF - 0.035, Z0 + 0.68 * TZ))   # IK goal is the WRIST; the palm then lies over his heart
LIE_L, LIE_R = REST_HIPS + Vector((0.24, -0.02, 0.0)), REST_HIPS + Vector((-0.24, -0.02, 0.0))
face_pt = him.anchor("Face", "Head", Vector((him.x0, him.nose.y + 0.05, him.nose.z - 0.01)), CAST)
eyes_mid = him.anchor("Eyes", "Head", (him.eye_l + him.eye_r) / 2, CAST)
heart_pt = him.anchor("HeartPt", "Spine2", HEART.copy(), CAST)
chest_pt = him.anchor("ChestPt", "Spine2", R(0, 0, 0.62), CAST)
hips_pt = him.anchor("HipsPt", "Hips", REST_HIPS.copy(), CAST)

for i, t in enumerate(T):
    s = SH[i]
    ch = channels(t)
    lie = s[3] == "lie"
    sed = ch["sedated"]
    br = math.sin(t * 2 * math.pi / (2.4 if ch["weak"] > 0.3 else 3.8))
    weak, gasp, wonder, brth = ch["weak"], ch["gasp"], ch["wonder"], ch["breathe"]
    spec = {
        "Hips": [(A.Z, 0.6 * wobble(t, 1) * (1 - sed))],
        "Spine": [(A.X, (0 if lie else 1.0) + 0.6 * br * (1 + weak) + 5 * weak - 3 * brth), (A.Z, 0.8 * wobble(t, 2) * (1 - sed))],
        "Spine1": [(A.X, 0.7 * br * (1 + weak) + 4 * weak + 2 * gasp - 3 * brth)],
        "Spine2": [(A.X, 1.5 + 0.8 * br * (1 + 1.5 * weak) - 2.5 * brth + 1.5 * gasp)],
        "Neck": [(A.X, 6 * wonder + 5 * weak - 4 * brth), (A.Z, 1.2 * wobble(t, 4) * (1 - sed))],
        "Head": [(A.X, 1.0 * wobble(t, 7, 0.6) * (1 - sed) + 12 * wonder + 6 * weak - 7 * brth - 3 * gasp),
                 (A.Z, 1.6 * wobble(t, 5, 0.5) * (1 - sed)),
                 (A.Y, 1.0 * wobble(t, 6) * (1 - sed) + 3 * weak)],
        "LeftShoulder": [(A.Y, 3 * gasp + 2 * brth)],
        "RightShoulder": [(A.Y, -3 * gasp - 2 * brth)],
    }
    rots = {}
    for bone, axes in spec.items():
        if him.has(bone):
            q = A.Quaternion()
            for axis, deg in axes:
                q = q @ him.q(bone, axis, deg)
            rots[bone] = q
    if lie:
        for bone in ("LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg", "LeftFoot", "RightFoot"):
            if him.has(bone):
                rots[bone] = A.Quaternion()
    else:
        rots.update(legs_stand)
    for bone in him.fingers():
        j = int(bone[-1])
        curl = ({1: 22, 2: 30, 3: 22} if "Thumb" not in bone else {1: 8, 2: 14, 3: 10})[j]
        if bone.startswith("Right"):
            curl -= 12 * ch["clutch"]                                  # flat palm on the chest
        rots[bone] = A.Quaternion((1, 0, 0), math.radians(curl))
    sh = {}
    for side in ("Left", "Right"):
        sh[f"eyeBlink{side}"] = min(1.0, ch["blink"] + sed + 0.25 * weak + 0.12 * ch["smile"])
        sh[f"eyeWide{side}"] = 0.45 * wonder * (1 - sed)
        sh[f"browDown{side}"] = 0.2 * weak
        sh[f"eyeSquint{side}"] = 0.3 * ch["smile"] + 0.2 * weak
        sh[f"mouthFrown{side}"] = 0.35 * weak
        sh[f"mouthSmile{side}"] = 0.8 * ch["smile"]
        sh[f"cheekSquint{side}"] = 0.4 * ch["smile"]
    sh["browInnerUp"] = 0.5 * wonder + 0.45 * weak + 0.3 * gasp
    sh["jawOpen"] = (0.18 * gasp + 0.12 * weak + 0.08 * wonder + 0.1 * brth) * (1 - sed)
    if lie:
        ikl, ikr = LIE_L, LIE_R
    else:
        ikl = SIDE_L + Vector((0, 0, 0.004 * br))
        ikr = (SIDE_R + Vector((0, 0, 0.004 * br))).lerp(CLUTCH_R + Vector((0, -0.006 * br, 0)), ch["clutch"])
    him.record(rots, sh, ikl, ikr, aim=(0.0, 0.0), follow={}, root=him_root(s, t))
him.bake(FRAMES)
for fc in A.fcurves_of(him.rig):
    if fc.data_path in ("location", "rotation_euler"):
        fc.keyframe_points.foreach_set("interpolation", [0] * len(fc.keyframe_points))   # teleports are cuts

# ---------------------------------------------------------------- the devices: rotor spin, float, magnet glow
SPIN = 1.15                                                        # visual revolutions per second (motion blur reads it)


def mag_level(t, ta):
    base = 0.55 + 0.15 * math.sin(2 * math.pi * 1.6 * ta)
    return base + 1.6 * ramp(t, MAG - 0.1, MAG + 0.25) * (1 if t < B[5] else 0.4) + 1.2 * spike(t, MAG, 0.03, 0.4)


for d, extra in ((MDEV, 0.0), (XDEV, 0.3), (WKDEV, 0.7)):
    bake(d["rotor"], "rotation_euler", [2 * math.pi * SPIN * TA[i] + extra for i in range(len(T))], index=2)
    bake(d["rotor"], "location", [0.0008 * math.sin(2 * math.pi * 0.9 * TA[i] + extra) * (1 if d is not WKDEV else 0.3) for i in range(len(T))], index=2)
    bake(d["mag"].node_tree, BSDF + '["Emission Strength"].default_value', [2.2 * mag_level(t, TA[i]) for i, t in enumerate(T)])
    bake(d["gap"].node_tree, BSDF + '["Emission Strength"].default_value',
         [6.0 * ramp(t, MAG, MAG + 0.4) * (1 if t < B[5] else 0.5) + 1.0 for t in T])
# the macro device turns slowly on its stand (a hero turntable), the prototype barely
bake(MDEV["root"], "rotation_euler", [0.30 * math.sin(0.35 * t) + 0.18 for t in T], index=2)


def cell_pos(side, u):
    """device-local path of a blood cell: in through a back inlet, 1.2 turns round the rotor, out of a top graft"""
    inlet = Vector((side * 0.015, -0.004, -0.06))
    cuff = Vector((side * 0.015, -0.004, -0.022))
    port = MDEV["ports"]["outL" if side > 0 else "outR"]
    z = side * 0.0055
    if u < 0.2:
        return inlet.lerp(cuff, u / 0.2)
    if u < 0.78:
        w = (u - 0.2) / 0.58
        a0 = math.atan2(cuff.y, cuff.x)
        a = a0 + 2 * math.pi * 1.2 * w
        r = 0.010 + 0.012 * min(1.0, w * 2.5)
        return Vector((r * math.cos(a), r * math.sin(a), cuff.z + (z - cuff.z) * min(1.0, w * 3)))
    w = (u - 0.78) / 0.22
    exit0 = Vector((side * 0.016, 0.026, -0.004))
    return exit0.lerp(port + Vector((side * 0.004, 0.012, -0.003)), w)


for o, side, ph, sz in CELLS:
    locs, scl = [], []
    for i, t in enumerate(T):
        u = (TA[i] * 0.42 * sz + ph) % 1.0
        locs.append(cell_pos(side, u))
        k = smooth(min(u, 1 - u) / 0.08)
        scl.append((0.0016 * k * sz, 0.0016 * k * sz, 0.0011 * k * sz))
    bake_vec(o, "location", locs)
    bake_vec(o, "scale", scl)

# ---------------------------------------------------------------- the X-ray hearts: failing -> titanium -> donor -> titanium (closer)
def dev_on(t):
    if t < B[1]:
        return 1.0
    if t < SWAP:
        return 0.0
    if t < DONOR:
        return smooth((t - SWAP) / 0.35)
    if t < B[9]:
        return 1.0 - smooth((t - DONOR) / 0.30)
    return 1.0


def sick_on(t):
    if B[1] <= t < SWAP:
        return 1.0 - smooth((t - (SWAP - 0.35)) / 0.35) if t > SWAP - 0.35 else 1.0
    return 0.0


def donor_on(t):
    if DONOR - 0.05 <= t < B[9]:
        return smooth((t - (DONOR - 0.05)) / 0.35)
    return 0.0


def sick_beat(t):
    # weak and irregular: small, uneven, with skipped beats
    ph = t * 1.35 + 0.25 * math.sin(t * 2.3)
    v = max(0.0, math.sin(2 * math.pi * ph)) ** 6
    return v * (0.5 + 0.5 * math.sin(t * 1.7) ** 2)


def donor_beat(t):
    ph = (t * 1.25) % 1.0
    return math.exp(-((ph - 0.08) / 0.05) ** 2) + 0.6 * math.exp(-((ph - 0.28) / 0.06) ** 2)


xd0 = XDEV["root"].scale.copy()
bake_vec(XDEV["root"], "scale", [tuple(c * max(0.001, dev_on(t)) for c in xd0) for t in T])
bake_vec(XDEV["root"], "location", [HEART + Vector((0, -0.12 * SC * (1 - dev_on(t)), 0)) for t in T])   # slides in from the front
for h, on_fn, beat_fn, amp in ((SICK, sick_on, sick_beat, 0.035), (DONOR_H, donor_on, donor_beat, 0.075)):
    vals, locs = [], []
    for t in T:
        k = on_fn(t)
        b = 1 + amp * beat_fn(t)
        vals.append((max(0.001, k * b),) * 3)
        lift = (1 - k) if h is SICK and t >= SWAP - 0.4 else 0.0
        locs.append(HEART + Vector((0, -0.14 * SC * lift, 0.05 * SC * lift)))
    bake_vec(h, "scale", vals)
    bake_vec(h, "location", locs)
bake(sick_m.node_tree, BSDF + '["Emission Strength"].default_value', [0.15 + 0.6 * sick_beat(t) for t in T])
bake(donor_m.node_tree, BSDF + '["Emission Strength"].default_value', [0.8 + 1.4 * donor_beat(t) for t in T])


def along(pts, u):
    u = max(0.0, min(1.0, u)) * (len(pts) - 1)
    i0 = min(int(u), len(pts) - 2)
    return pts[i0].lerp(pts[i0 + 1], u - i0)


def flow_rate(t):
    if B[1] <= t < SWAP:
        return 0.15                                                   # the failing heart barely moves blood
    return 0.55 if dev_on(t) > 0.5 else 0.45


acc, flow_ph = 0.0, []
for i, t in enumerate(T):
    acc += flow_rate(t) / FPS * (1.0 if not (SLO_A <= t < SLO_B) else 0.4)
    flow_ph.append(acc)
for o, path, ph in X_FLOW:
    locs, scl = [], []
    for i, t in enumerate(T):
        u = (flow_ph[i] + ph) % 1.0
        locs.append(along(path, u))
        k = smooth(min(u, 1 - u) / 0.1) * (0.4 if B[1] <= t < SWAP else 1.0)
        scl.append((0.004 * SC * k,) * 3)
    bake_vec(o, "location", locs)
    bake_vec(o, "scale", scl)
bake(lung_m.node_tree, BSDF + '["Emission Strength"].default_value', [0.35 + 0.25 * math.sin(t * 2 * math.pi / 3.8) for t in T])

# ---------------------------------------------------------------- props driven by time
bake(cooler, "location", [COOL_A.x + (COOL_B.x - COOL_A.x) * A.overshoot(t, COOLER_A, COOLER_B, 0.06) for t in T], index=0)
bake(cooler, "location", [COOL_A.y + (COOL_B.y - COOL_A.y) * smooth((t - COOLER_A) / (COOLER_B - COOLER_A)) for t in T], index=1)
for sx, lst in ((-1, DOORS_L), (1, DOORS_R)):
    d = lst[0]
    x0 = d.location.x
    bake(d, "location", [x0 + sx * 1.12 * smooth((t - DOORS) / 0.9) for t in T], index=0)

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


for name, coll in (("ward", WARD), ("or", OR), ("exit", EXIT), ("workshop", WK), ("device", DEV)):
    key_vis([o for o in coll.all_objects if not o.hide_render], lambda i, name=name: SET_OF[i] == name)
key_vis([o for o in ANAT.objects if not o.hide_render], lambda i: SET_OF[i] == "xray")
key_vis([o for o in him.objs], lambda i: SH[i][3] != "none")
key_vis([BAG, STRAP, CABLE], lambda i: SET_OF[i] == "exit")

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
WCOL = {"ward": ((0.66, 0.74, 0.80), 0.30), "or": ((0.60, 0.72, 0.72), 0.25), "exit": ((0.80, 0.88, 1.0), 0.6),
        "workshop": ((0.30, 0.24, 0.18), 0.18), "device": ((0.006, 0.014, 0.035), 1.0), "xray": ((0.003, 0.010, 0.026), 1.0)}
cols = [WCOL[s] for s in SET_OF]
bake_vec(wnt, 'nodes["Background"].inputs[0].default_value', [(*c_, 1) for c_, _ in cols], n=4, interp="CONSTANT")
bake(wnt, 'nodes["Background"].inputs[1].default_value', [s_ for _, s_ in cols], interp="CONSTANT")
CUTS = [s[0] for k, s in enumerate(SHOTS) if k and SHOTS[k - 1][2] != s[2]]
bake(scene, '["xray"]', XRAY, interp="CONSTANT")
bake(scene, "view_settings.exposure", [-0.30 + 0.7 * sum(spike(t, c, 0.005, 0.05) for c in CUTS) + 0.5 * spike(t, MAG, 0.02, 0.15)
                                       + 0.4 * spike(t, SWAP, 0.02, 0.12) + 0.4 * spike(t, DONOR, 0.02, 0.12) + 0.6 * spike(t, DOORS + 0.5, 0.25, 0.5)
                                       for t in T])


def _light(kind, name, coll, loc, target, energy, size, color):
    d = bpy.data.lights.new(name, kind)
    d.energy, d.color = energy, color
    if kind == "AREA":
        d.size = size
    elif kind == "SUN":
        d.angle = math.radians(size)
    else:
        d.shadow_soft_size = size
    o = bpy.data.objects.new(name, d)
    coll.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


HEAD_W = P_WARD + Vector((0, 0, 1.55))
HEAD_X = P_EXIT + Vector((0, 0, 1.55))
HEAD_OR = TABLE + Vector((0, 0.5, 1.10))
LIGHTS = {
    "ward": [_light("AREA", "WardKey", WARD, HEAD_W + Vector((1.3, -1.6, 1.0)), HEAD_W, 300, 1.4, (0.95, 0.97, 1.0)),
             _light("AREA", "WardFill", WARD, HEAD_W + Vector((-1.7, -1.3, 0.3)), HEAD_W, 90, 2.0, (0.82, 0.90, 1.0)),
             _light("AREA", "WardRim", WARD, HEAD_W + Vector((-0.6, 1.4, 0.9)), HEAD_W, 200, 0.8, (0.92, 0.95, 1.0)),
             _light("AREA", "WardWindow", WARD, WARDP + Vector((-1.6, 3.2, 1.6)), HEAD_W, 220, 1.3, (0.85, 0.92, 1.0))],
    "or": [_light("AREA", "ORTop", OR, HEAD_OR + Vector((0.1, -0.2, 1.2)), HEAD_OR + Vector((0, -0.5, 0)), 520, 1.0, (1.0, 0.99, 0.97)),
           _light("AREA", "ORFill", OR, TABLE + Vector((-1.8, -1.6, 2.0)), TABLE + Vector((0, 0, 1.0)), 200, 2.5, (0.85, 0.95, 1.0)),
           _light("AREA", "ORCooler", OR, COOL_B + Vector((0.6, -1.0, 1.9)), COOL_B + Vector((0, 0, 1.0)), 160, 1.0, (1.0, 0.97, 0.92))],
    "exit": [_light("SUN", "ExitSun", EXIT, P_EXIT + Vector((1.5, 6.0, 4.0)), P_EXIT + Vector((0, 0, 1.4)), 4.0, 2.0, (1.0, 0.92, 0.78)),
             _light("AREA", "ExitDoorGlow", EXIT, EXITP + Vector((0, DOOR_Y + 0.4, 1.6)), HEAD_X, 450, 2.4, (1.0, 0.95, 0.85)),
             _light("AREA", "ExitFill", EXIT, HEAD_X + Vector((-1.4, -1.6, 0.5)), HEAD_X, 120, 2.0, (0.85, 0.90, 1.0))],
    "workshop": [_light("POINT", "BenchLamp", WK, BENCH + Vector((-0.55, -0.08, TOP + 0.38)), BENCH + Vector((0, 0, TOP)), 60, 0.05, (1.0, 0.75, 0.45)),
                 _light("AREA", "WkKey", WK, BENCH + Vector((0.6, -1.2, TOP + 0.9)), BENCH + Vector((0, 0, TOP)), 120, 1.0, (1.0, 0.85, 0.65)),
                 _light("AREA", "WkFill", WK, BENCH + Vector((-1.2, -1.4, TOP + 0.5)), BENCH + Vector((0, 0, TOP)), 40, 2.0, (0.6, 0.72, 1.0))],
    "device": [_light("AREA", "DevKey", DEV, DC + Vector((0.25, -0.30, 0.22)), DC, 9, 0.35, (1.0, 0.95, 0.90)),
               _light("AREA", "DevFill", DEV, DC + Vector((-0.35, -0.25, 0.0)), DC, 3, 0.6, (0.55, 0.75, 1.0)),
               _light("AREA", "DevRim", DEV, DC + Vector((0.0, 0.30, 0.25)), DC, 7, 0.3, (0.6, 0.9, 1.0))],
}
BASE = {l.name: l.data.energy for ls in LIGHTS.values() for l in ls}
for set_name, ls in LIGHTS.items():
    for l in ls:
        vals = []
        for i, t in enumerate(T):
            e = BASE[l.name] * (SET_OF[i] == set_name)
            if l.name in ("ExitSun", "ExitDoorGlow"):
                e *= 0.35 + 0.65 * smooth((t - DOORS) / 0.9)              # the light floods in as the doors part
            elif l.name == "DevRim":
                e *= 1 + 1.2 * ramp(t, MAG, MAG + 0.3) * (1 if t < B[5] else 0.3)
            vals.append(e)
        bake(l.data, "energy", vals)
XBASE = {l.name: l.data.energy for l in XRAY_LIGHTS}
for l in XRAY_LIGHTS:
    bake(l.data, "energy", [XBASE[l.name] * XRAY[i] * (1 + 0.6 * spike(t, SWAP, 0.03, 0.3) + 0.6 * spike(t, DONOR, 0.03, 0.3)) for i, t in enumerate(T)])

# ---------------------------------------------------------------- cameras (v3: moving splines, DOF from subject size)
cams = S.Cameras(scene, T, F, CAST)


def span(name):
    i = next(k for k, s in enumerate(SHOTS) if s[1] == name)
    return SHOTS[i][0], (SHOTS[i + 1][0] if i + 1 < len(SHOTS) else DUR)


def mid(name):
    a, b = span(name)
    return (a + b) / 2


W = cams.world_at
DS = 0.0355 * SC * 1.05                                            # X-ray device radius in metres
# beat 1 HOOK (frame 1 = thumbnail): the titanium heart glowing and spinning inside his X-ray chest
a, b = span("HookX")
H0 = W(heart_pt, mid("HookX"))
cams.cam("HookX", a, b, keys=[(a, H0 + Vector((0.10, -0.40, 0.06))), (b, H0 + Vector((0.06, -0.29, 0.04)))], lens=50, aim=heart_pt,
         depth=0.12, shift_y=-0.04, shake=0.0004, ease="cine")
a, b = span("HookFace")
F0 = W(face_pt, mid("HookFace"))
cams.cam("HookFace", a, b, keys=[(a, F0 + Vector((0.30, -0.95, -0.05))), (b, F0 + Vector((0.20, -0.70, -0.04)))], lens=50, aim=face_pt, focus=eyes_mid,
         depth=0.18, shift_y=-0.07, shake=0.001)
# beat 2: failing heart, ward
a, b = span("WardWide")
C1 = W(chest_pt, mid("WardWide"))
cams.cam("WardWide", a, b, path=S.orbit(C1 + Vector((0.3, 0.3, 0.1)), 2.2, -28, -12, 0.25, 0.15), lens=32, aim=C1 + Vector((0.35, 0.3, 0.15)),
         focus=chest_pt, depth=1.2, shake=0.0008)
a, b = span("SickX")
H1 = W(heart_pt, mid("SickX"))
cams.cam("SickX", a, b, keys=[(a, H1 + Vector((-0.16, -0.56, 0.08))), (b, H1 + Vector((-0.10, -0.43, 0.05)))], lens=60, aim=heart_pt, depth=0.10, shake=0.0004)
# beat 3: the OR, then the swap in the X-ray
a, b = span("ORWide")
O0 = W(chest_pt, mid("ORWide"))
cams.cam("ORWide", a, b, keys=[(a, O0 + Vector((1.5, -1.4, 1.1))), (b, O0 + Vector((1.1, -1.0, 0.9)))], lens=30, aim=O0 + Vector((0, 0.2, 0.05)), focus=chest_pt,
         depth=0.8, shake=0.0006, plunge_out=(chest_pt, 0.30, 0.25))
a, b = span("SwapX")
H2 = W(heart_pt, mid("SwapX"))
cams.cam("SwapX", a, b, keys=[(a, H2 + Vector((0.20, -0.52, 0.10))), (SWAP, H2 + Vector((0.14, -0.45, 0.07))), (b, H2 + Vector((0.10, -0.39, 0.05)))], lens=50,
         aim=heart_pt, depth=0.12, shake=0.0004, kicks=[(SWAP, 0.004, 0.25)], plunge_in=(heart_pt, 0.25, 0.9))
# beat 4: the device itself
a, b = span("DeviceOrbit")
cams.cam("DeviceOrbit", a, b, path=S.orbit(DC, 0.30, -40, -10, 0.08, 0.04), lens=85, aim=DC, depth=0.07, shake=0.0)
a, b = span("RotorMacro")
cams.cam("RotorMacro", a, b, keys=[(a, DC + Vector((0.05, -0.20, 0.035))), (b, DC + Vector((0.03, -0.15, 0.02)))], lens=100, aim=DC + Vector((0.004, -0.01, 0.0)),
         depth=0.03, shake=0.0)
# beat 5 MONEY MOMENT: slow motion, the rotor floating between glowing magnet rings (edge-on so the gap reads)
a, b = span("FloatSlomo")
cams.cam("FloatSlomo", a, b, path=S.orbit(DC, 0.22, -60, -38, 0.05, 0.07, r1=0.17), lens=100, aim=DC + Vector((0, -0.005, 0.0)), depth=0.04,
         shake=0.0, ease="cine", kicks=[(MAG, 0.0015, 0.3)])
# beat 6: blood to body and lungs
a, b = span("FlowX")
C2 = W(chest_pt, mid("FlowX"))
cams.cam("FlowX", a, b, keys=[(a, C2 + Vector((-0.20, -0.74, 0.10))), (b, C2 + Vector((-0.12, -0.60, 0.06)))], lens=40, aim=C2 + Vector((0, 0, 0.05)),
         focus=heart_pt, depth=0.3, shake=0.0004)
a, b = span("FlowMacro")
cams.cam("FlowMacro", a, b, keys=[(a, DC + Vector((-0.12, -0.14, 0.10))), (b, DC + Vector((-0.08, -0.11, 0.075)))], lens=85, aim=DC + Vector((0, 0, 0.015)),
         depth=0.05, shake=0.0)
# beat 7: he walks out (the doors part, daylight floods in)
a, b = span("ExitWide")
X1 = W(chest_pt, mid("ExitWide"))
cams.cam("ExitWide", a, b, keys=[(a, X1 + Vector((-0.7, -2.4, 0.25))), (b, X1 + Vector((-0.45, -1.9, 0.15)))], lens=28, aim=X1 + Vector((0, 1.0, 0.25)),
         focus=chest_pt, depth=1.5, shake=0.0008)
a, b = span("ExitFace")
F6 = W(face_pt, mid("ExitFace"))
cams.cam("ExitFace", a, b, keys=[(a, F6 + Vector((-0.25, 0.95, -0.04))), (b, F6 + Vector((-0.15, 0.68, -0.03)))], lens=50, aim=face_pt, focus=eyes_mid,
         depth=0.18, shift_y=-0.07, shake=0.001)
# beat 8: the donor heart arrives
a, b = span("CoolerCU")
CB = COOL_B + Vector((0, 0, 1.08))
cams.cam("CoolerCU", a, b, keys=[(a, CB + Vector((0.55, -1.25, 0.25))), (b, CB + Vector((0.32, -0.90, 0.15)))], lens=40, aim=CB + Vector((-0.05, 0.1, 0)),
         focus=CB, depth=0.5, shake=0.0008)
a, b = span("DonorX")
H3 = W(heart_pt, mid("DonorX"))
cams.cam("DonorX", a, b, keys=[(a, H3 + Vector((-0.20, -0.52, 0.08))), (DONOR, H3 + Vector((-0.15, -0.45, 0.06))), (b, H3 + Vector((-0.10, -0.40, 0.04)))],
         lens=55, aim=heart_pt, depth=0.12, shake=0.0004, kicks=[(DONOR, 0.004, 0.25)])
# beat 9: the inventor's bench (props only)
a, b = span("WorkshopWide")
BW = BENCH + Vector((-0.2, 0.0, TOP + 0.15))
cams.cam("WorkshopWide", a, b, keys=[(a, BW + Vector((0.55, -1.35, 0.35))), (b, BW + Vector((0.25, -1.05, 0.25)))], lens=35, aim=BW, focus=PHOTO,
         depth=0.6, shake=0.0006)
a, b = span("ProtoMacro")
PD = WKDEV["root"].location.copy()
cams.cam("ProtoMacro", a, b, path=S.orbit(PD, 0.36, 20, -8, 0.06, 0.03), lens=85, aim=PD, depth=0.10, shake=0.0)
# beat 10: the device as a hero, then the loop back to frame 1
a, b = span("DeviceHero")
cams.cam("DeviceHero", a, b, path=S.orbit(DC, 0.27, 25, 8, -0.03, 0.01, r1=0.22), lens=85, aim=DC, depth=0.07, shake=0.0)
a, b = span("CloserX")
H9 = W(heart_pt, mid("CloserX"))
cams.cam("CloserX", a, b, keys=[(a, H9 + Vector((0.14, -0.50, 0.08))), (b, H9 + Vector((0.08, -0.32, 0.05)))], lens=50, aim=heart_pt, depth=0.12,
         shift_y=-0.04, shake=0.0003, ease="cine")

cams.markers(SHOTS)
S.check_shots(SHOTS, DUR)


def gaze_target(t):
    s = shot_at(t)
    if s[2] == "ward" and t < B[1]:
        return W(heart_pt, t) + Vector((0, -0.12, 0))
    if s[2] == "exit":
        return W(face_pt, t) + Vector((0.3, 3.0, 0.4))
    return None


him.bake_gaze(FRAMES, T, gaze_target, CAST, seed=29)

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
