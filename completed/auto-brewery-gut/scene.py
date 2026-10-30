"""auto-brewery-gut: "Arrested for drunk driving, he hadn't had a drink in twenty years" (auto-brewery syndrome;
case report "A Case of Auto-brewery Syndrome Treated with Micafungin", Cureus 2019, PMC6853272: two DWI arrests,
breathalyzer 0.41, gut yeast fermenting carbohydrate into ethanol, proven by a monitored carbohydrate challenge,
cleared by the antifungal micafungin).

Run (daily_render.ps1): blender -b --python scene.py -- <ROOT>/blend/<slug>.blend vo=<wav> beats=<json> fps=30
Optional: stills=1,200 pct=100 samples=128 device=gpu|cpu root=<ROOT>

v3 toolkit: every model is built in Blender from code (scripts/kit.py), the character acts procedurally on the
mixamorig bones (scripts/actor.py) and every camera is a moving spline that is already in motion on the cut
(scripts/shot.py). No captions, no on-screen text (owner's rule): the breathalyzer reading is a 7-segment prop
display built from geometry. Timing comes only from the beats JSON.

Cast: him = blend/char_hero.blend (opened as the main file). One character, one actor.
Sets: ROAD (night traffic stop: his parked sedan, a police car behind it with a red/blue light bar, street lamps),
HOSP (a hospital room: bed, IV pole, vitals monitor; he sits on the bed edge) and XRAY (a cutaway of his small
intestine 60 m under the road: glowing gut wall, villi, budding yeast cells, golden alcohol bubbles, a vessel).
Transitions between sets are HARD CUTS (whoosh SFX + a brief exposure spike). SYNC constants must match mix.py.
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
BLOW = at(1, 0.05)                                # he starts blowing into the breathalyzer
READ_A, READ_B = at(1, 0.50), at(1, 0.85)         # the display counts up to 0.41
SLAP = at(2, 0.06)                                # hands slap onto the car roof
SLO_A, SLO_B = B[6], at(6, 0.62)                  # screen-time slow-mo window: sugar hits the yeast (money moment)
ACT_A, ACT_B = SLO_A, SLO_A + (SLO_B - SLO_A) * 0.4
HIT_F = 0.35                                      # fraction of the slow-mo window where the sugar lands
HIT = SLO_A + HIT_F * (SLO_B - SLO_A)             # screen time of the hit
HIT_ACT = ACT_A + HIT_F * (ACT_B - ACT_A)         # the same moment in action time
DRUG = at(7, 0.45)                                # the antifungal reaches the gut (YeastDie shot)
SMILE = at(9, 0.55)
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

# ---------------------------------------------------------------- sets
ROADP, HOSPP, GUTP = Vector((0, 0, 0)), Vector((40, 0, 0)), Vector((0, 0, -60))
ROAD, HOSP, GUT = K.coll("SetRoad"), K.coll("SetHosp"), K.coll("SetGut")

# ROAD: a two-lane road along Y at night. Traffic drives toward -Y, so the parking lane is the -X side and a
# parked car's driver door (its left) faces the road centre (+X). He stands by that door facing -Y (the camera side).
K.road(ROAD, length=220.0, lanes=2, y0=-110.0)
MY_CAR = ROADP + Vector((-2.35, 0.55, 0))
K.car(ROAD, MY_CAR, color=(0.03, 0.10, 0.28), name="HisCar")
COP = ROADP + Vector((-2.25, 7.4, 0))
K.car(ROAD, COP, color=(0.86, 0.87, 0.89), name="Police", interior=False)
bar_dark = K.plastic("LightBarBase", (0.02, 0.02, 0.025), 0.4)
K.rbox("LightBar", ROAD, (1.15, 0.26, 0.07), COP + Vector((0, 0.45, 1.475)), bar_dark, bevel=0.02)
red_m = glowy("CopRed", (1.0, 0.04, 0.03), rough=0.2, sss=0.0, emit=0.0)
blue_m = glowy("CopBlue", (0.05, 0.20, 1.0), rough=0.2, sss=0.0, emit=0.0)
K.rbox("LightRed", ROAD, (0.50, 0.22, 0.09), COP + Vector((0.29, 0.45, 1.53)), red_m, bevel=0.025)
K.rbox("LightBlue", ROAD, (0.50, 0.22, 0.09), COP + Vector((-0.29, 0.45, 1.53)), blue_m, bevel=0.025)
door_m = K.plastic("CopDoorBlack", (0.015, 0.015, 0.018), 0.35, coat=0.6)
for sx in (-1, 1):
    K.rbox("CopDoorPanel", ROAD, (0.02, 1.4, 0.36), COP + Vector((sx * 0.905, 0.15, 0.62)), door_m, bevel=0.01)
for k, (p, rot) in enumerate((((-4.75, -4.0, 0), 0.0), ((-4.75, 21.0, 0), 0.0), ((4.75, 9.0, 0), math.pi))):
    K.street_lamp(ROAD, ROADP + Vector(p), name=f"Lamp{k}", rot=rot)
for k, (p, h) in enumerate((((-9.0, 4.0, 0), 7.5), ((-8.0, 15.0, 0), 6.5), ((9.5, 2.0, 0), 8.0), ((8.5, 18.0, 0), 7.0))):
    K.tree(ROAD, ROADP + Vector(p), h=h, name=f"Tree{k}", seed=k + 3)
cone_m = K.plastic("ConeOrange", (1.0, 0.28, 0.02), 0.45)
stripe_m = K.plastic("ConeStripe", (0.95, 0.95, 0.95), 0.3)
for k, p in enumerate(((-0.9, 3.4), (-0.6, 4.9))):
    K.lathe(f"Cone{k}", ROAD, [(0.0, 0.0), (0.16, 0.0), (0.15, 0.03), (0.035, 0.46), (0.0, 0.47)], ROADP + Vector((*p, 0)), cone_m)
    K.cyl(f"ConeStripe{k}", ROAD, 0.083, 0.06, ROADP + Vector((*p, 0.27)), stripe_m, verts=24)
P_ROAD = ROADP + Vector((-1.05, 0.35, 0))           # where he stands (feet), beside his driver door

# HOSP: a hospital room. The bed runs along X; he sits on its front (-Y) edge facing the open camera side.
K.room(HOSP, origin=HOSPP + Vector((0, 1.0, 0)), size=(6.0, 5.2, 2.8), floor_mat=K.paint("HospFloor", (0.58, 0.64, 0.66), 0.3),
       wall_color=(0.76, 0.84, 0.84), name="HospRoom", openings=[(1.7, 1.5, 1.44, 1.44)])
K.window(HOSP, HOSPP + Vector((1.7, 3.57, 1.5)), size=(1.3, 1.3), curtains=True, sky=(0.80, 0.88, 1.0), sky_strength=2.5)
bed_frame = K.metal("BedFrame", (0.82, 0.83, 0.86), 0.3)
bed_plast = K.plastic("BedPanel", (0.86, 0.88, 0.90), 0.35)
sheet_m = K.fabric("BedSheet", (0.90, 0.93, 0.95), weave=800)
blanket_m = K.fabric("BedBlanket", (0.42, 0.62, 0.78), weave=500)
BED = HOSPP + Vector((0, 0.47, 0))
K.rbox("BedBase", HOSP, (2.05, 0.95, 0.12), BED + Vector((0, 0, 0.42)), bed_frame, bevel=0.015)
K.cushion("Mattress", HOSP, (2.0, 0.9, 0.17), BED + Vector((0, 0, 0.565)), sheet_m, puff=0.25)
K.cushion("Pillow", HOSP, (0.55, 0.40, 0.13), BED + Vector((-0.72, 0.08, 0.71)), sheet_m, puff=0.7)
K.cushion("Blanket", HOSP, (0.75, 0.86, 0.07), BED + Vector((0.6, 0.0, 0.68)), blanket_m, puff=0.35)
for sx in (-1, 1):
    K.rbox("BedHead", HOSP, (0.05, 0.95, 0.55 if sx < 0 else 0.35), BED + Vector((sx * 1.04, 0, 0.72 if sx < 0 else 0.62)), bed_plast, bevel=0.02)
    for sy in (-1, 1):
        K.cyl("BedLeg", HOSP, 0.025, 0.34, BED + Vector((sx * 0.92, sy * 0.4, 0.2)), bed_frame, verts=16)
        K.cyl("BedWheel", HOSP, 0.045, 0.03, BED + Vector((sx * 0.92, sy * 0.4, 0.045)), K.rubber(), rot=(math.radians(90), 0, 0), verts=24)
K.tube("BedRail", HOSP, [BED + Vector((-0.75, 0.47, 0.70)), BED + Vector((0.0, 0.47, 0.82)), BED + Vector((0.75, 0.47, 0.70))], 0.015, bed_frame)
K.iv_pole(HOSP, HOSPP + Vector((0.78, -0.12, 0)), name="IV")
K.vital_monitor(HOSP, HOSPP + Vector((-1.25, 0.95, 1.45)), rot=math.radians(25))
K.rbox("Nightstand", HOSP, (0.45, 0.42, 0.72), HOSPP + Vector((-1.55, 0.35, 0.36)), K.wood("NightWood", (0.75, 0.62, 0.45), (0.6, 0.47, 0.32)), bevel=0.01)
K.mug(HOSP, HOSPP + Vector((-1.45, 0.3, 0.72)), color=(0.9, 0.9, 0.92))
K.potted_plant(HOSP, HOSPP + Vector((2.4, 2.4, 0)), h=1.2, seed=9)
K.picture_frame(HOSP, HOSPP + Vector((-0.9, 3.57, 1.65)), (0.8, 0.55), seed=7)
SEAT_H = HOSPP + Vector((0, 0.30, 0.72))             # his hips when seated on the bed edge
# the IV drip chamber (beat 8): a clear chamber under the bag with a drop falling through it
IV_CH = HOSPP + Vector((0.78 + 0.13, -0.12, 1.58))
ch_glass = K.plastic("DripChamber", (0.92, 0.96, 1.0), 0.05, coat=0.5)
ch_glass.node_tree.nodes["Principled BSDF"].inputs["Transmission Weight"].default_value = 0.9
K.cyl("DripChamber", HOSP, 0.009, 0.05, IV_CH, ch_glass, verts=24)
drip_m = glowy("DripDrop", (0.75, 0.88, 1.0), rough=0.05, sss=0.0, emit=1.5)
drip = K.sphere("Drip", HOSP, 0.0035, IV_CH + Vector((0, 0, 0.02)), drip_m, scale=(1, 1, 1.3), subdiv=2)

# ---------------------------------------------------------------- XRAY: a cutaway of his small intestine
def gut_axis(x):
    return GUTP + Vector((x, 0.03 * math.sin(2.1 * x), 0.035 * math.sin(2.8 * x + 1.0)))


def half_pipe(name, coll, r, x0, x1, mat, phi=110, nx=60, na=24):
    """The back half of a tube around gut_axis (the camera side, -Y, stays open)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    rows = []
    for i in range(nx + 1):
        x = x0 + (x1 - x0) * i / nx
        c = gut_axis(x)
        row = []
        for j in range(na + 1):
            a = math.radians(-phi + 2 * phi * j / na)
            row.append(bm.verts.new(c + Vector((0, r * math.cos(a), r * math.sin(a)))))
        rows.append(row)
    for i in range(nx):
        for j in range(na):
            bm.faces.new((rows[i][j], rows[i + 1][j], rows[i + 1][j + 1], rows[i][j + 1]))
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    o = bpy.data.objects.new(name, me)
    coll.objects.link(o)
    o.data.materials.append(mat)
    return o


