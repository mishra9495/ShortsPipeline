"""quicksand-survival: "Quicksand can't swallow you, but it can still kill you" (Khaldoun, Eiser, Wegdam & Bonn,
"Liquefaction of quicksand under stress", Nature 437:635, 2005 -- quicksand ~2 g/mL vs a body ~1 g/mL, so you stop
at the waist; pulling a foot out at 1 cm/s takes about the force needed to lift a medium-size car).

Run (daily_render.ps1): blender -b --python scene.py -- <ROOT>/blend/<slug>.blend vo=<wav> beats=<json> fps=30
Optional: stills=1,200 pct=100 samples=128 device=gpu|cpu root=<ROOT>

v3 toolkit: every model is built in Blender from code (scripts/kit.py), the character acts procedurally on the
mixamorig bones (scripts/actor.py) and every camera is a moving spline that is already in motion on the cut
(scripts/shot.py). No captions, no on-screen text (owner's rule). Timing comes only from the beats JSON.

Cast: him = blend/char_hero.blend (opened as the main file). One character, one actor.
Sets: BEACH (a tidal sand flat at golden hour; he is stuck waist-deep in a wet quicksand pit, the sea behind him)
and XRAY (a void cross-section of his lower leg and foot in a slab of magnified sand grains, 60 m under the beach).
Transitions between sets are HARD CUTS (whoosh SFX + a brief exposure spike). SYNC constants must match mix.py.
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
K.init(scene, seed=47)
random.seed(47)
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
SLO_A, SLO_B = at(4, 0.30), B[5] - 0.05          # screen-time slow-mo window: the yank (money moment)
ACT_A, ACT_B = SLO_A, SLO_A + (SLO_B - SLO_A) * 0.4
YANK_F = 0.45                                     # fraction of the slow-mo window where the foot locks
YANK = SLO_A + YANK_F * (SLO_B - SLO_A)           # screen time of the lock
YANK_ACT = ACT_A + YANK_F * (ACT_B - ACT_A)       # the same moment in action time
JERKS = [at(5, f) for f in (0.12, 0.42, 0.72)]    # the rope snaps taut (beat 6)
TIDE_A, TIDE_B = B[9] - 0.2, NARR - 0.1           # the tide sheet creeps in
print("TIMELINE", [round(b, 2) for b in B], "END", END, "YANK", round(YANK, 2))

S.setup_render(scene, fps=FPS, end=END, pct=PCT, samples=SAMPLES, device=DEVICE)
scene.cycles.adaptive_threshold = 0.015 if SAMPLES >= 96 else 0.03


def bake(idb, path, values, index=None, interp="LINEAR"):
    return A.bake(idb, path, values, FRAMES, index=index, interp=interp)


def bake_vec(idb, path, vecs, n=3, interp="LINEAR"):
    A.bake_vec(idb, path, vecs, FRAMES, n=n, interp=interp)


ramp, env, spike, smooth, wobble = A.ramp, A.env, A.spike, A.smooth, A.wobble
warp = A.timewarp(SLO_A, SLO_B, ACT_A, ACT_B)


def sand_mat(name, light, dark, rough=0.9, bump=0.25, scale=60.0, wet=0.0):
    """Sand: two-tone noise colour, fine grain bump, optional wet coat."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    N, L = m.node_tree.nodes, m.node_tree.links
    b = N["Principled BSDF"]
    tc = N.new("ShaderNodeTexCoord")
    nz = N.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = scale * 0.08
    nz.inputs["Detail"].default_value = 6.0
    L.new(tc.outputs["Object"], nz.inputs["Vector"])
    cr = N.new("ShaderNodeValToRGB")
    cr.color_ramp.elements[0].position, cr.color_ramp.elements[1].position = 0.35, 0.7
    cr.color_ramp.elements[0].color = (*dark, 1)
    cr.color_ramp.elements[1].color = (*light, 1)
    L.new(nz.outputs["Fac"], cr.inputs["Fac"])
    L.new(cr.outputs["Color"], b.inputs["Base Color"])
    gr = N.new("ShaderNodeTexNoise")
    gr.inputs["Scale"].default_value = scale * 40
    L.new(tc.outputs["Object"], gr.inputs["Vector"])
    bp = N.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value = bump
    bp.inputs["Distance"].default_value = 0.002
    L.new(gr.outputs["Fac"], bp.inputs["Height"])
    L.new(bp.outputs["Normal"], b.inputs["Normal"])
    b.inputs["Roughness"].default_value = rough
    if wet:
        b.inputs["Coat Weight"].default_value = wet
        b.inputs["Coat Roughness"].default_value = 0.08
    return m


# ---------------------------------------------------------------- him: stuck in the pit (the rig root sinks/floats)
REST_HIPS = him.hips0.copy()
WAIST_Z = REST_HIPS.z + 0.14          # rest-pose height of the navel line: the sand surface sits here when stuck


