"""Sound design + mix for "mirror-organs-99" (numpy + soundfile only).

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
rng = np.random.default_rng(23)

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

# SYNC with scene.py (0-indexed beats)
SWIM_F = 0.50                  # beat 2: "loved swimming" -> her swimming stroke
LAB_F = 0.50                   # beat 3: cut from home to the anatomy lab
VESSEL_F = 0.45                # beat 5: HeartOrbit -> VesselMacro
WRONG_F = 0.62                 # beat 5: the vessels flash amber
SLO_B_F = 0.62                 # beat 6: the slow-mo window is [B[5], this fraction]
HIT_F = 0.45                   # fraction of that window where the liver and stomach cross
HOMEX_F = 0.50                 # beat 7: HeartBeat -> BodyXFull (home, X-ray)
GRID_F = 0.50                  # beat 8: GridRise -> OneAmber
AMBER_F = 0.55                 # beat 8: the one amber dot lights up
HEART2_F = 0.50                # beat 9: HeartPulse -> HomeOrbit
CLOSER_F = 0.42                # beat 10: LabLamp -> Closer


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
# ------------------------------------------------------------------ extra synth: night road, gut, hospital
def crickets(sec):
    """Night ambience: soft low wind plus pulsing cricket chirps."""
    n = int(sec * SR)
    tt = np.arange(n) / SR
    wind = fft_filter(noise(sec), lo=60, hi=500) * (0.6 + 0.4 * np.sin(2 * np.pi * tt / 7.0))
    chirps = np.sin(2 * np.pi * 4300 * tt) * (np.sin(2 * np.pi * 28 * tt) > 0.3) * (np.sin(2 * np.pi * 0.9 * tt) > 0.2)
    return norm(wind + 0.25 * chirps.astype(np.float32))


def siren_whoop(sec=0.9):
    """A police 'whoop': a fast rising then falling sweep with harmonics."""
    tt = np.arange(int(sec * SR)) / SR
    f = 500 + 900 * np.sin(np.pi * np.clip(tt / sec, 0, 1)) ** 1.5
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph) + 0.4 * np.sin(2 * ph) + 0.2 * np.sin(3 * ph)
    return norm(s * env_ar(len(tt), 0.02, 0.25))


def radio(sec=0.8):
    """Police radio: a squelch click, then band-limited babble."""
    n = int(sec * SR)
    tt = np.arange(n) / SR
    babble = fft_filter(noise(sec), lo=500, hi=2600) * (0.5 + 0.5 * np.sin(2 * np.pi * np.cumsum(5 + 6 * rng.random(n)) / SR))
    s = babble * env_ar(n, 0.01, 0.1)
    click = fft_filter(noise(0.04), lo=2000, hi=8000) * env_ar(int(0.04 * SR), 0.001, 0.03)
    s[: len(click)] += click
    s[-len(click):] += click
    return norm(s)


def blow(sec=1.0):
    """A long breath into the mouthpiece."""
    n = int(sec * SR)
    return norm(fft_filter(noise(sec), lo=300, hi=3500) * env_ar(n, 0.12, 0.25))


def gurgle(sec):
    """Gut ambience: low wet rumbles with random bubbly blips."""
    n = int(sec * SR)
    tt = np.arange(n) / SR
    base = fft_filter(noise(sec), lo=40, hi=400) * (0.5 + 0.5 * np.sin(2 * np.pi * tt / 1.7) * np.sin(2 * np.pi * tt / 2.9))
    blips = np.zeros(n, np.float32)
    for _ in range(int(sec * 5)):
        i = int(rng.random() * (n - 4000))
        f = rng.uniform(180, 500)
        blips[i:i + 3200] += tone(f, 3200 / SR, decay=25) * 0.5
    return norm(base + blips)


def fizz(sec, lo=2500):
    """Carbonated fizz: dense tiny pops."""
    n = int(sec * SR)
    c = (rng.random(n) < 0.05).astype(np.float32) * rng.uniform(0.2, 1, n).astype(np.float32)
    c = np.convolve(c, np.exp(-np.arange(60) / 6), mode="same")
    return norm(fft_filter(c, lo=lo, hi=11000) * env_ar(n, 0.05, 0.2))


def gulp():
    s = boom(0.18, 110) + 0.5 * squish(0.18)
    return norm(s)


def monitor_beep():
    return (tone(880, 0.12) * env_ar(int(0.12 * SR), 0.005, 0.05)).astype(np.float32)


def woozy(sec=1.4):
    """Detuned, wobbling drone for the 'drunk' moment."""
    tt = np.arange(int(sec * SR)) / SR
    f = 220 * (1 + 0.04 * np.sin(2 * np.pi * 1.3 * tt))
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) + np.sin(2 * np.pi * np.cumsum(f * 1.012) / SR)
    return norm(s * env_ar(len(tt), 0.2, 0.5))


def power_down(sec=0.9):
    tt = np.arange(int(sec * SR)) / SR
    f = 600 * np.exp(-tt * 3.0) + 40
    return norm(np.sin(2 * np.pi * np.cumsum(f) / SR) * env_ar(len(tt), 0.01, 0.4))


# ------------------------------------------------------------------ timeline (mirrors scene.py SHOTS)
t = np.arange(N) / SR
NARR = TOTAL - TAIL
SWIM = at_beat(1, SWIM_F)
LAB = at_beat(2, LAB_F)
VESSEL = at_beat(4, VESSEL_F)
WRONG = at_beat(4, WRONG_F)
SLO_A, SLO_B = B[5], at_beat(5, SLO_B_F)
HIT = SLO_A + HIT_F * (SLO_B - SLO_A)
HOMEX = at_beat(6, HOMEX_F)
AMBER = at_beat(7, AMBER_F)
GRIDB = at_beat(7, GRID_F)
HEART2 = at_beat(8, HEART2_F)
CLOSER = at_beat(9, CLOSER_F)
SPANS = {"home": [(0.0, LAB), (HOMEX, B[7]), (HEART2, B[9]), (CLOSER, TOTAL)],
         "lab": [(LAB, B[4]), (B[9], CLOSER)],
         "organ": [(B[4], HOMEX), (B[8], HEART2)],
         "grid": [(B[7], B[8])]}


def mask(name, fade=240):
    m = np.zeros(N, np.float32)
    for a_, b_ in SPANS[name]:
        m[int(a_ * SR):int(min(b_, TOTAL) * SR)] = 1.0
    return np.convolve(m, np.ones(fade) / fade, mode="same").astype(np.float32)


def fit(x):
    out = np.zeros(N, np.float32)
    out[: min(N, len(x))] = x[:N]
    return out


home_m, lab_m, organ_m, grid_m = mask("home"), mask("lab"), mask("organ"), mask("grid")

# ------------------------------------------------------------------ music: warm wistful pad -> mystery -> sickly slow-mo -> wonder
def chord(freqs, gain=1.0):
    s = sum(np.sin(2 * np.pi * f * t + i) / (i + 1) for i, f in enumerate(freqs))
    return fft_filter(s.astype(np.float32), hi=1800) * gain


def smoothstep(x):
    x = np.clip(x, 0, 1)
    return (x * x * (3 - 2 * x)).astype(np.float32)


warm = chord((196.0, 246.9, 293.7, 392.0)) * (1 - smoothstep((t - B[4]) / 0.8))
mystery = chord((146.8, 207.7, 293.7)) * smoothstep((t - B[4]) / 0.8) * (1 - smoothstep((t - B[6]) / 0.8))
wonder = chord((220.0, 277.2, 329.6, 440.0, 554.4)) * smoothstep((t - B[6]) / 1.2)
swell = 0.7 + 0.3 * np.sin(2 * np.pi * t / 6.0)
music += (warm * 0.7 + mystery * 0.8 + wonder * 0.8) * swell.astype(np.float32) * float(db(-11))
sub = np.sin(2 * np.pi * 55 * t) * smoothstep((t - B[4]) / 0.6) * (1 - smoothstep((t - B[6]) / 0.6))
music += sub.astype(np.float32) * float(db(-17))
a_, b_ = int((HIT - 0.35) * SR), int((HIT - 0.02) * SR)
dip = np.ones(N, np.float32)
dip[max(0, a_):max(0, b_)] = 0.1                                      # a breath of near-silence before the swap
music *= np.convolve(dip, np.ones(480) / 480, mode="same").astype(np.float32)
place(tone(110.0, 1.8, decay=1.6), E[9] - 0.25, -9, bus=music)

# ------------------------------------------------------------------ ambience per set
amb = fit(fft_filter(noise(TOTAL), lo=90, hi=700)) * float(db(-31)) * home_m           # sunny room tone
amb += fit(hum(TOTAL)) * float(db(-27)) * lab_m                                         # lab ventilation
amb += fit(fft_filter(noise(TOTAL), lo=120, hi=900)) * float(db(-33)) * lab_m
amb += fit(gurgle(TOTAL)) * float(db(-24)) * organ_m
amb += fit(fizz(TOTAL, lo=5000)) * float(db(-31)) * grid_m                              # the dots shimmer
mix[: len(amb)] += amb
hb = fit(heartbeat(TOTAL, bpm=75)) * float(db(-9)) * organ_m                           # the heartbeat under every organ shot
mix[: len(hb)] += hb

# ------------------------------------------------------------------ per-beat SFX
# 1 hook: X-ray scan sweep on frame 1, a ping when the organs catch the light
place(whoosh(0.5), 0.0, -14)
place(fft_filter(hum(1.6) * env_ar(int(1.6 * SR), 0.1, 0.8), lo=70), 0.05, -17)
place(chime(), at_beat(0, 0.55), -22)
# 2 five photo frames tick by, then swimming strokes with splashes
for j in range(5):
    place(clink() * 0.6, B[1] + 0.25 + 0.34 * j, -22)
k = SWIM
while k < B[2] - 0.2:
    place(fft_filter(noise(0.5), lo=300, hi=3500) * env_ar(int(0.5 * SR), 0.1, 0.25), k + 0.15, -20)
    k += 0.95
# 3 "She died": one low soft note, then the cut to the lab (footstep thud, a sheet rustle)
place(tone(110.0, 2.0, decay=1.6), B[2] + 0.2, -14)
place(whoosh(0.4), LAB - 0.05, -13)
place(fft_filter(noise(0.6), lo=1000, hi=6000) * env_ar(int(0.6 * SR), 0.2, 0.3), LAB + 0.2, -26)
# 4 students: instruments clink on the tray, a skull-bench knock
place(clink(), B[3] + 0.25, -17)
place(clink(), B[3] + 0.85, -19)
place(clink(), B[3] + 1.5, -18)
place(creak(0.4), B[3] + 0.5, -26)
# 5 organ view: whoosh in, vessels flash amber (a sting + ping)
place(whoosh(0.45), B[4] - 0.05, -11)
place(whoosh(0.3), VESSEL - 0.05, -17)
place(fft_filter(sting(0.8), lo=300), WRONG - 0.05, -15)
place(chime(), WRONG, -19)
# 6 MONEY MOMENT: riser, the organs swap (sub boom, wet slides, a glassy swoosh), reverse whoosh out
place(whoosh(0.5), SLO_A - 0.4, -12)
place(fft_filter(sting(0.6), hi=1200), HIT - 0.55, -16)
place(boom(1.1, 38), HIT, -5)
place(squish(0.6) * env_ar(int(0.6 * SR), 0.1, 0.3), HIT - 0.25, -13)
place(squish(0.6) * env_ar(int(0.6 * SR), 0.1, 0.3), HIT - 0.05, -14)
place(crack(0.4), HIT + 0.03, -17)
place(chime(), HIT + 0.1, -16)
place(whoosh(0.35, rising=False), SLO_B - 0.05, -14)
# 7 the heart stays put: a firm thump, whoosh to the home X-ray with a warm hum
place(boom(0.4, 60), B[6] + 0.15, -9)
place(whoosh(0.4), HOMEX - 0.05, -12)
place(hum(1.4) * env_ar(int(1.4 * SR), 0.1, 0.4), HOMEX, -16)
# 8 one in 22,000: whoosh to the dots, shimmer, a rising tone and a bright chime on the amber dot
place(whoosh(0.45), B[7] - 0.05, -11)
place(fizz(B[8] - B[7], lo=4000), B[7], -24)
place(fft_filter(sting(1.0), lo=400), AMBER - 0.7, -14)
place(chime(), AMBER, -11)
# 9 heart pulse, then a warm cut back home
place(whoosh(0.35), B[8] - 0.05, -13)
place(boom(0.3, 62), B[8] + 0.3, -11)
place(whoosh(0.35, rising=False), HEART2 - 0.05, -17)
# 10 back to the lab, then the closer: a soft whoosh and a warm chime on the X-ray body
place(whoosh(0.4), B[9] - 0.05, -15)
place(whoosh(0.35), CLOSER - 0.05, -14)
place(chime(), at_beat(9, 0.70), -13)

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