GUT_R = 0.165
mucosa_m = K.plastic("GutMucosa", (0.50, 0.12, 0.14), 0.45, sss=0.3)
half_pipe("GutWall", GUT, GUT_R, -1.3, 1.3, mucosa_m)
shell = K.tube("GutShell", GUT, [gut_axis(x) for x in (-1.3, -0.65, 0.0, 0.65, 1.3)], GUT_R + 0.01,
               xglow("GutGlow", (1.0, 0.42, 0.36), 2.2, blend=0.35, core=0.0), res=12)
shell.visible_diffuse = shell.visible_glossy = shell.visible_transmission = False
villus_m = K.plastic("Villus", (0.86, 0.34, 0.36), 0.35, sss=0.45)
rngv = random.Random(5)
for i in range(30):
    x = -1.16 + i * 0.08
    for j in range(13):
        a = math.radians(-105 + j * 17.5 + rngv.uniform(-4, 4))
        out = Vector((0, math.cos(a), math.sin(a)))
        L_ = rngv.uniform(0.020, 0.030)
        c = gut_axis(x + rngv.uniform(-0.02, 0.02)) + out * (GUT_R - L_)
        o = K.sphere(f"Villus{i}_{j}", GUT, 1.0, c, villus_m, scale=(0.0075, 0.0075, L_), subdiv=2)
        o.rotation_euler = out.to_track_quat("Z", "Y").to_euler()
# yeast: budding ovoid cells floating in the gut (kept off the camera side so they never block the lens)
yeast_m = glowy("Yeast", (0.96, 0.82, 0.50), rough=0.35, sss=0.4, emit=0.6)
CELLS = []
rngy = random.Random(9)
while len(CELLS) < 46:
    x = rngy.uniform(-0.85, 0.85)
    r_, a = rngy.uniform(0.0, 0.105), rngy.uniform(0, 2 * math.pi)
    off = Vector((0, r_ * math.cos(a), r_ * math.sin(a)))
    if off.y < -0.035 or any((c["p"] - (gut_axis(x) + off)).length < 0.042 for c in CELLS):
        continue
    s = rngy.uniform(0.85, 1.25)
    o = K.sphere(f"Yeast{len(CELLS)}", GUT, 1.0, gut_axis(x) + off, yeast_m, scale=(0.017 * s, 0.013 * s, 0.013 * s), subdiv=3)
    o.rotation_euler = (rngy.uniform(0, 6.3), rngy.uniform(0, 6.3), rngy.uniform(0, 6.3))
    if rngy.random() < 0.55:                          # a bud on one end (how yeast divides)
        bud = K.sphere(f"YeastBud{len(CELLS)}", GUT, 1.0, (0.95, 0, 0), yeast_m, scale=(0.55, 0.62, 0.62), subdiv=3)
        bud.parent = o
    CELLS.append({"o": o, "p": o.location.copy(), "s": tuple(o.scale), "rot": tuple(o.rotation_euler), "ph": rngy.uniform(0, 9)})
