"""Word-level forced-alignment of the narration via faster-whisper, then match words to the
known 10 script beats to get accurate beat start/end times for retiming the scene.

Usage: tts-venv\\Scripts\\python.exe align_narration.py <audio.wav> <script.txt> <out.json>
"""
import json
import os
import re
import sys
import wave

AUDIO, SCRIPT, OUT = sys.argv[1:4]


def tts_timing_fallback(reason):
    """No ASR available: reuse tts.py's per-beat timings (<slug>_vo.json next to the audio), scaled to
    this audio's length so a silence-trimmed take still lines up. Keeps the nightly render going."""
    base = re.sub(r"(_final|_trim)+$", "", os.path.splitext(AUDIO)[0])
    src = base + ".json"
    if not os.path.exists(src):
        raise SystemExit(f"alignment failed ({reason}) and no TTS timing file {src}")
    meta = json.load(open(src, encoding="utf-8"))
    with wave.open(AUDIO, "rb") as w:
        dur = w.getnframes() / float(w.getframerate())
    k = dur / float(meta["duration"])
    beats = [{"text": b["text"], "start": round(b["start"] * k, 3), "end": round(b["end"] * k, 3)} for b in meta["beats"]]
    json.dump({"duration": round(dur, 3), "beats": beats}, open(OUT, "w", encoding="utf-8"), indent=1)
    print(f"WARN alignment fallback ({reason}): TTS timings from {src} scaled x{k:.3f}")
    print("WROTE", OUT)
    sys.exit(0)


try:
    from faster_whisper import WhisperModel
except Exception as exc:  # module missing or broken install
    tts_timing_fallback(f"faster_whisper unavailable: {exc}")

beats_text = [l.strip() for l in open(SCRIPT, encoding="utf-8") if l.strip()]


def norm(w):
    return re.sub(r"[^a-z']", "", w.lower())


try:
    model = WhisperModel("small.en", device="cpu", compute_type="int8")
    segments, info = model.transcribe(AUDIO, word_timestamps=True, beam_size=5, language="en")
    segments = list(segments)
except Exception as exc:  # e.g. model download blocked
    tts_timing_fallback(f"whisper failed: {exc}")

words = []
for seg in segments:
    for w in seg.words:
        words.append((norm(w.word), w.start, w.end))
words = [w for w in words if w[0]]

print("TRANSCRIBED_WORDS", len(words), "DURATION", info.duration)
for w in words:
    print("  ", w)

# Greedy sequential match: walk the known beat words in order against the ASR word stream.
beats = []
wi = 0
for bi, text in enumerate(beats_text):
    btoks = [norm(w) for w in text.split()]
    btoks = [t for t in btoks if t]
    start_idx = wi
    matched = 0
    bj = 0
    scan = wi
    # advance through ASR words, matching beat tokens loosely (allow skips on either side)
    while scan < len(words) and bj < len(btoks):
        if words[scan][0] == btoks[bj] or words[scan][0].startswith(btoks[bj][:4]):
            bj += 1
            matched += 1
        scan += 1
    end_idx = scan
    if matched == 0:
        tts_timing_fallback(f"beat {bi} ({text!r}) matched 0 words starting at asr idx {wi}")
    beat_start = words[start_idx][1]
    beat_end = words[end_idx - 1][2]
    beats.append({"text": text, "start": beat_start, "end": beat_end})
    wi = end_idx

duration = words[-1][2] if words else info.duration
out = {"duration": duration, "beats": beats}
json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1)
print("WROTE", OUT)
for b in beats:
    print(f"  {b['start']:6.2f} - {b['end']:6.2f}  {b['text'][:50]}")
