"""Character performance toolkit for MPFB humans with a Mixamo ("mixamorig:") rig.

    import actor as A
    her = A.Actor.load(path_to_blend, "Her")          # appends the character from a .blend
    her.measure()                                      # head/nose/eyes/hips etc. in REST pose
    her.setup_ik()                                     # IK arms with targets parented to the rig object
    ... per-frame:  her.set_pose(f, {"Spine": [(X, 10)], ...}, shapes={...}, ik={...})
    her.bake(frames)                                   # one fcurve per channel, fast

Everything is baked per frame (smooth at any FPS). The rig object itself can be moved between
sets with constant keys (teleport) so one actor can appear in several locations.
"""
import math

import bpy
from mathutils import Matrix, Quaternion, Vector

MX = "mixamorig:"
X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))


# ------------------------------------------------------------------ easing (smooth motion)
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def smooth(x):            # smootherstep, zero velocity AND acceleration at both ends
    x = clamp(x)
    return x * x * x * (x * (x * 6 - 15) + 10)


def ramp(t, a, b):
    if b <= a:
        return 1.0 if t >= b else 0.0
    return smooth((t - a) / (b - a))


def env(t, a, b, c, d):
    return ramp(t, a, b) * (1 - ramp(t, c, d))


def spike(t, at, rise, decay):
    x = t - at
    if x < -rise:
        return 0.0
    if x < 0:
        return smooth((x + rise) / rise)
    return math.exp(-x / decay)


def overshoot(t, a, b, amount=0.12):
    """0 -> 1 with a small springy overshoot after b (anticipation/settle feel)."""
    if t <= a:
        return 0.0
    if t >= b:
        k = (t - b) / max(1e-6, (b - a))
        return 1.0 + amount * math.sin(k * 2 * math.pi) * math.exp(-k * 4)
    return smooth((t - a) / (b - a)) * (1 + amount * 0.0)


def wobble(t, seed, speed=1.0, freqs=(0.21, 0.47, 0.83)):
    return sum(math.sin(t * speed * q * 2 * math.pi + seed * (i + 1.7)) / (i + 1) for i, q in enumerate(freqs))


# ------------------------------------------------------------------ overlap, follow-through, slow motion
def delay(vals, fps, sec):
    """Shift a per-frame channel later by `sec` (fractional samples), holding the first value."""
    k = sec * fps
    out = []
    for i in range(len(vals)):
        x = i - k
        if x <= 0:
            out.append(vals[0])
            continue
        j = int(x)
        u = x - j
        out.append(vals[j] if j + 1 >= len(vals) else vals[j] * (1 - u) + vals[j + 1] * u)
    return out


def spring(vals, fps, hz=3.0, zeta=0.4, sub=4):
    """Second-order follower of a per-frame channel: lag, overshoot and settle (frame-rate independent).
    Use on necks, heads, hands, hair and props so nothing stops dead."""
    w = 2 * math.pi * hz
    dt = 1.0 / (fps * sub)
    x, v = vals[0], 0.0
    out = []
    for target in vals:
        for _ in range(sub):
            v += (w * w * (target - x) - 2 * zeta * w * v) * dt
            x += v * dt
        out.append(x)
    return out


def follow(vals, fps, sec=0.06, hz=3.5, zeta=0.45):
    """delay + spring: the standard overlap for the next bone down a chain (spine -> neck -> head)."""
    return spring(delay(vals, fps, sec), fps, hz, zeta)


def timewarp(slo_a, slo_b, act_a, act_b):
    """Slow-motion map: screen time t in [slo_a, slo_b) plays action time act_a..act_b; identity elsewhere.
    Evaluate every animated channel at warp(t) inside the slow-mo shot (Zack's single 'money moment')."""
    def warp(t):
        if slo_a <= t < slo_b:
            return act_a + (act_b - act_a) * (t - slo_a) / (slo_b - slo_a)
        return t
    return warp


