# Pipeline Logging Improvement Plan

> **Summary**: 파이프라인 전 단계에 구조화된 JSON Lines 로그 체계 구축 — SQL별 결과 추적, Agent 동작 가시성 확보, 타이밍/에러 집계
>
> **Project**: Application SQL Transform Agent (OMA sub-module)
> **Author**: Plan
> **Date**: 2026-04-17
> **Status**: Active

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 6개 파이프라인 단계 중 Transform/Validate는 SQL별 로그 없음, Merge/Analyze는 로그 파일 자체 없음. Agent 내부 tool call 불가시. emit_progress 데이터 폐기. 1000+ SQL 변환 시 문제 추적 불가 |
| **Solution** | JSON Lines 기반 구조화 로그 — 단계별 SQL 결과, 타이밍, Agent tool call 추적. 실행 요약 자동 생성. 이전 실행 이력 보존 |
| **Function/UX Effect** | 변환 완료 후 `jq` 한 줄로 실패 SQL 추출, 느린 SQL 식별, 단계별 통계 즉시 확인. 이전 실행과 비교 가능 |
| **Core Value** | 대규모 변환 프로젝트에서 디버깅 시간 80% 단축 — "어디서 실패했는지"를 즉시 파악 |

---

## Context Anchor

| Anchor | Content |
|--------|---------|
| **WHY** | 현재 로그 체계로는 1000+ SQL 변환 시 개별 SQL 실패 원인 추적이 불가능. 로그 부재로 디버깅에 과도한 시간 소요 |
| **WHO** | OMA 운영자 (변환 실행/결과 확인), 개발자 (Agent 동작 디버깅) |
| **RISK** | 로그 과다 생성 시 디스크/성능 부담, Agent tool_use 캡처 시 코드 침습도 증가 |
| **SUCCESS** | 모든 단계에서 SQL별 결과 로그 생성, jq로 실패 SQL 즉시 추출 가능, 실행 시간 통계 확인 가능 |
| **SCOPE** | 6개 파이프라인 단계 (Transform, Review, Validate, Merge, Test, Analyze) 로그 체계. Agent SDK 내부 hook은 제외 |

---

## 1. 현재 상태 분석

### 1.1 단계별 로그 현황

| 단계 | 로그 파일 | SQL별 기록 | DB 기록 | 문제점 |
|------|:---:|:---:|:---:|------|
| **Transform** | `logs/transform/{mapper}.log` | ❌ (그룹만) | flag만 | 개별 SQL 성공/실패 안 남음. notes는 DB에만 |
| **Review** | `logs/review/{mapper}.log` | ✅ | JSON feedback | **유일하게 SQL별 기록** — 벤치마크 |
| **Validate** | `logs/validate/{mapper}.log` | ❌ (그룹만) | flag만 | Review보다 못함 |
| **Merge** | **없음** | N/A | 없음 | 로그 자체 없음 |
| **Test** | `logs/test/` + `test_execution.log` | 에러만 | result+notes | Phase 0/1은 test_execution.log에 |
| **Analyze** | **없음** | N/A | 없음 | 콘솔 스트리밍만 |

### 1.2 공통 문제

1. **Agent 내부 동작 불가시**: 5/6 단계 `callback_handler=None` — tool call 순서/인자 안 보임
2. **emit_progress 데이터 폐기**: SQL별 상태+notes가 진행바 갱신 후 버려짐
3. **로그 로테이션 없음**: 매 실행 시 덮어씀 (이전 결과 유실)
4. **타이밍 없음**: 느린 SQL 식별 불가
5. **구조화 안 됨**: 텍스트 grep만 가능, 프로그래밍 분석 불가

---

## 2. 요구사항

### 2.1 기능 요구사항

