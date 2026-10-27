# Queue item templates

**Rebuilt pipeline status.** The v2 reference scene is `completed/brain-leaking-nose/scene.py` (rendered and uploaded 2026-10-27). It uses `scripts/kit.py` (every model built in Blender) and `scripts/actor.py` (character acting). The newest scene on the full v3 toolkit (kit + actor + shot) is `queue/tooth-in-eye/scene.py` (reviewed with per-shot stills 2026-10-28); read it before writing a new one. The older `scene_template.py` and `mix_template.py` are v1 and were rejected for quality.

**v3 helpers (from the Zack D research in `STYLE_GUIDE.md`).** New scenes should use them instead of copying the v2 camera code:

- `scripts/shot.py`: `setup_render` (motion blur samples START, so cuts between sets never smear), `Cameras.cam` (one monotone spline through all keys, so the camera never stops at a key and is already moving on the cut; `depth=` sets the f-stop from the subject size; `orbit`, `kicks`, `plunge_in` and `plunge_out` for X-ray fly-ins; `shift_y` puts faces on the upper third), `markers` and `check_shots`.
- `scripts/actor.py`: `follow`/`spring`/`delay` for overlap and settle down a chain, `timewarp` for the slow-motion money moment, `Actor.bake_gaze` for eyes that look at things, with saccades.
- `scripts/kit.py`: `room(openings=...)` cuts real window holes (the sky card shows through), plus `crumpled_tissue`, `shards`, `crumple` (car crush shape key), `skull`, `endoscope`, `forceps`, `instrument_tray`, `iv_pole`, `bone_mat` and `paper_mat`.

Every `queue/<slug>/` needs these files before the nightly Windows render (`scripts/daily_render.ps1`) will pick it up:

| File | Purpose |
| --- | --- |
| `script.txt` | Narration, exactly one beat per line (the scene template expects 10 lines). |
| `metadata.txt` | YouTube metadata in the `final/sneeze_short_youtube_metadata.txt` format. |
| `scene.py` | Blender scene builder. Start from `scene_template.py`. |
| `mix.py` | Sound design and mix. Start from `mix_template.py`. |
| `scene_notes.txt`, `mix_notes.txt` | Human-readable direction. They are not executed. |

Items missing `script.txt`, `scene.py` or `mix.py` are skipped and logged.

## Scene contract

- Invocation: `blender -b --python scene.py -- <ROOT>/blend/<slug>.blend [vo=<wav>] [beats=<json>]`. With no `vo=` or `beats=`, the narration is found from the output path in `<ROOT>/audio/`.
- The script opens the character `.blend` itself (`blend/char_hero.blend`, or `blend/char_heroine.blend` for a female lead) and saves the scene to the given path.
- Timing comes only from the beats JSON (`{"duration", "beats": [{"start","end","text"}]}`), so any narration take works. Never hard-code seconds.
- Characters are animated procedurally on the `mixamorig:` bones (see `curves()` in the template). A 156-clip Mixamo FBX library exists on the Windows PC only (see `animation_manifest.txt` in the repo root); it is not in git and has no validated retarget path, so treat it as optional reference, never as a dependency.
- The frame range is `1..fr(duration)+36`. `render_anim.py` clamps to it.

## Mix contract

`python mix.py <beats.json> <vo.wav> <out_mix.wav>`, using numpy and soundfile only. Cue effects relative to beat times, and keep any cue fractions in sync with `scene.py`.

## Test before committing

```bash
bash templates/test/run_test.sh <slug> 24,75,130,200,330,440,540,680,800,940,1110,1250
```

The first run installs `bpy` (Blender as a Python module, about 375 MB) into `/tmp/shorts_test`. The script builds a stand-in hero, renders low-res stills from the frames you list and writes a contact sheet. Look at it, then fix the framing before you commit.
