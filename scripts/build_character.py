"""Build a reusable MPFB2 human with a Mixamo-compatible rig and save it as a .blend.

Run: blender -b --python build_character.py -- <out.blend> [preset_json]
The preset (optional) overrides the defaults in HERO below.
"""
import json
import os
import sys

import bpy
from bl_ext.blender_org.mpfb.services.humanservice import HumanService
from bl_ext.blender_org.mpfb.services.targetservice import TargetService
from bl_ext.blender_org.mpfb.services.faceservice import FaceService

argv = sys.argv[sys.argv.index("--") + 1:]
OUT = argv[0]

HERO = {
    "name": "Hero",
    "phenotype": {"gender": 1.0, "age": 0.5, "muscle": 0.62, "weight": 0.52,
                  "height": 0.55, "proportions": 0.6},
    "rig": "mixamo",
    "skin_mhmat": "young_caucasian_male.mhmat",
    "skin_material_type": "ENHANCED_SSS",
    "eyes": "high-poly.mhclo",
    # PROCEDURAL_EYES renders as dark discs under Cycles in Blender 5.2; MakeSkin eyes are reliable
    "eyes_material_type": "MAKESKIN",
    "eye_texture": "brownlight_eye.png",
    "eyebrows": "eyebrow001.mhclo",
    "eyelashes": "eyelashes01.mhclo",
    "teeth": "teeth_base.mhclo",
    "tongue": "tongue01.mhclo",
    "hair": "short02.mhclo",
    "proxy": "",
    "clothes": ["male_casualsuit05.mhclo", "shoes02.mhclo"],
    # Stylized-realism face: slightly caricatured, readable on a phone screen.
    "targets": [
        {"target": "l-eye-scale-incr", "value": 0.35}, {"target": "r-eye-scale-incr", "value": 0.35},
        {"target": "nose-scale-vert-incr", "value": 0.25}, {"target": "nose-scale-horiz-incr", "value": 0.2},
        {"target": "nose-point-width-incr", "value": 0.3},
        {"target": "chin-prominent-incr", "value": 0.35}, {"target": "chin-width-incr", "value": 0.25},
        {"target": "l-cheek-bones-incr", "value": 0.3}, {"target": "r-cheek-bones-incr", "value": 0.3},
        {"target": "mouth-lowerlip-volume-incr", "value": 0.25},
        {"target": "eyebrows-trans-down", "value": 0.2}, {"target": "head-square", "value": 0.3},
    ],
}
if len(argv) > 1:
    HERO.update(json.load(open(argv[1])))

bpy.ops.wm.read_factory_settings(use_empty=True)

eye_texture = HERO.pop("eye_texture")
info = HumanService._create_default_human_info_dict()
phenotype = TargetService.get_default_macro_info_dict()
phenotype.update(HERO.pop("phenotype"))
info.update(HERO)
info["phenotype"] = phenotype

settings = HumanService.get_default_deserialization_settings()
settings["subdiv_levels"] = 1
basemesh = HumanService.deserialize_from_dict(info, settings)

# Eyes: chosen iris texture + wet cornea coat for catchlights
eyes = next(o for o in bpy.data.objects if o.name.endswith("high-poly"))
eye_nt = eyes.material_slots[0].material.node_tree
eye_img = next(n for n in eye_nt.nodes if n.type == "TEX_IMAGE")
eye_img.image = bpy.data.images.load(
    os.path.join(os.path.dirname(bpy.path.abspath(eye_img.image.filepath)), eye_texture))
eye_bsdf = next(n for n in eye_nt.nodes if n.type == "BSDF_PRINCIPLED")
eye_bsdf.inputs["Roughness"].default_value = 0.25
eye_bsdf.inputs["Coat Weight"].default_value = 1.0
eye_bsdf.inputs["Coat Roughness"].default_value = 0.02
eye_bsdf.inputs["Coat IOR"].default_value = 1.376
print("EYETEX", eye_img.image.filepath)

# Face shape keys for expressions (ARKit 52) and lip sync (Meta/Oculus 15 visemes)
FaceService.load_targets(basemesh, load_microsoft_visemes=False, load_meta_visemes=True,
                         load_arkit_faceunits=True)
FaceService.interpolate_targets(basemesh)
keys = [k.name for k in basemesh.data.shape_keys.key_blocks]
print("SHAPEKEYS", len(keys), [k for k in keys if k.startswith(("!ex-", "viseme"))][:8])
print("MACRO", sorted(phenotype))

# Default rotation_mode on a new armature's pose bones is Euler ('XYZ'), which quietly makes
# any script that only writes rotation_quaternion (ours included) a no-op for FK purposes: the
# bone transform is actually driven by rotation_euler while rotation_quaternion is a dead
# property. Fixing it here, once, means every script and saved retargeted Action downstream
# (which store fcurve data only, not this per-bone mode setting) inherits the correct mode.
rig = next((o for o in bpy.data.objects if o.type == "ARMATURE"), None)
for pb in rig.pose.bones:
    pb.rotation_mode = "QUATERNION"
print("BASEMESH", basemesh.name, "verts", len(basemesh.data.vertices))
print("RIG", rig.name if rig else None, "bones", len(rig.data.bones) if rig else 0)
print("BONES", [b.name for b in rig.data.bones][:12] if rig else [])
print("OBJECTS", sorted(o.name for o in bpy.data.objects))
print("HEIGHT", round(max((rig.matrix_world @ b.head_local).z for b in rig.data.bones), 3) if rig else None)

bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("SAVED", OUT)