| ID | 요구사항 | 우선순위 |
|----|----------|:--------:|
| FR-01 | **JSON Lines 로그 포맷** — 각 이벤트를 독립 JSON 객체로 기록. `jq` 파싱 가능 | High |
| FR-02 | **SQL별 결과 기록** — Transform/Validate에서 개별 SQL 성공/실패/notes 기록 | High |
| FR-03 | **타이밍 기록** — SQL별/그룹별/단계별 실행 시간 (start, end, duration_ms) | High |
| FR-04 | **실행 요약 (run summary)** — 단계 완료 시 총 건수, Pass/Fail/Skip, 소요 시간 JSON 출력 | High |
| FR-05 | **로그 보존** — 실행마다 타임스탬프 디렉토리로 분리 (`logs/{step}/{YYYYMMDD_HHMMSS}/`) | Medium |
| FR-06 | **Agent tool call 추적** — convert_sql, set_reviewed 등 tool 호출 시 로그 이벤트 생성 | Medium |
| FR-07 | **Merge 단계 로그 추가** — mapper별 성공/실패/SQL 수 기록 | Medium |
| FR-08 | **에러 집계 리포트** — 실행 완료 후 에러 카테고리별 카운트 출력 | Low |
| FR-09 | **fix_history ↔ JSON 로그 연결** — `_save_fix_history()`에 step 파라미터 추가 (`v2_review.log` 형식), JSON 로그에 `fix_version` 필드로 상호 참조. SQL별 전체 파이프라인 여정 추적 가능 | High |
| FR-10 | **사용된 파라미터 로그 기록** — Test PASS/FAIL 시 해당 SQL에 적용된 파라미터를 JSON 로그의 `parameters` 필드에 기록. FAIL 원인 분석의 핵심 정보 | High |
| FR-11 | **SQL별 파라미터 프로파일 (sql_parameters.json)** — `_global` fallback + mapper/sqlId별 override 구조. Java executor가 SQL 실행 전 매칭 로드. 기존 `parameters.properties` 호환 유지. **이 Plan은 포맷 정의 + Java 로드만, 생성 로직은 next-gen-test-framework Phase 2** | High |
| FR-12 | **Java executor에 sqlState/errorCode 추가** — `SQLException.getSQLState()`, `getErrorCode()` 캡처하여 JSON 출력에 포함 | Medium |
| FR-13 | **summary.md 자동 생성** — 실행 완료 후 JSON 로그에서 사람이 읽는 리포트 자동 생성. Phase별 Pass/Fail/Skip 통계, FAIL 사유 분류, FAIL 전건 상세 (파라미터+sqlState), 재시도 이력 포함 | High |
| FR-14 | **`current_step` 컬럼 추가** — transform_target_list에 현재 단계 컬럼 추가. 값: `pending→transform→review→validate→merge→test→completed`. 기존 5개 flag 유지 (호환성), current_step은 조회 편의용. Phase 2에서 flag 조합을 current_step으로 점진 교체 | High |

### 2.2 비기능 요구사항

| ID | 요구사항 |
|----|----------|
| NFR-01 | 로그 추가로 인한 실행 시간 증가 < 5% |
| NFR-02 | 로그 파일 크기: 1000 SQL 기준 < 10MB |
| NFR-03 | 기존 동작 변경 없음 (backward compatible) |
| NFR-04 | Thread-safe (병렬 실행 환경) |
| NFR-05 | **mapper_file은 항상 sub_dir 포함 full path 사용** — 동명 mapper 구분 필수 (e.g., `master/UserMapper.xml` vs `batch/UserMapper.xml`). JSON 로그, fix_history 파일명 모두 동일 원칙 적용 |

---

## 3. 아키텍처 원칙

### 3.0 2-Tier 저장 구조

```
Tier 1: DB (transform_target_list)
  → 현재 상태 + 파이프라인 흐름 제어 (WHERE current_step = 'test')
  → 최종 flag + 최신 결과만 보관 (덮어쓰기)
  → 변경: current_step 컬럼 추가

Tier 2: JSON Lines 로그 (events.jsonl)
  → 전체 이력 (모든 단계, 모든 시도, 비정형)
  → 디버깅/분석용 (jq 파싱)
  → 신규 구현

보조: fix_history/ (기존)
  → SQL before/after diff (코드 변경 추적)
  → 보강: 파일명에 step 포함 + fix_version으로 JSON 로그 연결

※ 기존 히스토리 테이블 4개 (TransformHistory, ReviewHistory 등)은 미사용 — 방치
```

**동기화 원칙**: DB가 truth (파이프라인 제어용). JSON 로그는 보충 (이력 추적용). 충돌 시 DB 우선.

---

## 4. 설계 방향

### 4.1 JSON Lines 로그 포맷