HERO_CELL = min(CELLS, key=lambda c: (c["p"] - (GUTP + Vector((0.05, -0.02, 0.0)))).length)
# food crumbs drifting through (beat 5), sugar crystals flooding in (beat 7), golden alcohol bubbles, antifungal
crumb_m = K.plastic("Crumb", (0.80, 0.58, 0.30), 0.7)
CRUMBS = []
for k in range(14):
    x = rngy.uniform(-0.9, 0.9)
    off = Vector((0, rngy.uniform(-0.02, 0.09), rngy.uniform(-0.10, 0.06)))
    o = K.sphere(f"Crumb{k}", GUT, 1.0, gut_axis(x) + off, crumb_m, scale=(rngy.uniform(0.010, 0.02), rngy.uniform(0.008, 0.015), rngy.uniform(0.008, 0.014)), subdiv=2)
    tex = bpy.data.textures.new(f"CrumbTex{k}", "CLOUDS")
    tex.noise_scale = 0.3
    dp = o.modifiers.new("Lumpy", "DISPLACE")
    dp.texture, dp.strength = tex, 0.35
    CRUMBS.append((o, o.location.copy(), rngy.uniform(0, 6)))
sugar_m = glowy("Sugar", (0.97, 0.97, 1.0), rough=0.15, sss=0.0, emit=0.8)
SUGAR = []
for k in range(40):
    tgt = CELLS[k % len(CELLS)]["p"] + Vector((rngy.uniform(-0.02, 0.02), rngy.uniform(-0.02, 0.0), rngy.uniform(-0.015, 0.02)))
    o = K.rbox(f"Sugar{k}", GUT, (0.011, 0.011, 0.011), tgt, sugar_m, bevel=0.0015, segments=1)
    o.rotation_euler = (rngy.uniform(0, 6.3), rngy.uniform(0, 6.3), rngy.uniform(0, 6.3))
    SUGAR.append((o, tgt, rngy.uniform(-0.12, 0.12), Vector((rngy.uniform(-1.6, -1.2), rngy.uniform(-0.03, 0.06), rngy.uniform(-0.08, 0.08)))))
bubble_m = xglow("Ethanol", (1.0, 0.78, 0.30), 3.2, blend=0.25, core=0.12)
BUBBLES = []
for k in range(90):
    BUBBLES.append((K.sphere(f"Bubble{k}", GUT, 1.0, GUTP, bubble_m, subdiv=2), CELLS[k % len(CELLS)], rngy.random(),
                    rngy.uniform(0.5, 0.9), rngy.uniform(0.005, 0.012), Vector((rngy.uniform(0.02, 0.10), rngy.uniform(-0.01, 0.02), 1.0))))
for b_ in BUBBLES:
    b_[0].visible_diffuse = b_[0].visible_glossy = b_[0].visible_transmission = False
drug_m = glowy("Antifungal", (0.25, 0.65, 1.0), rough=0.2, sss=0.0, emit=6.0)
DRUGS = [(K.sphere(f"Drug{k}", GUT, 0.0055, GUTP, drug_m, subdiv=2), CELLS[(k * 7) % len(CELLS)], rngy.uniform(0, 0.6),
          Vector((rngy.uniform(-0.25, 0.25), rngy.uniform(-0.02, 0.04), -0.30))) for k in range(36)]
# a blood vessel running under the gut: its blood turns amber when the alcohol pours in (beat 7)
blood_m = glowy("Blood", (0.75, 0.04, 0.04), rough=0.3, sss=0.2, emit=1.2)
VES = [GUTP + Vector((x, -0.03, -0.27 + 0.02 * math.sin(3 * x))) for x in (-1.4, -0.7, 0.0, 0.7, 1.4)]
K.tube("Vessel", GUT, VES, 0.045, blood_m, res=10)
FLOW = [K.sphere(f"Flow{k}", GUT, 1.0, GUTP, glowy("FlowGold", (1.0, 0.6, 0.12), emit=5.0), scale=(0.012, 0.008, 0.008), subdiv=2) for k in range(24)]
GUTC = GUTP + Vector((0.0, 0.0, 0.0))

# ---------------------------------------------------------------- props on him: breathalyzer, glucose drink, belly glow
DEV = K.empty("Breathalyzer", CAST, (0, 0, 0))
dev_body = K.plastic("DevYellow", (0.95, 0.70, 0.06), 0.35, coat=0.3)
dev_face = K.plastic("DevFace", (0.02, 0.02, 0.025), 0.3, coat=0.5)
lcd_m = glowy("DevLCD", (0.05, 0.08, 0.06), rough=0.2, sss=0.0, emit=0.3)
seg_m = glowy("DevSegment", (1.0, 0.12, 0.05), rough=0.2, sss=0.0, emit=12.0)
dev_parts = [K.rbox("DevBody", CAST, (0.056, 0.030, 0.135), (0, 0, 0), dev_body, bevel=0.010),
             K.rbox("DevFacePlate", CAST, (0.046, 0.004, 0.105), (0, -0.0155, -0.006), dev_face, bevel=0.004),
             K.rbox("DevLCD", CAST, (0.040, 0.002, 0.024), (0, -0.0178, 0.026), lcd_m, bevel=0.002),
             K.cyl("DevButton", CAST, 0.007, 0.004, (0, -0.0175, -0.030), K.plastic("DevBtn", (0.1, 0.6, 0.15), 0.3), rot=(math.radians(90), 0, 0), verts=20),
             K.tube("DevMouthpiece", CAST, [Vector((0, 0.004, 0.064)), Vector((0, 0.012, 0.085)), Vector((0, 0.04, 0.10))], 0.0055,
                    K.plastic("Mouthpiece", (0.95, 0.96, 0.98), 0.3))]
SEGS = {"a": (0, 0.5, 1), "b": (0.5, 0.25, 0), "c": (0.5, -0.25, 0), "d": (0, -0.5, 1), "e": (-0.5, -0.25, 0), "f": (-0.5, 0.25, 0), "g": (0, 0, 1)}
DIGITS = {0: "abcdef", 1: "bc", 2: "abged", 3: "abgcd", 4: "fgbc", 5: "afgcd", 6: "afgedc", 7: "abc", 8: "abcdefg", 9: "abcfgd"}
DW, DH = 0.0072, 0.0145
digit_objs = []
for d_, cx in enumerate((-0.0115, 0.0035, 0.0135)):
    segs = {}
    for nm, (sx, sz, horiz) in SEGS.items():
        size = (DW * 0.9, 0.0012, 0.0014) if horiz else (0.0014, 0.0012, DH * 0.45)
        segs[nm] = K.rbox(f"Seg{d_}{nm}", CAST, size, (cx + sx * DW, -0.0192, 0.026 + sz * DH), seg_m, bevel=0.0003, segments=1)
    digit_objs.append(segs)
dp_obj = K.rbox("SegDot", CAST, (0.0016, 0.0012, 0.0016), (-0.0045, -0.0192, 0.026 - 0.5 * DH), seg_m, bevel=0.0003, segments=1)
lcd_pt = K.empty("DevLCDAim", CAST, (0, -0.018, 0.026))
K.parent(dev_parts + [o for d_ in digit_objs for o in d_.values()] + [dp_obj, lcd_pt], DEV)
CUP = K.empty("GlucoseDrink", CAST, (0, 0, 0))
cup_glass = K.plastic("CupClear", (0.95, 0.97, 1.0), 0.04, coat=0.4)
cup_glass.node_tree.nodes["Principled BSDF"].inputs["Transmission Weight"].default_value = 0.9
juice_m = glowy("GlucoseOrange", (1.0, 0.42, 0.04), rough=0.1, sss=0.5, emit=0.25)
cup_parts = [K.lathe("CupWall", CAST, [(0.0, 0.0), (0.030, 0.0), (0.036, 0.115), (0.034, 0.115), (0.028, 0.004), (0.0, 0.004)], (0, 0, -0.05), cup_glass),
             K.cyl("Juice", CAST, 0.031, 0.075, (0, 0, -0.008), juice_m, verts=32)]
