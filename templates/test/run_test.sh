#!/usr/bin/env bash
# Validate a queue item's scene.py + mix.py in a Linux container (no GPU, no real hero):
#   bash templates/test/run_test.sh <slug> [frames,to,render]
# Builds a stand-in Mixamo-named hero, fake narration timed from script.txt, runs scene.py and
# mix.py, renders low-res stills and tiles them into $WORK/sheet.png for a visual check.
set -euo pipefail
SLUG="$1"; STILLS="${2:-}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="${WORK:-/tmp/shorts_test}"
VENV="$WORK/bpyenv"
mkdir -p "$WORK/root/blend" "$WORK/root/audio"
ln -sfn "$REPO/scripts" "$WORK/root/scripts"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q bpy==5.0.1 numpy soundfile   # Blender as a Python module (Python 3.11)
fi
PY="$VENV/bin/python"
[ -f "$WORK/root/blend/char_hero.blend" ] || "$PY" "$REPO/templates/test/make_standin.py" -- "$WORK/root/blend/char_hero.blend"
A="$WORK/root/audio/$SLUG"
"$PY" "$REPO/templates/test/fake_vo.py" "$REPO/queue/$SLUG/script.txt" "${A}_vo"
cp "${A}_vo.json" "${A}_beats.json"; cp "${A}_vo.wav" "${A}_vo_final.wav"
rm -f "$WORK/root/blend/${SLUG}"_f*.png
ARGS=(device=cpu pct=25 samples=12)
[ -n "$STILLS" ] && ARGS+=("stills=$STILLS")
"$PY" "$REPO/queue/$SLUG/scene.py" -- "$WORK/root/blend/$SLUG.blend" "${ARGS[@]}" 2>&1 | grep -E "ARGS|SAVED|RENDERED|WARN|Error|Traceback|line [0-9]"
"$PY" -I "$REPO/queue/$SLUG/mix.py" "${A}_beats.json" "${A}_vo_final.wav" "${A}_mix.wav"
if [ -n "$STILLS" ]; then
  ffmpeg -y -hide_banner -loglevel error -pattern_type glob -i "$WORK/root/blend/${SLUG}_f*.png" \
    -vf "scale=180:320,tile=7x2:padding=4" -frames:v 1 "$WORK/sheet.png" && echo "SHEET $WORK/sheet.png"
fi
echo "TEST OK: $SLUG"
