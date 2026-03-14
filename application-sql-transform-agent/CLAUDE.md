# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Application SQL Transform Agent — a sub-module of OMA (Oracle Modernization Agent). AI-powered Multi-Agent system that converts Oracle SQL to PostgreSQL/MySQL in MyBatis Mapper XML files. Uses Strands Agents SDK with AWS Bedrock (Claude Sonnet 4.5) to automatically transform, review, validate, and test SQL conversions.

## Setup & Run

```bash
# Install
uv sync

# Configure (interactive — creates OUTPUT_DIR/oma_control.db)
cd src && PYTHONPATH=. python3 run_setup.py

# Run — Kiro CLI (recommended) or Claude Code
cd src && kiro-cli    # or: claude
# /oma-setup → /oma-run all → /oma-status

# Run — Orchestrator CLI (legacy)
cd src && PYTHONPATH=. python3 run_orchestrator.py

# Run example (self-contained demo with 3 mapper XMLs, 42 SQLs)
cd example && ./setup.sh && ./run.sh
```

### Pipeline Steps (individual execution)

All scripts run from `src/` with `PYTHONPATH=.`. Working directory for state/output is controlled by `OMA_OUTPUT_DIR` env var (default: `./output/`).

```bash
cd src
PYTHONPATH=. python3 run_source_analyzer.py          # Scan mappers, extract SQLs, generate strategy
PYTHONPATH=. python3 run_sql_transform.py --workers 8   # Oracle → Target DB conversion
PYTHONPATH=. python3 run_sql_review.py --workers 4 --max-rounds 3  # Multi-perspective review
PYTHONPATH=. python3 run_sql_validate.py --workers 6    # Functional equivalence validation
PYTHONPATH=. python3 run_sql_test.py --workers 6        # DB execution test (requires target DB)
PYTHONPATH=. python3 run_sql_merge.py                   # Reassemble final Mapper XMLs
PYTHONPATH=. python3 run_strategy.py                    # Manual strategy refinement
```

## Architecture

### Directory Structure

```
src/
├── mcp_server/          # MCP orchestration (18 tools) — Claude Code / Kiro interface
├── agents/              # 8 Strands agents
│   └── (orchestrator, sql_transform, sql_review, ...)
├── run_*.py             # Pipeline runners
├── core/                # DB models, state manager (shared)
├── utils/               # Path constants
├── reference/           # Conversion rules, Java test tools
├── skills/              # Skill definitions (shared, symlinked)
├── AGENT.md             # Shared agent guide
└── CLAUDE.md            # Claude Code specific
```

### 8 Agents

| Agent | Location | Role |
|-------|----------|------|
| **Orchestrator** | `src/agents/orchestrator/` | Pipeline control, interactive CLI (14 tools) |
| **ReviewManager** | `src/agents/review_manager/` | Diff comparison/approval (5 tools) |
| **Source Analyzer** | `src/agents/source_analyzer/` | Mapper scan, SQL extraction, strategy generation |
| **Transform** | `src/agents/sql_transform/` | Oracle → Target DB conversion |
| **Review** | `src/agents/sql_review/` | Multi-perspective: Syntax + Equivalence agents in parallel → LLM Facilitator |
| **Validate** | `src/agents/sql_validate/` | Functional equivalence verification |
| **Test** | `src/agents/sql_test/` | Phase 0: EXPLAIN DML, Phase 1: Java SELECT, Phase 2: Agent fix |
| **Strategy Refine** | `src/agents/strategy_refine/` | Strategy learning and compression |

Each agent directory follows: `agent.py` (factory), `tools/` (Strands @tool functions), `prompt.md` (system prompt).

### Pipeline Flow

```
Setup → Analyze → Transform → Review → Validate → Test → Merge
                                ↓ FAIL (specific feedback)
                          Re-transform (max 3 rounds, round 2+: Strategy Refine)
```

### Key Modules

- **`src/core/models.py`** — SQLAlchemy ORM models (transform_target_list, properties, history tables)
- **`src/core/state_manager.py`** — Centralized DB access interface (SQLAlchemy ORM)
- **`src/core/progress.py`** — Real-time progress tracking
- **`src/utils/project_paths.py`** — All path constants, model IDs, DB path resolution, target DBMS config (`get_target_dbms()`, `get_rules_path()`, `load_prompt_text()`)

### 2-Tier Rule System

- **Tier 1 (Static):** `src/reference/oracle_to_{dbms}_rules.md` — common Oracle→Target DB patterns (selected by TARGET_DBMS_TYPE)
- **Tier 2 (Dynamic):** `output/strategy/transform_strategy.md` — project-specific patterns learned from failures

### Prompt Caching (3-Block)

Agents use SystemContentBlock with cachePoints for cost optimization:
- Block 1: System prompt + General Rules + cachePoint
- Block 2: Project Strategy + cachePoint
- Block 3: Per-request context

## Critical Coding Rules

### Model Selection
- **Main model:** `claude-sonnet-4-5-20250929` (`MODEL_ID`) — Prompt Caching supported
- **Lite model:** `claude-haiku-4-5-20251001` (`LITE_MODEL_ID`) — for Facilitator/summaries
- **Never use** Sonnet 4.6 or Opus 4.6 — Prompt Caching not supported, costs 5-10x more

### DB Access Patterns
- **StateManager** uses SQLAlchemy ORM — use it for transform_target_list operations
- **Tool functions** use parameterized `sqlite3` queries — never use f-string SQL
- Always use `with sqlite3.connect(str(DB_PATH), timeout=10) as conn:` for connections

### Agent Creation
- Use `suppress_streaming=True` parameter in agent factory to set `callback_handler=None` at creation time
- Never overwrite `agent.callback_handler` after creation (causes NoneType errors)

### Security
- No hardcoded secrets — use env vars or AWS Secrets Manager
- Passwords via `getpass.getpass()` only
- All XML parsing via `defusedxml`
- Target: 0 Critical findings in semgrep/bandit scans

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `OMA_OUTPUT_DIR` | Working directory (DB + all output) | `./output/` |
| `OMA_MODEL_ID` | Bedrock model for agents | Sonnet 4.5 cross-region |
| `OMA_LITE_MODEL_ID` | Bedrock model for Facilitator | Haiku 4.5 |
| `TARGET_DBMS_TYPE` | Target DB type (`postgresql` or `mysql`) | DB property or `postgresql` |
| `AWS_DEFAULT_REGION` | AWS region | — |