def sink_z(t):
    """Rig root height. Frame 1 already shows him hip-deep; he sinks to the waist in beat 2 (with a small bob that
    stops dead: 'you only sink to your waist'), then floats up and leans back in beat 9."""
    z = -(REST_HIPS.z + 0.02) - 0.12 * ramp(t, B[1] + 0.1, B[1] + 0.9)
    z += 0.025 * spike(t, B[1] + 1.05, 0.25, 0.35) - 0.010 * spike(t, B[1] + 1.6, 0.2, 0.3)
    z += 0.10 * ramp(t, B[8] + 0.2, B[9] + 0.6)
    z += 0.004 * math.sin(t * 2 * math.pi / 3.1)
    return z


def root_loc(t):
    return Vector((-REST_HIPS.x, -REST_HIPS.y, sink_z(t)))


# ---------------------------------------------------------------- BEACH: tidal sand flat, the sea behind him (+Y)
BEACH = K.coll("Beach")
dry_m = sand_mat("DrySand", (0.80, 0.66, 0.46), (0.62, 0.49, 0.32), rough=0.92, bump=0.3)
wet_m = sand_mat("WetSand", (0.50, 0.39, 0.25), (0.36, 0.27, 0.17), rough=0.45, bump=0.2, wet=0.35)
quick_m = sand_mat("Quicksand", (0.38, 0.29, 0.17), (0.25, 0.18, 0.10), rough=0.35, bump=0.35, wet=0.25, scale=30)
K.plane("SandFlat", BEACH, (160, 160), (0, 0, 0), dry_m)
# the wet band near the waterline and the dark pit he's stuck in (both a hair above the dry sand)
K.plane("WetBand", BEACH, (160, 9.0), (0, 5.5, 0.001), wet_m)
pit = K.cyl("Pit", BEACH, 1.05, 0.001, (0, 0, 0.003), quick_m, verts=64)
# a damp halo that blends the pit into the dry flat (no hard disc edge)
K.lathe("PitHalo", BEACH, [(0.98, 0.0028), (1.3, 0.0024), (1.75, 0.0018)], (0, 0, 0), wet_m, steps=64, subsurf=1)
# a churned lip of sand pressed up around his waist
K.lathe("WaistLip", BEACH, [(0.12, -0.03), (0.17, 0.028), (0.24, 0.032), (0.34, 0.012), (0.48, 0.002), (0.6, -0.004)],
        (0, 0, 0), quick_m, steps=64, subsurf=2)
# ripple rings pushed out by his struggling (scale baked below)
RINGS = [K.lathe(f"Ripple{k}", BEACH, [(0.22, -0.002), (0.24, 0.006), (0.27, -0.002)], (0, 0, 0.002), quick_m,
                 steps=64, subsurf=1) for k in range(3)]
# his footprints leading into the pit (from the +X side, where he walked in)
print_m = sand_mat("Footprint", (0.55, 0.43, 0.28), (0.40, 0.30, 0.19), rough=0.6, bump=0.4, wet=0.2)
for k in range(9):
    side = 0.11 if k % 2 else -0.11
    p = Vector((1.25 + 0.62 * k, -0.35 - 0.30 * k + side, -0.006))
    o = K.sphere(f"Footprint{k}", BEACH, 0.15, p, print_m, scale=(0.75, 0.33, 0.06), subdiv=3)
    o.rotation_euler = (0, 0, math.atan2(-0.30, 0.62) + math.pi / 2)
# the sea: a glossy far sheet plus the incoming tide sheet whose near edge creeps toward him (beat 10)
sea_m = K.plastic("SeaWater", (0.02, 0.16, 0.20), 0.08, coat=0.5)
foam_m = K.plastic("Foam", (0.92, 0.94, 0.95), 0.6, sss=0.2)
K.plane("Sea", BEACH, (400, 300), (0, 160.0, 0.0045), sea_m)
TIDE_Y0, TIDE_Y1 = 9.5, 1.15
tide_me = bpy.data.meshes.new("Tide")
tide_me.from_pydata([(-60, 0, 0), (60, 0, 0), (60, 1, 0), (-60, 1, 0)], [], [(0, 1, 2, 3)])
tide = bpy.data.objects.new("Tide", tide_me)
BEACH.objects.link(tide)
tide.data.materials.append(sea_m)
tide.location = (0, TIDE_Y0, 0.004)
tide.scale = (1, 12.0, 1)          # reaches past the far sea sheet's near edge
foam = K.tube("FoamEdge", BEACH, [Vector((-60, 0, 0)), Vector((-1.5, 0.05, 0)), Vector((1.5, -0.05, 0)),
                                  Vector((60, 0, 0))], 0.035, foam_m, res=4)
foam.scale = (1, 1, 0.35)
foam_wave = bpy.data.textures.new("FoamWave", "CLOUDS")
foam_wave.noise_scale = 0.6
# rocks and driftwood to dress the flat (all real-world scale, soft in the DOF)
rock_m = sand_mat("Rock", (0.42, 0.38, 0.33), (0.22, 0.20, 0.18), rough=0.75, bump=0.6, scale=8)
for k, (p, s) in enumerate((((-2.6, 2.2, 0.0), (0.35, 0.6)), ((-3.4, 3.4, 0.0), (0.25, 0.45)),
                            ((3.1, 3.8, 0.0), (0.3, 0.55)), ((-6.5, 7.5, 0.0), (0.5, 0.9)), ((5.5, 8.0, 0.0), (0.4, 0.7)))):
    for r_ in K.shards(BEACH, 2, rock_m, p, size=s, seed=30 + k, name=f"Rock{k}_", spread=s[1] * 0.6):
        sd = r_.modifiers.new("Smooth", "SUBSURF")
        sd.levels = sd.render_levels = 2
