#!/usr/bin/env bash
# run.sh - Run MAYA INTELLIGENCE using JARVIS venv python
# Usage: ./run.sh [command] [args...]

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JARVIS_ROOT="$PROJECT_ROOT/../JARVIS"
VENV_PYTHON="$JARVIS_ROOT/.venv/bin/python"

if [[ ! -f "$VENV_PYTHON" ]]; then
    echo "Error: JARVIS venv not found at $VENV_PYTHON"
    echo "Please run 'uv sync' in the JARVIS directory first."
    exit 1
fi

export PYTHONPATH="$JARVIS_ROOT:$PROJECT_ROOT:${PYTHONPATH:-}"

exec "$VENV_PYTHON" -m maya_intelligence "$@"