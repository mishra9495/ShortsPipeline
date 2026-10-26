"""brain-leaking-nose v2: "Her brain was leaking out of her nose, and doctors blamed allergies."

Run (daily_render.ps1): blender -b --python scene.py -- <ROOT>/blend/<slug>.blend vo=<wav> beats=<json> fps=60
Optional: stills=1,200 pct=100 samples=64 device=gpu|cpu root=<ROOT>

Everything is modelled in Blender from code (scripts/kit.py); characters are MPFB humans:
  her    = blend/char_heroine.blend (built once from scripts/preset_heroine.json if missing; NEVER replaced by a man)
  doctor = blend/char_hero.blend, recoloured into a white coat (+ stethoscope; cap and mask in the OR)
Sets (far apart, so they never see each other): HOME living room, CLINIC, CAR on a night road, OR, plus X-ray
anatomy that rides on her head. No captions and no on-screen text (owner's rule).
Timing is in seconds from the narration beats JSON, so any fps works (default 60). SYNC constants match mix.py.
"""
import json
import math
import os
import random
import subprocess
import sys

import bpy
from mathutils import Matrix, Vector

# ---------------------------------------------------------------- arguments
argv = sys.argv[sys.argv.index("--") + 1:]
OUT = os.path.abspath(argv[0])
opts = dict(kv.split("=", 1) for kv in argv[1:] if "=" in kv)
SLUG = os.path.splitext(os.path.basename(OUT))[0]
ROOT = opts.get("root") or os.path.dirname(os.path.dirname(OUT))
SCRIPTS = os.path.join(ROOT, "scripts")
AUDIO = os.path.join(ROOT, "audio")
FPS = int(opts.get("fps", 60))
PCT = int(opts.get("pct", 100))
SAMPLES = int(opts.get("samples", 48))
DEVICE = opts.get("device", "gpu").lower()
STILLS = [int(f) for f in opts["stills"].split(",")] if opts.get("stills") else []
BEATS_JSON = opts.get("beats") or os.path.join(AUDIO, f"{SLUG}_vo.json")
VO_WAV = opts.get("vo") or os.path.join(AUDIO, f"{SLUG}_vo.wav")
if not os.path.exists(BEATS_JSON):
    raise SystemExit(f"Error: narration timing {BEATS_JSON} missing")
print(f"ARGS out={OUT} fps={FPS} pct={PCT} samples={SAMPLES} device={DEVICE} beats={BEATS_JSON}")
sys.path.insert(0, SCRIPTS)

# ---------------------------------------------------------------- characters (female lead is mandatory)
HEROINE = os.path.join(ROOT, "blend", "char_heroine.blend")
HERO = os.path.join(ROOT, "blend", "char_hero.blend")
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

scene = bpy.context.scene
K.init(scene, seed=11)
random.seed(11)
CAST = K.coll("Cast")
her = A.Actor.from_scene("Her")
doc = A.Actor.append(HERO, "Doc", CAST) if os.path.exists(HERO) else None
for a in (her, doc):
    if a:
        a.measure()
        a.setup_ik(CAST)
print("CAST", her.rig.name, doc.rig.name if doc else None, "her height", round(her.top, 3))

# ---------------------------------------------------------------- timeline (seconds)
META = json.load(open(BEATS_JSON, encoding="utf-8"))
B = [float(b["start"]) for b in META["beats"]]
assert len(B) == 10, f"expected 10 beats, got {len(B)}"
DUR = float(META["duration"]) + 0.8
BE = B[1:] + [DUR]


def at(i, frac):
    return B[i] + frac * (BE[i] - B[i])


def F(t):
    return int(round(t * FPS)) + 1


END = F(DUR)
FRAMES = range(1, END + 1)
T = [(f - 1) / FPS for f in FRAMES]
# SYNC with mix.py
IMPACT = at(1, 0.48)          # rear-end impact (exterior)
FACE_HIT = at(1, 0.80)        # face meets the dashboard (slow motion)
MUCUS = at(3, 0.62)           # "It wasn't mucus" -> strip turns
CRACK = at(5, 0.40)
SEAL = at(8, 0.78)
print("TIMELINE", [round(b, 2) for b in B], "END", END, "IMPACT", round(IMPACT, 2), "SEAL", round(SEAL, 2))

# ---------------------------------------------------------------- render settings
scene.frame_start, scene.frame_end = 1, END
scene.render.fps = FPS
scene.render.engine = "CYCLES"
c = scene.cycles
c.samples = SAMPLES
c.use_adaptive_sampling = True
c.adaptive_threshold = 0.03
c.use_denoising = True
c.max_bounces, c.diffuse_bounces, c.glossy_bounces, c.transmission_bounces, c.transparent_max_bounces = 8, 3, 3, 6, 32
c.caustics_reflective = c.caustics_refractive = False
c.blur_glossy = 1.0
if DEVICE == "gpu":
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.refresh_devices()
        for d in prefs.devices:
            d.use = d.type == "OPTIX"
        c.device = "GPU"
        c.denoiser = "OPTIX"
    except Exception as exc:
        print("WARN no OptiX:", exc)
else:
    c.device = "CPU"
scene.render.resolution_x, scene.render.resolution_y = 1080, 1920
scene.render.resolution_percentage = PCT
scene.render.use_motion_blur = True
scene.render.motion_blur_shutter = 0.5
scene.render.use_persistent_data = True
scene.render.image_settings.file_format = "PNG"
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Punchy"
scene.view_settings.exposure = -0.35


def bake(idb, path, values, index=None, interp="LINEAR"):
    return A.bake(idb, path, values, FRAMES, index=index, interp=interp)


def bake_vec(idb, path, vecs, n=3, interp="LINEAR"):
    A.bake_vec(idb, path, vecs, FRAMES, n=n, interp=interp)


ramp, env, spike, smooth, wobble = A.ramp, A.env, A.spike, A.smooth, A.wobble

# ---------------------------------------------------------------- sets (modelled here, far apart)
HOMEP, CLINP, CARP, ORP = Vector((0, 0, 0)), Vector((40, 0, 0)), Vector((80, 0, 0)), Vector((120, 0, 0))
FAR = Vector((0, 0, -200))
HOME, CLIN, ROAD, OR = K.coll("SetHome"), K.coll("SetClinic"), K.coll("SetRoad"), K.coll("SetOR")

