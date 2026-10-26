# Daily automated render pipeline (Windows Task Scheduler, 11:30 PM IST; see setup_scheduler.ps1).
#
# Queue item: queue/<slug>/ with script.txt, scene.py, mix.py, metadata.txt  (+ optional fps.txt, default 30)
#   HOLD     -> never touched
#   PREVIEW  -> quality check only: narration + scene build + full-quality stills of the frames listed in
#               PREVIEW (comma separated; empty = 12 evenly spaced). Stills, the voice and the log are pushed to
#               previews/<slug>/ for review. Delete PREVIEW (after review) to allow the full render.
#   (none)   -> full render of the oldest such item: narration, scene, frames, mix, MP4, upload (private).
#
# Owner's standing rules: ElevenLabs "Daniel" narration only (no fallback voice), NEVER captions/subtitles.
# Every run pushes its log to logs/. Keep this file ASCII-only (Windows PowerShell 5.1 reads it as ANSI).

$GIT     = "C:\Program Files\Git\cmd\git.exe"
$BLENDER = "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
$PYTHON  = "C:\Users\ANKIT MISHRA\AppData\Local\Programs\Python\Python311\python.exe"
$ROOT    = "D:\ShortsPipeline"
$WINGET_FF = "C:\Users\ANKIT MISHRA\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin"
$LOGNAME = "daily_$(Get-Date -Format 'yyyyMMdd_HHmm').log"
$LOG     = "$ROOT\logs\$LOGNAME"
$EXTRA_ADD = @()

New-Item -ItemType Directory -Force "$ROOT\logs" | Out-Null

function Log($msg) {
    $ts = Get-Date -Format "HH:mm:ss"
    "$ts  $msg" | Tee-Object -Append -FilePath $LOG
}

# Push this run's log (plus any preview files) to GitHub, then exit. Called on every exit path.
function Finish([int]$code, [string]$summary) {
    Log "=== $summary (exit $code) ==="
    Set-Location $ROOT
    & $GIT add "logs/$LOGNAME" 2>&1 | Out-Null
    foreach ($p in $script:EXTRA_ADD) { & $GIT add -A $p 2>&1 | Out-Null }
    & $GIT commit -m "Log: $summary" 2>&1 | Out-Null
    # the render takes hours; integrate anything pushed meanwhile so the push is not rejected
    & $GIT pull --no-edit --no-rebase origin main 2>&1 | Out-Null
    & $GIT push origin main 2>&1 | Out-Null
    exit $code
}

function Find-Tool($name) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $p = Join-Path $WINGET_FF "$name.exe"
    if (Test-Path $p) { return $p }
    return $null
}
$FFMPEG  = Find-Tool "ffmpeg"
$FFPROBE = Find-Tool "ffprobe"
if ($FFMPEG) { $env:FFMPEG = $FFMPEG }   # tts_elevenlabs.py uses the same ffmpeg

Log "=== Daily pipeline start ==="
if (-not $FFMPEG) { Finish 1 "ERROR: ffmpeg not found on PATH or at $WINGET_FF" }
if (-not (Test-Path $BLENDER)) { Finish 1 "ERROR: Blender not found at $BLENDER" }
if (-not (Test-Path $PYTHON)) { Finish 1 "ERROR: Python not found at $PYTHON" }

# 1. Pull latest from GitHub
Set-Location $ROOT
& $GIT pull --no-edit --no-rebase origin main 2>&1 | ForEach-Object { Log "$_" }

