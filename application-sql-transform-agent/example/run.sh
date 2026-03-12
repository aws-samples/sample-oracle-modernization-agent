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
# Example uses its own output directory (keeps src/ clean)
export OMA_OUTPUT_DIR="${OMA_OUTPUT_DIR:-$SCRIPT_DIR/output}"

echo "=== OMA Orchestrator ==="
cd "$SRC_DIR"
uv run --project "$PROJECT_ROOT" python run_orchestrator.py
