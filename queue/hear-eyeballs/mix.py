"""Sound design + music + mix for "hear his own eyeballs" (numpy only, everything synthesized).

Usage: python mix.py <vo.json> <vo.wav> <out.wav>
Timings mirror scene.py (same shot plan derived from vo.json, 30 fps). All effects and the music
bed are generated here, so there is nothing to license. Output: 48 kHz stereo, peak -1 dBFS;
final loudness is set by ffmpeg loudnorm when the video is assembled.
"""
import json
import sys

import numpy as np
import soundfile as sf

VO_JSON, VO_WAV, OUT = sys.argv[1:4]
SR = 48000
FPS = 30
rng = np.random.default_rng(11)

meta = json.load(open(VO_JSON))
BEAT = [int(round(b["start"] * FPS)) + 1 for b in meta["beats"]]
END = int(round(meta["duration"] * FPS)) + 1 + 42
SH = {"bed_cu": 1, "xray_head": 31, "eye_a": BEAT[1], "sand": BEAT[1] + 22, "eye_b": BEAT[1] + 44,
      "xray_heart": BEAT[2], "chew": BEAT[2] + 30, "ct": BEAT[3], "xray_dive": BEAT[3] + 39,
      "ear_flow": BEAT[4], "or": BEAT[5], "seal": BEAT[5] + 30, "morning": BEAT[6]}
SACCADES = [13, 26, 42, SH["eye_a"] + 10, SH["eye_b"] + 9]
CHEWS = [SH["chew"] + 4 + 9 * i for i in range(4)]
HEARTBEATS = [SH["xray_heart"] + 2 + 13 * i for i in range(3)]
SEAL = SH["seal"] + 14

N = int((END - 1) / FPS * SR) + SR // 2
L = np.zeros(N, np.float32)
Rr = np.zeros(N, np.float32)


def at(frame):
    return int((frame - 1) / FPS * SR)


def db(x):
    return 10 ** (x / 20)


def place(sig, frame, gain=1.0, pan=0.0, offset=0.0):
    """Add mono sig at frame (pan -1..1, constant power)."""
    i = at(frame) + int(offset * SR)
    if i >= N:
        return
    s = sig[: max(0, N - i)] * gain
    if i < 0:
        s, i = s[-i:], 0
    a = (pan + 1) * np.pi / 4
    L[i:i + len(s)] += s * np.cos(a)
    Rr[i:i + len(s)] += s * np.sin(a)


def t(sec):
    return np.arange(int(sec * SR)) / SR


def noise(sec):
    return rng.standard_normal(int(sec * SR)).astype(np.float32)


def band(x, lo=None, hi=None):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    g = np.ones_like(f)
    if lo:
        g *= np.clip(np.log2(np.maximum(f, 1) / (lo / 2)), 0, 1)
    if hi:
        g *= np.clip(np.log2((hi * 2) / np.maximum(f, 1)), 0, 1)
    return np.fft.irfft(X * g, len(x)).astype(np.float32)


def env(n, a, d, shape=2.0):
    """attack a sec then decay to the end with curve shape."""
    e = np.ones(n, np.float32)
    na = max(1, int(a * SR))
    e[:na] = np.linspace(0, 1, na)
    rest = n - na
    if rest > 0:
        e[na:] = (1 - np.linspace(0, 1, rest)) ** shape
    return e * (1 if d else 1)


def norm(x):
    return (x / (np.abs(x).max() + 1e-9)).astype(np.float32)


# ---------------------------------------------------------------- effect generators
def scrape(sec=0.32, bright=1.0):
    """Sandpaper on wood: grainy band noise with stick-slip impulses."""
    n = int(sec * SR)
    x = band(noise(sec), 900 * bright, 7000 * bright)
    grains = (rng.random(n) < 90 / SR).astype(np.float32)
    grains = np.convolve(grains, np.hanning(int(0.006 * SR)), mode="same")
    am = 0.35 + 0.65 * np.clip(grains * 3, 0, 1)
    shape = np.sin(np.pi * np.linspace(0, 1, n)) ** 0.7
    return norm(x * am * shape)


