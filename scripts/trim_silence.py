"""Compact long pauses in a narration down to a short fixed gap (keeps short natural
breath-pauses between words/clauses untouched, only tightens long sentence-boundary gaps).

Usage: tts-venv\\Scripts\\python.exe trim_silence.py <in.wav> <out.wav> [max_gap_sec] [thresh_db]
"""
import sys

import numpy as np
import soundfile as sf

IN, OUT = sys.argv[1], sys.argv[2]
MAX_GAP = float(sys.argv[3]) if len(sys.argv) > 3 else 0.12   # compacted gap length kept
THRESH_DB = float(sys.argv[4]) if len(sys.argv) > 4 else -38.0
MIN_SILENCE = 0.28  # only compact runs of silence longer than this

x, sr = sf.read(IN, dtype="float32")
win = int(0.02 * sr)
env = np.sqrt(np.convolve(x ** 2, np.ones(win) / win, mode="same") + 1e-12)
db = 20 * np.log10(env + 1e-9)
is_silent = db < THRESH_DB

# find runs of silence
runs = []
i = 0
n = len(is_silent)
while i < n:
    if is_silent[i]:
        j = i
        while j < n and is_silent[j]:
            j += 1
        runs.append((i, j))
        i = j
    else:
        i += 1

keep_gap = int(MAX_GAP * sr)
min_len = int(MIN_SILENCE * sr)
fade = int(0.008 * sr)

out_chunks = []
cursor = 0
removed_total = 0
for a, b in runs:
    if b - a < min_len:
        continue
    # keep audio up to a + keep_gap/2, then splice to b - keep_gap/2 (drop the middle)
    cut_start = a + keep_gap // 2
    cut_end = b - keep_gap // 2
    if cut_end <= cut_start:
        continue
    out_chunks.append(x[cursor:cut_start])
    cursor = cut_end
    removed_total += cut_end - cut_start
out_chunks.append(x[cursor:])
y = np.concatenate(out_chunks).astype(np.float32)

# gentle fades at any splice point are already implicit (silence itself), no clicks expected
sf.write(OUT, y, sr)
print(f"IN {len(x)/sr:.2f}s OUT {len(y)/sr:.2f}s removed {removed_total/sr:.2f}s across {sum(1 for a,b in runs if b-a>=min_len)} long pauses")
