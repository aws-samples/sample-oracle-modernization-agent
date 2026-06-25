# OMA Example — Oracle to PostgreSQL

3 MyBatis mapper XMLs (44 Oracle SQL statements) converted to PostgreSQL using the OMA pipeline inside Claude Code.

## What's Included

| Mapper | SQL Count | Key Oracle Features |
|--------|-----------|---------------------|
| UserMapper | 15 | `(+)` outer join, `NVL`, `DECODE`, `MERGE INTO`, `LISTAGG`, `CUBE`/`ROLLUP`, `ROWNUM`, window functions |
| ProductMapper | 15 | `CONNECT BY`/`START WITH`, `SYS_CONNECT_BY_PATH`, `CONNECT_BY_ISLEAF`, `LEVEL`, sequence `NEXTVAL` |
| OrderMapper | 14 | `MEDIAN`, `ROWNUM` pagination, `(+)` outer join, `EXTRACT` interval, window functions |

## Prerequisites

- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) installed
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- AWS credentials with Bedrock access (`aws configure`)

> PostgreSQL (target DB) is NOT required. All steps except Test work without a database.

## Run

```bash
# 1. Setup (install deps + configure)
cd example
./setup.sh

# 2. Launch Claude Code
export OMA_OUTPUT_DIR=$(pwd)/output
cd .. && claude

# 3. Inside Claude Code session, type:
#    '변환 시작' or /oma:start
```

## Pipeline Flow

Inside the Claude Code session, OMA runs as CC subagents. Each step pauses for approval:

```
Analyze → Transform → Review → Validate → Merge → Test
                        ↓ FAIL (specific feedback)
                  Re-transform (max 3 rounds)
```

- **Analyze** — Scans mapper XMLs, extracts SQL, generates conversion strategy
- **Transform** — Oracle SQL to PostgreSQL conversion
- **Review** — Multi-perspective review (Syntax + Equivalence + Facilitator)
- **Validate** — Functional equivalence verification
- **Merge** — Reassembles final mapper XMLs with converted SQL
- **Test** — EXPLAIN + Execute + Compare (requires target DB)

## Output

After pipeline completes, check `example/output/`:

| Path | Contents |
|------|----------|
| `xmls/merge/` | Final reassembled PostgreSQL mapper XMLs |
| `reports/oma_report.html` | Integrated HTML report (7 tabs) |
| `strategy/` | Learned conversion patterns |