def heartbeat():
    """Lub-dub, chest-deep, with sub thump."""
    out = np.zeros(int(0.7 * SR), np.float32)
    for off, f0, g in ((0.0, 62, 1.0), (0.17, 74, 0.7)):
        tt = t(0.22)
        f = f0 * (1 + 0.6 * np.exp(-tt * 30))
        s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 14)
        s += 0.3 * band(noise(0.22), 40, 220) * np.exp(-tt * 25)
        i = int(off * SR)
        out[i:i + len(s)] += g * s
    return norm(out)


def crunch():
    """Loud chew: dense crackle bursts + jaw thud."""
    sec = 0.28
    n = int(sec * SR)
    clicks = (rng.random(n) < 900 / SR).astype(np.float32) * rng.uniform(0.3, 1.0, n)
    clicks = band(clicks, 1200, 9000)
    body = band(noise(sec), 300, 2500) * 0.5
    e = env(n, 0.004, True, 2.5)
    tt = t(sec)
    thud = np.sin(2 * np.pi * 85 * tt) * np.exp(-tt * 30)
    return norm((clicks * 2 + body) * e + thud * 0.8)


def whoosh(sec=0.7, up=True, lo=300, hi=6000):
    n = int(sec * SR)
    x = noise(sec)
    out = np.zeros(n, np.float32)
    blocks = 24
    for b in range(blocks):
        a, z = b * n // blocks, (b + 1) * n // blocks
        u = b / (blocks - 1)
        c = lo * (hi / lo) ** (u if up else 1 - u)
        seg = band(x[max(0, a - 2048): z + 2048], c * 0.6, c * 1.6)
        out[a:z] = seg[(a - max(0, a - 2048)):(a - max(0, a - 2048)) + (z - a)]
    shape = np.sin(np.pi * np.linspace(0, 1, n) ** (0.6 if up else 1.4)) ** 1.5
    return norm(out * shape)


def boom(sec=1.8, f0=46):
    tt = t(sec)
    f = f0 * (1 + 1.2 * np.exp(-tt * 18))
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 3.2)
    s += 0.4 * band(noise(sec), 30, 400) * np.exp(-tt * 9)
    return norm(s)


def beep(f=1046, sec=0.14):
    tt = t(sec)
    return norm(np.sin(2 * np.pi * f * tt) * np.minimum(1, tt * 200) * np.minimum(1, (sec - tt) * 80))


def click(sec=0.06, lo=1800, hi=9000):
    tt = t(sec)
    return norm(band(noise(sec), lo, hi) * np.exp(-tt * 140) + 0.5 * np.sin(2 * np.pi * 2400 * tt) * np.exp(-tt * 90))


def chime(freqs=(1046.5, 1318.5, 1568.0, 2093.0), gap=0.07, sec=1.6):
    out = np.zeros(int((sec + gap * len(freqs)) * SR), np.float32)
    for k, f in enumerate(freqs):
        tt = t(sec)
        s = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(2 * np.pi * 2.01 * f * tt)) * np.exp(-tt * 3.0) * np.minimum(1, tt * 400)
        i = int(k * gap * SR)
        out[i:i + len(s)] += s
    return norm(out)


def shimmer(sec=2.0, base=880):
    tt = t(sec)
    s = sum(np.sin(2 * np.pi * base * r * tt + r) * (0.5 + 0.5 * np.sin(2 * np.pi * (5 + 3 * k) * tt))
            for k, r in enumerate((1, 1.5, 2, 2.5, 3)))
    return norm(s * np.sin(np.pi * tt / sec) ** 2)


def hum(sec, f0=60):
    tt = t(sec)
    s = np.sin(2 * np.pi * f0 * tt) + 0.5 * np.sin(2 * np.pi * 2 * f0 * tt) + 0.2 * np.sin(2 * np.pi * 3 * f0 * tt)
    s += 0.25 * band(noise(sec), 200, 1500)
    return norm(s)


