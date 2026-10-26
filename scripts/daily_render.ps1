# Daily automated render pipeline
# Triggered by Windows Task Scheduler at 11:30 PM IST (see setup_scheduler.ps1).
# Picks up the oldest COMPLETE topic prepared by the cloud agent in queue/<slug>/:
#   script.txt   narration, one beat per line
#   scene.py     Blender scene builder:  blender -b --python scene.py -- <out.blend> vo=<wav> beats=<json>
#   mix.py       sound design:           python mix.py <beats.json> <vo.wav> <out_mix.wav>
#   metadata.txt YouTube metadata (title/description/tags)
#   keywords.txt (optional) comma-separated caption words to highlight
# Every run (success or failure) pushes its log to logs/ so the cloud agent can see what happened.
# Keep this file ASCII-only: Windows PowerShell 5.1 reads BOM-less files as ANSI.

$GIT     = "C:\Program Files\Git\cmd\git.exe"
$BLENDER = "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
$PYTHON  = "C:\Users\ANKIT MISHRA\AppData\Local\Programs\Python\Python311\python.exe"
$ROOT    = "D:\ShortsPipeline"
$WINGET_FF = "C:\Users\ANKIT MISHRA\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin"
$LOGNAME = "daily_$(Get-Date -Format 'yyyyMMdd_HHmm').log"
$LOG     = "$ROOT\logs\$LOGNAME"

New-Item -ItemType Directory -Force "$ROOT\logs" | Out-Null

function Log($msg) {
    $ts = Get-Date -Format "HH:mm:ss"
    "$ts  $msg" | Tee-Object -Append -FilePath $LOG
}

# Push this run's log to GitHub, then exit. Called on every exit path.
function Finish([int]$code, [string]$summary) {
    Log "=== $summary (exit $code) ==="
    Set-Location $ROOT
    & $GIT add "logs/$LOGNAME" 2>&1 | Out-Null
    & $GIT commit -m "Log: $summary" 2>&1 | Out-Null
    & $GIT push origin main 2>&1 | ForEach-Object { "$_" } | Out-Null
    exit $code
}

# ffmpeg/ffprobe: prefer PATH (scheduled tasks can run with a reduced PATH), else the winget install
function Find-Tool($name) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $p = Join-Path $WINGET_FF "$name.exe"
    if (Test-Path $p) { return $p }
    return $null
}
$FFMPEG  = Find-Tool "ffmpeg"
$FFPROBE = Find-Tool "ffprobe"

Log "=== Daily pipeline start ==="
if (-not $FFMPEG) { Finish 1 "ERROR: ffmpeg not found on PATH or at $WINGET_FF" }
if (-not (Test-Path $BLENDER)) { Finish 1 "ERROR: Blender not found at $BLENDER" }
if (-not (Test-Path $PYTHON)) { Finish 1 "ERROR: Python not found at $PYTHON" }
Log "ffmpeg: $FFMPEG"

# 1. Pull latest from GitHub
Set-Location $ROOT
& $GIT pull origin main 2>&1 | ForEach-Object { Log "$_" }

# 2. Pick the oldest complete queue item (FIFO by the commit that added it; name as tie-break)
$queueDir = "$ROOT\queue"
if (-not (Test-Path $queueDir)) { Finish 0 "No queue folder yet" }
$candidates = @()
foreach ($d in (Get-ChildItem $queueDir -Directory)) {
    $missing = @("script.txt", "scene.py", "mix.py") | Where-Object { -not (Test-Path (Join-Path $d.FullName $_)) }
    if ($missing) {
        Log "Skipping $($d.Name): missing $($missing -join ', ')"
        continue
    }
    $ct = & $GIT log -1 --diff-filter=A --format=%ct -- "queue/$($d.Name)" 2>$null
    if (-not $ct) { $ct = "9999999999" }
    $candidates += [pscustomobject]@{ Name = $d.Name; Time = [long]$ct }
}
if ($candidates.Count -eq 0) { Finish 0 "Queue has no complete item - nothing to render" }
$slug = ($candidates | Sort-Object Time, Name | Select-Object -First 1).Name
Log "Processing: $slug"