# HOME: living room. Sofa seat front edge at y=0; she sits in the middle, facing -Y (towards the TV/camera side)
K.room(HOME, origin=(0, 0.7, 0), size=(6.0, 5.4, 2.7))
win = K.window(HOME, (-1.5, 3.33, 1.45), size=(1.3, 1.4), sky=(0.75, 0.85, 1.0), sky_strength=3.0)
sofa = K.sofa(HOME, (0, 0.0, 0), width=2.1, seat_h=0.44, color=(0.07, 0.19, 0.22))
K.rug(HOME, (0, -0.55, 0), (2.8, 2.0))
K.coffee_table(HOME, (0.1, -0.95, 0))
lamp = K.floor_lamp(HOME, (1.45, 0.45, 0))
K.potted_plant(HOME, (-1.55, 0.55, 0), h=1.25)
K.bookshelf(HOME, (2.35, 2.9, 0))
K.picture_frame(HOME, (0.0, 3.32, 1.62), (0.95, 0.62), seed=2)
TBOX = Vector((0.45, -0.95, 0.42))
K.tissue_box(HOME, TBOX, rot=(0, 0, 0.25))
K.mug(HOME, (-0.25, -1.0, 0.42))
jug, jug_liquid = K.measuring_jug(HOME, (-0.05, -0.85, 0.42))
_jb = jug_liquid.data.materials[0].node_tree.nodes["Principled BSDF"]
_jb.inputs["Base Color"].default_value = (0.75, 0.9, 1.0, 1)
_jb.inputs["Emission Color"].default_value = (0.35, 0.7, 1.0, 1)
_jb.inputs["Emission Strength"].default_value = 0.25
K.tv_unit(HOME, (0, -3.0, 0)).rotation_euler.z = math.pi
outside_tree = K.tree(HOME, (-1.9, 6.5, -0.5), h=6.5, seed=4, name="WindowTree")
# used tissues pile up on the table and floor during the "years" beat
paper = K.plastic("UsedTissue", (0.95, 0.95, 0.94), 0.8, sss=0.3)
pile = []
for i in range(16):
    if i < 8:
        p = Vector((random.uniform(-0.35, 0.5), random.uniform(-1.12, -0.8), 0.43 + 0.015 * (i // 4)))
    else:
        p = Vector((random.uniform(-0.9, 0.9), random.uniform(-0.45, -0.25), 0.03))
    pile.append(K.cushion(f"UsedTissue{i}", HOME, (0.07, 0.06, 0.05), p, paper, puff=0.9,
                          rot=(random.uniform(0, 3), random.uniform(0, 3), random.uniform(0, 3))))

# CLINIC: consulting room with a desk, lab bench and a patient chair
K.room(CLIN, origin=CLINP + Vector((0, 0.6, 0)), size=(5.5, 5.0, 2.8), floor_mat=K.paint("ClinicFloor", (0.62, 0.66, 0.68), 0.35),
       wall_color=(0.78, 0.86, 0.88), name="Clinic")
K.desk(CLIN, CLINP + Vector((1.5, 1.6, 0)), rot=math.radians(-20))
K.lab_bench(CLIN, CLINP + Vector((-1.2, 2.7, 0)))
K.window(CLIN, CLINP + Vector((1.6, 3.07, 1.5)), size=(1.2, 1.2), curtains=False)
chair_m = K.fabric("ClinicChair", (0.15, 0.25, 0.32))
for nm, size, loc in (("ChairSeat", (0.55, 0.52, 0.1), (0, 0.05, 0.42)), ("ChairBack", (0.55, 0.1, 0.55), (0, 0.32, 0.75))):
    K.cushion(nm, CLIN, size, CLINP + Vector(loc), chair_m, puff=0.3)
for sx in (-1, 1):
    for sy in (-0.18, 0.28):
        K.cyl("ChairLeg", CLIN, 0.015, 0.37, CLINP + Vector((sx * 0.24, sy, 0.185)), K.metal("ChairSteel", (0.75, 0.75, 0.78), 0.3), verts=12)
K.potted_plant(CLIN, CLINP + Vector((-2.2, 1.0, 0)), h=1.3, seed=8)
K.picture_frame(CLIN, CLINP + Vector((-0.4, 3.07, 1.6)), (0.7, 0.5), seed=5)
# vial + test strip held by the doctor (parented to his right hand later)
vial = K.empty("Vial", CLIN, (0, 0, 0))
vparts = [K.cyl("VialGlass", CLIN, 0.011, 0.075, (0, 0, 0.0375), K.glass("VialGlassM"), verts=32),
          K.cyl("VialFluid", CLIN, 0.0098, 0.05, (0, 0, 0.026), K.plastic("CSFClear", (0.85, 0.95, 1.0), 0.02), verts=32),
          K.cyl("VialCap", CLIN, 0.0125, 0.014, (0, 0, 0.079), K.plastic("VialCapM", (0.1, 0.3, 0.85), 0.35), verts=32)]
vparts[1].data.materials[0].node_tree.nodes["Principled BSDF"].inputs["Transmission Weight"].default_value = 0.9
K.parent(vparts, vial)
strip_pad_m = K.plastic("StripPad", (0.95, 0.93, 0.8), 0.6)
strip = K.empty("Strip", CLIN, (0, 0, 0))
K.parent([K.rbox("StripBody", CLIN, (0.006, 0.0012, 0.07), (0, 0, 0.035), K.plastic("StripWhite", (0.95, 0.95, 0.95), 0.4), bevel=0),
          K.rbox("StripPad", CLIN, (0.0062, 0.0014, 0.01), (0, -0.0002, 0.008), strip_pad_m, bevel=0)], strip)

# ROAD at night: two cars, rear-end crash
K.road(ROAD, length=160, y0=CARP.y - 80)
for o in ROAD.objects:
    if o.parent is None:
        o.location.x += CARP.x
for i, y in enumerate((-40, -22, -6, 12, 30)):
    K.tree(ROAD, CARP + Vector((-9.0, y, 0)), h=7.5, seed=i + 20, name=f"RoadTreeL{i}")
    K.tree(ROAD, CARP + Vector((9.5, y + 8, 0)), h=6.5, seed=i + 40, name=f"RoadTreeR{i}")
for i, y in enumerate((-18, 6, 30)):
    K.street_lamp(ROAD, CARP + Vector((-5.0, y, 0.15)))
    sl = bpy.data.lights.new(f"StreetLamp{i}", "SPOT")
    sl.energy, sl.spot_size, sl.spot_blend, sl.color, sl.shadow_soft_size = 3500, math.radians(110), 0.5, (1.0, 0.78, 0.5), 0.3
    so = bpy.data.objects.new(f"StreetLamp{i}", sl)
    ROAD.objects.link(so)
    so.location = CARP + Vector((-3.65, y, 6.4))
car_a = K.car(ROAD, CARP + Vector((1.75, 0, 0)), (0.12, 0.003, 0.003), "CarA", tint=(0.75, 0.8, 0.85))   # hers (stopped)
car_b = K.car(ROAD, CARP + Vector((1.75, 30, 0)), (0.45, 0.47, 0.5), "CarB", interior=False)
for nm in ("CarBHeadBeamL", "CarBHeadBeamR"):
    ld = bpy.data.lights.new(nm, "SPOT")
    ld.energy = 2500
    ld.spot_size = math.radians(55)
    ld.spot_blend = 0.6
    ld.color = (1.0, 0.95, 0.85)
    lo = bpy.data.objects.new(nm, ld)
    ROAD.objects.link(lo)
    lo.parent = car_b
    lo.location = (0.58 if nm.endswith("R") else -0.58, -2.2, 0.7)
    lo.rotation_euler = (math.radians(85), 0, 0)
DASH_LOCAL = Vector((0.42, -0.37, 0.95))       # passenger-side rear-top edge of CarA's dashboard

# OR: table, lamp, monitor
K.room(OR, origin=ORP + Vector((0, 0.8, 0)), size=(6.0, 6.0, 3.0), floor_mat=K.paint("ORFloor", (0.55, 0.68, 0.66), 0.3),
       wall_color=(0.62, 0.78, 0.76), name="ORRoom")
K.or_table(OR, ORP + Vector((0, 0.9, 0)))
K.surgical_lamp(OR, ORP + Vector((0.1, 1.5, 2.35)))
K.vital_monitor(OR, ORP + Vector((1.1, 2.4, 1.45)), rot=math.radians(-30))
K.rbox("InstrumentTray", OR, (0.6, 0.4, 0.03), ORP + Vector((-0.9, 1.8, 1.0)), K.metal("TraySteel", (0.8, 0.8, 0.82), 0.25), bevel=0.01)
K.cyl("TrayPole", OR, 0.02, 1.0, ORP + Vector((-0.9, 1.8, 0.5)), K.metal("TraySteel", (0.8, 0.8, 0.82), 0.25), verts=12)
drape = K.cushion("Drape", OR, (0.7, 1.3, 0.12), ORP + Vector((0, 0.45, 1.02)), K.fabric("Drape", (0.12, 0.4, 0.45), weave=300), puff=0.4)

# ---------------------------------------------------------------- shots
# (start seconds, camera name, set, her pose)  set: home/clinic/car/carint/or/xray
SHOTS = [
    (0.0, "NoseECU", "home", "sit"), (at(0, 0.30), "XSide", "xray", "sit"), (at(0, 0.62), "Clinic2Shot", "clinic", "sit"),
    (B[1], "RoadWide", "car", "car"), (IMPACT - 0.05, "RoadImpact", "car", "car"), (at(1, 0.62), "CarInt", "carint", "car"),
    (at(1, 0.93), "XCrash", "xray", "car"),
    (B[2], "HomeWide", "home", "sit"),
    (B[3], "VialCU", "clinic", "sit"), (MUCUS - 0.15, "StripMacro", "clinic", "sit"),
    (B[4], "XOrbit", "xray", "sit"), (B[5], "XHole", "xray", "sit"),
    (B[6], "JugShot", "home", "sit"), (B[7], "XBact", "xray", "sit"),
    (B[8], "ORWide", "or", "lie"), (at(8, 0.38), "XSurg", "xray", "lie"),
    (B[9], "HomeFront", "home", "sit"),
]


def shot_at(t):
    return max((s for s in SHOTS if s[0] <= t + 1e-6), key=lambda s: s[0])


SH = [shot_at(t) for t in T]
SET_OF = [s[2] for s in SH]
XRAY = [1.0 if s == "xray" else 0.0 for s in SET_OF]

# where she is (rig root) for each pose / set; X-ray shots keep her at the previous physical location
legs_sit, legs_stand = her.seated_legs(), her.standing_legs()
SEAT_HOME = HOMEP + Vector((0, 0.32, 0.53))
SEAT_CLIN = CLINP + Vector((0, 0.1, 0.55))
SEAT_CAR = CARP + Vector((1.75, 0, 0)) + Vector((0.42, 0.22, 0.68))
TABLE = ORP + Vector((0, 0.9, 0))


def her_root(t, s):
    """(location, euler) of her rig object."""
    name, pose = s[2], s[3]
    hips = her.hips0
    if pose == "lie":                      # on her back: local +Z (height) -> world +Y, her back rests on the pad
        return Vector((TABLE.x - her.x0, TABLE.y - 0.92, 0.945 + 0.12)), (math.radians(-90), 0, 0)
    if pose == "car":
        return SEAT_CAR - hips, (0, 0, 0)
    if name == "clinic":
        return SEAT_CLIN - hips, (0, 0, 0)
    return SEAT_HOME - hips, (0, 0, 0)


DOC_CLIN = CLINP + Vector((-0.45, -1.05, 0)), (0, 0, math.pi)          # facing her (+Y)
DOC_OR = Vector((TABLE.x - (doc.x0 if doc else 0), TABLE.y + 1.32, 0)), (0, 0, 0)   # at her head end, facing -Y


def doc_root(t, s):
    if s[2] == "clinic":
        return DOC_CLIN
    if s[2] == "or" or (s[2] == "xray" and s[3] == "lie"):
        return DOC_OR
    return FAR, (0, 0, 0)


# ---------------------------------------------------------------- anchors on the characters
nose_l = her.anchor("NoseWipe", "Head", Vector((her.x0 - 0.03, her.nose.y - 0.07, her.nose.z - 0.05)), CAST)
nostril = her.anchor("Nostril", "Head", Vector((her.x0 + 0.006, her.nose.y + 0.012, her.nose.z - 0.02)), CAST)
face_pt = her.anchor("Face", "Head", Vector((her.x0, her.nose.y + 0.06, her.nose.z - 0.02)), CAST)
eye_pt = her.anchor("Eyes", "Head", Vector((her.x0 + 0.03, her.nose.y + 0.02, her.nose.z + 0.04)), CAST)
tissue_pick = K.empty("TissuePick", HOME, TBOX + Vector((0, 0, 0.14)))
hand_r = her.rig.data.bones[A.MX + "RightHand"]
tissue = K.cushion("HandTissue", CAST, (0.09, 0.06, 0.07), hand_r.tail_local + Vector((0, -0.02, -0.03)), paper, puff=0.9)
her.parent_to_bone(tissue, "RightHand")
her.hand_follow("Right", nose_l, "ToNose")
her.hand_follow("Right", tissue_pick, "ToBox")
her_aim = her.anchor("HandAim", "Head", Vector((her.x0, her.nose.y + 0.01, her.nose.z + 0.02)), CAST)
her.hand_aim("Right", her_aim)
if doc:
    doc.tint_material("suit", (0.93, 0.94, 0.96), 0.9)                 # white coat
    doc_face = doc.anchor("Face", "Head", Vector((doc.x0, doc.nose.y + 0.06, doc.nose.z - 0.02)), CAST)
    doc_eyes = doc.anchor("Eyes", "Head", Vector((doc.x0 + 0.03, doc.nose.y + 0.02, doc.nose.z + 0.04)), CAST)
    steth = K.tube("Stethoscope", CAST, [Vector((doc.x0 - 0.09, doc.nose.y + 0.09, doc.nose.z - 0.17)),
                                         Vector((doc.x0, doc.nose.y + 0.03, doc.nose.z - 0.2)),
                                         Vector((doc.x0 + 0.09, doc.nose.y + 0.09, doc.nose.z - 0.17)),
                                         Vector((doc.x0 + 0.1, doc.nose.y + 0.0, doc.nose.z - 0.33))], 0.005,
                   K.plastic("StethRubber", (0.02, 0.02, 0.025), 0.4))
    doc.parent_to_bone(steth, "Spine2")
    cap = K.sphere("SurgCap", CAST, 1.0, Vector((doc.x0, (doc.nose.y + doc.back_y) / 2 + 0.01, doc.top - 0.06)),
                   K.fabric("ScrubBlue", (0.12, 0.35, 0.5), weave=500), scale=(0.1, 0.12, 0.085))
    mask = K.cushion("SurgMask", CAST, (0.15, 0.03, 0.09), Vector((doc.x0, doc.nose.y + 0.012, doc.nose.z - 0.035)),
                     K.fabric("MaskBlue", (0.35, 0.6, 0.75), weave=600), puff=0.8)
    for o in (cap, mask):
        doc.parent_to_bone(o, "Head")
    vial_hold = doc.anchor("VialHold", "Head", Vector((doc.x0 - 0.06, doc.nose.y - 0.22, doc.nose.z + 0.02)), CAST)
    hand_dr = doc.rig.data.bones[A.MX + "RightHand"]
    vial.location = hand_dr.tail_local + Vector((0, -0.03, 0.0))
    doc.parent_to_bone(vial, "RightHand")
    hand_dl = doc.rig.data.bones[A.MX + "LeftHand"]
    strip.location = hand_dl.tail_local + Vector((0, -0.03, 0.0))
    doc.parent_to_bone(strip, "LeftHand")
    scope_grip = K.empty("ScopeGrip", CAST, (0, 0, 0))
    doc.hand_follow("Right", scope_grip, "ToScope")

# ---------------------------------------------------------------- X-ray anatomy (rig-local rest space of her head)
ANAT = K.coll("Anatomy")
head_len = her.back_y - her.nose.y
BR_RY = min(0.085, max(0.06, head_len * 0.36))
BR_RX, BR_RZ = BR_RY * 0.8, BR_RY * 0.66
BR_C = Vector((her.x0, her.nose.y + head_len * 0.56, her.top - 0.03 - BR_RZ))
HOLE = Vector((her.x0, her.nose.y + head_len * 0.30, her.nose.z + 0.045))
if BR_C.z - BR_RZ * 0.9 < HOLE.z + 0.004:
    BR_C.z = HOLE.z + 0.004 + BR_RZ * 0.9
NOSTRIL = Vector((her.x0 + 0.006, her.nose.y + 0.014, her.nose.z - 0.02))
PATH = [HOLE + Vector((0, 0.002, 0.006)), HOLE, Vector((her.x0, HOLE.y - 0.010, HOLE.z - 0.022)),
        Vector((her.x0 + 0.003, her.nose.y + 0.032, her.nose.z - 0.008)), NOSTRIL]


def path_point(u):
    pts = [PATH[0]] + PATH + [PATH[-1]]
    n = len(PATH) - 1
    u = min(max(u, 0.0), 1.0) * n
    i = min(int(u), n - 1)
    s = u - i
    p0, p1, p2, p3 = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
    return 0.5 * ((2 * p1) + (-p0 + p2) * s + (2 * p0 - 5 * p1 + 4 * p2 - p3) * s * s + (-p0 + 3 * p1 - 3 * p2 + p3) * s * s * s)


def path_tangent(u):
    return (path_point(min(1, u + 0.02)) - path_point(max(0, u - 0.02))).normalized()


def xglow(name, color, strength, blend=0.25, core=0.03, value=None):
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
    em.name = "Glow"
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = strength
    if value:
        v = N.new("ShaderNodeValue")
        v.name = value
        v.outputs[0].default_value = 1.0
        mul = N.new("ShaderNodeMath")
        mul.operation = "MULTIPLY"
        mul.inputs[1].default_value = strength
        L.new(v.outputs[0], mul.inputs[0])
        L.new(mul.outputs[0], em.inputs["Strength"])
    tr = N.new("ShaderNodeBsdfTransparent")
    mx = N.new("ShaderNodeMixShader")
    L.new(mr.outputs[0], mx.inputs[0])
    L.new(tr.outputs[0], mx.inputs[1])
    L.new(em.outputs[0], mx.inputs[2])
    L.new(mx.outputs[0], out.inputs["Surface"])
    return m


skull_m = xglow("SkullXRay", (0.95, 0.93, 0.85), 1.0, blend=0.12, core=0.0)
csf_m = xglow("CSFGlow", (0.25, 0.75, 1.0), 2.4, blend=0.2, core=0.03, value="Pulse")
alarm = csf_m.node_tree.nodes.new("ShaderNodeValue")
alarm.name = "Alarm"
cmix = csf_m.node_tree.nodes.new("ShaderNodeMix")
cmix.data_type = "RGBA"
cmix.inputs["A"].default_value = (0.25, 0.75, 1.0, 1)
cmix.inputs["B"].default_value = (1.0, 0.12, 0.08, 1)
csf_m.node_tree.links.new(alarm.outputs[0], cmix.inputs["Factor"])
csf_m.node_tree.links.new(cmix.outputs["Result"], csf_m.node_tree.nodes["Glow"].inputs["Color"])
airway_m = xglow("Airway", (1.0, 0.55, 0.6), 1.8, blend=0.3, core=0.08)
anat = []
anat.append(K.sphere("Skull", ANAT, 1.0, BR_C, skull_m, scale=(BR_RX * 1.16, BR_RY * 1.16, BR_RZ * 1.25), subdiv=5))
anat.append(K.sphere("CSF", ANAT, 1.0, BR_C, csf_m, scale=(BR_RX * 1.07, BR_RY * 1.07, BR_RZ * 1.15), subdiv=5))
anat += K.brain(ANAT, BR_C, size=(BR_RX * 2 * 0.98, BR_RY * 0.98, BR_RZ * 0.97), subdiv=5)
plate_m = K.plastic("SkullBase", (0.92, 0.88, 0.78), 0.5)
plate_m.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (0.9, 0.87, 0.8, 1)
plate_m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 0.4
anat.append(K.cyl("SkullBasePlate", ANAT, 0.026, 0.003, HOLE, plate_m, rot=(math.radians(-8), 0, 0), verts=48))
anat.append(K.cyl("Hole", ANAT, 0.0042, 0.0036, HOLE + Vector((0, 0, 0.0002)), K.emissive("HoleDark", (0, 0, 0), 0), rot=(math.radians(-8), 0, 0)))
ring_m = K.emissive("HoleRing", (1.0, 0.15, 0.08), 0.0)
ring = K.lathe("HoleRingMesh", ANAT, [(0.0045, -0.0006), (0.0055, 0.0), (0.0045, 0.0006)], HOLE, ring_m, steps=32,
               rot=(math.radians(-8), 0, 0))
anat.append(ring)
cracks = []
for k, a in enumerate((20, 140, 250)):
    d = Vector((math.cos(math.radians(a)), math.sin(math.radians(a)), 0))
    cr = K.cyl(f"Crack{k}", ANAT, 0.0006, 0.010, HOLE + d * 0.009, ring_m, rot=(0, math.radians(90), math.radians(a)), verts=8)
    cracks.append(cr)
    anat.append(cr)
air = K.tube("AirwayTube", ANAT, [path_point(i / 12) for i in range(13)] + [NOSTRIL + Vector((0, -0.003, -0.006))], 0.0055, airway_m)
anat.append(air)
drip_m = K.emissive("DripGlow", (0.35, 0.8, 1.0), 7.0)
bact_m = K.plastic("Bacteria", (0.2, 0.9, 0.2), 0.4)
bact_m.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (0.25, 1.0, 0.3, 1)
bact_m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 2.5
fat_m = K.plastic("FatGraft", (1.0, 0.82, 0.3), 0.45, sss=0.5)
fat_m.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (1.0, 0.8, 0.3, 1)
fat_m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 0.8
scope = K.cyl("Endoscope", ANAT, 0.0032, 0.12, (0, 0, 0), K.metal("ScopeSteel", (0.2, 0.2, 0.22), 0.25), verts=16)
scope.data.transform(Matrix.Translation((0, 0, -0.06)))
scope_tip = K.sphere("ScopeTip", ANAT, 0.0024, (0, 0, 0), K.emissive("ScopeLight", (1, 1, 0.95), 25), subdiv=2)
scope_tip.parent = scope
fat = K.sphere("FatGraft", ANAT, 1.0, (0, 0, 0), fat_m, scale=(1, 1, 0.75), subdiv=3)
LEAK = [(at(0, 0.30), at(0, 0.62)), (at(1, 0.93), B[2]), (B[4], SEAL + 0.1)]
drops, bugs = [], []
proto = K.sphere("DripProto", ANAT, 1.0, (0, 0, -50), drip_m, subdiv=2)
t0 = 0.0
while t0 < DUR:
    if any(a - 0.7 <= t0 <= b for a, b in LEAK) and t0 < SEAL - 0.15:
        o = bpy.data.objects.new("Drip", proto.data)
        ANAT.objects.link(o)
        drops.append((o, t0 + random.uniform(0, 0.03), random.uniform(0.0011, 0.0019),
                      Vector((random.uniform(-0.0008, 0.0008), random.uniform(-0.0008, 0.0008), 0))))
    t0 += 0.066
for i in range(34):
    o = K.sphere(f"Bacterium{i}", ANAT, 1.0, (0, 0, -50), bact_m, subdiv=2)
    tex = bpy.data.textures.new("BactTex", "CLOUDS")
    tex.noise_scale = 0.5
    dp = o.modifiers.new("Disp", "DISPLACE")
    dp.texture = tex
    dp.strength = 0.35
    bugs.append((o, B[7] + random.uniform(0, (B[8] - B[7]) * 0.45), random.uniform(0.7, 1.0),
                 Vector((random.uniform(-1, 1) * BR_RX * 0.7, random.uniform(-0.6, 0.6) * BR_RY, 0)), random.uniform(0.0016, 0.0028),
                 random.uniform(0, 9)))
for o in list(ANAT.objects):
    if o.parent is None:
        her.parent_to_bone(o, "Head")          # basis = rig-local rest coordinates

# ---------------------------------------------------------------- X-ray look on her materials (driven by scene["xray"])
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
for o in her.objs:
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

# ---------------------------------------------------------------- performance
WIPES = [(at(0, 0.66), at(0, 0.95)), (at(2, 0.05), at(2, 0.33)), (at(2, 0.55), at(2, 0.85)), (at(6, 0.62), at(6, 0.95))]
SNIFFS = [at(0, 0.1), at(0, 0.7), at(2, 0.42), at(6, 0.25), at(3, 0.2)]
BLINKS = [b for b in (x * 2.7 + 0.9 for x in range(40)) if b < DUR]


def her_channels(t):
    ch = {}
    w_reach, w_nose = 0.0, 0.0
    for a, b in WIPES:
        d = b - a
        w_reach = max(w_reach, env(t, a, a + 0.18 * d, a + 0.32 * d, a + 0.45 * d))
        w_nose = max(w_nose, env(t, a + 0.35 * d, a + 0.5 * d, b - 0.18 * d, b))
    ch["reach"], ch["wipe"] = w_reach, w_nose
    ch["sniff"] = max((spike(t, s, 0.08, 0.15) for s in SNIFFS), default=0.0)
    ch["worry"] = max(env(t, 0, 0.2, B[1] - 0.2, B[1]), env(t, B[2], B[2] + 0.2, B[3] - 0.1, B[3]),
                      env(t, B[6], B[6] + 0.2, B[7] - 0.2, B[7]), env(t, B[3], B[3] + 0.2, B[4] - 0.2, B[4]) * 0.7)
    ch["lean"] = env(t, at(6, 0.1), at(6, 0.4), B[7] - 0.2, B[7] + 0.1)
    ch["brace"] = spike(t, IMPACT, 0.06, 0.12)                       # back into the seat on impact
    ch["lurch"] = env(t, FACE_HIT - 0.35, FACE_HIT, FACE_HIT + 0.08, FACE_HIT + 0.5)
    ch["daze"] = env(t, FACE_HIT + 0.3, FACE_HIT + 0.55, B[2] - 0.1, B[2])
    ch["wince"] = spike(t, FACE_HIT, 0.04, 0.25)
    ch["look_doc"] = max(env(t, at(0, 0.62), at(0, 0.7), B[1] - 0.1, B[1]), env(t, B[3], B[3] + 0.15, B[4] - 0.1, B[4]))
    ch["relief"] = ramp(t, B[9] + 0.05, B[9] + 0.5)
    ch["nod"] = spike(t, at(9, 0.78), 0.12, 0.2)
    ch["sedated"] = 1.0 if B[8] <= t < B[9] else 0.0
    ch["blink"] = max((env(t, b - 0.03, b, b + 0.05, b + 0.12) for b in BLINKS), default=0.0)
    ch["tired"] = env(t, B[2], B[2] + 0.2, B[3] - 0.2, B[3])
    return ch


def doc_channels(t):
    ch = {}
    ch["shrug"] = env(t, at(0, 0.70), at(0, 0.80), at(0, 0.92), B[1])
    ch["offer"] = env(t, at(0, 0.66), at(0, 0.78), B[1] - 0.15, B[1])
    ch["raise"] = env(t, B[3] + 0.05, B[3] + 0.4, B[4] - 0.2, B[4])
    ch["surprise"] = env(t, MUCUS - 0.05, MUCUS + 0.12, B[4] - 0.2, B[4])
    ch["operate"] = 1.0 if B[8] <= t < B[9] else 0.0
    ch["blink"] = max((env(t, b - 0.03, b, b + 0.05, b + 0.12) for b in (x * 3.1 + 1.4 for x in range(40)) if b < DUR), default=0.0)
    return ch


THIGH_R = her.hips0.lerp(her.bone_rest_head("RightLeg"), 0.6) + Vector((-0.03, -0.25, 0.07))
THIGH_L = her.hips0.lerp(her.bone_rest_head("LeftLeg"), 0.6) + Vector((0.03, -0.25, 0.07))
WHEEL_HANDS = None
for i, t in enumerate(T):
    s = SH[i]
    ch = her_channels(t)
    br = math.sin(t * 2 * math.pi / 3.6)
    lie = s[3] == "lie"
    fwd = 30 * ch["lurch"] - 10 * ch["brace"] + 12 * ch["lean"] + 5 * ch["wipe"]
    rots = {}
    spec = {
        "Hips": [(A.Z, 0.5 * wobble(t, 1))],
        "Spine": [(A.X, (0 if lie else -9) + 0.5 * br + 0.45 * fwd), (A.Z, 0.8 * wobble(t, 2))],
        "Spine1": [(A.X, (0 if lie else -3) + 0.7 * br + 0.35 * fwd - 2 * ch["relief"])],
        "Spine2": [(A.X, 2 + 0.7 * br + 0.2 * fwd)],
        "Neck": [(A.X, (0 if lie else 4) + 0.25 * fwd + 4 * ch["tired"] + 3 * ch["nod"]), (A.Z, 1.5 * wobble(t, 4) + 8 * ch["look_doc"])],
        "Head": [(A.X, 1 + 0.35 * fwd + 8 * ch["daze"] - 5 * ch["sniff"] + 6 * ch["tired"] + 6 * ch["nod"] + 1.0 * wobble(t, 7, 0.6)),
                 (A.Z, 2.0 * wobble(t, 5, 0.5) * (1 - ch["sedated"]) - 7 * ch["daze"] + 12 * ch["look_doc"]),
                 (A.Y, 1.2 * wobble(t, 6) + 9 * ch["daze"] + 4 * ch["worry"])],
        "LeftShoulder": [(A.Y, 3 * ch["sniff"] + 5 * ch["lurch"])],
        "RightShoulder": [(A.Y, -3 * ch["sniff"] - 5 * ch["lurch"])],
    }
    for bone, axes in spec.items():
        if her.has(bone):
            q = A.Quaternion()
            for axis, deg in axes:
                q = q @ her.q(bone, axis, deg)
            rots[bone] = q
    for bone, q in (legs_sit if not lie else {}).items():
        rots[bone] = q
    if lie:
        for bone in ("LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg", "LeftFoot", "RightFoot"):
            if her.has(bone):
                rots[bone] = A.Quaternion()
    for bone in her.fingers():
        j = int(bone[-1])
        curl = ({1: 25, 2: 35, 3: 25} if "Thumb" not in bone else {1: 8, 2: 15, 3: 10})[j]
        if bone.startswith("Right"):
            curl += 35 * max(ch["wipe"], ch["reach"])
        rots[bone] = A.Quaternion((1, 0, 0), math.radians(curl))
    sh = {}
    for side in ("Left", "Right"):
        sh[f"eyeBlink{side}"] = min(1, ch["blink"] + 0.9 * ch["wince"] + 0.4 * ch["daze"] + 0.25 * ch["tired"] + ch["sedated"]
                                    + 0.15 * ch["relief"])
        sh[f"eyeSquint{side}"] = 0.5 * ch["sniff"] + 0.4 * ch["wince"] + 0.35 * ch["relief"]
        sh[f"eyeWide{side}"] = 0.6 * ch["brace"]
        sh[f"browDown{side}"] = 0.6 * ch["wince"] + 0.25 * ch["sniff"]
        sh[f"noseSneer{side}"] = 0.8 * ch["sniff"] + 0.4 * ch["wipe"]
        sh[f"mouthFrown{side}"] = 0.35 * ch["worry"] + 0.2 * ch["tired"]
        sh[f"mouthStretch{side}"] = 0.4 * ch["wince"]
        sh[f"mouthSmile{side}"] = 0.7 * ch["relief"]
        sh[f"cheekSquint{side}"] = 0.4 * ch["relief"]
    sh["browInnerUp"] = 0.6 * ch["worry"] + 0.4 * ch["tired"] + 0.3 * ch["daze"]
    sh["jawOpen"] = 0.25 * ch["brace"] + 0.2 * ch["daze"] + 0.15 * ch["wince"]
    if lie:
        ikl = her.hips0 + Vector((0.24, -0.02, 0.0))
        ikr = her.hips0 + Vector((-0.24, -0.02, 0.0))
    else:
        ikl = THIGH_L + Vector((0, -0.12 * ch["lurch"], 0.04 * ch["lurch"]))
        ikr = THIGH_R.copy()
    follow = {"ToNose": ch["wipe"], "ToBox": ch["reach"] * (1.0 if s[2] == "home" else 0.0)}
    her.record(rots, sh, ikl, ikr, aim=(0.0, min(1.0, 1.4 * ch["wipe"])), follow=follow, root=her_root(t, s))

if doc:
    dlegs = doc.standing_legs()
    for i, t in enumerate(T):
        s = SH[i]
        ch = doc_channels(t)
        br = math.sin(t * 2 * math.pi / 4.0 + 1)
        op = ch["operate"]
        rots = {}
        spec = {
            "Spine": [(A.X, 2 + 0.4 * br + 18 * op)], "Spine1": [(A.X, 2 + 0.5 * br + 10 * op)],
            "Neck": [(A.X, 5 + 3 * ch["raise"] + 12 * op), (A.Z, 1.2 * wobble(t, 3))],
            "Head": [(A.X, 3 - 4 * ch["surprise"] + 10 * op + wobble(t, 9, 0.5)), (A.Y, 6 * ch["shrug"] + 1.5 * wobble(t, 4)),
                     (A.Z, 2 * wobble(t, 8, 0.4))],
            "LeftShoulder": [(A.Y, 9 * ch["shrug"])], "RightShoulder": [(A.Y, -9 * ch["shrug"])],
        }
        for bone, axes in spec.items():
            if doc.has(bone):
                q = A.Quaternion()
                for axis, deg in axes:
                    q = q @ doc.q(bone, axis, deg)
                rots[bone] = q
        rots.update(dlegs)
        for bone in doc.fingers():
            j = int(bone[-1])
            rots[bone] = A.Quaternion((1, 0, 0), math.radians(({1: 30, 2: 45, 3: 30} if "Thumb" not in bone else {1: 10, 2: 20, 3: 10})[j]))
        sh = {}
        for side in ("Left", "Right"):
            sh[f"eyeBlink{side}"] = ch["blink"]
            sh[f"eyeWide{side}"] = 0.7 * ch["surprise"]
            sh[f"browOuterUp{side}"] = 0.6 * ch["surprise"] + 0.4 * ch["shrug"]
            sh[f"mouthSmile{side}"] = 0.25 * ch["shrug"]
            sh[f"mouthPress{side}"] = 0.4 * ch["shrug"]
        sh["browInnerUp"] = 0.5 * ch["shrug"] + 0.6 * ch["surprise"]
        sh["jawOpen"] = 0.25 * ch["surprise"]
        hip = doc.hips0
        side_l = hip + Vector((0.22, 0.02, -0.12))
        side_r = hip + Vector((-0.22, 0.02, -0.12))
        offer = hip + Vector((-0.12, -0.45, 0.25))
        hold = Vector((doc.x0 - 0.08, doc.nose.y - 0.3, doc.nose.z - 0.02))
        strip_hold = Vector((doc.x0 + 0.1, doc.nose.y - 0.3, doc.nose.z - 0.12))
        ikr = side_r.lerp(offer, ch["offer"]).lerp(hold, ch["raise"])
        ikl = side_l.lerp(strip_hold, ch["raise"])
        doc.record(rots, sh, ikl, ikr, follow={"ToScope": op}, root=doc_root(t, s))

# scope grip follows her nostril (world), so the surgeon's hand is at her nose in the OR
# (filled after baking her, below)

# ---------------------------------------------------------------- bake characters
her.bake(FRAMES)
if doc:
    doc.bake(FRAMES)
for o, path in ((her.rig, "location"), (her.rig, "rotation_euler")):
    for fc in A.fcurves_of(o):
        if fc.data_path == path:
            fc.keyframe_points.foreach_set("interpolation", [0] * len(fc.keyframe_points))   # teleports are cuts
if doc:
    for fc in A.fcurves_of(doc.rig):
        if fc.data_path in ("location", "rotation_euler"):
            fc.keyframe_points.foreach_set("interpolation", [0] * len(fc.keyframe_points))

# ---------------------------------------------------------------- props driven by time
bake_vec(tissue, "scale", [(s, s, s) for s in ((1.0 if (her_channels(t)["wipe"] > 0.02 or her_channels(t)["reach"] > 0.6)
                                                and SET_OF[i] == "home" else 0.0) for i, t in enumerate(T))], interp="CONSTANT")
for i, o in enumerate(pile):
    t_in = B[2] + (i + 1) * (B[3] - B[2] - 0.2) / (len(pile) + 1)
    s0 = tuple(o.scale)
    bake_vec(o, "scale", [tuple(v * ramp(t, t_in, t_in + 0.08) for v in s0) for t in T])
bake(jug_liquid, "scale", [0.001 + 0.62 * ramp(t, B[6] + 0.1, at(6, 0.85)) for t in T], index=2)
# window: day/night cycles during "years", tree outside turns autumn and back
sky_m = bpy.data.materials["SkyCard"] if "SkyCard" in bpy.data.materials else None
cyc = [0.5 + 0.5 * math.cos(2 * math.pi * 3 * ramp(t, B[2], B[3])) if B[2] <= t < B[3] else 1.0 for t in T]
if sky_m:
    bake(sky_m.node_tree, 'nodes["Principled BSDF"].inputs["Emission Strength"].default_value', [0.15 + 2.85 * k for k in cyc])
leaf_m = next((m for m in bpy.data.materials if m.name.startswith("TreeLeaf")), None)
# vial: doctor holds it; strip pad turns bright green on "It wasn't mucus"
for k, comp in enumerate((0.1, 0.85, 0.3)):
    bake(strip_pad_m.node_tree, 'nodes["Principled BSDF"].inputs[0].default_value',
         [(0.95, 0.93, 0.8)[k] + (comp - (0.95, 0.93, 0.8)[k]) * ramp(t, MUCUS - 0.05, MUCUS + 0.15) for t in T], index=k)

# her nose drip in home shots (a real, glossy droplet that swells and falls)
drop = K.sphere("NoseDrop", CAST, 1.0, (0, 0, 0), K.glass("Droplet", rough=0.0, ior=1.33), subdiv=3)
d_loc, d_s = [], []
phase, falling, fall_from = 0.0, 0, None
for i, t in enumerate(T):
    if i % 1 == 0:
        scene.frame_set(i + 1)
    n = nostril.matrix_world.translation.copy()
    ch = her_channels(t)
    hidden = ch["wipe"] > 0.05 or t >= B[9] or SET_OF[i] not in ("home", "clinic")
    if falling:
        falling += 1
        tt = falling / FPS
        d_loc.append(fall_from + Vector((0, -0.02 * tt, -4.9 * tt * tt)))
        d_s.append(0.0035)
        if tt > 0.4:
            falling, phase = 0, 0.0
        continue
    phase += (1 / (1.1 * FPS)) * (1 + 1.5 * ch["lean"])
    if phase >= 1.0 and not hidden:
        falling, fall_from = 1, n.copy()
    d_loc.append(n + Vector((0, 0, -0.002 * min(phase, 1))))
    d_s.append(0.0 if hidden else 0.0012 + 0.0024 * min(phase, 1))
bake_vec(drop, "location", d_loc)
bake_vec(drop, "scale", [(s, s, s * 1.2) for s in d_s])

# crash: CarB rushes in and hits CarA; CarA jolts forward, then the dashboard meets her face
def car_b_y(t):                            # constant speed into the impact, small bounce back after
    if t < IMPACT:
        k = min(1.0, max(0.0, (t - B[1]) / max(0.1, IMPACT - B[1])))
        return CARP.y + 32.0 - (32.0 - 4.5) * k
    return CARP.y + 4.5 + 0.4 * (1 - math.exp(-(t - IMPACT) / 0.08)) * math.exp(-(t - IMPACT) / 0.5)


bake(car_b, "location", [car_b_y(t) for t in T], index=1)
ya = [CARP.y - 0.45 * ramp(t, IMPACT, IMPACT + 0.25) for t in T]
bake(car_a, "location", ya, index=1)
bake(car_a, "rotation_euler", [math.radians(-1.5) * spike(t, IMPACT, 0.01, 0.15) for t in T], index=0)
# her root moves with her car after the impact (rig is not parented to the car)
# -> shift her recorded root by the same jolt
for fc in A.fcurves_of(her.rig):
    if fc.data_path == "location" and fc.array_index == 1:
        pts = fc.keyframe_points
        for i, kp in enumerate(pts):
            if SH[i][3] == "car":
                kp.co[1] += ya[i] - CARP.y
        fc.update()
# her face lands on the dashboard: slide the dashboard so its edge meets her nose at FACE_HIT
scene.frame_set(F(FACE_HIT))
nose_w = nostril.matrix_world.translation.copy()
dash = next(o for o in bpy.data.objects if o.name.startswith("Dashboard") and o.parent is car_a)
target_local = car_a.matrix_world.inverted() @ (nose_w + Vector((0, -0.015, -0.04)))
dash.location.y += target_local.y - DASH_LOCAL.y
dash.location.z += target_local.z - DASH_LOCAL.z

# scope grip = her nostril in world space (OR), surgeon's right hand follows it
nost_w = []
for i in range(len(T)):
    if SH[i][3] == "lie":
        scene.frame_set(i + 1)
        nost_w.append(nostril.matrix_world.translation + Vector((0, -0.06, -0.02)))
    else:
        nost_w.append(Vector((0, 0, -200)))
if doc:
    bake_vec(scope_grip, "location", nost_w)

# X-ray particles, scope, fat, cracks, CSF pulse/alarm (rig-local rest space of her head)
TRAVEL, FALL = 0.7, 0.27
for o, born, r, jit in drops:
    locs, sc = [], []
    for t in T:
        age = t - born
        if age < 0 or age > TRAVEL + FALL:
            locs.append(PATH[0])
            sc.append(0.0)
        elif age <= TRAVEL:
            locs.append(path_point(age / TRAVEL) + jit)
            sc.append(r * min(1.0, age / 0.07))
        else:
            tf = age - TRAVEL
            locs.append(NOSTRIL + jit + Vector((0, -0.01 * tf, -4.9 * tf * tf)))
            sc.append(r * (1 - tf / FALL))
    bake_vec(o, "location", locs)
    bake_vec(o, "scale", [(v, v, v) for v in sc])
for o, born, durk, spread, r, seed in bugs:
    dur = 0.8 * durk
    locs, sc = [], []
    for t in T:
        age = t - born
        if age < 0 or t >= B[8]:
            locs.append(NOSTRIL)
            sc.append(0.0)
            continue
        u = min(1.0, age / dur)
        p = path_point(1 - u) if u < 1 else PATH[0] + (spread + Vector((0, 0, 0.004))) * min(1.0, (age - dur) / 0.5)
        p = p + Vector((0.0012 * math.sin(t * 40 + seed), 0.0012 * math.cos(t * 50 + seed), 0))
        locs.append(p)
        sc.append(r * min(1.0, age / 0.1) * (1 + 0.12 * math.sin(t * 70 + seed)))
    bake_vec(o, "location", locs)
    bake_vec(o, "scale", [(v, v, v) for v in sc])
S_IN, S_OUT = B[8] + 0.1, SEAL - 0.04


def scope_u(t):
    return 1.15 - 1.09 * ramp(t, S_IN, S_OUT) + 1.1 * ramp(t, SEAL + 0.15, SEAL + 0.5)


sl, sr, ss, fl, fs = [], [], [], [], []
for t in T:
    u = scope_u(t)
    tip = path_point(u) if u <= 1 else NOSTRIL + (NOSTRIL - path_point(0.95)).normalized() * 0.03 * (u - 1) / 0.15
    tan = path_tangent(min(u, 0.99))
    sl.append(tip)
    sr.append(Vector((0, 0, 1)).rotation_difference(-tan))
    on = B[8] <= t < B[9]
    ss.append(1.0 if on else 0.0)
    if t < SEAL:
        fl.append(tip + (-tan) * 0.004)
        fs.append(0.0036 if on else 0.0)
    else:
        k = ramp(t, SEAL, SEAL + 0.1)
        fl.append(HOLE + Vector((0, 0, -0.0012 * k)))
        fs.append(0.0036 + 0.0024 * k)
bake_vec(scope, "location", sl)
scope.rotation_mode = "QUATERNION"
bake_vec(scope, "rotation_quaternion", sr, n=4)
bake_vec(scope, "scale", [(v, v, v) for v in ss], interp="CONSTANT")
bake_vec(fat, "location", fl)
bake_vec(fat, "scale", [(v, v, v * 0.75) for v in fs])
for cr in cracks:
    bake_vec(cr, "scale", [(1, 1, max(0.001, max(ramp(t, FACE_HIT + 0.05, FACE_HIT + 0.12), ramp(t, CRACK - 0.05, CRACK + 0.1)))) for t in T])
bake(ring_m.node_tree, 'nodes["Principled BSDF"].inputs["Emission Strength"].default_value',
     [8.0 * max(spike(t, FACE_HIT + 0.06, 0.02, 0.5), ramp(t, CRACK - 0.03, CRACK + 0.05)) for t in T])
for k, (a_, b_) in enumerate(((1.0, 0.2), (0.15, 1.0), (0.08, 0.35))):
    bake(ring_m.node_tree, 'nodes["Principled BSDF"].inputs["Emission Color"].default_value',
         [a_ if t < SEAL else b_ for t in T], index=k, interp="CONSTANT")
bake(csf_m.node_tree, 'nodes["Pulse"].outputs[0].default_value',
     [0.75 + 0.25 * math.sin(t * 2 * math.pi / 1.1) + 0.6 * env(t, B[4], B[4] + 0.2, B[5] - 0.1, B[5]) for t in T])
bake(csf_m.node_tree, 'nodes["Alarm"].outputs[0].default_value', [ramp(t, at(7, 0.55), at(7, 0.85)) * (1 - ramp(t, B[8], B[8] + 0.1)) for t in T])

# ---------------------------------------------------------------- visibility per set
in_set = {"home": HOME, "clinic": CLIN, "car": ROAD, "carint": ROAD, "or": OR}


def key_vis(objs, fn):
    for o in objs:
        prev = None
        for i in range(len(T)):
            v = bool(fn(i))
            if v != prev:
                o.hide_render = not v
                o.keyframe_insert("hide_render", frame=i + 1)
                prev = v


key_vis([o for o in ANAT.objects], lambda i: SET_OF[i] == "xray")
for name, coll in (("home", HOME), ("clinic", CLIN), ("car", ROAD), ("or", OR)):
    key_vis([o for o in coll.all_objects], lambda i, name=name: SET_OF[i] != "xray")
if doc:
    key_vis([o for o in doc.objs] + [steth], lambda i: SET_OF[i] in ("clinic", "or"))
    key_vis([cap, mask], lambda i: SET_OF[i] == "or")
    key_vis([vial, *vparts], lambda i: SET_OF[i] == "clinic" and T[i] >= B[3])
    key_vis([strip, *strip.children], lambda i: SET_OF[i] == "clinic" and T[i] >= B[3])

# ---------------------------------------------------------------- lights + world per set
world = bpy.data.worlds.new("ShortWorld")
scene.world = world
world.use_nodes = True
wnt = world.node_tree
wnt.nodes.clear()
wbg = wnt.nodes.new("ShaderNodeBackground")
wbg.name = "Background"
wout = wnt.nodes.new("ShaderNodeOutputWorld")
wnt.links.new(wbg.outputs[0], wout.inputs[0])
WCOL = {"home": ((0.55, 0.5, 0.45), 0.35), "clinic": ((0.7, 0.78, 0.82), 0.3), "car": ((0.02, 0.035, 0.08), 1.0),
        "carint": ((0.02, 0.035, 0.08), 1.0), "or": ((0.6, 0.72, 0.72), 0.25), "xray": ((0.003, 0.01, 0.026), 1.0)}
cols = [WCOL[s] for s in SET_OF]
bake_vec(wnt, 'nodes["Background"].inputs[0].default_value', [(*c_, 1) for c_, _ in cols], n=4, interp="CONSTANT")
bake(wnt, 'nodes["Background"].inputs[1].default_value', [s_ for _, s_ in cols], interp="CONSTANT")


def _area(name, coll, loc, target, energy, size, color):
    d = bpy.data.lights.new(name, "AREA")
    d.energy, d.size, d.color = energy, size, color
    o = bpy.data.objects.new(name, d)
    coll.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


HEAD_HOME = SEAT_HOME + Vector((0, -0.05, 0.62))
LIGHTS = {
    "home": [_area("HomeKey", HOME, HEAD_HOME + Vector((1.3, -1.6, 1.0)), HEAD_HOME, 320, 1.4, (1.0, 0.92, 0.82)),
             _area("HomeFill", HOME, HEAD_HOME + Vector((-1.6, -1.2, 0.2)), HEAD_HOME, 80, 2.0, (0.8, 0.88, 1.0)),
             _area("HomeRim", HOME, HEAD_HOME + Vector((-0.7, 1.3, 0.9)), HEAD_HOME, 220, 0.8, (0.95, 0.97, 1.0)),
             _area("WindowSpill", HOME, Vector((-1.5, 3.1, 1.6)), HEAD_HOME, 260, 1.3, (0.85, 0.92, 1.0))],
    "clinic": [_area("ClinKey", CLIN, CLINP + Vector((1.5, -1.0, 2.4)), SEAT_CLIN + Vector((0, 0, 0.6)), 380, 1.5, (1.0, 0.97, 0.94)),
               _area("ClinFill", CLIN, CLINP + Vector((-1.8, -1.5, 1.6)), SEAT_CLIN + Vector((0, 0, 0.6)), 120, 2.0, (0.85, 0.92, 1.0))],
    "car": [_area("MoonFill", ROAD, CARP + Vector((-6, -6, 8)), CARP + Vector((1.75, 0, 0.8)), 2500, 8, (0.45, 0.55, 0.9)),
            _area("CarSpill", ROAD, CARP + Vector((-1.5, 4.0, 3.0)), CARP + Vector((1.75, 1.5, 0.6)), 900, 2, (1.0, 0.8, 0.55))],
    "carint": [_area("DashGlowL", ROAD, SEAT_CAR + Vector((0, -0.6, 0.25)), SEAT_CAR + Vector((0, 0, 0.6)), 14, 0.5, (1.0, 0.55, 0.25)),
               _area("CarRim", ROAD, SEAT_CAR + Vector((-1.0, 0.6, 0.9)), SEAT_CAR + Vector((0, 0, 0.6)), 30, 0.6, (0.6, 0.7, 1.0)),
               _area("StreetSpill", ROAD, SEAT_CAR + Vector((1.4, -0.5, 1.2)), SEAT_CAR + Vector((0, 0, 0.6)), 40, 0.8, (1.0, 0.8, 0.55))],
    "or": [_area("ORFill", OR, TABLE + Vector((-1.8, -1.5, 2.2)), TABLE + Vector((0, 0, 1.0)), 200, 2.5, (0.85, 0.95, 1.0))],
    "xray": [_area("XKey", ANAT, her.nose + Vector((0.6, -0.5, 0.5)), her.nose, 12, 0.8, (1.0, 0.92, 0.88)),
             _area("XFill", ANAT, her.nose + Vector((0.5, 0.4, -0.2)), her.nose, 6, 1.0, (0.5, 0.7, 1.0))],
}
for o in LIGHTS["xray"]:
    her.parent_to_bone(o, "Head")
BASE = {l.name: l.data.energy for ls in LIGHTS.values() for l in ls}
for set_name, ls in LIGHTS.items():
    for l in ls:
        vals = []
        for i, t in enumerate(T):
            on = SET_OF[i] == set_name or (set_name == "car" and SET_OF[i] == "carint")
            e = BASE[l.name] * on
            if l.name == "WindowSpill" and B[2] <= t < B[3]:
                e *= 0.1 + 0.9 * cyc[i]
            if l.name == "StreetSpill":
                e *= 1 + 25 * spike(t, IMPACT, 0.01, 0.06)
            vals.append(e)
        bake(l.data, "energy", vals)
bake(scene, '["xray"]', XRAY, interp="CONSTANT")
# exposure accents: impact flash, X-ray entry flash
bake(scene, "view_settings.exposure", [-0.35 + (0.9 if SET_OF[i] in ("car", "carint") else 0.0) + 1.6 * spike(t, IMPACT, 0.01, 0.05) + 1.0 * spike(t, FACE_HIT, 0.01, 0.05)
                                       + 0.8 * sum(spike(t, s[0], 0.005, 0.04) for s in SHOTS if s[2] == "xray") for i, t in enumerate(T)])

# ---------------------------------------------------------------- cameras (smooth bezier moves + subtle handheld)
CAMS = {}


def world_at(obj, t):
    scene.frame_set(F(t))
    return obj.matrix_world.translation.copy()


def cam(name, keys, lens, fstop, aim, focus=None, shake=0.0015):
    """keys: [(t, location)], aim: object to track (or Vector -> static empty)."""
    if isinstance(aim, Vector):
        e = bpy.data.objects.new(name + "Aim", None)
        CAST.objects.link(e)
        e.location = aim
        aim = e
    d = bpy.data.cameras.new(name)
    d.lens, d.sensor_width, d.clip_start = lens, 36, 0.005
    d.dof.use_dof = True
    d.dof.aperture_fstop = fstop
    d.dof.focus_object = focus or aim
    o = bpy.data.objects.new(name, d)
    CAST.objects.link(o)
    tr = o.constraints.new("TRACK_TO")
    tr.target, tr.track_axis, tr.up_axis = aim, "TRACK_NEGATIVE_Z", "UP_Y"
    t0, t1 = keys[0][0], keys[-1][0]
    pts = []
    for t in T:
        k = 0
        while k < len(keys) - 2 and t > keys[k + 1][0]:
            k += 1
        (ta, la), (tb, lb) = keys[k], keys[k + 1]
        u = smooth((t - ta) / max(1e-6, tb - ta))
        p = la.lerp(lb, u)
        p += Vector((wobble(t, 11, 0.6), wobble(t, 12, 0.5), wobble(t, 13, 0.55))) * shake
        pts.append(p)
    bake_vec(o, "location", pts)
    CAMS[name] = o
    return o


def shot_span(name):
    i = next(k for k, s in enumerate(SHOTS) if s[1] == name)
    a = SHOTS[i][0]
    b = SHOTS[i + 1][0] if i + 1 < len(SHOTS) else DUR
    return a, b


def mid(name):
    a, b = shot_span(name)
    return (a + b) / 2


# hook
a, b = shot_span("NoseECU")
N0 = world_at(nostril, mid("NoseECU"))
cam("NoseECU", [(a, N0 + Vector((0.07, -0.2, -0.005))), (b, N0 + Vector((0.05, -0.14, -0.004)))], 70, 2.8, nostril)
a, b = shot_span("XSide")
H0 = world_at(her.anchor("XHead", "Head", BR_C + Vector((0, -0.03, -0.02)), CAST), mid("XSide"))
xhead = bpy.data.objects[f"{her.name}.XHead"]
cam("XSide", [(a, H0 + Vector((0.5, -0.07, 0.02))), (b, H0 + Vector((0.62, -0.08, 0.02)))], 50, 8.0, xhead)
a, b = shot_span("Clinic2Shot")
FC = world_at(face_pt, mid("Clinic2Shot"))
cam("Clinic2Shot", [(a, FC + Vector((-1.05, -1.75, 0.32))), (b, FC + Vector((-0.95, -1.55, 0.28)))], 40, 2.8,
    FC + Vector((-0.12, -0.25, 0.0)), eye_pt)
# crash
a, b = shot_span("RoadWide")
CA = CARP + Vector((1.75, 0, 0.8))
cam("RoadWide", [(a, CA + Vector((-3.2, 9.0, 0.6))), (b, CA + Vector((-2.8, 6.5, 0.5)))], 24, 5.6, CA + Vector((0.0, 3.0, 0.0)), shake=0.004)
a, b = shot_span("RoadImpact")
cam("RoadImpact", [(a, CA + Vector((-3.0, 1.8, 0.0))), (b, CA + Vector((-2.8, 1.6, 0.05)))], 28, 4.0, CA + Vector((0.0, 2.6, -0.1)), shake=0.03)
a, b = shot_span("CarInt")
FI = world_at(face_pt, a + 0.05)
cam("CarInt", [(a, FI + Vector((0.95, -0.38, 0.02))), (b, FI + Vector((0.85, -0.42, 0.0)))], 32, 2.8, FI + Vector((0.0, -0.2, -0.06)),
    eye_pt, shake=0.002)
a, b = shot_span("XCrash")
HC = world_at(xhead, a)
cam("XCrash", [(a, HC + Vector((0.55, -0.05, 0.02))), (b, HC + Vector((0.5, -0.05, 0.02)))], 50, 8.0, xhead)
# years
a, b = shot_span("HomeWide")
cam("HomeWide", [(a, Vector((1.6, -3.0, 1.35))), (b, Vector((1.35, -2.7, 1.3)))], 24, 5.6, Vector((0.1, 0.3, 0.75)), face_pt)
# specialist
a, b = shot_span("VialCU")
if doc:
    VW = world_at(vial, mid("VialCU"))          # camera on her side of the vial, the doctor's face behind it
    cam("VialCU", [(a, VW + Vector((0.12, 0.34, 0.03))), (b, VW + Vector((0.09, 0.26, 0.02)))], 60, 2.2, VW + Vector((0, 0, 0.035)))
    a, b = shot_span("StripMacro")
    SW = world_at(strip, mid("StripMacro"))
    cam("StripMacro", [(a, SW + Vector((0.05, 0.16, 0.02))), (b, SW + Vector((0.04, 0.12, 0.015)))], 85, 4.0, SW + Vector((0, 0, 0.01)))
# X-ray beats
a, b = shot_span("XOrbit")
HO = world_at(xhead, mid("XOrbit"))
cam("XOrbit", [(a + (b - a) * k / 4, HO + Vector((0.62 * math.sin(math.radians(30 + 15 * k)), -0.62 * math.cos(math.radians(30 + 15 * k)),
                                                       0.06 - 0.015 * k))) for k in range(5)], 50, 8.0, xhead)
hole_a = her.anchor("HoleAim", "Head", HOLE.copy(), CAST)
a, b = shot_span("XHole")
HH = world_at(hole_a, mid("XHole"))
cam("XHole", [(a, HH + Vector((0.3, -0.03, 0.03))), (CRACK, HH + Vector((0.16, -0.02, 0.015))), (b, HH + Vector((0.11, -0.02, 0.01)))],
    50, 5.6, hole_a)
a, b = shot_span("JugShot")
JW = Vector((-0.05, -0.85, 0.42))
cam("JugShot", [(a, JW + Vector((0.3, -0.62, 0.2))), (b, JW + Vector((0.25, -0.52, 0.18)))], 28, 5.6, JW.lerp(world_at(face_pt, a), 0.45), eye_pt)
pm_a = her.anchor("PathMid", "Head", path_point(0.5), CAST)
a, b = shot_span("XBact")
PM = world_at(pm_a, mid("XBact"))
cam("XBact", [(a, PM + Vector((0.22, -0.06, -0.03))), (b, PM + Vector((0.15, -0.04, 0.0)))], 50, 5.6, pm_a)
# surgery
a, b = shot_span("ORWide")
NW = world_at(nostril, mid("ORWide"))
cam("ORWide", [(a, NW + Vector((1.4, -1.2, 0.9))), (b, NW + Vector((1.15, -0.95, 0.7)))], 30, 4.0, NW + Vector((0, 0.15, 0.1)), face_pt)
a, b = shot_span("XSurg")
PS = world_at(pm_a, mid("XSurg"))
cam("XSurg", [(a, PS + Vector((0.28, -0.05, -0.02))), (SEAL - 0.1, PS + Vector((0.22, -0.04, -0.01))), (b, PS + Vector((0.15, -0.03, 0.0)))],
    50, 5.6, pm_a)
# closer
a, b = shot_span("HomeFront")
FH = world_at(face_pt, mid("HomeFront"))
cam("HomeFront", [(a, FH + Vector((0.05, -0.55, -0.03))), (b, FH + Vector((0.08, -1.05, -0.12)))], 40, 2.8, FH + Vector((0, 0, -0.06)), eye_pt)

for t0, name, _, _ in SHOTS:
    if name in CAMS:
        scene.timeline_markers.new(name, frame=F(t0)).camera = CAMS[name]
scene.camera = CAMS[SHOTS[0][1]]
scene.frame_set(1)

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