K.parent(cup_parts, CUP)
REST_HIPS = him.hips0.copy()
BELLY = Vector((him.x0, REST_HIPS.y - 0.03, REST_HIPS.z + 0.14))
belly_glow = K.sphere("BellyGlow", CAST, 1.0, BELLY, xglow("BellyAmber", (1.0, 0.62, 0.18), 4.0, blend=0.35, core=0.25),
                      scale=(0.11, 0.08, 0.10), subdiv=3)
him.parent_to_bone(belly_glow, "Spine")
BELLY_BUB = []
for k in range(14):
    o = K.sphere(f"BellyBubble{k}", CAST, 1.0, BELLY, bubble_m, scale=(0.009,) * 3, subdiv=2)
    him.parent_to_bone(o, "Spine")
    BELLY_BUB.append((o, Vector((random.uniform(-0.07, 0.07), random.uniform(-0.04, 0.03), random.uniform(-0.07, 0.0))), random.random()))

# ---------------------------------------------------------------- shots (start, camera, set, his pose)
SHOTS = [
    (0.0, "LightsFace", "road", "stand"),
    (at(0, 0.50), "RoadWide", "road", "stand"),
    (B[1], "BlowMed", "road", "stand"),
    (at(1, 0.45), "MeterECU", "road", "stand"),
    (B[2], "RoofLow", "road", "roof"),
    (at(2, 0.50), "SoberFace", "road", "roof"),
    (B[3], "BodyX", "road", "stand"),
    (at(3, 0.50), "GutDive", "xray", "stand"),
    (B[4], "YeastOrbit", "xray", "stand"),
    (at(4, 0.50), "YeastMacro", "xray", "stand"),
    (B[5], "HospWide", "hosp", "sit"),
    (at(5, 0.50), "DrinkCU", "hosp", "sit"),
    (SLO_A, "SugarSlomo", "xray", "sit"),
    (SLO_B, "DizzyCU", "hosp", "sit"),
    (B[7], "IVDrip", "hosp", "sit"),
    (DRUG, "YeastDie", "xray", "sit"),
    (B[8], "HospOrbit", "hosp", "sit"),
    (B[9], "BreweryX", "hosp", "sit"),
    (at(9, 0.42), "Closer", "hosp", "sit"),
]


def shot_at(t):
    return max((s for s in SHOTS if s[0] <= t + 1e-6), key=lambda s: s[0])


SH = [shot_at(t) for t in T]
SET_OF = [s[2] for s in SH]


def him_root(s):
    """(location, euler) of his rig object. X-ray shots keep him where the story has him (hidden)."""
    if s[3] == "sit":
        return SEAT_H - REST_HIPS, (0, 0, 0)
    rz = -math.pi / 2 if s[3] == "roof" else 0.0          # roof: turned to face his car (-X)
    off = Matrix.Rotation(rz, 3, "Z") @ Vector((him.x0, REST_HIPS.y, 0))
    return P_ROAD - off, (0, 0, rz)


# ---------------------------------------------------------------- performance
BLINKS = [1.0 + 2.9 * k for k in range(60) if 1.0 + 2.9 * k < DUR]


def strobe(t, ph):
    """A police light-bar flash pattern: two quick flashes per half cycle."""
    u = (t * 1.9 + ph) % 1.0
    return max(env(u, 0.0, 0.02, 0.10, 0.13), env(u, 0.18, 0.20, 0.28, 0.31))


def channels(t):
    ch = {}
    ch["caught"] = env(t, -1, 0, B[1], B[1] + 0.3)                          # beat 1: wide eyes in the strobe
    ch["blow"] = env(t, B[1] - 0.05, BLOW + 0.15, B[2] - 0.25, B[2])        # device up at his mouth
    ch["puff"] = env(t, BLOW + 0.1, BLOW + 0.25, READ_A - 0.1, READ_A + 0.1)
    ch["shock"] = env(t, READ_B - 0.1, READ_B + 0.1, B[2], B[2] + 0.2)
    ch["roof"] = env(t, B[2] - 0.05, SLAP, B[3] - 0.1, B[3])
    ch["shake"] = env(t, at(2, 0.55), at(2, 0.62), BE[2] - 0.15, BE[2])     # "no, I'm sober"
    ch["drink"] = env(t, at(5, 0.45), at(5, 0.62), BE[5] - 0.2, BE[5] + 0.05)
    ch["gulp"] = sum(spike(t, at(5, f), 0.05, 0.18) for f in (0.70, 0.84))
    ch["dizzy"] = env(t, SLO_B - 0.2, SLO_B + 0.3, B[7] + 0.3, B[7] + 0.9)
    ch["relief"] = ramp(t, B[8] - 0.2, B[8] + 0.6)
    ch["smile"] = max(0.5 * ch["relief"], ramp(t, SMILE - 0.3, SMILE + 0.3))
    ch["blink"] = max((env(t, b_ - 0.03, b_, b_ + 0.05, b_ + 0.12) for b_ in BLINKS), default=0.0)
    return ch


legs_sit, legs_stand = him.seated_legs(), him.standing_legs()
MOUTH = him.mouth.copy()
SH_L, SH_R = him.bone_rest_head("LeftArm"), him.bone_rest_head("RightArm")
SIDE_L = REST_HIPS + Vector((0.22, 0.02, -0.12))
SIDE_R = REST_HIPS + Vector((-0.22, 0.02, -0.12))
THIGH_L = REST_HIPS.lerp(him.bone_rest_head("LeftLeg"), 0.6) + Vector((0.03, -0.25, 0.07))
THIGH_R = REST_HIPS.lerp(him.bone_rest_head("RightLeg"), 0.6) + Vector((-0.03, -0.25, 0.07))
mouth_pt = him.anchor("Mouth", "Head", MOUTH + Vector((0, -0.02, 0)), CAST)
face_pt = him.anchor("Face", "Head", Vector((him.x0, him.nose.y + 0.05, him.nose.z - 0.01)), CAST)
eyes_mid = him.anchor("Eyes", "Head", (him.eye_l + him.eye_r) / 2, CAST)
chest_pt = him.anchor("Chest", "Spine2", him.bone_rest_head("Spine2"), CAST)
belly_pt = him.anchor("Belly", "Spine", BELLY, CAST)
sip_pt = him.anchor("Sip", "Head", MOUTH + Vector((-0.03, -0.11, -0.10)), CAST)      # the drinking hand's target
him.hand_follow("Right", sip_pt, "ToSip")

