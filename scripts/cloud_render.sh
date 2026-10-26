#!/usr/bin/env bash
# Render one frame range of a prebuilt scene in a Claude Code cloud session (CPU Cycles via the
# `bpy` pip module) and push the encoded segment to its own branch, so several sessions can
# split one Short and the coordinator concatenates the parts.
#
# Usage: scripts/cloud_render.sh <scene.blend> <start> <end> <part-name> <branch>
# Resumable: frames already on disk are skipped (render_anim.py), so just re-run after a restart.
set -euo pipefail
BLEND=$1; START=$2; END=$3; PART=$4; BRANCH=$5
ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=${WORK:-/tmp/cloud_render}
VENV=$WORK/venv
FRAMES=$WORK/frames_$PART
mkdir -p "$WORK" "$FRAMES"

if [ ! -x "$VENV/bin/python" ]; then
  python3.11 -m venv "$VENV"
  "$VENV/bin/pip" install -q bpy==5.0.1
fi

# bpy-module stand-in for `blender -b <blend> --python render_anim.py -- <out> <start> <end>`
"$VENV/bin/python" - "$ROOT/$BLEND" "$FRAMES" "$START" "$END" "$ROOT/scripts/render_anim.py" <<'EOF'
import sys, bpy
blend, out, a, b, script = sys.argv[1:6]
bpy.ops.wm.open_mainfile(filepath=blend)
sys.argv = ["render_anim.py", "--", out, a, b]
exec(compile(open(script).read(), "render_anim.py", "exec"))
EOF

n=$(ls "$FRAMES"/f*.png | wc -l)
want=$((END - START + 1))
if [ "$n" -lt "$want" ]; then echo "ONLY $n/$want FRAMES - re-run to resume"; exit 1; fi

# near-lossless intermediate; the coordinator does the final encode
mkdir -p "$ROOT/renders/parts"
ffmpeg -loglevel error -y -framerate 30 -start_number "$START" -i "$FRAMES/f%04d.png" \
  -c:v libx264 -preset slow -crf 10 -pix_fmt yuv420p "$ROOT/renders/parts/$PART.mp4"

cd "$ROOT"
git checkout -B "$BRANCH"
git add -f "renders/parts/$PART.mp4"
git commit -m "Render part $PART (frames $START-$END)"
for i in 1 2 3 4; do git push -u origin "$BRANCH" --force && break || sleep $((2 ** i)); done
echo "PUSHED $PART frames $START-$END to $BRANCH"
