"""Per-beat narration vs. effects level in a mix (least-squares separation of the known VO)."""
import json
import sys

import numpy as np
import soundfile as sf

mix_path, vo_path, meta_path = sys.argv[1:4]
m, sr = sf.read(mix_path)
v, _ = sf.read(vo_path)
j = json.load(open(meta_path))
v = np.pad(v, (0, max(0, len(m) - len(v))))[: len(m)]
k = np.dot(m, v) / np.dot(v, v)
res = m - k * v


def db(x):
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)


for b in j["beats"]:
    a, e = int(b["start"] * sr), int(b["end"] * sr)
    print(f"{b['start']:5.1f}s VO {db(k * v[a:e]):6.1f} dB  FX {db(res[a:e]):6.1f} dB  gap {db(k * v[a:e]) - db(res[a:e]):5.1f}  {b['text'][:42]}")
