"""Camera + render helpers shared by every queue scene.py (v3, Zack D style).

    import shot as S
    S.setup_render(scene, fps=FPS, end=END, pct=PCT, samples=SAMPLES, device=DEVICE)
    cams = S.Cameras(scene, T, F, coll=CAST)
    cams.cam("NoseECU", a, b, keys=[(a, p0), (b, p1)], lens=85, aim=nostril, depth=0.03)
    cams.cam("XOrbit", a, b, path=S.orbit(head_pos, 0.6, 20, 45, 0.05, 0.02), lens=50, aim=xhead, depth=0.12)
    cams.markers(SHOTS)                       # SHOTS = [(t0, name, ...), ...]

Why (from the Zack D research, templates/STYLE_GUIDE.md):
  * every shot moves, and the camera is already moving on the cut frame (no ease-in/ease-out stops);
    keys are joined by one monotone cubic spline per axis, so interior keys never stop the camera;
  * depth of field is computed from the subject's real size (fstop_for), never hand-picked mush;
  * motion blur samples [f, f+0.5] (START) so CONSTANT set teleports never smear the cut frame;
  * plunge in/out moves give the "fly into the body" transition between a live shot and the X-ray.
"""
import math

import bpy
from mathutils import Vector

import actor as A


# ------------------------------------------------------------------ render
def setup_render(scene, fps, end, pct=100, samples=48, device="gpu", exposure=-0.35, look="AgX - Punchy"):
    scene.frame_start, scene.frame_end = 1, end
    scene.render.fps = fps
    scene.render.engine = "CYCLES"
    c = scene.cycles
    c.samples = samples
    c.use_adaptive_sampling = True
    c.adaptive_threshold = 0.03
    c.use_denoising = True
    c.max_bounces, c.diffuse_bounces, c.glossy_bounces, c.transmission_bounces, c.transparent_max_bounces = 8, 3, 3, 6, 32
    c.caustics_reflective = c.caustics_refractive = False
    c.blur_glossy = 1.0
    if device == "gpu":
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
    r = scene.render
    r.resolution_x, r.resolution_y = 1080, 1920
    r.resolution_percentage = pct
    r.use_motion_blur = True
    r.motion_blur_shutter = 0.5
    r.motion_blur_position = "START"      # never straddle a CONSTANT teleport on a cut frame
    r.use_persistent_data = True
    r.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = look
    except TypeError:
        print("WARN look not available:", look)
    scene.view_settings.exposure = exposure
    if pct != 100:
        print(f"!! WARNING: resolution_percentage={pct}, NOT a full-resolution render")


def fstop_for(depth, lens_mm, dist, coc=0.00003):
    """f-number whose depth of field covers `depth` metres of subject at `dist` metres (36 mm sensor, ~2 px CoC)."""
    dist = max(dist, 1e-3)
    return max(1.4, min(32.0, depth * (lens_mm / 1000.0) ** 2 / (2 * coc * dist ** 2)))


# ------------------------------------------------------------------ paths
def _hermite_slopes(ts, ys):
    """Fritsch-Carlson monotone slopes; end slopes are the end secants (camera keeps moving on the cut)."""
    n = len(ts)
    d = [(ys[i + 1] - ys[i]) / max(1e-9, ts[i + 1] - ts[i]) for i in range(n - 1)]
    m = [d[0]] + [0.0 if d[i - 1] * d[i] <= 0 else (d[i - 1] + d[i]) / 2 for i in range(1, n - 1)] + [d[-1]]
    for i in range(n - 1):
        if d[i] == 0:
            m[i] = m[i + 1] = 0.0
            continue
        a, b = m[i] / d[i], m[i + 1] / d[i]
        s = a * a + b * b
        if s > 9:
            k = 3 / math.sqrt(s)
            m[i], m[i + 1] = k * a * d[i], k * b * d[i]
    return m


