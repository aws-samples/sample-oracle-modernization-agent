# Application SQL Transform Agent — System Documentation

**OMA 서브 모듈: Application SQL Transform Agent 시스템 문서**

**버전**: 5.0
**최종 업데이트**: 2026-07
**상태**: Production Ready

---

## 목차

1. [시스템 개요](#시스템-개요)
2. [아키텍처](#아키텍처)
3. [파이프라인 워크플로우](#파이프라인-워크플로우)
4. [oma CLI 레퍼런스](#oma-cli-레퍼런스)
5. [2-Tier 룰 시스템](#2-tier-룰-시스템)
6. [상태 모델](#상태-모델)
7. [데이터 흐름](#데이터-흐름)
8. [디렉토리 구조](#디렉토리-구조)

---

## 시스템 개요

OMA Application SQL Transform Agent는 Oracle SQL을 PostgreSQL 또는 MySQL로
자동 변환하는 하이브리드 시스템이다. MyBatis Mapper XML 내의 SQL을 추출, 변환,
검증, 병합하여 최종 Target DB용 XML을 생성한다.

### 핵심 특징

- **하이브리드 아키텍처**: Claude Code 메인 세션(오케스트레이터) + subagent(LLM 작업) + CLI(결정적 인프라)
- **7단계 품질 파이프라인**: Analyze → Transform → Review → Validate → Merge → Test → Report
- **2-Tier 규칙 체계**: 정적 General Rules + 프로젝트별 동적 전략
- **체크포인트 승인형**: 매 단계 결과 요약 후 사용자 승인 대기
- **Review 재변환 루프**: FAIL 시 피드백 기반 자동 재변환 (최대 3라운드)
- **다중 Target DB**: PostgreSQL, MySQL 지원 (TARGET_DBMS_TYPE으로 전환)

---

## 아키텍처

### 전체 구조

```
Claude Code Session (Orchestrator)
  │
  ├── Skills (.claude/skills/)
  │     oma-pipeline   — 7-step workflow SSOT + checkpoint protocol
  │     oma-start      — session startup
  │     oma-status     — quick status check
  │
  ├── Subagents (.claude/agents/)  — LLM workers
  │     oma-transformer       — Oracle → Target DB SQL conversion
  │     oma-reviewer          — Multi-perspective review (syntax + equivalence)
  │     oma-validator         — Functional equivalence verification
  │     oma-test-fixer        — Fix SQL that fails DB execution
  │     oma-strategy-refiner  — Learn patterns from failures
  │
  └── oma CLI (src/cli/)  — deterministic infrastructure
        setup / status / db / analyze / merge / test-exec / report
```

### 역할 분담

| 계층 | 역할 | 상태 관리 |
|------|------|-----------|
| **Orchestrator** (메인 세션) | 파이프라인 진행, 체크포인트, 사용자 분기 | DB 읽기 (oma status) |
| **Subagents** (5개) | SQL 변환/리뷰/검증/수정/전략 보강 | DB 쓰기 (oma db save-*) |
| **oma CLI** (7 commands) | 스캔/병합/테스트/리포트 등 결정적 작업 | DB 읽기+쓰기 |

모든 계층이 `output/oma_control.db` (SQLite)를 SSOT로 공유한다.

### 실행 환경

- **런타임**: Claude Code CLI (로컬 실행)
- **패키지 관리**: uv
- **의존성**: defusedxml, sqlalchemy, rich (LLM SDK 의존 없음)

---

## 파이프라인 워크플로우

### 7단계 파이프라인

| # | 단계 | 실행 주체 | 필수 여부 | 산출물 |
|---|------|-----------|-----------|--------|
| 1 | **Analyze** | oma CLI (`oma analyze`) | Required | source_xml_list, transform_target_list, strategy draft |
| 2 | **Transform** | Subagent (oma-transformer) | Required | transformed SQL → extract_record + transform_history |
| 3 | **Review** | Subagent (oma-reviewer) | Required | review_result (PASS/FAIL) → review_history |
| 4 | **Validate** | Subagent (oma-validator) | Required | validation_result → validate_history |
| 5 | **Merge** | oma CLI (`oma merge`) | Required | output/xmls/merge/*.xml |
| 6 | **Test** | oma CLI (`oma test-exec`) | Optional* | test_result (PASS/FAIL/SKIP) |
| 7 | **Report** | oma CLI (`oma report`) | Optional | output/reports/oma_report.html |

*Test는 Target DB 접속 정보가 있을 때만 실행 가능.

### Review 재변환 루프

```
Review → FAIL?
  ├─ Yes (round < 3) → strategy-refiner → re-transform → re-review
  ├─ Yes (round = 3) → 수동 처리 목록으로 보고
  └─ No → Validate로 진행
```

### 체크포인트 프로토콜

매 단계 완료 시:
1. 결과 요약 (성공/실패 건수, 대표 사례 2~3건)
2. AskUserQuestion으로 다음 선택지 제시
3. 사용자 승인 없이 자동 진행 금지

---

## oma CLI 레퍼런스

실행: `uv run oma <command> [options]`

### setup

환경 설정 (DB 생성 + properties 저장).

```
oma setup [--non-interactive] [--source PATH] [--target-db postgresql|mysql]
          [--pg-host H] [--pg-port P] [--pg-database D] [--pg-user U]
          [--mysql-host H] [--mysql-port P] [--mysql-database D] [--mysql-user U]
          [--oracle-host H] [--oracle-port P] [--oracle-service S] [--oracle-user U]
```

비밀번호는 플래그로 받지 않음 — 환경변수(`PGPASSWORD`/`MYSQL_PASSWORD`/`ORACLE_SVC_PASSWORD`) 또는 interactive mode에서 입력.

### status

파이프라인 진행 현황 (step별 건수).

```
oma status [--json]
```

### analyze

Mapper 스캔 → SQL 추출 → 전략 초안 생성.

```
oma analyze [--source PATH] [--json]
```

`--source` 미지정 시 DB의 JAVA_SOURCE_FOLDER property 사용.

### db

상태 DB 조회/갱신 (subagent와 orchestrator의 공용 인터페이스).

```
oma db pending --step transform|review|validate [--max-batch N] [--only LIST] [--json]
oma db read-sql MAPPER_FILE SQL_ID [--json]
oma db read-transform MAPPER_FILE SQL_ID [--json]
oma db save-transform MAPPER_FILE SQL_ID [--sql-file PATH|-] [--notes TEXT] [--step STEP] [--json]
oma db set-reviewed MAPPER_FILE SQL_ID --result PASS|FAIL|SKIP [--feedback TEXT] [--feedback-file F] [--json]
oma db set-validated MAPPER_FILE SQL_ID --result PASS|FAIL|SKIP [--notes TEXT] [--json]
oma db set-tested MAPPER_FILE SQL_ID --result PASS|FAIL|SKIP|FIXED [--notes TEXT] [--json]
oma db get-property KEY [--json]
oma db reset --step transform|review|validate|test [--only LIST]
oma db feedback-patterns [--json]
```

### merge

변환된 SQL을 원본 XML에 병합하여 최종 mapper 생성.

```
oma merge [--mapper MAPPER_FILE] [--json]
```

`--mapper`: 단일 mapper만 재병합 (test-fixer 수정 후 사용).

### test-exec

Target DB에서 SQL 실행 테스트.

```
oma test-exec [--phase 0|1|1.5|all] [--only LIST] [--json]
```

- Phase 0: EXPLAIN (syntax validation)
- Phase 1: EXPLAIN + Execute
- Phase 1.5/all: Full (Oracle comparison 포함)

### report

HTML 리포트 재생성.

```
oma report
```

산출물: `output/reports/oma_report.html`

---

## 2-Tier 룰 시스템

### Tier 1: Static General Rules

위치: `src/reference/oracle_to_{dbms}_rules.md`

TARGET_DBMS_TYPE에 따라 선택됨:
- `oracle_to_postgresql_rules.md` (~680줄)
- `oracle_to_mysql_rules.md` (~600줄)

내용: 공통 Oracle→Target 변환 패턴, 함수 매핑, 자료형, PL/SQL 구문 등.
Subagent가 변환 시 Read하여 참조.

### Tier 2: Dynamic Project Strategy

위치: `output/strategy/transform_strategy.md`

Analyze 단계에서 초안 생성, 프로젝트 진행 중 oma-strategy-refiner가 갱신.
내용: 해당 프로젝트에서 발견된 고유 패턴, 반복 실패 수정법, 특수 함수/패키지 처리.

---

## 상태 모델

### oma_control.db

SQLite 데이터베이스. 위치: `$OMA_OUTPUT_DIR/oma_control.db` (기본: `output/oma_control.db`)

### 주요 테이블

| 테이블 | 역할 | 키 |
|--------|------|-----|
| `properties` | 설정 key/value (setup 결과) | PK: key |
| `source_xml_list` | 발견된 Mapper XML 목록 | PK: id |
| `transform_target_list` | **Master State** — SQL별 현재 상태 | UQ: (mapper_file, sql_id) |
| `extract_record` | SQL별 원본 기록 (UPSERT) | UQ: (mapper_file, sql_id) |
| `transform_history` | 변환 시도 로그 (append-only) | FK: (mapper_file, sql_id) |
| `review_history` | 리뷰 로그 (append-only) | FK: (mapper_file, sql_id) |
| `validate_history` | 검증 로그 (append-only) | FK: (mapper_file, sql_id) |
| `test_history` | 테스트 로그 (append-only) | FK: (mapper_file, sql_id) |
| `target_metadata` | Target DB 컬럼 메타데이터 (타입 캐스팅용) | — |

### transform_target_list 상태 플래그

```
transformed : N / Y / F  (Not done / Yes / Failed)
reviewed    : N / Y / F
validated   : N / Y
tested      : N / Y
completed   : N / Y
current_step: pending / extract / transform / review / validate / test / completed
```

상세 스키마: `docs/db-schema.md` 참조.

---

## 데이터 흐름

```
Source Java Project (MyBatis XMLs)
    │
    │ [oma analyze] scan + extract
    ▼
source_xml_list + transform_target_list + extract_record
    │
    │ [oma-transformer subagent] convert SQL
    ▼
transform_history (converted SQL saved via oma db save-transform)
    │
    │ [oma-reviewer subagent] syntax + equivalence check
    ▼
review_history (PASS/FAIL via oma db set-reviewed)
    │                         ↑ FAIL → re-transform loop
    │ [oma-validator subagent]
    ▼
validate_history (PASS/FAIL via oma db set-validated)
    │
    │ [oma merge] XML reassembly
    ▼
output/xmls/merge/*.xml (final mapper XMLs)
    │
    │ [oma test-exec] run against Target DB
    ▼
test_result (PASS/FAIL/SKIP via oma db set-tested)
    │
    │ [oma report]
    ▼
output/reports/oma_report.html
```

---

## 디렉토리 구조

```
repo/
├── .claude/
│   ├── agents/              # 5 subagent definitions (markdown)
│   │   ├── oma-transformer.md
│   │   ├── oma-reviewer.md
│   │   ├── oma-validator.md
│   │   ├── oma-test-fixer.md
│   │   └── oma-strategy-refiner.md
│   └── skills/              # Pipeline skills (loaded into main session)
│       ├── oma-pipeline/SKILL.md
│       ├── oma-start/SKILL.md
│       └── oma-status/SKILL.md
├── src/
│   ├── cli/                 # oma CLI (Python, single entry point)
│   │   ├── main.py
│   │   ├── cmd_setup.py
│   │   ├── cmd_status.py
│   │   ├── cmd_db.py
│   │   ├── cmd_analyze.py
│   │   ├── cmd_merge.py
│   │   ├── cmd_test.py
│   │   └── cmd_report.py
│   ├── core/                # Shared modules
│   │   ├── state_manager.py (SQLAlchemy ORM)
│   │   ├── models.py        (DB schema definitions)
│   │   ├── html_report.py   (self-contained HTML report)
│   │   ├── sql_executor.py  (psql/mysql execution)
│   │   ├── db_conn.py       (DB connection helpers)
│   │   ├── metadata.py      (target DB metadata)
│   │   └── complexity.py    (SQL complexity scoring)
│   ├── reference/           # Conversion rules (subagents Read these)
│   │   ├── oracle_to_postgresql_rules.md
│   │   └── oracle_to_mysql_rules.md
│   └── utils/
│       ├── project_paths.py (path constants)
│       └── db_utils.py      (query_by_mapper/update_by_mapper)
├── output/                  # Working directory (gitignored)
│   ├── oma_control.db
│   ├── strategy/transform_strategy.md
│   ├── xmls/origin/         # Analyze가 복사한 원본
│   ├── xmls/merge/          # Merge 산출물 (최종)
│   └── reports/oma_report.html
├── tests/cli/               # pytest suite
├── example/                 # E2E demo project
└── docs/                    # Documentation
```