$itemDir     = "$queueDir\$slug"
$scriptFile  = "$itemDir\script.txt"
$sceneScript = "$itemDir\scene.py"
$mixScript   = "$itemDir\mix.py"
$metaFile    = "$itemDir\metadata.txt"
$kwFile      = "$itemDir\keywords.txt"
New-Item -ItemType Directory -Force "$ROOT\audio", "$ROOT\blend", "$ROOT\renders", "$ROOT\final" | Out-Null

# 3. Kokoro TTS narration. tts.py takes an output PREFIX and writes <prefix>.wav + <prefix>.json
$voPrefix = "$ROOT\audio\${slug}_vo"
$voWav    = "$voPrefix.wav"
$ttsJson  = "$voPrefix.json"
$voFinal  = "$ROOT\audio\${slug}_vo_final.wav"
$voJson   = "$ROOT\audio\${slug}_beats.json"
Log "Generating TTS narration..."
& $PYTHON "$ROOT\scripts\tts.py" $scriptFile $voPrefix 2>&1 | ForEach-Object { Log "$_" }
if (-not (Test-Path $voWav)) { Finish 1 "ERROR: TTS failed for $slug" }

# 4. Trim long pauses, verify words, then align beats on the FINAL audio
Log "Trimming silence..."
$voTrimmed = "$ROOT\audio\${slug}_vo_trim.wav"
& $FFMPEG -y -hide_banner -loglevel error -i $voWav -af "silenceremove=stop_periods=-1:stop_duration=0.3:stop_threshold=-40dB:stop_silence=0.05" $voTrimmed 2>&1 | ForEach-Object { Log "$_" }
if (Test-Path $voTrimmed) { Copy-Item $voTrimmed $voFinal -Force } else { Copy-Item $voWav $voFinal -Force }
& $PYTHON -I "$ROOT\scripts\verify_words.py" $voFinal $scriptFile 2>&1 | ForEach-Object { Log "$_" }

Log "Aligning narration beats..."
if (Test-Path $voJson) { Remove-Item $voJson -Force }
& $PYTHON -I "$ROOT\scripts\align_narration.py" $voFinal $scriptFile $voJson 2>&1 | Select-String "WROTE|Error|error|Traceback|^\s+\d" | ForEach-Object { Log "$_" }
if (-not (Test-Path $voJson)) {
    # Fallback: untrimmed TTS audio + its own per-beat timings are always consistent with each other
    Log "WARNING: alignment failed - falling back to untrimmed TTS audio and TTS beat timings"
    Copy-Item $voWav $voFinal -Force
    Copy-Item $ttsJson $voJson -Force
}

# 5. Build Blender scene (scene.py opens the hero .blend itself)
Log "Building Blender scene..."
$blendFile = "$ROOT\blend\${slug}.blend"
if (Test-Path $blendFile) { Remove-Item $blendFile -Force }
& $BLENDER -b --python $sceneScript -- $blendFile "vo=$voFinal" "beats=$voJson" 2>&1 |
    Select-String "ARGS|SAVED|WARN|Error|error|Traceback|line \d+|File " | ForEach-Object { Log "$_" }
if (-not (Test-Path $blendFile)) { Finish 1 "ERROR: Scene build failed for $slug" }

# 6. Render frames (resumes: existing frames are skipped; range clamps to the scene's frame_end)
$framesDir = "$ROOT\renders\${slug}_frames"
New-Item -ItemType Directory -Force $framesDir | Out-Null
Log "Rendering frames (this takes several hours)..."
& $BLENDER -b $blendFile --python "$ROOT\scripts\render_anim.py" -- $framesDir 1 9999 2>&1 |
    Select-String "RANGE|FRAME \d*00\b|Error|Traceback" | ForEach-Object { Log "$_" }
$frameCount = (Get-ChildItem "$framesDir\f*.png" -ErrorAction SilentlyContinue | Measure-Object).Count
Log "Frames rendered: $frameCount"
if ($frameCount -lt 100) { Finish 1 "ERROR: Too few frames for $slug - render likely failed" }

# 7. Mix audio (falls back to narration only so a video still ships)
Log "Mixing audio..."
$mixWav = "$ROOT\audio\${slug}_mix.wav"
& $PYTHON -I $mixScript $voJson $voFinal $mixWav 2>&1 | ForEach-Object { Log "$_" }
if (-not (Test-Path $mixWav)) {
    Log "WARNING: mix failed - using narration only"
    Copy-Item $voFinal $mixWav -Force
}

