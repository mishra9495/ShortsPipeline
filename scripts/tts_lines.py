"""Generate short one-off character vocal lines with Kokoro.
Usage: tts-venv\\Scripts\\python.exe tts_lines.py <voice> <speed> <out.wav> "<text>" [<out2.wav> "<text2>" ...]
"""
import sys

import soundfile as sf
from kokoro_onnx import Kokoro

kokoro = Kokoro(r"D:\ShortsPipeline\tools\kokoro\kokoro-v1.0.onnx", r"D:\ShortsPipeline\tools\kokoro\voices-v1.0.bin")
voice, speed = sys.argv[1], float(sys.argv[2])
pairs = sys.argv[3:]
for out, text in zip(pairs[0::2], pairs[1::2]):
    samples, sr = kokoro.create(text, voice=voice, speed=speed, lang="en-us")
    sf.write(out, samples, sr)
    print(out, round(len(samples) / sr, 2), "s", text)
