"""ElevenLabs "Daniel" narration (the sneeze short's voice): script -> WAV + exact per-beat timings.

Usage: python tts_elevenlabs.py <script.txt> <out_prefix | out.wav>
Writes <prefix>.wav and <prefix>.json ({"voice", "duration", "beats": [{"text","start","end"}]}).

Same treatment as the sneeze short: one natural read of the whole script, long pauses trimmed,
tempo +15% (pitch kept). Beat timings come from ElevenLabs' character alignment, so no Whisper
alignment is needed.

API key: env ELEVENLABS_API_KEY, or the first line of D:\\ShortsPipeline\\secrets\\elevenlabs_api_key.txt
(secrets/ is gitignored). Optional voice override: secrets\\elevenlabs_voice_id.txt.
There is deliberately NO fallback voice: the owner only accepts Daniel.
"""
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

import numpy as np
import soundfile as sf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS = os.path.join(ROOT, "secrets")
DANIEL = "onwK4e9ZLuTAKqWW03F9"          # ElevenLabs premade voice "Daniel"
MODEL = "eleven_multilingual_v2"
TEMPO = 1.15                              # +15%, as on the sneeze short
MAX_GAP = 0.14                            # longest pause kept between words/sentences (s)
SR = 44100


def secret(name):
    p = os.path.join(SECRETS, name)
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            return fh.readline().strip()
    return ""


def ffmpeg_bin():
    for c in ("ffmpeg", os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe")):
        try:
            subprocess.run([c, "-version"], capture_output=True, check=True)
            return c
        except Exception:
            continue
    raise SystemExit("ERROR: ffmpeg not found")


def main():
    script_path, out = sys.argv[1], sys.argv[2]
    prefix = out[:-4] if out.lower().endswith(".wav") else out
    key = os.environ.get("ELEVENLABS_API_KEY") or secret("elevenlabs_api_key.txt")
    if not key:
        raise SystemExit("ERROR: no ElevenLabs API key (set ELEVENLABS_API_KEY or create secrets\\elevenlabs_api_key.txt)")
    voice = secret("elevenlabs_voice_id.txt") or DANIEL
    lines = [l.strip() for l in open(script_path, encoding="utf-8") if l.strip()]
    text = " ".join(lines)
    spans, pos = [], 0                    # character span of each beat inside `text`
    for l in lines:
        spans.append((pos, pos + len(l)))
        pos += len(l) + 1

    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps?output_format=mp3_44100_192",
        data=json.dumps({"text": text, "model_id": MODEL,
                         "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.15,
                                            "use_speaker_boost": True}}).encode(),
        headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"ERROR: ElevenLabs HTTP {e.code}: {e.read()[:300]!r}")
    al = resp.get("alignment") or resp.get("normalized_alignment")
    chars, c_start, c_end = al["characters"], al["character_start_times_seconds"], al["character_end_times_seconds"]
    if "".join(chars) != text:            # alignment indexes the text we sent; bail loudly if not
        print("WARN alignment text differs from the script; mapping by position")

    mp3 = prefix + "_raw.mp3"
    with open(mp3, "wb") as fh:
        fh.write(base64.b64decode(resp["audio_base64"]))
    ff = ffmpeg_bin()
    raw_wav = prefix + "_raw.wav"
    subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-i", mp3, "-ac", "1", "-ar", str(SR), raw_wav], check=True)
    x, sr = sf.read(raw_wav, dtype="float32")

    # word spans (s) from the character alignment; pauses = gaps between consecutive words
    words, cur = [], None
    for i, ch in enumerate(chars):
        if ch.strip() and ch not in "\"'":
            if cur is None:
                cur = [i, i]
            cur[1] = i
        elif cur is not None:
            words.append(tuple(cur))
            cur = None
    if cur is not None:
        words.append(tuple(cur))
    cuts = []                             # (start_s, end_s) removed from the raw audio
    for (a0, a1), (b0, b1) in zip(words, words[1:]):
        g0, g1 = c_end[a1] + 0.02, c_start[b0] - 0.02
        if g1 - g0 > MAX_GAP:
            cuts.append((g0 + MAX_GAP / 2, g1 - MAX_GAP / 2))
    lead = max(0.0, c_start[words[0][0]] - 0.05)
    if lead > 0:
        cuts.insert(0, (0.0, lead))
    tail = c_end[words[-1][1]] + 0.25
    keep, t = [], 0.0
    for a, b in cuts:
        keep.append((t, a))
        t = b
    keep.append((t, min(tail, len(x) / sr)))
    fade = int(0.006 * sr)
    pieces = []
    for a, b in keep:
        seg = x[int(a * sr):int(b * sr)].copy()
        if len(seg) > 2 * fade:
            seg[:fade] *= np.linspace(0, 1, fade)
            seg[-fade:] *= np.linspace(1, 0, fade)
        pieces.append(seg)
    trimmed = np.concatenate(pieces)

    def remap(ts):                        # raw time -> trimmed time
        removed = sum(min(b, ts) - a for a, b in cuts if ts > a)
        return max(0.0, ts - removed)

    trim_wav = prefix + "_trim.wav"
    sf.write(trim_wav, trimmed, sr)
    subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-i", trim_wav, "-af", f"atempo={TEMPO}",
                    "-ar", str(SR), prefix + ".wav"], check=True)
    dur = sf.info(prefix + ".wav").duration
    beats = []
    for line, (s0, s1) in zip(lines, spans):
        idx = [i for i in range(s0, min(s1, len(chars))) if chars[i].strip()]
        st, en = remap(c_start[idx[0]]) / TEMPO, remap(c_end[idx[-1]]) / TEMPO
        beats.append({"text": line, "start": round(st, 3), "end": round(en, 3)})
    json.dump({"voice": f"elevenlabs:{voice}", "tempo": TEMPO, "duration": round(dur, 3), "beats": beats},
              open(prefix + ".json", "w", encoding="utf-8"), indent=2)
    for p in (mp3, raw_wav, trim_wav):
        try:
            os.remove(p)
        except OSError:
            pass
    print(f"ElevenLabs {voice}: {dur:.2f}s, {len(beats)} beats -> {prefix}.wav")


if __name__ == "__main__":
    main()
