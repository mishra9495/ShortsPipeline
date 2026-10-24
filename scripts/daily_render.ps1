# Daily automated render pipeline
# Triggered by Windows Task Scheduler at 11:30 PM IST
# Picks up new topic prepared by cloud agent from GitHub

$GIT  = "C:\Program Files\Git\cmd\git.exe"
$BLENDER = "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
$PYTHON  = "C:\Users\ANKIT MISHRA\AppData\Local\Programs\Python\Python312\python.exe"
$FFMPEG  = "ffmpeg"
$ROOT = "D:\ShortsPipeline"
$LOG  = "$ROOT\logs\daily_$(Get-Date -Format 'yyyyMMdd_HHmm').log"

New-Item -ItemType Directory -Force "$ROOT\logs" | Out-Null

function Log($msg) {
    $ts = Get-Date -Format "HH:mm:ss"
    "$ts  $msg" | Tee-Object -Append $LOG
}

Log "=== Daily pipeline start ==="

# 1. Pull latest from GitHub
Set-Location $ROOT
& $GIT pull origin main 2>&1 | ForEach-Object { Log $_ }

# 2. Find oldest unprocessed queue item
$queueDir = "$ROOT\queue"
if (-not (Test-Path $queueDir)) { Log "No queue folder yet — exiting."; exit 0 }
$topic = Get-ChildItem $queueDir -Directory | Sort-Object Name | Select-Object -First 1
if (-not $topic) { Log "Queue empty — nothing to render today."; exit 0 }

$slug = $topic.Name
Log "Processing: $slug"

$scriptFile  = "$queueDir\$slug\script.txt"
$sceneScript = "$queueDir\$slug\scene.py"
$mixScript   = "$queueDir\$slug\mix.py"
$metaFile    = "$queueDir\$slug\metadata.txt"

if (-not (Test-Path $scriptFile) -or -not (Test-Path $sceneScript)) {
    Log "ERROR: missing script.txt or scene.py for $slug — skipping."
    exit 1
}

# 3. Generate Kokoro TTS narration
$voWav  = "$ROOT\audio\${slug}_vo.wav"
$voJson = "$ROOT\audio\${slug}_beats.json"
Log "Generating TTS narration..."
& $PYTHON "$ROOT\scripts\tts.py" $scriptFile $voWav 2>&1 | ForEach-Object { Log $_ }
if (-not (Test-Path $voWav)) { Log "ERROR: TTS failed."; exit 1 }

# 4. Align narration beats
Log "Aligning narration beats..."
& $PYTHON -I "$ROOT\scripts\align_narration.py" $voWav $scriptFile $voJson 2>&1 | ForEach-Object { Log $_ }
if (-not (Test-Path $voJson)) { Log "ERROR: Alignment failed."; exit 1 }

# 5. Trim silence + verify words
Log "Trimming silence..."
$voTrimmed = "$ROOT\audio\${slug}_vo_trim.wav"
& ffmpeg -y -i $voWav -af "silenceremove=stop_periods=-1:stop_duration=0.3:stop_threshold=-40dB:stop_silence=0.05" $voTrimmed 2>&1 | Out-Null
& $PYTHON -I "$ROOT\scripts\verify_words.py" $voTrimmed $scriptFile 2>&1 | ForEach-Object { Log $_ }
Copy-Item $voTrimmed "$ROOT\audio\${slug}_vo_final.wav" -Force

# 6. Re-align after trim
& $PYTHON -I "$ROOT\scripts\align_narration.py" "$ROOT\audio\${slug}_vo_final.wav" $scriptFile $voJson 2>&1 | ForEach-Object { Log $_ }

# 7. Build Blender scene
Log "Building Blender scene..."
$blendFile = "$ROOT\blend\${slug}.blend"
& $BLENDER -b --python $sceneScript -- $blendFile 2>&1 | Select-String "ARGS|Error|error" | ForEach-Object { Log $_ }
if (-not (Test-Path $blendFile)) { Log "ERROR: Scene build failed."; exit 1 }

