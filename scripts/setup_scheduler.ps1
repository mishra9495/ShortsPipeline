# Run this ONCE as Administrator to register the daily render task.
# Right-click PowerShell -> Run as Administrator -> paste this path and press Enter.

$action = New-ScheduledTaskAction `
    -Execute "PowerShell.exe" `
    -Argument "-NonInteractive -ExecutionPolicy Bypass -File D:\ShortsPipeline\scripts\daily_render.ps1" `
    -WorkingDirectory "D:\ShortsPipeline"

$trigger = New-ScheduledTaskTrigger -Daily -At "23:30"

$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Hours 16) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

Register-ScheduledTask `
    -TaskName "ShortsPipeline_DailyRender" `
    -TaskPath "\ShortsPipeline\" `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Daily YouTube Shorts render pipeline" `
    -RunLevel Highest `
    -Force

Write-Host "Done. Task registered: ShortsPipeline\ShortsPipeline_DailyRender"
Write-Host "It will run every day at 11:30 PM and wake the PC if asleep."
