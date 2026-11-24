# Maya AI — Windows autostart installer
#
# Registers a Task Scheduler job that starts the Maya tray app at logon.
#
# Usage (normal PowerShell, no admin needed for current-user task):
#   powershell -ExecutionPolicy Bypass -File "LAPTOP\windows\app\install_autostart.ps1"
#
# Uninstall:
#   Unregister-ScheduledTask -TaskName "MayaAI" -Confirm:$false

$ErrorActionPreference = "Stop"

$appDir = $PSScriptRoot
$root = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $appDir))
$exe = Join-Path $root "LAPTOP\windows\dist\mayaai.exe"
$taskName = "MayaAI"

if (-not (Test-Path $exe)) {
    Write-Error "mayaai.exe not found at $exe. Build first (see BUILD.md 3.4)."
    exit 1
}

$action = New-ScheduledTaskAction -Execute $exe -Argument "--tray" -WorkingDirectory (Split-Path -Parent $exe)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Maya AI tray app (local assistant)" -Force | Out-Null

Write-Host "Autostart installed: task '$taskName'"
Write-Host "  runs: $exe --tray"
Write-Host "  remove: Unregister-ScheduledTask -TaskName $taskName -Confirm:`$false"