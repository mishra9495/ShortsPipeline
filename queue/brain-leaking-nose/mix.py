"""Sound design + mix for "brain-leaking-nose" (numpy + soundfile only).

Usage: python mix.py <beats.json> <vo.wav> <out_mix.wav>
beats.json comes from align_narration.py (or tts.py): {"duration": s, "beats": [{"start","end","text"}, ...]}.
All effects are synthesized and cued RELATIVE to the beat times, so any narration take works.
Cue fractions marked SYNC must match the same constants in scene.py.
Final loudness (-14 LUFS) is applied by ffmpeg loudnorm when the video is muxed.
"""
import json
import sys

import numpy as np
import soundfile as sf

BEATS_JSON, VO_WAV, OUT = sys.argv[1:4]
rng = np.random.default_rng(7)

vo, SR = sf.read(VO_WAV, dtype="float32")
if vo.ndim > 1:
    vo = vo.mean(axis=1)
meta = json.load(open(BEATS_JSON, encoding="utf-8"))
B = [float(b["start"]) for b in meta["beats"]]
E = [float(b["end"]) for b in meta["beats"]]
assert len(B) == 10, f"expected 10 beats, got {len(B)}"
TAIL = 0.8                                      # scene.py holds 0.8 s after the narration
TOTAL = max(float(meta["duration"]), len(vo) / SR) + TAIL
N = int(TOTAL * SR) + SR // 2
mix = np.zeros(N, np.float32)
music = np.zeros(N, np.float32)

# SYNC with scene.py (v2)
IMPACT_F = 0.48      # beat 2: car B rear-ends her car (exterior)
FACE_F = 0.80        # beat 2: slow-motion face meets the dashboard
MUCUS_F = 0.62       # beat 4: "It wasn't mucus" -> test strip turns
CRACK_F = 0.40       # beat 6: crack reveal
SEAL_F = 0.78        # beat 9: fat graft seats into the hole


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


def drip(f0=1400):
    """Water-drop 'plip': fast upward pitch chirp with a short decay."""
    sec = 0.12
    t = np.arange(int(sec * SR)) / SR
    pitch = f0 * (1 + 1.4 * t / sec)
    return (np.sin(2 * np.pi * np.cumsum(pitch) / SR) * np.exp(-t * 45)).astype(np.float32)


def crack(sec=0.35):
    n = int(sec * SR)
    c = (rng.random(n) < 0.01).astype(np.float32) * rng.uniform(0.4, 1, n).astype(np.float32)
    c = np.convolve(c, np.exp(-np.arange(160) / 18), mode="same")
    s = fft_filter(c, lo=1200, hi=9000) * np.exp(-np.arange(n) / (0.08 * SR))
    return norm(s)


def thud(sec=0.5):
    return norm(boom(sec, 45) + 0.4 * fft_filter(noise(sec), hi=400) * env_ar(int(sec * SR), 0.002, sec * 0.9))


def screech(sec=0.6):
    t = np.arange(int(sec * SR)) / SR
    f = 2200 + 300 * np.sin(2 * np.pi * 7 * t)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.5 + 0.5 * fft_filter(noise(sec), lo=1800, hi=4000)
    return norm(s * env_ar(len(t), 0.05, 0.25))


def mwomp():
    """Descending 'wah-wah' brass-ish shrug for 'doctors blamed allergies'."""
    sec = 0.55
    t = np.arange(int(sec * SR)) / SR
    f = 220 * (1 - 0.35 * t / sec)
    s = sum(np.sin(2 * np.pi * k * np.cumsum(f) / SR) / k for k in (1, 2, 3, 4))
    s *= (0.6 + 0.4 * np.sin(2 * np.pi * 6 * t)) * env_ar(len(t), 0.02, 0.2)
    return norm(fft_filter(s.astype(np.float32), hi=2500))


def sniff(sec=0.35):
    return norm(fft_filter(noise(sec), lo=1500, hi=7000) * env_ar(int(sec * SR), 0.12, 0.15))


def tissue(sec=0.3):
    return norm(fft_filter(noise(sec), lo=2500, hi=11000) * (0.6 + 0.4 * (rng.random(int(sec * SR)) < 0.3))
                * env_ar(int(sec * SR), 0.01, 0.1))


def tick(f=3000, sec=0.03):
    return (tone(f, sec, decay=180) * 0.8 + 0.2 * fft_filter(noise(sec), lo=4000) * np.exp(-np.arange(int(sec * SR)) / 60)).astype(np.float32)


def clink():
    return norm(sum(tone(f, 0.6, decay=9) / k for k, f in enumerate((2637, 3951, 5274), 1)))


