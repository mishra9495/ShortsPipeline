"""frozen-heart-anna: "Her heart stopped for hours, and she lived." (Anna Bagenholm, 20 May 1999, Norway).
Sources: Gilbert M et al., "Resuscitation from accidental hypothermia of 13.7 C with circulatory arrest", The Lancet 2000;
355:375-6; Wikipedia "Anna Bagenholm"; ScienceAlert. 29-year-old skier trapped 80 min under 20 cm of ice, air pocket, about
40 min conscious before circulatory arrest, core temperature 13.7 C on arrival, heart-lung (cardiopulmonary bypass) rewarming,
heartbeat back after 2 h 35 min, woke 10 days later paralysed, recovered almost completely.

Run (daily_render.ps1): blender -b --python scene.py -- <ROOT>/blend/<slug>.blend vo=<wav> beats=<json> fps=30
Optional: stills=1,200 pct=100 samples=128 device=gpu|cpu root=<ROOT>

v3 toolkit: every model is built in Blender from code (scripts/kit.py), she acts procedurally on the mixamorig bones
(scripts/actor.py) and every camera is a moving spline that is already in motion on the cut (scripts/shot.py).
No captions, no on-screen text (owner's rule). Timing comes only from the beats JSON. SYNC constants must match mix.py.

Cast: her = blend/char_heroine.blend (female lead; never replaced by the male hero). One actor.
Sets: ICE (frozen stream, hole), UNDER (beneath the ice, air pocket), HEART (X-ray chest, heart that cools, stops, restarts),
THERMO (a giant thermometer), OR (operating room with a heart-lung machine), BRAIN (cold X-ray brain), HOME (sunny room).
Set changes are HARD CUTS.
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
K.init(scene, seed=83)
random.seed(83)
CAST = K.coll("Cast")
her = A.Actor.from_scene("Her")
her.measure()
her.setup_ik(CAST)
print("CAST", her.rig.name, "height", round(her.top, 3))

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

# SYNC with mix.py (beat index, fraction)
FALL_A, FALL_B = at(1, 0.50), at(1, 0.80)         # she goes through the ice
EYES = at(3, 0.22)                                # under the ice her eyes close
HS0, HS1 = at(3, 0.40), at(3, 0.85)               # heart slows (HS0) and stops (HS1)
TEMP_A, TEMP_B = B[4], at(4, 0.85)                # thermometer falls 37 -> 13.7
SLO_A, SLO_B = B[6], at(6, 0.60)                  # slow-motion window: the heart restarts (money moment)
ACT_A, ACT_B = SLO_A, SLO_A + (SLO_B - SLO_A) * 0.4
HIT_F = 0.40
HIT = SLO_A + HIT_F * (SLO_B - SLO_A)             # screen time of the restart
HIT_ACT = ACT_A + HIT_F * (ACT_B - ACT_A)         # the same moment in action time
WAKE = at(8, 0.30)                                # her eyes open
SMILE = at(9, 0.50)
BEAT_GAP = 0.85                                   # seconds between heartbeats after the restart
print("TIMELINE", [round(b, 2) for b in B], "END", END, "HIT", round(HIT, 2))

S.setup_render(scene, fps=FPS, end=END, pct=PCT, samples=SAMPLES, device=DEVICE)
scene.cycles.adaptive_threshold = 0.015 if SAMPLES >= 96 else 0.03


def bake(idb, path, values, index=None, interp="LINEAR"):
    return A.bake(idb, path, values, FRAMES, index=index, interp=interp)


def bake_vec(idb, path, vecs, n=3, interp="LINEAR"):
    A.bake_vec(idb, path, vecs, FRAMES, n=n, interp=interp)


ramp, env, spike, smooth, wobble = A.ramp, A.env, A.spike, A.smooth, A.wobble
warp = A.timewarp(SLO_A, SLO_B, ACT_A, ACT_B)
BSDF = 'nodes["Principled BSDF"].inputs'


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


def cone(name, c, r, h, loc, mat, verts=9):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=r, radius2=0.0, depth=h)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    o.location = loc
    return K._finish(o, c, mat)


def along(pts, u):
    u = max(0.0, min(1.0, u)) * (len(pts) - 1)
    i0 = min(int(u), len(pts) - 2)
    return pts[i0].lerp(pts[i0 + 1], u - i0)


# ---------------------------------------------------------------- sets
HOMEP, ICEP, UNP, ORP, THP = (Vector((0, 0, 0)), Vector((40, 0, 0)), Vector((80, 0, 0)), Vector((120, 0, 0)), Vector((160, 0, 0)))
HEARTP, BRAINP = Vector((0, 0, -60)), Vector((0, 0, -120))
HOME, ICE, UNDER, OR, THERMO, HEART, BRAIN = (K.coll("SetHome"), K.coll("SetIce"), K.coll("SetUnder"), K.coll("SetOR"),
                                              K.coll("SetThermo"), K.coll("SetHeart"), K.coll("SetBrain"))

# HOME: a sunny living room, window on the right, photo frames on the back wall.
K.room(HOME, origin=HOMEP + Vector((0, 1.0, 0)), size=(6.0, 5.2, 2.8), floor_mat=K.floorboards(),
       wall_color=(0.88, 0.80, 0.68), name="HomeRoom", openings=[(1.9, 1.5, 1.44, 1.44)])
K.window(HOME, HOMEP + Vector((1.9, 3.57, 1.5)), size=(1.3, 1.3), curtains=True, sky=(1.0, 0.93, 0.78), sky_strength=4.0)
P_HOME = HOMEP + Vector((-0.6, 1.2, 0))
for k in range(5):
    K.picture_frame(HOME, HOMEP + Vector((-2.4 + 0.5 * k, 3.55, 1.62 + 0.05 * (k % 2))), (0.30, 0.38), name=f"Pic{k}", seed=31 + k)
K.rug(HOME, P_HOME + Vector((0.3, 0.2, 0.0)), size=(2.8, 2.0), name="HomeRug")
K.floor_lamp(HOME, HOMEP + Vector((2.9, 2.6, 0)))
K.potted_plant(HOME, HOMEP + Vector((-2.7, 0.2, 0)), h=1.3, seed=4)
K.sofa(HOME, HOMEP + Vector((0.6, 3.0, 0)), width=1.9)
K.mug(HOME, HOMEP + Vector((1.2, 0.2, 0.0)), color=(0.9, 0.9, 0.92))

# ICE: a frozen Norwegian stream between snowy banks, pines and mountains. A hole waits in the ice.
snow_m = K.paint("Snow", (0.93, 0.96, 1.0), rough=0.55)
ice_m = glowy("IceTop", (0.62, 0.80, 0.92), rough=0.10, sss=0.0, emit=0.0)
water_m = glowy("HoleWater", (0.01, 0.05, 0.10), rough=0.05, sss=0.0, emit=0.5)
HX0, HX1, HY = -3.0, -0.5, 0.9                                    # the hole (relative to the skier's start mark)
slabs = [((-12.0, 8.0), (-6.0, -HY)), ((-12.0, 8.0), (HY, 6.0)), ((-12.0, HX0), (-HY, HY)), ((HX1, 8.0), (-HY, HY))]
for k, ((x0, x1), (y0, y1)) in enumerate(slabs):
    K.rbox(f"IceSlab{k}", ICE, (x1 - x0, y1 - y0, 0.22), ICEP + Vector(((x0 + x1) / 2, (y0 + y1) / 2, -0.11)), ice_m, bevel=0.012)
K.plane("HoleWater", ICE, (HX1 - HX0 - 0.02, 2 * HY - 0.02), ICEP + Vector(((HX0 + HX1) / 2, 0, -0.10)), water_m)
for k, (cx, cy, sz, rz_) in enumerate(((-1.0, 0.55, 0.32, 0.4), (-2.2, -0.4, 0.40, -0.5), (-1.8, 0.2, 0.22, 1.2), (-2.6, 0.55, 0.26, 0.2))):
    K.rbox(f"IceChunk{k}", ICE, (sz, sz * 0.7, 0.10), ICEP + Vector((cx, cy, -0.075)), ice_m, bevel=0.015, rot=(0.05, 0.04, rz_))
for sy in (-1, 1):
    K.rbox(f"Bank{sy}", ICE, (30.0, 12.0, 0.9), ICEP + Vector((-2, sy * 12.0, 0.15)), snow_m, bevel=0.3, subsurf=1)
K.plane("SnowFar", ICE, (400.0, 300.0), ICEP + Vector((0, 40, -0.02)), snow_m)
rock_m = K.paint("Rock", (0.34, 0.36, 0.42), rough=0.9)
pine_m = K.paint("Pine", (0.07, 0.20, 0.12), rough=0.9)
trunk_m = K.paint("Trunk", (0.16, 0.10, 0.06), rough=0.9)
for k in range(46):
    rr = random.Random(100 + k)
    px, py = rr.uniform(-22, 22), rr.choice((-1, 1)) * rr.uniform(8.0, 26.0)
    ph = rr.uniform(3.0, 6.0)
    K.cyl(f"Trunk{k}", ICE, 0.12, 0.8, ICEP + Vector((px, py, 0.9)), trunk_m, verts=8)
    for lv in range(3):
        cone(f"Pine{k}_{lv}", ICE, ph * (0.20 - 0.04 * lv), ph * 0.42, ICEP + Vector((px, py, 1.1 + ph * (0.22 + 0.2 * lv))), pine_m)
    cone(f"PineSnow{k}", ICE, ph * 0.09, ph * 0.18, ICEP + Vector((px, py, 1.1 + ph * 0.86)), snow_m, verts=7)
for k in range(9):
    rr = random.Random(200 + k)
    mxp, mh = -70 + 17 * k, rr.uniform(26, 46)
    cone(f"Mountain{k}", ICE, mh * 0.8, mh, ICEP + Vector((mxp, 75 + rr.uniform(-8, 10), mh / 2 - 1)), rock_m, verts=7)
    cone(f"MountainCap{k}", ICE, mh * 0.8 * 0.38, mh * 0.38, ICEP + Vector((mxp, 75 + rr.uniform(-8, 10) * 0, mh * 0.81 - 1)), snow_m, verts=7)
# skis and poles planted in the snow near the hole
ski_m = K.plastic("Ski", (0.9, 0.12, 0.10), 0.35, coat=0.4)
pole_m = K.metal("Pole", (0.1, 0.1, 0.12), 0.3)
for k, sy in enumerate((-0.12, 0.12)):
    K.rbox(f"Ski{k}", ICE, (1.5, 0.09, 0.02), ICEP + Vector((2.0, 1.4 + sy, 0.03)), ski_m, bevel=0.01, rot=(0, 0, 0.18))
    K.tube(f"SkiPole{k}", ICE, [ICEP + Vector((1.2 + 0.2 * k, 2.4 + 0.2 * sy, 1.2)), ICEP + Vector((1.1 + 0.2 * k, 2.35, 0.0))], 0.012, pole_m)
P_ICE = ICEP + Vector((0.0, 0.0, 0.0))

# UNDER: the underside of the ice sheet, a bright hole she fell through, an air pocket against the ceiling.
under_ice_m = glowy("IceUnder", (0.55, 0.80, 0.95), rough=0.2, sss=0.0, emit=0.9)
CX0, CX1, CY = 1.4, 2.7, 0.8                                       # the entry hole in the ceiling
for k, ((x0, x1), (y0, y1)) in enumerate((((-25.0, 25.0), (-25.0, -CY)), ((-25.0, 25.0), (CY, 25.0)), ((-25.0, CX0), (-CY, CY)), ((CX1, 25.0), (-CY, CY)))):
    K.rbox(f"Ceiling{k}", UNDER, (x1 - x0, y1 - y0, 0.3), UNP + Vector(((x0 + x1) / 2, (y0 + y1) / 2, 0.15)), under_ice_m, bevel=0.01)
sky_m = glowy("SkyHole", (0.85, 0.95, 1.0), rough=0.5, sss=0.0, emit=9.0)
K.plane("SkyHole", UNDER, (CX1 - CX0, 2 * CY), UNP + Vector(((CX0 + CX1) / 2, 0, 0.9)), sky_m)
crack_m = glowy("Crack", (0.85, 0.97, 1.0), rough=0.3, sss=0.0, emit=2.2)
for k in range(30):
    rr = random.Random(300 + k)
    p = Vector((rr.uniform(-5, 6), rr.uniform(-4, 4), -0.004))
    pts = [p.copy()]
    ang = rr.uniform(0, 6.28)
    for _ in range(5):
        ang += rr.uniform(-0.8, 0.8)
        p = p + Vector((math.cos(ang), math.sin(ang), 0)) * rr.uniform(0.25, 0.7)
        pts.append(p.copy())
    K.tube(f"Crack{k}", UNDER, [UNP + q for q in pts], 0.004, crack_m, res=3)
mote_m = glowy("Mote", (0.7, 0.9, 1.0), rough=0.3, sss=0.0, emit=3.0)
for k in range(70):
    rr = random.Random(400 + k)
    K.sphere(f"Mote{k}", UNDER, rr.uniform(0.006, 0.016), UNP + Vector((rr.uniform(-3, 5), rr.uniform(-3, 3), rr.uniform(-2.2, -0.15))), mote_m, subdiv=2)
K.plane("DeepFloor", UNDER, (80.0, 80.0), UNP + Vector((0, 0, -6.0)), K.paint("Deep", (0.01, 0.05, 0.09), rough=0.9))
P_UN = UNP + Vector((0.8, 0.0, -0.40))                            # her feet mark (head toward -X)
pocket_m = glowy("AirPocket", (0.85, 0.95, 1.0), rough=0.05, sss=0.0, emit=1.6)
bubble_m = glowy("Bubble", (0.85, 0.95, 1.0), rough=0.05, sss=0.0, emit=3.0)

# OR: operating room, table, lamp, monitor and a heart-lung machine joined to her by two tubes.
K.room(OR, origin=ORP + Vector((0, 0.6, 0)), size=(6.0, 5.2, 2.8), floor_mat=K.paint("ORFloor", (0.55, 0.62, 0.64), rough=0.25),
       wall_color=(0.66, 0.82, 0.80), name="ORRoom")
K.or_table(OR, ORP)
K.surgical_lamp(OR, ORP + Vector((0.0, 0.1, 2.5)))
MON = ORP + Vector((-0.55, 1.45, 1.65))
K.vital_monitor(OR, MON)
K.instrument_tray(OR, ORP + Vector((-1.3, 0.2, 0)), rot=0.4)
K.iv_pole(OR, ORP + Vector((-0.9, 1.2, 0)))
MP = ORP + Vector((1.75, 0.25, 0))
mach_m = K.plastic("MachineShell", (0.86, 0.88, 0.90), 0.3)
K.rbox("MachineBody", OR, (0.62, 0.55, 1.0), MP + Vector((0, 0, 0.6)), mach_m, bevel=0.03)
K.rbox("MachineTop", OR, (0.66, 0.60, 0.04), MP + Vector((0, 0, 1.12)), K.metal("MachineTopM", (0.7, 0.72, 0.75), 0.3), bevel=0.01)
for sx in (-1, 1):
    for sy in (-1, 1):
        K.cyl("Caster", OR, 0.04, 0.05, MP + Vector((sx * 0.25, sy * 0.2, 0.04)), K.rubber(), verts=12)
K.rbox("MachineScreen", OR, (0.30, 0.01, 0.16), MP + Vector((0, -0.285, 0.78)), glowy("MScreen", (0.2, 1.0, 0.5), rough=0.3, sss=0.0, emit=3.0), bevel=0.003)
res_m = glowy("Reservoir", (0.35, 0.02, 0.04), rough=0.1, sss=0.0, emit=0.5)
oxy_m = glowy("Oxygenator", (0.7, 0.04, 0.04), rough=0.1, sss=0.0, emit=0.7)
RES = K.cyl("Reservoir", OR, 0.085, 0.36, MP + Vector((-0.17, -0.12, 1.32)), res_m, verts=32)
OXY = K.cyl("Oxygenator", OR, 0.10, 0.40, MP + Vector((0.15, -0.12, 1.34)), oxy_m, verts=32)
coil_m = glowy("WarmCoil", (1.0, 0.45, 0.10), rough=0.3, sss=0.0, emit=0.0)
COILP = [MP + Vector((0.15 + 0.07 * math.cos(a * 0.9), -0.12 + 0.07 * math.sin(a * 0.9), 1.18 + 0.032 * a)) for a in range(0, 14)]
K.tube("WarmCoil", OR, COILP, 0.007, coil_m, res=5)
roller_parts = [K.cyl("PumpHead", OR, 0.13, 0.04, Vector((0, 0, 0)), K.metal("PumpM", (0.55, 0.57, 0.6), 0.3), verts=32)]
for k in range(3):
    a_ = 2 * math.pi * k / 3
    roller_parts.append(K.cyl(f"Roller{k}", OR, 0.025, 0.05, Vector((0.09 * math.cos(a_), 0.09 * math.sin(a_), 0.03)),
                              K.metal("RollerM", (0.9, 0.9, 0.92), 0.2), verts=16))
PUMP = K.empty("Pump", OR, MP + Vector((0, 0.12, 1.16)))
K.parent(roller_parts, PUMP)
ven_m = K.plastic("VenousLine", (0.20, 0.03, 0.07), 0.15)
art_m = K.plastic("ArterialLine", (0.85, 0.06, 0.05), 0.15)
VEN = [ORP + Vector((0.10, -0.40, 1.24)), ORP + Vector((0.50, -0.55, 1.05)), ORP + Vector((1.05, -0.40, 0.98)),
       MP + Vector((-0.40, -0.22, 1.10)), MP + Vector((-0.17, -0.12, 1.18))]
ART = [MP + Vector((0.15, -0.12, 1.14)), MP + Vector((0.45, -0.34, 1.02)), ORP + Vector((0.95, -0.80, 0.90)),
       ORP + Vector((0.45, -0.72, 1.02)), ORP + Vector((-0.10, -0.40, 1.24))]
K.tube("VenousLine", OR, VEN, 0.016, ven_m, res=8)
K.tube("ArterialLine", OR, ART, 0.016, art_m, res=8)
bead_ven = glowy("BeadVen", (0.30, 0.03, 0.08), rough=0.2, sss=0.0, emit=1.2)
bead_art = glowy("BeadArt", (1.0, 0.10, 0.06), rough=0.2, sss=0.0, emit=3.0)
NB = 9
BEADS = [(K.sphere(f"BeadV{k}", OR, 0.011, VEN[0], bead_ven, subdiv=2), VEN, k / NB) for k in range(NB)] + \
        [(K.sphere(f"BeadA{k}", OR, 0.011, ART[0], bead_art, subdiv=2), ART, k / NB) for k in range(NB)]
P_OR = ORP + Vector((0.0, -0.85, 0.98))                          # her feet mark on the table (head toward +Y)
sheet_m = K.fabric("Sheet", (0.85, 0.92, 0.90), weave=700)
SHEET = K.cushion("Sheet", OR, (0.80, 1.10, 0.05), ORP + Vector((0, -0.38, 1.20)), sheet_m, puff=0.35)

# THERMO: a giant glowing thermometer on a dark ground (37 C at the top mark, 13.7 C where she ended).
glass_m = xglow("ThermoGlass", (0.6, 0.85, 1.0), 2.0, blend=0.4, core=0.0)
THG = K.cyl("ThermoTube", THERMO, 0.075, 3.4, THP + Vector((0, 0, 0.0)), glass_m, verts=40)
hidden_from_rays(THG)
BULB = K.sphere("ThermoBulb", THERMO, 0.16, THP + Vector((0, 0, -1.7)), glass_m, subdiv=4)
hidden_from_rays(BULB)
fill_m = glowy("ThermoFill", (0.9, 0.08, 0.05), rough=0.2, sss=0.0, emit=4.0)
ZLO, ZHI = -1.5, 1.5                                             # temperature 10 .. 40 C maps to this z range


def tz(temp):
    return THP.z + ZLO + (temp - 10.0) / 30.0 * (ZHI - ZLO)


FILL = K.cyl("ThermoFill", THERMO, 0.05, 1.0, THP + Vector((0, 0, 0)), fill_m, verts=32)
FILL_BULB = K.sphere("ThermoFillBulb", THERMO, 0.12, THP + Vector((0, 0, -1.7)), fill_m, subdiv=4)
tick_m = glowy("Tick", (0.8, 0.9, 1.0), rough=0.4, sss=0.0, emit=3.0)
for tmp in range(10, 41, 5):
    K.rbox(f"Tick{tmp}", THERMO, (0.20 if tmp % 10 == 0 else 0.12, 0.012, 0.012), Vector((THP.x + 0.16, THP.y - 0.06, tz(tmp))), tick_m, bevel=0.002)
norm_m = glowy("Norm37", (0.2, 1.0, 0.45), rough=0.4, sss=0.0, emit=7.0)
K.rbox("Norm37", THERMO, (0.5, 0.02, 0.025), Vector((THP.x + 0.0, THP.y - 0.08, tz(37.0))), norm_m, bevel=0.004)
goal_m = glowy("Goal13", (0.5, 0.9, 1.0), rough=0.3, sss=0.0, emit=0.0)
GOAL = K.lathe("Goal13", THERMO, [(0.13, 0.0), (0.16, 0.0)], Vector((THP.x, THP.y, tz(13.7))), goal_m, steps=48, thickness=0.02)
TOP_PT = K.empty("FillTop", THERMO, Vector((THP.x, THP.y, tz(37.0))))
SPK = []
rngt = random.Random(5)
for k in range(60):
    SPK.append(K.sphere(f"Frost{k}", THERMO, rngt.uniform(0.006, 0.014), THP + Vector((rngt.uniform(-1.4, 1.4), rngt.uniform(-0.8, 0.8), rngt.uniform(-1.8, 1.8))), mote_m, subdiv=2))
K.plane("ThermoBack", THERMO, (30.0, 30.0), THP + Vector((0, 3.0, 0)), K.paint("ThermoBack", (0.02, 0.03, 0.06), rough=0.9), rot=(math.radians(90), 0, 0))

# HEART: an X-ray rib cage with a heart that cools, stops and restarts.
bone_m = K.bone_mat()
lung_m = glowy("Lung", (0.92, 0.50, 0.55), rough=0.5, sss=0.4, emit=0.5)
LUNGS = [K.sphere(f"Lung{sx}", HEART, 1.0, HEARTP + Vector((sx * 0.19, 0.07, 0.08)), lung_m, scale=(0.13, 0.11, 0.22), subdiv=4) for sx in (-1, 1)]
heart_m = glowy("Heart", (0.80, 0.08, 0.08), rough=0.35, sss=0.35, emit=1.0)
HP = HEARTP + Vector((0.0, -0.075, 0.07))
hparts = [K.sphere("LV", HEART, 1.0, Vector((0.03, 0.0, -0.015)), heart_m, scale=(0.062, 0.060, 0.090), subdiv=4),
          K.sphere("RV", HEART, 1.0, Vector((-0.032, -0.012, -0.012)), heart_m, scale=(0.055, 0.052, 0.080), subdiv=4),
          K.sphere("LA", HEART, 1.0, Vector((0.034, 0.028, 0.065)), heart_m, scale=(0.040, 0.036, 0.036), subdiv=3),
          K.sphere("RA", HEART, 1.0, Vector((-0.040, 0.004, 0.068)), heart_m, scale=(0.042, 0.038, 0.040), subdiv=3),
          K.tube("Aorta", HEART, [Vector((0.010, 0.0, 0.07)), Vector((0.012, -0.004, 0.13)), Vector((0.05, 0.0, 0.17)),
                                  Vector((0.09, 0.02, 0.12)), Vector((0.09, 0.03, 0.04))], 0.016, heart_m, res=10),
          K.tube("PulmArtery", HEART, [Vector((-0.01, -0.02, 0.07)), Vector((-0.02, -0.03, 0.12)), Vector((-0.07, -0.01, 0.15))], 0.013, heart_m, res=8),
          K.tube("VenaCava", HEART, [Vector((-0.05, 0.01, 0.08)), Vector((-0.06, 0.01, 0.15)), Vector((-0.06, 0.02, 0.24))], 0.012, heart_m, res=8)]
HEARTOBJ = K.empty("HeartGroup", HEART, HP)
K.parent(hparts, HEARTOBJ)
for k in range(8):
    z = 0.32 - 0.058 * k + (HEARTP.z - HEARTP.z)
    rx = 0.22 + 0.07 * math.sin(math.pi * min(1.0, (k + 1.5) / 7.5)) * 1.1
    ry = 0.15 + 0.03 * math.sin(math.pi * min(1.0, (k + 1.5) / 7.5))
    pts = [HEARTP + Vector((rx * math.cos(math.radians(a)), 0.03 + ry * math.sin(math.radians(a)), z - 0.015 * (1 - math.sin(math.radians(a))))) for a in range(-30, 211, 20)]
    K.tube(f"Rib{k}", HEART, pts, 0.0085, bone_m, res=6)
for k in range(14):
    K.sphere(f"Vertebra{k}", HEART, 1.0, HEARTP + Vector((0, 0.19, 0.38 - 0.052 * k)), bone_m, scale=(0.03, 0.026, 0.021), subdiv=3)
chest_shell = K.sphere("ChestShell", HEART, 1.0, HEARTP + Vector((0, 0.04, 0.12)), xglow("ChestGlow", (0.3, 0.6, 1.0), 1.4, blend=0.35, core=0.0),
                       scale=(0.40, 0.26, 0.46), subdiv=4)
hidden_from_rays(chest_shell)
HC = HP + Vector((0, 0, 0.0))

# BRAIN: an X-ray brain, cold and dim, a few slow sparks of oxygen.
BR_SIZE = (0.15, 0.19, 0.125)
brain_parts = K.brain(BRAIN, BRAINP, size=BR_SIZE, name="Brain", subdiv=5)
brain_shell = K.sphere("BrainShell", BRAIN, 1.0, BRAINP + Vector((0, 0.03, -0.04)), xglow("BrainGlow", (0.35, 0.65, 1.0), 1.6, blend=0.3, core=0.0),
                       scale=(0.17, 0.23, 0.20), subdiv=4)
hidden_from_rays(brain_shell)
frost_m = glowy("BrainFrost", (0.6, 0.85, 1.0), rough=0.2, sss=0.0, emit=0.0)
O2_M = glowy("Oxygen", (1.0, 0.75, 0.30), rough=0.2, sss=0.0, emit=10.0)
O2 = []
for k in range(7):
    rr = random.Random(500 + k)
    O2.append((K.sphere(f"O2_{k}", BRAIN, 0.0035, BRAINP, O2_M, subdiv=2), Vector((rr.uniform(-0.09, 0.09), rr.uniform(-0.10, 0.12), rr.uniform(-0.04, 0.09))), rr.uniform(0, 6.28)))
BRC = BRAINP + Vector((0, 0.02, 0.0))

# ---------------------------------------------------------------- shots (start, camera, set)
SHOTS = [
    (0.0, "HookHeart", "heart"),
    (at(0, 0.56), "HookOR", "or"),
    (B[1], "SkiWide", "ice"),
    (at(1, 0.44), "IceBreak", "ice"),
    (B[2], "UnderWide", "under"),
    (at(2, 0.50), "AirPocket", "under"),
    (B[3], "UnderEyes", "under"),
    (HS0, "HeartStop", "heart"),
    (B[4], "ThermoDrop", "thermo"),
    (at(4, 0.55), "ThermoCU", "thermo"),
    (B[5], "MachineWide", "or"),
    (at(5, 0.45), "TubeCU", "or"),
    (SLO_A, "RestartHeart", "heart"),
    (SLO_B, "MonitorCU", "or"),
    (B[7], "BrainCold", "brain"),
    (at(7, 0.50), "BrainMacro", "brain"),
    (B[8], "WakeFace", "or"),
    (at(8, 0.50), "RecoverWide", "home"),
    (B[9], "FinalHeart", "heart"),
    (at(9, 0.46), "Closer", "home"),
]


def shot_at(t):
    return max((s for s in SHOTS if s[0] <= t + 1e-6), key=lambda s: s[0])


SH = [shot_at(t) for t in T]
SET_OF = [s[2] for s in SH]
REST_HIPS = her.hips0.copy()


def fall_state(t):
    u = max(0.0, min(1.0, (t - FALL_A) / (FALL_B - FALL_A)))
    return -math.radians(88) * u ** 1.6, -1.0 * u ** 1.5, -1.5 * u ** 3


def her_root(s, t):
    """(location, euler) of her rig object so that her feet pivot on the floor mark of the set she is in."""
    if s[2] == "ice":
        th, dx, dz = fall_state(t)
        rz, P = math.pi / 2, P_ICE + Vector((dx, 0, dz))
    elif s[2] == "under":
        th, rz, P = -math.radians(88), math.pi / 2, P_UN + Vector((0, 0, 0.012 * math.sin(1.7 * t) + 0.02 * math.sin(0.6 * t)))
    elif s[2] == "or":
        th, rz, P = -math.radians(88), 0.0, P_OR
    else:
        th, rz, P = 0.0, 0.0, P_HOME
    R = Euler((th, 0, rz), "XYZ").to_matrix()
    off = R @ Vector((her.x0, REST_HIPS.y, 0))
    return P - off, (th, 0, rz)


# ---------------------------------------------------------------- performance
BLINKS = [1.0 + 3.1 * k for k in range(60) if 1.0 + 3.1 * k < DUR]


def channels(t, s):
    ch = {}
    setn = s[2]
    ch["fall"] = env(t, FALL_A - 0.15, FALL_A + 0.05, FALL_B - 0.1, FALL_B)
    ch["gasp"] = env(t, FALL_A, FALL_A + 0.1, FALL_B - 0.1, FALL_B)
    if setn == "or":
        ch["closed"] = 1.0 - ramp(t, WAKE, WAKE + 0.5) if t < B[9] else 0.0
    elif setn == "under":
        ch["closed"] = ramp(t, EYES, EYES + 0.5)
    else:
        ch["closed"] = 0.0
    ch["wake"] = env(t, WAKE, WAKE + 0.7, WAKE + 1.2, WAKE + 1.8)
    ch["smile"] = 0.5 * (setn == "ice" and t < FALL_A - 0.1) + 0.85 * (setn == "home") * ramp(t, at(8, 0.5), at(8, 0.5) + 0.5)
    ch["blink"] = max((env(t, b_ - 0.03, b_, b_ + 0.05, b_ + 0.12) for b_ in BLINKS), default=0.0) * (1 - ch["closed"])
    ch["breath"] = 0.5 + 0.5 * math.sin(t * 2 * math.pi / 2.6)
    return ch


legs_stand = her.standing_legs()
SIDE_L = REST_HIPS + Vector((0.22, 0.02, -0.12))
SIDE_R = REST_HIPS + Vector((-0.22, 0.02, -0.12))
FLING_L = Vector((her.x0 + 0.42, REST_HIPS.y - 0.05, REST_HIPS.z + 0.72))
FLING_R = Vector((her.x0 - 0.42, REST_HIPS.y - 0.05, REST_HIPS.z + 0.72))
face_pt = her.anchor("Face", "Head", Vector((her.x0, her.nose.y + 0.05, her.nose.z - 0.01)), CAST)
eyes_mid = her.anchor("Eyes", "Head", (her.eye_l + her.eye_r) / 2, CAST)
chest_pt = her.anchor("Chest", "Spine2", her.bone_rest_head("Spine2"), CAST)
mouth_pt = her.anchor("MouthPt", "Head", Vector((her.x0, her.nose.y + 0.03, her.nose.z - 0.045)), CAST)

for i, t in enumerate(T):
    s = SH[i]
    ch = channels(t, s)
    br = math.sin(t * 2 * math.pi / 3.6)
    fall, gasp = ch["fall"], ch["gasp"]
    spec = {
        "Hips": [(A.Z, 0.6 * wobble(t, 1))],
        "Spine": [(A.X, 0.6 * br - 8 * fall), (A.Z, 0.8 * wobble(t, 2))],
        "Spine1": [(A.X, 0.7 * br - 5 * fall)],
        "Spine2": [(A.X, 1.5 + 0.6 * br + 3 * ch["wake"])],
        "Neck": [(A.X, 5 * fall - 4 * ch["wake"]), (A.Z, 1.2 * wobble(t, 4))],
        "Head": [(A.X, 1.0 * wobble(t, 7, 0.6) + 7 * fall - 3 * ch["wake"]), (A.Z, 1.6 * wobble(t, 5, 0.5) + 6 * ch["wake"] * math.sin(2 * t))],
        "LeftShoulder": [(A.Y, 6 * fall)],
        "RightShoulder": [(A.Y, -6 * fall)],
    }
    rots = {}
    for bone, axes in spec.items():
        if her.has(bone):
            q = A.Quaternion()
            for axis, deg in axes:
                q = q @ her.q(bone, axis, deg)
            rots[bone] = q
    rots.update(legs_stand)
    for bone in her.fingers():
        j = int(bone[-1])
        curl = ({1: 22, 2: 30, 3: 22} if "Thumb" not in bone else {1: 8, 2: 14, 3: 10})[j]
        curl += 30 * ch["wake"]
        rots[bone] = A.Quaternion((1, 0, 0), math.radians(curl))
    sh = {}
    for side in ("Left", "Right"):
        sh[f"eyeBlink{side}"] = min(1.0, ch["blink"] + ch["closed"] + 0.15 * ch["smile"])
        sh[f"eyeWide{side}"] = 0.8 * fall + 0.5 * ch["wake"] * (1 - ch["closed"])
        sh[f"browDown{side}"] = 0.0
        sh[f"eyeSquint{side}"] = 0.3 * ch["smile"]
        sh[f"mouthSmile{side}"] = 0.9 * ch["smile"]
        sh[f"cheekSquint{side}"] = 0.4 * ch["smile"]
    sh["browInnerUp"] = 0.8 * fall + 0.3 * ch["wake"]
    sh["jawOpen"] = 0.55 * gasp + 0.12 * ch["wake"]
    ikl, ikr = SIDE_L + Vector((0, 0, 0.004 * br)), SIDE_R + Vector((0, 0, 0.004 * br))
    if fall > 0.001:
        ikl, ikr = ikl.lerp(FLING_L, fall), ikr.lerp(FLING_R, fall)
    her.record(rots, sh, ikl, ikr, aim=(0.0, 0.0), follow={}, root=her_root(s, t))
her.bake(FRAMES)
for fc in A.fcurves_of(her.rig):
    if fc.data_path in ("location", "rotation_euler"):
        fc.keyframe_points.foreach_set("interpolation", [0] * len(fc.keyframe_points))   # teleports are cuts

# ---------------------------------------------------------------- the heart: warm and beating, slowing, stopped, restarted
TA = [warp(t) for t in T]
HB = []
tb = B[1] + 0.30
while tb < HS0:
    HB.append((tb, 1.0))
    tb += 0.85
for gap, amp in ((0.95, 0.8), (1.4, 0.55), (2.0, 0.35)):
    if tb < HS1:
        HB.append((tb, amp))
    tb += gap
HB.append((HIT_ACT, 1.7))                                                            # the restart (slow motion)
HB += [(SLO_B + 0.25 + BEAT_GAP * k, 1.2 if k < 3 else 1.0) for k in range(40)]


def cold(t):
    if t < B[1]:
        return 1.0
    if t < HS0:
        return 0.0
    if t < HIT:
        return ramp(t, HS0, HS1 + 0.3)
    return 1.0 - ramp(t, HIT, HIT + 1.6)


def pulse(ta):
    return sum(a_ * spike(ta, h, 0.035, 0.24) for h, a_ in HB)


PUL = [pulse(TA[i]) for i in range(len(T))]
COLD = [cold(t) for t in T]
bake_vec(HEARTOBJ, "scale", [(1 + 0.11 * p, 1 + 0.09 * p, 1 + 0.12 * p) for p in PUL])
WARM_C, ICY_C = (0.75, 0.05, 0.06), (0.28, 0.55, 0.95)
mixc = lambda c: tuple(w + (i_ - w) * c for w, i_ in zip(WARM_C, ICY_C)) + (1,)
bake_vec(heart_m.node_tree, BSDF + '["Base Color"].default_value', [mixc(c) for c in COLD], n=4)
bake_vec(heart_m.node_tree, BSDF + '["Emission Color"].default_value', [mixc(c) for c in COLD], n=4)
bake(heart_m.node_tree, BSDF + '["Emission Strength"].default_value', [(0.55 - 0.25 * COLD[i]) + 1.8 * PUL[i] * (1 - 0.6 * COLD[i]) for i in range(len(T))])
for lg in LUNGS:
    bake_vec(lg, "scale", [(0.13 * (1 + 0.025 * math.sin(t * 2 * math.pi / 3.6)), 0.11, 0.22 * (1 + 0.03 * math.sin(t * 2 * math.pi / 3.6))) for t in T])
bake_vec(lung_m.node_tree, BSDF + '["Base Color"].default_value',
         [tuple(w + (i_ - w) * c * 0.8 for w, i_ in zip((0.92, 0.50, 0.55), (0.5, 0.75, 1.0))) + (1,) for c in COLD], n=4)
bake_vec(lung_m.node_tree, BSDF + '["Emission Color"].default_value',
         [tuple(w + (i_ - w) * c * 0.8 for w, i_ in zip((0.92, 0.50, 0.55), (0.5, 0.75, 1.0))) + (1,) for c in COLD], n=4)

# ---------------------------------------------------------------- the thermometer
def temp(t):
    if t < TEMP_A:
        return 37.0
    return 37.0 - (37.0 - 13.7) * smooth((t - TEMP_A) / (TEMP_B - TEMP_A))


TMP = [temp(t) for t in T]
bake_vec(FILL, "scale", [(1.0, 1.0, max(0.01, tz(x) - (THP.z + ZLO) + 0.02)) for x in TMP])
bake(FILL, "location", [THP.z + ZLO - 0.02 + (tz(x) - (THP.z + ZLO) + 0.02) / 2 for x in TMP], index=2)
bake(TOP_PT, "location", [tz(x) for x in TMP], index=2)
fmix = lambda x: tuple(a + (b - a) * (37.0 - x) / (37.0 - 13.7) for a, b in zip((0.9, 0.08, 0.05), (0.35, 0.70, 1.0))) + (1,)
bake_vec(fill_m.node_tree, BSDF + '["Base Color"].default_value', [fmix(x) for x in TMP], n=4)
bake_vec(fill_m.node_tree, BSDF + '["Emission Color"].default_value', [fmix(x) for x in TMP], n=4)
bake(goal_m.node_tree, BSDF + '["Emission Strength"].default_value', [10.0 * smooth((t - TEMP_B + 0.25) / 0.25) * (0.8 + 0.2 * math.sin(9 * t)) for t in T])
bake_vec(GOAL, "scale", [(1 + 0.4 * smooth((t - TEMP_B + 0.25) / 0.25) * (1 + 0.15 * math.sin(9 * t)),) * 2 + (1.0,) for t in T])

# ---------------------------------------------------------------- under the ice: bubbles from her mouth, an air pocket above her head
bubbles = [K.sphere(f"Bubble{k}", UNDER, 0.016, UNP, bubble_m, subdiv=2) for k in range(14)]

# ---------------------------------------------------------------- the machine: roller pump spins, blood beads flow, coil heats
bake(PUMP, "rotation_euler", [-(max(0.0, t - B[5] + 0.05)) * 5.0 for t in T], index=2)
WARMUP = [ramp(t, B[5], B[6] - 0.3) for t in T]
bake(coil_m.node_tree, BSDF + '["Emission Strength"].default_value', [6.0 * w for w in WARMUP])
bake_vec(res_m.node_tree, BSDF + '["Base Color"].default_value', [(0.30 + 0.45 * w, 0.02, 0.04, 1) for w in WARMUP], n=4)
bake_vec(res_m.node_tree, BSDF + '["Emission Color"].default_value', [(0.30 + 0.45 * w, 0.02, 0.04, 1) for w in WARMUP], n=4)
for o, path, ph in BEADS:
    locs, scl = [], []
    for t in T:
        on = ramp(t, B[5] - 0.05, B[5] + 0.15)
        u = ((t - B[5]) * 0.45 + ph) % 1.0
        locs.append(along(path, u))
        scl.append(on * smooth(min(u, 1 - u) / 0.08))
    bake_vec(o, "location", locs)
    bake_vec(o, "scale", [(v, v, v) for v in scl])
bake(bead_art.node_tree, BSDF + '["Emission Strength"].default_value', [2.0 + 2.5 * w for w in WARMUP])
# the vital monitor: dark until the heart restarts, then a green trace
vit = K._vitals_mat()
bake(vit.node_tree, BSDF + '["Emission Strength"].default_value', [0.1 if t < HIT else 3.5 * smooth((t - HIT) / 0.2) for t in T])

# ---------------------------------------------------------------- the brain: cold, dim, a few slow sparks
for o, d0, ph in O2:
    bake_vec(o, "location", [BRAINP + d0 + Vector((0.01 * math.sin(0.7 * t + ph), 0.01 * math.cos(0.5 * t + ph), 0.008 * math.sin(0.4 * t))) for t in T])
    bake_vec(o, "scale", [((0.5 + 0.5 * math.sin(0.6 * t + ph)) ** 2 + 0.02,) * 3 for t in T])
bake(frost_m.node_tree, BSDF + '["Emission Strength"].default_value', [0.0 for t in T])

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


for name, coll in (("home", HOME), ("ice", ICE), ("under", UNDER), ("or", OR), ("thermo", THERMO), ("heart", HEART), ("brain", BRAIN)):
    key_vis([o for o in coll.all_objects if not o.hide_render], lambda i, name=name: SET_OF[i] == name)
key_vis([o for o in her.rig.children_recursive if o.type in ("MESH", "CURVES", "CURVE")], lambda i: SET_OF[i] in ("home", "ice", "under", "or"))

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
WCOL = {"home": ((0.66, 0.74, 0.80), 0.30), "ice": ((0.50, 0.68, 0.95), 1.1), "under": ((0.01, 0.07, 0.14), 1.0),
        "or": ((0.5, 0.62, 0.62), 0.15), "thermo": ((0.004, 0.006, 0.014), 1.0), "heart": ((0.008, 0.012, 0.03), 1.0),
        "brain": ((0.012, 0.010, 0.030), 1.0)}
cols = [WCOL[s] for s in SET_OF]
bake_vec(wnt, 'nodes["Background"].inputs[0].default_value', [(*c_, 1) for c_, _ in cols], n=4, interp="CONSTANT")
bake(wnt, 'nodes["Background"].inputs[1].default_value', [s_ for _, s_ in cols], interp="CONSTANT")
CUTS = [s[0] for k, s in enumerate(SHOTS) if k and SHOTS[k - 1][2] != s[2]]
bake(scene, "view_settings.exposure", [-0.2 + 0.8 * sum(spike(t, c, 0.005, 0.05) for c in CUTS) + 0.6 * spike(t, HIT, 0.02, 0.12)
                                       + 0.5 * spike(t, FALL_B, 0.01, 0.08) for t in T])


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
HEAD_I = P_ICE + Vector((0, 0, 1.2))
HEAD_U = P_UN + Vector((-0.8, 0, 0.05))
BODY_OR = ORP + Vector((0, 0.0, 1.2))
THC = THP
LIGHTS = {
    "home": [_light("AREA", "HomeKey", HOME, HEAD_H + Vector((1.4, -1.5, 1.2)), HEAD_H, 320, 1.5, (1.0, 0.93, 0.80)),
             _light("AREA", "HomeFill", HOME, HEAD_H + Vector((-1.8, -1.5, 0.6)), HEAD_H, 120, 2.0, (0.85, 0.90, 1.0)),
             _light("AREA", "HomeRim", HOME, HEAD_H + Vector((-0.6, 1.4, 1.0)), HEAD_H, 190, 0.8, (1.0, 0.92, 0.80)),
             _light("AREA", "HomeWindow", HOME, HOMEP + Vector((1.9, 3.4, 1.6)), HEAD_H, 260, 1.3, (1.0, 0.92, 0.75))],
    "ice": [_light("AREA", "IceKey", ICE, HEAD_I + Vector((2.6, -3.0, 3.0)), HEAD_I, 600, 3.0, (1.0, 0.97, 0.90)),
            _light("AREA", "IceFill", ICE, HEAD_I + Vector((-3.0, -3.0, 1.0)), HEAD_I, 260, 4.0, (0.75, 0.88, 1.0)),
            _light("AREA", "IceRim", ICE, HEAD_I + Vector((-1.0, 3.0, 2.0)), HEAD_I, 320, 2.0, (1.0, 0.95, 0.85))],
    "under": [_light("AREA", "ShaftKey", UNDER, UNP + Vector((2.0, 0.0, 0.8)), HEAD_U, 700, 1.3, (0.75, 0.92, 1.0)),
              _light("AREA", "UKey", UNDER, HEAD_U + Vector((1.2, -2.2, 0.6)), HEAD_U, 420, 2.0, (0.55, 0.85, 1.0)),
              _light("AREA", "UFill", UNDER, HEAD_U + Vector((-1.5, -1.5, -0.6)), HEAD_U, 150, 2.0, (0.4, 0.7, 1.0)),
              _light("AREA", "URim", UNDER, HEAD_U + Vector((-0.6, 1.6, 0.5)), HEAD_U, 220, 1.2, (0.7, 0.9, 1.0))],
    "or": [_light("AREA", "ORCeil", OR, BODY_OR + Vector((0.0, 0.2, 1.4)), BODY_OR, 700, 2.5, (0.85, 0.95, 1.0)),
           _light("AREA", "ORKey", OR, BODY_OR + Vector((-1.8, -2.2, 0.9)), BODY_OR, 450, 2.0, (0.85, 0.95, 1.0)),
           _light("AREA", "ORFill", OR, BODY_OR + Vector((1.5, -2.0, 0.4)), BODY_OR, 220, 2.5, (1.0, 0.9, 0.85)),
           _light("AREA", "ORMachine", OR, MP + Vector((-0.6, -1.4, 1.5)), MP + Vector((0, 0, 1.2)), 180, 1.0, (1.0, 0.88, 0.8))],
    "thermo": [_light("AREA", "TKey", THERMO, THC + Vector((0.8, -2.4, 0.6)), THC, 90, 1.2, (1.0, 0.92, 0.85)),
               _light("AREA", "TRim", THERMO, THC + Vector((-1.2, -1.5, 1.2)), THC, 60, 1.2, (0.6, 0.8, 1.0))],
    "heart": [_light("AREA", "HKey", HEART, HC + Vector((0.5, -0.8, 0.5)), HC, 18, 0.8, (1.0, 0.88, 0.80)),
              _light("AREA", "HFill", HEART, HC + Vector((-0.8, -0.7, 0.1)), HC, 12, 1.0, (0.55, 0.70, 1.0)),
              _light("AREA", "HRim", HEART, HC + Vector((0.0, 0.7, 0.6)), HC, 16, 0.6, (0.6, 0.8, 1.0))],
    "brain": [_light("AREA", "BKey", BRAIN, BRC + Vector((0.5, -0.7, 0.3)), BRC, 22, 0.6, (0.55, 0.78, 1.0)),
              _light("AREA", "BFill", BRAIN, BRC + Vector((-0.7, -0.6, 0.1)), BRC, 8, 1.0, (0.55, 0.70, 1.0)),
              _light("AREA", "BRim", BRAIN, BRC + Vector((0.0, 0.6, 0.5)), BRC, 12, 0.6, (0.9, 0.7, 1.0))],
}
BASE = {l.name: l.data.energy for ls in LIGHTS.values() for l in ls}
for set_name, ls in LIGHTS.items():
    for l in ls:
        vals = []
        for i, t in enumerate(T):
            e = BASE[l.name] * (SET_OF[i] == set_name)
            if l.name == "HKey":
                e *= 1 + 1.6 * PUL[i] * (1 - COLD[i]) + 0.3 * (1 - COLD[i])
            elif l.name == "HFill":
                e *= 1 + 0.8 * COLD[i]
            elif l.name == "ORKey":
                e *= 1 + 0.2 * smooth((t - WAKE) / 1.0)
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


W = cams.world_at
# air pocket above her head, and bubbles from her mouth (positions measured on the posed character)
tU = mid("UnderWide")
HEAD_W = W(face_pt, tU)
MOUTH_W = W(mouth_pt, tU)
print("UNDER head", [round(v, 2) for v in HEAD_W], "mouth", [round(v, 2) for v in MOUTH_W])
POCKET = K.sphere("AirPocket", UNDER, 1.0, Vector((HEAD_W.x, HEAD_W.y, -0.035)), pocket_m, scale=(0.34, 0.26, 0.07), subdiv=4)
for k, bo in enumerate(bubbles):
    locs, scl = [], []
    for t in T:
        u = ((t - B[2]) * 0.55 + k / len(bubbles)) % 1.0
        rise = min(1.0, u * 1.2)
        locs.append(Vector((MOUTH_W.x + 0.04 * math.sin(7 * u + k), MOUTH_W.y + 0.04 * math.cos(5 * u + k), MOUTH_W.z + (-0.05 - MOUTH_W.z) * rise)))
        scl.append(smooth(min(u, 1 - u) / 0.1) * (0.6 + 0.8 * ((k * 0.37) % 1.0)) * (1.0 if t < EYES + 1.0 else 0.0))
    bake_vec(bo, "location", locs)
    bake_vec(bo, "scale", [(v, v, v) for v in scl])

# beat 1 hook (frame 1 = thumbnail): the frozen blue heart, then her on the table
a, b = span("HookHeart")
cams.cam("HookHeart", a, b, keys=[(a, HP + Vector((0.20, -0.52, 0.06))), (b, HP + Vector((0.10, -0.36, 0.03)))], lens=50, aim=HP + Vector((0, 0, 0.02)),
         depth=0.12, shake=0.0008, ease="cine")
a, b = span("HookOR")
CO = W(chest_pt, mid("HookOR"))
cams.cam("HookOR", a, b, keys=[(a, CO + Vector((1.5, -1.9, 1.0))), (b, CO + Vector((1.05, -1.4, 0.75)))], lens=32, aim=CO + Vector((0, 0.25, 0.1)),
         depth=1.0, shake=0.001)
# beat 2: skiing, the ice gives way
a, b = span("SkiWide")
SM = ICEP + Vector((-0.3, 0.0, 0.95))
cams.cam("SkiWide", a, b, keys=[(a, SM + Vector((2.6, -4.4, 0.2))), (b, SM + Vector((1.8, -3.7, 0.15)))], lens=30, aim=SM, depth=2.5, shake=0.001)
a, b = span("IceBreak")
IM = ICEP + Vector((-1.0, 0.0, 0.2))
cams.cam("IceBreak", a, b, keys=[(a, IM + Vector((1.8, -2.5, 0.55))), (b, IM + Vector((1.0, -2.0, 0.30)))], lens=26, aim=IM, depth=2.0, shake=0.0015,
         kicks=[(FALL_B, 0.02, 0.25)])
# beat 3: trapped under the ice
a, b = span("UnderWide")
UM = W(chest_pt, mid("UnderWide"))
cams.cam("UnderWide", a, b, keys=[(a, UM + Vector((1.5, -2.6, -0.35))), (b, UM + Vector((0.5, -2.1, -0.45)))], lens=28, aim=UM + Vector((-0.3, 0, 0.15)),
         depth=2.0, shake=0.001)
a, b = span("AirPocket")
PK = Vector((HEAD_W.x, HEAD_W.y, -0.12))
cams.cam("AirPocket", a, b, keys=[(a, PK + Vector((0.5, -0.85, -0.25))), (b, PK + Vector((0.25, -0.52, -0.12)))], lens=50, aim=PK, depth=0.35, shake=0.0006)
# beat 4: the eyes close, then the heart stops
a, b = span("UnderEyes")
FU = W(face_pt, mid("UnderEyes"))
cams.cam("UnderEyes", a, b, keys=[(a, FU + Vector((-0.55, -0.25, 0.14))), (b, FU + Vector((-0.38, -0.16, 0.10)))], lens=50, aim=FU, focus=eyes_mid,
         depth=0.12, shake=0.0005, ease="cine")
a, b = span("HeartStop")
cams.cam("HeartStop", a, b, keys=[(a, HP + Vector((-0.22, -0.50, 0.05))), (b, HP + Vector((-0.08, -0.32, 0.03)))], lens=50, aim=HP + Vector((0, 0, 0.02)),
         depth=0.12, shake=0.0004)
# beat 5: the thermometer
a, b = span("ThermoDrop")
cams.cam("ThermoDrop", a, b, keys=[(a, THP + Vector((0.9, -2.0, 1.45))), (b, THP + Vector((0.7, -1.7, -0.9)))], lens=40, aim=TOP_PT, depth=0.8,
         shake=0.0005, ease="cine")
a, b = span("ThermoCU")
GP = Vector((THP.x, THP.y, tz(13.7)))
cams.cam("ThermoCU", a, b, keys=[(a, GP + Vector((0.55, -1.0, 0.15))), (b, GP + Vector((0.30, -0.55, 0.05)))], lens=50, aim=GP, depth=0.3, shake=0.0004)
# beat 6: the heart-lung machine
a, b = span("MachineWide")
cams.cam("MachineWide", a, b, keys=[(a, ORP + Vector((-1.7, -2.5, 1.55))), (b, ORP + Vector((-1.0, -2.0, 1.40)))], lens=28, aim=ORP + Vector((0.7, -0.1, 1.0)),
         depth=3.0, shake=0.001)
a, b = span("TubeCU")
OXC = MP + Vector((0.0, -0.12, 1.30))
cams.cam("TubeCU", a, b, keys=[(a, OXC + Vector((-0.65, -0.75, 0.10))), (b, OXC + Vector((-0.40, -0.48, 0.06)))], lens=50, aim=OXC, depth=0.4, shake=0.0005)
# beat 7 MONEY MOMENT: the heart restarts in slow motion
a, b = span("RestartHeart")
cams.cam("RestartHeart", a, b, keys=[(a, HP + Vector((0.24, -0.52, 0.10))), (b, HP + Vector((0.05, -0.30, 0.02)))], lens=50, aim=HP + Vector((0, 0, 0.02)),
         depth=0.1, shake=0.0003, kicks=[(HIT, 0.012, 0.3)], ease="cine")
a, b = span("MonitorCU")
cams.cam("MonitorCU", a, b, keys=[(a, MON + Vector((0.25, -1.05, 0.05))), (b, MON + Vector((0.10, -0.62, 0.0)))], lens=50, aim=MON, depth=0.25, shake=0.0006)
# beat 8: the cold brain
a, b = span("BrainCold")
cams.cam("BrainCold", a, b, path=S.orbit(BRAINP + Vector((0, 0.03, -0.05)), 0.62, -22, 22, 0.05, 0.0), lens=40, aim=BRAINP + Vector((0, 0.03, -0.06)),
         depth=0.3, shake=0.0004)
a, b = span("BrainMacro")
cams.cam("BrainMacro", a, b, keys=[(a, BRAINP + Vector((0.16, -0.30, 0.10))), (b, BRAINP + Vector((0.08, -0.20, 0.06)))], lens=70, aim=BRAINP + Vector((0, 0, 0.02)),
         depth=0.08, shake=0.0003)
# beat 9: she wakes, then home
a, b = span("WakeFace")
FW = W(face_pt, mid("WakeFace"))
cams.cam("WakeFace", a, b, keys=[(a, FW + Vector((-0.40, -0.50, 0.55))), (b, FW + Vector((-0.24, -0.30, 0.38)))], lens=50, aim=FW, focus=eyes_mid,
         depth=0.12, shake=0.0006, ease="cine")
a, b = span("RecoverWide")
C8 = W(chest_pt, mid("RecoverWide"))
cams.cam("RecoverWide", a, b, path=S.orbit(C8, 2.1, -30, 8, 0.2, 0.05, 1.7), lens=28, aim=C8 + Vector((0, 0.3, 0.2)), focus=chest_pt, depth=1.4, shake=0.0008)
# beat 10: a strong warm heartbeat, then her smile
a, b = span("FinalHeart")
cams.cam("FinalHeart", a, b, path=S.orbit(HP + Vector((0, 0, 0.02)), 0.42, -32, 18, 0.05, 0.03), lens=50, aim=HP + Vector((0, 0, 0.02)), depth=0.14,
         shake=0.0004)
a, b = span("Closer")
F9 = W(face_pt, mid("Closer"))
cams.cam("Closer", a, b, keys=[(a, F9 + Vector((0.12, -1.05, 0.02))), (b, F9 + Vector((0.05, -0.52, 0.0)))], lens=55, aim=face_pt,
         focus=eyes_mid, depth=0.12, shift_y=-0.06, shake=0.0008, ease="cine")

cams.markers(SHOTS)
S.check_shots(SHOTS, DUR)


def gaze_target(t):
    return None


her.bake_gaze(FRAMES, T, gaze_target, CAST, seed=29)

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
