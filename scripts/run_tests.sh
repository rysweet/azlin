#!/bin/bash
# Test runner script using the correct virtual environment

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# This worktree's venv is at the parent azlin directory
VENV_PYTHON="/Users/ryan/src/TuesdayTmp/azlin/.venv/bin/python3"

# Check if venv exists
if [ ! -f "$VENV_PYTHON" ]; then
    echo "Error: Virtual environment not found at $VENV_PYTHON"
    exit 1
fi

# Run pytest with any arguments passed to this script
"$VENV_PYTHON" -m pytest "$@"
