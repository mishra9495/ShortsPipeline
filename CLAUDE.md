# ShortsPipeline

3D animated medical and science YouTube Shorts. A cloud agent queues topics. A Windows PC renders one finished queue item each night at 23:30 IST with `scripts/daily_render.ps1`, then uploads it to YouTube as public.

## Owner's standing rules (never break these)

- NEVER burn captions or subtitles into any video. No `make_captions.py`, no `subtitles=` filter, no on-screen narration text.
- Narration voice: ElevenLabs "Daniel" (the sneeze short's voice) when available, with pauses trimmed and tempo +15%. On 2026-10-27 the owner had no ElevenLabs key and approved a free voice: Kokoro `am_fenrir`, the closest free match to Daniel's pitch and timbre. `daily_render.ps1` picks the voice in this order:
  1. a ready-made `queue/<slug>/narration.wav` with its `narration.json`
  2. a `narration.mp3` downloaded from the ElevenLabs website
  3. an ElevenLabs API key
  4. free Kokoro `am_fenrir`
- Quality bar is Zack D Films. Never ship primitive placeholder geometry (box cars, capsule people) in a final video.
- A queue folder containing a `HOLD` file is never rendered.
- Uploads are ALWAYS public, automatically (owner's instruction, 2026-10-27). Never upload as private or unlisted. YouTube itself locks uploads from an unaudited Google Cloud API project as private; `scripts/upload_youtube.py` logs a WARN when that happens.
- `scripts/youtube_upload.py` is a frozen copy of the PC's old uploader, kept byte-identical so the PC's `git pull` does not abort on its local edit to that file. Do not edit it; the pipeline uses `scripts/upload_youtube.py`.

## Queue items must be render-ready

The nightly render only picks up a `queue/<slug>/` folder that contains all of these files:

- `script.txt`: exactly 10 narration lines, one beat per line, 90-100 words.
- `metadata.txt`: in the format of `final/sneeze_short_youtube_metadata.txt`.
- `scene.py`: the Blender scene builder. Adapt it from `templates/scene_template.py`.
- `mix.py`: the sound design. Adapt it from `templates/mix_template.py`.

Folders without `scene.py` or `mix.py` are skipped forever. When you queue a topic, write those two files too. If you find an existing queue item without them, write them before adding a new topic.

The contract for both files is in `templates/README.md`. Before committing, test with `bash templates/test/run_test.sh <slug> <frames>`. It runs the scene against a stand-in hero, renders low-res stills and makes a contact sheet. Look at the sheet and fix framing problems.

## Facts about this repo

- Build every model in Blender from code. Don't download assets. Use `scripts/kit.py` (props, sets, vehicles, anatomy), `scripts/actor.py` (character performance, any fps: `follow`/`spring` overlap, `timewarp` slow motion, `bake_gaze` eyes) and `scripts/shot.py` (render setup and cameras that keep moving through every key, DOF from subject size, orbit, kick and plunge moves).
- Follow `templates/STYLE_GUIDE.md` (Zack D research): 12-20 shots of 1.5-3 s, every shot moving, frame 1 is the thumbnail, one slow-motion money moment, titles of 4-7 words with exactly one emoji at the end.
- A queue folder with `PREVIEW` gets full-quality stills rendered on the PC. They are pushed to `previews/<slug>/` for review, and the full render waits until `PREVIEW` is removed.

- `D:\ShortsPipeline\animation\` on the Windows PC holds 156 Mixamo FBX clips (90 MB, PC-local, never committed). `animation_manifest.txt` in the repo root lists every clip so you can see what exists. It is Mixamo's action/combat pack: only about 25 clips (sitting, injured, lying, talking, scared, pointing) suit medical stories, and `scripts/retarget.py` has never been validated end to end on `char_hero`. Characters are therefore animated procedurally on the `mixamorig:` bones with `scripts/actor.py` (the method that produced the approved brain-leaking-nose video). Reach for a Mixamo clip only when the manifest has a direct match for the beat AND the retarget has been proven with PREVIEW stills first.
- The characters are `blend/char_hero.blend` (male) and `blend/char_heroine.blend` (female). The female file is built on demand from `scripts/preset_heroine.json`. Both exist only on the Windows PC.
- The nightly render pushes its log to `logs/daily_*.log`. Read the newest one at the start of each run and fix any failure it shows.
- The updated daily routine prompt is in `templates/ROUTINE_PROMPT.md`.
- Narration pace target is about 190 words per minute (the sneeze short: 117 words in 37 seconds). `scripts/tts.py ... auto` re-reads Kokoro at the speed that lands 182-198 wpm (Kokoro at speed 1.15 was 222 wpm, too fast). A 100-word script gives about 31 seconds.
- `scripts/tts.py` imports `kokoro_onnx` (not the PyTorch `kokoro` package) and loads `tools/kokoro/kokoro-v1.0.onnx` + `voices-v1.0.bin`. Those exist only inside `tools/tts-venv/` on the Windows PC, so `daily_render.ps1` runs tts.py with `$TTSPY` (that venv's python), never with `$PYTHON`. Every other script runs under `$PYTHON` (system Python 3.11). Do not "unify" these two.