wood_m = K.wood("Driftwood", (0.58, 0.52, 0.44), (0.34, 0.30, 0.26), rough=0.8)
K.tube("Driftwood", BEACH, [Vector((1.6, 1.6, 0.04)), Vector((2.3, 1.9, 0.07)), Vector((3.0, 1.75, 0.05))], 0.06, wood_m,
       res=6)
K.tube("DriftBranch", BEACH, [Vector((2.3, 1.9, 0.07)), Vector((2.5, 2.25, 0.05))], 0.025, wood_m, res=4)
# the rope a friend throws him (beat 6): taut toward the top of frame, origin baked onto his hands
rope_m = K.fabric("Rope", (0.72, 0.58, 0.36), rough=0.9, weave=900.0)
rope = K.tube("Rope", BEACH, [Vector((0, 0, 0)), Vector((0.05, 0.4, 1.4)), Vector((0.1, 0.9, 4.5))], 0.012, rope_m, res=4)

# ---------------------------------------------------------------- XRAY: his lower leg in a slab of magnified grains
ANATP = Vector((0.0, 0.0, -60.0))
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


ANKLE = ANATP.copy()
FOOTC = ANATP + Vector((0.06, 0.0, -0.01))
leg_root = K.empty("LegRoot", ANAT, ANKLE)
skin_m = xglow("LegSkin", (0.32, 0.72, 1.0), 2.0, blend=0.35, core=0.02)
halo_m = xglow("WaterHalo", (0.20, 0.85, 1.0), 0.0, blend=0.25, core=0.0)
bone_m = K.bone_mat("LegBone")
LEG = []


def leg_tube(name, pts, r, mat, res=10):
    o = K.tube(name, ANAT, [Vector(p) for p in pts], r, mat, res=res)
    LEG.append(o)
    return o


# skin shell (ankle at the origin, foot pointing +X so the camera on -Y sees the side profile)
leg_tube("Thigh", [(0, 0, 0.47), (0, 0.0, 0.90)], 0.072, skin_m)
leg_tube("Calf", [(0, 0, -0.025), (0, 0.006, 0.22), (0, 0, 0.47)], 0.052, skin_m)
leg_tube("Foot", [(-0.045, 0, -0.03), (0.05, 0, -0.042), (0.17, 0, -0.058)], 0.036, skin_m)
for o in list(LEG):
    o.data.splines[0].bezier_points[0].radius = 0.8
    o.visible_diffuse = o.visible_glossy = o.visible_transmission = False
halo = leg_tube("WaterHalo", [(0, 0, -0.02), (0, 0, 0.30)], 0.07, halo_m)
halo_foot = leg_tube("WaterHaloFoot", [(-0.06, 0, -0.04), (0.19, 0, -0.06)], 0.05, halo_m)
for o in (halo, halo_foot):
    o.visible_diffuse = o.visible_glossy = o.visible_transmission = False
# bones: femur + condyles, patella, tibia, fibula, talus, calcaneus, metatarsals, toes
leg_tube("Femur", [(0, 0.004, 0.49), (0, 0.0, 0.92)], 0.015, bone_m, res=6)
for sx in (-1, 1):
    LEG.append(K.sphere(f"Condyle{sx}", ANAT, 0.022, (0.0, 0.012 * sx, 0.475), bone_m, scale=(1.1, 0.9, 0.85), subdiv=3))
LEG.append(K.sphere("Patella", ANAT, 0.018, (-0.028, 0, 0.47), bone_m, scale=(0.6, 1.0, 1.2), subdiv=3))
LEG.append(K.sphere("TibiaHead", ANAT, 0.026, (0.0, 0, 0.445), bone_m, scale=(1.0, 1.0, 0.55), subdiv=3))
leg_tube("Tibia", [(0, 0, 0.03), (-0.004, 0, 0.24), (0, 0, 0.44)], 0.012, bone_m, res=6)
leg_tube("Fibula", [(0.012, 0.018, 0.04), (0.014, 0.02, 0.25), (0.01, 0.017, 0.42)], 0.0055, bone_m, res=4)
LEG.append(K.sphere("Talus", ANAT, 0.018, (0.005, 0, -0.012), bone_m, scale=(1.3, 1.0, 0.8), subdiv=3))
LEG.append(K.sphere("Calcaneus", ANAT, 0.022, (-0.03, 0, -0.04), bone_m, scale=(1.4, 0.9, 0.9), subdiv=3))
for k in range(5):
    y = (k - 2) * 0.011
    leg_tube(f"Metatarsal{k}", [(0.03, y * 0.6, -0.035), (0.12, y, -0.055 + 0.002 * abs(k - 2))], 0.0045, bone_m, res=4)
    leg_tube(f"Toe{k}", [(0.125, y, -0.056), (0.16 - 0.004 * abs(k - 2), y * 1.05, -0.062)], 0.0038, bone_m, res=4)
