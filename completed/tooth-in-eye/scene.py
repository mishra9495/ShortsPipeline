"""tooth-in-eye v2: "Doctors put this man's tooth inside his eye, to cure his blindness."

Run (daily_render.ps1): blender -b --python scene.py -- <ROOT>/blend/<slug>.blend vo=<wav> beats=<json> fps=30
Optional: stills=1,200 pct=100 samples=64 device=gpu|cpu root=<ROOT>

v3 toolkit: every model is built in Blender from code (scripts/kit.py), characters act procedurally on the
mixamorig bones (scripts/actor.py) and every camera is a moving spline that is already in motion on the cut
(scripts/shot.py). No captions and no on-screen text (owner's rule). Timing comes only from the beats JSON.

Cast:  him = blend/char_hero.blend   (Brent Chapman, the patient; opened as the main file)
       doc = blend/char_heroine.blend (the surgeon; white coat, cap + mask in the OR)
Sets, far apart so they never see each other: HOME, CLINIC, OR, LAB bench, plus X-ray anatomy riding on his head.
SYNC constants match mix.py.
"""
import json
import math
import os
import random
import sys
import warnings

import bpy
from mathutils import Vector

# Material.use_nodes / World.use_nodes still work in Blender 5.x (removal is 6.0); without this the nightly log's
# WARN filter fills with DeprecationWarnings and the cloud agent is told to chase them.
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
SAMPLES = int(opts.get("samples", 64))
DEVICE = opts.get("device", "gpu").lower()
STILLS = [int(f) for f in opts["stills"].split(",")] if opts.get("stills") else []
BEATS_JSON = opts.get("beats") or os.path.join(AUDIO, f"{SLUG}_vo.json")
VO_WAV = opts.get("vo") or os.path.join(AUDIO, f"{SLUG}_vo.wav")
if not os.path.exists(BEATS_JSON):
    raise SystemExit(f"Error: narration timing {BEATS_JSON} missing")
print(f"ARGS out={OUT} fps={FPS} pct={PCT} samples={SAMPLES} device={DEVICE} beats={BEATS_JSON}")
sys.path.insert(0, SCRIPTS)

# ---------------------------------------------------------------- characters
HERO = os.path.join(ROOT, "blend", "char_hero.blend")
HEROINE = os.path.join(ROOT, "blend", "char_heroine.blend")
if not os.path.exists(HERO):
    raise SystemExit(f"Error: {HERO} missing")
print("CHAR", HERO)
bpy.ops.wm.open_mainfile(filepath=HERO)

import actor as A  # noqa: E402
import kit as K  # noqa: E402
import shot as S  # noqa: E402

scene = bpy.context.scene
K.init(scene, seed=23)
random.seed(23)
CAST = K.coll("Cast")
him = A.Actor.from_scene("Him")
doc = A.Actor.append(HEROINE, "Doc", CAST) if os.path.exists(HEROINE) else None
for a in (him, doc):
    if a:
        a.measure()
        a.setup_ik(CAST)
print("CAST", him.rig.name, doc.rig.name if doc else None, "his height", round(him.top, 3))

# ---------------------------------------------------------------- timeline (seconds)
META = json.load(open(BEATS_JSON, encoding="utf-8"))
B = [float(b["start"]) for b in META["beats"]]
assert len(B) == 10, f"expected 10 beats, got {len(B)}"
NARR = float(META["duration"])
DUR = NARR + 36.0 / FPS                      # the template's +36 frame tail (mix.py: TAIL)
BE = B[1:] + [NARR]                          # beat ends; at(9, f) matches mix.py at_beat(9, f)


def at(i, frac):
    return B[i] + frac * (BE[i] - B[i])


def F(t):
    return int(round(t * FPS)) + 1


END = F(DUR)
FRAMES = range(1, END + 1)
T = [(f - 1) / FPS for f in FRAMES]
# SYNC with mix.py
PILL = at(1, 0.18)        # the pill goes in
CLOUD = at(1, 0.60)       # both corneas cloud over
EXTRACT = at(3, 0.55)     # the canine lifts out of the jaw
SHAVE = at(4, 0.15)       # tooth -> block
DRILL = at(4, 0.40)       # drill bores the block
LENS = at(4, 0.70)        # the acrylic lens slides in
SEAT = at(6, 0.70)        # the block seats into the eye
FOCUS = at(8, 0.35)       # POV: the surgeon's face snaps into focus
GLINT = at(9, 0.60)       # his canine glints in the closing smile
print("TIMELINE", [round(b, 2) for b in B], "END", END, "EXTRACT", round(EXTRACT, 2), "SEAT", round(SEAT, 2))

S.setup_render(scene, fps=FPS, end=END, pct=PCT, samples=SAMPLES, device=DEVICE)


def bake(idb, path, values, index=None, interp="LINEAR"):
    return A.bake(idb, path, values, FRAMES, index=index, interp=interp)


def bake_vec(idb, path, vecs, n=3, interp="LINEAR"):
    A.bake_vec(idb, path, vecs, FRAMES, n=n, interp=interp)


ramp, env, spike, smooth, wobble = A.ramp, A.env, A.spike, A.smooth, A.wobble


def first(x):
    return x[0] if isinstance(x, (tuple, list)) else x


# ---------------------------------------------------------------- sets (modelled here, far apart)
HOMEP, CLINP, ORP, LABP = Vector((0, 0, 0)), Vector((40, 0, 0)), Vector((80, 0, 0)), Vector((120, 0, 0))
FAR = Vector((0, 0, -200))
HOME, CLIN, OR, LAB = K.coll("SetHome"), K.coll("SetClinic"), K.coll("SetOR"), K.coll("SetLab")

# HOME: a dressed living-room corner. He sits in the middle of the sofa facing -Y (the open, camera side).
K.room(HOME, origin=(0, 0.7, 0), size=(6.0, 5.4, 2.7), openings=[(-1.5, 1.45, 1.44, 1.54)])
K.window(HOME, (-1.5, 3.33, 1.45), size=(1.3, 1.4), sky=(0.78, 0.86, 1.0), sky_strength=3.0)
K.sofa(HOME, (0, 0.0, 0), width=2.1, seat_h=0.44, color=(0.16, 0.14, 0.12))
K.rug(HOME, (0, -0.55, 0), (2.8, 2.0), main=(0.22, 0.24, 0.30), border=(0.10, 0.10, 0.12), field=(0.72, 0.70, 0.64))
K.coffee_table(HOME, (0.1, -0.95, 0))
K.floor_lamp(HOME, (1.45, 0.45, 0))
K.potted_plant(HOME, (-1.55, 0.55, 0), h=1.25)
K.bookshelf(HOME, (2.35, 2.9, 0))
K.picture_frame(HOME, (0.0, 3.32, 1.62), (0.95, 0.62), seed=2)
K.mug(HOME, (-0.25, -1.0, 0.42), color=(0.2, 0.25, 0.3))
# a pill bottle on the table (beat 1), a few loose pills beside it
amber = K.plastic("PillAmber", (0.75, 0.42, 0.08), 0.15)
amber.node_tree.nodes["Principled BSDF"].inputs["Transmission Weight"].default_value = 0.65
BOTTLE = Vector((-0.42, 0.22, 0.455))          # on the sofa cushion by his right hand (the coffee table is out of reach seated)
bottle = K.cyl("PillBottle", HOME, 0.016, 0.055, BOTTLE + Vector((0, 0, 0.0275)), amber, verts=32, bevel=0.002)
K.cyl("PillCap", HOME, 0.017, 0.012, BOTTLE + Vector((0, 0, 0.061)), K.plastic("PillCapWhite", (0.95, 0.95, 0.93), 0.4), verts=32, bevel=0.002)
pill_m = K.plastic("PillWhite", (0.96, 0.95, 0.90), 0.35, coat=0.3)
for k, (dx, dy) in enumerate(((0.045, 0.02), (0.06, -0.01), (0.05, 0.045))):
    K.sphere(f"LoosePill{k}", HOME, 0.0045, BOTTLE + Vector((dx, dy, 0.0035)), pill_m, scale=(1.0, 1.0, 0.65), subdiv=3)

# CLINIC: an eye clinic consulting room; the examination light is the hero prop
K.room(CLIN, origin=CLINP + Vector((0, 0.6, 0)), size=(5.5, 5.0, 2.8), floor_mat=K.paint("ClinicFloor", (0.60, 0.64, 0.66), 0.35),
       wall_color=(0.80, 0.86, 0.88), name="Clinic", openings=[(1.6, 1.5, 1.34, 1.34)])
K.window(CLIN, CLINP + Vector((1.6, 3.07, 1.5)), size=(1.2, 1.2), curtains=False, sky_strength=2.2)
K.desk(CLIN, CLINP + Vector((1.5, 1.6, 0)), rot=math.radians(-20))
K.lab_bench(CLIN, CLINP + Vector((-1.2, 2.7, 0)))
chair_m = K.fabric("ClinicChair", (0.14, 0.22, 0.30))
for nm, size, loc in (("ChairSeat", (0.55, 0.52, 0.1), (0, 0.05, 0.42)), ("ChairBack", (0.55, 0.1, 0.55), (0, 0.32, 0.75))):
    K.cushion(nm, CLIN, size, CLINP + Vector(loc), chair_m, puff=0.3)
