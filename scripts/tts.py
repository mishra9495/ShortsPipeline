"""Kokoro TTS: script text file -> WAV + per-sentence timing JSON.

Usage: tts-venv\\Scripts\\python.exe tts.py <script.txt> <out_prefix> [voice] [speed]
Each non-empty line of the script is one narration beat; timings are written per beat
so shots can be cut to the voice-over.
"""
import json
import sys

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

MODEL = r"D:\ShortsPipeline\tools\kokoro\kokoro-v1.0.onnx"
VOICES = r"D:\ShortsPipeline\tools\kokoro\voices-v1.0.bin"
GAP = 0.12  # seconds of silence between beats; keeps delivery rapid


def main():
    script_path, out_prefix = sys.argv[1], sys.argv[2]
    voice = sys.argv[3] if len(sys.argv) > 3 else "am_michael"
    speed = float(sys.argv[4]) if len(sys.argv) > 4 else 1.15

    kokoro = Kokoro(MODEL, VOICES)
    lines = [l.strip() for l in open(script_path, encoding="utf-8") if l.strip()]
    chunks, beats, t = [], [], 0.0
    sr = 24000
    for line in lines:
        samples, sr = kokoro.create(line, voice=voice, speed=speed, lang="en-us")
        dur = len(samples) / sr
        beats.append({"text": line, "start": round(t, 3), "end": round(t + dur, 3)})
        chunks.append(samples)
        chunks.append(np.zeros(int(GAP * sr), dtype=samples.dtype))
        t += dur + GAP
    audio = np.concatenate(chunks)
    sf.write(out_prefix + ".wav", audio, sr)
    json.dump({"voice": voice, "speed": speed, "duration": round(t, 3), "beats": beats},
              open(out_prefix + ".json", "w"), indent=2)
    print(f"{voice}: {t:.2f}s, {len(beats)} beats -> {out_prefix}.wav")


if __name__ == "__main__":
    main()
