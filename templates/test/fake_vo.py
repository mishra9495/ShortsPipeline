import json, sys, numpy as np, soundfile as sf
script, prefix = sys.argv[1], sys.argv[2]
SR = 24000; lines = [l.strip() for l in open(script) if l.strip()]
t, beats, chunks = 0.0, [], []
rng = np.random.default_rng(1)
for l in lines:
    d = len(l.split()) / 2.4
    n = int(d * SR); tt = np.arange(n) / SR
    syl = (0.5 + 0.5 * np.sin(2 * np.pi * 4.5 * tt)) ** 2
    v = (np.sin(2 * np.pi * 140 * tt) * 0.4 + rng.standard_normal(n) * 0.05) * syl
    chunks += [v.astype(np.float32), np.zeros(int(0.12 * SR), np.float32)]
    beats.append({"text": l, "start": round(t, 3), "end": round(t + d, 3)}); t += d + 0.12
sf.write(prefix + ".wav", np.concatenate(chunks), SR)
json.dump({"duration": round(t, 3), "beats": beats}, open(prefix + ".json", "w"), indent=1)
print("FAKE VO", round(t, 2), "s")
