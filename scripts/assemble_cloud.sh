#!/usr/bin/env bash
# Join the rendered parts of a Short, lay in the mix and burned captions, master to -14 LUFS.
#
# Usage: scripts/assemble_cloud.sh <slug> <parts_dir> <out.mp4> [font_dir]
#   parts_dir holds the part*.mp4 segments (from cloud_render.sh); they are joined in name order.
#   CAPTIONS=0 skips the burned-in captions.
# Needs: ffmpeg with libass, python3 with numpy + soundfile (for mix.py).
set -euo pipefail
SLUG=$1; PARTS=$2; OUT=$3; FONTS=${4:-$HOME/.fonts}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
Q=$ROOT/queue/$SLUG
WORK=$(mktemp -d)

ls "$PARTS"/part*.mp4 | sort | sed "s/^/file '/; s/$/'/" > "$WORK/list.txt"
ffmpeg -loglevel error -y -f concat -safe 0 -i "$WORK/list.txt" -c copy "$WORK/video.mp4"
frames=$(ffprobe -v error -count_packets -select_streams v:0 -show_entries stream=nb_read_packets -of csv=p=0 "$WORK/video.mp4")
echo "JOINED $frames frames"

python3 -I "$Q/mix.py" "$Q/vo.json" "$Q/vo.wav" "$WORK/mix.wav"
VF="format=yuv420p"
if [ "${CAPTIONS:-1}" != "0" ]; then
  python3 "$ROOT/scripts/make_captions.py" "$Q/vo.json" "$WORK/caps.ass" "${CAPTION_KEYS:-}"
  sed -i 's/Style: Cap,Arial Black,104/Style: Cap,Montserrat Black,100/' "$WORK/caps.ass"
  VF="subtitles=caps.ass:fontsdir=$FONTS,format=yuv420p"
fi

cd "$WORK"  # libass path escaping is fragile; use bare file names
ffmpeg -loglevel error -y -i video.mp4 -i mix.wav \
  -vf "$VF" \
  -af "loudnorm=I=-14:TP=-1.0:LRA=11,aresample=48000" \
  -c:v libx264 -preset slow -crf 16 -profile:v high -pix_fmt yuv420p \
  -color_primaries bt709 -color_trc bt709 -colorspace bt709 -movflags +faststart \
  -c:a aac -b:a 320k -shortest "$OUT"
ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate -show_entries format=duration -of compact "$OUT"
rm -rf "$WORK"
