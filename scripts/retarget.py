"""Retarget a Mixamo FBX animation onto the hero rig (MPFB 'mixamo' skeleton).

Run: blender -b blend/char_hero.blend --python retarget.py -- <clip.fbx> <action_name> [--in-place]
Writes blend/anims/<action_name>.blend holding the retargeted action (fake user), which shot
scripts append and place with NLA strips.

Method (full derivation; this replaced two earlier, buggy attempts -- see inline notes):
Blender's FK model is   W(b) = W(parent(b)) @ R(b) @ P(b)
  W(b) = bone b's rotation in world/armature space for the CURRENT pose
  R(b) = bone b's REST rotation relative to its parent (constant)
  P(b) = pose_bone.rotation_quaternion, the animated local delta-from-rest (what we write)

For each bone mapped between skeletons, we compute ONCE (from each skeleton's rest pose) a
per-bone WORLD-space correction  Delta(b) = G_tgt_rest(b) @ G_src_rest(b)^-1  (G_*_rest is the
bone's absolute world rest rotation). This Delta absorbs BOTH a differing rest pose between the
two rigs (e.g. true T-pose vs. MPFB's slight A-pose) AND any difference in bone-roll convention
-- both of which a naive "compare the bone's own Y-axis direction" check cannot see, since a
bone's local Y-axis is by definition always its own head->tail direction on both skeletons.
We then define the target's desired world rotation per animated frame as
  W_tgt(b) = Delta(b) @ W_src(b)
and solve the FK equation above for P_tgt(b), processing bones parent-first so W_tgt(parent)
is already known from earlier in the same frame. Unmapped target bones keep local identity
rotation and simply inherit their (now-corrected) parent's world rotation, so e.g. fingers
dangle naturally off a retargeted hand even with no finger data in the source clip.
Hips translation is scaled by leg length so motion scales to the hero's height.
"""
import math
import os
import re
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

PREFIX = re.compile(r"^mixamorig\d*:")


def norm(name):
    return PREFIX.sub("", name)


def world_rest_rot(arm_obj, bone):
    return arm_obj.matrix_world.to_quaternion() @ bone.matrix_local.to_quaternion()


def hierarchy(arm_obj):
    out = []

    def walk(b):
        out.append(b)
        for c in b.children:
            walk(c)
    for b in arm_obj.data.bones:
        if b.parent is None:
            walk(b)
    return out


