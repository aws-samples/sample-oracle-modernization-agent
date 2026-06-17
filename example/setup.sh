#!/usr/bin/env bash
# OMA example setup — CC subagent 구조용
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "=== Installing dependencies (uv) ==="
uv sync

export OMA_OUTPUT_DIR="$SCRIPT_DIR/output"
echo "=== OMA setup (target: PostgreSQL) ==="
uv run oma setup --non-interactive \
  --source "$SCRIPT_DIR/src" --target-db postgresql

echo ""
echo "Setup complete. Next steps:"
echo "  1) export OMA_OUTPUT_DIR=$SCRIPT_DIR/output"
echo "  2) cd $PROJECT_ROOT && claude"
echo "  3) In Claude Code: type '변환 시작' or /oma:start"
echo ""
echo "  (Keep OMA_OUTPUT_DIR set throughout the session — all oma commands use it)"
