# Orchestrator Agent Design

> Last synced with code: 2026-04-24. The authoritative runtime contract lives in
> [`src/AGENT.md`](../../src/AGENT.md) and [`src/agents/orchestrator/prompt.md`](../../src/agents/orchestrator/prompt.md).
> This document captures architecture intent; if it diverges from those files, trust the code.

## 1. Agent 개요

### 1.1 목적
- 대화형 파이프라인 제어, 상태 모니터링, 단건 SQL 관리를 통해 Oracle → PostgreSQL/MySQL 마이그레이션을 한 곳에서 지휘
- 자연어 명령을 파이프라인 tool 호출로 변환하고, 각 단계 결과를 해석하여 사용자에게 다음 액션을 제안

### 1.2 사용 시나리오
- 전체 파이프라인 순차 실행 (`analyze` → `transform` → `review` → `validate` → `merge` → `test`)
- 단계별 재실행 / 단일 SQL 재변환 / 실패 건 분류·SKIP / 전략 재생성 및 학습
- 산출물 안내 (HTML 리포트, 테스트 보고서, diff 보고서)

### 1.3 완료 기준
- [x] 21개 tool을 통해 파이프라인 전 단계를 자연어로 제어
- [x] `transform_target_list` 기반 상태를 StateManager로 중앙 조회
- [x] 단일 SQL 흐름(transform/validate/test/fix)을 tool 4개로 제공
- [x] SQL 비교·승인은 ReviewManager Agent에게 위임 (`delegate_to_review_manager`)
- [x] 완료 후 `output/reports/oma_report.html` (7 tab) 생성·안내

---

## 2. 아키텍처

### 2.1 실행 형태
- 엔트리: `src/run_orchestrator.py` → Strands Agent REPL
- 모델: `claude-sonnet-4-5-20250929` (env `OMA_MODEL_ID`) — Prompt Caching 활성
- 프롬프트: `src/agents/orchestrator/prompt.md` (Tool 목록 + Workflow + Response Style)
- 상태 저장: `$OMA_OUTPUT_DIR/oma_control.db` (SQLite)

### 2.2 의존 모듈
| 계층 | 모듈 | 역할 |
|------|------|------|
| DB 접근 | `core/state_manager.py` | SQLAlchemy ORM — `transform_target_list`/properties 중앙 조회 |
| Path 규약 | `utils/project_paths.py` | `DB_PATH`, `MERGE_DIR`, `REPORTS_DIR`, `get_target_dbms()` |
| 리포트 | `core/html_report.py` + `core/report_template.html` | 7 탭 단일 HTML 리포트 |
| 히스토리 | `core/history_writer.py` | transform/review/validate/test 시도별 append-only 기록 |

### 2.3 하위 Agent와의 관계
- **ReviewManager** (`agents/review_manager/`) — Diff/승인/수정/보고서. Orchestrator가 `delegate_to_review_manager` 한 개 tool로 위임.
- **Transform/Validate/Test 단일 실행** — `agents/sql_transform/single_transform.py`, `sql_validate/single_validate.py`, `sql_test/test_tools.py`, `sql_test/single_test_fix.py`를 각각 tool로 래핑.

---

## 3. 명령 해석 가이드

실제 라우팅 규칙은 `prompt.md`에 있지만 핵심 패턴은 다음과 같음.

### 3.1 파이프라인 실행
- "분석해줘" / "변환해줘" / ... → `run_step('<step>')` (pending 건만 처리)
- "전체 실행" → `check_step_status()` → 남은 단계를 순서대로 `run_step(...)`
- "재실행/재수행/다시" → **사용자 확인 후** `reset_step(step)` + `run_step(step)`
- "실패만 재수행" → `reset_step(step, failed_only=True)` + `run_step(step)`

### 3.2 샘플 변환
- "샘플 N개 변환" → `run_step('transform', sample=N)` (sample은 자체 reset 포함. `reset_step` 호출 금지)