# ------------------------------------------------------------------ fcurve baking
def fcurves_of(idb):
    act = idb.animation_data.action
    if hasattr(act, "fcurves"):
        return act.fcurves
    from bpy_extras import anim_utils
    return anim_utils.action_get_channelbag_for_slot(act, idb.animation_data.action_slot).fcurves


def bake(idb, path, values, frames, index=None, interp="LINEAR"):
    frames = list(frames)
    before = set()
    if idb.animation_data and idb.animation_data.action:
        before = {(c.data_path, c.array_index) for c in fcurves_of(idb)}
    if index is None:
        idb.keyframe_insert(data_path=path, frame=frames[0])
    else:
        idb.keyframe_insert(data_path=path, index=index, frame=frames[0])
    fcs = fcurves_of(idb)
    fc = fcs.find(path, index=index or 0)
    if fc is None:
        fc = next(c for c in fcs if (c.data_path, c.array_index) not in before)
    fc.keyframe_points.clear()
    fc.keyframe_points.add(len(values))
    fc.keyframe_points.foreach_set("co", [c for f, v in zip(frames, values) for c in (f, float(v))])
    fc.keyframe_points.foreach_set("interpolation", [{"CONSTANT": 0, "LINEAR": 1}[interp]] * len(values))
    fc.update()
    return fc


def bake_vec(idb, path, vecs, frames, n=3, interp="LINEAR"):
    for i in range(n):
        bake(idb, path, [v[i] for v in vecs], frames, index=i, interp=interp)