# 8. Render frames
$framesDir = "$ROOT\renders\${slug}_frames"
New-Item -ItemType Directory -Force $framesDir | Out-Null
Log "Rendering frames (this takes ~6 hours)..."
& $BLENDER -b $blendFile --python "$ROOT\scripts\render_anim.py" -- $framesDir 1 9999 2>&1 | Select-String "FRAME|Error" | ForEach-Object { Log $_ }

$frameCount = (Get-ChildItem "$framesDir\*.png" -ErrorAction SilentlyContinue | Measure-Object).Count
Log "Frames rendered: $frameCount"
if ($frameCount -lt 100) { Log "ERROR: Too few frames — render likely failed."; exit 1 }

# 9. Mix audio
Log "Mixing audio..."
$mixWav = "$ROOT\audio\${slug}_mix.wav"
& $PYTHON -I $mixScript $voJson "$ROOT\audio\${slug}_vo_final.wav" $mixWav 2>&1 | ForEach-Object { Log $_ }

# 10. Rename frames for ffmpeg
$frames = Get-ChildItem "$framesDir\*.png" | Sort-Object Name
$i = 1
foreach ($f in $frames) {
    $newName = "seq{0:D4}.png" -f $i
    if ($f.Name -ne $newName) { Rename-Item $f.FullName $newName }
    $i++
}

# 11. Assemble final MP4
Log "Assembling final video..."
$finalMp4 = "$ROOT\final\${slug}_final.mp4"
& ffmpeg -y `
    -framerate 30 -i "$framesDir\seq%04d.png" `
    -i $mixWav `
    -c:v libx264 -preset slow -crf 16 -pix_fmt yuv420p `
    -c:a aac -b:a 192k -shortest `
    $finalMp4 2>&1 | Select-String "size=|error" | ForEach-Object { Log $_ }

# 12. Verify output
$info = & ffprobe -v error -show_entries stream=width,height -show_entries format=duration -of default $finalMp4 2>&1
Log "Output: $info"

# 13. Copy metadata
if (Test-Path $metaFile) {
    Copy-Item $metaFile "$ROOT\final\${slug}_youtube_metadata.txt" -Force
}

# 14. Mark as completed
$doneDir = "$ROOT\completed\$slug"
New-Item -ItemType Directory -Force $doneDir | Out-Null
Move-Item "$queueDir\$slug" $doneDir -Force

# 15. Commit result back to GitHub
& $GIT add "final/${slug}_youtube_metadata.txt" "completed/" 2>&1 | Out-Null
& $GIT commit -m "Completed: $slug" 2>&1 | Out-Null
& $GIT push origin main 2>&1 | Out-Null

# 16. Copy to user's Videos folder inside a titled subfolder
$videosBase = "C:\Users\ANKIT MISHRA\Videos\CONTENT\3D SHORTS ANIMATION\Animation"

# Extract recommended title (line after "TITLE (pick one", strip "1. " prefix)
$videoTitle = $slug  # fallback
if (Test-Path $metaFile) {
    $lines = Get-Content $metaFile
    for ($li = 0; $li -lt $lines.Count - 1; $li++) {
        if ($lines[$li] -match "TITLE \(pick one") {
            $raw = $lines[$li + 1] -replace '^\d+\.\s*', ''
            # Sanitize: remove chars forbidden in Windows filenames
            $videoTitle = $raw -replace '[\\/:*?"<>|]', '' -replace '\s+', ' '
            $videoTitle = $videoTitle.Trim()
            break
        }
    }
}

$titleDir = "$videosBase\$videoTitle"
New-Item -ItemType Directory -Force $titleDir | Out-Null
Copy-Item $finalMp4 "$titleDir\$videoTitle.mp4" -Force
if (Test-Path $metaFile) {
    Copy-Item "$ROOT\final\${slug}_youtube_metadata.txt" "$titleDir\$videoTitle - YouTube Metadata.txt" -Force
}
Log "Saved to: $titleDir\$videoTitle.mp4"

Log "=== Done: $titleDir\$videoTitle.mp4 ==="