steel = K.metal("ChairSteel", (0.75, 0.75, 0.78), 0.3)
for sx in (-1, 1):
    for sy in (-0.18, 0.28):
        K.cyl("ChairLeg", CLIN, 0.015, 0.37, CLINP + Vector((sx * 0.24, sy, 0.185)), steel, verts=12)
K.potted_plant(CLIN, CLINP + Vector((-2.2, 1.0, 0)), h=1.3, seed=8)
K.picture_frame(CLIN, CLINP + Vector((-0.4, 3.07, 1.6)), (0.7, 0.5), seed=5)
# penlight the surgeon shines into his eye (parented to her hand below)
pen = K.empty("Penlight", CLIN, (0, 0, 0))
pen_parts = [K.cyl("PenBody", CLIN, 0.006, 0.13, (0, 0, 0.065), K.metal("PenSteel", (0.82, 0.82, 0.85), 0.2), verts=24),
             K.cyl("PenTip", CLIN, 0.0045, 0.006, (0, 0, 0.133), K.emissive("PenLED", (1.0, 1.0, 0.95), 40.0), verts=24)]
K.parent(pen_parts, pen)
pen_lamp = bpy.data.lights.new("PenSpot", "SPOT")
pen_lamp.energy, pen_lamp.spot_size, pen_lamp.spot_blend, pen_lamp.color = 6.0, math.radians(28), 0.6, (1.0, 1.0, 0.96)
pen_spot = bpy.data.objects.new("PenSpot", pen_lamp)
CLIN.objects.link(pen_spot)
pen_spot.parent = pen
pen_spot.location = (0, 0, 0.136)
pen_spot.rotation_euler = (math.pi, 0, 0)        # a spot shines along local -Z; the pen body points +Z, so flip it

# OR: table, lamp, monitor, tray, IV pole. He lies on the table, head toward +Y where the surgeon stands.
K.room(OR, origin=ORP + Vector((0, 0.8, 0)), size=(6.0, 6.0, 3.0), floor_mat=K.paint("ORFloor", (0.52, 0.66, 0.64), 0.3),
       wall_color=(0.64, 0.78, 0.76), name="ORRoom")
TABLE = ORP + Vector((0, 0.9, 0))
K.or_table(OR, TABLE)
K.surgical_lamp(OR, ORP + Vector((0.1, 1.5, 2.35)))
K.vital_monitor(OR, ORP + Vector((1.1, 2.4, 1.45)), rot=math.radians(-30))
K.instrument_tray(OR, ORP + Vector((-0.9, 1.8, 0.0)))
K.iv_pole(OR, ORP + Vector((1.0, 0.4, 0.0)))
drape = K.cushion("Drape", OR, (0.7, 1.3, 0.12), ORP + Vector((0, 0.45, 1.02)), K.fabric("Drape", (0.12, 0.40, 0.45), weave=300), puff=0.4)
forceps = first(K.forceps(OR, (0, 0, 0), open_deg=10.0))

# LAB: a bench corner with a steel tray; the tooth is the hero and the macro lens makes it big
K.room(LAB, origin=LABP + Vector((0, 0.6, 0)), size=(5.0, 4.5, 2.8), floor_mat=K.paint("LabFloor", (0.40, 0.42, 0.45), 0.3),
       wall_color=(0.55, 0.58, 0.62), name="Lab")
K.lab_bench(LAB, LABP + Vector((0, 0.9, 0)))
# kit.lab_bench's BenchTop is an rbox at local z 0.92, 0.04 thick, 0.75 deep -> top surface z 0.94, front edge y 0.525.
# The tray must sit ON that surface and inside that footprint; at z 0.92 it is buried in the bench and the macro
# cameras see only epoxy.
BENCH_TOP = 0.94
TRAY = LABP + Vector((0, 0.70, BENCH_TOP + 0.006))
tray_m = K.metal("LabTrayDark", (0.35, 0.35, 0.38), 0.6, brushed=False)   # own name: kit caches materials by name and the OR tray already made "TraySteel"
K.rbox("LabTray", LAB, (0.30, 0.22, 0.012), TRAY, tray_m, bevel=0.004)
K.rbox("LabTrayLip", LAB, (0.30, 0.012, 0.03), TRAY + Vector((0, 0.104, 0.015)), tray_m, bevel=0.003)
K.rbox("LabTrayLip2", LAB, (0.012, 0.22, 0.03), TRAY + Vector((-0.144, 0, 0.015)), tray_m, bevel=0.003)
K.rbox("Gauze", LAB, (0.09, 0.07, 0.006), TRAY + Vector((0.09, -0.05, 0.009)), K.fabric("Gauze", (0.95, 0.95, 0.93), weave=900, bump=0.5))
K.cyl("SalineCup", LAB, 0.022, 0.03, TRAY + Vector((-0.09, 0.05, 0.021)), K.glass("CupGlass"), verts=32)
TOOTH_SPOT = TRAY + Vector((0, 0, 0.0065))
enamel = K.ceramic("CanineEnamel", (0.93, 0.91, 0.84), 0.22)
root_m = K.plastic("Dentine", (0.74, 0.58, 0.40), 0.5)                # no SSS: at the default radius a 10 mm block goes translucent and vanishes
# the whole canine: crown (enamel) + long root (dentine), lying on its side
tooth_lab = K.empty("LabTooth", LAB, TOOTH_SPOT)
K.parent([K.lathe("LabCrown", LAB, [(0.0, 0.0), (0.0042, 0.0), (0.0048, 0.004), (0.0035, 0.009), (0.0, 0.011)], (0, 0, 0), enamel, steps=24),
          K.lathe("LabRoot", LAB, [(0.0, 0.0), (0.0040, 0.0), (0.0026, -0.010), (0.0012, -0.017), (0.0, -0.018)], (0, 0, 0), root_m, steps=24)],
         tooth_lab)
tooth_lab.rotation_euler = (0, math.radians(90), 0)
# The block lies FLAT on the tray (10 x 10 mm face up, 4.5 mm thick: 3.5 mm dentine + a 1 mm jawbone lamina). The real
# OOKP lamina is ~4 mm and the optical cylinder passes through that thickness, so the bore runs through the THIN axis.
# Flat puts the bore, the descending drill and the dropped-in lens on ONE vertical axis; standing the slab on edge
# asks a 3.8 mm bore to cross a 3.5 mm thickness and leaves the drill perpendicular to the hole it is making.
block_lab = K.empty("LabBlock", LAB, TOOTH_SPOT)
blk_dentine = K.rbox("BlockDentine", LAB, (0.010, 0.010, 0.0035), (0, 0, 0.00175), root_m, bevel=0.0006, segments=2)
blk_bone = K.rbox("BlockBone", LAB, (0.010, 0.010, 0.0010), (0, 0, 0.0040), K.bone_mat("JawSliver"), bevel=0.0004, segments=2)
blk_parts = [blk_dentine, blk_bone]
K.parent(blk_parts, block_lab)
# a real bored hole: one cylinder boolean-subtracted from both layers, parked below the tray until the bit arrives
hole_cut = K.cyl("BlockHoleCut", LAB, 0.0019, 0.016, (0, 0, -0.03), None, rot=(0, 0, 0), verts=24)
hole_cut.parent = block_lab
K._cut(blk_dentine, hole_cut)
K._cut(blk_bone, hole_cut)
# a clear acrylic plastic, not kit.glass: at macro under a dim lab world a glass cylinder refracts the dark
# surroundings and renders as a black plug. Transmission + coat keeps it readable and catches the key light.
lens_m = K.plastic("AcrylicLens", (0.95, 0.97, 1.0), 0.05, coat=0.6)
lens_m.node_tree.nodes["Principled BSDF"].inputs["Transmission Weight"].default_value = 0.85
lens_m.node_tree.nodes["Principled BSDF"].inputs["IOR"].default_value = 1.49
lens_lab = K.cyl("LabLens", LAB, 0.0018, 0.0062, (0, 0, 0.0022), lens_m, rot=(0, 0, 0), verts=32)
lens_lab.parent = block_lab
# a slim dental handpiece parked out of frame, so its body never hides the block from the macro camera
drill = K.empty("Drill", LAB, TOOTH_SPOT + Vector((0, 0, 0.11)))
K.parent([K.cyl("DrillBit", LAB, 0.0018, 0.024, (0, 0, -0.012), K.metal("DrillSteel", (0.55, 0.56, 0.6), 0.35), verts=12),
          K.cyl("DrillChuck", LAB, 0.005, 0.016, (0, 0, 0.008), K.metal("DrillChuckM", (0.3, 0.3, 0.32), 0.3), verts=24, bevel=0.001),
          K.cyl("DrillBody", LAB, 0.0075, 0.07, (0, 0, 0.051), K.plastic("DrillBody", (0.08, 0.10, 0.14), 0.35), verts=32, bevel=0.002)], drill)