### 3.3 단일 SQL
- 키워드 검색 → `search_sql_ids(keyword)` → 확인 → 단건 실행
  - Transform: `transform_single_sql(mapper_file, sql_id)`
  - Validate: `validate_single_sql(mapper_file, sql_id)`
  - Test (only): `run_single_test(mapper_file, sql_id)`
  - Test + Fix: `test_and_fix_single_sql(mapper_file, sql_id)`

### 3.4 Review / Diff / 보고서
- "비교/리뷰/승인/리포트" → `delegate_to_review_manager(user_request)` 일임

### 3.5 Test 실패 처리
1. `classify_test_failures()` 로 카테고리 분류
2. `skip_by_category(category)` 또는 `skip_sql(mapper_file, sql_id, reason)`
3. 남은 FAIL은 `retry failed test` (기본) 또는 `retry failed test --fix` (Agent 자동 수정 + re-merge)

### 3.6 전략 관리
- 최초 생성: `generate_project_strategy()` — analyze 단계에서 자동 호출됨. 빠짐 시 수동 호출
- 학습: `refine_project_strategy('validation_failures'|'test_failures'|'all_failures')`
- 압축: `compact_strategy()` — 파일이 크거나 learning entry가 많을 때

---

## 4. Tool 카탈로그 (21 tools)

`src/agents/orchestrator/agent.py` 팩토리와 `prompt.md`를 기준으로 분류.

### 4.1 Pipeline Control (13)

| Tool | 목적 | 핵심 반환 |
|------|------|-----------|
| `check_setup` | `oma_control.db` 존재 + 필수 properties 점검 | `{ready, missing[]}` |
| `check_step_status` | 단계별 진행률/완료 플래그 | `{extracted, transformed, …, transform_complete, …}` |
| `run_step` | `analyze/transform/review/validate/merge/test` 실행 (pending만). `sample=N`/`failed_only=True` 옵션 | `{status, details, needs_merge?}` |
| `reset_step` | 단계 초기화 (`failed_only=True` 지원) | `{status, step, reset_count}` |
| `get_summary` | 전체 요약 + 산출물 경로 | dict |
| `search_sql_ids` | 키워드로 SQL 탐색 | `{total, results}` |
| `get_failures` | 단계별 FAIL 조회 | 리스트 |
| `backup_output` | `output/backup/{step}_{timestamp}/` 로 스냅샷 | 경로 |
| `classify_test_failures` | Test FAIL 카테고리 분류 | 분류 표 |
| `skip_by_category` | 카테고리 단위 SKIP 처리 | 카운트 |
| `skip_sql` | 단건 SKIP (`reason` 기록) | dict |
| `generate_test_report` | `output/reports/test_result_report.md` 생성 | 경로 |
| `setup_test_parameters` | Phase 1 Java bulk test용 parameters.properties 구성 | dict |

### 4.2 Strategy (3)

| Tool | 목적 |
|------|------|
| `generate_project_strategy` | SQL 패턴 분석 → `output/strategy/transform_strategy.md` 작성. 큰 경우 `needs_compression=true` 안내 |
| `refine_project_strategy` | 실패 학습 섹션 추가 (feedback_type: `validation_failures`/`test_failures`/`all_failures`) |
| `compact_strategy` | 중복 패턴 병합 / 크기 축소 |

### 4.3 Single SQL (4)

| Tool | 동작 |
|------|------|
| `transform_single_sql(mapper_file, sql_id)` | Transform Agent 직접 호출 |
| `validate_single_sql(mapper_file, sql_id)` | Validate Agent (auto-fix 포함) |
| `run_single_test(mapper_file, sql_id)` | DB 실행 테스트만 (수정 없음) |
| `test_and_fix_single_sql(mapper_file, sql_id)` | 테스트 실패 시 Agent fix → convert_sql → auto re-merge → 재테스트 |

