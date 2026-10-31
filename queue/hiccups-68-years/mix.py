"""Sound design + mix for "hiccups-68-years" (numpy + soundfile only).

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

# SYNC with scene.py (fractions of the beat they live in; beat indexes are 0-based)
SLIP_F, IMP_F = 0.36, 0.52     # beat 3: he slips, then hits the barn floor
HIC1_F = 0.78                  # beat 3: the first hiccup
HIC_GAP = 1.5                  # seconds between hiccups
HIC_END_F = 0.40               # beat 9: the last hiccup (1990)
BURST_F = 0.66                 # beat 4: the vessel in his brain bursts
DAM_F, DEAD_F = 0.30, 0.62     # beat 5: the off switch is damaged, then dead
SLO_B_F = 0.66                 # beat 6: slow-mo window is [B[5], this fraction]
HIT_F = 0.42                   # fraction of that window where the hiccup lands
TALLY_B_F = 0.55               # beat 7: the dots finish popping
RELIEF_F = 0.55
SMILE_F = 0.50                 # beat 10: his calm smile
SET_CUTS = ()


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


# ------------------------------------------------------------------ extra synth: barn, hiccups, chest, brain
def gurgle(sec):
    """Chest ambience: low wet rumbles with soft bubbly blips."""
    n = int(sec * SR)
    tt = np.arange(n) / SR
    base = fft_filter(noise(sec), lo=40, hi=400) * (0.5 + 0.5 * np.sin(2 * np.pi * tt / 1.7) * np.sin(2 * np.pi * tt / 2.9))
    blips = np.zeros(n, np.float32)
    for _ in range(int(sec * 3)):
        i = int(rng.random() * (n - 4000))
        blips[i:i + 3200] += tone(rng.uniform(180, 500), 3200 / SR, decay=25) * 0.4
    return norm(base + blips)


def power_down(sec=0.9):
    tt = np.arange(int(sec * SR)) / SR
    f = 600 * np.exp(-tt * 3.0) + 40
    return norm(np.sin(2 * np.pi * np.cumsum(f) / SR) * env_ar(len(tt), 0.01, 0.4))


def hic(sec=0.16):
    """A hiccup: a sharp glottal click on top of a short, rasping inhale."""
    n = int(sec * SR)
    tt = np.arange(n) / SR
    f = 520 * np.exp(-tt * 14) + 180
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 20)
    rasp = fft_filter(noise(sec), lo=400, hi=2500) * np.exp(-tt * 18)
    click = np.zeros(n, np.float32)
    k = int(0.02 * SR)
    click[:k] = fft_filter(noise(0.02), lo=1500, hi=7000) * np.linspace(1, 0, k)
    return norm(0.55 * body + 0.4 * rasp + 0.7 * click)


def grunt(sec=0.45):
    """A hog's low grunt."""
    tt = np.arange(int(sec * SR)) / SR
    f = 95 + 25 * np.sin(2 * np.pi * 6 * tt) - 40 * tt
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.6 * np.sin(2 * np.pi * np.cumsum(2 * f) / SR)
    s = s * (0.7 + 0.3 * fft_filter(noise(sec), lo=40, hi=200))
    return norm(fft_filter(s.astype(np.float32), hi=900) * env_ar(len(tt), 0.05, 0.25))


def strain(sec=0.8):
    """A man's effort: a low breathy groan."""
    tt = np.arange(int(sec * SR)) / SR
    f = 120 + 18 * np.sin(2 * np.pi * 5 * tt) + 40 * tt
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.5 + 0.5 * fft_filter(noise(sec), lo=200, hi=1400)
    return norm(s * env_ar(len(tt), 0.25, 0.3))


def thud(sec=0.5):
    return norm(boom(sec, 62) + 0.4 * fft_filter(noise(sec), lo=60, hi=500) * env_ar(int(sec * SR), 0.003, 0.3))


def wind(sec):
    n = int(sec * SR)
    tt = np.arange(n) / SR
    return norm(fft_filter(noise(sec), lo=70, hi=700) * (0.6 + 0.4 * np.sin(2 * np.pi * tt / 6.0)))


def rustle(sec=0.5):
    n = int(sec * SR)
    c = (rng.random(n) < 0.03).astype(np.float32) * rng.uniform(0.2, 1, n).astype(np.float32)
    return norm(fft_filter(c, lo=2000, hi=9000) * env_ar(n, 0.05, 0.3))