def whir(sec, f_lo=180, f_hi=760):
    tt = t(sec)
    f = f_lo + (f_hi - f_lo) * np.clip(tt / (sec * 0.7), 0, 1) ** 1.5
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * (0.6 + 0.4 * np.sin(2 * np.pi * 9 * tt))
    s += 0.3 * np.sin(2 * np.pi * np.cumsum(2 * f) / SR)
    return norm(s * np.minimum(1, tt * 4))


def birds(sec):
    out = np.zeros(int(sec * SR), np.float32)
    k = 0.15
    while k < sec - 0.4:
        n_notes = rng.integers(2, 6)
        f = rng.uniform(2800, 5200)
        for j in range(n_notes):
            d = rng.uniform(0.04, 0.09)
            tt = t(d)
            sweep = f * (1 + rng.uniform(-0.25, 0.35) * tt / d)
            s = np.sin(2 * np.pi * np.cumsum(sweep) / SR) * np.sin(np.pi * tt / d) ** 2
            i = int((k + j * (d + 0.02)) * SR)
            if i + len(s) < len(out):
                out[i:i + len(s)] += s * rng.uniform(0.4, 1.0)
        k += rng.uniform(0.35, 0.9)
    return norm(out)


def muffle(x, hi=500):
    return band(x, None, hi)


def frames_to_sec(a, b):
    return (b - a) / FPS


# ---------------------------------------------------------------- effects placement
# eye "scratch" on every glance (louder and drier in the bedroom, muffled inside the x-ray head)
for i, f in enumerate(SACCADES):
    inside = SH["xray_head"] <= f < SH["eye_a"]
    sc = scrape(0.3 if i < 3 else 0.36)
    if inside:
        sc = band(sc, 400, 3000)
    place(sc, f - 1, db(-9 if not inside else -12), pan=0.25)
    place(scrape(0.18, 0.7), f + 2, db(-17), pan=-0.2)
# the sandpaper shot: one stroke per block pass (13-frame period, see scene.py)
sa = SH["sand"]
for k in range(int((SH["eye_b"] - sa) / 6.5) + 1):
    place(scrape(0.2, 0.85 + 0.15 * (k % 2)), sa + int(k * 6.5), db(-8), pan=0.15 * (1 if k % 2 else -1))
# heartbeats: huge in the x-ray chest shot
for f in HEARTBEATS:
    place(heartbeat(), f - 1, db(-3))
    place(boom(0.6, 40), f - 1, db(-12))
# chewing: deafening crunch + jaw thud each bite
for f in CHEWS:
    place(crunch(), f + 2, db(-4), pan=0.2)
    place(boom(0.35, 70), f + 3, db(-15))
# transitions
place(whoosh(0.55, True), SH["xray_head"] - 10, db(-10))
place(boom(1.4, 44), SH["xray_head"], db(-9))
place(whoosh(0.45, False, 500, 7000), SH["sand"] - 6, db(-16), pan=-0.3)
place(whoosh(0.45, True, 400, 6000), SH["eye_b"] - 6, db(-16), pan=0.3)
place(whoosh(0.6, True), SH["xray_heart"] - 12, db(-10))
place(boom(1.2, 40), SH["xray_heart"], db(-10))
place(whoosh(0.45, False), SH["chew"] - 5, db(-14))
place(whoosh(0.5, False, 300, 5000), SH["ct"] - 7, db(-14))
# CT scanner: hum, the table motor and two beeps
ct_len = frames_to_sec(SH["ct"], SH["xray_dive"]) + 0.3
place(hum(ct_len, 60) * np.minimum(1, np.arange(int(ct_len * SR)) / (0.15 * SR)), SH["ct"], db(-24))
place(whir(ct_len), SH["ct"] + 2, db(-20))
place(beep(1046), SH["ct"] + 6, db(-18))
place(beep(1318), SH["ct"] + 12, db(-18))
# the dive into the skull: big whoosh down, rumble, then muffled "inside" world
place(whoosh(1.1, False, 120, 5000), SH["xray_dive"] - 6, db(-7))
place(boom(2.2, 38), SH["xray_dive"] + 14, db(-9))
place(shimmer(1.6, 660), SH["xray_dive"] + 24, db(-20))
# inside the inner ear: body sounds flood in (muffled heart, muffled scrapes) + glowing drone
ef_a, ef_b = SH["ear_flow"], SH["or"]
for k, f in enumerate(range(ef_a + 4, ef_b - 6, 13)):
    place(muffle(heartbeat(), 300), f, db(-6))