def spline(keys):
    """keys [(t, Vector)] -> f(t) Vector: one monotone cubic per axis through every key (no stops at keys)."""
    keys = sorted(keys, key=lambda k: k[0])
    if len(keys) == 1:
        p = keys[0][1].copy()
        return lambda t: p.copy()
    ts = [k[0] for k in keys]
    axes = [[k[1][i] for k in keys] for i in range(3)]
    slopes = [_hermite_slopes(ts, ys) for ys in axes]

    def f(t):
        if t <= ts[0]:
            return Vector([axes[i][0] + slopes[i][0] * (t - ts[0]) for i in range(3)])
        if t >= ts[-1]:
            return Vector([axes[i][-1] + slopes[i][-1] * (t - ts[-1]) for i in range(3)])
        j = 0
        while t > ts[j + 1]:
            j += 1
        h = ts[j + 1] - ts[j]
        u = (t - ts[j]) / h
        h00, h10, h01, h11 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u, -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
        return Vector([h00 * axes[i][j] + h10 * h * slopes[i][j] + h01 * axes[i][j + 1] + h11 * h * slopes[i][j + 1]
                       for i in range(3)])
    return f


def orbit(center, radius, az0, az1, z0=0.0, z1=0.0, r1=None):
    """Path u(0..1) -> point on a true arc around `center` (degrees; az 0 = in front, i.e. -Y; +az towards +X)."""
    center = Vector(center)
    r1 = radius if r1 is None else r1

    def f(u):
        az = math.radians(az0 + (az1 - az0) * u)
        r = radius + (r1 - radius) * u
        return center + Vector((r * math.sin(az), -r * math.cos(az), z0 + (z1 - z0) * u))
    return f


EASES = {
    "lin": lambda x: x,
    "cine": lambda x: 0.7 * x + 0.3 * A.smooth(x),     # moving on both cuts, slightly softer in the middle
    "in": lambda x: x ** 3,                            # accelerate (plunge into a body)
    "out": lambda x: 1 - (1 - x) ** 3,                 # decelerate (arrive from a plunge)
    "smooth": A.smooth,                                # only for the very first / last shot
}