def creak(sec=0.5):
    tt = np.arange(int(sec * SR)) / SR
    f = 160 + 40 * np.sin(2 * np.pi * 3.5 * tt)
    return norm((np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.4 + 0.6 * fft_filter(noise(sec), lo=150, hi=900)) * env_ar(len(tt), 0.08, 0.3))


def splash(sec=0.5):
    return norm(fft_filter(noise(sec), lo=300, hi=3500) * env_ar(int(sec * SR), 0.005, 0.4) + 0.5 * pop(sec))


def dying_tone(sec=1.8):
    """An amber pulse tone that falls out of tune and dies."""
    tt = np.arange(int(sec * SR)) / SR
    f = 440 * np.exp(-tt * 0.9) * (1 + 0.03 * np.sin(2 * np.pi * (4 + 6 * tt) * tt))
    return norm(np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 1.4) * env_ar(len(tt), 0.02, 0.5))


def breath(sec=1.6):
    n = int(sec * SR)
    return norm(fft_filter(noise(sec), lo=250, hi=2800) * np.sin(np.linspace(0, np.pi, n)) ** 1.5)


def shimmer(sec):
    tt = np.arange(int(sec * SR)) / SR
    s = sum(np.sin(2 * np.pi * f * tt + i) * (0.5 + 0.5 * np.sin(2 * np.pi * (0.3 + 0.1 * i) * tt)) for i, f in enumerate((1318.5, 1760.0, 2093.0, 2637.0)))
    return norm(s.astype(np.float32))


# ------------------------------------------------------------------ timeline (mirrors scene.py SHOTS)
t = np.arange(N) / SR
NARR = TOTAL - TAIL
SLIP, IMP = at_beat(2, SLIP_F), at_beat(2, IMP_F)
HIC1 = at_beat(2, HIC1_F)
HIC_END = at_beat(8, HIC_END_F)
HOOK = [0.30 + HIC_GAP * k for k in range(8) if 0.30 + HIC_GAP * k < B[1] - 0.2]
HICS = HOOK + [HIC1 + HIC_GAP * k for k in range(40) if HIC1 + HIC_GAP * k <= HIC_END + 1e-6]
BURST = at_beat(3, BURST_F)
DAM, DEAD = at_beat(4, DAM_F), at_beat(4, DEAD_F)
SLO_A, SLO_B = B[5], at_beat(5, SLO_B_F)
HIT = SLO_A + HIT_F * (SLO_B - SLO_A)
TALLY_A, TALLY_B = B[6], at_beat(6, TALLY_B_F)
RELIEF = at_beat(8, RELIEF_F)
SMILE = at_beat(9, SMILE_F)
CHEST_SH = [(SLO_A, B[6]), (at_beat(8, 0.5), B[9])]
SPANS = {"home": [(0.0, B[1]), (TALLY_B, at_beat(8, 0.5)), (B[9], TOTAL)],
         "barn": [(B[1], B[3])], "brain": [(B[3], B[5])], "chest": CHEST_SH, "tally": [(TALLY_A, TALLY_B)]}


def mask(name, fade=240):
    m = np.zeros(N, np.float32)
    for a_, b_ in SPANS[name]:
        m[int(a_ * SR):int(min(b_, TOTAL) * SR)] = 1.0
    return np.convolve(m, np.ones(fade) / fade, mode="same").astype(np.float32)


def fit(x):
    out = np.zeros(N, np.float32)
    out[: min(N, len(x))] = x[:N]
    return out


# ------------------------------------------------------------------ music: uneasy pad -> barn drone -> cold pulse -> relief
home_m, barn_m, brain_m, chest_m, tally_m = (mask(n) for n in ("home", "barn", "brain", "chest", "tally"))
relief = np.clip((t - (HIC_END + 0.3)) / 1.0, 0, 1).astype(np.float32)
drone = (0.6 * np.sin(2 * np.pi * 55 * t) + 0.3 * np.sin(2 * np.pi * 82.4 * t + 1.0) + 0.15 * np.sin(2 * np.pi * 110 * t)) * (0.7 + 0.3 * np.sin(2 * np.pi * 0.22 * t))
tense = drone.astype(np.float32) * (1 - relief)
pulse = np.zeros(N, np.float32)
k = B[3]
while k < HIC_END:
    if not (SLO_A - 0.1 < k < SLO_B):
        place(fft_filter(boom(0.3, 46), hi=180), k, -7, bus=pulse)
    k += 60 / 96
