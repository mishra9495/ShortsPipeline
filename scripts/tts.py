"""Kokoro TTS: script text file -> WAV + per-sentence timing JSON.

Usage: tts-venv\\Scripts\\python.exe tts.py <script.txt> <out_prefix | out.wav> [voice] [speed|auto]
Each non-empty line of the script is one narration beat; timings are written per beat
so shots can be cut to the voice-over.

speed "auto" (the default) re-reads once at the speed that lands the whole read at TARGET_WPM: the sneeze
short (ElevenLabs Daniel, +15% tempo) ran 117 words in 37 s = 190 wpm, and Zack D shorts sit at ~185-195.
Kokoro at speed 1.15 runs ~222 wpm, which is too fast.
"""
import json
import sys

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

MODEL = r"D:\ShortsPipeline\tools\kokoro\kokoro-v1.0.onnx"
VOICES = r"D:\ShortsPipeline\tools\kokoro\voices-v1.0.bin"
GAP = 0.12  # seconds of silence between beats; keeps delivery rapid
TARGET_WPM = 190.0
WPM_OK = (182.0, 198.0)


def read(kokoro, lines, voice, speed):
    chunks, beats, t = [], [], 0.0
    sr = 24000
    for line in lines:
        samples, sr = kokoro.create(line, voice=voice, speed=speed, lang="en-us")
        dur = len(samples) / sr
        beats.append({"text": line, "start": round(t, 3), "end": round(t + dur, 3)})
        chunks.append(samples)
        chunks.append(np.zeros(int(GAP * sr), dtype=samples.dtype))
        t += dur + GAP
    return np.concatenate(chunks), sr, beats, t


def main():
    script_path, out_prefix = sys.argv[1], sys.argv[2]
    # Accept "<name>.wav" as well as a bare prefix: daily_render.ps1 used to pass the .wav path,
    # which silently produced "<name>.wav.wav" and failed the pipeline's existence check.
    if out_prefix.lower().endswith(".wav"):
        out_prefix = out_prefix[:-4]
    voice = sys.argv[3] if len(sys.argv) > 3 else "am_michael"
    arg = sys.argv[4] if len(sys.argv) > 4 else "auto"

    kokoro = Kokoro(MODEL, VOICES)
    lines = [l.strip() for l in open(script_path, encoding="utf-8") if l.strip()]
    words = sum(len(l.split()) for l in lines)
    speed = 1.0 if arg == "auto" else float(arg)
    audio, sr, beats, t = read(kokoro, lines, voice, speed)
    wpm = words / t * 60
    print(f"{voice} speed {speed:.3f}: {words} words in {t:.2f}s = {wpm:.0f} wpm")
    if arg == "auto" and not (WPM_OK[0] <= wpm <= WPM_OK[1]):
        speed = max(0.7, min(1.4, speed * TARGET_WPM / wpm))
        audio, sr, beats, t = read(kokoro, lines, voice, speed)
        wpm = words / t * 60
        print(f"{voice} re-read at speed {speed:.3f}: {t:.2f}s = {wpm:.0f} wpm")
    sf.write(out_prefix + ".wav", audio, sr)
    json.dump({"voice": voice, "speed": round(speed, 3), "wpm": round(wpm, 1), "duration": round(t, 3), "beats": beats},
              open(out_prefix + ".json", "w"), indent=2)
    print(f"{voice}: {t:.2f}s, {len(beats)} beats -> {out_prefix}.wav")


if __name__ == "__main__":
    main()
