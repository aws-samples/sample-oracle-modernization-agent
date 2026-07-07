#!/usr/bin/env bash
# OMA example — CC subagent 구조에서는 Claude Code 세션이 오케스트레이터입니다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "This example runs inside a Claude Code session:"
echo ""
echo "  export OMA_OUTPUT_DIR=$SCRIPT_DIR/output"
echo "  cd $PROJECT_ROOT && claude"
echo "  Then type: '변환 시작' or /oma:start"
echo ""
echo "Run ./setup.sh first if you haven't already."
