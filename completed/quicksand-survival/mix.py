"""Sound design + mix for "quicksand-survival" (numpy + soundfile only).

Usage: python mix.py <beats.json> <vo.wav> <out_mix.wav>
beats.json: {"duration": s, "beats": [{"start","end","text"}, ...]}. Effects are synthesized and
cued RELATIVE to the beat times, so any narration take works. SYNC fractions below must match the
same beats in scene.py. Final loudness (-14 LUFS) is applied by ffmpeg loudnorm when muxed.
"""
import json
import sys

import numpy as np
import soundfile as sf

BEATS_JSON, VO_WAV, OUT = sys.argv[1:4]
rng = np.random.default_rng(11)

vo, SR = sf.read(VO_WAV, dtype="float32")
if vo.ndim > 1:
    vo = vo.mean(axis=1)
meta = json.load(open(BEATS_JSON, encoding="utf-8"))
B = [float(b["start"]) for b in meta["beats"]]
E = [float(b["end"]) for b in meta["beats"]]
assert len(B) == 10, f"expected 10 beats, got {len(B)}"
TAIL = 36 / 30
TOTAL = max(float(meta["duration"]), len(vo) / SR) + TAIL
N = int(TOTAL * SR) + SR // 2
mix = np.zeros(N, np.float32)
music = np.zeros(N, np.float32)

# SYNC with scene.py
SLO_A_F = 0.30     # beat 5 (0-indexed 4): the slow-mo yank starts at this fraction of the beat
YANK_F = 0.45      # fraction of the slow-mo window [SLO_A, next beat - 0.05] where the foot locks
JERK_F = (0.12, 0.42, 0.72)   # beat 6 (0-indexed 5): the rope snaps taut


def at_beat(i, frac):
    nxt = B[i + 1] if i + 1 < len(B) else TOTAL - TAIL
    return B[i] + frac * (nxt - B[i])


# ------------------------------------------------------------------ synth helpers
def db(x):
    return 10 ** (np.asarray(x) / 20)


def fft_filter(x, lo=None, hi=None):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    g = np.ones_like(f)
    if lo:
        g *= np.clip(np.log2(np.maximum(f, 1) / (lo / 2)), 0, 1)
    if hi:
        g *= np.clip(np.log2((hi * 2) / np.maximum(f, 1)), 0, 1)
    return np.fft.irfft(X * g, len(x)).astype(np.float32)


def noise(sec):
    return rng.standard_normal(max(1, int(sec * SR))).astype(np.float32)


def norm(x):
    return (x / (np.abs(x).max() + 1e-9)).astype(np.float32)


def env_ar(n, a, r):
    e = np.ones(n, np.float32)
    na, nr = min(n, int(a * SR)), min(n, int(r * SR))
    if na:
        e[:na] = np.linspace(0, 1, na)
    if nr:
        e[-nr:] *= np.linspace(1, 0, nr) ** 2
    return e


def place(sig, t, gain_db, bus=None):
    bus = mix if bus is None else bus
    i = int(t * SR)
    j = max(0, i)
    s = sig[j - i:][: max(0, N - j)]
    bus[j:j + len(s)] += s * float(db(gain_db))


def tone(freq, sec, decay=None):
    t = np.arange(int(sec * SR)) / SR
    s = np.sin(2 * np.pi * freq * t)
    if decay:
        s *= np.exp(-t * decay)
    return s.astype(np.float32)


def boom(sec=0.6, f0=55):
    t = np.arange(int(sec * SR)) / SR
    pitch = f0 * (1 + 0.8 * np.exp(-t * 18))
    return (np.sin(2 * np.pi * np.cumsum(pitch) / SR) * np.exp(-t * 7)).astype(np.float32)


def whoosh(sec=0.5, rising=True):
    n = int(sec * SR)
    out = np.zeros(n, np.float32)
    w = noise(sec + 0.1)
    seg = 1024
    for k in range(0, n, seg):
        x = k / n if rising else 1 - k / n
        c = 300 + 3500 * x ** 2
        chunk = fft_filter(w[k:k + seg * 2], lo=c * 0.6, hi=c * 1.6)[:seg]
        out[k:k + len(chunk)] = chunk[: n - k]
    return norm(out * np.sin(np.linspace(0, np.pi, n)) ** 1.5)


def crack(sec=0.3):
    n = int(sec * SR)
    c = (rng.random(n) < 0.012).astype(np.float32) * rng.uniform(0.4, 1, n).astype(np.float32)
    c = np.convolve(c, np.exp(-np.arange(160) / 18), mode="same")
    s = fft_filter(c, lo=1200, hi=9000) * np.exp(-np.arange(n) / (0.08 * SR))
    return norm(s)


