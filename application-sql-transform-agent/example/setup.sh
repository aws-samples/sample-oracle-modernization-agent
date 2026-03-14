#!/bin/bash
# OMA Example — Setup (dependencies + config)
#
# Usage:
#   cd example
#   ./setup.sh             # non-interactive (recommended)
#   ./setup.sh --interactive   # manual config

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_DIR="$PROJECT_ROOT/src"
MAPPER_DIR="$SCRIPT_DIR/src/main/resources/sqlmap/mapper"

# Example uses its own output directory (keeps src/ clean)
export OMA_OUTPUT_DIR="${OMA_OUTPUT_DIR:-$SCRIPT_DIR/output}"

# --- Install dependencies via uv ---

echo "=== Installing dependencies ==="
uv sync --project "$PROJECT_ROOT"
echo "Done."
echo ""

# --- OMA Setup ---

cd "$SRC_DIR"

if [ "$1" = "--interactive" ]; then
    echo "=== OMA Setup (interactive) ==="
    echo ""
    echo "Mapper XML location (copy this when prompted for JAVA_SOURCE_FOLDER):"
    echo "  $MAPPER_DIR"
    echo ""
    uv run --project "$PROJECT_ROOT" python run_setup.py
else
    echo "=== OMA Setup (auto) ==="
    uv run --project "$PROJECT_ROOT" python run_setup.py --defaults "$MAPPER_DIR"
fi
