"""Beat timings (tts.py JSON) -> punchy 1-3 word ASS captions for a 1080x1920 Short.

Usage: python make_captions.py <vo.json> <out.ass> [keyword,keyword,...]
Kokoro gives per-beat (not per-word) timing, so words inside a beat are timed by length
(characters + a fixed per-word cost), which tracks fast narration closely enough for chunks.
"""
import json
import re
import sys

meta = json.load(open(sys.argv[1]))
OUT = sys.argv[2]
KEYS = [k.lower() for k in (sys.argv[3].split(",") if len(sys.argv) > 3 else [])]


def ts(t):
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


events = []
for b in meta["beats"]:
    words = b["text"].split()
    for k in (k for k in KEYS if " " in k):   # keep key phrases ("hay fever") in one chunk
        n = len(k.split())
        i = 0
        while i <= len(words) - n:
            if " ".join(re.sub(r"[^\w']", "", w).lower() for w in words[i:i + n]) == k:
                words[i:i + n] = [" ".join(words[i:i + n])]
            i += 1
    weights = [len(re.sub(r"\W", "", w)) + 2.5 + (3 if w[-1] in ",." else 0) for w in words]
    total, t = sum(weights), b["start"]
    span = b["end"] - b["start"]
    timed = []
    for w, wt in zip(words, weights):
        d = span * wt / total
        timed.append((w, t, t + d))
        t += d
    chunk = []
    for i, (w, s, e) in enumerate(timed):
        chunk.append((w, s, e))
        text = " ".join(c[0] for c in chunk)
        brk = (len(chunk) == 3 or len(text) >= 14 or w[-1] in ",.!?" or i == len(timed) - 1)
        if brk:
            events.append((chunk[0][1], chunk[-1][2], [c[0] for c in chunk]))
            chunk = []

lines = [
    "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "WrapStyle: 2", "",
    "[V4+ Styles]",
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
    "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
    "Style: Cap,Arial Black,104,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,1,0,1,9,3,2,50,50,640,1",
    "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
]
for i, (s, e, words) in enumerate(events):
    nxt = events[i + 1][0] if i + 1 < len(events) else e + 0.4
    e = min(max(e, s + 0.35), nxt)  # hold until the next chunk, never overlap it
    out = []
    for w in words:
        clean = re.sub(r"[^\w' ]", "", w).lower()
        hit = clean in KEYS
        word = re.sub(r"[,.]$", "", w).upper()
        out.append(r"{\c&H0000E6FF&}" + word + r"{\c&H00FFFFFF&}" if hit else word)
    pop = r"{\fscx82\fscy82\t(0,90,\fscx100\fscy100)}"
    lines.append(f"Dialogue: 0,{ts(s)},{ts(e)},Cap,,0,0,0,,{pop}{' '.join(out)}")
open(OUT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print(f"{len(events)} caption chunks -> {OUT}")
