# Maya AI Windows Autostart Setup
#
# Registers Maya AI to start on login via Windows Task Scheduler.
# Run as Administrator once after installation.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File LAPTOP/windows/app/autostart.ps1

$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path "C:\Users\devar\Desktop\MAYA AI PROJECT"
$mayaMaya = Join-Path $projectRoot "JARVIS"
$pythonExe = Join-Path $mayaMaya ".venv-engine\Scripts\python.exe"
$trayScript = Join-Path $projectRoot "LAPTOP\windows\app\maya_tray.py"

$taskName = "MayaAI"
$taskDescription = "Maya AI — Local Personal Assistant"

# Check if python exists
if (-not (Test-Path $pythonExe)) {
    Write-Error "Python not found at $pythonExe. Run uv sync first."
    exit 1
}

# Check if tray script exists
if (-not (Test-Path $trayScript)) {
    Write-Error "Tray script not found at $trayScript"
    exit 1
}

# Delete existing task if present
try {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
    Write-Host "Removed existing Maya AI task."
} catch {
    # Task didn't exist, that's fine
}

# Create the task
$action = New-ScheduledTaskAction -Execute $pythonExe -Argument "$trayScript" -WorkingDirectory $mayaMaya
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType S4U -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description $taskDescription

Write-Host "Maya AI autostart configured successfully."
Write-Host "Maya will start on login via Task Scheduler (`"$taskName`")."