for o in LEG:
    o.parent = leg_root          # positions above are already relative to the ankle
# bones must read through the X-ray skin: give them a soft glow
bone_bsdf = bone_m.node_tree.nodes.get("Principled BSDF")
if bone_bsdf is not None:
    bone_bsdf.inputs["Emission Color"].default_value = (0.95, 0.90, 0.78, 1)
    bone_bsdf.inputs["Emission Strength"].default_value = 0.25

# magnified sand grains: a back wall behind the leg plus a mid layer around it (not in front: it would hide the leg)
grain_ms = [K.plastic(f"Grain{k}", c, 0.55, sss=0.15) for k, c in
            enumerate(((0.78, 0.62, 0.38), (0.66, 0.50, 0.30), (0.86, 0.74, 0.52), (0.55, 0.42, 0.28)))]
for m_ in grain_ms:
    m_.node_tree.nodes["Principled BSDF"].inputs["Subsurface Scale"].default_value = 0.004
GROUPS = [K.empty(f"Grains{k}", ANAT, FOOTC) for k in range(3)]


def leg_dist(p):
    """Distance from a point (relative to the ankle) to the leg's skin axis (calf/thigh vertical, foot along +X)."""
    d_leg = math.hypot(p.x, p.y) - 0.055 if p.z > -0.02 else 9.0
    q = Vector((min(max(p.x, -0.05), 0.18), 0.0, -0.045))
    d_foot = (p - q).length - 0.036
    return min(d_leg, d_foot)


rng = random.Random(3)
GRAINS = []
for layer, (y0, y1) in enumerate(((0.07, 0.10), (-0.03, 0.03))):
    step = 0.030
    for ix in range(-12, 14):
        for iz in range(-11, 22):
            rel = Vector((ix * step + rng.uniform(-0.008, 0.008), rng.uniform(y0, y1),
                          iz * step + rng.uniform(-0.008, 0.008) + (step / 2 if ix % 2 else 0)))
            r = rng.uniform(0.010, 0.017)
            if layer == 1 and leg_dist(rel) < r + 0.006:
                continue
            w = ANKLE + rel
            dfoot = (w - FOOTC).length
            g = 0 if dfoot < 0.15 else (1 if dfoot < 0.30 else 2)
            o = K.sphere(f"Grain{layer}_{ix}_{iz}", ANAT, r, w, grain_ms[rng.randrange(4)],
                         scale=(rng.uniform(0.8, 1.2), rng.uniform(0.8, 1.2), rng.uniform(0.7, 1.0)), subdiv=1)
            o.rotation_euler = (rng.uniform(0, 6.3), rng.uniform(0, 6.3), rng.uniform(0, 6.3))
            for poly in o.data.polygons:
                poly.use_smooth = False     # faceted, chunky quartz grains
            o.parent = GROUPS[g]
            o.location = w - FOOTC
            GRAINS.append(o)
print("GRAINS", len(GRAINS))
# water droplets seeping down along the leg (beat 8) and the suction flash at the yank (beat 5)
water_m = K.emissive("Seep", (0.25, 0.80, 1.0), 2.5)
DROPS = [K.sphere(f"Drop{k}", ANAT, 0.0065, ANKLE, water_m, scale=(1, 1, 1.4), subdiv=2) for k in range(36)]
flash_m = K.emissive("YankFlash", (0.85, 0.95, 1.0), 0.0)
flash = K.sphere("YankFlash", ANAT, 0.02, FOOTC + Vector((0, -0.04, 0)), flash_m, subdiv=3)

# ---------------------------------------------------------------- shots (names, start times, set)
SHOTS = [
    (0.0, "PanicMed", "beach"),
    (at(0, 0.55), "PanicOrbit", "beach"),
    (B[1], "BeachWide", "beach"),
    (at(1, 0.55), "WaistCU", "beach"),
    (B[2], "XrayLeg", "xray"),
    (B[3], "XrayFoot", "xray"),
    (B[4], "YankBuild", "xray"),
    (SLO_A, "YankSlomo", "xray"),
    (B[5], "RopeLow", "beach"),
    (at(5, 0.5), "RopeFace", "beach"),
    (B[6], "XrayCircles", "xray"),
    (B[7], "XrayWater", "xray"),
    (B[8], "LeanBack", "beach"),
    (B[9], "TideWide", "beach"),
    (at(9, 0.5), "CloserPush", "beach"),
]


def shot_at(t):
    return max((s for s in SHOTS if s[0] <= t + 1e-6), key=lambda s: s[0])


SH = [shot_at(t) for t in T]
SET_OF = [s[2] for s in SH]

# ---------------------------------------------------------------- performance (channels, 0..1 envelopes over time)
BLINKS = [1.2 + 3.1 * k for k in range(60) if 1.2 + 3.1 * k < DUR]


