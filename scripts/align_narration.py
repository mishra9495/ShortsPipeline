"""Word-level forced-alignment of the narration via faster-whisper, then match words to the
known 10 script beats to get accurate beat start/end times for retiming the scene.

Usage: tts-venv\\Scripts\\python.exe align_narration.py <audio.wav> <script.txt> <out.json>
"""
import json
import re
import sys

from faster_whisper import WhisperModel

AUDIO, SCRIPT, OUT = sys.argv[1:4]

beats_text = [l.strip() for l in open(SCRIPT, encoding="utf-8") if l.strip()]


def norm(w):
    return re.sub(r"[^a-z']", "", w.lower())


model = WhisperModel("small.en", device="cpu", compute_type="int8")
segments, info = model.transcribe(AUDIO, word_timestamps=True, beam_size=5, language="en")

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
        raise RuntimeError(f"beat {bi} ({text!r}) matched 0 words starting at asr idx {wi}")
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