# ------------------------------------------------------------------ cameras
class Cameras:
    def __init__(self, scene, T, F, coll):
        self.scene, self.T, self.F, self.coll = scene, T, F, coll
        self.frames = range(1, len(T) + 1)
        self.cams = {}

    def world_at(self, obj, t):
        self.scene.frame_set(self.F(t))
        return obj.matrix_world.translation.copy()

    def _target(self, name, aim):
        if isinstance(aim, (Vector, tuple, list)):
            e = bpy.data.objects.new(name, None)
            self.coll.objects.link(e)
            e.location = Vector(aim)
            return e
        return aim

    def cam(self, name, t0, t1, keys=None, path=None, lens=50, aim=None, focus=None, depth=None, fstop=None,
            ease="lin", shake=0.0012, kicks=(), shift_y=0.0, plunge_out=None, plunge_in=None, lens_keys=None):
        """A tracked camera for the shot [t0, t1] (seconds).

        keys      [(t, Vector)] world positions (spline through all of them), or
        path      f(u) -> Vector with u = ease((t-t0)/(t1-t0)) (e.g. orbit(...)).
        aim       object (or point) the camera tracks; focus defaults to aim.
        depth     metres of subject that must be sharp -> f-stop from the mid-shot distance (fstop overrides).
        shift_y   frame offset (fraction of 1920 px); -0.1 puts the tracked point ~190 px above centre.
        kicks     [(t, amp_m, decay_s)] damped jolts (impacts, slams).
        plunge_out (anchor_obj_or_point, dur_s, stop_dist_m): accelerate into the anchor over the last dur_s.
        plunge_in  (anchor_obj_or_point, dur_s, start_dist_m): arrive from start_dist on the same ray, decelerating.
        lens_keys [(t, mm)] animated focal length.
        """
        aim = self._target(name + "Aim", aim)
        focus = self._target(name + "Focus", focus) if focus is not None else aim
        d = bpy.data.cameras.new(name)
        d.lens, d.sensor_width, d.clip_start, d.clip_end = lens, 36, 0.004, 400
        d.shift_y = shift_y
        d.dof.use_dof = True
        d.dof.focus_object = focus
        o = bpy.data.objects.new(name, d)
        self.coll.objects.link(o)
        tr = o.constraints.new("TRACK_TO")
        tr.target, tr.track_axis, tr.up_axis = aim, "TRACK_NEGATIVE_Z", "UP_Y"

        e = EASES[ease] if isinstance(ease, str) else ease
        span = max(1e-6, t1 - t0)
        sp = spline(keys) if keys else None

        def base(t):
            tc = min(max(t, t0), t1)
            if sp is not None:
                return sp(t0 + e((tc - t0) / span) * span)
            return path(e((tc - t0) / span))

        def anchor_pos(a, t):
            return self.world_at(a, t) if hasattr(a, "matrix_world") else Vector(a)

        po = pi = None
        if plunge_out:
            po = (anchor_pos(plunge_out[0], t1), plunge_out[1], plunge_out[2])
        if plunge_in:
            pi = (anchor_pos(plunge_in[0], t0), plunge_in[1], plunge_in[2])
        pts = []
        for t in self.T:
            p = base(t)
            if po and t > t1 - po[1]:
                w = min(1.0, (t - (t1 - po[1])) / po[1]) ** 3
                p = p.lerp(po[0] + (p - po[0]).normalized() * po[2], w)
            if pi and t < t0 + pi[1]:
                w = (1 - max(0.0, (t - t0) / pi[1])) ** 3
                p = p.lerp(pi[0] + (p - pi[0]).normalized() * pi[2], w)
            if shake:
                p = p + Vector((A.wobble(t, 11, 0.6), A.wobble(t, 12, 0.5), A.wobble(t, 13, 0.55))) * shake
            for tk, amp, dec in kicks:
                if t >= tk:
                    k = amp * math.exp(-(t - tk) / dec)
                    p = p + Vector((A.wobble(t, 21, 9), A.wobble(t, 22, 8), A.wobble(t, 23, 10))) * k
            pts.append(p)
        A.bake_vec(o, "location", pts, self.frames)
        if lens_keys:
            lk = sorted(lens_keys)
            vals = []
            for t in self.T:
                if t <= lk[0][0]:
                    vals.append(lk[0][1])
                elif t >= lk[-1][0]:
                    vals.append(lk[-1][1])
                else:
                    j = next(i for i in range(len(lk) - 1) if lk[i][0] <= t <= lk[i + 1][0])
                    u = A.smooth((t - lk[j][0]) / max(1e-6, lk[j + 1][0] - lk[j][0]))
                    vals.append(lk[j][1] + (lk[j + 1][1] - lk[j][1]) * u)
            A.bake(d, "lens", vals, self.frames)
        if fstop is None:
            tm = (t0 + t1) / 2
            dist = (base(tm) - self.world_at(focus, tm)).length
            fstop = fstop_for(depth if depth is not None else 0.25, lens, dist)
        d.dof.aperture_fstop = fstop
        self.cams[name] = o
        return o

    def markers(self, shots):
        """shots: [(t0, name, ...)] in order; binds a timeline marker per camera and sets the first camera."""
        for s in shots:
            if s[1] in self.cams:
                self.scene.timeline_markers.new(s[1], frame=self.F(s[0])).camera = self.cams[s[1]]
        first = next(s[1] for s in shots if s[1] in self.cams)
        self.scene.camera = self.cams[first]
        self.scene.frame_set(1)
        return [self.F(s[0]) for s in shots]


def check_shots(shots, dur, min_len=0.9, max_len=3.4):
    """Warn about shots outside the Zack D rhythm (1.5-3 s typical; nothing static and long)."""
    out = []
    for i, s in enumerate(shots):
        b = shots[i + 1][0] if i + 1 < len(shots) else dur
        L = b - s[0]
        if L < min_len or L > max_len:
            out.append((s[1], round(L, 2)))
    if out:
        print("WARN shot lengths outside", (min_len, max_len), out)
    print(f"SHOTS {len(shots)} over {dur:.1f}s, mean {dur / max(1, len(shots)):.2f}s")
    return out