def channels(t):
    ch = {}
    ch["panic"] = max(1.0 - ramp(t, B[1] + 1.0, B[2]), env(t, B[9] + 0.1, B[9] + 0.6, DUR, DUR + 1))
    ch["strain"] = env(t, B[5], B[5] + 0.2, B[6] - 0.2, B[6] + 0.1)
    ch["calm"] = env(t, B[6] - 0.1, B[6] + 0.5, B[9], B[9] + 0.4)
    ch["lean"] = env(t, B[8] + 0.1, B[8] + 1.1, B[9] + 0.2, B[9] + 1.0)
    ch["rope"] = env(t, B[5] - 0.05, B[5] + 0.15, B[6] - 0.15, B[6] + 0.1)
    ch["jerk"] = max((spike(t, j, 0.04, 0.18) for j in JERKS), default=0.0) * ch["rope"]
    ch["blink"] = max((env(t, b_ - 0.03, b_, b_ + 0.05, b_ + 0.12) for b_ in BLINKS), default=0.0)
    return ch


SH_L, SH_R = him.bone_rest_head("LeftArm"), him.bone_rest_head("RightArm")
HEAD_L = him.head0.copy()
for i, t in enumerate(T):
    ch = channels(t)
    br = math.sin(t * 2 * math.pi / (2.4 if ch["panic"] > 0.5 else 3.6))
    p = ch["panic"]
    flail = (wobble(t, 31, 2.4), wobble(t, 32, 2.1), wobble(t, 33, 2.7))
    lean = ch["lean"]
    spec = {
        "Hips": [(A.Z, 1.5 * p * wobble(t, 1, 1.8) + 0.4 * wobble(t, 2))],
        "Spine": [(A.X, -3 + 0.8 * br + 14 * lean - 4 * ch["strain"]), (A.Z, (3.0 * p + 0.5) * wobble(t, 3, 1.4))],
        "Spine1": [(A.X, 0.6 * br + 9 * lean - 3 * ch["strain"])],
        "Spine2": [(A.X, 1 + 0.6 * br + 6 * lean)],
        "Neck": [(A.X, -3 * p + 4 * ch["strain"] - 6 * lean + 0.4 * wobble(t, 4)), (A.Z, 1.2 * wobble(t, 5))],
        "Head": [(A.X, -6 * ch["strain"] - 10 * lean + 3 * p * wobble(t, 7, 1.6) + 1.0 * wobble(t, 8, 0.6)),
                 (A.Y, 14 * p * wobble(t, 9, 1.2) + 2.0 * wobble(t, 6, 0.5) + 20 * env(t, B[9], B[9] + 0.4, DUR, DUR + 1)),
                 (A.Z, 2 * p * wobble(t, 10, 1.3))],
        "LeftShoulder": [(A.Y, 6 * p + 8 * ch["rope"] - 4 * lean)],
        "RightShoulder": [(A.Y, -6 * p - 8 * ch["rope"] + 4 * lean)],
    }
    rots = {}
    for bone, axes in spec.items():
        if him.has(bone):
            q = A.Quaternion()
            for axis, deg in axes:
                q = q @ him.q(bone, axis, deg)
            rots[bone] = q
    for bone in him.fingers():
        j = int(bone[-1])
        base_curl = {1: 12, 2: 16, 3: 12}[j]
        grip = {1: 55, 2: 75, 3: 60}[j]
        rots[bone] = A.Quaternion((1, 0, 0), math.radians(base_curl * (1 - ch["rope"]) + grip * ch["rope"]
                                                          - 8 * p * (0.5 + 0.5 * flail[j % 3])))
    sh = {}
    for side in ("Left", "Right"):
        sh[f"eyeBlink{side}"] = min(1.0, ch["blink"])
        sh[f"eyeWide{side}"] = 0.7 * p
        sh[f"browDown{side}"] = 0.6 * ch["strain"] + 0.2 * ch["calm"]
        sh[f"eyeSquint{side}"] = 0.6 * ch["strain"]
        sh[f"mouthPress{side}"] = 0.5 * ch["strain"] + 0.2 * ch["calm"]
        sh[f"mouthStretch{side}"] = 0.4 * p
    sh["browInnerUp"] = 0.8 * p
    sh["jawOpen"] = 0.28 * p + 0.06 * p * (0.5 + 0.5 * br)
    sh["mouthClose"] = 0.0
    # hands: panic = flailing up by the shoulders; rope = both hands together overhead, yanked up on each jerk;
    # lean = arms spread flat out to the sides on the sand surface
    up = 0.18 + 0.06 * flail[0]
    ikl_p = SH_L + Vector((0.20 + 0.07 * flail[1], -0.22 + 0.05 * flail[2], up))
    ikr_p = SH_R + Vector((-0.20 - 0.07 * flail[2], -0.20 + 0.05 * flail[0], 0.16 + 0.06 * flail[1]))
    rest_l = SH_L + Vector((0.30, -0.14, -0.28))
    rest_r = SH_R + Vector((-0.30, -0.14, -0.28))
    rope_pt = HEAD_L + Vector((0.0, -0.30, 0.22 + 0.07 * ch["jerk"]))
    spread_l = SH_L + Vector((0.55, 0.05, -0.30))
    spread_r = SH_R + Vector((-0.55, 0.05, -0.30))
    ikl = rest_l.lerp(ikl_p, p)
    ikr = rest_r.lerp(ikr_p, p)
    ikl = ikl.lerp(rope_pt + Vector((0.03, 0, -0.03)), ch["rope"]).lerp(spread_l, lean)
    ikr = ikr.lerp(rope_pt + Vector((-0.03, 0, 0.0)), ch["rope"]).lerp(spread_r, lean)
    loc = root_loc(t) + Vector((0, 0, 0.05 * ch["jerk"]))
    him.record(rots, sh, ikl, ikr, aim=(0.0, 0.0), root=(loc, (0.0, 0.0, 0.0)))