### 4.4 Delegation (1)

| Tool | 위임 대상 |
|------|-----------|
| `delegate_to_review_manager(user_request)` | ReviewManager Agent가 6개 tool(`show_sql_diff`, `generate_diff_report`, `get_review_candidates`, `approve_conversion`, `suggest_revision`, `generate_test_failure_report`)로 응답 |

---

## 5. Workflow 기본 절차

```text
1) check_setup
   └── ready=False → run_setup 안내
2) check_step_status
3) next step에 맞는 run_step (transform 전엔 strategy 파일 확인)
4) 각 단계 후 check_step_status 재호출 → 결과/다음 액션 제안
5) test 완료 후 FAIL 있으면 classify_test_failures → skip_* → retry
6) 모든 단계 완료 시 get_summary + 보고서 안내
```

### 5.1 산출물 안내 문구

```text
📊 파이프라인 완료! 보고서:
1. 전체 통합 보고서: output/reports/oma_report.html (7 탭, 각 단계 종료 시 자동 재생성)
2. Test 종합 보고서: output/reports/test_result_report.md (선택)
3. 변환 비교 보고서: output/reports/diff_report_all.md (선택)
```

`oma_report.html` 탭 구성: Dashboard / Analyze / Transform / Review / Validate / Merge / Test. 각 runner 종료 시 `generate_html_report()` 가 재생성.

---

## 6. 오류 처리 전략

| 상황 | Orchestrator 동작 |
|------|--------------------|
| Setup 미완료 | "`python3 src/run_setup.py`" 안내, 파이프라인 진행 중단 |
| 단계 의존성 위반 | 선행 단계 실행 제안 (예: review 전 transform_complete 확인) |
| 재실행 요청 | 삭제 범위/영향/비용 경고 문구 표시 → 명시적 승인 받은 뒤 `reset_step` |
| Test 후 FAIL 잔존 | `classify_test_failures` → 카테고리 안내 → SKIP/재시도/자동 수정 옵션 제시 |
| Test 자동 수정 결과 | 수정된 SQL은 자동 re-merge. 사용자에게 추가 merge 요구하지 않음 |
| Strategy 파일 비대 | `needs_compression=true` 수신 시 `compact_strategy` 실행 여부 질문 |

### 6.1 역순 리셋 가이드 (필수 경고)

Test까지 완료된 SQL을 Transform부터 재수행하려면 사용자에게 다음 경고를 보낸 뒤에만 진행:

```text
⚠️ Test까지 완료된 SQL이 있어 Transform 재실행이 제한됩니다.
전체 재변환을 원하시면 역순으로 리셋해야 합니다:
  1. reset_step('test')
  2. reset_step('validate')
  3. reset_step('review')
  4. reset_step('transform')
모든 파이프라인 결과가 삭제됩니다. 계속할까요? (y/n)
```

단건만 재변환할 때는 `transform_single_sql` 사용 — 전체 리셋 불필요.

---

## 7. Response Style (요약)

`prompt.md` §Response Style 전문 참조. 핵심:

- Rich tool 출력은 그대로 두고 **중복 렌더 금지**
- 각 단계 완료 시 템플릿: `{Step} 완료 ({done}/{total}). 다음은 **{NextStep} 단계**입니다. {NextStep}를 실행할까요?`
- 전체 완료 시 위 5.1 보고서 안내 문구 사용

---

## 8. 관련 문서

- [src/AGENT.md](../../src/AGENT.md) — 공용 에이전트 운영 가이드 (SSOT)
- [src/agents/orchestrator/prompt.md](../../src/agents/orchestrator/prompt.md) — 런타임 시스템 프롬프트
- [src/agents/orchestrator/agent.py](../../src/agents/orchestrator/agent.py) — Agent 팩토리, Tool 목록
- [docs/db-schema.md](../db-schema.md) — `transform_target_list` + history 테이블 관계도
