#!/bin/bash
# OMA Example — Run orchestrator (after setup.sh)
#
# Usage:
#   cd example
#   ./run.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_DIR="$PROJECT_ROOT/src"
VENV_DIR="$SCRIPT_DIR/.venv"

# Example uses its own output directory (keeps src/ clean)
export OMA_OUTPUT_DIR="${OMA_OUTPUT_DIR:-$SCRIPT_DIR/output}"

if [ ! -d "$VENV_DIR" ]; then
    echo "Error: Virtual environment not found. Run ./setup.sh first."
    exit 1
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "=== OMA Orchestrator ==="
cd "$SRC_DIR"
python run_orchestrator.py
