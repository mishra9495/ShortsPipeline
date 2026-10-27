# Daily automated render pipeline (Windows Task Scheduler, 11:30 PM IST; see setup_scheduler.ps1).
#
# Queue item: queue/<slug>/ with script.txt, scene.py, mix.py, metadata.txt  (+ optional fps.txt, default 30)
#   HOLD     -> never touched
#   PREVIEW  -> quality check only: narration + scene build + full-quality stills of the frames listed in
#               PREVIEW (comma separated; empty = 12 evenly spaced). Stills, the voice and the log are pushed to
#               previews/<slug>/ for review. Delete PREVIEW (after review) to allow the full render.
#   (none)   -> full render of the oldest such item: narration, scene, frames, mix, MP4, upload (PUBLIC).
#
# Owner's standing rules: NEVER captions/subtitles. Voice: queue narration.wav > narration.mp3 (ElevenLabs website)
#   > ElevenLabs API key > free Kokoro am_fenrir (owner approved the free voice on 2026-10-27).
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

# Log to file + console WITHOUT writing to the output stream: inside a function, pipeline output becomes the
# function's return value (Tee-Object did that and turned Prepare-Item's result into an array of log lines).
function Log($msg) {
    $line = "$(Get-Date -Format 'HH:mm:ss')  $msg"
    Add-Content -Path $LOG -Value $line
    Write-Host $line
}

# GitHub is the source of truth on this PC: a local edit to a tracked file blocks every pull ("would be overwritten
# by merge"), which left this PC on old scripts and its logs unpushed. Stash such edits (recover: git stash list / pop).
function Stash-LocalEdits {
    $dirty = & $GIT -C $ROOT status --porcelain --untracked-files=no
    if ($dirty) {
        Log "Local edits stashed so the pull can update them: $(($dirty | ForEach-Object { "$_".Trim() }) -join ', ')"
        & $GIT -C $ROOT stash push -m "daily_render auto-stash $(Get-Date -Format 'yyyyMMdd_HHmm')" 2>&1 | ForEach-Object { Log "$_" }
    }
}

# Push this run's log (plus any preview files) to GitHub, then exit. Called on every exit path.
function Finish([int]$code, [string]$summary) {
    Log "=== $summary (exit $code) ==="
    Set-Location $ROOT
    & $GIT add "logs/$LOGNAME" 2>&1 | Out-Null
    foreach ($p in $script:EXTRA_ADD) { & $GIT add -A $p 2>&1 | Out-Null }
    & $GIT commit -m "Log: $summary" 2>&1 | Out-Null
    # the render takes hours; integrate anything pushed meanwhile so the push is not rejected
    Stash-LocalEdits
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
# Keep Windows awake (no sleep) while this runs; the render takes many hours. Released when the process exits.
try {
    Add-Type -Namespace Shorts -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint esFlags);'
    [Shorts.Power]::SetThreadExecutionState([uint32]2147483649) | Out-Null   # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    Log "Sleep blocked while the pipeline runs"
} catch { Log "WARN could not block sleep: $_" }

# Push the log mid-render (every 100 frames) so progress is visible on GitHub.
function Push-Progress {
    Set-Location $ROOT
    & $GIT add "logs/$LOGNAME" 2>&1 | Out-Null
    & $GIT commit -m "Progress: $LOGNAME" 2>&1 | Out-Null
    Stash-LocalEdits
    & $GIT pull --no-edit --no-rebase origin main 2>&1 | Out-Null
    & $GIT push origin main 2>&1 | Out-Null
}
if (-not $FFMPEG) { Finish 1 "ERROR: ffmpeg not found on PATH or at $WINGET_FF" }
if (-not (Test-Path $BLENDER)) { Finish 1 "ERROR: Blender not found at $BLENDER" }
if (-not (Test-Path $PYTHON)) { Finish 1 "ERROR: Python not found at $PYTHON" }