def heartbeat(sec, bpm=72):
    s = np.zeros(int(sec * SR), np.float32)
    beat = boom(0.22, 48)
    t = 0.0
    while t < sec - 0.5:
        for off, g in ((0, 1.0), (0.26, 0.55)):
            i = int((t + off) * SR)
            s[i:i + len(beat)] += beat[: len(s) - i] * g
        t += 60 / bpm
    return s


def squelch(sec):
    n = int(sec * SR)
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * np.cumsum(3 + 3 * rng.random(n)) / SR)
    return norm(fft_filter(noise(sec), lo=150, hi=900) * lfo * env_ar(n, 0.2, 0.3))


def chime():
    return norm(sum(tone(f, 1.2, decay=4.0) for f in (1046.5, 1318.5, 1568.0)))


def beep():
    return (tone(1000, 0.09) * env_ar(int(0.09 * SR), 0.005, 0.02)).astype(np.float32)


def chirp():
    sec = 0.18
    t = np.arange(int(sec * SR)) / SR
    f = 3200 + 1800 * np.sin(2 * np.pi * 14 * t)
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * env_ar(len(t), 0.01, 0.08)).astype(np.float32)


def sting(sec=1.0):
    t = np.arange(int(sec * SR)) / SR
    f = 330 * 2 ** (t / sec)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.5 * np.sin(2 * np.pi * np.cumsum(f * 1.5) / SR)
    return norm(s * env_ar(len(t), 0.4, 0.3))


def clink():
    return norm(sum(tone(f, 0.5, decay=9) / k for k, f in enumerate((2637, 3951, 5274), 1)))


def knife(sec=0.3):
    return norm(fft_filter(noise(sec), lo=800, hi=6000) * env_ar(int(sec * SR), 0.01, 0.2))


def squish(sec=0.25):
    return norm(fft_filter(noise(sec), lo=100, hi=1800) * env_ar(int(sec * SR), 0.01, 0.15))


def pop(sec=0.3):
    n = int(sec * SR)
    click = (rng.random(n) < 0.02).astype(np.float32)
    s = fft_filter(click, lo=400, hi=5000) * np.exp(-np.arange(n) / (0.015 * SR))
    return norm(s)


def creak(sec=0.4):
    t = np.arange(int(sec * SR)) / SR
    f = 180 + 30 * np.sin(2 * np.pi * 3 * t)
    return norm((np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.5 + 0.5 * fft_filter(noise(sec), lo=150, hi=900))
                * env_ar(len(t), 0.05, 0.3))


def hum(sec):
    t = np.arange(int(sec * SR)) / SR
    return (0.5 * np.sin(2 * np.pi * 42 * t) + 0.3 * np.sin(2 * np.pi * 63 * t)).astype(np.float32)


# ------------------------------------------------------------------ narration cleanup
v = fft_filter(vo, lo=75)
win = int(0.02 * SR)
rms = np.sqrt(np.convolve(v ** 2, np.ones(win) / win, mode="same") + 1e-12)
lvl = 20 * np.log10(rms)
g = np.where(lvl > -24, -(lvl + 24) * 0.5, 0.0)
g = np.convolve(g, np.ones(win) / win, mode="same")
v = norm(v * db(g).astype(np.float32))
voice = np.zeros(N, np.float32)
voice[: len(v)] = v[:N] * float(db(-3))
# ------------------------------------------------------------------ extra synth: surf, gulls, suction, rope
def surf(sec):
    """Distant waves: low-passed noise swelling on a slow, uneven cycle."""
    n = int(sec * SR)
    tt = np.arange(n) / SR
    swell = 0.55 + 0.45 * np.sin(2 * np.pi * tt / 5.5) * np.sin(2 * np.pi * tt / 9.1 + 1.0)
    return norm(fft_filter(noise(sec), lo=80, hi=1400) * swell.astype(np.float32))


def gull():
    sec = 0.55
    tt = np.arange(int(sec * SR)) / SR
    f = 1500 + 700 * np.exp(-tt * 6) * np.sin(2 * np.pi * 7 * tt)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.3 * np.sin(4 * np.pi * np.cumsum(f) / SR)
    return norm(s * env_ar(len(tt), 0.03, 0.25))


def suction(sec=0.6):
    """Thick, low, sucking slurp: band-passed noise with a falling centre and a wobbly gate."""
    n = int(sec * SR)
    out = np.zeros(n, np.float32)
    w = noise(sec + 0.1)
    seg = 1024
    for k in range(0, n, seg):
        c = 900 - 700 * (k / n)
        chunk = fft_filter(w[k:k + seg * 2], lo=c * 0.5, hi=c * 1.4)[:seg]
        out[k:k + len(chunk)] = chunk[: n - k]
    gate = 0.6 + 0.4 * np.sin(2 * np.pi * np.cumsum(6 + 6 * rng.random(n)) / SR)
    return norm(out * gate * env_ar(n, 0.05, 0.25))