def sting(sec=1.2):
    t = np.arange(int(sec * SR)) / SR
    f = 330 * 2 ** (t / sec)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) + 0.5 * np.sin(2 * np.pi * np.cumsum(f * 1.5) / SR)
    return norm(s * env_ar(len(t), 0.4, 0.3))


def bubbles(sec, rate=14):
    out = np.zeros(int(sec * SR), np.float32)
    for _ in range(int(sec * rate)):
        b = drip(rng.uniform(400, 900)) * rng.uniform(0.3, 1.0)
        i = rng.integers(0, max(1, len(out) - len(b)))
        out[i:i + len(b)] += b[: len(out) - i]
    return out


def pour(sec):
    n = int(sec * SR)
    w = fft_filter(noise(sec), lo=500, hi=5000)
    gurgle = 0.6 + 0.4 * np.sin(2 * np.pi * np.cumsum(9 + 4 * rng.random(n)) / SR)
    return norm(w * gurgle * env_ar(n, 0.15, 0.4))


def heartbeat(sec, bpm=72):
    s = np.zeros(int(sec * SR), np.float32)
    beat = boom(0.25, 48)
    t = 0.0
    while t < sec - 0.5:
        for off, g in ((0, 1.0), (0.28, 0.6)):
            i = int((t + off) * SR)
            s[i:i + len(beat)] += beat[: len(s) - i] * g
        t += 60 / bpm
    return s


def squelch(sec):
    n = int(sec * SR)
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * np.cumsum(3 + 3 * rng.random(n)) / SR)
    return norm(fft_filter(noise(sec), lo=150, hi=900) * lfo * env_ar(n, 0.2, 0.3))


def chime():
    return norm(sum(tone(f, 1.4, decay=3.5) for f in (1046.5, 1318.5, 1568.0)))


def beep():
    return (tone(1000, 0.09) * env_ar(int(0.09 * SR), 0.005, 0.02)).astype(np.float32)


def chirp():
    sec = 0.18
    t = np.arange(int(sec * SR)) / SR
    f = 3200 + 1800 * np.sin(2 * np.pi * 14 * t)
    return (np.sin(2 * np.pi * np.cumsum(f) / SR) * env_ar(len(t), 0.01, 0.08)).astype(np.float32)


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

# ------------------------------------------------------------------ music bed
t = np.arange(N) / SR
end_dark = B[8]                       # tension through the bacteria beat
pulse = np.zeros(N, np.float32)
k = 0.0
while k < end_dark:
    place(fft_filter(boom(0.35, 41), hi=180), k, -4, bus=pulse)
    place(tick(6500, 0.02) * 0.5, k + 0.25, -14, bus=pulse)
    k += 0.5                          # 120 bpm pulse
drone = (0.6 * np.sin(2 * np.pi * 55 * t) + 0.3 * np.sin(2 * np.pi * 82.4 * t + 1.0)
         + 0.15 * np.sin(2 * np.pi * 110.3 * t)) * (0.7 + 0.3 * np.sin(2 * np.pi * 0.17 * t))
dark = (pulse + 0.5 * drone.astype(np.float32))
dark *= np.clip((end_dark + 0.6 - t) / 0.6, 0, 1).astype(np.float32)
# tension swell under the bacteria beat
sw = np.clip((t - B[7]) / max(0.1, B[8] - B[7]), 0, 1) * (t < B[8] + 0.3)
dark += (0.5 * np.sin(2 * np.pi * 58.3 * t) * sw).astype(np.float32)
# hopeful resolve: warm major pad + soft plucks from the surgery beat on
res = np.clip((t - B[8]) / 1.2, 0, 1).astype(np.float32)
pad = sum(np.sin(2 * np.pi * f * t + i) / (i + 1) for i, f in enumerate((261.6, 329.6, 392.0, 523.3)))
pad = fft_filter(pad.astype(np.float32), hi=1800) * res * (0.8 + 0.2 * np.sin(2 * np.pi * 0.3 * t)).astype(np.float32)
pluck_t = B[8]
notes = (523.3, 659.3, 784.0, 659.3)
ni = 0
while pluck_t < TOTAL - 0.5:
    place(tone(notes[ni % 4], 0.8, decay=6), pluck_t, -10, bus=music)
    pluck_t += 0.5
    ni += 1
music += dark * float(db(-6)) + pad * float(db(-9))
# hard dips to near-silence right before the two reveals
for tdip in (at_beat(3, MUCUS_F), B[4]):
    a, b = int((tdip - 0.32) * SR), int(tdip * SR)
    ramp_ = np.ones(N, np.float32)
    ramp_[max(0, a):max(0, b)] = 0.08
    music *= np.convolve(ramp_, np.ones(480) / 480, mode="same").astype(np.float32)