shav_m = K.plastic("ToothDust", (0.80, 0.70, 0.52), 0.6)
# dust swept to one side: shards scattered on the block's own 10 mm footprint simply hide it at macro scale
shavings = K.shards(LAB, 14, shav_m, TOOTH_SPOT + Vector((0.038, 0.006, 0.0)), size=(0.0006, 0.0022), seed=4, name="Shaving", spread=0.016)
shavings = list(shavings) if isinstance(shavings, (list, tuple)) else [shavings]
glint = K.sphere("LensGlint", LAB, 0.0015, TOOTH_SPOT + Vector((0.003, -0.003, 0.009)), K.emissive("GlintWhite", (1, 1, 1), 15.0), subdiv=2)

# ---------------------------------------------------------------- shots
# (start seconds, camera name, set, his pose)    set: home/clinic/or/lab/xray   pose: sit/lie
SHOTS = [
    (0.0, "EyeECU", "home", "sit"), (at(0, 0.48), "FacePull", "home", "sit"),
    (B[1], "PillCU", "home", "sit"), (at(1, 0.46), "CloudEyes", "home", "sit"),
    (B[2], "ClinicOrbit", "clinic", "sit"), (at(2, 0.5), "GraftECU", "clinic", "sit"),
    (B[3], "ORWide", "or", "lie"), (at(3, 0.32), "XJaw", "xray", "lie"),
    (B[4], "TrayMacro", "lab", "lie"), (at(4, 0.55), "LensMacro", "lab", "lie"),
    (B[5], "CheekX", "xray", "sit"), (at(5, 0.55), "VesselMacro", "xray", "sit"),
    (B[6], "EyeSeat", "xray", "lie"),
    (B[7], "Immune", "xray", "sit"),
    (B[8], "POVFocus", "clinic", "sit"), (at(8, 0.55), "TwoShot", "clinic", "sit"),
    (B[9], "Closer", "home", "sit"),
]


def shot_at(t):
    return max((s for s in SHOTS if s[0] <= t + 1e-6), key=lambda s: s[0])


SH = [shot_at(t) for t in T]
SET_OF = [s[2] for s in SH]
XRAY = [1.0 if s == "xray" else 0.0 for s in SET_OF]

legs_sit = him.seated_legs()
SEAT_HOME = HOMEP + Vector((0, 0.32, 0.53))
SEAT_CLIN = CLINP + Vector((0, 0.1, 0.55))


def him_root(t, s):
    """(location, euler) of his rig object. X-ray shots keep him where the story has him."""
    name, pose = s[2], s[3]
    if pose == "lie":                      # on his back, head toward +Y (the surgeon's end), face up
        return Vector((TABLE.x - him.x0, TABLE.y - 0.92, 0.945 + 0.12)), (math.radians(-90), 0, 0)
    if name == "clinic" or (name == "xray" and B[7] <= t < B[8]):
        return SEAT_CLIN - him.hips0, (0, 0, 0)
    return SEAT_HOME - him.hips0, (0, 0, 0)


DOC_CLIN = CLINP + Vector((-0.30, -0.82, 0)), (0, 0, math.pi)            # facing him (+Y), close enough to lean in
DOC_OR = Vector((TABLE.x - (doc.x0 if doc else 0), TABLE.y + 1.32, 0)), (0, 0, 0)   # at his head end, facing -Y


def doc_root(t, s):
    if s[2] == "clinic":
        return DOC_CLIN
    if s[2] == "or" or (s[2] == "xray" and s[3] == "lie"):
        return DOC_OR
    return FAR, (0, 0, 0)


# ---------------------------------------------------------------- anchors on the characters (rig-local rest space)
EYE_R = him.eye_r.copy()                                   # his right eye (the operated one), -X side
EYE_L = him.eye_l.copy()
CHEEK = Vector((him.x0 - 0.052, him.nose.y + 0.004, him.nose.z - 0.034))
MOUTH = him.mouth.copy()
eye_pt = him.anchor("EyeR", "Head", EYE_R, CAST)
eyes_mid = him.anchor("Eyes", "Head", (EYE_L + EYE_R) / 2, CAST)
face_pt = him.anchor("Face", "Head", Vector((him.x0, him.nose.y + 0.06, him.nose.z - 0.02)), CAST)
mouth_pt = him.anchor("Mouth", "Head", MOUTH + Vector((0, -0.02, 0)), CAST)
cheek_pt = him.anchor("Cheek", "Head", CHEEK, CAST)
canine_pt = him.anchor("CanineLive", "Head", Vector((him.x0 - 0.016, him.nose.y - 0.004, him.nose.z - 0.052)), CAST)
hand_r = him.rig.data.bones[A.MX + "RightHand"]
pill_hand = K.sphere("HandPill", CAST, 0.0045, hand_r.tail_local + Vector((0, -0.015, -0.01)), pill_m, scale=(1.0, 1.0, 0.65), subdiv=3)
him.parent_to_bone(pill_hand, "RightHand")
him.hand_follow("Right", mouth_pt, "ToMouth")
bottle_pick = K.empty("BottlePick", HOME, BOTTLE + Vector((0, 0, 0.12)))
him.hand_follow("Right", bottle_pick, "ToBottle")
if doc:
    for key in ("suit", "shirt", "dress", "top", "jacket", "coat", "blouse", "sweater"):
        doc.tint_material(key, (0.93, 0.94, 0.96), 0.9)                   # white coat
    doc_face = doc.anchor("Face", "Head", Vector((doc.x0, doc.nose.y + 0.06, doc.nose.z - 0.02)), CAST)
    doc_eyes = doc.anchor("Eyes", "Head", (doc.eye_l + doc.eye_r) / 2, CAST)
    cap = K.sphere("SurgCap", CAST, 1.0, Vector((doc.x0, (doc.nose.y + doc.back_y) / 2 + 0.01, doc.top - 0.06)),
                   K.fabric("ScrubBlue", (0.12, 0.35, 0.5), weave=500), scale=(0.1, 0.12, 0.085))
    mask = K.cushion("SurgMask", CAST, (0.15, 0.03, 0.09), Vector((doc.x0, doc.nose.y + 0.012, doc.nose.z - 0.035)),
                     K.fabric("MaskBlue", (0.35, 0.6, 0.75), weave=600), puff=0.8)
    for o in (cap, mask):
        doc.parent_to_bone(o, "Head")
    hand_dr = doc.rig.data.bones[A.MX + "RightHand"]
    pen.location = hand_dr.tail_local + Vector((0, -0.02, -0.01))
    pen.rotation_euler = (math.radians(-90), 0, 0)
    doc.parent_to_bone(pen, "RightHand")
    forceps.location = hand_dr.tail_local + Vector((0, -0.03, -0.01))
    forceps.rotation_euler = (math.radians(-90), 0, 0)
    doc.parent_to_bone(forceps, "RightHand")
    mouth_grip = K.empty("MouthGrip", CAST, (0, 0, 0))
    doc.hand_follow("Right", mouth_grip, "ToMouth")
    eye_grip = K.empty("EyeGrip", CAST, (0, 0, 0))
    doc.hand_follow("Right", eye_grip, "ToEye")

# ---------------------------------------------------------------- X-ray anatomy (rig-local rest space of his head)
ANAT = K.coll("Anatomy")
head_len = him.back_y - him.nose.y
SK_W, SK_D, SK_H = 0.148, head_len * 1.06, 0.166
SK_C = Vector((him.x0, him.nose.y + head_len * 0.50, him.top - 0.012 - SK_H / 2))
skull_root, skull_parts = K.skull(ANAT, SK_C, size=(SK_W, SK_D, SK_H), name="Skull")
upper = sorted([p for p in skull_parts if p.name.startswith("SkullToothUp")], key=lambda o: o.location.x)
canine = upper[4] if len(upper) >= 5 else upper[0]          # his right canine (-X side, 5th from the end)
canine_home = canine.location.copy()
sliver = K.rbox("JawSliverX", ANAT, (0.009, 0.004, 0.003), canine_home + Vector((0, 0.001, 0.0065)), K.bone_mat("JawSliver"), bevel=0.0004, segments=2)
sliver.parent = skull_root
canine_hi = K.emissive("CanineHi", (1.0, 0.85, 0.25), 0.0)
canine_ring = K.lathe("CanineRing", ANAT, [(0.0052, -0.0008), (0.0064, 0.0), (0.0052, 0.0008)], canine_home + Vector((0, 0, 0.004)), canine_hi, steps=28)
canine_ring.parent = skull_root


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


