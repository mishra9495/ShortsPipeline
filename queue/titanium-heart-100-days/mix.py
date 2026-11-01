"""Sound design + mix for "titanium-heart-100-days" (numpy + soundfile only).

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

# SYNC with scene.py (fractions of the beat they live in; beat indexes are 0-based)
HOOK_CUT_F = 0.52              # beat 1: X-ray -> his face
SICK_F = 0.50                  # beat 2: ward -> X-ray of the failing heart
SWAP_F = 0.72                  # beat 3: the failing heart lifts out, the titanium heart slides in
XCUT3_F = 0.42                 # beat 3: OR -> X-ray
ROTOR_F = 0.50                 # beat 4: orbit -> rotor macro
SLO_B_F = 0.80                 # beat 5: slow-mo window is [B[4], this fraction]
MAG_F = 0.18                   # beat 5: the magnet rings flare on
FLOWM_F = 0.50                 # beat 6: X-ray -> flow macro
DOORS_F = 0.10                 # beat 7: the doors slide open
COOLER_B_F = 0.34              # beat 8: the cooler stops
DONOR_F = 0.70                 # beat 8: the donor heart takes over
PROTO_F = 0.50                 # beat 9: bench -> prototype macro
CLOSE_F = 0.48                 # beat 10: device -> closing X-ray


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


# ------------------------------------------------------------------ extra synth: the titanium heart
def breath(sec=1.6):
    n = int(sec * SR)
    return norm(fft_filter(noise(sec), lo=250, hi=2800) * np.sin(np.linspace(0, np.pi, n)) ** 1.5)


def rotor_hum(sec, f0=118.0, slow=None):
    """The pump: a smooth electric whirr (fundamental + blade-pass partial), no clicks, no bearings."""
    tt = np.arange(int(sec * SR)) / SR
    k = np.ones_like(tt) if slow is None else slow
    ph = np.cumsum(f0 * k) / SR
    s = 0.6 * np.sin(2 * np.pi * ph) + 0.25 * np.sin(2 * np.pi * 7 * ph) + 0.12 * np.sin(2 * np.pi * 14 * ph + 1.0)
    s += 0.15 * fft_filter(noise(sec), lo=300, hi=1800) * (0.6 + 0.4 * np.sin(2 * np.pi * ph))
    return norm(s.astype(np.float32))


def mag_swell(sec=1.2):
    """Magnetic field powering on: a rising, shimmering electric tone."""
    tt = np.arange(int(sec * SR)) / SR
    f = 180 * 2 ** (1.5 * tt / sec)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.4 * np.sin(2 * np.pi * np.cumsum(f * 2.01) / SR) + 0.25 * np.sin(2 * np.pi * np.cumsum(f * 3.98) / SR)
    return norm(s * env_ar(len(tt), 0.5, 0.4))


def servo(sec=0.6):
    """Motorised doors gliding apart."""
    tt = np.arange(int(sec * SR)) / SR
    f = 260 + 60 * np.sin(np.pi * tt / sec)
    return norm((np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.4 + 0.6 * fft_filter(noise(sec), lo=500, hi=3000)) * env_ar(len(tt), 0.08, 0.25))


def birds(sec):
    out = np.zeros(int(sec * SR), np.float32)
    k = 0.2
    while k < sec - 0.3:
        i = int(k * SR)
        c = chirp()
        out[i:i + len(c)] += c[: len(out) - i] * rng.uniform(0.3, 1.0)
        k += rng.uniform(0.35, 1.2)
    return out


def rattle(sec=1.2):
    """Trolley wheels on a hospital floor."""
    n = int(sec * SR)
    c = (rng.random(n) < 0.006).astype(np.float32) * rng.uniform(0.3, 1, n).astype(np.float32)
    s = fft_filter(np.convolve(c, np.exp(-np.arange(200) / 30), mode="same"), lo=300, hi=4000) + 0.3 * fft_filter(noise(sec), lo=60, hi=300)
    return norm(s * env_ar(n, 0.15, 0.3))


def metal_tap(sec=0.4):
    return norm(sum(tone(f, sec, decay=11) / k for k, f in enumerate((1480, 2210, 3320), 1)) + 0.3 * pop(sec))


# ------------------------------------------------------------------ timeline (mirrors scene.py SHOTS)
t = np.arange(N) / SR
NARR = TOTAL - TAIL
SWAP = at_beat(2, SWAP_F)
SLO_A, SLO_B = B[4], at_beat(4, SLO_B_F)
MAG = at_beat(4, MAG_F)
DOORS = at_beat(6, DOORS_F)
COOLER_A, COOLER_B = B[7], at_beat(7, COOLER_B_F)
DONOR = at_beat(7, DONOR_F)
SPANS = {"xray": [(0.0, at_beat(0, HOOK_CUT_F)), (at_beat(1, SICK_F), B[2]), (at_beat(2, XCUT3_F), B[3]), (B[5], at_beat(5, FLOWM_F)),
                  (at_beat(7, 0.55), B[8]), (at_beat(9, CLOSE_F), TOTAL)],
         "device": [(B[3], B[5]), (at_beat(5, FLOWM_F), B[6]), (B[9], at_beat(9, CLOSE_F))],
         "ward": [(at_beat(0, HOOK_CUT_F), at_beat(1, SICK_F))],
         "or": [(B[2], at_beat(2, XCUT3_F)), (B[7], at_beat(7, 0.55))],
         "exit": [(B[6], B[7])], "workshop": [(B[8], B[9])]}
CUTS = sorted({a_ for v_ in SPANS.values() for a_, _ in v_ if a_ > 0.05})


def mask(name, fade=240):
    m = np.zeros(N, np.float32)
    for a_, b_ in SPANS[name]:
        m[int(a_ * SR):int(min(b_, TOTAL) * SR)] = 1.0
    return np.convolve(m, np.ones(fade) / fade, mode="same").astype(np.float32)


def fit(x):
    out = np.zeros(N, np.float32)
    out[: min(N, len(x))] = x[:N]
    return out


xray_m, dev_m, ward_m, or_m, exit_m, wk_m = (mask(n) for n in ("xray", "device", "ward", "or", "exit", "workshop"))
# titanium heart "on": the hook, after the swap until the donor heart, and the closer (matches scene.py dev_on)
dev_on = ((t < B[1]) | ((t >= SWAP) & (t < DONOR)) | (t >= B[9])).astype(np.float32)
dev_on = np.convolve(dev_on, np.ones(2400) / 2400, mode="same").astype(np.float32)

# ------------------------------------------------------------------ music: tense medical pulse -> wonder -> warm hope
drone = (0.6 * np.sin(2 * np.pi * 55 * t) + 0.3 * np.sin(2 * np.pi * 82.4 * t + 1.0)) * (0.7 + 0.3 * np.sin(2 * np.pi * 0.2 * t))
hope = np.clip((t - (B[6] - 0.2)) / 1.2, 0, 1).astype(np.float32)
music += drone.astype(np.float32) * (1 - 0.7 * hope) * float(db(-12))
arp = np.zeros(N, np.float32)
notes = (329.6, 392.0, 493.9, 587.3)
k, j = B[3], 0
while k < NARR:
    if not (SLO_A - 0.4 < k < SLO_B):
        place(tone(notes[j % 4] * (1.0 if k < B[6] else 1.122), 0.35, decay=9), k, -10, bus=arp)
    k += 60 / 120 / 2
    j += 1
music += arp * float(db(-8))
pad = sum(np.sin(2 * np.pi * f * t + i) / (i + 1) for i, f in enumerate((220.0, 277.2, 329.6, 440.0)))
music += fft_filter(pad.astype(np.float32), hi=1800) * hope * float(db(-12))
a_, b_ = int((SLO_A - 0.45) * SR), int((SLO_A - 0.02) * SR)                # near-silence just before the slow-mo reveal
dip = np.ones(N, np.float32)
dip[max(0, a_):max(0, b_)] = 0.1
music *= np.convolve(dip, np.ones(480) / 480, mode="same").astype(np.float32)
place(tone(110.0, 1.8, decay=1.6), E[9] - 0.2, -8, bus=music)

# ------------------------------------------------------------------ ambience per set
amb = fit(fft_filter(noise(TOTAL), lo=80, hi=600)) * float(db(-30)) * (ward_m + or_m)
amb += fit(fft_filter(noise(TOTAL), lo=100, hi=1200)) * float(db(-28)) * exit_m * np.clip((t - DOORS) / 0.6, 0, 1).astype(np.float32)
amb += fit(birds(TOTAL)) * float(db(-24)) * exit_m * np.clip((t - DOORS) / 0.6, 0, 1).astype(np.float32)
amb += fit(hum(TOTAL)) * float(db(-28)) * wk_m
mix[: len(amb)] += amb
# the pump whirr: under every titanium-heart shot (X-ray and macro), pitched down in the slow-motion window
slow = np.where((t >= SLO_A) & (t < SLO_B), 0.4, 1.0).astype(np.float32)
slow = np.convolve(slow, np.ones(2400) / 2400, mode="same").astype(np.float32)
rh = fit(rotor_hum(TOTAL, 118.0, slow=fit(slow)[: int(TOTAL * SR)]))
mix += rh * (dev_m + xray_m * dev_on + 0.6 * wk_m) * float(db(-19))
# heartbeats: weak and irregular before the swap, strong after the donor heart
hb_weak = fit(heartbeat(TOTAL, 84)) * (np.sin(2 * np.pi * 0.45 * t) ** 2).astype(np.float32)
mix += hb_weak * ((t >= B[1]) & (t < SWAP)).astype(np.float32) * (ward_m + xray_m) * float(db(-17))
hb_strong = fit(heartbeat(TOTAL, 75))
mix += hb_strong * ((t >= DONOR) & (t < B[9])).astype(np.float32) * (xray_m + or_m) * float(db(-14))
# OR / ward monitors
k = B[1]
while k < B[2]:
    place(beep(), k + 0.2, -26)
    k += 0.71 + 0.25 * rng.random()                                       # irregular: a failing heart
k = B[2]
while k < at_beat(2, XCUT3_F):
    place(beep(), k + 0.1, -26)
    k += 0.8

# ------------------------------------------------------------------ per-beat SFX
for c in CUTS:                                                            # a whoosh on every set change
    place(whoosh(0.35), c - 0.15, -16)
# 1 hook: the pump spins up as the first frame lands
place(mag_swell(0.8), 0.0, -18)
# 2 laboured breathing in the ward
for k_ in range(3):
    place(breath(0.8), B[1] + 0.35 + 0.95 * k_, -16)
# 3 the swap: a deep boom and a metallic seat
place(boom(0.6, 52), SWAP, -7)
place(metal_tap(0.5), SWAP + 0.3, -14)
# 4 the device turntable: a soft metallic shimmer
place(metal_tap(0.4), B[3] + 0.1, -20)
# 5 MONEY MOMENT: silence dip, the magnets power on, slow-motion whirr
place(mag_swell(1.4), MAG - 0.6, -8)
place(boom(1.0, 40), MAG, -6)
place(whoosh(0.5, rising=False), SLO_B - 0.1, -15)
# 6 blood flowing out to body and lungs
place(squelch(1.6), B[5] + 0.2, -16)
place(squelch(1.2), at_beat(5, FLOWM_F) + 0.1, -18)
# 7 the doors part, daylight, a deep breath of fresh air
place(servo(0.9), DOORS, -12)
place(breath(1.4), DOORS + 0.5, -15)
place(chime(), DOORS + 0.6, -16)
# 8 the cooler rolls in, then the new heart starts
place(rattle(COOLER_B - COOLER_A + 0.2), COOLER_A, -13)
place(clink(), COOLER_B, -18)
place(boom(0.6, 60), DONOR, -9)
# 9 the workshop: a wrench clink, a little prototype whirr
place(clink(), B[8] + 0.3, -18)
place(metal_tap(0.4), at_beat(8, PROTO_F) + 0.1, -18)
# 10 close: warm chime
place(chime(), at_beat(9, CLOSE_F) + 0.2, -14)

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