def grind(sec):
    """Grains packing together: dense granular crackle."""
    n = int(sec * SR)
    c = (rng.random(n) < 0.03).astype(np.float32) * rng.uniform(0.3, 1, n).astype(np.float32)
    c = np.convolve(c, np.exp(-np.arange(90) / 10), mode="same")
    return norm(fft_filter(c, lo=500, hi=5000) * env_ar(n, 0.1, 0.2))


def trickle(sec):
    """Water seeping: bubbly band-passed noise plus tiny random blips."""
    n = int(sec * SR)
    base = fft_filter(noise(sec), lo=600, hi=3000) * (0.5 + 0.5 * np.sin(2 * np.pi * np.cumsum(4 + 8 * rng.random(n)) / SR))
    blips = np.zeros(n, np.float32)
    for _ in range(int(sec * 9)):
        i = int(rng.random() * (n - 2000))
        f = rng.uniform(900, 2200)
        blips[i:i + 1600] += tone(f, 1600 / SR, decay=40) * 0.6
    return norm((base + blips) * env_ar(n, 0.2, 0.3))


def twang():
    """A rope snapping taut: low thump plus a short creaky fibre stretch."""
    s = boom(0.25, 70) + 0.6 * creak(0.25)
    snap = fft_filter(noise(0.08), lo=1500, hi=6000) * env_ar(int(0.08 * SR), 0.002, 0.06)
    s[: len(snap)] += 0.3 * snap
    return norm(s)


def gasp():
    return norm(fft_filter(noise(0.35), lo=500, hi=4000) * env_ar(int(0.35 * SR), 0.06, 0.2))


def wash(sec=2.2):
    """A wave washing in across the flat: rising roar then fizz."""
    n = int(sec * SR)
    tt = np.arange(n) / SR
    roar = fft_filter(noise(sec), lo=60, hi=900) * np.clip(tt / (0.45 * sec), 0, 1) ** 1.5
    fizz = fft_filter(noise(sec), lo=2500, hi=9000) * np.clip((tt - 0.45 * sec) / (0.3 * sec), 0, 1)
    return norm((roar + 0.5 * fizz) * env_ar(n, 0.05, 0.5))


# ------------------------------------------------------------------ music bed: tense pulse -> calm hope -> danger again
t = np.arange(N) / SR
SLO_A = at_beat(4, SLO_A_F)
SLO_B = B[5] - 0.05
yank_t = SLO_A + YANK_F * (SLO_B - SLO_A)
drone = (0.6 * np.sin(2 * np.pi * 55 * t) + 0.3 * np.sin(2 * np.pi * 82.4 * t + 1.0)
         + 0.15 * np.sin(2 * np.pi * 110 * t)) * (0.7 + 0.3 * np.sin(2 * np.pi * 0.2 * t))
tense = drone.astype(np.float32) * (1 - 0.6 * np.clip((t - B[6]) / 0.6, 0, 1) * (1 - np.clip((t - B[9]) / 0.6, 0, 1)))
pulse = np.zeros(N, np.float32)
k = 0.0
while k < B[6]:
    place(fft_filter(boom(0.3, 46), hi=180), k, -6, bus=pulse)
    k += 60 / (110 if k < B[2] else 100)
k = B[9] + 0.1
while k < TOTAL - 0.6:
    place(fft_filter(boom(0.3, 46), hi=180), k, -6, bus=pulse)
    k += 60 / 120
calm = np.clip((t - B[6]) / 0.8, 0, 1) * (1 - np.clip((t - B[9]) / 0.4, 0, 1))
pad = sum(np.sin(2 * np.pi * f * t + i) / (i + 1) for i, f in enumerate((220.0, 277.2, 329.6, 440.0)))
pad = fft_filter(pad.astype(np.float32), hi=1600) * calm.astype(np.float32)
music += tense * float(db(-10)) + pulse * float(db(-3)) + pad * float(db(-10))
# dip to near-silence just before the yank lock and before the tide warning
for tdip in (yank_t - 0.05, B[9] - 0.05):
    a_, b_ = int((tdip - 0.3) * SR), int(tdip * SR)
    ramp_ = np.ones(N, np.float32)
    ramp_[max(0, a_):max(0, b_)] = 0.08
    music *= np.convolve(ramp_, np.ones(480) / 480, mode="same").astype(np.float32)