for f in (ef_a + 12, ef_a + 30, ef_a + 48):
    place(band(scrape(0.3), 300, 2500), f, db(-13), pan=0.3)
drone_len = frames_to_sec(ef_a, ef_b)
tt = t(drone_len)
drone = sum(np.sin(2 * np.pi * f * tt) for f in (110, 165, 220.5)) * np.sin(np.pi * tt / drone_len) ** 0.5
place(norm(drone) * 0.5, ef_a, db(-18))
# operating room: lamp switch + monitor
place(whoosh(0.4, False), SH["or"] - 5, db(-16))
place(click(0.08, 600, 5000), SH["or"] + 3, db(-8))
place(hum(frames_to_sec(SH["or"], SH["seal"]), 100) * 0.3, SH["or"] + 3, db(-28))
for f in (SH["or"] + 9, SH["or"] + 27):
    place(beep(880, 0.12), f, db(-20))
# the seal: whoosh in, bone click, sparkle, everything settles
place(whoosh(0.5, True, 400, 8000), SH["seal"] - 4, db(-12))
place(whoosh(0.45, True, 600, 9000), SEAL - 12, db(-12))
place(click(0.07), SEAL, db(-3))
place(boom(0.9, 60), SEAL, db(-14))
place(chime(), SEAL + 2, db(-12))
place(shimmer(2.2, 1046), SEAL + 4, db(-20))
# morning: birds and room tone; his glances are silent now; "Gone." gets a soft chime
mo = SH["morning"]
place(whoosh(0.6, False, 300, 4000), mo - 8, db(-18))
mlen = frames_to_sec(mo, END) + 0.3
bird = birds(mlen) * np.minimum(1, np.arange(int(mlen * SR)) / (0.6 * SR))
place(band(bird, 2000, 9000), mo, db(-22), pan=-0.4)
place(band(noise(mlen), 100, 1200) * 0.08, mo, db(-30))
gone = int(round(meta["beats"][-1]["end"] * FPS)) - 8
place(chime((1568.0, 2093.0, 2637.0), 0.09, 2.2), gone, db(-16))

# ---------------------------------------------------------------- music bed (100 bpm, A minor pulse -> C major lift)
BPM = 100
beat_s = 60 / BPM
TOT = N / SR
tt = np.arange(N) / SR
music_l = np.zeros(N, np.float32)
music_r = np.zeros(N, np.float32)
morning_t = (mo - 1) / FPS
chords_dark = [(110.0, 130.81, 164.81), (87.31, 110.0, 130.81), (98.0, 123.47, 146.83), (82.41, 103.83, 123.47)]  # Am F G E
chords_lift = [(130.81, 164.81, 196.0, 246.94), (174.61, 220.0, 261.63, 329.63)]                                 # Cmaj7 Fmaj7
bar = 4 * beat_s
# pad: detuned saw-ish stack through a soft low-pass, chord per bar
for i0 in range(int(TOT / bar) + 1):
    a, b = i0 * bar, (i0 + 1) * bar
    lift = a >= morning_t - 0.2
    ch = chords_lift[i0 % 2] if lift else chords_dark[i0 % 4]
    ia, ib = int(a * SR), min(N, int(b * SR) + int(0.4 * SR))
    if ia >= N:
        break
    seg_t = np.arange(ib - ia) / SR
    e = np.minimum(1, seg_t / 0.25) * np.clip((b - a + 0.4 - seg_t) / 0.45, 0, 1)
    sl = np.zeros(ib - ia); sr_ = np.zeros(ib - ia)
    for k, f in enumerate(ch):
        for det, side in ((-0.004, 0), (0.004, 1)):
            ph = 2 * np.pi * f * (1 + det) * seg_t
            w = np.sin(ph) + 0.35 * np.sin(2 * ph) + 0.15 * np.sin(3 * ph)
            (sl if side == 0 else sr_)[:] += w
    music_l[ia:ib] += (sl * e * 0.12).astype(np.float32)
    music_r[ia:ib] += (sr_ * e * 0.12).astype(np.float32)
