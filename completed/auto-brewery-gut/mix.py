"""Sound design + mix for "auto-brewery-gut" (numpy + soundfile only).

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
BLOW_F = 0.05                  # beat 2 (0-indexed 1): he starts blowing into the breathalyzer
READ_F = (0.50, 0.85)          # beat 2: the display counts up to 0.41 between these fractions
SLAP_F = 0.06                  # beat 3 (0-indexed 2): hands slap onto the car roof
DIVE_F = 0.50                  # beat 4 (0-indexed 3): cut from the X-ray body into the gut
GULP_F = (0.70, 0.84)          # beat 6 (0-indexed 5): he gulps the glucose drink
SLO_B_F = 0.62                 # beat 7 (0-indexed 6): the slow-mo window is [B[6], this fraction]
HIT_F = 0.35                   # fraction of that window where the sugar lands on the yeast
DRUG_F = 0.45                  # beat 8 (0-indexed 7): cut to the gut as the antifungal arrives
BREW_F = 0.42                  # beat 10 (0-indexed 9): BreweryX -> Closer
SMILE_F = 0.55                 # beat 10: his relieved smile


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
BLOW = at_beat(1, BLOW_F)
READ_A, READ_B = at_beat(1, READ_F[0]), at_beat(1, READ_F[1])
SLAP = at_beat(2, SLAP_F)
DIVE = at_beat(3, DIVE_F)
SLO_A, SLO_B = B[6], at_beat(6, SLO_B_F)
HIT = SLO_A + HIT_F * (SLO_B - SLO_A)
DRUG = at_beat(7, DRUG_F)
BREW = at_beat(9, BREW_F)
SMILE = at_beat(9, SMILE_F)
SPANS = {"road": [(0.0, DIVE)], "xray": [(DIVE, B[5]), (SLO_A, SLO_B), (DRUG, B[8])],
         "hosp": [(B[5], SLO_A), (SLO_B, DRUG), (B[8], TOTAL)]}


def mask(name, fade=240):
    m = np.zeros(N, np.float32)
    for a_, b_ in SPANS[name]:
        m[int(a_ * SR):int(min(b_, TOTAL) * SR)] = 1.0
    return np.convolve(m, np.ones(fade) / fade, mode="same").astype(np.float32)


# ------------------------------------------------------------------ music bed: tense pulse -> sickly slow-mo -> warm relief
drone = (0.6 * np.sin(2 * np.pi * 49 * t) + 0.3 * np.sin(2 * np.pi * 73.4 * t + 1.0)
         + 0.15 * np.sin(2 * np.pi * 98 * t)) * (0.7 + 0.3 * np.sin(2 * np.pi * 0.25 * t))
relief = np.clip((t - (DRUG + 0.4)) / 1.0, 0, 1)
tense = drone.astype(np.float32) * (1 - relief).astype(np.float32)
pulse = np.zeros(N, np.float32)
k = 0.0
while k < DRUG:
    if not (SLO_A - 0.1 < k < SLO_B):
        place(fft_filter(boom(0.3, 46), hi=180), k, -6, bus=pulse)
    k += 60 / (112 if k < B[3] else 100)
pad = sum(np.sin(2 * np.pi * f * t + i) / (i + 1) for i, f in enumerate((196.0, 246.9, 293.7, 392.0)))
pad = fft_filter(pad.astype(np.float32), hi=1600) * relief.astype(np.float32)
music += tense * float(db(-10)) + pulse * float(db(-3)) + pad * float(db(-9))
# a breath of near-silence just before the sugar lands
a_, b_ = int((HIT - 0.35) * SR), int((HIT - 0.02) * SR)
dip = np.ones(N, np.float32)
dip[max(0, a_):max(0, b_)] = 0.1
music *= np.convolve(dip, np.ones(480) / 480, mode="same").astype(np.float32)
place(tone(98.0, 1.6, decay=1.8), E[9] - 0.2, -8, bus=music)

# ------------------------------------------------------------------ ambience per set
road_m, xray_m, hosp_m = mask("road"), mask("xray"), mask("hosp")
def fit(x):
    out = np.zeros(N, np.float32)
    out[: min(N, len(x))] = x[:N]
    return out


amb = fit(crickets(TOTAL)) * float(db(-21)) * road_m
amb += fit(hum(TOTAL)) * float(db(-26)) * road_m                        # idling engines
amb += fit(gurgle(TOTAL)) * float(db(-17)) * xray_m
amb += fit(fft_filter(noise(TOTAL), lo=80, hi=600)) * float(db(-30)) * hosp_m   # room tone
mix[: len(amb)] += amb
k = B[5] + 0.2
while k < TOTAL - 0.3:                                                 # the ward's vitals monitor
    i0 = int(k * SR)
    if hosp_m[min(i0, N - 1)] > 0.5:
        place(monitor_beep(), k, -24)
    k += 0.95 if k < B[8] else 1.05

# ------------------------------------------------------------------ per-beat SFX
# 1 hook: a siren whoop and the police radio
place(siren_whoop(0.9), 0.02, -12)
place(radio(0.9), at_beat(0, 0.55), -18)
# 2 the breathalyzer: a long blow, the counter ticking up, a triple alarm beep on 0.41
place(blow(READ_A - BLOW + 0.2), BLOW, -14)
k = READ_A
while k < READ_B:
    place(beep() * 0.5, k, -24)
    k += 0.07
for j in range(3):
    place(fft_filter(beep(), lo=600), READ_B + 0.16 * j, -12)
place(sting(0.8), READ_B, -16)
# 3 hands slap the roof; the radio crackles; a tense swallow
place(boom(0.35, 70), SLAP, -9)
place(fft_filter(noise(0.12), lo=600, hi=4000) * env_ar(int(0.12 * SR), 0.003, 0.08), SLAP, -14)
place(radio(1.0), at_beat(2, 0.40), -19)
# 4 X-ray reveal (hum), then the plunge into the gut
place(whoosh(0.45), B[3] - 0.05, -11)
place(hum(1.4) * env_ar(int(1.4 * SR), 0.1, 0.4), B[3], -16)
place(whoosh(0.4), DIVE - 0.35, -10)
place(squelch(0.5), DIVE + 0.05, -16)
# 5 the yeast brewing: fizz and bubbling pops
place(fizz(B[5] - B[4], lo=2000), B[4], -19)
k = B[4] + 0.15
while k < B[5] - 0.2:                                                  # bubbles bursting off the yeast
    place(pop(0.2), k + 0.1 * rng.random(), -20)
    k += 0.23
# 6 hospital: two gulps of the glucose drink
place(whoosh(0.35, rising=False), B[5] - 0.05, -16)
for f_ in GULP_F:
    place(gulp(), at_beat(5, f_), -12)
# 7 MONEY MOMENT: riser into the gut, the sugar hits (sub boom), a slowed fizz eruption; then the woozy drone
place(whoosh(0.5), SLO_A - 0.4, -12)
place(fft_filter(sting(0.6), hi=1200), HIT - 0.6, -16)
place(boom(1.1, 36), HIT, -5)
place(fft_filter(fizz(1.6, lo=600), hi=2500), HIT + 0.02, -9)
place(crack(0.4), HIT + 0.03, -14)
place(whoosh(0.35, rising=False), SLO_B - 0.05, -14)
place(woozy(1.5), SLO_B + 0.05, -14)
# 8 the IV drip, then the yeast powers down
k = B[7] + 0.1
while k < DRUG - 0.1:
    place(tone(1900, 0.06, decay=60), k, -18)
    k += 0.55
place(whoosh(0.4), DRUG - 0.3, -12)
place(power_down(1.0), DRUG + 0.5, -12)
# 9-10 relief: a soft swell into the X-ray gut glow, a warm chime on the smile
place(whoosh(0.35, rising=False), B[8] - 0.05, -17)
place(whoosh(0.4), B[9] - 0.05, -15)
place(fizz(0.9, lo=3000), B[9] + 0.2, -24)
place(chime(), SMILE, -13)

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
