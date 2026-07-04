# Application SQL Transform Agent

![Python](https://img.shields.io/badge/python-3.11+-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Claude Code](https://img.shields.io/badge/Claude_Code-subagent-purple)

> Part of **OMA (Oracle Modernization Agent)** — an AI-powered Oracle to PostgreSQL/MySQL modernization toolkit.

> **Warning**: Sample code for educational purposes. Not for production use without review. See [Disclaimer](#disclaimer).

## What is this?

**Application SQL Transform Agent** is a sub-module of OMA that automatically transforms Oracle SQL to PostgreSQL/MySQL in MyBatis Mapper XML files. It uses Claude Code subagents as LLM workers and the `oma` CLI for deterministic infrastructure, converting, reviewing, validating, and testing hundreds to thousands of SQL statements.

Instead of DBAs and developers manually converting and testing SQL, AI agents automatically handle the process and complete validation against the target database.

<details>
<summary><b>Korean</b></summary>

**Application SQL Transform Agent**는 OMA의 서브 모듈로, MyBatis Mapper XML 내 Oracle SQL을 PostgreSQL/MySQL로 자동 변환합니다.
Claude Code subagent가 LLM 작업자로, `oma` CLI가 결정적 인프라로 동작하여, 수백~수천 개의 SQL을 자동 변환, 검증, 테스트합니다.

</details>

### Before / After

```sql
-- Oracle (Before)
SELECT NVL(u.name, 'none'), DECODE(u.status, 'A', 'active', 'inactive')
FROM users u, orders o
WHERE u.id = o.user_id(+)
  AND ROWNUM <= 10
```
```sql
-- PostgreSQL (After)
SELECT COALESCE(u.name, 'none'), CASE u.status WHEN 'A' THEN 'active' ELSE 'inactive' END
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
LIMIT 10
```

## Requirements

- **Claude Code CLI** (latest)
- **Python 3.11+**
- **uv** (Python package manager)
- AWS credentials (for target DB test phase, optional)

## Quick Start

```bash
# 1. Clone and install
git clone <repo-url> && cd application-sql-transform-assistant
uv sync

# 2. Configure (creates output/oma_control.db)
uv run oma setup --non-interactive \
  --source /path/to/java-project/src/main/resources/mapper \
  --target-db postgresql

# 3. Launch Claude Code and start the pipeline
claude
# Then say: "변환 시작" or type /oma:start
```

The Claude Code session acts as the orchestrator — it loads the `oma-pipeline` skill
which defines the full 7-step workflow and checkpoint protocol.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Claude Code Session  (= Orchestrator)                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────┐  ┌────────────────┐  │
│  │ oma-pipeline│  │ oma-start   │  │ oma-status│  │ (user dialog)  │  │
│  │   (skill)   │  │   (skill)   │  │  (skill)  │  │                │  │
│  └──────┬──────┘  └─────────────┘  └───────────┘  └────────────────┘  │
│         │ delegates LLM work                                            │
│         ▼                                                               │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │  .claude/agents/  (5 Subagents — LLM Workers)                  │    │
│  │  oma-transformer · oma-reviewer · oma-validator                 │    │
│  │  oma-test-fixer · oma-strategy-refiner                         │    │
│  └────────────────────────────────────────────────────────────────┘    │
│         │ invokes deterministic operations                              │
│         ▼                                                               │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │  oma CLI  (src/cli/)                                           │    │
│  │  status · db · analyze · merge · test-exec · report · setup    │    │
│  └────────────────────────────────────────────────────────────────┘    │
│         │ reads/writes                                                  │
│         ▼                                                               │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │  SQLite oma_control.db  (State SSOT)                           │    │
│  └────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

| Layer | Location | Role |
|-------|----------|------|
| **Orchestrator** | Claude Code main session | Pipeline control, user interaction, checkpoint approval |
| **Subagents** | `.claude/agents/` | LLM-powered SQL transformation, review, validation, test fix, strategy refinement |
| **oma CLI** | `src/cli/` | Deterministic infrastructure: DB queries, file merging, SQL execution, reporting |
| **Core** | `src/core/` | Shared modules: state_manager, sql_executor, tc_generator, html_report |
| **Rules** | `src/reference/` | Conversion rules (subagents Read these) |
| **State** | `output/oma_control.db` | Single SQLite DB — all pipeline state |

## Pipeline

7 stages, each followed by a checkpoint requiring user approval before proceeding:

| # | Stage | Actor | What happens |
|---|-------|-------|--------------|
| 1 | **Analyze** | `oma analyze` | Scan mapper XMLs, extract SQLs, generate initial strategy |
| 2 | **Transform** | `oma-transformer` subagent | Oracle to Target DB conversion (per SQL) |
| 3 | **Review** | `oma-reviewer` subagent | Multi-perspective review; FAIL loops back to Transform (max 3 rounds) |
| 4 | **Validate** | `oma-validator` subagent | Functional equivalence verification |
| 5 | **Merge** | `oma merge` | Reassemble final Mapper XMLs from converted snippets |
| 6 | **Test** | `oma test-exec` + `oma-test-fixer` | Execute against target DB; auto-fix failures |
| 7 | **Report** | `oma report` | Generate HTML report |

```
Analyze → Transform → Review → Validate → Merge → Test → Report
                        ↓ FAIL
                  Re-transform (max 3 rounds, round 2+: strategy refine)
```

After each stage, the orchestrator presents results and waits for user approval
("proceed" / "retry failed" / "skip") before advancing.

## oma CLI Reference

```bash
uv run oma --help
```

| Subcommand | Description |
|------------|-------------|
| `setup` | Configure source paths, target DB type, connection info |
| `status` | Show pipeline progress (per-step counts) |
| `db pending` | List SQLs pending for a given step |
| `db read-sql` | Read original SQL for a mapper/sql_id |
| `db read-transform` | Read current transformed SQL |
| `db save-transform` | Save transformed SQL (from subagent) |
| `db set-reviewed` | Mark SQL as review-passed |
| `db set-validated` | Mark SQL as validation-passed |
| `db set-tested` | Record test result |
| `db get-property` | Read a property from DB |
| `db reset` | Reset a pipeline step (with safety prompts) |
| `db feedback-patterns` | Extract failure patterns for strategy refinement |
| `analyze` | Run source analysis (extract SQLs, generate strategy) |
| `merge` | Reassemble Mapper XMLs from converted snippets |
| `test-exec` | Execute SQL against target DB (EXPLAIN / run) |
| `report` | Generate HTML report |

## Example

The `example/` folder contains a self-contained demo with 3 Oracle MyBatis mapper XMLs (44 SQLs):

```bash
cd example && ./setup.sh
claude   # then: "변환 시작"
```

See [example/README.md](example/README.md) for details.

## Applying to a Real Project (Site Runbook)

For converting an actual customer codebase (not the bundled example) — covering
source-path selection, target-DB connection setup, resume-after-interrupt, and
troubleshooting — see **[docs/SITE_GUIDE.md](docs/SITE_GUIDE.md)**.

## Generated Assets

| Asset | Location |
|-------|----------|
| Converted SQL snippets | `output/xmls/transform/` |
| Project-specific strategy | `output/strategy/transform_strategy.md` |
| Final Mapper XMLs | `output/xmls/merge/` |
| HTML Report (7 tabs) | `output/reports/oma_report.html` |
| Fix history (3-way diff) | `output/logs/fix_history/` |

## Data Model

All pipeline state lives in `output/oma_control.db` (SQLite). Tables are split into
3 semantic categories, joinable by `(mapper_file, sql_id)`:

| Category | Tables | Write Semantics |
|---|---|---|
| **State** | `transform_target_list` | UPDATE — one row per SQL |
| **Master** | `extract_record`, `source_xml_list`, `target_metadata`, `properties` | UPSERT |
| **History** | `transform_history`, `review_history`, `validation_history`, `test_history` | INSERT-only (append) |

See [docs/db-schema.md](docs/db-schema.md) for full schema documentation.

## 2-Tier Rule System

- **Tier 1 (Static):** `src/reference/oracle_to_{dbms}_rules.md` — common patterns
- **Tier 2 (Dynamic):** `output/strategy/transform_strategy.md` — project-specific patterns learned from failures

## Cost

Costs are determined by Claude Code CLI usage (per your Anthropic plan or AWS Bedrock
proxy). The `oma` CLI itself performs no LLM calls — all inference goes through
Claude Code subagents.

## Project Structure

```
application-sql-transform-assistant/
├── .claude/
│   ├── agents/               # 5 Subagents (LLM workers)
│   │   ├── oma-transformer.md
│   │   ├── oma-reviewer.md
│   │   ├── oma-validator.md
│   │   ├── oma-test-fixer.md
│   │   └── oma-strategy-refiner.md
│   └── skills/               # Pipeline skills
│       ├── oma-pipeline.md
│       ├── oma-start.md
│       └── oma-status.md
├── src/
│   ├── cli/                  # oma CLI (single entry point)
│   ├── core/                 # Shared: state_manager, sql_executor, html_report...
│   ├── reference/            # Conversion rules
│   │   ├── oracle_to_postgresql_rules.md
│   │   └── oracle_to_mysql_rules.md
│   └── utils/                # Path constants, db_utils
├── output/                   # Working directory ($OMA_OUTPUT_DIR)
│   ├── oma_control.db
│   ├── xmls/transform/
│   ├── xmls/merge/
│   ├── strategy/
│   └── reports/
├── example/                  # Self-contained demo (3 mappers, 44 SQLs)
├── docs/                     # Documentation
└── tests/                    # pytest test suite
```

## Disclaimer

This code is provided as a sample for educational and demonstration purposes only.

- **NOT FOR PRODUCTION USE**: Do not deploy without additional security testing.
- **AI-Generated Output**: SQL transformations must be reviewed before execution.
- **No Warranty**: Provided "AS IS" without warranty of any kind.

## License

See [LICENSE](LICENSE) file for details.

---

**Last Updated**: 2026-06
**Version**: 5.0 (CC Subagent Architecture)
