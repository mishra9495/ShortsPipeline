# Build the ice test scene, render all frames, mux with voice-over into an MP4.
$ErrorActionPreference = "Stop"
$b = "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
$root = "D:\ShortsPipeline"
$frames = "$root\renders\ice_test_frames"
New-Item -ItemType Directory -Force $frames | Out-Null
& $b -b "$root\blend\char_hero.blend" --python "$root\scripts\scene_ice_test.py" -- "$root\blend\ice_test.blend" | Select-String "SAVED|Traceback|Error:"
$t = Get-Date
& $b -b "$root\blend\ice_test.blend" -o "$frames\f####" -F PNG -a | Select-String "Saved:|Traceback|Error:" | Select-Object -Last 3
"render minutes: {0:N1}" -f ((Get-Date) - $t).TotalMinutes
$env:Path = [Environment]::GetEnvironmentVariable('Path','User') + ';' + [Environment]::GetEnvironmentVariable('Path','Machine')
ffmpeg -y -loglevel error -framerate 30 -start_number 1 -i "$frames\f%04d.png" -ss 0 -t 5.5 -i "$root\audio\vo_michael_125.wav" `
  -c:v libx264 -preset slow -crf 16 -pix_fmt yuv420p -c:a aac -b:a 192k -shortest "$root\final\ice_test_v1.mp4"
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height,r_frame_rate -of compact "$root\final\ice_test_v1.mp4"
