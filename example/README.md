# OMA Example — Quick Start

This folder contains a sample Spring Boot + MyBatis application with Oracle SQL mapper XMLs.
Use it to try OMA's Oracle-to-PostgreSQL migration pipeline.

> For application details (API endpoints, project structure), see [APPLICATION.md](APPLICATION.md).

## Prerequisites

- Python 3.11+
- AWS credentials configured (`aws configure`) with Bedrock access

## Run

```bash
cd example
./run_example.sh
```

This single script will:
1. Create a Python virtual environment (`.venv/`)
2. Install dependencies from `requirements.txt`
3. Run `run_setup.py` — enter project settings when prompted
4. Run `run_orchestrator.py` — interactive migration pipeline

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
- `분석 시작` — analyze mapper XMLs
- `변환 시작` — transform Oracle SQL to PostgreSQL
- `리뷰 시작` — multi-perspective review
- `검증 시작` — functional equivalence validation
- `종료` — exit

### Run steps separately

```bash
./run_example.sh setup    # Setup only (venv + configuration)
./run_example.sh run      # Orchestrator only (after setup)
```

## What's included

10 MyBatis mapper XMLs with Oracle-specific SQL:

| Mapper | Features |
|--------|----------|
| UserMapper | `(+)` outer joins, `DECODE`, `NVL`, `CONNECT BY` hierarchy |
| OrderMapper | `ROWNUM` pagination, window functions, `MERGE INTO` |
| ProductMapper | `SYS_CONNECT_BY_PATH`, `CONNECT_BY_ISLEAF`, `LISTAGG` |
| PaymentMapper | `TO_CHAR` date formatting, `DECODE`, subquery aggregation |
| InventoryMapper | `MERGE INTO`, `BULK COLLECT` patterns, `MINUS` |
| SellerMapper | `NVL2`, `INSTR`, `REGEXP_LIKE`, `WM_CONCAT` |
| ShippingMapper | `ADD_MONTHS`, `MONTHS_BETWEEN`, `LAST_DAY` |
| PromotionMapper | `DECODE` nested, `DUAL`, `SYSDATE` arithmetic |
| CustomerServiceMapper | `XMLAGG`, `LISTAGG`, `REGEXP_SUBSTR` |
| AnalyticsMapper | Complex analytics with `PARTITION BY`, `ROLLUP`, `CUBE` |

## Output

After running, check `output/` in the project root:
- `output/xmls/transform/` — converted PostgreSQL mapper XMLs
- `output/reports/` — diff reports (original vs converted)
- `output/strategy/` — learned conversion patterns