him.bake(FRAMES)
for fc in A.fcurves_of(him.rig):
    fc.update()
ROOT_LOC = [root_loc(t) + Vector((0, 0, 0.05 * channels(t)["jerk"])) for t in T]

# rope: rides on his hands, only while he holds it
rope_pts = []
for i, t in enumerate(T):
    ch = channels(t)
    rope_pts.append(ROOT_LOC[i] + HEAD_L + Vector((0.0, -0.30, 0.22 + 0.07 * ch["jerk"])))
bake_vec(rope, "location", rope_pts)
bake_vec(rope, "scale", [(1, 1, 1 + 0.03 * channels(t)["jerk"]) for t in T])

# ripple rings: pushed out while he struggles (panic, the rope jerks)
for k, ring in enumerate(RINGS):
    sc, hz = [], []
    for t in T:
        ch = channels(t)
        drive = max(ch["panic"], ch["rope"], 0.4 * ch["calm"])
        ph = ((t + k * 0.6) / 1.8) % 1.0
        sc.append(1.0 + 3.2 * ph)
        hz.append(drive * (1 - ph) ** 1.5)
    bake_vec(ring, "scale", [(s, s, max(0.001, h)) for s, h in zip(sc, hz)])

# tide sheet + foam edge creep in (beat 10); a slow lap the rest of the time
tide_y = [TIDE_Y0 + (TIDE_Y1 - TIDE_Y0) * ramp(t, TIDE_A, TIDE_B) + 0.25 * math.sin(t * 2 * math.pi / 4.5) for t in T]
bake_vec(tide, "location", [(0, y, 0.005) for y in tide_y])
bake_vec(foam, "location", [(0, y, 0.01) for y in tide_y])

# ---------------------------------------------------------------- X-ray process animation
leg_locs, leg_rots = [], []
for t in T:
    ta = warp(t)
    z = 0.004 * math.sin(t * 2 * math.pi / 2.7)
    z += 0.018 * ramp(t, B[2] + 0.2, B[2] + 1.2) * (1 - ramp(t, B[3], B[3] + 0.6))       # buoyant: it floats up
    pull = ramp(ta, ACT_A, YANK_ACT) * (1 - ramp(ta, YANK_ACT + 0.02, ACT_B))              # yank: rises, locks, drops
    z += 0.035 * pull * (1 - 0.6 * ramp(ta, YANK_ACT - 0.05, YANK_ACT))
    circ = env(t, B[6] + 0.1, B[6] + 0.5, B[8], B[8] + 0.4)                              # wiggle in little circles
    w_ = 2 * math.pi * 0.75 * t
    x, y = 0.012 * circ * math.cos(w_), 0.010 * circ * math.sin(w_)
    z += 0.065 * ramp(t, B[7] + 0.5, B[8] + 1.0)                                          # loosened: floats up
    leg_locs.append(ANKLE + Vector((x, y, z)))
    shake = 0.02 * spike(ta, YANK_ACT, 0.02, 0.15) * math.sin(70 * ta)
    leg_rots.append((0.05 * circ * math.sin(w_), 0.06 * circ * math.cos(w_) + shake, 0.0))
bake_vec(leg_root, "location", leg_locs)
bake_vec(leg_root, "rotation_euler", leg_rots)
# grains: clamp around the foot (beats 4-5, hardest at the lock), loosen as water seeps in (beat 8)
for k, g in enumerate(GROUPS):
    amt = (0.045, 0.025, 0.008)[k]
    vals = []
    for t in T:
        ta = warp(t)
        tight = ramp(t, B[3] + 0.3, B[4]) * (1 - ramp(t, B[7] + 0.2, B[8]))
        lock = spike(ta, YANK_ACT, 0.03, 0.25)
        loose = ramp(t, B[7] + 0.2, B[8] + 0.6)
        jig = 0.004 * env(t, B[6], B[6] + 0.4, B[8], B[8] + 0.3) * math.sin(2 * math.pi * 0.75 * t + k)
        vals.append(1.0 - amt * tight - 1.6 * amt * lock + 2.6 * amt * loose + jig)
    bake_vec(g, "scale", [(v, v, v) for v in vals])
bake(flash_m.node_tree, 'nodes["Principled BSDF"].inputs["Emission Strength"].default_value',
     [30.0 * spike(warp(t), YANK_ACT, 0.02, 0.12) for t in T])
bake_vec(flash, "scale", [(min(1.0, 3 * spike(warp(t), YANK_ACT, 0.02, 0.12)),) * 3 for t in T])
bake(halo_m.node_tree, 'nodes["Emission"].inputs["Strength"].default_value',
     [1.6 * ramp(t, B[7] + 0.1, B[7] + 1.2) * (1 - ramp(t, B[8] + 0.5, B[8] + 1.0)) for t in T])
