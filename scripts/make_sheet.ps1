# Contact sheet of PNG stills: make_sheet.ps1 <dir> <filter> <out.png> [cols] [thumbWidth]
param([string]$Dir, [string]$Filter, [string]$Out, [int]$Cols = 8, [int]$W = 270)
$ff = "C:\Users\ANKIT MISHRA\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin\ffmpeg.exe"
$tmp = Join-Path $env:TEMP ("sheet_" + [guid]::NewGuid())
New-Item -ItemType Directory $tmp | Out-Null
$files = Get-ChildItem $Dir -Filter $Filter | Sort-Object Name
$i = 0
foreach ($f in $files) {
    $label = $f.BaseName -replace '.*_f', ''
    & $ff -y -loglevel error -i $f.FullName -vf "scale=${W}:-1,drawtext=fontfile='C\:/Windows/Fonts/arialbd.ttf':text='$label':x=6:y=6:fontsize=24:fontcolor=yellow:box=1:boxcolor=black@0.6" (Join-Path $tmp ("{0:D3}.png" -f $i))
    $i++
}
$rows = [math]::Ceiling($i / $Cols)
& $ff -y -loglevel error -i (Join-Path $tmp "%03d.png") -vf "tile=${Cols}x${rows}:padding=4:color=white" -frames:v 1 $Out
Remove-Item -Recurse -Force $tmp
Write-Output "sheet: $i images -> $Out"
