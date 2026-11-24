<# 
.SYNOPSIS
    Run MAYA INTELLIGENCE using JARVIS venv python.

.DESCRIPTION
    Sets PYTHONPATH to include both JARVIS and MAYA INTELLIGENCE roots,
    then runs python -m maya_intelligence with the provided arguments.

.EXAMPLE
    .\run.ps1 chat
    .\run.ps1 memory add --category personal --key "name" --value "User"
#>

param(
    [string[]]$Args
)

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$JarvisRoot = Join-Path $ProjectRoot "..\JARVIS"
$VenvPython = Join-Path $JarvisRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Error: JARVIS venv not found at $VenvPython"
    Write-Error "Please run 'uv sync' in the JARVIS directory first."
    exit 1
}

$env:PYTHONPATH = "$JarvisRoot;$ProjectRoot;$env:PYTHONPATH"

& $VenvPython -m maya_intelligence @Args