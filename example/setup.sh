#!/bin/bash
# OMA Example — Setup (venv + dependencies + interactive config)
#
# Usage:
#   cd example
#   ./setup.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_DIR="$PROJECT_ROOT/src"
VENV_DIR="$SCRIPT_DIR/.venv"
MAPPER_DIR="$SCRIPT_DIR/src/main/resources/sqlmap/mapper"

# Example uses its own output directory (keeps src/ clean)
export OMA_OUTPUT_DIR="${OMA_OUTPUT_DIR:-$SCRIPT_DIR/output}"

# --- venv ---

if [ ! -d "$VENV_DIR" ]; then
    echo "=== Creating Python virtual environment ==="
    python3 -m venv "$VENV_DIR"
    echo "Created: $VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "=== Installing dependencies ==="
pip install -q -r "$PROJECT_ROOT/requirements.txt"
echo "Done."
echo ""

# --- OMA Setup ---

echo "=== OMA Setup ==="
echo ""
echo "Mapper XML location (copy this when prompted for JAVA_SOURCE_FOLDER):"
echo "  $MAPPER_DIR"
echo ""
echo "NOTE: This is an example run. DB connection info is NOT required."
echo "      When asked 'DB 접속 정보를 지금 설정하시겠습니까?', enter 'n'."
echo "      (Transform, Review, Validate steps work without DB)"
echo ""

cd "$SRC_DIR"
python run_setup.py
