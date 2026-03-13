# OMA Example — Quick Start

This folder contains a sample Spring Boot + MyBatis application with Oracle SQL mapper XMLs.
Use it to try OMA's Oracle-to-PostgreSQL migration pipeline.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- AWS credentials configured (`aws configure`) with **Bedrock access only**

> **Note:** PostgreSQL (target DB) is NOT required for this example. All pipeline steps except Test work without a database. During setup, skip the DB connection prompt (`n`). Only Bedrock API access is needed.

## Run

```bash
cd example
./setup.sh    # 1회: 의존성 설치 (uv) + 프로젝트 설정
./run.sh      # 이후: 오케스트레이터 실행
```

### Setup hints

| Prompt | What to enter |
|--------|---------------|
| `JAVA_SOURCE_FOLDER` | The script prints the path — just copy and paste it |
| `SOURCE_DBMS_TYPE` | `oracle` (default) |
| `TARGET_DBMS_TYPE` | `postgresql` (default) |
| `OMA_MODEL_ID` | Press Enter for default (Sonnet 4.5) |
| `OMA_LITE_MODEL_ID` | Press Enter for default (Haiku 4.5) |
| `DB 접속 정보 설정?` | **`n`** — not needed for this example |

### After setup

In the orchestrator, type commands like:
- `전체 수행` — run full pipeline (Analyze → Transform → Review → Validate → Merge)
- `샘플 변환 5개` — sample transform 5 representative SQLs first
- `진행 단계 확인` — check pipeline status
- `종료` — exit

> Test step is automatically skipped when no DB is configured.

## What's included

3 MyBatis mapper XMLs (42 SQL statements) covering major Oracle conversion patterns:

| Mapper | SQL | Key Oracle Features |
|--------|-----|---------------------|
| UserMapper | 15 | `(+)` outer join, `NVL`, `DECODE`, `MERGE INTO`, `LISTAGG`, `CUBE`/`ROLLUP`, `ROWNUM`, window functions |
| ProductMapper | 14 | `CONNECT BY`/`START WITH`, `SYS_CONNECT_BY_PATH`, `CONNECT_BY_ISLEAF`, `LEVEL`, sequence `NEXTVAL` |
| OrderMapper | 13 | `MEDIAN`, `ROWNUM` pagination, `(+)` outer join, `EXTRACT` interval, window functions |

## Output

After running, check `example/output/`:
- `example/output/xmls/transform/` — converted PostgreSQL mapper XMLs
- `example/output/reports/` — diff reports (original vs converted)
- `example/output/strategy/` — learned conversion patterns
