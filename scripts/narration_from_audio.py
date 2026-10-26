"""Turn a narration recording (e.g. an MP3 downloaded from the ElevenLabs website, voice "Daniel") into the
pipeline's narration WAV + beat timings. No API key needed.

Usage: python narration_from_audio.py <audio.mp3|wav> <script.txt> <out_prefix>
Writes <prefix>.wav and <prefix>.json ({"voice", "duration", "beats": [{"text","start","end"}]}).

Same treatment as the sneeze short: long pauses trimmed, tempo +15% (pitch kept). Beat boundaries are the
pauses that best split the audio in proportion to each line's length (dynamic programming over the detected
pauses), so the 10 script lines map onto the read even when a line contains two sentences.
"""
import json
import os
import subprocess
import sys

import numpy as np
import soundfile as sf

TEMPO = 1.15
MAX_GAP = 0.16       # longest pause kept (s)
MIN_PAUSE = 0.12     # silences shorter than this are not candidate beat boundaries
SR = 44100


def ffmpeg_bin():
    import glob
    local = os.environ.get("LOCALAPPDATA", "")
    cands = [os.environ.get("FFMPEG", ""), "ffmpeg", os.path.join(local, "Microsoft", "WinGet", "Links", "ffmpeg.exe")]
    cands += sorted(glob.glob(os.path.join(local, "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg*", "*", "bin", "ffmpeg.exe")))
    for c in cands:
        if not c:
            continue
        try:
            subprocess.run([c, "-version"], capture_output=True, check=True)
            return c
        except Exception:
            continue
    raise SystemExit("ERROR: ffmpeg not found")


def silences(x, sr, thresh_db=-38.0):
    win = int(0.02 * sr)
    env = np.sqrt(np.convolve(x.astype(np.float64) ** 2, np.ones(win) / win, mode="same") + 1e-12)
    quiet = 20 * np.log10(env + 1e-9) < thresh_db
    runs, i, n = [], 0, len(quiet)
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]:
                j += 1
            runs.append((i / sr, j / sr))
            i = j
        else:
            i += 1
    return runs


def main():
    src, script_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
    prefix = out[:-4] if out.lower().endswith(".wav") else out
    lines = [l.strip() for l in open(script_path, encoding="utf-8") if l.strip()]
    ff = ffmpeg_bin()
    raw = prefix + "_raw.wav"
    subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-i", src, "-ac", "1", "-ar", str(SR), raw], check=True)
    x, sr = sf.read(raw, dtype="float32")
    runs = silences(x, sr)
    total = len(x) / sr
    speech_start = runs[0][1] if runs and runs[0][0] <= 0.01 else 0.0
    speech_end = runs[-1][0] if runs and runs[-1][1] >= total - 0.01 else total
    inner = [(a, b) for a, b in runs if a > speech_start + 0.05 and b < speech_end - 0.05 and b - a >= MIN_PAUSE]

    # choose len(lines)-1 boundaries among the inner pauses, matching each line's share of the characters
    weights = np.array([len(l) for l in lines], float)
    target = np.cumsum(weights)[:-1] / weights.sum()                  # expected boundary positions (0..1)
    mids = [((a + b) / 2 - speech_start) / max(1e-6, speech_end - speech_start) for a, b in inner]
    lens = [b - a for a, b in inner]
    K, M = len(target), len(inner)
    if M < K:
        raise SystemExit(f"ERROR: found only {M} pauses for {K} beat boundaries; the read is too run-together")
    INF = 1e18
    cost = np.full((K + 1, M + 1), INF)
    back = np.zeros((K + 1, M + 1), int)
    cost[0, :] = 0.0
    for k in range(1, K + 1):
        for m in range(k, M + 1):                                   # boundary k uses pause m-1
            c = (mids[m - 1] - target[k - 1]) ** 2 * 40 - min(lens[m - 1], 0.6) * 0.5
            best, arg = INF, 0
            for p in range(k - 1, m):
                if cost[k - 1, p] < best:
                    best, arg = cost[k - 1, p], p
            cost[k, m] = best + c
            back[k, m] = arg
    m = int(np.argmin(cost[K, :]))
    chosen = []
    for k in range(K, 0, -1):
        chosen.append(m - 1)
        m = back[k, m]
    chosen = sorted(chosen)
    bounds = [inner[i] for i in chosen]

    # trim long pauses (and leading/trailing silence), keeping a time map raw -> trimmed
    cuts = [(0.0, max(0.0, speech_start - 0.05))]
    for a, b in runs:
        if a > speech_start and b < speech_end and b - a > MAX_GAP:
            cuts.append((a + MAX_GAP / 2, b - MAX_GAP / 2))
    keep, t = [], 0.0
    for a, b in cuts:
        if b > a:
            keep.append((t, a))
            t = b
    keep.append((t, min(total, speech_end + 0.25)))
    fade = int(0.006 * sr)
    pieces = []
    for a, b in keep:
        seg = x[int(a * sr):int(b * sr)].copy()
        if len(seg) > 2 * fade:
            seg[:fade] *= np.linspace(0, 1, fade)
            seg[-fade:] *= np.linspace(1, 0, fade)
        pieces.append(seg)
    trimmed = np.concatenate(pieces)

    def remap(ts):
        return max(0.0, ts - sum(min(b, ts) - a for a, b in cuts if ts > a and b > a))

    trim = prefix + "_trim.wav"
    sf.write(trim, trimmed, sr)
    subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-i", trim, "-af", f"atempo={TEMPO}", "-ar", str(SR),
                    prefix + ".wav"], check=True)
    dur = sf.info(prefix + ".wav").duration
    edges = [speech_start] + [x_ for a, b in bounds for x_ in (a, b)] + [speech_end]
    beats = []
    for i, line in enumerate(lines):
        st, en = edges[2 * i], edges[2 * i + 1]
        beats.append({"text": line, "start": round(remap(st) / TEMPO, 3), "end": round(remap(en) / TEMPO, 3)})
    json.dump({"voice": "recording:" + os.path.basename(src), "tempo": TEMPO, "duration": round(dur, 3), "beats": beats},
              open(prefix + ".json", "w", encoding="utf-8"), indent=2)
    for p in (raw, trim):
        try:
            os.remove(p)
        except OSError:
            pass
    print(f"Narration from {os.path.basename(src)}: {dur:.2f}s, {len(beats)} beats -> {prefix}.wav")
    for b in beats:
        print(f"  {b['start']:6.2f} {b['end']:6.2f}  {b['text'][:50]}")


if __name__ == "__main__":
    main()