# Narration (ElevenLabs Daniel) + scene build for one queue item. Returns a hashtable of paths, or $null.
function Prepare-Item($slug) {
    $it = @{}
    $it.slug  = $slug
    $it.dir   = "$ROOT\queue\$slug"
    $it.fps   = 30
    if (Test-Path "$($it.dir)\fps.txt") { $it.fps = [int]((Get-Content "$($it.dir)\fps.txt" -Raw).Trim()) }
    New-Item -ItemType Directory -Force "$ROOT\audio", "$ROOT\blend", "$ROOT\renders", "$ROOT\final" | Out-Null
    $prefix   = "$ROOT\audio\${slug}_vo"
    $it.vo    = "$prefix.wav"
    $it.beats = "$prefix.json"
    Log "[$slug] Narration: ElevenLabs Daniel..."
    if (Test-Path $it.vo) { Remove-Item $it.vo -Force }
    & $PYTHON "$ROOT\scripts\tts_elevenlabs.py" "$($it.dir)\script.txt" $prefix 2>&1 | ForEach-Object { Log "$_" }
    if (-not (Test-Path $it.vo) -or -not (Test-Path $it.beats)) {
        Log "[$slug] ERROR: ElevenLabs narration failed. Put the API key in $ROOT\secrets\elevenlabs_api_key.txt (no fallback voice by design)."
        return $null
    }
    Log "[$slug] Building Blender scene ($($it.fps) fps)..."
    $it.blend = "$ROOT\blend\${slug}.blend"
    if (Test-Path $it.blend) { Remove-Item $it.blend -Force }
    & $BLENDER -b --python "$($it.dir)\scene.py" -- $it.blend "vo=$($it.vo)" "beats=$($it.beats)" "fps=$($it.fps)" 2>&1 |
        Select-String "ARGS|CHAR|SAVED|WARN|Error|error|Traceback|line \d+|File " | ForEach-Object { Log "$_" }
    if (-not (Test-Path $it.blend)) { Log "[$slug] ERROR: scene build failed"; return $null }
    return $it
}

# 2. Previews first: quick full-quality stills for review (no video, item stays queued)
foreach ($d in (Get-ChildItem "$ROOT\queue" -Directory -ErrorAction SilentlyContinue)) {
    if (Test-Path "$($d.FullName)\HOLD") { continue }
    if (-not (Test-Path "$($d.FullName)\PREVIEW")) { continue }
    $it = Prepare-Item $d.Name
    $out = "$ROOT\previews\$($d.Name)"
    New-Item -ItemType Directory -Force $out | Out-Null
    if ($it) {
        $frames = (Get-Content "$($d.FullName)\PREVIEW" -Raw)
        if ($frames) { $frames = $frames.Trim() } else { $frames = "" }
        Log "[$($d.Name)] Preview stills: '$frames'"
        & $BLENDER -b $it.blend --python "$ROOT\scripts\render_stills.py" -- $out $frames 2>&1 |
            Select-String "STILL|Error|Traceback" | ForEach-Object { Log "$_" }
        foreach ($png in (Get-ChildItem "$out\still_*.png" -ErrorAction SilentlyContinue)) {   # JPG keeps the repo small
            & $FFMPEG -y -hide_banner -loglevel error -i $png.FullName -q:v 3 ($png.FullName -replace '\.png$', '.jpg') 2>&1 | Out-Null
            Remove-Item $png.FullName -Force
        }
        & $FFMPEG -y -hide_banner -loglevel error -i $it.vo -b:a 128k "$out\voice.mp3" 2>&1 | Out-Null
        Copy-Item $it.beats "$out\beats.json" -Force
    }
    Copy-Item $LOG "$out\build.log" -Force
    $script:EXTRA_ADD += "previews/$($d.Name)"
}

# 3. Pick the oldest item for the full render (FIFO by the commit that added it; name as tie-break)
$candidates = @()
foreach ($d in (Get-ChildItem "$ROOT\queue" -Directory -ErrorAction SilentlyContinue)) {
    if (Test-Path "$($d.FullName)\HOLD") { Log "Skipping $($d.Name): on HOLD"; continue }
    if (Test-Path "$($d.FullName)\PREVIEW") { Log "Skipping full render of $($d.Name): in PREVIEW"; continue }
    $missing = @("script.txt", "scene.py", "mix.py") | Where-Object { -not (Test-Path (Join-Path $d.FullName $_)) }
    if ($missing) { Log "Skipping $($d.Name): missing $($missing -join ', ')"; continue }
    $ct = & $GIT log -1 --diff-filter=A --format=%ct -- "queue/$($d.Name)" 2>$null
    if (-not $ct) { $ct = "9999999999" }
    $candidates += [pscustomobject]@{ Name = $d.Name; Time = [long]$ct }
}
if ($candidates.Count -eq 0) { Finish 0 "No item ready for a full render" }
$slug = ($candidates | Sort-Object Time, Name | Select-Object -First 1).Name
Log "Full render: $slug"
$it = Prepare-Item $slug
if (-not $it) { Finish 1 "ERROR: could not prepare $slug" }
$itemDir = $it.dir
$FPS = $it.fps

