# Maya AI launcher (Windows / PowerShell)
#
# Usage:
#   .\MAYA AI\scripts\maya.ps1 chat
#   .\MAYA AI\scripts\maya.ps1 todo add "Buy milk"
#   .\MAYA AI\scripts\maya.ps1 monitor status
#
# Runs the custom CLI with the same Python 3.13 interpreter as the engine.

param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Rest)

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$maya = Join-Path $root "JARVIS"
$venvPython = Join-Path $maya ".venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Error "JARVIS venv not found at $venvPython"
    Write-Error "Please run 'uv sync' in the JARVIS directory first."
    exit 1
}

$env:PYTHONPATH = "$maya;$env:PYTHONPATH"
& $venvPython -m custom.cli @Rest
exit $LASTEXITCODE