```jsonl
{"ts":"2026-04-17T14:30:01","step":"transform","event":"sql_complete","mapper":"master/UserMapper.xml","sql_id":"selectUser","status":"success","duration_ms":2340,"notes":"NVL→COALESCE, (+)→LEFT JOIN"}
{"ts":"2026-04-17T14:30:03","step":"transform","event":"sql_complete","mapper":"master/UserMapper.xml","sql_id":"insertUser","status":"fail","duration_ms":1200,"error":"context overflow"}
{"ts":"2026-04-17T15:00:01","step":"review","event":"sql_complete","mapper":"master/UserMapper.xml","sql_id":"selectUser","status":"fail","reason":"OR IS NULL missing on LEFT JOIN column"}
{"ts":"2026-04-17T15:10:02","step":"review","event":"re_transform","mapper":"master/UserMapper.xml","sql_id":"selectUser","fix_version":"v2_review","notes":"OR IS NULL 추가"}
{"ts":"2026-04-17T16:00:01","step":"test","event":"sql_complete","mapper":"master/UserMapper.xml","sql_id":"selectUser","phase":1,"status":"fail","fail_category":"parameter","parameters":{"userId":"1","status":"Y"},"parameter_source":"global","sql_state":"42883","error_code":0,"error":"operator does not exist: character varying = integer"}
{"ts":"2026-04-17T16:10:03","step":"test","event":"agent_fix","mapper":"master/UserMapper.xml","sql_id":"selectUser","fix_version":"v3_test","notes":"::integer cast 추가"}
{"ts":"2026-04-17T16:35:00","step":"test","event":"run_summary","total":42,"pass":38,"fail":3,"skip":1,"duration_ms":300000}
```

**출력 구조:**
```
output/logs/test/20260417_143000/
  ├── events.jsonl       ← 원본 (전체 이벤트, jq 분석용)
  └── summary.md         ← 자동 생성 (사람이 읽는 리포트)
        ├── Phase별 Pass/Fail/Skip 통계
        ├── FAIL 사유 분류 (parameter/sql_syntax/schema/infra)
        ├── FAIL 전건 상세 (mapper, sql_id, 파라미터, sqlState, 에러)
        └── 재시도 이력 (fix_version 연결)
```

**SQL별 여정 추적:**
```bash
# selectUser의 전체 파이프라인 여정
jq 'select(.sql_id=="selectUser")' output/logs/*/*.jsonl

# 대응하는 fix_history 파일
ls output/logs/fix_history/UserMapper_selectUser_v*
  v1_transform.log   ← 최초 변환 (before/after diff)
  v2_review.log      ← Review FAIL → 재변환
  v3_test.log        ← Test FAIL → Agent fix

# summary.md → 한눈에 전체 현황 (jq 필요 없음)
cat output/logs/test/20260417_143000/summary.md
```

### 4.2 공통 로거 모듈

```python
# src/core/pipeline_logger.py (신규)
class PipelineLogger:
    """Thread-safe JSON Lines logger for pipeline steps."""
    
    def __init__(self, step: str, run_id: str = None):
        # logs/{step}/{YYYYMMDD_HHMMSS}.jsonl
        
    def log_event(self, event: str, **kwargs):
        # Thread-safe JSON append
        
    def log_sql_result(self, mapper, sql_id, status, duration_ms, **kwargs):
        # Convenience: event="sql_complete"
        
    def log_summary(self, total, success, fail, skip, duration_ms):
        # event="run_summary"
```

### 4.3 단계별 통합 계획

| 단계 | 통합 방식 | 코드 변경 |
|------|----------|----------|
| **Transform** | 그룹 완료 후 DB 조회 → SQL별 결과 로깅 | `run_sql_transform.py` |
| **Review** | 기존 SQL별 로그 → JSON Lines로 전환 | `run_sql_review.py` |
| **Validate** | Review와 동일 패턴 적용 | `run_sql_validate.py` |
| **Merge** | assemble_mapper 결과 로깅 추가 | `run_sql_merge.py` |
| **Test** | test_execution.log → JSON Lines 전환 | `run_sql_test.py` |
| **Analyze** | 분석 결과 로깅 추가 | `run_source_analyzer.py` |

### 4.4 DB current_step 컬럼 (FR-14)

```
Phase 1: 기존 flag 유지 + current_step 추가 (읽기 전용 뷰)
Phase 2: flag 조합 → current_step 전환 (20곳+ 점진 교체)
```

```python
# models.py — 컬럼 추가
current_step = Column(Text, default='pending', server_default='pending')
# 값: pending → transform → review → validate → merge → test → completed

# 각 tool에서 갱신
convert_sql()      → current_step = 'review'     (다음: review 대기)
set_reviewed('Y')  → current_step = 'validate'
set_reviewed('F')  → current_step = 'transform'  (재변환 필요)
set_validated()    → current_step = 'merge'
assemble_mapper()  → current_step = 'test'
_update_tested()   → current_step = 'completed' or 'test' (FAIL 시)
```

```sql
-- Phase 1: 기존 방식 + current_step 병행
SELECT * FROM transform_target_list WHERE current_step = 'test'
-- 동일: WHERE transformed='Y' AND reviewed='Y' AND validated='Y' AND tested='N'

-- Phase 2: current_step으로 통합
SELECT * FROM transform_target_list WHERE current_step = 'validate'
```

