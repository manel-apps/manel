#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/.venv"

if [ ! -f "$VENV/bin/activate" ]; then
    echo "Error: Virtual environment not found at $VENV"
    echo "Run: python -m venv .venv && .venv/bin/pip install -e ."
    exit 1
fi

source "$VENV/bin/activate"

if [ $# -eq 0 ]; then
    python -m manel.cli gui
else
    python -m manel.cli "$@"
fi
