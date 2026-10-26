# ShortsPipeline

3D animated medical and science YouTube Shorts. A cloud agent queues topics. A Windows PC renders one finished queue item each night at 23:30 IST with `scripts/daily_render.ps1`, then uploads it to YouTube as private.

## Queue items must be render-ready

The nightly render only picks up a `queue/<slug>/` folder that contains all of these files:

- `script.txt`: exactly 10 narration lines, one beat per line, 90-100 words.
- `metadata.txt`: in the format of `final/sneeze_short_youtube_metadata.txt`.
- `scene.py`: the Blender scene builder. Adapt it from `templates/scene_template.py`.
- `mix.py`: the sound design. Adapt it from `templates/mix_template.py`.
- `keywords.txt`: optional caption highlight words.

Folders without `scene.py` or `mix.py` are skipped forever. When you queue a topic, write those two files too. If you find an existing queue item without them, write them before adding a new topic.

The contract for both files is in `templates/README.md`. Before committing, test with `bash templates/test/run_test.sh <slug> <frames>`. It runs the scene against a stand-in hero, renders low-res stills and makes a contact sheet. Look at the sheet and fix framing problems.

## Facts about this repo

- There is no `animation/` folder and no Mixamo FBX library. Characters are animated procedurally on the `mixamorig:` bones.
- The characters are `blend/char_hero.blend` (male) and `blend/char_heroine.blend` (female). The female file is built on demand from `scripts/preset_heroine.json`. Both exist only on the Windows PC.
- The nightly render pushes its log to `logs/daily_*.log`. Read the newest one at the start of each run and fix any failure it shows.
- The updated daily routine prompt is in `templates/ROUTINE_PROMPT.md`.