# 1. Pull latest from GitHub. PowerShell has already loaded THIS file, so if the pull changed it, restart once with
#    the new version (otherwise fixes only take effect on the following run).
Set-Location $ROOT
$selfHash = (Get-FileHash $PSCommandPath).Hash
Stash-LocalEdits
& $GIT pull --no-edit --no-rebase origin main 2>&1 | ForEach-Object { Log "$_" }
if (((Get-FileHash $PSCommandPath).Hash -ne $selfHash) -and -not $env:SHORTS_REEXEC) {
    Log "daily_render.ps1 was updated by the pull - restarting with the new version"
    $env:SHORTS_REEXEC = "1"
    & powershell -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath
    exit $LASTEXITCODE
}

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
    foreach ($f in @($it.vo, $it.beats)) { if (Test-Path $f) { Remove-Item $f -Force } }
    $script_txt = "$($it.dir)\script.txt"
    $rec = Get-ChildItem "$($it.dir)\narration.mp3", "$($it.dir)\narration_raw.wav" -ErrorAction SilentlyContinue | Select-Object -First 1
    $key = (Test-Path "$ROOT\secrets\elevenlabs_api_key.txt") -or [bool]$env:ELEVENLABS_API_KEY
    if ((Test-Path "$($it.dir)\narration.wav") -and (Test-Path "$($it.dir)\narration.json")) {
        Log "[$slug] Narration: using the ready-made queue narration.wav"
        Copy-Item "$($it.dir)\narration.wav" $it.vo -Force
        Copy-Item "$($it.dir)\narration.json" $it.beats -Force
    } elseif ($rec) {
        Log "[$slug] Narration: from recording $($rec.Name) (pauses trimmed, tempo +15%)"
        & $PYTHON "$ROOT\scripts\narration_from_audio.py" $rec.FullName $script_txt $prefix 2>&1 | ForEach-Object { Log "$_" }
    } elseif ($key) {
        Log "[$slug] Narration: ElevenLabs Daniel (API)"
        & $PYTHON "$ROOT\scripts\tts_elevenlabs.py" $script_txt $prefix 2>&1 | ForEach-Object { Log "$_" }
    } else {
        # Owner approved a free voice when ElevenLabs is unavailable (2026-10-27): Kokoro am_fenrir is the closest
        # free match to Daniel's pitch and timbre.
        Log "[$slug] Narration: free Kokoro am_fenrir voice (no ElevenLabs key)"
        & $PYTHON "$ROOT\scripts\tts.py" $script_txt $prefix am_fenrir auto 2>&1 | ForEach-Object { Log "$_" }
    }
    if (-not (Test-Path $it.vo) -or -not (Test-Path $it.beats)) {
        Log "[$slug] ERROR: narration failed (see the lines above)."
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
    if (($it -is [hashtable]) -and $it.blend -and (Test-Path $it.blend)) {
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
if (-not ($it -is [hashtable]) -or -not $it.blend -or -not (Test-Path $it.blend)) { Finish 1 "ERROR: could not prepare $slug (see the narration/scene lines above)" }
$itemDir = $it.dir
$FPS = $it.fps

# 4. Render frames (resumes: existing frames are skipped; range clamps to the scene's frame_end)
$framesDir = "$ROOT\renders\${slug}_frames"
$sig = ((Get-FileHash "$itemDir\scene.py").Hash + (Get-FileHash $it.beats).Hash + "$FPS")
$sigFile = "$framesDir\BUILD.txt"
if ((Test-Path $framesDir) -and (-not (Test-Path $sigFile) -or ((Get-Content $sigFile -Raw).Trim() -ne $sig))) {
    Log "Removing frames from a different build"
    Remove-Item $framesDir -Recurse -Force
}
New-Item -ItemType Directory -Force $framesDir | Out-Null
Set-Content -Path $sigFile -Value $sig
Log "Rendering frames (this takes several hours)..."
& $BLENDER -b $it.blend --python "$ROOT\scripts\render_anim.py" -- $framesDir 1 99999 2>&1 |
    Select-String "RANGE|FRAME \d*00\b|Error|Traceback" | ForEach-Object {
        Log "$_"
        if ("$_" -match "FRAME \d*00\b") { Push-Progress }
    }
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

# 9. Upload to YouTube as PUBLIC - owner's standing rule since 2026-10-27 (one-time auth via youtube_auth.py)
$credsFile = "$ROOT\secrets\yt_credentials.json"
if (Test-Path $credsFile) {
    Log "Uploading to YouTube..."
    & $PYTHON -I "$ROOT\scripts\upload_youtube.py" "$titleDir\$videoTitle.mp4" "$titleDir\$videoTitle - YouTube Metadata.txt" 2>&1 | ForEach-Object { Log "$_" }
} else {
    Log "YouTube credentials not found - skipping upload. Run scripts\youtube_auth.py once to enable."
}

Finish 0 "Done: $slug -> $titleDir\$videoTitle.mp4"
