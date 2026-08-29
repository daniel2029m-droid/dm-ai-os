<#
.SYNOPSIS
Registers a Windows Scheduled Task to launch DM AI OS automatically on Windows logon/boot.
#>

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir
$targetScript = "$rootDir\start_platform.ps1"

$taskName = "DMAIOS_AutoRecovery"

Write-Host "Registering Windows Scheduled Task: $taskName ..." -ForegroundColor Cyan
Write-Host "Target Script: $targetScript" -ForegroundColor DarkGray

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$targetScript`" -Daemon"
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 0)

try {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "Auto-recovery for DM AI OS Services on Windows Startup/Logon" | Out-Null
    Write-Host "==========================================================" -ForegroundColor Green
    Write-Host " [SUCCESS] Scheduled Task '$taskName' registered successfully!" -ForegroundColor Green
    Write-Host " DM AI OS will now auto-start automatically on Windows logon." -ForegroundColor White
    Write-Host "==========================================================" -ForegroundColor Green
} catch {
    Write-Host "Error registering scheduled task: $_" -ForegroundColor Red
}
