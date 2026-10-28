"""Sound design + mix for "cholesterol-through-skin" (numpy + soundfile only).

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
ERUPT_F = 0.45     # beat 9 (0-indexed 8): the plaque bursts through the vessel wall


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

# ------------------------------------------------------------------ music bed: quiet unease -> warm but unresolved
t = np.arange(N) / SR
drone = (0.6 * np.sin(2 * np.pi * 58 * t) + 0.3 * np.sin(2 * np.pi * 87 * t + 1.0)
         + 0.15 * np.sin(2 * np.pi * 116 * t)) * (0.7 + 0.3 * np.sin(2 * np.pi * 0.15 * t))
unease = drone.astype(np.float32)
pulse = np.zeros(N, np.float32)
k = B[6]
while k < at_beat(8, ERUPT_F) - 0.1:
    place(fft_filter(boom(0.3, 44), hi=180), k, -6, bus=pulse)
    k += 60 / (95 if k < B[7] else 105)
res = np.clip((t - B[9]) / 1.0, 0, 1).astype(np.float32)
pad = sum(np.sin(2 * np.pi * f * t + i) / (i + 1) for i, f in enumerate((261.6, 311.1, 392.0, 466.2)))
pad = fft_filter(pad.astype(np.float32), hi=1700) * res
music += unease * float(db(-10)) + pulse * float(db(-2)) + pad * float(db(-9))
# dip to near-silence before the vial reveal and before the eruption
for tdip in (B[6] - 0.05, at_beat(8, ERUPT_F) - 0.05):
    a_, b_ = int((tdip - 0.32) * SR), int(tdip * SR)
    ramp_ = np.ones(N, np.float32)
    ramp_[max(0, a_):max(0, b_)] = 0.08
    music *= np.convolve(ramp_, np.ones(480) / 480, mode="same").astype(np.float32)
# a single low, unresolved note under the very last words (no full resolve -- it's a warning)
place(tone(98.0, 1.4, decay=2.0), E[9] - 0.2, -7, bus=music)
place(boom(0.9, 46), E[9] - 0.2, -6, bus=music)

# ------------------------------------------------------------------ per-beat SFX
# 1 hook: wet squelch under the push-in, low sub-hum
place(squelch(0.5), B[0] + 0.05, -14)
place(hum(B[1] - B[0]), B[0], -22)
# 2 kitchen wide: room tone, chair creak, knife scrape
place(creak(0.4), B[1] + 0.1, -18)
place(knife(0.3), B[1] + 0.6, -16)
# 3 food insert: louder cheese cut, butter scrape, meat squish
place(knife(0.35), B[2] + 0.1, -10)
place(squish(0.3), B[2] + 0.7, -14)
place(knife(0.25), B[2] + 1.3, -15)
# 4 feels great: content exhale (low tone swell), soft chew
place(fft_filter(noise(0.4), hi=500) * 0.4, B[3] + 0.1, -20)
place(squish(0.2), B[3] + 0.5, -18)
# 5 palm shock: breath-catch + rising sting near the line's end
place(fft_filter(noise(0.12), lo=1200) * np.exp(-np.arange(int(0.12 * SR)) / 140), B[4] + 0.05, -14)
place(sting(0.9), at_beat(4, 0.55), -10)
# 6 vial insert: glass clink, uneasy drone swell (handled in music bed)
place(clink(), B[5] + 0.1, -11)
place(fft_filter(noise(0.5), lo=300, hi=2500) * env_ar(int(0.5 * SR), 0.15, 0.3), B[5] + 0.3, -18)
# 7 plunge into the vessel: whoosh in, heartbeat starts (bpm ~95)
place(whoosh(0.45), B[6] - 0.05, -10)
place(heartbeat(B[7] - B[6], bpm=95), B[6], -16)
# 8 plaque orbit: heartbeat continues faster (bpm ~105), building crackle
place(heartbeat(B[8] - B[7], bpm=105), B[7], -15)
place(crack(0.3), B[7] + (B[8] - B[7]) * 0.5, -16)
# 9 MONEY MOMENT: whoosh build, wet pop at the exact erupt frame, sub-boom, heartbeat cuts for the slomo window
erupt_t = at_beat(8, ERUPT_F)
place(whoosh(0.4), erupt_t - 0.35, -14)
place(pop(0.3), erupt_t, -6)
place(boom(0.8, 42), erupt_t + 0.02, -8)
place(squish(0.3), erupt_t + 0.15, -13)
# 10 closer: settle to resting heartbeat, warm chime, chair creak
place(heartbeat(B[9] - erupt_t - 0.3 if B[9] - erupt_t > 0.3 else 0.3, bpm=70), erupt_t + 0.3, -20)
place(chime(), B[9] + 0.1, -14)
place(creak(0.3), B[9] + 1.0, -20)
for dt in (0.2, 1.0, 1.8):
    place(chirp(), B[9] + dt, -28)

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