### 4.5 convert_sql step 주입 (FR-09)

`convert_sql`은 `@tool` 데코레이터라 Agent가 호출 — 파라미터 추가하면 불안정. 대신 **모듈 레벨 컨텍스트 변수**로 step 주입:

```python
# convert_sql.py
_current_step = "transform"

def set_step(step: str):
    global _current_step
    _current_step = step

@tool
def convert_sql(sql_id, converted_sql, mapper_file, notes=""):
    # Agent는 기존 인터페이스 그대로 호출
    _save_fix_history(..., step=_current_step)   # step 자동 포함
    logger.log_event("sql_convert", step=_current_step, ...)  # JSON 로그
```

각 runner가 Agent 생성 전에 호출:
```python
# run_sql_review.py
from agents.sql_transform.tools.convert_sql import set_step
set_step("review")    # → fix_history: v2_review.log

# run_sql_test.py
set_step("test")      # → fix_history: v3_test.log
```

- Agent tool 인터페이스 변경 없음 (호환성 유지)
- Thread-safe: 각 runner가 순차 실행이므로 race condition 없음
- 병렬 실행 시 worker별 step은 동일 (transform runner 내 thread는 전부 "transform")

### 4.6 Agent Tool Call 추적 (FR-06, Phase 3 연기)

Strands SDK의 callback 인터페이스에서 tool_use event를 분리 캡처하는 경량 핸들러. SDK 호환성 확인 필요 — Phase 3으로 연기.

---

## 5. 구현 범위 (3 Phase)

### Phase 1: 핵심 인프라 + Test (Highest Priority)

Test가 가장 시급 — Phase 0(EXPLAIN) + Phase 1(Java bulk) + Phase 2(Agent fix) 3단계를 거치는데,
어떤 SQL이 왜 FAIL인지 추적 불가. `test_execution.log`는 첫 5건만 표시하고 나머지 생략.
FAIL 사유 분류(parameter/SQL변환/스키마)도 로그에 없음.

| 항목 | 파일 | 설명 |
|------|------|------|
| 공통 로거 | `src/core/pipeline_logger.py` (신규) | PipelineLogger 클래스 (Thread-safe JSON Lines) |
| Test Phase 0 로그 | `src/run_sql_test.py` | DML EXPLAIN SQL별 PASS/FAIL JSON 로그 |
| Test Phase 1 로그 | `src/run_sql_test.py` | Java bulk test SQL별 결과 (**전건** — 첫 5건 제한 해제) |
| Test Phase 2 로그 | `src/run_sql_test.py` | Agent fix SQL별 시도/성공/실패 로그 |
| FAIL 사유 분류 | `src/run_sql_test.py` | parameter / sql_syntax / schema / infra 4카테고리 |
| summary.md 자동 생성 | `src/core/pipeline_logger.py` | JSON 로그에서 사람용 리포트 자동 생성 |
| Java sqlState 추가 | `MyBatisBulkExecutorWithJson.java` | `getSQLState()`, `getErrorCode()` 캡처 |
| fix_history step 연결 | `src/agents/sql_transform/tools/convert_sql.py` | `set_step()` 모듈 변수 + 파일명 `v2_review.log` + JSON `fix_version` |
| `current_step` 컬럼 추가 | `src/core/models.py` | 컬럼 정의 + auto-migration. **갱신은 Test tool만** (Phase 1 범위 제한) |

**Phase 1에서 의도적으로 빠진 것:**
- FR-10 파라미터 로깅: Python에서 `parameters.properties` 읽어서 JSON 로그에 첨부 (Java 수정 불필요)
- FR-11 sql_parameters.json: next-gen-test-framework Phase 2에서 구현. 이 Plan은 포맷 정의 + 로딩 구조만
- current_step 갱신 (Test 외 5개 tool): Phase 2에서 통합

### Phase 2: 나머지 단계 + current_step 전면 적용

| 항목 | 파일 | 설명 |
|------|------|------|
| Transform 통합 | `src/run_sql_transform.py` | 그룹 완료 후 DB 조회 → SQL별 JSON 로그 |
| Merge 로그 추가 | `src/run_sql_merge.py` | mapper별 결과 JSON 로그 |
| Review 전환 | `src/run_sql_review.py` | 텍스트 → JSON Lines 전환 |
| Validate 보강 | `src/run_sql_validate.py` | SQL별 결과 추가 |
| **flag → current_step 전환** | 20곳+ WHERE 조건 | `WHERE transformed='Y' AND reviewed='N'` → `WHERE current_step='validate'` 점진 교체. Phase 1 안정화 후 진행 |