# ------------------------------------------------------------------ actor
class Actor:
    def __init__(self, rig, objs, name):
        self.name = name
        self.rig = rig
        self.objs = objs                               # every object that came with the character
        self.body = next((o for o in objs if o.name.endswith(".body")), None) or max(
            (o for o in objs if o.type == "MESH"), key=lambda o: len(o.data.vertices))
        self.faces = [o for o in objs if o.type == "MESH" and o.data.shape_keys]
        for pb in rig.pose.bones:
            pb.rotation_mode = "QUATERNION"
            pb.rotation_quaternion = (1, 0, 0, 0)
        self.rest = {pb.name: pb.bone.matrix_local.to_quaternion() for pb in rig.pose.bones}
        self.rot = {}                                  # bone -> [quat per frame]
        self.shapes = {}                               # shape key -> [value per frame]
        self.ik_loc = {"Left": [], "Right": []}        # rig-local IK target positions
        self.aim_infl = {"Left": [], "Right": []}
        self.copy_infl = {}                            # constraint name -> [influence]
        self.root_loc, self.root_rot = [], []

    # ---------------- loading
    @staticmethod
    def from_scene(name):
        """Use the character already in the open file (the one that was opened as the main file)."""
        rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
        objs = [o for o in bpy.data.objects if o.type in ("MESH", "CURVES", "CURVE") and _root_of(o) is rig]
        rig.name = name + "Rig"
        return Actor(rig, objs, name)

    @staticmethod
    def append(path, name, coll):
        """Append every object of another character .blend (second actor), renamed with a prefix."""
        with bpy.data.libraries.load(path, link=False) as (src, dst):
            dst.objects = list(src.objects)
        new = [o for o in dst.objects if o is not None]
        for o in new:
            coll.objects.link(o)
            o.name = f"{name}.{o.name}"
        rig = next(o for o in new if o.type == "ARMATURE")
        objs = [o for o in new if o.type in ("MESH", "CURVES", "CURVE")]
        return Actor(rig, objs, name)

    # ---------------- measurements (rest pose, rig-local coordinates)
    def measure(self):
        rig = self.rig
        mw_inv = rig.matrix_world.inverted()
        rig.data.pose_position = "REST"
        bpy.context.view_layer.update()
        deps = bpy.context.evaluated_depsgraph_get()
        ev = self.body.evaluated_get(deps)
        me = ev.to_mesh()
        verts = [mw_inv @ (self.body.matrix_world @ v.co) for v in me.vertices]
        ev.to_mesh_clear()
        rig.data.pose_position = "POSE"
        b = rig.data.bones
        self.head0 = b[MX + "Head"].head_local.copy()
        self.hips0 = b[MX + "Hips"].head_local.copy()
        x0 = self.head0.x
        hv = [v for v in verts if v.z > self.head0.z - 0.06 and abs(v.x - x0) < 0.13]
        self.top = max(v.z for v in hv)
        mid = [v for v in hv if abs(v.x - x0) < 0.015]
        band = [v for v in mid if self.top - 0.21 < v.z < self.top - 0.09] or mid
        self.nose = min(band, key=lambda v: v.y).copy()
        self.back_y = max(v.y for v in mid if v.z > self.top - 0.16)
        self.x0 = x0
        self.eye_l = Vector((x0 + 0.032, self.nose.y + 0.03, self.nose.z + 0.035))
        self.eye_r = Vector((x0 - 0.032, self.nose.y + 0.03, self.nose.z + 0.035))
        self.mouth = Vector((x0, self.nose.y + 0.012, self.nose.z - 0.045))
        self.height = self.top
        return self

    def bone_rest_tail(self, bone):
        return self.rig.data.bones[MX + bone].tail_local.copy()

    def bone_rest_head(self, bone):
        return self.rig.data.bones[MX + bone].head_local.copy()

    # ---------------- parenting helpers
    def parent_to_bone(self, obj, bone):
        """Parent obj to a bone so it keeps its CURRENT rig-local rest position: afterwards obj.matrix_basis is
        expressed in the rig's rest-pose local space (bake locations in that space)."""
        b = self.rig.data.bones[MX + bone]
        obj.parent, obj.parent_type, obj.parent_bone = self.rig, "BONE", MX + bone
        rest = b.matrix_local @ Matrix.Translation((0, b.length, 0))
        obj.matrix_parent_inverse = rest.inverted()
        return obj

    def anchor(self, name, bone, local_pos, coll):
        e = bpy.data.objects.new(f"{self.name}.{name}", None)
        coll.objects.link(e)
        e.empty_display_size = 0.03
        e.location = local_pos
        self.parent_to_bone(e, bone)
        return e

    # ---------------- rotations
    def q(self, bone, axis, deg):
        r = self.rest[MX + bone]
        return r.inverted() @ Quaternion(axis, math.radians(deg)) @ r

    def aim_chain(self, chain):
        out, parent_delta = {}, Quaternion()
        for bone, target in chain:
            b = self.rig.data.bones[MX + bone]
            d = (b.tail_local - b.head_local).normalized()
            c = d.rotation_difference(parent_delta.inverted() @ Vector(target).normalized())
            r = self.rest[MX + bone]
            out[bone] = r.inverted() @ c @ r
            parent_delta = parent_delta @ c
        return out

    def seated_legs(self, spread=0.14):
        legs = {}
        for side, sx in (("Left", 1), ("Right", -1)):
            legs.update(self.aim_chain([(f"{side}UpLeg", (spread * sx, -1, -0.06)), (f"{side}Leg", (0.05 * sx, -0.3, -1)),
                                        (f"{side}Foot", (0.03 * sx, -1, -0.7))]))
        return legs

    def standing_legs(self):
        legs = {}
        for side, sx in (("Left", 1), ("Right", -1)):
            legs.update(self.aim_chain([(f"{side}UpLeg", (0.03 * sx, -0.02, -1)), (f"{side}Leg", (0.0, 0.02, -1)),
                                        (f"{side}Foot", (0.02 * sx, -1, -0.55))]))
        return legs

    def has(self, bone):
        return MX + bone in self.rig.pose.bones

    def fingers(self):
        return [b.name[len(MX):] for b in self.rig.data.bones if "Hand" in b.name and b.name[-1] in "123"]

    # ---------------- IK arms (targets live in rig-local space, so they follow teleports)
    def setup_ik(self, coll):
        self.ik = {}
        for side, sx in (("Left", 1), ("Right", -1)):
            t = bpy.data.objects.new(f"{self.name}.IK_{side}", None)
            coll.objects.link(t)
            t.parent = self.rig
            t.empty_display_size = 0.04
            c = self.rig.pose.bones[MX + side + "ForeArm"].constraints.new("IK")
            c.name = "IK"
            c.target = t
            c.chain_count = 2
            c.use_tail = True
            pole = bpy.data.objects.new(f"{self.name}.Pole_{side}", None)
            coll.objects.link(pole)
            pole.parent = self.rig
            pole.location = (self.x0 + 0.6 * sx, self.hips0.y + 0.4, self.hips0.z + 0.2)
            c.pole_target = pole
            c.pole_angle = math.radians(-90)
            self.ik[side] = t
        return self.ik

    def hand_follow(self, side, target_obj, name):
        """Blend the IK target onto another (moving) object via a Copy Location constraint; animate with
        self.copy_infl[name]."""
        c = self.ik[side].constraints.new("COPY_LOCATION")
        c.name = name
        c.target = target_obj
        c.influence = 0.0
        self.copy_infl[name] = (side, [])
        return c

    def hand_aim(self, side, target_obj):
        c = self.rig.pose.bones[MX + side + "Hand"].constraints.new("DAMPED_TRACK")
        c.name = "Aim"
        c.target = target_obj
        c.track_axis = "TRACK_Y"
        c.influence = 0.0
        return c

    # ---------------- per-frame recording
    def record(self, rots, shapes, ik_l, ik_r, aim=(0.0, 0.0), follow=None, root=None):
        """rots: {bone: Quaternion}; shapes: {key: value}; ik_*: rig-local Vector;
        follow: {constraint_name: influence}; root: (location Vector, euler tuple) of the rig object."""
        for bone, q in rots.items():
            self.rot.setdefault(bone, []).append(q)
        for k, v in shapes.items():
            self.shapes.setdefault(k, []).append(clamp(v))
        self.ik_loc["Left"].append(ik_l)
        self.ik_loc["Right"].append(ik_r)
        self.aim_infl["Left"].append(aim[0])
        self.aim_infl["Right"].append(aim[1])
        for name, (side, vals) in self.copy_infl.items():
            vals.append((follow or {}).get(name, 0.0))
        if root is not None:
            self.root_loc.append(root[0])
            self.root_rot.append(root[1])

    def bake(self, frames):
        frames = list(frames)
        for bone, qs in self.rot.items():
            for i in range(1, len(qs)):
                if qs[i].dot(qs[i - 1]) < 0:
                    qs[i] = -qs[i]
            path = f'pose.bones["{MX}{bone}"].rotation_quaternion'
            for i in range(4):
                bake(self.rig, path, [q[i] for q in qs], frames, index=i)
        for o in self.faces:
            kb = o.data.shape_keys.key_blocks
            for k, vals in self.shapes.items():
                if k in kb:
                    bake(o.data.shape_keys, f'key_blocks["{k}"].value', vals, frames)
        for side in ("Left", "Right"):
            bake_vec(self.ik[side], "location", self.ik_loc[side], frames)
            if any(self.aim_infl[side]):
                bake(self.rig, f'pose.bones["{MX}{side}Hand"].constraints["Aim"].influence', self.aim_infl[side], frames)
        for name, (side, vals) in self.copy_infl.items():
            bake(self.ik[side], f'constraints["{name}"].influence', vals, frames)
        if self.root_loc:
            bake_vec(self.rig, "location", self.root_loc, frames)
            bake_vec(self.rig, "rotation_euler", self.root_rot, frames)

    # ---------------- eyes (ARKit eyeLook* shape keys; the mixamo rig has no eye bones)
    def bake_gaze(self, frames, T, target_fn, coll, seed=1, step=2, deg_per_unit=(30.0, 25.0)):
        """Eyes that look at things. Call AFTER self.bake(). target_fn(t) -> world Vector, or None to look ahead.
        Adds micro-saccades (new offset every 0.5-2 s, up to 1.5 deg). Evaluated every `step` frames."""
        import random
        frames = list(frames)
        rnd = random.Random(seed)
        mid = (self.eye_l + self.eye_r) / 2
        eye = self.anchor("EyeMid", "Head", mid, coll)
        sac, t_next, cur = [], 0.0, (0.0, 0.0)
        for t in T:
            if t >= t_next:
                cur = (rnd.uniform(-1.5, 1.5), rnd.uniform(-1.0, 1.0))
                t_next = t + rnd.uniform(0.5, 2.0)
            sac.append(cur)
        scene = bpy.context.scene
        yaw, pitch = [], []
        idx = list(range(0, len(frames), step))
        if idx[-1] != len(frames) - 1:
            idx.append(len(frames) - 1)
        samples = {}
        for i in idx:
            tgt = target_fn(T[i])
            if tgt is None:
                samples[i] = (0.0, 0.0)
                continue
            scene.frame_set(frames[i])
            M = eye.matrix_world
            d = M.to_3x3().normalized().inverted() @ (Vector(tgt) - M.translation)
            samples[i] = (math.degrees(math.atan2(d.x, -d.y)), math.degrees(math.atan2(d.z, math.hypot(d.x, d.y))))
        for k in range(len(idx) - 1):
            a, b = idx[k], idx[k + 1]
            for i in range(a, b):
                u = (i - a) / (b - a)
                yaw.append(samples[a][0] * (1 - u) + samples[b][0] * u)
                pitch.append(samples[a][1] * (1 - u) + samples[b][1] * u)
        yaw.append(samples[idx[-1]][0])
        pitch.append(samples[idx[-1]][1])
        fps = scene.render.fps
        yaw = spring([y + s[0] for y, s in zip(yaw, sac)], fps, hz=9.0, zeta=0.8)     # fast, slightly damped saccades
        pitch = spring([p + s[1] for p, s in zip(pitch, sac)], fps, hz=9.0, zeta=0.8)
        hy, vp = deg_per_unit
        keys = {
            "eyeLookOutLeft": [clamp(y / hy) for y in yaw], "eyeLookInRight": [clamp(y / hy) for y in yaw],
            "eyeLookInLeft": [clamp(-y / hy) for y in yaw], "eyeLookOutRight": [clamp(-y / hy) for y in yaw],
            "eyeLookUpLeft": [clamp(p / vp) for p in pitch], "eyeLookUpRight": [clamp(p / vp) for p in pitch],
            "eyeLookDownLeft": [clamp(-p / vp) for p in pitch], "eyeLookDownRight": [clamp(-p / vp) for p in pitch],
        }
        n = 0
        for o in self.faces:
            kb = o.data.shape_keys.key_blocks
            for k, vals in keys.items():
                if k in kb:
                    bake(o.data.shape_keys, f'key_blocks["{k}"].value', vals, frames)
                    n += 1
        print(f"GAZE {self.name}: {n} eyeLook channels baked" + ("" if n else " -- WARN no eyeLook* shape keys found"))
        return n

    # ---------------- materials
    def tint_material(self, obj_suffix, color, amount=0.85):
        """Recolour a clothing item (e.g. turn a suit into a white lab coat) while keeping its texture detail."""
        for o in self.objs:
            if o.type == "MESH" and obj_suffix in o.name:
                for slot in o.material_slots:
                    m = slot.material
                    if not m or not m.use_nodes:
                        continue
                    m = m.copy()
                    slot.material = m
                    nt = m.node_tree
                    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
                    if bsdf is None:
                        continue
                    sock = bsdf.inputs["Base Color"]
                    mix = nt.nodes.new("ShaderNodeMix")
                    mix.data_type = "RGBA"
                    mix.inputs["Factor"].default_value = amount
                    mix.inputs["B"].default_value = (*color, 1)
                    if sock.links:
                        nt.links.new(sock.links[0].from_socket, mix.inputs["A"])
                    else:
                        mix.inputs["A"].default_value = sock.default_value
                    nt.links.new(mix.outputs["Result"], sock)


def _root_of(o):
    while o.parent is not None:
        o = o.parent
    return o