for i, t in enumerate(T):
    s = SH[i]
    ch = channels(t)
    sit = s[3] == "sit"
    roof = ch["roof"] if s[3] == "roof" else 0.0
    br = math.sin(t * 2 * math.pi / 3.6)
    dz = ch["dizzy"]
    sway = dz * math.sin(t * 2 * math.pi / 2.3)
    shake = 16 * ch["shake"] * math.sin(2 * math.pi * 2.6 * (t - at(2, 0.55)))
    spec = {
        "Hips": [(A.Z, 0.6 * wobble(t, 1))],
        "Spine": [(A.X, (-6 if sit else 0) + 0.6 * br + 22 * roof - 3 * ch["shock"]), (A.Z, 0.8 * wobble(t, 2)), (A.Y, 4 * sway)],
        "Spine1": [(A.X, (-2 if sit else 0) + 0.7 * br + 8 * roof - 2 * ch["relief"])],
        "Spine2": [(A.X, 1.5 + 0.6 * br + 4 * roof)],
        "Neck": [(A.X, -4 * roof + 3 * dz + 2 * ch["drink"]), (A.Z, 1.2 * wobble(t, 4) + 0.4 * shake)],
        "Head": [(A.X, 1.0 * wobble(t, 7, 0.6) - 8 * roof - 6 * ch["drink"] + 6 * dz + 4 * ch["gulp"]),
                 (A.Z, 1.6 * wobble(t, 5, 0.5) + shake),
                 (A.Y, 1.0 * wobble(t, 6) + 9 * sway + 4 * ch["caught"] * wobble(t, 8, 1.5))],
        "LeftShoulder": [(A.Y, 6 * roof + 2 * ch["relief"])],
        "RightShoulder": [(A.Y, -6 * roof - 4 * ch["blow"] - 3 * ch["drink"])],
    }
    rots = {}
    for bone, axes in spec.items():
        if him.has(bone):
            q = A.Quaternion()
            for axis, deg in axes:
                q = q @ him.q(bone, axis, deg)
            rots[bone] = q
    rots.update(legs_sit if sit else legs_stand)
    for bone in him.fingers():
        j = int(bone[-1])
        curl = ({1: 22, 2: 30, 3: 22} if "Thumb" not in bone else {1: 8, 2: 14, 3: 10})[j]
        if bone.startswith("Right"):
            curl += 45 * max(ch["blow"], ch["drink"] if sit else 0.0) + (40 if sit and t >= B[5] and t < BE[5] + 0.2 else 0)
        curl *= 1 - 0.7 * roof                                       # flat palms on the roof
        rots[bone] = A.Quaternion((1, 0, 0), math.radians(curl))
    sh = {}
    for side in ("Left", "Right"):
        sh[f"eyeBlink{side}"] = min(1.0, ch["blink"] + 0.45 * dz + 0.15 * ch["smile"])
        sh[f"eyeWide{side}"] = 0.6 * ch["caught"] + 0.8 * ch["shock"]
        sh[f"browDown{side}"] = 0.35 * roof + 0.25 * ch["shake"]
        sh[f"eyeSquint{side}"] = 0.25 * ch["shake"] + 0.3 * ch["smile"] + 0.2 * dz
        sh[f"mouthFrown{side}"] = 0.35 * ch["shake"] + 0.25 * ch["caught"]
        sh[f"mouthSmile{side}"] = 0.85 * ch["smile"] + 0.15 * dz
        sh[f"cheekSquint{side}"] = 0.4 * ch["smile"]
        sh[f"mouthPress{side}"] = 0.3 * ch["shake"]
    sh["browInnerUp"] = 0.7 * ch["caught"] + 0.8 * ch["shock"] + 0.3 * dz
    sh["cheekPuff"] = 0.9 * ch["puff"]
    sh["mouthPucker"] = 0.8 * ch["puff"] + 0.4 * ch["drink"]
    sh["jawOpen"] = 0.25 * ch["shock"] + 0.12 * dz + 0.05 * ch["shake"]
    # hands: road = by his sides; blow = right hand holds the breathalyzer under his mouth; roof = both palms flat on
    # the roof in front of him; seated = on his thighs; drink = right hand to the Sip anchor (Copy Location)
    if sit:
        ikl = THIGH_L + Vector((0.0, 0.0, 0.02 * sway))
        ikr = THIGH_R + Vector((-0.02, 0.06, 0.08)) * (1 if B[5] <= t < BE[5] + 0.2 else 0)
    else:
        ikl, ikr = SIDE_L + Vector((0, 0, 0.004 * br)), SIDE_R + Vector((0, 0, 0.004 * br))
        ikr = ikr.lerp(MOUTH + Vector((-0.02, -0.11, -0.13)), ch["blow"])
        ikl = ikl.lerp(Vector((him.x0 + 0.24, REST_HIPS.y - 0.62, 1.47 - 0.02 * ch["shake"])), roof)
        ikr = ikr.lerp(Vector((him.x0 - 0.24, REST_HIPS.y - 0.60, 1.47)), roof)
    follow = {"ToSip": ch["drink"] if sit else 0.0}
    him.record(rots, sh, ikl, ikr, aim=(0.0, 0.0), follow=follow, root=him_root(s))
him.bake(FRAMES)
for fc in A.fcurves_of(him.rig):
    if fc.data_path in ("location", "rotation_euler"):
        fc.keyframe_points.foreach_set("interpolation", [0] * len(fc.keyframe_points))   # teleports are cuts

# ---------------------------------------------------------------- props that ride on his right hand (world space)
hand_pb = him.rig.pose.bones[A.MX + "RightHand"]
dev_locs, cup_locs, cup_rots = [], [], []
for i, t in enumerate(T):
    ch = channels(t)
    held_dev = SET_OF[i] == "road" and ch["blow"] > 0.02
    held_cup = SET_OF[i] == "hosp" and B[5] <= t < BE[5] + 0.2
    lips = None
    if held_dev or held_cup:
        scene.frame_set(i + 1)
        hp = him.rig.matrix_world @ hand_pb.tail
        lips = mouth_pt.matrix_world.translation + Vector((0, -0.07, -0.035))
    else:
        hp = Vector((0, 0, -200))
    dev_locs.append(hp + Vector((0.01, -0.025, 0.035)))
    # the cup rides on the hand, and is held to his lips while he drinks (whatever the rig's arm reach)
    cup_locs.append((hp + Vector((0.0, -0.03, 0.03))).lerp(lips, ch["drink"]) if lips else hp)
    cup_rots.append((math.radians(-55) * ch["drink"], 0, 0))
bake_vec(DEV, "location", dev_locs)
bake_vec(DEV, "rotation_euler", [(math.radians(-8), 0, math.radians(-12)) for _ in T])
bake_vec(CUP, "location", cup_locs)
bake_vec(CUP, "rotation_euler", cup_rots)


def reading(t):
    return 0.41 * smooth(ramp(t, READ_A, READ_B))