### Phase 3: 고급 기능

| 항목 | 설명 |
|------|------|
| Analyze 로그 추가 | 분석 결과 로깅 |
| Agent tool call 추적 | ToolCallLogger 핸들러 (SDK 호환 확인 후) |
| 에러 집계 리포트 | 실행 완료 후 카테고리별 통계 |
| 로그 뷰어 CLI | `python run_log_viewer.py --step test --status fail` |

---

## 6. 성공 기준

| 항목 | 현재 | Phase 1 목표 | Phase 2 목표 |
|------|:----:|:----:|:----:|
| SQL별 로그 (Test) | 에러만 | ✅ 전체 (Phase 0/1/2) | ✅ |
| SQL별 로그 (Transform) | ❌ | ❌ | ✅ |
| SQL별 로그 (모든 단계) | 1/6 | 2/6 (Test+Review) | 6/6 |
| FAIL 사유 분류 | ❌ | ✅ (4 카테고리) | ✅ |
| JSON 구조화 | ❌ | ✅ | ✅ |
| jq로 실패 SQL 추출 | ❌ | ✅ | ✅ |
| 타이밍 기록 | ❌ | ✅ | ✅ |
| 실행 이력 보존 | ❌ | ✅ | ✅ |
| 실행 요약 자동 생성 | ❌ | ✅ | ✅ |

**검증 명령어:**
```bash
# Phase 1 완료 확인 — Test 로그
jq 'select(.status=="fail")' output/logs/test/20260417_143000.jsonl
jq 'select(.event=="run_summary")' output/logs/test/20260417_143000.jsonl
jq 'select(.fail_category=="parameter")' output/logs/test/20260417_143000.jsonl
```

---

## 7. 리스크

| 리스크 | 영향 | 대응 |
|--------|------|------|
| 병렬 실행 시 JSON 깨짐 | 로그 파서 에러 | Thread lock per file + flush |
| 로그 파일 누적 | 디스크 부족 | 30일 이상 자동 정리 (optional) |
| DB 조회 부하 (Transform) | 그룹 완료 후 N건 SELECT | Batch query, 기존 timeout 내 |
| Strands SDK callback 제약 | FR-06 구현 불가 | Phase 3으로 연기, 대안 검토 |
| current_step ↔ flag 불일치 | 조회 결과 혼란 | DB가 truth. Phase 1에서는 current_step은 보조 뷰. Phase 2 전환 시 flag deprecated 후 제거 |
| FR-10 파라미터 로깅 소스 | Java가 SQL별 사용 파라미터 미리턴 | Python에서 `parameters.properties` 읽어서 JSON 로그에 첨부 (Phase 1). sql_parameters.json 도입 후 SQL별 매칭 (Phase 2) |

---

## 8. 연관 Plan

### next-gen-test-framework Phase 2 와의 관계

| 항목 | pipeline-logging (이 Plan) | next-gen-test-framework Phase 2 |
|------|---------------------------|--------------------------------|
| **역할** | 구조 (JSON 포맷 + Java 로드 + 로그 기록) | 내용 (Smart Parameter Generator가 프로파일 자동 생성) |
| **산출물** | `sql_parameters.json` 포맷 정의 + Java 로드 구현 | `generate_parameters.py` 확장 → 프로파일 자동 생성 |
| **선후관계** | **이것 먼저** (로드 구조) → Phase 2 (생성 로직) |

### sql_parameters.json 구조

```json
{
  "_global": {
    "userId": "1",
    "status": "Y",
    "startDate": "20250101"
  },
  "master/UserMapper.xml": {
    "selectUser": {
      "userId": "admin",
      "status": "Y"
    },
    "selectOrder": {
      "userId": "1",
      "orderId": "100"
    }
  }
}
```

**조회 로직**: `mapper+sqlId` 매칭 → 없으면 `_global` fallback → 둘 다 없으면 빈값
**parameter_source 필드**: `"global"` | `"sql_profile"` | `"choose_branch"` (Phase 2에서 확장)

---

## 9. Next Steps

1. [ ] Phase 1 Design 문서 작성 (`/pdca design pipeline-logging`)
2. [ ] `PipelineLogger` 클래스 구현
3. [ ] Test runner 통합 (Phase 0/1/2 전체)
4. [ ] FAIL 사유 분류 로직 구현
5. [ ] example/ 프로젝트로 검증 (42 SQL)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-04-17 | Initial plan — 6단계 로그 분석, JSON Lines 설계 | Plan |