# the implant (ivory block + clear optical cylinder) rides on his head: at the eye in the hook and after SEAT,
# under the cheek during beat 5, moving cheek -> eye during beat 6
implant = K.empty("Implant", ANAT, EYE_R + Vector((0, -0.006, 0)))
imp_block_m = K.bone_mat("ImplantDentine")
# In a real OOKP the tooth block is buried under a pink buccal-mucosa graft: live shots show only that graft and the
# clear optical cylinder poking out of it. The ivory block itself is an X-ray-only sight.
imp_block = K.rbox("ImpBlock", ANAT, (0.0095, 0.0032, 0.0095), (0, 0, 0), imp_block_m, bevel=0.0005, segments=2)
imp_lens = K.cyl("ImpLens", ANAT, 0.0017, 0.0095, (0, -0.0015, 0), lens_m, rot=(math.radians(90), 0, 0), verts=32)
# an ellipse that fits inside the lid gap (about 19 x 10 mm), thin and sunk into the globe, wet and dark like real mucosa
imp_mucosa = K.sphere("ImpMucosa", ANAT, 1.0, (0, 0.0015, 0.0015), K.plastic("Mucosa", (0.62, 0.22, 0.24), 0.25, coat=0.3, sss=0.5),
                      scale=(0.0095, 0.0022, 0.0052), subdiv=4)
imp_parts = [imp_block, imp_lens]
K.parent([imp_block, imp_lens, imp_mucosa], implant)
imp_glow = K.sphere("ImpGlow", ANAT, 1.0, (0, 0, 0), xglow("ImplantGlow", (1.0, 0.72, 0.35), 3.0, blend=0.3, core=0.05, value="Pulse"),
                    scale=(0.0075, 0.004, 0.0075), subdiv=3)
imp_glow.parent = implant
# cornea caps on both eyes: clear glass <-> milky cloud (mix factor "Cloud" is baked)
cornea_m = bpy.data.materials.new("Cornea")
cornea_m.use_nodes = True
N, L = cornea_m.node_tree.nodes, cornea_m.node_tree.links
N.clear()
c_out = N.new("ShaderNodeOutputMaterial")
c_glass = N.new("ShaderNodeBsdfGlass")
c_glass.inputs["Roughness"].default_value = 0.04
c_glass.inputs["IOR"].default_value = 1.38
c_milk = N.new("ShaderNodeBsdfPrincipled")
c_milk.inputs["Base Color"].default_value = (0.88, 0.89, 0.86, 1)
c_milk.inputs["Roughness"].default_value = 0.45
c_milk.inputs["Subsurface Weight"].default_value = 0.45
c_milk.inputs["Subsurface Radius"].default_value = (0.4, 0.4, 0.4)
c_milk.inputs["Subsurface Scale"].default_value = 0.004
c_milk.inputs["Transmission Weight"].default_value = 0.28   # iris ghosts through even at full cloud opacity
c_val = N.new("ShaderNodeValue")
c_val.name = "Cloud"
c_val.outputs[0].default_value = 0.0
c_mix = N.new("ShaderNodeMixShader")
L.new(c_val.outputs[0], c_mix.inputs[0])
L.new(c_glass.outputs[0], c_mix.inputs[1])
L.new(c_milk.outputs[0], c_mix.inputs[2])
L.new(c_mix.outputs[0], c_out.inputs["Surface"])
CR = (0.0080, 0.0010, 0.0080)          # flat disc: 8 mm visible cornea, 1 mm deep — no dome at 100 mm macro distance
cornea_r = K.sphere("CorneaR", ANAT, 1.0, EYE_R + Vector((0, -0.0010, 0.0048)), cornea_m, scale=CR, subdiv=4)
CR_L = (0.0070, 0.0008, 0.0070)              # the untreated eye stays hazy to the end; keep its film subtle
cornea_l = K.sphere("CorneaL", ANAT, 1.0, EYE_L + Vector((0, -0.0010, 0.0048)), cornea_m, scale=CR_L, subdiv=4)
# offset: eyelash mesh z=1.6706 vs measure() z=1.6658 → add +0.0048 in Z; Y pushed 1 mm forward only
# (was -0.0025, deepened to -0.0048 → reverted; flat disc needs minimal protrusion to stay flush with iris)
rash_m = xglow("Rash", (1.0, 0.18, 0.12), 1.4, blend=0.5, core=0.0, value="Rash")
rash = K.sphere("RashShell", ANAT, 1.0, Vector((him.x0, him.nose.y + head_len * 0.45, him.nose.z + 0.02)), rash_m,
                scale=(0.082, head_len * 0.56, 0.11), subdiv=4)