# 4. Render frames (resumes: existing frames are skipped; range clamps to the scene's frame_end)
$framesDir = "$ROOT\renders\${slug}_frames"
New-Item -ItemType Directory -Force $framesDir | Out-Null
Log "Rendering frames (this takes several hours)..."
& $BLENDER -b $it.blend --python "$ROOT\scripts\render_anim.py" -- $framesDir 1 99999 2>&1 |
    Select-String "RANGE|FRAME \d*00\b|Error|Traceback" | ForEach-Object { Log "$_" }
$frameCount = (Get-ChildItem "$framesDir\f*.png" -ErrorAction SilentlyContinue | Measure-Object).Count
Log "Frames rendered: $frameCount"
if ($frameCount -lt 100) { Finish 1 "ERROR: Too few frames for $slug - render likely failed" }

# 5. Mix audio (falls back to narration only so a video still ships)
Log "Mixing audio..."
$mixWav = "$ROOT\audio\${slug}_mix.wav"
& $PYTHON -I "$itemDir\mix.py" $it.beats $it.vo $mixWav 2>&1 | ForEach-Object { Log "$_" }
if (-not (Test-Path $mixWav)) {
    Log "WARNING: mix failed - using narration only"
    Copy-Item $it.vo $mixWav -Force
}

# 6. Assemble final MP4: H.264 High + AAC, -14 LUFS. NEVER burn captions/subtitles (owner's standing rule).
Log "Assembling final video..."
$finalMp4 = "$ROOT\final\${slug}_final.mp4"
& $FFMPEG -y -hide_banner -loglevel error `
    -framerate $FPS -i "$framesDir\f%04d.png" -i $mixWav `
    -vf "format=yuv420p" `
    -af "loudnorm=I=-14:TP=-1.0:LRA=11,aresample=48000" `
    -c:v libx264 -preset slow -crf 16 -profile:v high -pix_fmt yuv420p -movflags +faststart `
    -c:a aac -b:a 320k -shortest `
    $finalMp4 2>&1 | ForEach-Object { Log "$_" }
if (-not (Test-Path $finalMp4)) { Finish 1 "ERROR: ffmpeg assembly failed for $slug" }
if ($FFPROBE) {
    $info = & $FFPROBE -v error -show_entries stream=width,height,r_frame_rate -show_entries format=duration -of compact $finalMp4 2>&1
    Log "Output: $info"
}

# 7. Copy metadata, mark the item completed, push back to GitHub
$metaFile = "$itemDir\metadata.txt"
if (Test-Path $metaFile) { Copy-Item $metaFile "$ROOT\final\${slug}_youtube_metadata.txt" -Force }
$doneDir = "$ROOT\completed\$slug"
if (Test-Path $doneDir) { Remove-Item $doneDir -Recurse -Force }
Move-Item $itemDir $doneDir -Force    # destination must NOT pre-exist, or the folder nests inside it
& $GIT add -A "queue" "completed" "final/${slug}_youtube_metadata.txt" 2>&1 | Out-Null
& $GIT commit -m "Completed: $slug" 2>&1 | ForEach-Object { Log "$_" }

# 8. Copy to the Videos folder inside a titled subfolder
$videosBase = "C:\Users\ANKIT MISHRA\Videos\CONTENT\3D SHORTS ANIMATION\Animation"
$videoTitle = $slug
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
if (Test-Path $doneMeta) { Copy-Item $doneMeta "$titleDir\$videoTitle - YouTube Metadata.txt" -Force }
Log "Saved to: $titleDir\$videoTitle.mp4"

# 9. Upload to YouTube as private (requires one-time auth via youtube_auth.py)
$credsFile = "$ROOT\secrets\yt_credentials.json"
if (Test-Path $credsFile) {
    Log "Uploading to YouTube..."
    & $PYTHON -I "$ROOT\scripts\youtube_upload.py" "$titleDir\$videoTitle.mp4" "$titleDir\$videoTitle - YouTube Metadata.txt" 2>&1 | ForEach-Object { Log "$_" }
} else {
    Log "YouTube credentials not found - skipping upload. Run scripts\youtube_auth.py once to enable."
}

Finish 0 "Done: $slug -> $titleDir\$videoTitle.mp4"