music_l = band(music_l, 60, 2200 if True else None)
music_r = band(music_r, 60, 2200)
# pulse: muted 8th-note bass + soft tick, only in the dark section
pulse = np.zeros(N, np.float32)
k = 0
while k * beat_s / 2 < morning_t - 0.3:
    s0 = int(k * beat_s / 2 * SR)
    d = t(0.16)
    root = chords_dark[int(k * beat_s / 2 / bar) % 4][0] / 2
    s = np.sin(2 * np.pi * root * d) * np.exp(-d * 18) * (1.0 if k % 2 == 0 else 0.6)
    pulse[s0:s0 + len(s)] += s[: max(0, N - s0)]
    if k % 4 == 2:
        tick = band(rng.standard_normal(len(d)).astype(np.float32), 5000, 12000) * np.exp(-d * 60) * 0.25
        pulse[s0:s0 + len(tick)] += tick[: max(0, N - s0)]
    k += 1
# bell motif on the lift
bell = np.zeros(N, np.float32)
for j, f in enumerate((523.25, 659.25, 783.99, 1046.5)):
    s0 = int((morning_t + 0.9 + j * beat_s) * SR)
    d = t(2.0)
    s = (np.sin(2 * np.pi * f * d) + 0.25 * np.sin(2 * np.pi * 2.76 * f * d)) * np.exp(-d * 2.2)
    if s0 < N:
        bell[s0:s0 + len(s)] += s[: N - s0] * 0.18
# music dips while the inner-ear "inside" and the seal moment play, and fades at the very end
mgain = np.ones(N, np.float32)
fade_out = np.clip((TOT - tt) / 1.2, 0, 1)
dip = 1 - 0.5 * ((tt > (ef_a - 1) / FPS) & (tt < (SEAL + 10) / FPS))
mgain *= fade_out * dip
music_l = (music_l + pulse * 0.55 + bell) * mgain
music_r = (music_r + pulse * 0.55 + bell) * mgain
L += music_l * db(-6)
Rr += music_r * db(-6)

# ---------------------------------------------------------------- voice, ducking, master
vo, vsr = sf.read(VO_WAV, dtype="float32")
if vo.ndim > 1:
    vo = vo.mean(1)
if vsr != SR:
    idx = np.arange(int(len(vo) * SR / vsr)) * (vsr / SR)
    vo = np.interp(idx, np.arange(len(vo)), vo).astype(np.float32)
voice = np.zeros(N, np.float32)
voice[: min(N, len(vo))] = vo[:N]
win = int(0.03 * SR)
venv = np.sqrt(np.convolve(voice ** 2, np.ones(win) / win, mode="same"))
act = np.clip((20 * np.log10(venv + 1e-9) + 45) / 15, 0, 1).astype(np.float32)
hold = np.zeros_like(act)
level, rel = 0.0, np.exp(-64 / (0.25 * SR))
for i in range(0, N, 64):
    level = max(float(act[i:i + 64].max(initial=0)), level * rel)
    hold[i:i + 64] = level
duck = db(-8 * hold)
L = L * duck + voice
Rr = Rr * duck + voice
mix = np.stack([L, Rr], 1)
peak = float(np.abs(mix).max())
mix = mix / peak * db(-1.0)
sf.write(OUT, mix, SR)
print("MIX", OUT, round(N / SR, 2), "s, pre-normalize peak", round(peak, 3))
