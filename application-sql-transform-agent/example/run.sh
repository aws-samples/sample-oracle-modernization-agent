#!/bin/bash
# OMA Example — Launch the orchestrator REPL (after setup.sh)
#
# run_orchestrator.py boots a Strands Agent with 21 tools and drives the
# whole pipeline from natural-language prompts. See src/AGENT.md for the
# full tool list and workflow rules. After each stage the pipeline regenerates
# output/reports/oma_report.html — open it in a browser to inspect progress.
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

echo "=== OMA Orchestrator REPL ==="
cd "$SRC_DIR"
uv run --project "$PROJECT_ROOT" python run_orchestrator.py