# blood vessels growing into the block under the cheek (curves with bevel_factor_end 0 -> 1)
vessel_m = K.emissive("VesselRed", (1.0, 0.12, 0.08), 6.0)
vessels = []
for k in range(7):
    a = math.radians(k * 360 / 7 + 12)
    rr = random.uniform(0.028, 0.042)
    p0 = CHEEK + Vector((math.cos(a) * rr, random.uniform(0.004, 0.012), math.sin(a) * rr))
    p1 = CHEEK + Vector((math.cos(a) * rr * 0.55, random.uniform(0.002, 0.007), math.sin(a) * rr * 0.55))
    p2 = CHEEK + Vector((math.cos(a) * 0.0055, 0.0, math.sin(a) * 0.0055))
    cu = bpy.data.curves.new(f"Vessel{k}", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.0007
    cu.bevel_resolution = 3
    cu.fill_mode = "FULL"
    cu.bevel_factor_mapping_end = "SPLINE"
    sp = cu.splines.new("NURBS")
    sp.points.add(3)
    for pt, co in zip(sp.points, (p0, p0.lerp(p1, 0.5) + Vector((0, 0.004, 0.003)), p1, p2)):
        pt.co = (*co, 1.0)
    sp.use_endpoint_u = True
    sp.order_u = 3
    vo = bpy.data.objects.new(f"Vessel{k}", cu)
    ANAT.objects.link(vo)
    vo.data.materials.append(vessel_m)
    vo.cycles.use_motion_blur = False          # bevel_factor_end changes the topology per frame; Cycles would warn every still
    vessels.append(vo)
# immune cells (beat 7): approach the implant, sniff it, turn away
imm_m = K.plastic("ImmuneCell", (0.25, 0.85, 0.3), 0.4, sss=0.4)
imm_m.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (0.3, 1.0, 0.35, 1)
imm_m.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 2.2
cells = []
for i in range(14):
    o = K.sphere(f"Immune{i}", ANAT, 1.0, (0, 0, -50), imm_m, subdiv=3)
    tex = bpy.data.textures.new("ImmTex", "CLOUDS")
    tex.noise_scale = 0.4
    dp = o.modifiers.new("Disp", "DISPLACE")
    dp.texture = tex
    dp.strength = 0.3
    ang = random.uniform(0, 2 * math.pi)
    el = random.uniform(-0.6, 0.6)
    d = Vector((math.cos(ang) * math.cos(el), -abs(math.sin(ang)) * 0.6 - 0.4, math.sin(el))).normalized()
    cells.append((o, d, random.uniform(0.0, 0.35), random.uniform(0.0022, 0.0036), random.uniform(0, 9)))
for o in list(ANAT.objects):
    if o.parent is None:
        him.parent_to_bone(o, "Head")          # basis = rig-local rest coordinates
xray_lights_anchor = him.nose.copy()

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

# ---------------------------------------------------------------- performance
BLINKS = [b for b in (x * 3.1 + 1.1 for x in range(40)) if b < DUR and not (B[1] <= b < B[2])]


def him_channels(t):
    ch = {}
    ch["reach"] = env(t, B[1] - 0.05, B[1] + 0.25, PILL - 0.55, PILL - 0.35)          # hand to the bottle
    ch["pill"] = env(t, PILL - 0.5, PILL - 0.12, PILL + 0.05, PILL + 0.35)             # hand to the mouth
    ch["swallow"] = spike(t, PILL + 0.1, 0.08, 0.25)
    ch["sting"] = env(t, CLOUD + 0.12, CLOUD + 0.40, CLOUD + 0.72, CLOUD + 1.12)        # eyes burn AFTER cloud: stays open while corneas fog, then sting arrives
    ch["blind"] = max(env(t, CLOUD + 0.2, CLOUD + 0.6, B[3] - 0.2, B[3]), env(t, B[5], B[5] + 0.2, SEAT - 0.3, SEAT))
    ch["worry"] = max(env(t, 0, 0.2, B[1] - 0.2, B[1]) * 0.5, env(t, B[2], B[2] + 0.2, B[3] - 0.1, B[3]))
    ch["exam"] = env(t, B[2] + 0.1, B[2] + 0.4, B[3] - 0.2, B[3])                      # chin up into the penlight
    ch["sedated"] = 1.0 if (B[3] <= t < B[4]) or (B[6] <= t < B[7]) else 0.0
    ch["wake"] = env(t, B[8] - 0.1, B[8] + 0.3, DUR, DUR + 1)
    ch["focus"] = ramp(t, FOCUS - 0.1, FOCUS + 0.25)                                   # the world snaps sharp
    ch["lift"] = env(t, at(8, 0.55), at(8, 0.75), DUR, DUR + 1)                        # head lifts to the surgeon
    ch["joy"] = ramp(t, at(8, 0.72), B[9] + 0.3)
    ch["smile"] = max(ramp(t, B[9] + 0.05, B[9] + 0.6), 0.6 * ch["joy"])
    ch["glint"] = spike(t, GLINT, 0.06, 0.3)
    ch["blink"] = max((env(t, b - 0.03, b, b + 0.05, b + 0.12) for b in BLINKS), default=0.0)
    ch["unfocused"] = ch["blind"] * (1 - ch["focus"])
    return ch


def doc_channels(t):
    ch = {}
    ch["examine"] = env(t, B[2] + 0.05, B[2] + 0.45, B[3] - 0.2, B[3])                 # lean in with the penlight
    ch["extract"] = env(t, B[3] + 0.2, EXTRACT - 0.35, EXTRACT + 0.25, EXTRACT + 0.6)
    ch["pull"] = spike(t, EXTRACT, 0.10, 0.30)
    ch["implant"] = env(t, B[6] + 0.05, B[6] + 0.35, SEAT + 0.15, SEAT + 0.5)
    ch["operate"] = 1.0 if (B[3] <= t < B[4]) or (B[6] <= t < B[7]) else 0.0
    ch["meet"] = env(t, at(8, 0.5), at(8, 0.7), DUR, DUR + 1)
    ch["smile"] = ramp(t, at(8, 0.75), B[9] + 0.2)
    ch["blink"] = max((env(t, b - 0.03, b, b + 0.05, b + 0.12) for b in (x * 2.9 + 1.6 for x in range(40)) if b < DUR), default=0.0)
    return ch


THIGH_R = him.hips0.lerp(him.bone_rest_head("RightLeg"), 0.6) + Vector((-0.03, -0.25, 0.07))
THIGH_L = him.hips0.lerp(him.bone_rest_head("LeftLeg"), 0.6) + Vector((0.03, -0.25, 0.07))
for i, t in enumerate(T):
    s = SH[i]
    ch = him_channels(t)
    br = math.sin(t * 2 * math.pi / 3.8)
    lie = s[3] == "lie"
    sed = ch["sedated"]
    fwd = 6 * ch["exam"] - 4 * ch["sting"] + 3 * ch["pill"]
    rots = {}
    spec = {
        "Hips": [(A.Z, 0.5 * wobble(t, 1))],
        "Spine": [(A.X, (0 if lie else -8) + 0.5 * br + 0.45 * fwd), (A.Z, 0.7 * wobble(t, 2))],
        "Spine1": [(A.X, (0 if lie else -3) + 0.7 * br + 0.35 * fwd - 2 * ch["joy"])],
        "Spine2": [(A.X, 2 + 0.7 * br + 0.2 * fwd)],
        "Neck": [(A.X, (0 if lie else 4) + 0.25 * fwd - 6 * ch["exam"] - 5 * ch["lift"] + 3 * ch["blind"] * (1 - lie)),
                 (A.Z, 1.5 * wobble(t, 4) * (1 - sed) - 10 * ch["sting"] + 6 * ch["lift"])],
        "Head": [(A.X, 1 + 0.35 * fwd - 7 * ch["exam"] - 8 * ch["lift"] + 5 * ch["blind"] * (1 - lie) - 3 * ch["swallow"] + 1.0 * wobble(t, 7, 0.6) * (1 - sed)),
                 (A.Z, 2.0 * wobble(t, 5, 0.5) * (1 - sed) - 14 * ch["sting"] + 7 * ch["lift"] + 3 * ch["unfocused"] * math.sin(t * 1.7)),
                 (A.Y, 1.2 * wobble(t, 6) * (1 - sed) + 4 * ch["worry"] - 6 * ch["sting"])],
        "LeftShoulder": [(A.Y, 2 * ch["sting"] + 1.5 * ch["joy"])],
        "RightShoulder": [(A.Y, -2 * ch["sting"] - 4 * ch["pill"])],
    }
    for bone, axes in spec.items():
        if him.has(bone):
            q = A.Quaternion()
            for axis, deg in axes:
                q = q @ him.q(bone, axis, deg)
            rots[bone] = q
    for bone, q in (legs_sit if not lie else {}).items():
        rots[bone] = q
    if lie:
        for bone in ("LeftUpLeg", "RightUpLeg", "LeftLeg", "RightLeg", "LeftFoot", "RightFoot"):
            if him.has(bone):
                rots[bone] = A.Quaternion()
    for bone in him.fingers():
        j = int(bone[-1])
        curl = ({1: 25, 2: 35, 3: 25} if "Thumb" not in bone else {1: 8, 2: 15, 3: 10})[j]
        if bone.startswith("Right"):
            curl += 30 * max(ch["pill"], ch["reach"])
        rots[bone] = A.Quaternion((1, 0, 0), math.radians(curl))
    sh = {}
    for side in ("Left", "Right"):
        sh[f"eyeBlink{side}"] = min(1, ch["blink"] + 0.85 * ch["sting"] + sed + 0.35 * ch["blind"] * (1 - ch["focus"]) + 0.12 * ch["smile"])
        sh[f"eyeSquint{side}"] = 0.6 * ch["sting"] + 0.3 * ch["smile"] + 0.25 * ch["unfocused"]
        sh[f"eyeWide{side}"] = 0.45 * ch["focus"] * (1 - ch["smile"]) + 0.3 * ch["swallow"]
        sh[f"browDown{side}"] = 0.6 * ch["sting"] + 0.2 * ch["worry"]
        sh[f"mouthFrown{side}"] = 0.35 * ch["worry"] + 0.3 * ch["blind"] * (1 - ch["joy"])
        sh[f"mouthStretch{side}"] = 0.4 * ch["sting"]
        sh[f"mouthSmile{side}"] = 0.85 * ch["smile"]
        sh[f"cheekSquint{side}"] = 0.45 * ch["smile"]
        sh[f"mouthUpperUp{side}"] = 0.8 * ch["glint"]
    sh["browInnerUp"] = 0.5 * ch["worry"] + 0.6 * ch["focus"] * (1 - ch["smile"]) + 0.3 * ch["unfocused"]
    sh["jawOpen"] = 0.22 * ch["pill"] + 0.18 * ch["sting"] + 0.06 * ch["glint"] + 0.08 * ch["focus"] * (1 - ch["smile"])
    if lie:
        ikl = him.hips0 + Vector((0.24, -0.02, 0.0))
        ikr = him.hips0 + Vector((-0.24, -0.02, 0.0))
    else:
        ikl = THIGH_L.copy()
        ikr = THIGH_R + Vector((0, -0.05 * ch["sting"], 0.03 * ch["sting"]))
    follow = {"ToMouth": ch["pill"], "ToBottle": ch["reach"] * (1.0 if s[2] == "home" else 0.0)}
    him.record(rots, sh, ikl, ikr, aim=(0.0, 0.0), follow=follow, root=him_root(t, s))

if doc:
    dlegs = doc.standing_legs()
    for i, t in enumerate(T):
        s = SH[i]
        ch = doc_channels(t)
        br = math.sin(t * 2 * math.pi / 4.2 + 1)
        op = ch["operate"]
        lean = max(ch["examine"], op)
        rots = {}
        spec = {
            "Spine": [(A.X, 2 + 0.4 * br + 16 * lean)], "Spine1": [(A.X, 2 + 0.5 * br + 10 * lean)],
            "Neck": [(A.X, 5 + 10 * lean - 4 * ch["meet"]), (A.Z, 1.2 * wobble(t, 3))],
            "Head": [(A.X, 3 + 8 * lean - 5 * ch["meet"] + wobble(t, 9, 0.5)), (A.Y, 1.5 * wobble(t, 4) + 4 * ch["smile"]),
                     (A.Z, 2 * wobble(t, 8, 0.4))],
            "RightShoulder": [(A.Y, -5 * ch["examine"] - 4 * ch["pull"])],
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
            curl = ({1: 30, 2: 45, 3: 30} if "Thumb" not in bone else {1: 10, 2: 20, 3: 10})[j]
            if bone.startswith("Right"):
                curl += 15 * max(ch["examine"], op)
            rots[bone] = A.Quaternion((1, 0, 0), math.radians(curl))
        sh = {}
        for side in ("Left", "Right"):
            sh[f"eyeBlink{side}"] = ch["blink"]
            sh[f"eyeSquint{side}"] = 0.35 * ch["examine"] + 0.3 * ch["smile"]
            sh[f"mouthSmile{side}"] = 0.8 * ch["smile"]
            sh[f"cheekSquint{side}"] = 0.4 * ch["smile"]
            sh[f"browDown{side}"] = 0.3 * op
        sh["browInnerUp"] = 0.4 * ch["meet"]
        hip = doc.hips0
        side_l = hip + Vector((0.22, 0.02, -0.12))
        side_r = hip + Vector((-0.22, 0.02, -0.12))
        pen_up = Vector((doc.x0 - 0.08, doc.nose.y - 0.45, doc.nose.z - 0.32))   # rig-local: down and forward toward his seated eye
        ikr = side_r.lerp(pen_up, ch["examine"])
        ikl = side_l.lerp(hip + Vector((0.18, -0.30, 0.22)), op)
        doc.record(rots, sh, ikl, ikr, follow={"ToMouth": ch["extract"], "ToEye": ch["implant"]}, root=doc_root(t, s))

# ---------------------------------------------------------------- bake characters
him.bake(FRAMES)
if doc:
    doc.bake(FRAMES)
for rig in ([him.rig] + ([doc.rig] if doc else [])):
    for fc in A.fcurves_of(rig):
        if fc.data_path in ("location", "rotation_euler"):
            fc.keyframe_points.foreach_set("interpolation", [0] * len(fc.keyframe_points))   # teleports are cuts

# surgeon's hand targets in world space (filled from his baked head)
if doc:
    mg, eg = [], []
    for i in range(len(T)):
        if SH[i][3] == "lie":
            scene.frame_set(i + 1)
            mg.append(mouth_pt.matrix_world.translation + Vector((0, 0, 0.035)))
            eg.append(eye_pt.matrix_world.translation + Vector((0, 0, 0.03)))
        else:
            mg.append(FAR)
            eg.append(FAR)
    bake_vec(mouth_grip, "location", mg)
    bake_vec(eye_grip, "location", eg)

# ---------------------------------------------------------------- props driven by time
# pill in hand only while he reaches/takes it; the pill bottle tips on the pick-up
bake_vec(pill_hand, "scale", [(s_, s_, s_) for s_ in ((1.0 if (him_channels(t)["pill"] > 0.02 or him_channels(t)["reach"] > 0.6)
                                                    and SET_OF[i] == "home" and t < PILL + 0.12 else 0.0) for i, t in enumerate(T))], interp="CONSTANT")
bake(bottle, "rotation_euler", [math.radians(-14) * env(t, B[1] + 0.1, B[1] + 0.35, PILL - 0.4, PILL - 0.1) for t in T], index=0)
# corneas: clear until CLOUD, then milky; the graft in beat 2 clears and clouds again three times; the right one
# peels away at SEAT (the implant takes its place); the left stays cloudy for the rest of the story
cyc3 = lambda t: 0.5 - 0.5 * math.cos(2 * math.pi * 3 * ramp(t, B[2] + 0.1, B[3] - 0.1))
cloud_r, cloud_l = [], []
for t in T:
    base = ramp(t, CLOUD - 0.15, CLOUD + 0.35)
    if B[2] <= t < B[3]:
        base = 0.25 + 0.75 * cyc3(t)
    cloud_r.append(base)
    cloud_l.append(ramp(t, CLOUD - 0.15, CLOUD + 0.35))
bake(cornea_m.node_tree, 'nodes["Cloud"].outputs[0].default_value', [0.85 * v for v in cloud_r])   # the iris still ghosts through
bake_vec(cornea_r, "scale", [tuple(c * k for c in CR) for k in (1.0 - ramp(t, SEAT - 0.25, SEAT - 0.05) if t >= B[1] else 0.0 for t in T)])
bake_vec(cornea_l, "scale", [tuple(c * k for c in CR_L) for k in ((1.0 if B[1] <= t else 0.0) for t in T)])
# the ibuprofen reaction: a red flush washes over the face at CLOUD - 0.4
bake(rash_m.node_tree, 'nodes["Rash"].outputs[0].default_value', [env(t, CLOUD - 0.45, CLOUD - 0.15, CLOUD + 0.5, B[2]) for t in T])
# implant: eye (hook) -> hidden -> cheek (beat 5) -> eye (beat 6) -> eye
EYE_POS = EYE_R + Vector((0, -0.006, 0))
imp_loc, imp_sc = [], []
for t in T:
    if t < B[1]:
        p, k = EYE_POS, 1.0
    elif t < B[5] + 0.12:
        p, k = CHEEK, 0.0
    elif t < B[6]:
        p, k = CHEEK, ramp(t, B[5] + 0.12, B[5] + 0.4)
    else:
        u = ramp(t, B[6] + 0.25, SEAT)
        arc = Vector((0, -0.012, 0)) * math.sin(u * math.pi)
        p, k = CHEEK.lerp(EYE_POS, u) + arc, 1.0
    imp_loc.append(p)
    imp_sc.append(k)
bake_vec(implant, "location", imp_loc)
bake_vec(implant, "scale", [(k, k, k) for k in imp_sc])
bake(imp_glow.data.materials[0].node_tree, 'nodes["Pulse"].outputs[0].default_value',
     [(0.7 + 0.3 * math.sin(t * 2 * math.pi / 1.0)) * max(env(t, B[5], B[5] + 0.3, B[6] - 0.1, B[6]), 0.6 * env(t, B[7], B[7] + 0.2, B[8] - 0.1, B[8])) for t in T])
# vessels branch into the block during beat 5
for k_, vo in enumerate(vessels):
    a0 = B[5] + 0.35 + 0.08 * k_
    bake(vo.data, "bevel_factor_end", [ramp(t, a0, a0 + 1.0) for t in T])
# X-ray canine: ring lights up, then the tooth and its bone sliver lift down and out into the forceps
bake(canine_hi.node_tree, 'nodes["Principled BSDF"].inputs["Emission Strength"].default_value',
     [14.0 * env(t, B[3] + 0.15, B[3] + 0.4, EXTRACT - 0.1, EXTRACT + 0.2) for t in T])
pull = [ramp(t, EXTRACT - 0.05, EXTRACT + 0.45) for t in T]
bake_vec(canine, "location", [canine_home + Vector((0, -0.045 * u, -0.045 * u)) for u in pull])
bake_vec(sliver, "location", [canine_home + Vector((0, 0.001 - 0.045 * u, 0.0065 - 0.045 * u)) for u in pull])
for o in (canine, sliver):
    bake_vec(o, "scale", [(1, 1, 1) if t < B[4] else (0.001, 0.001, 0.001) for t in T], interp="CONSTANT")
# lab: whole tooth -> block (SHAVE), shavings scatter, drill descends (DRILL), lens slides in (LENS) with a glint
bake_vec(tooth_lab, "scale", [(1, 1, 1) if t < SHAVE else (0.001, 0.001, 0.001) for t in T], interp="CONSTANT")
bake_vec(block_lab, "scale", [(0.001, 0.001, 0.001) if t < SHAVE else (1, 1, 1) for t in T], interp="CONSTANT")
bake(block_lab, "rotation_euler", [0.75 + 0.3 * (t - B[4]) for t in T], index=2)             # slow turntable, big face starts toward the camera
for k_, sh_ in enumerate(shavings):
    s0 = tuple(sh_.scale)
    born = SHAVE - 0.05 + 0.02 * k_
    bake_vec(sh_, "scale", [tuple(v * ramp(t, born, born + 0.12) for v in s0) for t in T])
    bake_vec(sh_, "location", [sh_.location + Vector((0, 0, 0.012 * (1 - min(1.0, max(0.0, (t - born) / 0.25))) * (1 if t >= born else 0))) for t in T])
drill_z = [0.11 - 0.1055 * env(t, DRILL - 0.35, DRILL - 0.02, DRILL + 0.22, DRILL + 0.45) for t in T]   # bit tip reaches 1 mm into the 4.5 mm block
bake(drill, "location", [TOOTH_SPOT.z + z for z in drill_z], index=2)
bake(drill, "rotation_euler", [40.0 * t * env(t, DRILL - 0.5, DRILL - 0.3, DRILL + 0.4, DRILL + 0.7) for t in T], index=2)
# the cutter rises with the bit, so the bore opens progressively instead of popping in
bake(hole_cut, "location", [-0.03 + 0.0318 * env(t, DRILL - 0.3, DRILL - 0.02, 1e9, 1e9) for t in T], index=2)
lens_in = [ramp(t, LENS - 0.3, LENS + 0.05) for t in T]
bake_vec(lens_lab, "location", [Vector((0, 0, 0.0022 + 0.022 * (1 - u))) for u in lens_in])   # drops in from above, down the bore
bake_vec(lens_lab, "scale", [(1, 1, 1) if t >= LENS - 0.35 else (0.001, 0.001, 0.001) for t in T], interp="CONSTANT")
bake_vec(glint, "scale", [(k, k, k) for k in (0.001 + spike(t, LENS + 0.05, 0.03, 0.10) for t in T)])
# the closing "canine glint" is the lifted upper lip (mouthUpperUp on GLINT) catching the key on real enamel; no emissive dot
# immune cells: approach the implant, hover, turn away
for o, d, dly, r, seed in cells:
    locs, sc = [], []
    for t in T:
        if not (B[7] <= t < B[8]):
            locs.append(EYE_POS)
            sc.append(0.0)
            continue
        u_in = ramp(t, B[7] + dly, B[7] + dly + 0.9)
        u_out = ramp(t, at(7, 0.62) + dly * 0.5, B[8] - 0.05)
        dist = 0.11 * (1 - u_in) + 0.022 * u_in + 0.10 * u_out
        p = EYE_POS + d * dist + Vector((0.002 * math.sin(t * 6 + seed), 0.0015 * math.cos(t * 7 + seed), 0.002 * math.sin(t * 5 + seed)))
        locs.append(p)
        sc.append(r * min(1.0, (t - B[7]) / 0.2) * (1 + 0.1 * math.sin(t * 9 + seed)))
    bake_vec(o, "location", locs)
    bake_vec(o, "scale", [(v, v, v) for v in sc])

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


# Each anatomy object gets exactly one visibility pass: a second pass on the same object would leave the first
# pass's "visible" keys standing wherever its own value did not change. Boolean cutters (already hide_render)
# are never touched, or they would appear as spheres inside the skull.
key_vis([cornea_r, cornea_l], lambda i: SET_OF[i] != "xray")
key_vis([implant, imp_lens], lambda i: SET_OF[i] != "xray" or B[5] <= T[i] < B[8])
key_vis([imp_block], lambda i: SET_OF[i] == "xray" and B[5] <= T[i] < B[8])
key_vis([imp_mucosa], lambda i: SET_OF[i] != "xray")
key_vis([imp_glow], lambda i: SET_OF[i] == "xray")
key_vis([rash], lambda i: SET_OF[i] == "home" and B[1] <= T[i] < B[2])
key_vis([skull_root, *skull_parts, sliver, canine_ring], lambda i: SET_OF[i] == "xray" and B[3] <= T[i] < B[4])
key_vis(vessels, lambda i: SET_OF[i] == "xray" and B[5] <= T[i] < B[6] + 0.3)
key_vis([c[0] for c in cells], lambda i: SET_OF[i] == "xray" and B[7] <= T[i] < B[8])
special = {cornea_r, cornea_l, implant, *imp_parts, imp_mucosa, imp_glow, rash, skull_root, *skull_parts, sliver, canine_ring, *vessels,
           *[c[0] for c in cells]}
key_vis([o for o in ANAT.objects if o not in special and not o.hide_render], lambda i: SET_OF[i] == "xray")
for name, coll in (("home", HOME), ("clinic", CLIN), ("or", OR), ("lab", LAB)):
    # skip objects kit already hid: boolean cutters (kit._cut sets hide_render) must stay hidden, or they render as
    # solid geometry filling the very hole they cut
    key_vis([o for o in coll.all_objects if not o.hide_render], lambda i, name=name: SET_OF[i] == name)
key_vis([pen, *pen_parts, pen_spot], lambda i: SET_OF[i] == "clinic" and B[2] <= T[i] < B[3])
if doc:
    key_vis([o for o in doc.objs], lambda i: SET_OF[i] in ("clinic", "or"))
    key_vis([cap, mask], lambda i: SET_OF[i] == "or")
    key_vis([forceps, *getattr(forceps, "children", [])], lambda i: SET_OF[i] == "or")

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
WCOL = {"home": ((0.55, 0.50, 0.45), 0.35), "clinic": ((0.66, 0.74, 0.80), 0.28), "or": ((0.60, 0.72, 0.72), 0.25),
        "lab": ((0.30, 0.33, 0.38), 0.22), "xray": ((0.003, 0.010, 0.026), 1.0)}
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
HEAD_CLIN = SEAT_CLIN + Vector((0, -0.05, 0.62))
HEAD_OR = TABLE + Vector((0, -0.17, 1.12))
LIGHTS = {
    "home": [_area("HomeKey", HOME, HEAD_HOME + Vector((1.3, -1.6, 1.0)), HEAD_HOME, 320, 1.4, (1.0, 0.90, 0.80)),
             _area("HomeFill", HOME, HEAD_HOME + Vector((-1.6, -1.2, 0.2)), HEAD_HOME, 80, 2.0, (0.82, 0.90, 1.0)),
             _area("HomeRim", HOME, HEAD_HOME + Vector((-0.7, 1.3, 0.9)), HEAD_HOME, 220, 0.8, (0.92, 0.95, 1.0)),
             _area("WindowSpill", HOME, Vector((-1.5, 3.1, 1.6)), HEAD_HOME, 260, 1.3, (0.85, 0.92, 1.0))],
    "clinic": [_area("ClinKey", CLIN, HEAD_CLIN + Vector((1.4, -1.2, 1.6)), HEAD_CLIN, 300, 1.5, (0.96, 0.97, 1.0)),
               _area("ClinFill", CLIN, HEAD_CLIN + Vector((-1.8, -1.5, 1.0)), HEAD_CLIN, 110, 2.0, (0.82, 0.90, 1.0)),
               _area("ClinRim", CLIN, HEAD_CLIN + Vector((-0.6, 1.4, 1.1)), HEAD_CLIN, 160, 0.8, (0.9, 0.95, 1.0))],
    "or": [_area("ORTop", OR, HEAD_OR + Vector((0.1, 0.3, 1.15)), HEAD_OR, 520, 0.9, (1.0, 0.99, 0.97)),
           _area("ORFill", OR, TABLE + Vector((-1.8, -1.5, 2.2)), TABLE + Vector((0, 0, 1.0)), 180, 2.5, (0.85, 0.95, 1.0))],
    "lab": [_area("LabKey", LAB, TRAY + Vector((0.35, -0.45, 0.55)), TRAY, 45, 0.5, (1.0, 0.98, 0.95)),
            _area("LabFill", LAB, TRAY + Vector((-0.5, -0.3, 0.35)), TRAY, 30, 0.9, (0.85, 0.92, 1.0)),
            _area("LabRim", LAB, TRAY + Vector((-0.25, 0.40, 0.65)), TRAY, 25, 0.3, (0.95, 0.97, 1.0))],   # high, so its reflection misses the lens
    "xray": [_area("XKey", ANAT, xray_lights_anchor + Vector((0.6, -0.5, 0.5)), xray_lights_anchor, 12, 0.8, (1.0, 0.92, 0.88)),
             _area("XFill", ANAT, xray_lights_anchor + Vector((0.5, 0.4, -0.2)), xray_lights_anchor, 6, 1.0, (0.5, 0.7, 1.0))],
}
for o in LIGHTS["xray"]:
    him.parent_to_bone(o, "Head")
BASE = {l.name: l.data.energy for ls in LIGHTS.values() for l in ls}
for set_name, ls in LIGHTS.items():
    for l in ls:
        vals = []
        for i, t in enumerate(T):
            e = BASE[l.name] * (SET_OF[i] == set_name)
            if l.name == "WindowSpill" and B[1] <= t < B[2]:
                e *= 1.0 - 0.75 * ramp(t, CLOUD - 0.3, CLOUD + 0.3)                     # the room goes cold
            vals.append(e)
        bake(l.data, "energy", vals)
# beat 1: warm key turns cold as the corneas cloud (color storytelling, no text)
hk = LIGHTS["home"][0].data
for k_, (w, c_) in enumerate(zip((1.0, 0.90, 0.80), (0.70, 0.82, 1.0))):
    bake(hk, "color", [w + (c_ - w) * (ramp(t, CLOUD - 0.3, CLOUD + 0.3) if B[1] <= t < B[2] else 0.0) for t in T], index=k_)
bake(scene, '["xray"]', XRAY, interp="CONSTANT")
# exposure accents: X-ray entries, the drill, the focus snap
bake(scene, "view_settings.exposure", [-0.35 + 0.8 * sum(spike(t, s[0], 0.005, 0.04) for s in SHOTS if s[2] == "xray")
                                       + 0.5 * spike(t, FOCUS, 0.02, 0.12) + 0.15 * spike(t, LENS + 0.05, 0.01, 0.06) for t in T])

# ---------------------------------------------------------------- cameras (v3: moving splines, DOF from subject size)
cams = S.Cameras(scene, T, F, CAST)


def span(name):
    i = next(k for k, s in enumerate(SHOTS) if s[1] == name)
    return SHOTS[i][0], (SHOTS[i + 1][0] if i + 1 < len(SHOTS) else DUR)


def mid(name):
    a, b = span(name)
    return (a + b) / 2


W = cams.world_at
# hook: his implanted eye, pushing in; then a pull back to his face (frame 1 is the thumbnail: the eye, lit, moving)
a, b = span("EyeECU")
E0 = W(eye_pt, mid("EyeECU"))
cams.cam("EyeECU", a, b, keys=[(a, E0 + Vector((-0.045, -0.22, 0.02))), (b, E0 + Vector((-0.03, -0.15, 0.012)))], lens=85, aim=eye_pt, depth=0.02, shake=0.0, ease="cine")
a, b = span("FacePull")
F0 = W(face_pt, mid("FacePull"))
cams.cam("FacePull", a, b, keys=[(a, F0 + Vector((-0.08, -0.42, 0.02))), (b, F0 + Vector((-0.22, -1.05, 0.0)))], lens=50, aim=face_pt, focus=eyes_mid, depth=0.12, shift_y=-0.08, shake=0.0)
# beat 1: the pill goes in; the eyes cloud over
a, b = span("PillCU")
P0 = W(mouth_pt, PILL)
# an insert on the ibuprofen bottle beside him: his hand drops in from the top of frame, tips it and leaves with a pill
# (every framing of hand-to-mouth put the rising forearm or the hand itself across the lens)
BW = BOTTLE + Vector((0, 0, 0.03))
cams.cam("PillCU", a, b, keys=[(a, BW + Vector((-0.22, -0.30, 0.24))), (b, BW + Vector((-0.15, -0.21, 0.17)))], lens=85, aim=BW, depth=0.06, shake=0.0)
a, b = span("CloudEyes")
C0 = W(eyes_mid, mid("CloudEyes"))
cams.cam("CloudEyes", a, b, keys=[(a, C0 + Vector((0.03, -0.30, 0.01))), (b, C0 + Vector((-0.02, -0.22, 0.005)))], lens=85, aim=eyes_mid, depth=0.05, shake=0.0)
# beat 2: the clinic; the graft clouds again and again
a, b = span("ClinicOrbit")
HC = W(face_pt, mid("ClinicOrbit"))
# profile two-shot from his right side (the surgeon stands in front of him, so a frontal camera would see only her back)
CC = HC + Vector((-0.10, -0.40, -0.02))
cams.cam("ClinicOrbit", a, b, path=S.orbit(CC, 1.2, -84, -56, 0.22, 0.14), lens=40, aim=CC, focus=face_pt, depth=0.5, shift_y=-0.05, shake=0.0)
a, b = span("GraftECU")
G0 = W(eye_pt, mid("GraftECU"))
cams.cam("GraftECU", a, b, keys=[(a, G0 + Vector((-0.07, -0.22, 0.03))), (b, G0 + Vector((-0.045, -0.16, 0.02)))], lens=100, aim=eye_pt, depth=0.02, shake=0.0)
# beat 3: the OR, then a plunge into the jaw
a, b = span("ORWide")
M0 = W(mouth_pt, mid("ORWide"))
cams.cam("ORWide", a, b, keys=[(a, M0 + Vector((1.3, -1.0, 0.95))), (b, M0 + Vector((0.95, -0.7, 0.75)))], lens=32, aim=M0 + Vector((0, 0.1, 0.05)), focus=mouth_pt, depth=0.5, shake=0.0,
         plunge_out=(canine_pt, 0.45, 0.18))
# he lies face-up (head toward +Y), so "in front of the teeth" is +Z and the chin side is -Y
a, b = span("XJaw")
J0 = W(canine_pt, mid("XJaw"))
cams.cam("XJaw", a, b, keys=[(a, J0 + Vector((-0.03, -0.08, 0.19))), (EXTRACT, J0 + Vector((-0.10, -0.09, 0.14))), (b, J0 + Vector((-0.13, -0.11, 0.11)))], lens=50, aim=canine_pt, depth=0.05, shake=0.0,
         plunge_in=(canine_pt, 0.35, 0.18))
# beat 4: macro on the tray
a, b = span("TrayMacro")
# 3/4 height on the slab's 10 x 10 mm face. Never drop below ~40 mm above the tray: the tray is 300 x 220 mm and its
# near edge then fills the frame as foreground blur.
BLOCK_C = TOOTH_SPOT + Vector((0, 0, 0.0022))
cams.cam("TrayMacro", a, b, path=S.orbit(BLOCK_C, 0.115, 20, 50, 0.075, 0.065), lens=100, aim=BLOCK_C, depth=0.014, shake=0.0)
a, b = span("LensMacro")
cams.cam("LensMacro", a, b, keys=[(a, BLOCK_C + Vector((0.058, -0.092, 0.072))), (LENS, BLOCK_C + Vector((0.045, -0.072, 0.060))), (b, BLOCK_C + Vector((0.034, -0.058, 0.050)))], lens=120, aim=BLOCK_C, depth=0.016, shake=0.0)
# beat 5: X-ray of the cheek, vessels branching in
a, b = span("CheekX")
K0 = W(cheek_pt, mid("CheekX"))
cams.cam("CheekX", a, b, keys=[(a, K0 + Vector((-0.30, -0.28, 0.06))), (b, K0 + Vector((-0.20, -0.20, 0.04)))], lens=60, aim=cheek_pt, depth=0.05, shake=0.0)
a, b = span("VesselMacro")
K1 = W(cheek_pt, mid("VesselMacro"))
cams.cam("VesselMacro", a, b, path=S.orbit(K1, 0.12, -70, -35, 0.03, 0.015), lens=100, aim=cheek_pt, depth=0.012, shake=0.0)
# beat 6: the implant seats into the eye (one short beat, one macro shot; we are already inside the X-ray)
a, b = span("EyeSeat")
Z0 = W(eye_pt, mid("EyeSeat"))
cams.cam("EyeSeat", a, b, keys=[(a, Z0 + Vector((-0.07, -0.03, 0.14))), (SEAT, Z0 + Vector((-0.045, -0.02, 0.10))), (b, Z0 + Vector((-0.03, -0.015, 0.085)))], lens=85, aim=eye_pt, depth=0.014, shake=0.0)
# beat 7: inside the body, immune cells approach and turn away
a, b = span("Immune")
Q0 = W(eye_pt, mid("Immune"))
cams.cam("Immune", a, b, path=S.orbit(Q0, 0.22, -55, -10, 0.03, -0.01, r1=0.17), lens=60, aim=eye_pt, depth=0.06, shake=0.0)
# beat 8: POV through the lens (a real tube in front of the glass gives the small round field of view), then the two-shot
a, b = span("POVFocus")
if doc:
    EP = W(eye_pt, mid("POVFocus"))
    DF = W(doc_face, mid("POVFocus"))
    toward = (DF - EP).normalized()
    pov = cams.cam("POVFocus", a, b, keys=[(a, EP + toward * 0.012), (b, EP + toward * 0.03 + Vector((0, 0, 0.01)))], lens=35, aim=doc_face, depth=0.3, fstop=2.8, shake=0.0)
    bake(pov.data, "dof.aperture_fstop", [0.5 + 2.3 * ramp(t, FOCUS - 0.25, FOCUS + 0.2) for t in T])
    tube_m = K.plastic("LensTube", (0.01, 0.01, 0.012), 0.6)
    vig = K.lathe("POVTube", CAST, [(0.0105, 0.0), (0.03, 0.0), (0.03, -0.05), (0.0105, -0.05)], (0, 0, 0), tube_m, steps=48, subsurf=0)
    vig.parent = pov
    vig.location = (0, 0, -0.012)
    vig.rotation_euler = (0, 0, 0)
    key_vis([vig], lambda i: SH[i][1] == "POVFocus")
    a, b = span("TwoShot")
    FF = W(face_pt, mid("TwoShot"))
    DD = W(doc_face, mid("TwoShot"))
    over = FF.lerp(DD, 0.35)
    # over HER shoulder (she faces +Y, so behind her is -Y): her hair and coat edge soft in the foreground, his face sharp
    cams.cam("TwoShot", a, b, keys=[(a, DD + Vector((0.14, -0.42, 0.12))), (b, DD + Vector((0.11, -0.34, 0.10)))], lens=55, aim=face_pt, focus=eyes_mid, depth=0.15, shift_y=-0.06, shake=0.0)
else:
    cams.cam("POVFocus", a, b, keys=[(a, W(face_pt, a) + Vector((0, -0.6, 0))), (b, W(face_pt, b) + Vector((0, -0.5, 0)))], lens=50, aim=face_pt, depth=0.15, shake=0.0)
    a, b = span("TwoShot")
    cams.cam("TwoShot", a, b, keys=[(a, W(face_pt, a) + Vector((0.3, -0.7, 0.1))), (b, W(face_pt, b) + Vector((0.2, -0.6, 0.05)))], lens=50, aim=face_pt, depth=0.15, shake=0.0)
# closer: back home, a matching push-in to the implanted eye (echoes frame 1 for the loop)
a, b = span("Closer")
L0 = W(face_pt, mid("Closer"))
cams.cam("Closer", a, b, keys=[(a, L0 + Vector((-0.20, -0.95, 0.06))), (GLINT, L0 + Vector((-0.10, -0.55, 0.06))), (b, L0 + Vector((-0.04, -0.26, 0.05)))], lens=65, aim=face_pt, focus=eyes_mid, depth=0.06, shift_y=-0.07, shake=0.0, ease="cine")

cams.markers(SHOTS)
S.check_shots(SHOTS, DUR)

# eyes that look at things: the pill, the penlight, the surgeon
def gaze_target(t):
    s = shot_at(t)
    if s[2] == "clinic" and doc:
        return W(doc_eyes, t)
    if s[2] == "home" and B[1] <= t < PILL:
        return W(mouth_pt, t) + Vector((-0.1, -0.3, -0.1))
    return None


him.bake_gaze(FRAMES, T, gaze_target, CAST, seed=5)
if doc:
    doc.bake_gaze(FRAMES, T, lambda t: W(eyes_mid, t) if shot_at(t)[2] in ("clinic", "or") else None, CAST, seed=6)

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