for d_, segs in enumerate(digit_objs):
    for nm, o in segs.items():
        vals = []
        for t in T:
            r = int(round(reading(t) * 100))
            dig = (0, (r // 10) % 10, r % 10)[d_]
            vals.append(1.0 if nm in DIGITS[dig] else 0.0)
        bake_vec(o, "scale", [(v, v, v) for v in vals], interp="CONSTANT")
bake(seg_m.node_tree, BSDF + '["Emission Strength"].default_value',
     [12.0 * (1.0 if t < READ_B else (0.25 + 0.75 * (math.sin(2 * math.pi * 4 * (t - READ_B)) > 0))) for t in T])
bake(lcd_m.node_tree, BSDF + '["Emission Strength"].default_value', [0.3 + 2.5 * spike(t, READ_B, 0.02, 0.2) for t in T])

# police light bar strobe + the drip falling through the chamber
bake(red_m.node_tree, BSDF + '["Emission Strength"].default_value', [60 * strobe(t, 0.05) + 2 for t in T])
bake(blue_m.node_tree, BSDF + '["Emission Strength"].default_value', [60 * strobe(t, 0.55) + 2 for t in T])
bake_vec(drip, "location", [IV_CH + Vector((0, 0, 0.02 - 0.04 * smooth(((t - B[7]) / 0.55) % 1.0))) for t in T])

# belly glow + bubbles in the X-ray reveal (beat 4)
XSHOTS = ("BodyX", "BreweryX")                    # his body goes X-ray and his belly glows amber


def xray_on(i):
    s = SH[i]
    return ramp(T[i], s[0] + 0.05, s[0] + 0.35) if s[1] in XSHOTS else 0.0


bake(belly_glow.data.materials[0].node_tree, 'nodes["Emission"].inputs["Strength"].default_value',
     [4.0 * (0.7 + 0.3 * math.sin(2 * math.pi * 1.6 * t)) * xray_on(i) for i, t in enumerate(T)])
for o, off, ph in BELLY_BUB:
    locs, sc = [], []
    for t in T:
        u = (ph + 0.8 * t) % 1.0
        locs.append(BELLY + off + Vector((0.01 * math.sin(7 * t + ph * 9), 0, 0.12 * u)))
        sc.append(0.009 * smooth(min(u, 1 - u) / 0.15) * xray_on(F(t) - 1))
    bake_vec(o, "location", locs)
    bake_vec(o, "scale", [(v, v, v) for v in sc])

# ---------------------------------------------------------------- the gut: brewing, the sugar hit, the antifungal
def brew(t):
    """How hard the yeast is fermenting: a steady simmer, a blast at the sugar hit, nothing after the drug."""
    b0 = 0.55 * ramp(t, B[3], B[3] + 0.3)
    b1 = 0.6 * ramp(warp(t), HIT_ACT - 0.02, HIT_ACT + 0.1) if t >= SLO_A else 0.0
    return (b0 + b1) * (1 - ramp(t, DRUG + 0.25, DRUG + 1.1))


def alive(t):
    return 1.0 - ramp(t, DRUG + 0.15, DRUG + 1.0)


TA = [warp(t) for t in T]
for c in CELLS:
    locs, rots, scl = [], [], []
    for i, t in enumerate(T):
        ta = TA[i]
        a_ = alive(t)
        drift = Vector((0.008 * math.sin(0.7 * ta + c["ph"]), 0.004 * math.sin(0.9 * ta + 2 * c["ph"]), 0.006 * math.sin(0.8 * ta + 3 * c["ph"])))
        locs.append(c["p"] + drift * a_)
        rots.append(tuple(r + 0.25 * ta * a_ for r in c["rot"]))
        k = (1.0 + 0.04 * math.sin(3.0 * ta + c["ph"])) * (1 + 0.22 * spike(ta, HIT_ACT + 0.03, 0.03, 0.25)) * (0.72 + 0.28 * a_)
        scl.append(tuple(v * k for v in c["s"]))
    bake_vec(c["o"], "location", locs)
    bake_vec(c["o"], "rotation_euler", rots)
    bake_vec(c["o"], "scale", scl)
bake_vec(yeast_m.node_tree, BSDF + '["Base Color"].default_value',
         [tuple(a * alive(t) + b * (1 - alive(t)) for a, b in zip((0.96, 0.82, 0.50), (0.32, 0.31, 0.29))) + (1,) for t in T], n=4)
bake(yeast_m.node_tree, BSDF + '["Emission Strength"].default_value',
     [(0.6 + 3.0 * spike(TA[i], HIT_ACT + 0.03, 0.03, 0.3)) * alive(t) for i, t in enumerate(T)])
for o, p0, ph in CRUMBS:
    bake_vec(o, "location", [p0 + Vector((0.05 * math.sin(0.3 * TA[i] + ph), 0.006 * math.sin(0.8 * TA[i] + ph), 0.01 * math.sin(0.5 * TA[i] + ph))) for i in range(len(T))])
    bake_vec(o, "rotation_euler", [(0.3 * TA[i] + ph, 0.2 * TA[i], ph) for i in range(len(T))])
for o, tgt, jit, src in SUGAR:
    locs, scl = [], []
    for i, t in enumerate(T):
        ta = TA[i]
        arrive = HIT_ACT + 0.02 * jit / 0.12
        u = ramp(ta, ACT_A - 0.15, arrive)
        p = (tgt + src).lerp(tgt, 1 - (1 - u) ** 2) + Vector((0, 0, 0.03 * math.sin(math.pi * u)))
        locs.append(p)
        on = 1.0 if t >= SLO_A - 0.05 else 0.0
        scl.append(on * (1.0 - ramp(ta, arrive + 0.02, arrive + 0.22)))
    bake_vec(o, "location", locs)
    bake_vec(o, "scale", [(v, v, v) for v in scl])
    bake(o, "rotation_euler", [jit * 40 * TA[i] for i in range(len(T))], index=2)
for o, cell, ph, spd, size, dirv in BUBBLES:
    locs, scl, acc = [], [], ph
    for i, t in enumerate(T):
        dta = TA[i] - TA[i - 1] if i else 0.0
        boost = ramp(TA[i], HIT_ACT, HIT_ACT + 0.12) if t >= SLO_A else 0.0
        acc += dta * spd * (1 + 1.4 * boost)
        u = acc % 1.0
        locs.append(cell["p"] + Vector((dirv.x * u, dirv.y * u, 0.14 * u)) + Vector((0.006 * math.sin(11 * TA[i] + ph * 7), 0, 0)))
        scl.append(size * (1 + 0.5 * boost) * smooth(min(u, 1 - u) / 0.12) * min(1.0, brew(t) / 0.55))
    bake_vec(o, "location", locs)
    bake_vec(o, "scale", [(v, v, v) for v in scl])
for o, cell, dly, src in DRUGS:
    locs, scl = [], []
    for t in T:
        u = ramp(t, DRUG - 0.1 + dly, DRUG + 0.75 + dly)
        locs.append((cell["p"] + src).lerp(cell["p"] + Vector((0, -0.012, 0)), 1 - (1 - u) ** 2))
        scl.append(1.0 if t >= DRUG - 0.15 else 0.0)
    bake_vec(o, "location", locs)
    bake_vec(o, "scale", [(v, v, v) for v in scl], interp="CONSTANT")
AMBER = [ramp(TA[i], HIT_ACT + 0.03, HIT_ACT + 0.18) if t >= SLO_A else 0.0 for i, t in enumerate(T)]
bake_vec(blood_m.node_tree, BSDF + '["Base Color"].default_value',
         [tuple(r + (a - r) * k for r, a in zip((0.75, 0.04, 0.04), (1.0, 0.50, 0.08))) + (1,) for k in AMBER], n=4)
bake_vec(blood_m.node_tree, BSDF + '["Emission Color"].default_value',
         [tuple(r + (a - r) * k for r, a in zip((0.75, 0.04, 0.04), (1.0, 0.50, 0.08))) + (1,) for k in AMBER], n=4)
bake(blood_m.node_tree, BSDF + '["Emission Strength"].default_value', [1.2 + 3.5 * k for k in AMBER])
for k_, o in enumerate(FLOW):
    ph = k_ / len(FLOW)
    locs, scl = [], []
    for i, t in enumerate(T):
        u = (ph + 0.35 * TA[i]) % 1.0
        x = -1.3 + 2.6 * u
        locs.append(GUTP + Vector((x, -0.03 + 0.02 * math.sin(k_ * 2.3), -0.27 + 0.02 * math.sin(3 * x) + 0.02 * math.cos(k_ * 1.7))))
        scl.append(AMBER[i])
    bake_vec(o, "location", locs)
    bake_vec(o, "scale", [(0.012 * v, 0.008 * v, 0.008 * v) for v in scl])

# ---------------------------------------------------------------- X-ray look on his body (driven by scene["xray"])
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
bake(scene, '["xray"]', [xray_on(i) for i in range(len(T))])


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


for name, coll in (("road", ROAD), ("hosp", HOSP), ("xray", GUT)):
    key_vis([o for o in coll.all_objects if not o.hide_render], lambda i, name=name: SET_OF[i] == name)
key_vis([o for o in him.rig.children_recursive if o.type in ("MESH", "CURVES", "CURVE") and o not in
         (belly_glow, *[b[0] for b in BELLY_BUB])], lambda i: SET_OF[i] in ("road", "hosp"))
key_vis([belly_glow, *[b[0] for b in BELLY_BUB]], lambda i: SH[i][1] in XSHOTS)
key_vis([DEV, *DEV.children_recursive], lambda i: SET_OF[i] == "road" and channels(T[i])["blow"] > 0.02)
key_vis([CUP, *CUP.children_recursive], lambda i: SET_OF[i] == "hosp" and B[5] <= T[i] < BE[5] + 0.2)

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
WCOL = {"road": ((0.012, 0.020, 0.045), 1.0), "hosp": ((0.66, 0.74, 0.80), 0.30), "xray": ((0.030, 0.008, 0.010), 1.0)}
cols = [WCOL[s] for s in SET_OF]
bake_vec(wnt, 'nodes["Background"].inputs[0].default_value', [(*c_, 1) for c_, _ in cols], n=4, interp="CONSTANT")
bake(wnt, 'nodes["Background"].inputs[1].default_value', [s_ for _, s_ in cols], interp="CONSTANT")
bake(scene, "view_settings.exposure", [-0.35 + 0.8 * sum(spike(t, s[0], 0.005, 0.05) for s in SHOTS if s[2] == "xray" or s[1] in XSHOTS)
                                       + 0.6 * spike(t, HIT, 0.02, 0.12) + 0.3 * spike(t, READ_B, 0.02, 0.1) for t in T])


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


HEAD_R = P_ROAD + Vector((0, 0, 1.6))
HEAD_H = SEAT_H + Vector((0, -0.05, 0.62))
moon = bpy.data.lights.new("Moon", "SUN")
moon.energy, moon.angle, moon.color = 0.12, math.radians(2), (0.55, 0.65, 1.0)
moon_o = bpy.data.objects.new("Moon", moon)
ROAD.objects.link(moon_o)
moon_o.rotation_euler = Euler((math.radians(50), 0, math.radians(30)))
cop_red = _light("POINT", "CopRedLight", ROAD, COP + Vector((0.3, 0.2, 1.75)), HEAD_R, 2600, 0.15, (1.0, 0.05, 0.03))
cop_blue = _light("POINT", "CopBlueLight", ROAD, COP + Vector((-0.3, 0.2, 1.75)), HEAD_R, 2600, 0.15, (0.08, 0.25, 1.0))
LIGHTS = {
    "road": [moon_o, cop_red, cop_blue,
             _light("SPOT", "CopHeadlights", ROAD, COP + Vector((0.2, -2.3, 0.75)), HEAD_R + Vector((0, 0, -0.6)), 900, 0.3, (1.0, 0.96, 0.88)),
             _light("AREA", "StreetSodium", ROAD, ROADP + Vector((-3.4, -4.0, 6.3)), HEAD_R, 900, 0.6, (1.0, 0.70, 0.40)),
             _light("AREA", "SpillRed", ROAD, HEAD_R + Vector((0.9, 2.2, 0.6)), HEAD_R, 260, 0.8, (1.0, 0.05, 0.03)),
             _light("AREA", "SpillBlue", ROAD, HEAD_R + Vector((-0.9, 2.2, 0.6)), HEAD_R, 260, 0.8, (0.08, 0.25, 1.0)),
             _light("AREA", "FaceFill", ROAD, HEAD_R + Vector((1.6, -2.0, 0.6)), HEAD_R, 70, 2.0, (0.55, 0.65, 1.0))],
    "hosp": [_light("AREA", "HospKey", HOSP, HEAD_H + Vector((1.4, -1.5, 1.2)), HEAD_H, 300, 1.5, (0.96, 0.97, 1.0)),
             _light("AREA", "HospFill", HOSP, HEAD_H + Vector((-1.8, -1.5, 0.6)), HEAD_H, 110, 2.0, (0.82, 0.90, 1.0)),
             _light("AREA", "HospRim", HOSP, HEAD_H + Vector((-0.6, 1.4, 1.0)), HEAD_H, 180, 0.8, (0.92, 0.96, 1.0)),
             _light("AREA", "HospWindow", HOSP, HOSPP + Vector((1.7, 3.4, 1.6)), HEAD_H, 260, 1.3, (0.85, 0.92, 1.0))],
    "xray": [_light("AREA", "XKey", GUT, GUTC + Vector((0.5, -0.8, 0.7)), GUTC, 22, 0.8, (1.0, 0.88, 0.75)),
             _light("AREA", "XFill", GUT, GUTC + Vector((-0.8, -0.7, 0.1)), GUTC, 9, 1.0, (0.55, 0.70, 1.0)),
             _light("AREA", "XRim", GUT, GUTC + Vector((0.0, 0.6, 0.6)), GUTC, 12, 0.6, (1.0, 0.6, 0.6))],
}
BASE = {l.name: l.data.energy for ls in LIGHTS.values() for l in ls}
for set_name, ls in LIGHTS.items():
    for l in ls:
        vals = []
        for i, t in enumerate(T):
            e = BASE[l.name] * (SET_OF[i] == set_name)
            if l is cop_red or l.name == "SpillRed":
                e *= 0.05 + strobe(t, 0.05)
            elif l is cop_blue or l.name == "SpillBlue":
                e *= 0.05 + strobe(t, 0.55)
            elif l.name == "XKey":
                e *= 1 + 1.5 * spike(TA[i], HIT_ACT + 0.03, 0.03, 0.3) if t >= SLO_A else 1
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
# beat 1 hook (frame 1 = thumbnail): his face lit red/blue by the light bar behind him, already pushing in
a, b = span("LightsFace")
F0 = W(face_pt, mid("LightsFace"))
cams.cam("LightsFace", a, b, keys=[(a, F0 + Vector((0.36, -0.95, -0.04))), (b, F0 + Vector((0.24, -0.70, -0.02)))],
         lens=50, aim=face_pt, focus=eyes_mid, depth=0.18, shift_y=-0.06, shake=0.0012, ease="cine")
a, b = span("RoadWide")
RW = P_ROAD + Vector((-0.7, 2.6, 0.95))
cams.cam("RoadWide", a, b, keys=[(a, RW + Vector((3.4, -6.4, 0.65))), (b, RW + Vector((2.9, -5.6, 0.45)))],
         lens=28, aim=RW, focus=chest_pt, depth=2.0, shift_y=0.04, shake=0.001)
# beat 2: he blows; insert on the display counting up to 0.41
a, b = span("BlowMed")
F1 = W(face_pt, mid("BlowMed"))
cams.cam("BlowMed", a, b, keys=[(a, F1 + Vector((0.42, -0.95, -0.10))), (b, F1 + Vector((0.30, -0.74, -0.08)))],
         lens=45, aim=F1 + Vector((0, 0, -0.07)), focus=face_pt, depth=0.25, shift_y=-0.04, shake=0.0012)
a, b = span("MeterECU")
cams.cam("MeterECU", a, b, keys=[(a, Vector((0.04, -0.34, 0.05))), (b, Vector((0.025, -0.25, 0.04)))], lens=85, aim=lcd_pt,
         fstop=S.fstop_for(0.05, 85, 0.3), shake=0.0004, kicks=[(READ_B, 0.004, 0.2)])
# the MeterECU keys are relative to the device: re-bake them on top of its world position
md = cams.cams["MeterECU"]
locs = []
for i, t in enumerate(T):
    fc = [f for f in A.fcurves_of(md) if f.data_path == "location"]
    rel = Vector([f.evaluate(i + 1) for f in sorted(fc, key=lambda f: f.array_index)])
    locs.append(Vector(dev_locs[i]) + rel)
md.animation_data_clear()
bake_vec(md, "location", locs)
# beat 3: hands on the roof (low, lights behind), then he turns and shakes his head over the roof
a, b = span("RoofLow")
C2 = W(chest_pt, mid("RoofLow"))
cams.cam("RoofLow", a, b, keys=[(a, C2 + Vector((0.95, -1.55, -0.75))), (b, C2 + Vector((0.80, -1.25, -0.70)))],
         lens=28, aim=C2 + Vector((-0.25, 0, 0.1)), focus=chest_pt, depth=0.9, shake=0.0012, kicks=[(SLAP, 0.010, 0.2)])
a, b = span("SoberFace")
F2 = W(face_pt, mid("SoberFace"))
cams.cam("SoberFace", a, b, keys=[(a, F2 + Vector((-0.80, 0.06, 0.10))), (b, F2 + Vector((-0.62, 0.04, 0.08)))],
         lens=60, aim=face_pt, focus=eyes_mid, depth=0.15, shift_y=-0.05, shake=0.001)
# beat 4: X-ray body reveal, plunge into the belly; arrive in the gut
a, b = span("BodyX")
C3 = W(chest_pt, mid("BodyX"))
cams.cam("BodyX", a, b, keys=[(a, C3 + Vector((0.55, -2.1, -0.15))), (b, C3 + Vector((0.35, -1.5, -0.25)))],
         lens=35, aim=belly_pt, depth=0.6, shake=0.0008, plunge_out=(belly_pt, 0.35, 0.08))
a, b = span("GutDive")
cams.cam("GutDive", a, b, keys=[(a, GUTC + Vector((0.12, -0.42, 0.10))), (b, GUTC + Vector((0.26, -0.72, 0.16)))],
         lens=30, aim=GUTC, depth=0.5, shake=0.0004, ease="out")
# beat 5: yeast brewing
a, b = span("YeastOrbit")
cams.cam("YeastOrbit", a, b, path=S.orbit(GUTC + Vector((0, 0.02, 0)), 0.55, -24, 6, 0.10, 0.05), lens=40, aim=GUTC + Vector((0, 0.02, 0)),
         depth=0.25, shake=0.0004)
a, b = span("YeastMacro")
HC = HERO_CELL["p"]
cams.cam("YeastMacro", a, b, keys=[(a, HC + Vector((0.07, -0.20, 0.04))), (b, HC + Vector((0.035, -0.13, 0.025)))], lens=85, aim=HERO_CELL["o"],
         depth=0.035, shake=0.0002)
# beat 6: hospital, the glucose challenge
a, b = span("HospWide")
C4 = W(chest_pt, mid("HospWide"))
cams.cam("HospWide", a, b, keys=[(a, C4 + Vector((1.7, -2.9, 0.35))), (b, C4 + Vector((1.3, -2.3, 0.25)))], lens=28, aim=C4 + Vector((0.1, 0.3, -0.1)),
         focus=chest_pt, depth=1.2, shake=0.0008)
a, b = span("DrinkCU")
F4 = W(face_pt, mid("DrinkCU"))
cams.cam("DrinkCU", a, b, keys=[(a, F4 + Vector((0.34, -0.70, -0.04))), (b, F4 + Vector((0.24, -0.54, -0.03)))], lens=55, aim=face_pt,
         focus=eyes_mid, depth=0.18, shift_y=-0.05, shake=0.0008)
# beat 7 MONEY MOMENT: sugar floods in, slow motion, the yeast erupts and the blood turns amber
a, b = span("SugarSlomo")
cams.cam("SugarSlomo", a, b, keys=[(a, GUTC + Vector((-0.10, -0.62, 0.10))), (b, GUTC + Vector((0.02, -0.44, 0.04)))], lens=38,
         aim=GUTC + Vector((0, 0.01, -0.03)), depth=0.3, shake=0.0003, kicks=[(HIT, 0.008, 0.3)], ease="cine")
a, b = span("DizzyCU")
F5 = W(face_pt, mid("DizzyCU"))
cams.cam("DizzyCU", a, b, path=S.orbit(F5, 0.85, -18, 14, -0.02, 0.0), lens=50, aim=face_pt, focus=eyes_mid, depth=0.18,
         shift_y=-0.05, shake=0.0012)
# beat 8: the antifungal drip, then the yeast greys out
a, b = span("IVDrip")
cams.cam("IVDrip", a, b, keys=[(a, IV_CH + Vector((0.12, -0.30, 0.06))), (b, IV_CH + Vector((0.07, -0.21, 0.03)))], lens=85,
         aim=IV_CH + Vector((0, 0, 0.01)), depth=0.05, shake=0.0003)
a, b = span("YeastDie")
cams.cam("YeastDie", a, b, path=S.orbit(GUTC, 0.48, 18, -6, 0.12, 0.06), lens=42, aim=GUTC, depth=0.25, shake=0.0003)
# beats 9-10: recovered on the ward; matching push-in to his relieved face
a, b = span("HospOrbit")
C6 = W(chest_pt, mid("HospOrbit"))
cams.cam("HospOrbit", a, b, path=S.orbit(C6, 1.7, -34, -8, 0.15, 0.05), lens=35, aim=C6 + Vector((0, 0, 0.1)), focus=chest_pt,
         depth=0.8, shake=0.0008)
a, b = span("BreweryX")
C7 = W(chest_pt, mid("BreweryX"))
cams.cam("BreweryX", a, b, keys=[(a, C7 + Vector((-0.55, -1.45, -0.20))), (b, C7 + Vector((-0.40, -1.10, -0.25)))], lens=40,
         aim=belly_pt, depth=0.5, shake=0.0006)
a, b = span("Closer")
F6 = W(face_pt, mid("Closer"))
cams.cam("Closer", a, b, keys=[(a, F6 + Vector((0.12, -1.05, 0.02))), (b, F6 + Vector((0.05, -0.52, 0.0)))], lens=55, aim=face_pt,
         focus=eyes_mid, depth=0.12, shift_y=-0.06, shake=0.0008, ease="cine")

cams.markers(SHOTS)
S.check_shots(SHOTS, DUR)


def gaze_target(t):
    s = shot_at(t)
    ch = channels(t)
    if s[2] == "road" and ch["blow"] > 0.3:
        return Vector(dev_locs[F(t) - 1]) + Vector((0, 0, 0.03))
    if s[2] == "hosp" and B[5] <= t < at(5, 0.5):
        return Vector(cup_locs[F(t) - 1])
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
