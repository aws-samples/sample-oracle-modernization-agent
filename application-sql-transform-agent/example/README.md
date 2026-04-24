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
./setup.sh    # 1회: 의존성 설치 + 자동 설정 (프롬프트 없음)
./run.sh      # 이후: 오케스트레이터 실행
```

> `setup.sh` uses default values automatically. For manual configuration, use `./setup.sh --interactive`.

### Orchestrator (메인)

`run.sh`가 Strands Agent 기반 REPL(21 tools)을 실행합니다. 자연어로 명령합니다:

| 명령 예시 | 동작 |
|---------|------|
| `파이프라인 현황 알려줘` | 설정 + 단계별 진행률 표시 |
| `전체 수행` | Analyze → Transform → Review → Validate → Merge 순차 실행 |
| `분석 수행` | Analyze 단계만 실행 |
| `변환 수행` | Transform 단계만 실행 |
| `샘플 변환 3개` | 3개 대표 SQL만 변환 (전체 reset 없음) |
| `리뷰 수행` | Review — 다관점 리뷰 (Syntax + Equivalence + Facilitator) |
| `검증 수행` | Validate — 기능 동치 검증 |
| `병합 수행` | Merge — 최종 mapper XML 재조립 |
| `테스트 수행` | Test — EXPLAIN + Execute + Oracle-PG Compare |
| `selectUserList 재변환` | 특정 SQL 검색 → reset → 재변환 |
| `test fail 분류하고 보고서 만들어` | 실패 분류 + 보고서 생성 |
| `parameter 카테고리 전부 SKIP` | 인프라 실패 일괄 SKIP |
| `종료` | Exit (`q`/`quit`/`exit`) |

> Test step requires DB connection (PG/MySQL). Without DB, test is skipped.
> With Oracle DB, TC auto-generation + Oracle-PG result comparison enabled.

### CLI (보조)

Claude Code / Kiro CLI에서도 `AGENT.md`를 참조해 동일 tool을 Bash로 호출 가능합니다.

### Pipeline

```
Analyze → Transform → Review → Validate → Merge → Test
                        ↓ FAIL
                  Re-transform (max 3 rounds)

Test: TC Gen → EXPLAIN (all) → Execute (SELECT) → Compare (if Oracle) → Agent fix
```

### Reports

각 단계 종료 시 `output/reports/oma_report.html` 자동 재생성 — 브라우저에서 7개 탭 확인.

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
- `example/output/xmls/merge/` — final reassembled mapper XMLs
- `example/output/reports/oma_report.html` — 통합 HTML 보고서 (7 tabs)
- `example/output/test/test_cases.json` — auto-generated test parameters
- `example/output/strategy/` — learned conversion patterns
