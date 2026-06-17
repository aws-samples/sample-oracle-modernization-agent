# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

**Application SQL Transform Agent** — a sub-module of OMA (Oracle Modernization Agent).
Converts Oracle SQL to PostgreSQL/MySQL in MyBatis Mapper XML files using a hybrid
Claude Code subagent + `oma` CLI architecture.

- **Main session = Orchestrator**: The Claude Code conversation controls the pipeline
- **`.claude/agents/`** = 5 subagents (LLM workers): oma-transformer, oma-reviewer, oma-validator, oma-test-fixer, oma-strategy-refiner
- **`src/cli/`** = `oma` CLI (deterministic infrastructure): status, db, analyze, merge, test-exec, report, setup
- **SQLite `oma_control.db`** = state SSOT (all pipeline progress)

When the user requests a SQL transformation task, load the `oma-pipeline` skill and
follow its procedure. Do NOT perform SQL conversion directly in the main session.

## Setup & Commands

```bash
# Install dependencies
uv sync

# Run oma CLI
uv run oma --help
uv run oma setup --non-interactive --source <path> --target-db postgresql
uv run oma status
uv run oma analyze
uv run oma merge
uv run oma report

# Run tests
uv run pytest tests/cli/ -v

# E2E example
cd example && ./setup.sh
# Then launch claude and say "변환 시작"
```

## Architecture

```
Claude Code Session (Orchestrator)
  │
  ├── Skills (.claude/skills/)
  │     oma-pipeline.md   — 7-step workflow SSOT + checkpoint protocol
  │     oma-start.md      — session startup
  │     oma-status.md     — quick status check
  │
  ├── Subagents (.claude/agents/)  — LLM workers
  │     oma-transformer.md     — Oracle → Target DB SQL conversion
  │     oma-reviewer.md        — Multi-perspective review (syntax + equivalence)
  │     oma-validator.md       — Functional equivalence verification
  │     oma-test-fixer.md      — Fix SQL that fails DB execution
  │     oma-strategy-refiner.md — Learn patterns from failures
  │
  └── oma CLI (src/cli/)  — deterministic infrastructure
        setup / status / db / analyze / merge / test-exec / report
```

### Directory Structure

| Path | Purpose |
|------|---------|
| `.claude/agents/` | 5 subagent definitions (spawned by orchestrator) |
| `.claude/skills/` | Pipeline skills (loaded into main session) |
| `src/cli/` | `oma` CLI — single Python entry point, subcommands |
| `src/core/` | Shared modules: state_manager (SQLAlchemy), sql_executor, tc_generator, html_report, metadata, complexity, db_conn |
| `src/reference/` | Conversion rules (`oracle_to_postgresql_rules.md`, `oracle_to_mysql_rules.md`) — subagents Read these |
| `src/utils/` | Path constants (`project_paths.py`), DB helpers (`db_utils.py`) |
| `output/` | Working directory (DB + all artifacts) |
| `tests/cli/` | pytest suite for CLI |

### 2-Tier Rule System

- **Tier 1 (Static):** `src/reference/oracle_to_{dbms}_rules.md` — common patterns (selected by TARGET_DBMS_TYPE)
- **Tier 2 (Dynamic):** `output/strategy/transform_strategy.md` — project-specific patterns learned from failures

## Critical Coding Rules

### DB Access Patterns
- **StateManager** uses SQLAlchemy ORM — use for `transform_target_list` operations
- **CLI/tool code** uses parameterized `sqlite3` queries — **never f-string SQL**
- Always: `with sqlite3.connect(str(DB_PATH), timeout=10) as conn:`
- **mapper_file queries** — use `utils/db_utils.query_by_mapper()` / `update_by_mapper()` (handles path prefix variations)

### XML Parsing
- All XML parsing via `defusedxml` — never `xml.etree.ElementTree` directly

### Subagent Definitions
- When modifying `.claude/agents/*.md`, never embed full conversion rule text — subagents Read rules from `src/reference/` at runtime
- Keep agent prompts focused on procedure and output format

### CLI Output Convention
- Machine-readable: `--json` flag outputs JSON to stdout
- Human-readable: formatted output to stderr
- Exit codes: 0 = success, 1 = error, 2 = invalid args

### Security
- No hardcoded secrets — use env vars
- All XML parsing via `defusedxml`
- Parameterized SQL only (no string interpolation)

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `OMA_OUTPUT_DIR` | Working directory (DB + all output) | `./output/` |
| `TARGET_DBMS_TYPE` | Target DB type (`postgresql` or `mysql`) | DB property or `postgresql` |
| **Oracle DB** | *`oma setup` stores in DB properties* | |
| `ORACLE_HOST` | Oracle DB host | — |
| `ORACLE_SID` | Oracle Service Name | — |
| `ORACLE_USER` | Oracle user | — |
| **Target DB** | *`oma setup` stores in DB properties* | |
| `PGHOST` / `MYSQL_HOST` | Target DB host | — |
| `PGDATABASE` / `MYSQL_DATABASE` | Target DB name | — |

## Pipeline (7 Steps)

```
Analyze → Transform → Review → Validate → Merge → Test → Report
                        ↓ FAIL
                  Re-transform (max 3 rounds)
```

Each step writes to `oma_control.db`. After each step the orchestrator presents
results and waits for checkpoint approval before proceeding.

## Response Style

- Communicate in Korean (user preference)
- After each step: brief summary (counts, pass/fail) + next recommended action
- No long log dumps — counts and 2-3 representative samples max
