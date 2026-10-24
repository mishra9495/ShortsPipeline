# Frames + mixed audio + burned captions -> upload-ready Short (H.264 High, AAC, -14 LUFS).
# assemble_short.ps1 <framesDir> <mix.wav> <captions.ass> <out.mp4>
param([string]$Frames, [string]$Audio, [string]$Ass, [string]$Out)
$ff = "C:\Users\ANKIT MISHRA\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"
$assDir = Split-Path $Ass -Parent
$assName = Split-Path $Ass -Leaf
Push-Location $assDir   # libass path escaping on Windows is fragile; use a bare filename
& $ff -y -hide_banner -loglevel error -stats `
    -framerate 30 -i (Join-Path $Frames "f%04d.png") -i $Audio `
    -vf "subtitles=${assName}:fontsdir=C\\:/Windows/Fonts,format=yuv420p" `
    -af "loudnorm=I=-14:TP=-1.0:LRA=11,aresample=48000" `
    -c:v libx264 -preset slow -crf 16 -profile:v high -pix_fmt yuv420p -movflags +faststart `
    -c:a aac -b:a 320k -shortest $Out
Pop-Location
Write-Output "wrote $Out"