# 8. Captions (punchy 1-3 word chunks, keywords highlighted)
$assFile = "$ROOT\renders\${slug}_captions.ass"
$keywords = ""
if (Test-Path $kwFile) { $keywords = (Get-Content $kwFile -Raw).Trim() }
& $PYTHON -I "$ROOT\scripts\make_captions.py" $voJson $assFile $keywords 2>&1 | ForEach-Object { Log "$_" }

# 9. Assemble final MP4: H.264 High + AAC, -14 LUFS, burned captions
Log "Assembling final video..."
$finalMp4 = "$ROOT\final\${slug}_final.mp4"
$vf = "format=yuv420p"
if (Test-Path $assFile) {
    $vf = "subtitles=$(Split-Path $assFile -Leaf):fontsdir=C\\:/Windows/Fonts,format=yuv420p"
}
Push-Location (Split-Path $assFile -Parent)   # libass path escaping on Windows is fragile; use a bare filename
& $FFMPEG -y -hide_banner -loglevel error `
    -framerate 30 -i "$framesDir\f%04d.png" -i $mixWav `
    -vf $vf `
    -af "loudnorm=I=-14:TP=-1.0:LRA=11,aresample=48000" `
    -c:v libx264 -preset slow -crf 16 -profile:v high -pix_fmt yuv420p -movflags +faststart `
    -c:a aac -b:a 320k -shortest `
    $finalMp4 2>&1 | ForEach-Object { Log "$_" }
Pop-Location
if (-not (Test-Path $finalMp4)) { Finish 1 "ERROR: ffmpeg assembly failed for $slug" }

# 10. Verify output
if ($FFPROBE) {
    $info = & $FFPROBE -v error -show_entries stream=width,height -show_entries format=duration -of compact $finalMp4 2>&1
    Log "Output: $info"
}

# 11. Copy metadata, mark the item completed, push back to GitHub
if (Test-Path $metaFile) {
    Copy-Item $metaFile "$ROOT\final\${slug}_youtube_metadata.txt" -Force
}
$doneDir = "$ROOT\completed\$slug"
if (Test-Path $doneDir) { Remove-Item $doneDir -Recurse -Force }
Move-Item $itemDir $doneDir -Force    # destination must NOT pre-exist, or the folder nests inside it
& $GIT add -A "queue" "completed" "final/${slug}_youtube_metadata.txt" 2>&1 | Out-Null
& $GIT commit -m "Completed: $slug" 2>&1 | ForEach-Object { Log "$_" }

# 12. Copy to the Videos folder inside a titled subfolder
$videosBase = "C:\Users\ANKIT MISHRA\Videos\CONTENT\3D SHORTS ANIMATION\Animation"
$videoTitle = $slug  # fallback
$doneMeta = "$doneDir\metadata.txt"
if (Test-Path $doneMeta) {
    $lines = Get-Content $doneMeta
    for ($li = 0; $li -lt $lines.Count - 1; $li++) {
        if ($lines[$li] -match "TITLE \(pick one") {
            $raw = $lines[$li + 1] -replace '^\d+\.\s*', ''
            $videoTitle = ($raw -replace '[\\/:*?"<>|]', '' -replace '\s+', ' ').Trim()
            break
        }
    }
}
$titleDir = "$videosBase\$videoTitle"
New-Item -ItemType Directory -Force $titleDir | Out-Null
Copy-Item $finalMp4 "$titleDir\$videoTitle.mp4" -Force
if (Test-Path $doneMeta) {
    Copy-Item $doneMeta "$titleDir\$videoTitle - YouTube Metadata.txt" -Force
}
Log "Saved to: $titleDir\$videoTitle.mp4"

# 13. Upload to YouTube as private (requires one-time auth via youtube_auth.py)
$credsFile = "$ROOT\secrets\yt_credentials.json"
if (Test-Path $credsFile) {
    Log "Uploading to YouTube..."
    & $PYTHON -I "$ROOT\scripts\youtube_upload.py" "$titleDir\$videoTitle.mp4" "$titleDir\$videoTitle - YouTube Metadata.txt" 2>&1 | ForEach-Object { Log "$_" }
} else {
    Log "YouTube credentials not found - skipping upload. Run scripts\youtube_auth.py once to enable."
}

Finish 0 "Done: $slug -> $titleDir\$videoTitle.mp4"
