# OMA Database Schema

## 테이블 관계도

```
┌─────────────────────────────┐        ┌───────────────────────────┐
│     source_xml_list         │        │       properties          │
│  (발견된 Mapper XML 목록)     │        │    (설정 key/value)        │
│                             │        │                           │
│  PK: id                     │        │  PK: key                  │
│      file_path              │        │      value                │
│      file_name              │        │      description          │
│      relative_path          │        └───────────────────────────┘
└──────────────┬──────────────┘
               │ scan
               │ (source_analyzer)
               ▼
┌──────────────────────────────────────────────────────────────────┐
│                     transform_target_list                        │
│              ★ MASTER STATE TABLE (현재 상태)                     │
│                                                                  │
│  PK: id                                                          │
│  ID: (mapper_file, sql_id)  ←─────── JOIN key (모든 history)      │
│      sql_type, seq_no, namespace                                 │
│      source_file, target_file                                    │
│                                                                  │
│  [Pipeline Flags]                                                │
│      transformed  : N/Y/F                                        │
│      reviewed     : N/Y/F                                        │
│      validated    : N/Y                                          │
│      tested       : N/Y                                          │
│      completed    : N/Y                                          │
│      current_step : pending/extract/transform/review/validate/   │
│                     test/completed                               │
│                                                                  │
│  [Result Details]                                                │
│      transform_count, review_result, validation_result           │
│      test_result (PASS/FAIL/SKIP/FIXED), test_notes              │
└──┬──────┬──────┬──────┬──────┬───────────────────────────────────┘
   │      │      │      │      │
   │      │      │      │      │ 1 : 1 (master record, UPSERT)
   │      │      │      │      ▼
   │      │      │      │   ┌──────────────────────────────────┐
   │      │      │      │   │       extract_record             │
   │      │      │      │   │   ★ MASTER RECORD (1 per SQL)    │
   │      │      │      │   │                                  │
   │      │      │      │   │  PK: id                          │
   │      │      │      │   │  UQ: (mapper_file, sql_id) ◄── UPSERT
   │      │      │      │   │      mapper_path                 │
   │      │      │      │   │      sql_type, namespace, seq_no │
   │      │      │      │   │      original_sql  (원본 Oracle) │
   │      │      │      │   │      created_at                  │
   │      │      │      │   └──────────────────────────────────┘
   │      │      │      │
   │      │      │      │ 1 : N (attempt per retry, append-only)
   │      │      │      ▼
   │      │      │   ┌──────────────────────────────────┐
   │      │      │   │       transform_history          │
   │      │      │   │   (변환 시도 로그, 매 재시도)       │
   │      │      │   │                                  │
   │      │      │   │  PK: id                          │
   │      │      │   │  FK: (mapper_file, sql_id)       │
   │      │      │   │      attempt_no                  │
   │      │      │   │      original_sql                │
   │      │      │   │      transformed_sql             │
   │      │      │   │      transform_log (reasoning)   │
   │      │      │   │      model_id, status            │
   │      │      │   │      error_message               │
   │      │      │   │      duration_ms                 │
   │      │      │   └──────────────────────────────────┘
   │      │      │
   │      │      │ 1 : N (review round, append-only)
   │      │      ▼
   │      │   ┌──────────────────────────────────┐
   │      │   │        review_history            │
   │      │   │   (Syntax + Equivalence + Facil) │
   │      │   │                                  │
   │      │   │  PK: id                          │
   │      │   │  FK: (mapper_file, sql_id)       │
   │      │   │      round_no                    │
   │      │   │      reviewed_sql                │
   │      │   │      syntax_result (JSON)        │
   │      │   │      equivalence_result (JSON)   │
   │      │   │      facilitator_verdict         │
   │      │   │        PASS/FAIL/PASS_WITH_WARN  │
   │      │   │      review_log                  │
   │      │   │      duration_ms                 │
   │      │   └──────────────────────────────────┘
   │      │
   │      │ 1 : N (validation round, append-only)
   │      ▼
   │   ┌──────────────────────────────────┐
   │   │      validation_history          │
   │   │  (정적 equivalence 검증 로그)     │
   │   │                                  │
   │   │  PK: id                          │
   │   │  FK: (mapper_file, sql_id)       │
   │   │      round_no                    │
   │   │      validated_sql               │
   │   │      verdict (PASS/FAIL)         │
   │   │      validation_log              │
   │   │      issues_found (JSON array)   │
   │   │      duration_ms                 │
   │   └──────────────────────────────────┘
   │
   │ 1 : N (test attempt, append-only)
   ▼
┌──────────────────────────────────┐
│          test_history            │
│  (DB 실행 테스트 로그)            │
│                                  │
│  PK: id                          │
│  FK: (mapper_file, sql_id)       │
│      phase                       │
│        phase0_explain (DML)      │
│        phase1_java    (SELECT)   │
│        phase2_fix     (Agent fix)│
│      attempt_no                  │
│      tested_sql                  │
│      bind_parameters (JSON)      │
│      test_result                 │
│        PASS/FAIL/SKIP/FIXED      │
│      execution_log               │
│      sql_state (JDBC SQLState)   │
│      error_message, stack_trace  │
│      execution_time_ms           │
│      rows_affected               │
└──────────────────────────────────┘

┌──────────────────────────────────┐
│       target_metadata            │
│  (PG/MySQL 컬럼 타입 캐시)        │
│                                  │
│  PK: id                          │
│  IDX: (table_name, column_name)  │
│      table_schema, data_type     │
└──────────────────────────────────┘
   ▲
   │ lookup (convert_sql, validate)
   │
   └─── transform/validate agents query for type-aware conversions
```

