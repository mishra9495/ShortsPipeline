"""Sound design + mix for the sneeze short (numpy only; 24 kHz mono, matching Kokoro).

Usage: tts-venv\\Scripts\\python.exe mix_sneeze.py <out.wav>
Narration is cleaned (high-pass, gentle compression); SFX are synthesized and placed on the
shot timeline (frame numbers match scene_sneeze.py, 30 fps). Final loudness is set later by
ffmpeg loudnorm when the video is muxed.
"""
import json
import sys

import numpy as np
import soundfile as sf

SR = 24000
FPS = 30
A = r"D:\ShortsPipeline\audio"
OUT = sys.argv[1]
rng = np.random.default_rng(5)

vo, sr = sf.read(A + r"\vo_sneeze.wav", dtype="float32")
assert sr == SR
meta = json.load(open(A + r"\vo_sneeze.json"))
END_FRAME = int(round(meta["duration"] * FPS)) + 1 + 36
N = int(END_FRAME / FPS * SR) + SR // 2
mix = np.zeros(N, np.float32)

# Every spot-effect frame below was originally hand-placed against the Kokoro narration's
# beat timing. rmap() re-times each one for whatever narration is actually loaded (see the
# matching function/comment in scene_sneeze.py).
BEAT = [int(round(b["start"] * FPS)) + 1 for b in meta["beats"]]
END = END_FRAME
OLD_BEAT = [1, 110, 180, 265, 301, 487, 558, 673, 788, 919]
OLD_END = 1053


def rmap(f):
    old_pts = OLD_BEAT + [OLD_END]
    new_pts = BEAT + [END]
    if f <= old_pts[0]:
        i = 0
    elif f >= old_pts[-1]:
        i = len(old_pts) - 2
    else:
        i = next(k for k in range(len(old_pts) - 1) if old_pts[k] <= f <= old_pts[k + 1])
    a, b, na, nb = old_pts[i], old_pts[i + 1], new_pts[i], new_pts[i + 1]
    t = 0.0 if b == a else (f - a) / (b - a)
    return na + t * (nb - na)


def t_of(frame):
    return (frame - 1) / FPS


def at(frame):
    return int(t_of(frame) * SR)


