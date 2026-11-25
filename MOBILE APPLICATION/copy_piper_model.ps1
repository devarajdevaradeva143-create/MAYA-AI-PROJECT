# copy_piper_model.ps1
# Copies the Piper Tamil voice model from MAYA AI\voice\tamil\ into the app's
# assets folder. Run from the MOBILE APP\ directory.
#
# Prerequisites:
#   - MAYA AI\voice\tamil\ta_IN-rasa_female-medium.onnx (~60 MB)
#   - MAYA AI\voice\tamil\ta_IN-rasa_female-medium.onnx.json
#
# Note: tokens.txt and espeak-ng-data/ are NOT in the repo. You must obtain
# them separately (sherpa-onnx tts-models release) before Piper TTS will load.
# See: https://github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models

$ErrorActionPreference = "Stop"

$srcRoot = Resolve-Path "..\MAYA AI\voice\tamil"
$dstRoot = Join-Path (Get-Location) "app\src\main\assets\piper"

Write-Host "Source: $srcRoot"
Write-Host "Destination: $dstRoot"

# Ensure destination exists
New-Item -ItemType Directory -Path $dstRoot -Force | Out-Null

# Copy the model + config
foreach ($file in @("ta_IN-rasa_female-medium.onnx", "ta_IN-rasa_female-medium.onnx.json")) {
    $src = Join-Path $srcRoot $file
    $dst = Join-Path $dstRoot $file
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination $dst -Force
        $size = (Get-Item -LiteralPath $dst).Length
        Write-Host ("Copied {0} ({1} bytes)" -f $file, $size)
    } else {
        Write-Warning "Source not found: $src"
    }
}

# Check for tokens.txt + espeak-ng-data (not in repo, must be obtained separately)
$tokens = Join-Path $srcRoot "tokens.txt"
$espeak = Join-Path $srcRoot "espeak-ng-data"
if (-not (Test-Path -LiteralPath $tokens)) {
    Write-Warning "tokens.txt not found at $tokens — obtain from sherpa-onnx tts-models release"
}
if (-not (Test-Path -LiteralPath $espeak)) {
    Write-Warning "espeak-ng-data/ not found at $espeak — obtain from sherpa-onnx tts-models release"
}

Write-Host "Done. Piper assets are in $dstRoot (git-ignored)."
