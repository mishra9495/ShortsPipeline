# Queue item templates

Every `queue/<slug>/` needs these files before the nightly Windows render (`scripts/daily_render.ps1`) will pick it up:

| File | Purpose |
| --- | --- |
| `script.txt` | Narration, exactly one beat per line (the scene template expects 10 lines). |
| `metadata.txt` | YouTube metadata in the `final/sneeze_short_youtube_metadata.txt` format. |
| `scene.py` | Blender scene builder. Start from `scene_template.py`. |
| `mix.py` | Sound design and mix. Start from `mix_template.py`. |
| `keywords.txt` | Optional. Comma-separated caption words to highlight. |
| `scene_notes.txt`, `mix_notes.txt` | Human-readable direction. They are not executed. |

Items missing `script.txt`, `scene.py` or `mix.py` are skipped and logged.

## Scene contract

- Invocation: `blender -b --python scene.py -- <ROOT>/blend/<slug>.blend [vo=<wav>] [beats=<json>]`. With no `vo=` or `beats=`, the narration is found from the output path in `<ROOT>/audio/`.
- The script opens the character `.blend` itself (`blend/char_hero.blend`, or `blend/char_heroine.blend` for a female lead) and saves the scene to the given path.
- Timing comes only from the beats JSON (`{"duration", "beats": [{"start","end","text"}]}`), so any narration take works. Never hard-code seconds.
- Characters are animated procedurally on the `mixamorig:` bones (see `curves()` in the template). The repo has no Mixamo FBX library.
- The frame range is `1..fr(duration)+36`. `render_anim.py` clamps to it.

## Mix contract

`python mix.py <beats.json> <vo.wav> <out_mix.wav>`, using numpy and soundfile only. Cue effects relative to beat times, and keep any cue fractions in sync with `scene.py`.

## Test before committing

```bash
bash templates/test/run_test.sh <slug> 24,75,130,200,330,440,540,680,800,940,1110,1250
```

The first run installs `bpy` (Blender as a Python module, about 375 MB) into `/tmp/shorts_test`. The script builds a stand-in hero, renders low-res stills from the frames you list and writes a contact sheet. Look at it, then fix the framing before you commit.