## 테이블 분류 (3 종류)

### 1. State Table (현재 상태)
| 테이블 | 역할 | Row 증가 |
|---|---|---|
| `transform_target_list` | SQL별 파이프라인 진행 상태 (flags + current_step) | 1 per SQL (UPDATE) |

### 2. Master Record (원본 자료)
| 테이블 | 역할 | Row 증가 |
|---|---|---|
| `extract_record` | 추출된 원본 Oracle SQL (UNIQUE UPSERT) | 1 per SQL |
| `source_xml_list` | 발견된 Mapper XML 파일 목록 | 1 per XML |
| `target_metadata` | Target DB 컬럼 타입 캐시 | 1 per column |
| `properties` | key/value 설정 | 1 per key |

### 3. History Log (append-only audit)
| 테이블 | 역할 | Row 증가 |
|---|---|---|
| `transform_history` | 변환 시도마다 1행 (재시도 포함) | N per SQL |
| `review_history` | 리뷰 round마다 1행 (3-perspective) | N per SQL |
| `validation_history` | 검증 round마다 1행 | N per SQL |
| `test_history` | 테스트 phase/attempt마다 1행 | N per SQL |

## 조인 규칙

모든 테이블은 `(mapper_file, sql_id)` 복합키로 조인:

```sql
-- 특정 SQL의 전체 파이프라인 이력
SELECT t.sql_id, t.current_step, t.test_result,
       e.original_sql,
       COUNT(DISTINCT th.id) AS transform_attempts,
       COUNT(DISTINCT rh.id) AS review_rounds,
       COUNT(DISTINCT vh.id) AS validation_rounds,
       COUNT(DISTINCT teh.id) AS test_attempts
FROM transform_target_list t
LEFT JOIN extract_record       e   USING (mapper_file, sql_id)
LEFT JOIN transform_history    th  USING (mapper_file, sql_id)
LEFT JOIN review_history       rh  USING (mapper_file, sql_id)
LEFT JOIN validation_history   vh  USING (mapper_file, sql_id)
LEFT JOIN test_history         teh USING (mapper_file, sql_id)
WHERE t.sql_id = ?
GROUP BY t.sql_id;
```

## Pipeline Flow

```
Analyze → split_mapper
   └─→ INSERT/UPDATE transform_target_list (state)
   └─→ UPSERT extract_record (master, UNIQUE(mapper_file, sql_id))

Transform → convert_sql
   └─→ UPDATE transform_target_list.transformed='Y', current_step='transform'
   └─→ INSERT transform_history (attempt_no++)

Review → set_reviewed (multi-perspective + facilitator)
   └─→ UPDATE transform_target_list.reviewed='Y'/'F', current_step='review'
   └─→ INSERT review_history (round_no++)

Validate → set_validated
   └─→ UPDATE transform_target_list.validated='Y', current_step='validate'
   └─→ INSERT validation_history (round_no++)

Merge → (파일 시스템 작업, DB 변경 없음)

Test → run_single_test / explain_dml_batch
   └─→ UPDATE transform_target_list.tested, test_result, current_step='test'
   └─→ INSERT test_history (phase + attempt_no++)
```

## 정보의 흐름 (Information Flow)

### 큰 그림: 3 레인 모델

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  IN  (원본)  │ ──→ │  WORK (상태) │ ──→ │ OUT (결과물) │
└──────────────┘     └──────────────┘     └──────────────┘
 source_xml_list      transform_target     파일 시스템:
 extract_record       _list (State)         output/merge/
 target_metadata      + 4 history tables    output/reports/
 (외부 DB meta)                              oma_report.html