# droplets trickle down beside the leg into the gaps, each on its own loop
rng5 = random.Random(8)
for o in DROPS:
    ph, ang, spd = rng5.random(), rng5.uniform(0, 2 * math.pi), rng5.uniform(0.35, 0.6)
    side = Vector((math.cos(ang), 0.0, 0.0))
    r_off = rng5.uniform(0.06, 0.09)
    locs, scl = [], []
    for i, t in enumerate(T):
        live = ramp(t, B[6] + 1.0, B[7] + 0.3) * (1 - ramp(t, B[8] + 0.6, B[8] + 1.0))
        u = (ph + spd * t) % 1.0
        z = 0.45 - 0.55 * u
        if z < 0:
            p = Vector((-0.07 + 0.30 * (-z / 0.10), math.sin(ang) * 0.04, -0.09))
        else:
            p = Vector((side.x * r_off, math.sin(ang) * 0.035, z))
        locs.append(leg_locs[i] + p)
        scl.append(live * smooth(min(u, 1 - u) / 0.1))
    bake_vec(o, "location", locs)
    bake_vec(o, "scale", [(v, v, 1.4 * v) for v in scl])

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


for name, coll in (("beach", BEACH), ("xray", ANAT)):
    key_vis([o for o in coll.all_objects if not o.hide_render and o is not rope],
            lambda i, name=name: SET_OF[i] == name)
key_vis([rope], lambda i: SET_OF[i] == "beach" and channels(T[i])["rope"] > 0.05)
key_vis([o for o in him.rig.children_recursive if o.type == "MESH"], lambda i: SET_OF[i] == "beach")

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
WCOL = {"beach": ((0.62, 0.74, 0.92), 0.9), "xray": ((0.045, 0.028, 0.014), 1.0)}
cols = [WCOL[s] for s in SET_OF]
bake_vec(wnt, 'nodes["Background"].inputs[0].default_value', [(*c_, 1) for c_, _ in cols], n=4, interp="CONSTANT")
bake(wnt, 'nodes["Background"].inputs[1].default_value', [s_ for _, s_ in cols], interp="CONSTANT")
bake(scene, "view_settings.exposure", [-0.35 + 0.8 * spike(t, B[2], 0.01, 0.06) + 0.6 * spike(t, YANK, 0.02, 0.1)
                                       + 0.5 * spike(t, B[6], 0.01, 0.06) for t in T])


def _area(name, coll, loc, target, energy, size, color):
    d = bpy.data.lights.new(name, "AREA")
    d.energy, d.size, d.color = energy, size, color
    o = bpy.data.objects.new(name, d)
    coll.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