# final hit on the closer's last word
place(norm(boom(1.2, 49) + 0.5 * tone(130.8, 1.2, decay=2.5)), E[9] - 0.05, -2, bus=music)

# ------------------------------------------------------------------ per-beat effects
# 1 hook: drips on the nose close-up, boom on "brain", whoosh to the X-ray, shrug on "allergies"
for dt in (0.05, 0.85):
    place(drip(), B[0] + dt, -10)
place(boom(0.7, 50), B[0] + 0.45, -6)
place(whoosh(0.45), at_beat(0, 0.30) - 0.3, -12)
place(whoosh(0.4, False), at_beat(0, 0.66) - 0.1, -16)
place(mwomp(), E[0] - 0.3, -11)
place(heartbeat(B[2] - B[0]), B[0], -20)
# 2 crash: night road ambience, engine rushing in, screech, rear-end impact, slow-mo face hit + skull crack
imp = at_beat(1, IMPACT_F)
face = at_beat(1, FACE_F)
cab = fft_filter(noise(B[2] - B[1]), hi=260)
place(norm(cab) * env_ar(len(cab), 0.2, 0.2), B[1], -20)
eng_len = max(0.3, imp - B[1])
tt = np.arange(int(eng_len * SR)) / SR
eng = np.sin(2 * np.pi * np.cumsum(70 + 90 * (tt / eng_len) ** 2) / SR) * (tt / eng_len) ** 1.5
place(norm(fft_filter(eng.astype(np.float32) + 0.3 * noise(eng_len)[:len(tt)], hi=900)), B[1], -12)
place(screech(0.5), imp - 0.5, -12)
place(thud(0.7), imp, -2)
place(crack(0.4), imp + 0.01, -8)
place(fft_filter(noise(0.9), lo=2500) * env_ar(int(0.9 * SR), 0.002, 0.7), imp, -20)   # glass + metal debris
place(fft_filter(boom(1.0, 38), hi=300), face - 0.02, -4)                              # slow-mo body hit
place(crack(0.3), face + 0.03, -7)
# 3 years: sped-up clock, tissue pulls and sniffs
k = B[2]
while k < B[3] - 0.1:
    place(tick(2600), k, -16)
    k += 0.18
for dt in (0.15, 0.95, 1.7):
    place(tissue(), B[2] + dt, -16)
    place(sniff(), B[2] + dt + 0.3, -15)
# 4 specialist: vial clink, rising sting on "It wasn't mucus"
place(clink(), B[3] + 0.15, -12)
place(sting(1.0), at_beat(3, MUCUS_F) - 0.05, -9)
place(whoosh(0.35), at_beat(3, MUCUS_F) - 0.3, -15)
# 5 CSF: underwater bubbles + submerged swoosh
place(bubbles(B[5] - B[4], rate=10), B[4], -17)
place(whoosh(1.2), B[4] + 0.1, -18)
# 6 hole: dolly whoosh, bone crack, trickle, alert blip
place(whoosh(0.5), B[5] - 0.1, -12)
place(crack(0.4), at_beat(5, CRACK_F), -6)
place(bubbles(B[6] - at_beat(5, CRACK_F), rate=18) * 0.6, at_beat(5, CRACK_F) + 0.1, -18)
place(beep(), at_beat(5, CRACK_F) + 0.35, -16)
# 7 half a pint: pour + ding when the line lights up
place(pour(max(0.5, (B[7] - B[6]) * 0.75)), B[6] + 0.1, -15)
place(chime() * 0.6, at_beat(6, 0.82), -16)
# 8 bacteria: squelchy crawl, faster heartbeat, warning thrum
place(squelch(B[8] - B[7]), B[7], -14)
place(heartbeat(B[8] - B[7], bpm=110), B[7], -15)
place(fft_filter(boom(0.9, 38), hi=200), at_beat(7, 0.6), -8)
# 9 surgery: monitor beeps, glove snap, scope slide, squish, sealed click + chime
k = B[8]
while k < B[9]:
    place(beep(), k, -24)
    k += 0.8
place(norm(fft_filter(noise(0.05), lo=1500)) * np.exp(-np.arange(int(0.05 * SR)) / 150), B[8] + 0.05, -12)
place(whoosh(0.8), at_beat(8, 0.2), -16)
place(squelch(0.35), at_beat(8, SEAL_F) - 0.2, -12)
place(tick(1800, 0.05), at_beat(8, SEAL_F), -8)
place(chime(), at_beat(8, SEAL_F) + 0.05, -12)
# 10 closer: daylight birds, checklist ticks
for dt in (0.2, 0.9, 1.6, 2.6, 3.4):
    place(chirp(), B[9] + dt, -26)
for frac in (0.25, 0.45, 0.65):
    place(tick(2400, 0.04), at_beat(9, frac), -12)

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