def fft_filter(x, lo=None, hi=None):
    """Brick-ish band filter with soft (1-octave cosine) edges, via FFT."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    g = np.ones_like(f)
    if lo:
        g *= np.clip(np.log2(np.maximum(f, 1) / (lo / 2)), 0, 1)
    if hi:
        g *= np.clip(np.log2((hi * 2) / np.maximum(f, 1)), 0, 1)
    return np.fft.irfft(X * g, len(x)).astype(np.float32)


def noise(sec):
    return rng.standard_normal(int(sec * SR)).astype(np.float32)


def brown(sec):
    w = noise(sec)
    b = np.cumsum(w)
    b -= np.convolve(b, np.ones(2400) / 2400, mode="same")  # remove drift
    return (b / (np.abs(b).max() + 1e-9)).astype(np.float32)


def env_adsr(n, a, r):
    e = np.ones(n, np.float32)
    na, nr = int(a * SR), int(r * SR)
    if na:
        e[:na] = np.linspace(0, 1, na)
    if nr:
        e[-nr:] *= np.linspace(1, 0, nr) ** 2
    return e


def place(sig, frame, gain, offset_sec=0.0):
    i = at(frame) + int(offset_sec * SR)
    j = max(0, i)
    s = sig[j - i:]
    s = s[: max(0, N - j)]
    mix[j:j + len(s)] += s * gain


def db(x):
    return 10 ** (x / 20)


def boom(sec=0.6, f0=55):
    t = np.arange(int(sec * SR)) / SR
    pitch = f0 * (1 + 0.8 * np.exp(-t * 18))
    s = np.sin(2 * np.pi * np.cumsum(pitch) / SR) * np.exp(-t * 7)
    return s.astype(np.float32)


def whoosh(sec=0.55, rising=True):
    n = int(sec * SR)
    out = np.zeros(n, np.float32)
    seg = 1024
    w = noise(sec + 0.1)
    for k in range(0, n, seg):
        x = k / n if rising else 1 - k / n
        c = 300 + 3500 * x ** 2
        chunk = fft_filter(w[k:k + seg * 2], lo=c * 0.6, hi=c * 1.6)[:seg]
        out[k:k + len(chunk)] = chunk[: n - k]
    e = np.sin(np.linspace(0, np.pi, n)) ** 1.5
    return out * e / (np.abs(out).max() + 1e-9)


def rip(sec=0.4):
    n = int(sec * SR)
    w = fft_filter(noise(sec), lo=900, hi=9000)
    crack = (rng.random(n) < 0.004).astype(np.float32) * rng.uniform(0.5, 1, n)
    crack = np.convolve(crack, np.exp(-np.arange(200) / 25), mode="same")
    e = np.exp(-np.arange(n) / (0.12 * SR)) * env_adsr(n, 0.004, 0.05)
    s = (0.7 * w / np.abs(w).max() + 0.6 * fft_filter(crack, lo=1500)) * e
    return (s / np.abs(s).max()).astype(np.float32)


def crackle(sec, rate):
    n = int(sec * SR)
    s = np.zeros(n, np.float32)
    for _ in range(int(sec * rate)):
        i = rng.integers(0, n - 400)
        L = rng.integers(60, 300)
        s[i:i + L] += rng.uniform(0.3, 1.0) * rng.standard_normal(L) * np.exp(-np.arange(L) / (L / 4))
    return fft_filter(s, lo=1200, hi=10000)


def heartbeat(sec, bpm=72):
    s = np.zeros(int(sec * SR), np.float32)
    beat = boom(0.25, 48)
    period = 60 / bpm
    t = 0.0
    while t < sec - 0.5:
        for off, g in ((0, 1.0), (0.28, 0.6)):
            i = int((t + off) * SR)
            s[i:i + len(beat)] += beat[: len(s) - i] * g
        t += period
    return s


# --------------------------------------------------------------- narration cleanup
vo = fft_filter(vo, lo=75)
# gentle RMS compression (2:1 above -24 dBFS), 20 ms window
win = int(0.02 * SR)
rms = np.sqrt(np.convolve(vo ** 2, np.ones(win) / win, mode="same") + 1e-12)
lvl = 20 * np.log10(rms)
gain_db = np.where(lvl > -24, -(lvl + 24) * 0.5, 0.0)
gain_db = np.convolve(gain_db, np.ones(win) / win, mode="same")
vo = vo * db(gain_db).astype(np.float32)
vo /= np.abs(vo).max()
voice = np.zeros(N, np.float32)
voice[: len(vo)] = vo * db(-3)

# --------------------------------------------------------------- beds
XRAY = [(rmap(54), BEAT[1] - 1), (BEAT[4], BEAT[6] - 1), (BEAT[7], rmap(865))]
car_bed = fft_filter(brown(N / SR + 0.1)[:N], hi=320) * 1.0
tire = fft_filter(noise(N / SR + 0.1)[:N], lo=90, hi=600)
car_bed = car_bed / np.abs(car_bed).max() * 0.8 + tire / np.abs(tire).max() * 0.25
t = np.arange(N) / SR
drone = (0.6 * np.sin(2 * np.pi * 55 * t) + 0.3 * np.sin(2 * np.pi * 82.5 * t + 1)) * (0.7 + 0.3 * np.sin(2 * np.pi * 0.2 * t))
drone = drone.astype(np.float32) + heartbeat(N / SR) * 0.9
mask = np.zeros(N, np.float32)
for a, b in XRAY:
    mask[at(a):at(b + 1)] = 1
fade = int(0.04 * SR)
mask = np.convolve(mask, np.ones(fade) / fade, mode="same")
mix += car_bed * (1 - mask) * db(-27) + drone * mask * db(-26)

# --------------------------------------------------------------- spot effects
for a, b in XRAY:
    place(whoosh(0.5, True), a, db(-14), offset_sec=-0.38)
    place(whoosh(0.4, False), b + 1, db(-20), offset_sec=-0.1)

mmph, _ = sf.read(A + r"\sfx_mmph.wav", dtype="float32")
mmph = fft_filter(mmph, hi=900)  # mouth clamped shut -> muffled
for jf in (rmap(26), BEAT[3] + 8):
    place(boom(0.7, 50), jf, db(-10))
    place(mmph / np.abs(mmph).max(), jf, db(-12), offset_sec=-0.12)

# pressure build: rising rumble + rising tone from 330 to the tear
TEAR_F, TEAR_HOOK_F = BEAT[5] + 10, rmap(62)
n = at(TEAR_F) - at(rmap(330))
tt = np.arange(n) / SR
ramp_ = (tt / tt[-1]) ** 2
tone = np.sin(2 * np.pi * np.cumsum(70 + 160 * ramp_) / SR) * ramp_
rum = fft_filter(brown(n / SR + 0.1)[:n], hi=200) * ramp_
place((tone * 0.5 + rum / np.abs(rum).max() * 0.8).astype(np.float32), rmap(330), db(-13))
# hook pressure (shorter)
n2 = at(TEAR_HOOK_F) - at(rmap(40))
r2 = (np.arange(n2) / n2) ** 2
place((np.sin(2 * np.pi * np.cumsum(90 + 140 * r2) / SR) * r2).astype(np.float32), rmap(40), db(-16))

for tf in (TEAR_HOOK_F, TEAR_F):
    place(rip(0.45), tf, db(-8))
    place(boom(0.5, 70), tf, db(-12))
    place(fft_filter(noise(0.6), lo=2000, hi=8000) * env_adsr(int(0.6 * SR), 0.01, 0.4), tf, db(-24))  # air hiss out

place(crackle(1.9, 30), rmap(690), db(-11))     # "it crackled"
place(crackle(6.0, 3), rmap(510), db(-22))      # bubbles slowly spreading
# healing shimmer
n = int(2.0 * SR)
tt = np.arange(n) / SR
shim = sum(np.sin(2 * np.pi * f * tt) for f in (523, 659, 784)) * np.sin(np.pi * tt / 2.0) ** 2
place((shim / 3).astype(np.float32), rmap(800), db(-28))
# wheel/indicator-free car: a couple of tyre thumps over road seams for realism
for f in (rmap(150), rmap(420), rmap(905)):
    place(fft_filter(boom(0.2, 80), hi=300), f, db(-26))

# final sneeze: align the loudest burst ("CHOO") with frame 978
achoo, _ = sf.read(A + r"\sfx_achoo.wav", dtype="float32")
e = np.sqrt(np.convolve(achoo ** 2, np.ones(480) / 480, mode="same"))
thr = 0.5 * e.max()
peak = int(np.argmax(e))
onset = peak
while onset > 0 and e[onset] > thr * 0.5:
    onset -= 1
place(achoo / np.abs(achoo).max(), rmap(978), db(-6), offset_sec=-onset / SR)
place(fft_filter(noise(0.35), lo=1500, hi=9000) * env_adsr(int(0.35 * SR), 0.005, 0.3), rmap(978), db(-22))  # spray hiss
print("ACHOO_onset_sec", round(onset / SR, 3), "of", round(len(achoo) / SR, 2))

# sidechain duck: effects drop up to 9 dB while the narrator is talking (fast attack, 250 ms release)
venv = np.sqrt(np.convolve(voice ** 2, np.ones(int(0.03 * SR)) / int(0.03 * SR), mode="same"))
rel = int(0.25 * SR)
act =np.clip((20 * np.log10(venv + 1e-9) + 45) / 15, 0, 1).astype(np.float32)
hold = np.zeros_like(act)
level = 0.0
decay = np.exp(-1 / rel)
for i in range(0, N, 64):                    # block-wise peak-hold with exponential release
    level = max(float(act[i:i + 64].max(initial=0)), level * decay ** 64)
    hold[i:i + 64] = level
mix = mix * db(-9 * hold) + voice
peak = np.abs(mix).max()
mix = mix / peak * db(-1.0)
sf.write(OUT, mix, SR)
print("MIX", OUT, round(N / SR, 2), "s, pre-normalize peak", round(float(peak), 3))