sun_d = bpy.data.lights.new("Sun", "SUN")
sun_d.energy, sun_d.angle, sun_d.color = 3.2, math.radians(1.5), (1.0, 0.86, 0.68)
sun = bpy.data.objects.new("Sun", sun_d)
BEACH.objects.link(sun)
sun.rotation_euler = Euler((math.radians(62), 0.0, math.radians(-145)))     # low golden sun from front-left
CHEST0 = Vector((0, 0, 0.35))
LIGHTS = {
    "beach": [sun,
              _area("BeachFill", BEACH, CHEST0 + Vector((-1.6, -1.8, 0.6)), CHEST0, 120, 2.5, (0.80, 0.88, 1.0)),
              _area("BeachRim", BEACH, CHEST0 + Vector((0.8, 1.6, 1.2)), CHEST0, 260, 1.0, (1.0, 0.92, 0.80))],
    "xray": [_area("XKey", ANAT, FOOTC + Vector((0.5, -0.6, 0.5)), FOOTC, 14, 0.6, (1.0, 0.86, 0.70)),
             _area("XFill", ANAT, FOOTC + Vector((-0.6, -0.5, 0.1)), FOOTC, 6, 0.8, (0.6, 0.72, 1.0)),
             _area("XRim", ANAT, FOOTC + Vector((0.0, 0.6, 0.6)), FOOTC, 10, 0.5, (0.9, 0.95, 1.0))],
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
face_pt = him.anchor("Face", "Head", Vector((him.x0, him.nose.y + 0.05, him.nose.z - 0.01)), CAST)
chest_pt = him.anchor("Chest", "Spine2", him.bone_rest_head("Spine2"), CAST)
a, b = span("PanicMed")
C0 = W(chest_pt, mid("PanicMed"))
cams.cam("PanicMed", a, b, keys=[(a, C0 + Vector((0.40, -1.75, -0.05))), (b, C0 + Vector((0.28, -1.40, 0.0)))],
         lens=40, aim=chest_pt, depth=0.8, shift_y=-0.03, shake=0.0015, ease="cine")
a, b = span("PanicOrbit")
C1 = W(chest_pt, mid("PanicOrbit"))
cams.cam("PanicOrbit", a, b, path=S.orbit(C1, 1.2, 22, 4, 0.05, 0.12), lens=50, aim=face_pt, depth=0.35,
         shift_y=-0.06, shake=0.0015)
a, b = span("BeachWide")
BW = Vector((0, 0.6, 0.25))
cams.cam("BeachWide", a, b, keys=[(a, BW + Vector((2.6, -4.6, 1.3))), (b, BW + Vector((2.1, -3.9, 1.1)))],
         lens=28, aim=BW, focus=Vector((0, 0, 0.3)), depth=1.5, shift_y=0.05, shake=0.001)
a, b = span("WaistCU")
WP = Vector((0, 0, 0.16))
cams.cam("WaistCU", a, b, path=S.orbit(WP, 1.15, -32, -8, 0.42, 0.32, r1=0.95), lens=50, aim=WP, depth=0.45,
         shake=0.001)
XC = FOOTC + Vector((0.0, 0.0, 0.16))
a, b = span("XrayLeg")
cams.cam("XrayLeg", a, b, keys=[(a, XC + Vector((0.18, -1.05, 0.55))), (b, XC + Vector((0.12, -0.88, 0.18)))],
         lens=35, aim=XC, depth=0.45, shake=0.0006, ease="out")
a, b = span("XrayFoot")
cams.cam("XrayFoot", a, b, path=S.orbit(FOOTC + Vector((0, 0, 0.04)), 0.58, -16, 10, 0.08, 0.05), lens=45,
         aim=FOOTC + Vector((0, 0, 0.04)), depth=0.25, shake=0.0005)
a, b = span("YankBuild")
cams.cam("YankBuild", a, b, keys=[(a, FOOTC + Vector((0.12, -0.55, 0.12))), (b, FOOTC + Vector((0.08, -0.44, 0.09)))],
         lens=50, aim=FOOTC + Vector((0, 0, 0.03)), depth=0.18, shake=0.0005)
a, b = span("YankSlomo")
cams.cam("YankSlomo", a, b, keys=[(a, FOOTC + Vector((0.06, -0.42, 0.07))), (b, FOOTC + Vector((0.04, -0.36, 0.06)))],
         lens=50, aim=FOOTC + Vector((0, 0, 0.03)), depth=0.16, shake=0.0003, kicks=[(YANK, 0.006, 0.25)], ease="cine")
a, b = span("RopeLow")
H0 = W(chest_pt, mid("RopeLow")) + Vector((0, 0, 0.35))
cams.cam("RopeLow", a, b, keys=[(a, H0 + Vector((0.75, -1.35, -0.42))), (b, H0 + Vector((0.55, -1.15, -0.40)))],
         lens=28, aim=H0, depth=0.8, shake=0.0012, kicks=[(j, 0.012, 0.2) for j in JERKS])
a, b = span("RopeFace")
cams.cam("RopeFace", a, b, keys=[(a, W(face_pt, a) + Vector((-0.10, -0.64, -0.12))),
                                 (b, W(face_pt, b) + Vector((-0.06, -0.50, -0.09)))],
         lens=75, aim=face_pt, depth=0.18, shift_y=-0.06, shake=0.001, kicks=[(j, 0.006, 0.2) for j in JERKS])
a, b = span("XrayCircles")
cams.cam("XrayCircles", a, b, path=S.orbit(FOOTC + Vector((0, 0, 0.06)), 0.62, 18, -8, 0.10, 0.06), lens=42,
         aim=FOOTC + Vector((0, 0, 0.06)), depth=0.3, shake=0.0004)
a, b = span("XrayWater")
cams.cam("XrayWater", a, b, path=S.orbit(FOOTC + Vector((0, 0, 0.10)), 0.48, -10, 6, 0.04, 0.10, r1=0.40), lens=50,
         aim=FOOTC + Vector((0, 0, 0.10)), depth=0.25, shake=0.0004)
a, b = span("LeanBack")
C2 = W(chest_pt, mid("LeanBack"))
cams.cam("LeanBack", a, b, keys=[(a, C2 + Vector((0.35, -1.0, 2.3))), (b, C2 + Vector((0.25, -0.75, 2.0)))],
         lens=32, aim=C2 + Vector((0, 0.05, -0.1)), depth=1.0, shake=0.0008)
a, b = span("TideWide")
TW = Vector((0, 1.2, 0.2))
cams.cam("TideWide", a, b, keys=[(a, TW + Vector((-2.9, -3.6, 1.0))), (b, TW + Vector((-2.4, -3.1, 0.85)))],
         lens=30, aim=TW, focus=Vector((0, 0, 0.3)), depth=2.0, shift_y=0.04, shake=0.001)
a, b = span("CloserPush")
C3 = W(chest_pt, mid("CloserPush"))
cams.cam("CloserPush", a, b, keys=[(a, C3 + Vector((0.40, -1.75, -0.05))), (b, C3 + Vector((0.26, -1.30, 0.0)))],
         lens=40, aim=chest_pt, depth=0.8, shift_y=-0.03, shake=0.0012, ease="cine")

cams.markers(SHOTS)
S.check_shots(SHOTS, DUR)


def gaze_target(t):
    s = shot_at(t)
    if s[2] != "beach":
        return None
    if channels(t)["rope"] > 0.3:
        return ROOT_LOC[min(len(T) - 1, F(t) - 1)] + HEAD_L + Vector((0.05, 0.6, 1.4))
    if t >= B[9]:
        return Vector((0.4, 6.0, 0.1))        # glances back at the incoming tide
    return None


him.bake_gaze(FRAMES, T, gaze_target, CAST, seed=13)

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