```

- **IN 레인** — 외부에서 수집한 불변 원본 (파일 시스템 + Oracle/PG 카탈로그)
- **WORK 레인** — 파이프라인이 만드는 모든 DB 쓰기 (state + audit log)
- **OUT 레인** — 파일 시스템의 변환 결과 (merge XML + HTML 보고서)

### 단계별 정보 흐름

각 단계는 **읽기(source) → 가공(processor) → 쓰기(sink)** 3단 구조로 동작.

#### ① Analyze (Source Analyzer)
| 측면 | 내용 |
|---|---|
| 읽기 | 디스크의 `**/*Mapper.xml` 스캔 → `defusedxml` 파싱 |
| 가공 | XML 구조 분해 → SQL 조각 + 메타(sql_type, namespace, seq_no) |
| 쓰기 | `source_xml_list` (파일 목록) · `transform_target_list` (state row 생성, current_step='pending') · `extract_record` UPSERT (원본 SQL 보관) |
| 외부 I/O | 파일시스템 READ-only + PG/MySQL `information_schema` → `target_metadata` 캐시 |

#### ② Transform
| 측면 | 내용 |
|---|---|
| 읽기 | `extract_record.original_sql` + `target_metadata` (타입 인식) + `transform_strategy.md` (Tier 2 룰) |
| 가공 | Strands Agent (Sonnet 4.5) → Oracle → Target SQL 생성, prompt caching 3-block |
| 쓰기 | `transform_history` (매 attempt 1행, reasoning 포함) · `transform_target_list.transformed='Y'`, `current_step='transform'` |
| 실패 시 | status='failure' + error_message 기록, row는 pending 상태 유지 → 다음 run에서 retry |

#### ③ Review
| 측면 | 내용 |
|---|---|
| 읽기 | `transform_history` 최신 `transformed_sql` + 원본 `extract_record.original_sql` |
| 가공 | Syntax agent + Equivalence agent **병렬 실행** → LLM Facilitator (Haiku 4.5)가 PASS/FAIL/PASS_WITH_WARN 결정 |
| 쓰기 | `review_history` (round_no 증가, syntax/equivalence JSON + facilitator_verdict + review_log) · `transform_target_list.reviewed='Y'/'F'` |
| FAIL | reviewed='F' → Transform 재호출 (max 3 rounds), 2라운드부터 Strategy Refine 개입 |

#### ④ Validate
| 측면 | 내용 |
|---|---|
| 읽기 | `review_history` 최신 `reviewed_sql` + `target_metadata` |
| 가공 | 정적 equivalence 검증 (타입/NULL/집합연산/정렬 semantic) |
| 쓰기 | `validation_history` (verdict PASS/FAIL + issues_found JSON) · `transform_target_list.validated='Y'` |

#### ⑤ Merge (파일 시스템만)
| 측면 | 내용 |
|---|---|
| 읽기 | `transform_target_list` (target_file path) + 변환된 SQL snippets |
| 가공 | XML 재조립 — 주석/변수/OGNL/`<include refid>` 원형 보존 |
| 쓰기 | `output/merge/**/*.xml` 파일 — **DB 쓰기 없음** (결과물은 디스크) |

#### ⑥ Test
| 측면 | 내용 |
|---|---|
| 읽기 | `output/merge/*.xml` (Phase 1은 MERGE_DIR 기준 Java 번들 실행) + `target_metadata` (bind parameter 타입 추론) |
| 가공 | **Phase 0**: EXPLAIN (DML) · **Phase 1**: Java JDBC 실행 (SELECT, `--select-only`) · **Phase 2**: 실패 시 Agent fix → convert_sql → 자동 re-merge → re-test |
| 쓰기 | `test_history` (phase + attempt_no, tested_sql, bind_parameters JSON, sql_state, rows_affected) · `transform_target_list.tested`, `test_result` (PASS/FAIL/SKIP/FIXED), `test_notes` |
| 보고서 | `output/reports/test_result_report.md` (Pass/Fail/Skip 분류별 종합) |

### 조회 흐름 (Read Path)

```
HTML Report (output/reports/oma_report.html)       Orchestrator Agent
      │                                                  │
      ▼                                                  ▼
단계 종료 시 generate_html_report()             search_sql_ids, check_step_status
  → sqlite3 직접 질의 + JOIN                    (tool 기반 상태 조회)
      │                                                  │
      └─────────────┬────────────────────────────────────┘
                    ▼
            transform_target_list  +  4 history tables
            (State + current_step)   (drill-down: attempt_no / round_no 순)
                    │                         │
                    └── JOIN (mapper_file, sql_id) ──┘

HTML Report 탭 → LEFT JOIN 4 history tables → 탭별 렌더
      ├─ Transform : transform_history (status/duration_ms/transform_log/error_message)
      ├─ Review    : review_history (facilitator_verdict/syntax/equivalence/review_log)
      ├─ Validation: validation_history (verdict/issues_found/validation_log)
      └─ Test      : test_history (phase/test_result/sql_state/bind_parameters)
```

### 핵심 원칙

1. **Append-only audit (4 history tables)** — 절대 UPDATE/DELETE 하지 않음. 모든 재시도/라운드가 물리적으로 보존되어 디버깅/메트릭 가능.
2. **Master record (1: extract_record)** — `(mapper_file, sql_id)` UNIQUE + UPSERT로 원본은 항상 최신 1건 유지. 재스캔 시 중복 없음.
3. **State table (1: transform_target_list)** — UPDATE 전용. 현재 진행 상태를 한 곳에 응축 → HTML 보고서/Orchestrator 조회 최적화.
4. **Universal join key** — 모든 history/state/master 테이블이 `(mapper_file, sql_id)` 복합키로 USING JOIN 가능.
5. **Best-effort write** — `history_writer.py`는 모든 insert를 try/except로 감싸 파이프라인 붕괴 방지 (`_warn()`만 stderr 출력).
6. **No DB in Merge** — 파일 시스템 산출물(`output/merge/`)은 Test 단계에서 역으로 읽힘. DB는 상태/로그만.