def retarget(src, tgt, frame_start, frame_end, action_name, in_place=False):
    src_by_norm = {norm(b.name): b for b in src.data.bones}
    mapping = {tb.name: src_by_norm[norm(tb.name)] for tb in tgt.data.bones if norm(tb.name) in src_by_norm}
    missing = [norm(b.name) for b in tgt.data.bones if b.name not in mapping]
    print("RETARGET mapped", len(mapping), "missing", missing)

    tgt_order = hierarchy(tgt)
    delta = {tb.name: world_rest_rot(tgt, tb) @ world_rest_rot(src, sb).inverted()
             for tb, sb in ((tb, mapping.get(tb.name)) for tb in tgt_order) if sb is not None}
    g_tgt_rest = {b.name: world_rest_rot(tgt, b) for b in tgt_order}
    r_tgt = {}  # bone's rest rotation relative to its parent
    for b in tgt_order:
        parent_g = g_tgt_rest[b.parent.name] if b.parent else tgt.matrix_world.to_quaternion()
        r_tgt[b.name] = parent_g.inverted() @ g_tgt_rest[b.name]
    max_delta_deg = max((d.angle * 180 / math.pi for d in delta.values()), default=0)
    print("REST_POSE_CORRECTION_DEG_RANGE", round(min((d.angle * 180 / math.pi for d in delta.values()), default=0), 1),
          "to", round(max_delta_deg, 1))

    hips_t = tgt.data.bones["mixamorig:Hips"]
    hips_s = mapping["mixamorig:Hips"]
    scale = (tgt.matrix_world @ hips_t.head_local).z / max((src.matrix_world @ hips_s.head_local).z, 1e-6)
    src_hips_rest_w = src.matrix_world @ hips_s.head_local
    tgt_hips_rest_w = tgt.matrix_world @ hips_t.head_local

    if tgt.animation_data is None:
        tgt.animation_data_create()
    action = bpy.data.actions.new(action_name)
    action.use_fake_user = True
    tgt.animation_data.action = action
    # Bones default to Euler ('XYZ') rotation_mode; build_character.py already switches the
    # hero's own bones to QUATERNION so the fcurves we write below actually drive the pose (see
    # its comment for why this matters), but we defensively re-assert it here too, and the
    # source/Mixamo rig also needs it so we can read spb.rotation_quaternion correctly below.
    for pb in tgt.pose.bones:
        pb.rotation_mode = "QUATERNION"
    for pb in src.pose.bones:
        pb.rotation_mode = "QUATERNION"

    scene = bpy.context.scene
    first_xy = None
    for f in range(frame_start, frame_end + 1):
        scene.frame_set(f)
        w_tgt = {}  # this frame's computed world rotation per target bone, parent-first
        for tb in tgt_order:
            sb = mapping.get(tb.name)
            parent_w = w_tgt[tb.parent.name] if tb.parent else tgt.matrix_world.to_quaternion()
            if sb is None:
                w_tgt[tb.name] = parent_w @ r_tgt[tb.name]  # identity local pose; just follow parent
                continue
            spb = src.pose.bones[sb.name]
            w_src = src.matrix_world.to_quaternion() @ spb.matrix.to_quaternion()
            w_tgt[tb.name] = delta[tb.name] @ w_src
            local = r_tgt[tb.name].inverted() @ parent_w.inverted() @ w_tgt[tb.name]
            local.normalize()
            pb = tgt.pose.bones[tb.name]
            pb.rotation_quaternion = local
            pb.keyframe_insert("rotation_quaternion", frame=f)

        cur_w = src.matrix_world @ src.pose.bones[hips_s.name].head
        offset_w = (cur_w - src_hips_rest_w) * scale
        if in_place:
            if first_xy is None:
                first_xy = offset_w.xy.copy()
            offset_w.x -= first_xy.x
            offset_w.y -= first_xy.y
        desired_arm = tgt.matrix_world.inverted() @ (tgt_hips_rest_w + offset_w)
        rest3 = hips_t.matrix_local.to_3x3()
        pbh = tgt.pose.bones[hips_t.name]
        pbh.location = rest3.inverted() @ (desired_arm - hips_t.head_local)
        pbh.keyframe_insert("location", frame=f)
    action.frame_range = (frame_start, frame_end)
    return action, mapping


def import_fbx(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=path, ignore_leaf_bones=True, automatic_bone_orientation=False)
    new = [o for o in bpy.data.objects if o not in before]
    src = next(o for o in new if o.type == "ARMATURE")
    act = src.animation_data.action if src.animation_data else None
    return src, new, act


def save_action(action, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    bpy.data.libraries.write(out_path, {action}, fake_user=True)


if __name__ == "__main__" and "--" in sys.argv:
    args = sys.argv[sys.argv.index("--") + 1:]
    fbx, name = args[0], args[1]
    in_place = "--in-place" in args
    tgt = bpy.data.objects["Hero"]
    src, new_objs, src_action = import_fbx(fbx)
    fs, fe = (int(src_action.frame_range[0]), int(src_action.frame_range[1])) if src_action else (1, 1)
    print("SOURCE", src.name, "frames", fs, fe, "bones", len(src.data.bones))
    action, mapping = retarget(src, tgt, fs, fe, name, in_place)
    save_action(action, os.path.join(r"D:\ShortsPipeline\blend\anims", name + ".blend"))
    print("SAVED_ACTION", name, fs, fe)
