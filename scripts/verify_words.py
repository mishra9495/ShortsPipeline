"""Transcribe audio and compare the word sequence against the expected script to catch
any dropped/garbled words before trusting the audio for the final retime.
Usage: tts-venv\\Scripts\\python.exe verify_words.py <audio.wav> <script.txt>
"""
import re
import sys

from faster_whisper import WhisperModel

AUDIO, SCRIPT = sys.argv[1], sys.argv[2]


def norm(w):
    return re.sub(r"[^a-z']", "", w.lower())


expected = []
for line in open(SCRIPT, encoding="utf-8"):
    expected += [norm(w) for w in line.split() if norm(w)]

model = WhisperModel("small.en", device="cpu", compute_type="int8")
segments, info = model.transcribe(AUDIO, word_timestamps=True, beam_size=5, language="en")
got = []
for seg in segments:
    for w in seg.words:
        nw = norm(w.word)
        if nw:
            got.append(nw)

print(f"DURATION {info.duration:.2f}s  expected_words={len(expected)}  got_words={len(got)}")
# simple longest-common-subsequence-ish diff to spot drops
i = j = 0
missing = []
while i < len(expected) and j < len(got):
    if expected[i] == got[j] or got[j].startswith(expected[i][:4]) or expected[i].startswith(got[j][:4]):
        i += 1
        j += 1
    else:
        # try skipping a got-word (insertion) first, else mark expected as missing
        if j + 1 < len(got) and (expected[i] == got[j + 1]):
            j += 1
        else:
            missing.append((i, expected[i]))
            i += 1
if i < len(expected):
    missing += [(k, expected[k]) for k in range(i, len(expected))]
print("POSSIBLY_MISSING", missing)
print("OK" if not missing else "PROBLEM")