place(tone(73.4, 1.6, decay=1.8), E[9] - 0.2, -7, bus=music)
place(boom(0.9, 44), E[9] - 0.2, -6, bus=music)

# ------------------------------------------------------------------ ambience: surf + gulls on every beach shot
beach_amb = surf(TOTAL)
xray_mask = np.zeros(N, np.float32)
for a_, b_ in ((B[2], B[5]), (B[6], B[8])):
    xray_mask[int(a_ * SR):int(b_ * SR)] = 1.0
xray_mask = np.convolve(xray_mask, np.ones(240) / 240, mode="same").astype(np.float32)
mix[: len(beach_amb)] += beach_amb[:N] * float(db(-20)) * (1 - xray_mask[: len(beach_amb)])
for tg in (0.6, B[1] + 0.9, B[8] + 0.5, B[9] + 1.2):
    place(gull(), tg, -26)

# ------------------------------------------------------------------ per-beat SFX
# 1 hook: wet sucking churn as he flails, a panicked gasp
place(suction(0.7), B[0] + 0.05, -12)
place(gasp(), B[0] + 0.3, -16)
place(squelch(0.6), at_beat(0, 0.6), -15)
# 2 sinks to the waist then stops dead: slow slurp, a soft thud as it holds
place(suction(0.9), B[1] + 0.1, -11)
place(boom(0.4, 60), B[1] + 1.05, -14)
# 3 cut into the X-ray: whoosh in, a buoyant low swell as the leg floats up
place(whoosh(0.45), B[2] - 0.05, -10)
place(fft_filter(noise(0.8), hi=300) * env_ar(int(0.8 * SR), 0.3, 0.4), B[2] + 0.3, -18)
# 4 the trap: grains packing in around the foot
place(grind(B[4] - B[3]), B[3] + 0.2, -15)
# 5 MONEY MOMENT: strain build, then the lock: huge suction + sub boom, slowed (pitched-down tail)
place(grind(0.5), B[4] + 0.1, -13)
place(whoosh(0.4), yank_t - 0.4, -14)
place(fft_filter(suction(1.2), hi=500), yank_t - 0.02, -6)
place(boom(1.0, 38), yank_t, -6)
place(crack(0.4), yank_t + 0.03, -12)
# 6 rope: whoosh back out, a taut twang + strained grunt on every jerk
place(whoosh(0.35, rising=False), B[5] - 0.05, -14)
for f_ in JERK_F:
    tj = at_beat(5, f_)
    place(twang(), tj, -10)
    place(fft_filter(noise(0.2), lo=200, hi=1200) * env_ar(int(0.2 * SR), 0.02, 0.12), tj + 0.04, -18)
# 7 slow circles: a gentle squelch on each turn
place(whoosh(0.4), B[6] - 0.05, -14)
k = B[6] + 0.3
while k < B[7] - 0.2:
    place(squish(0.35), k, -19)
    k += 1 / 0.75
# 8 water seeps in: trickle, grains loosening
place(trickle(B[8] - B[7]), B[7] + 0.05, -14)
place(grind(0.6), B[7] + 0.8, -21)
# 9 lean back and float: relieved exhale, soft release slurp, the warm pad (music bed)
place(whoosh(0.35, rising=False), B[8] - 0.05, -16)
place(fft_filter(noise(0.6), hi=600) * env_ar(int(0.6 * SR), 0.15, 0.35), B[8] + 0.2, -18)
place(suction(0.8), B[8] + 1.0, -17)
# 10 the tide: a wave washing in, the fast pulse returns (music bed)
place(wash(2.4), B[9] + 0.1, -10)
place(sting(0.9), at_beat(9, 0.5), -12)

# ------------------------------------------------------------------ sidechain duck + sum
fx = mix + music
venv = np.sqrt(np.convolve(voice ** 2, np.ones(int(0.03 * SR)) / int(0.03 * SR), mode="same"))
act = np.clip((20 * np.log10(venv + 1e-9) + 45) / 15, 0, 1).astype(np.float32)
hold = np.zeros_like(act)
level = 0.0
decay = np.exp(-64 / (0.25 * SR))
for i in range(0, N, 64):
    level = max(float(act[i:i + 64].max(initial=0)), level * decay)
    hold[i:i + 64] = level
fx_n = fx / (np.abs(fx).max() + 1e-9)
out = fx_n * float(db(-12)) * db(-9 * hold).astype(np.float32) + voice
peak = float(np.abs(out).max())
out = out / peak * float(db(-1.0))
sf.write(OUT, out.astype(np.float32), SR)
print("MIX", OUT, round(N / SR, 2), "s  beats", [round(b, 2) for b in B], "peak", round(peak, 3))
