#!/bin/bash
# OMA Example — Oracle to PostgreSQL migration demo
#
# Usage:
#   cd example
#   ./run_example.sh          # Full: setup + orchestrator
#   ./run_example.sh setup    # Setup only
#   ./run_example.sh run      # Orchestrator only (after setup)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC_DIR="$PROJECT_ROOT/src"
VENV_DIR="$SCRIPT_DIR/.venv"
MAPPER_DIR="$SCRIPT_DIR/src/main/resources/sqlmap/mapper"

# Example uses its own output directory (keeps src/ clean)
export OMA_OUTPUT_DIR="${OMA_OUTPUT_DIR:-$SCRIPT_DIR/output}"

# --- Functions ---

setup_venv() {
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
}

run_setup() {
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"

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
}

run_orchestrator() {
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"

    echo "=== OMA Orchestrator ==="
    cd "$SRC_DIR"
    python run_orchestrator.py
}

# --- Main ---

case "${1:-full}" in
    setup)
        setup_venv
        run_setup
        ;;
    run)
        run_orchestrator
        ;;
    full|"")
        setup_venv
        run_setup
        run_orchestrator
        ;;
    *)
        echo "Usage: $0 [setup|run|full]"
        exit 1
        ;;
esac