pad = sum(np.sin(2 * np.pi * f * t + i) / (i + 1) for i, f in enumerate((196.0, 246.9, 293.7, 392.0)))
pad = fft_filter(pad.astype(np.float32), hi=1600)
warm = pad * (0.25 + 0.75 * relief)
music += tense * float(db(-11)) + pulse * float(db(-4)) + warm * float(db(-12))
a_, b_ = int((HIT - 0.35) * SR), int((HIT - 0.02) * SR)                  # near-silence just before the snap
dip = np.ones(N, np.float32)
dip[max(0, a_):max(0, b_)] = 0.1
music *= np.convolve(dip, np.ones(480) / 480, mode="same").astype(np.float32)
place(tone(98.0, 1.6, decay=1.8), E[9] - 0.2, -8, bus=music)

# ------------------------------------------------------------------ ambience per set
amb = fit(fft_filter(noise(TOTAL), lo=80, hi=600)) * float(db(-30)) * home_m
amb += fit(wind(TOTAL)) * float(db(-20)) * barn_m
amb += fit(hum(TOTAL)) * float(db(-24)) * brain_m
amb += fit(gurgle(TOTAL)) * float(db(-18)) * chest_m
amb += fit(shimmer(TOTAL)) * float(db(-24)) * tally_m
mix[: len(amb)] += amb
# a heartbeat under the chest and brain shots
hb = fit(heartbeat(TOTAL, 72)) * (chest_m + 0.6 * brain_m)
mix[: len(hb)] += hb * float(db(-17))

# ------------------------------------------------------------------ the hiccups: every one is heard
for h in HICS:
    place(hic(), h, -9)
place(hic(0.2), HIT, -8)                                                     # the slow-motion hiccup (a lower, longer one)
# ------------------------------------------------------------------ per-beat SFX
# 1 hook: first hiccup is in HICS; a soft whoosh into the story
place(whoosh(0.4), 0.0, -22)
# 2 the barn: a hog grunt, hay rustle, a wood creak
place(whoosh(0.35), B[1] - 0.05, -12)
place(grunt(0.5), at_beat(1, 0.60), -14)
place(rustle(0.6), B[1] + 0.3, -22)
place(creak(0.5), B[1] + 0.8, -22)
# 3 the strain, the slip, the thud, the first hiccup
place(strain(0.9), B[2] + 0.05, -14)
place(rustle(0.4), SLIP - 0.05, -14)
place(whoosh(0.25, rising=False), SLIP, -16)
place(thud(0.6), IMP, -6)
place(rustle(0.5), IMP + 0.02, -16)
# 4 the brain: a cold whoosh in, then the vessel bursts
place(whoosh(0.4), B[3] - 0.05, -10)
place(hum(1.2) * env_ar(int(1.2 * SR), 0.1, 0.4), B[3] + 0.1, -18)
place(boom(0.5, 60), BURST, -8)
place(splash(0.6), BURST + 0.02, -13)
place(sting(0.8), BURST - 0.3, -20)
# 5 the amber off switch dies
place(whoosh(0.3), B[4] - 0.05, -13)
place(dying_tone(1.8), at_beat(4, 0.05), -15)
place(power_down(1.0), DEAD - 0.4, -14)
# 6 MONEY MOMENT: riser, the snap in slow motion, then the cords slam shut repeatedly
place(whoosh(0.5), SLO_A - 0.4, -11)
place(breath(1.2), HIT - 1.0, -17)
place(boom(1.0, 38), HIT, -5)
place(crack(0.35), HIT + 0.02, -12)
place(whoosh(0.35, rising=False), SLO_B - 0.05, -14)
# 7 the tally: a run of rising pops as the dots light up
k = TALLY_A + 0.15
while k < TALLY_B:
    place(pop(0.15) * 0.8, k, -22 + 8 * (k - TALLY_A) / (TALLY_B - TALLY_A))
    k += 0.045 + 0.05 * rng.random()
place(whoosh(0.5), TALLY_A - 0.05, -12)
place(whoosh(0.35, rising=False), TALLY_B - 0.1, -15)
# 8 family: a warm swell
place(whoosh(0.35), B[7] - 0.05, -17)
place(chime(), at_beat(7, 0.30), -17)
# 9 the last hiccup, silence, a relieved exhale, a chime
place(whoosh(0.35), at_beat(8, 0.50) - 0.05, -14)
place(breath(1.4), HIC_END + 0.5, -15)
place(chime(), RELIEF, -13)
# 10 close
place(whoosh(0.35, rising=False), B[9] - 0.05, -16)
place(chime(), SMILE, -14)

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
