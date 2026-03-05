# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OMA (Oracle Migration Assistant) — AI-powered Multi-Agent system that converts Oracle SQL to PostgreSQL in MyBatis Mapper XML files. Uses Strands Agents SDK with AWS Bedrock (Claude Sonnet 4.5) to automatically transform, review, validate, and test SQL conversions.

## Setup & Run

```bash
# Install
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure (interactive — creates OUTPUT_DIR/oma_control.db)
python3 src/run_setup.py

# Run (interactive orchestrator)
python3 src/run_orchestrator.py

# Run example (self-contained demo with 3 mapper XMLs, 42 SQLs)
cd example && ./run_example.sh
```

### Pipeline Steps (individual execution)

All scripts run from project root. Working directory for state/output is controlled by `OMA_OUTPUT_DIR` env var (default: `./output/`).

```bash
python3 src/run_source_analyzer.py          # Scan mappers, extract SQLs, generate strategy
python3 src/run_sql_transform.py --workers 8   # Oracle → PostgreSQL conversion
python3 src/run_sql_review.py --workers 4 --max-rounds 3  # Multi-perspective review
python3 src/run_sql_validate.py --workers 6    # Functional equivalence validation
python3 src/run_sql_test.py --workers 6        # DB execution test (requires PostgreSQL)
python3 src/run_sql_merge.py                   # Reassemble final Mapper XMLs
python3 src/run_strategy.py                    # Manual strategy refinement
```

## Architecture

### 8 Agents

| Agent | Location | Role |
|-------|----------|------|
| **Orchestrator** | `src/agents/orchestrator/` | Pipeline control, interactive CLI (14 tools) |
| **ReviewManager** | `src/agents/review_manager/` | Diff comparison/approval (5 tools) |
| **Source Analyzer** | `src/agents/source_analyzer/` | Mapper scan, SQL extraction, strategy generation |
| **Transform** | `src/agents/sql_transform/` | Oracle → PostgreSQL conversion |
| **Review** | `src/agents/sql_review/` | Multi-perspective: Syntax + Equivalence agents in parallel → LLM Facilitator |
| **Validate** | `src/agents/sql_validate/` | Functional equivalence verification |
| **Test** | `src/agents/sql_test/` | Phase 0: EXPLAIN DML, Phase 1: Java SELECT, Phase 2: Agent fix |
| **Strategy Refine** | `src/agents/strategy_refine/` | Strategy learning and compression |

Each agent directory follows: `agent.py` (factory), `tools/` (Strands @tool functions), `prompt/` (system prompt text files).

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
- **`src/utils/project_paths.py`** — All path constants, model IDs, DB path resolution

### 2-Tier Rule System

- **Tier 1 (Static):** `src/reference/oracle_to_postgresql_rules.md` — common Oracle→PG patterns
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
| `AWS_DEFAULT_REGION` | AWS region | — |
