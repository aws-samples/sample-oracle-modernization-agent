# Pipeline Logging & Dashboard Design Document

> **Feature**: pipeline-logging
> **Architecture**: Option C — Pragmatic Balance
> **Author**: Design
> **Date**: 2026-04-18
> **Status**: Active

---

## Context Anchor

| Anchor | Content |
|--------|---------|
| **WHY** | CLI 수동 운영 한계 — 1000+ SQL 변환 시 실패 추적 불가, 비개발자 접근 불가, 실행 제어가 명령어 의존 |
| **WHO** | OMA 운영자, 프로젝트 매니저, 개발자 |
| **RISK** | 기술 스택 복잡도 증가 (Python + Next.js), SQLite 동시 접근, 로그 데이터 크기 |
| **SUCCESS** | 웹 대시보드에서 SQL별 여정 추적 + FAIL 분석 + 파이프라인 제어 + 실행 트렌드 확인 |
| **SCOPE** | 4 Phase: 로그 인프라 → 전 단계 통합 → 대시보드 → 고급 기능 |

---

## 1. Overview

### 1.1 System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        사용자 접점                                │
│   CLI (기존)              Web Dashboard (Phase 3)                │
│   run_*.py 직접 실행       Next.js 15 App Router                 │
└────────┬──────────────────────────┬─────────────────────────────┘
         │                          │
         ▼                          ▼
┌─────────────────┐    ┌──────────────────────┐
│ Pipeline Runner  │    │   Next.js API Routes  │
│ (Python, ~100줄) │    │   /api/pipeline/*     │
│  pipeline.md 파싱 │    │   /api/sql/*          │
│  oma-config.yaml │    │   /api/config         │
└────────┬─────────┘    └──────────┬───────────┘
         │                          │
         ▼                          ▼ (read-only)
┌─────────────────────────────────────────────────────────────────┐
│                      데이터 계층                                  │
│                                                                  │
│  Tier 1: SQLite DB (transform_target_list)                       │
│    → 현재 상태 + 파이프라인 흐름 제어 (truth)                      │
│    → current_step 컬럼 추가                                      │
│                                                                  │
│  Tier 2: JSON Lines 로그 (events.jsonl)                          │
│    → 전체 이력, 비정형, jq 파싱                                    │
│    → output/logs/{step}/{YYYYMMDD_HHMMSS}/events.jsonl           │
│                                                                  │
│  보조: fix_history/ (before/after diff)                           │
│    → output/logs/fix_history/{mapper}_{sqlId}_v{N}_{step}.log    │
│                                                                  │
│  설정: oma-config.yaml                                           │
│    → env var > yaml > DB properties 우선순위                      │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 Module Map

| Module | Phase | 설명 | 주요 파일 |
|--------|:-----:|------|----------|
| **M1-logger** | 1 | PipelineLogger 클래스 | `src/core/pipeline_logger.py` (신규) |
| **M2-test-log** | 1 | Test runner JSON 로그 통합 | `src/run_sql_test.py`, `src/agents/sql_test/tools/test_tools.py` |
| **M3-db-step** | 1 | current_step 컬럼 + 갱신 | `src/core/models.py`, 각 tool |
| **M4-fix-link** | 1 | fix_history step 연결 | `src/agents/sql_transform/tools/convert_sql.py` |
| **M5-java** | 1 | Java sqlState/errorCode | `MyBatisBulkExecutorWithJson.java` |
| **M6-other-logs** | 2 | 나머지 5단계 JSON 로그 | `run_sql_transform.py`, `run_sql_review.py`, `run_sql_validate.py`, `run_sql_merge.py` |
| **M7-step-migrate** | 2 | flag → current_step 전환 | 20곳+ WHERE 조건 |
| **M8-dashboard** | 3 | Next.js 대시보드 + API | `dashboard/` (신규 프로젝트) |
| **M9-orchestrator** | 3 | MD 기반 Pipeline Runner | `src/run_pipeline.py` (신규), `pipeline.md` |
| **M10-config** | 3 | 통합 config | `oma-config.yaml`, `src/core/config.py` (신규) |

---

## 2. M1-logger: PipelineLogger

### 2.1 클래스 설계

```python
# src/core/pipeline_logger.py

import json
import time
import threading
from pathlib import Path
from utils.project_paths import LOGS_DIR

class PipelineLogger:
    """Thread-safe JSON Lines logger for pipeline steps."""

    def __init__(self, step: str):
        self._step = step
        self._lock = threading.Lock()
        # output/logs/{step}/{YYYYMMDD_HHMMSS}/
        self._run_dir = LOGS_DIR / step / time.strftime('%Y%m%d_%H%M%S')
        self._run_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = self._run_dir / 'events.jsonl'
        # run_start 이벤트
        self.log_event('run_start')

    def log_event(self, event: str, **kwargs) -> None:
        """Thread-safe JSON event append."""
        entry = {
            'ts': time.strftime('%Y-%m-%dT%H:%M:%S'),
            'step': self._step,
            'event': event,
            **kwargs
        }
        line = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            with open(self._log_path, 'a', encoding='utf-8') as f:
                f.write(line + '\n')

    def log_sql_result(self, mapper: str, sql_id: str, status: str,
                       duration_ms: int = 0, **kwargs) -> None:
        """SQL별 결과 기록."""
        self.log_event('sql_complete',
                       mapper=mapper, sql_id=sql_id, status=status,
                       duration_ms=duration_ms, **kwargs)

    def log_summary(self, **kwargs) -> None:
        """실행 완료 요약."""
        self.log_event('run_summary', **kwargs)

    def generate_summary_md(self) -> Path:
        """events.jsonl → summary.md 자동 생성."""
        events = []
        with open(self._log_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    events.append(json.loads(line))

        summary_path = self._run_dir / 'summary.md'
        # Phase별 통계, FAIL 전건, 사유 분류, 재시도 이력
        md = _build_summary_md(events, self._step)
        summary_path.write_text(md, encoding='utf-8')
        return summary_path

    @property
    def run_dir(self) -> Path:
        return self._run_dir

    @property
    def log_path(self) -> Path:
        return self._log_path


def _build_summary_md(events: list, step: str) -> str:
    """events에서 summary.md markdown 생성."""
    sql_events = [e for e in events if e.get('event') == 'sql_complete']
    summary = [e for e in events if e.get('event') == 'run_summary']

    # 통계
    total = len(sql_events)
    passed = sum(1 for e in sql_events if e.get('status') == 'success')
    failed = sum(1 for e in sql_events if e.get('status') == 'fail')
    skipped = sum(1 for e in sql_events if e.get('status') == 'skip')

    # FAIL 사유 분류
    fail_categories = {}
    for e in sql_events:
        if e.get('status') == 'fail':
            cat = e.get('fail_category', 'unknown')
            fail_categories.setdefault(cat, []).append(e)

    md = f"# {step.title()} Run Summary\n\n"
    md += f"**Run**: {events[0].get('ts', '')} | **Total**: {total} | "
    md += f"**Pass**: {passed} | **Fail**: {failed} | **Skip**: {skipped}\n\n"

    if summary:
        s = summary[-1]
        dur = s.get('duration_ms', 0)
        md += f"**Duration**: {dur // 1000}s\n\n"

    # FAIL 사유 분류 테이블
    if fail_categories:
        md += "## FAIL by Category\n\n"
        md += "| Category | Count | Representative Error |\n"
        md += "|----------|:-----:|---------------------|\n"
        for cat, items in sorted(fail_categories.items(), key=lambda x: -len(x[1])):
            rep = items[0].get('error', '')[:80]
            md += f"| {cat} | {len(items)} | {rep} |\n"
        md += "\n"

    # FAIL 전건 상세
    fail_events = [e for e in sql_events if e.get('status') == 'fail']
    if fail_events:
        md += "## FAIL Details\n\n"
        md += "| Mapper | SQL ID | Category | sqlState | Parameters | Error |\n"
        md += "|--------|--------|----------|:--------:|------------|-------|\n"
        for e in fail_events:
            mapper = e.get('mapper', '')
            sql_id = e.get('sql_id', '')
            cat = e.get('fail_category', '')
            sql_state = e.get('sql_state', '')
            params = json.dumps(e.get('parameters', {}), ensure_ascii=False)[:50]
            error = e.get('error', '')[:60]
            md += f"| {mapper} | {sql_id} | {cat} | {sql_state} | {params} | {error} |\n"
        md += "\n"

    # 재시도 이력
    fix_events = [e for e in events if e.get('event') in ('agent_fix', 're_transform')]
    if fix_events:
        md += "## Fix History\n\n"
        md += "| SQL ID | fix_version | Notes |\n"
        md += "|--------|-------------|-------|\n"
        for e in fix_events:
            md += f"| {e.get('sql_id','')} | {e.get('fix_version','')} | {e.get('notes','')} |\n"

    return md
```

### 2.2 사용 패턴

```python
# 각 runner에서
from core.pipeline_logger import PipelineLogger

logger = PipelineLogger(step='test')

# SQL별 결과
logger.log_sql_result('master/UserMapper.xml', 'selectUser', 'fail',
                      duration_ms=1200, fail_category='parameter',
                      sql_state='42883', error='operator does not exist...',
                      parameters={'userId': '1'}, parameter_source='global')

# 요약
logger.log_summary(total=42, pass_=38, fail=3, skip=1, duration_ms=300000)

# summary.md 생성
logger.generate_summary_md()
```

---

## 3. M2-test-log: Test Runner 통합

### 3.1 수정 파일: `src/run_sql_test.py`

**변경 지점:**

```python
# line 131: run() 함수 시작부에 logger 생성
def run(max_workers=8, auto_fix=False):
    logger = PipelineLogger(step='test')
    ...

# Phase 0 (line 208-240): explain_dml_batch 결과를 SQL별 로깅
for item in explain_result.get('failures', []):
    logger.log_sql_result(item['mapper_file'], item['sql_id'], 'fail',
                          phase=0, fail_category='sql_syntax', error=item.get('error',''))
for item in dml_items:  # PASS 항목도 기록
    if item not in failures:
        logger.log_sql_result(item['mapper_file'], item['sql_id'], 'success', phase=0)

# Phase 1 (line 244-309): run_bulk_test 결과를 전건 로깅
# 현재: 첫 5건만 표시 → 변경: 전건 JSON 로그
for item in all_items:  # test_tools.py에서 리턴된 전체 결과
    logger.log_sql_result(
        item['xmlFile'], item['sqlId'],
        'success' if item['success'] else 'fail',
        phase=1,
        fail_category=_classify_error(item.get('error', '')) if not item['success'] else None,
        sql_state=item.get('sqlState'),
        error_code=item.get('errorCode'),
        error=item.get('error', ''),
        parameters=_load_parameters_for_sql(item['xmlFile'], item['sqlId']),
        parameter_source='global',  # Phase 2에서 sql_profile로 확장
    )

# Phase 2 (line 352-427): Agent fix 결과 로깅
# fix_mapper_failures 완료 후 DB 조회하여 결과 기록

# 실행 완료 시
logger.log_summary(total=total, pass_=passed, fail=failed, skip=skipped,
                   duration_ms=int((time.time() - start_time) * 1000),
                   by_phase={'phase0': {...}, 'phase1': {...}})
logger.generate_summary_md()
```

### 3.2 FAIL 사유 분류 함수

```python
# src/run_sql_test.py (또는 core/pipeline_logger.py)

def _classify_error(error_msg: str) -> str:
    """에러 메시지에서 FAIL 카테고리 분류."""
    if not error_msg:
        return 'unknown'
    e = error_msg.lower()

    # parameter 오류
    if any(p in e for p in ['invalid input syntax', 'operator does not exist',
                             'type mismatch', 'cannot cast']):
        return 'parameter'

    # SQL 변환 오류
    if any(p in e for p in ['syntax error', 'unexpected token', 'near "',
                             'missing keyword']):
        return 'sql_syntax'

    # 스키마 오류
    if any(p in e for p in ['relation "', 'does not exist', 'column "',
                             'table "', 'unknown column']):
        return 'schema'

    # 인프라 오류
    if any(p in e for p in ['classnotfound', 'connection refused', 'timeout',
                             'could not connect', 'java.lang.']):
        return 'infra'

    return 'other'
```

### 3.3 파라미터 로딩 함수

```python
def _load_parameters_for_sql(mapper_file: str, sql_id: str) -> dict:
    """SQL에 적용된 파라미터를 로드. sql_parameters.json > parameters.properties fallback."""
    # Phase 1: parameters.properties (글로벌) — 전체 파라미터 반환
    props_path = _find_parameters_properties()
    if props_path and props_path.exists():
        params = {}
        for line in props_path.read_text().splitlines():
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                params[k.strip()] = v.strip()
        return params
    return {}
```

### 3.4 수정 파일: `src/agents/sql_test/tools/test_tools.py`

**`_update_tested()` (line 647)에 JSON 로그 이벤트 추가:**

기존 `emit_progress()` 호출 라인 (664) 옆에 logger 이벤트 추가. 단, `_update_tested`는 여러 곳에서 호출되므로, logger를 모듈 변수로 주입:

```python
# test_tools.py 상단
_logger = None

def set_logger(logger):
    global _logger
    _logger = logger
```

`run_sql_test.py`에서 `set_logger(logger)` 호출 후 test 실행.

---

## 4. M3-db-step: current_step 컬럼

### 4.1 모델 변경

```python
# src/core/models.py — TransformTargetList 클래스
# line 36 (completed) 다음에 추가:
current_step = Column(Text, default='pending', server_default='pending')
```

### 4.2 Auto Migration

SQLite는 `ALTER TABLE ADD COLUMN`만 지원. `run_setup.py` 또는 각 runner 시작 시:

```python
# src/core/db_migrate.py (신규, ~30줄)
def ensure_current_step_column():
    """current_step 컬럼이 없으면 추가 + 기존 데이터 backfill."""
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(transform_target_list)")
        columns = {row[1] for row in cursor.fetchall()}
        if 'current_step' not in columns:
            cursor.execute("ALTER TABLE transform_target_list ADD COLUMN current_step TEXT DEFAULT 'pending'")
            # Backfill: 기존 flag 기반으로 current_step 계산
            cursor.execute("UPDATE transform_target_list SET current_step = 'completed' WHERE tested='Y' AND test_result='PASS'")
            cursor.execute("UPDATE transform_target_list SET current_step = 'test' WHERE validated='Y' AND tested='N'")
            cursor.execute("UPDATE transform_target_list SET current_step = 'test' WHERE tested='Y' AND test_result IN ('FAIL','SKIP')")
            cursor.execute("UPDATE transform_target_list SET current_step = 'merge' WHERE validated='Y' AND tested='N'")
            cursor.execute("UPDATE transform_target_list SET current_step = 'validate' WHERE reviewed='Y' AND validated='N'")
            cursor.execute("UPDATE transform_target_list SET current_step = 'review' WHERE transformed='Y' AND reviewed='N'")
            cursor.execute("UPDATE transform_target_list SET current_step = 'transform' WHERE transformed='N'")
            conn.commit()
```

### 4.3 갱신 시점 (Phase 1: Test tool만)

```python
# test_tools.py의 _update_tested() 확장
def _update_tested(mapper_file, sql_id, result="PASS", error=""):
    ...
    # 기존: tested='Y', test_result, test_notes
    # 추가:
    next_step = 'completed' if result == 'PASS' else 'test'
    update_by_mapper(..., current_step=next_step)
```

Phase 2에서 나머지 tool (convert_sql, set_reviewed, set_validated, assemble_mapper)에 갱신 추가.

---

## 5. M4-fix-link: fix_history step 연결

### 5.1 convert_sql.py 변경

```python
# 모듈 변수
_current_step = "transform"

def set_step(step: str):
    """Runner가 Agent 생성 전에 호출."""
    global _current_step
    _current_step = step

def _save_fix_history(mapper_file, sql_id, target_path, new_sql, notes):
    ...
    # 파일명에 step 포함
    log_path = fix_dir / f"{stem}_v{ver}_{_current_step}.log"

    # 헤더에 step 포함
    content = (
        f"=== FIX v{ver} [{_current_step}] | {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
        f"Notes: {notes}\n\n"
    )
    ...
```

### 5.2 Runner 연동

```python
# run_sql_review.py
from agents.sql_transform.tools.convert_sql import set_step
set_step("review")

# run_sql_validate.py
set_step("validate")

# run_sql_test.py
set_step("test")
```

### 5.3 JSON 로그 연결

`convert_sql()` 내에서 fix_history 저장 후 JSON 로그에도 기록:

```python
@tool
def convert_sql(sql_id, converted_sql, mapper_file, notes=""):
    ...
    if target_path.exists():
        _save_fix_history(mapper_file, sql_id, target_path, converted_sql, notes)
        fix_version = f"v{ver}_{_current_step}"
        # JSON 로그 (logger가 설정된 경우)
        if _logger:
            _logger.log_event('sql_convert', mapper=mapper_file, sql_id=sql_id,
                              fix_version=fix_version, step=_current_step, notes=notes)
```

---

## 6. M5-java: Java executor 변경

### 6.1 `MyBatisBulkExecutorWithJson.java`

**TestResult 클래스 확장 (line ~1830):**
```java
private static class TestResult {
    SqlTestInfo testInfo;
    boolean success;
    int rowCount;
    String errorMessage;
    String sqlState;      // 추가
    int errorCode;        // 추가
    List<Map<String, Object>> resultData;
}
```

**catch 블록 변경 (line ~857-859):**
```java
} catch (Exception sqlException) {
    result.success = false;
    result.errorMessage = sqlException.getMessage();
    if (sqlException instanceof java.sql.SQLException) {
        java.sql.SQLException se = (java.sql.SQLException) sqlException;
        result.sqlState = se.getSQLState();
        result.errorCode = se.getErrorCode();
    }
    ...
}
```

**JSON 출력 확장 (line ~440-445):**
```java
testNode.put("errorMessage", result.errorMessage != null ? result.errorMessage : "");
testNode.put("sqlState", result.sqlState != null ? result.sqlState : "");
testNode.put("errorCode", result.errorCode);
```

---

## 7. M6-other-logs: 나머지 단계 로그 (Phase 2)

### 7.1 Transform (run_sql_transform.py)

그룹 완료 후 DB 조회하여 SQL별 결과 로깅:

```python
# transform_mapper() 함수 내, 그룹 실행 후
with sqlite3.connect(str(DB_PATH)) as conn:
    for s in group:
        cursor.execute("SELECT transformed, updated_at FROM transform_target_list WHERE mapper_file=? AND sql_id=?",
                        (mapper_file, s['sql_id']))
        row = cursor.fetchone()
        logger.log_sql_result(mapper_file, s['sql_id'],
                              'success' if row and row[0]=='Y' else 'fail',
                              duration_ms=group_duration // len(group))
```

### 7.2 Review (run_sql_review.py)

기존 `log()` 텍스트 로그를 JSON으로 전환. per-SQL PASS/FAIL/WARN 이미 있으므로 포맷만 변경.

### 7.3 Validate (run_sql_validate.py)

Review와 동일 패턴. per-SQL 결과 추가.

### 7.4 Merge (run_sql_merge.py)

mapper별 결과만 (SQL 단위 아님):
```python
logger.log_event('mapper_merged', mapper=mapper_file,
                 total=result['total'], success=result['success'])
```

---

## 8. M8-dashboard: Next.js 대시보드 (Phase 3)

### 8.1 기술 스택

| 항목 | 선택 |
|------|------|
| Framework | Next.js 15 (App Router) |
| UI | Tailwind CSS + shadcn/ui |
| Charts | Recharts |
| SQLite | better-sqlite3 (read-only) |
| JSON Lines 파서 | readline + JSON.parse (스트리밍) |
| Diff 뷰어 | react-diff-viewer-continued |
| 상태 관리 | React Server Components + SWR (client polling) |

### 8.2 디렉토리 구조

```
dashboard/
  ├── app/
  │   ├── layout.tsx              ← 사이드바 네비게이션
  │   ├── page.tsx                ← Overview
  │   ├── sql/
  │   │   ├── page.tsx            ← SQL Explorer (테이블, 필터, 검색)
  │   │   └── [mapper]/[sqlId]/
  │   │       └── page.tsx        ← SQL Detail (여정 타임라인, diff)
  │   ├── analysis/page.tsx       ← FAIL Analysis (차트, 일괄 SKIP)
  │   ├── runs/page.tsx           ← Run History (트렌드 차트)
  │   ├── control/page.tsx        ← Pipeline Control (실행 버튼, 상태)
  │   ├── settings/page.tsx       ← Config 편집
  │   └── api/
  │       ├── pipeline/
  │       │   ├── status/route.ts
  │       │   └── run/[step]/route.ts
  │       ├── sql/
  │       │   ├── route.ts               ← 목록 + 필터
  │       │   ├── [mapper]/[sqlId]/route.ts ← 상세 + 여정
  │       │   ├── skip/route.ts
  │       │   └── skip-category/route.ts
  │       ├── runs/
  │       │   ├── route.ts
  │       │   └── [runId]/summary/route.ts
  │       ├── stats/trend/route.ts
  │       └── config/route.ts
  ├── components/
  │   ├── ui/                     ← shadcn/ui 컴포넌트
  │   ├── pipeline-progress.tsx   ← 단계별 진행 바
  │   ├── sql-table.tsx           ← SQL 목록 데이터 테이블
  │   ├── journey-timeline.tsx    ← SQL 여정 타임라인
  │   ├── fail-category-chart.tsx ← 사유별 도넛 차트
  │   ├── trend-chart.tsx         ← Pass Rate 트렌드
  │   ├── diff-viewer.tsx         ← fix_history diff
  │   └── config-editor.tsx       ← YAML 편집기
  ├── lib/
  │   ├── db.ts                   ← better-sqlite3 연결 (WAL, read-only)
  │   ├── log-parser.ts           ← JSON Lines 스트리밍 파서
  │   ├── pipeline-runner.ts      ← Python subprocess 실행
  │   └── config.ts               ← oma-config.yaml 파서
  ├── package.json
  ├── tailwind.config.ts
  └── tsconfig.json
```

### 8.3 핵심 API 상세

**GET /api/pipeline/status**
```typescript
// DB에서 current_step별 카운트
const rows = db.prepare(`
  SELECT current_step, COUNT(*) as count,
    SUM(CASE WHEN test_result='PASS' THEN 1 ELSE 0 END) as passed,
    SUM(CASE WHEN test_result='FAIL' THEN 1 ELSE 0 END) as failed
  FROM transform_target_list
  GROUP BY current_step
`).all();

return { steps: rows, total: sum, passRate: ... }
```

**GET /api/sql/[mapper]/[sqlId]**
```typescript
// 1. DB에서 현재 상태
const sql = db.prepare('SELECT * FROM transform_target_list WHERE mapper_file=? AND sql_id=?').get(mapper, sqlId);

// 2. JSON 로그에서 여정 (전 단계 events.jsonl 스캔)
const journey = parseJourneyFromLogs(mapper, sqlId);

// 3. fix_history 파일 목록
const fixes = glob(`fix_history/${mapperStem}_${sqlId}_v*`);

return { current: sql, journey, fixes }
```

**POST /api/pipeline/run/[step]**
```typescript
// Python runner subprocess 실행
const proc = spawn('python3', ['run_pipeline.py', '--step', step], {
  cwd: srcDir,
  env: { ...process.env, PYTHONPATH: srcDir }
});
// SSE로 stdout 스트리밍 가능 (Phase 4)
return { status: 'started', pid: proc.pid }
```

### 8.4 핵심 컴포넌트

**journey-timeline.tsx** — SQL 여정 타임라인:
```
Transform ──●── Review ──●── Validate ──●── Merge ──●── Test ──●
            │            │                           │
         success       FAIL→Fix                    FAIL→Fix
         v1_transform  v2_review                   v3_test
```

**diff-viewer.tsx** — fix_history before/after:
```
--- BEFORE (PostgreSQL) ---              --- AFTER (PostgreSQL) ---
  SELECT user_id, status                   SELECT user_id, status
- WHERE user_id = #{userId}              + WHERE user_id = #{userId}::integer
  AND status = #{status}                   AND status = #{status}::varchar
```

---

## 9. M9-orchestrator: MD 기반 Pipeline Runner (Phase 3)

### 9.1 `src/run_pipeline.py` (신규, ~100줄)

```python
"""MD 기반 파이프라인 실행기. LLM 불필요."""
import subprocess, yaml, re, sys, time
from pathlib import Path
from core.pipeline_logger import PipelineLogger
from core.config import load_config

def parse_pipeline_md(md_path: Path) -> list[dict]:
    """pipeline.md에서 step 목록 추출."""
    steps = []
    for line in md_path.read_text().splitlines():
        m = re.match(r'^\d+\.\s+(\w+)\s*\|\s*(.+?)\s*\|\s*(required|optional)', line)
        if m:
            steps.append({'name': m.group(1), 'command': m.group(2).strip(), 'required': m.group(3) == 'required'})
    return steps

def run_pipeline(step_filter=None):
    config = load_config()
    md_path = Path(config.get('pipeline', {}).get('definition', 'pipeline.md'))
    steps = parse_pipeline_md(md_path)

    logger = PipelineLogger(step='pipeline')

    for step in steps:
        if step_filter and step['name'] != step_filter:
            continue

        logger.log_event('step_start', step_name=step['name'], command=step['command'])
        start = time.time()

        # config에서 workers 등 옵션 주입
        cmd = _inject_config_args(step['command'], config)
        result = subprocess.run(['python3'] + cmd.split(), cwd='src/', env={**os.environ, 'PYTHONPATH': '.'})

        duration = int((time.time() - start) * 1000)
        status = 'success' if result.returncode == 0 else 'fail'
        logger.log_event('step_complete', step_name=step['name'], status=status, duration_ms=duration)

        if status == 'fail' and step['required']:
            if config.get('pipeline', {}).get('stop_on_fail', True):
                logger.log_event('pipeline_stopped', reason=f"{step['name']} failed")
                break

    logger.log_summary(steps_completed=..., steps_failed=...)
    logger.generate_summary_md()
```

### 9.2 `pipeline.md` (프로젝트 루트)

```markdown
# Pipeline: Oracle → PostgreSQL

## Steps
1. analyze    | run_source_analyzer.py | required
2. transform  | run_sql_transform.py --workers 8 | required
3. review     | run_sql_review.py --workers 4 --max-rounds 3 | optional
4. validate   | run_sql_validate.py --workers 6 | optional
5. merge      | run_sql_merge.py | required
6. test       | run_sql_test.py --workers 6 | required
```

---

## 10. M10-config: 통합 설정 (Phase 3)

### 10.1 `oma-config.yaml`

```yaml
project:
  output_dir: ./output
  target_dbms: postgresql
  model_id: global.anthropic.claude-sonnet-4-5-20250929-v1:0

database:
  host: localhost
  port: 5432
  user: postgres
  password: ${DB_PASSWORD}
  database: mydb

pipeline:
  definition: pipeline.md
  transform:
    workers: 8
  review:
    workers: 4
    max_rounds: 3
  validate:
    workers: 6
  test:
    workers: 6
    timeout: 5
  stop_on_fail: true
  retry_failed: true
```

### 10.2 `src/core/config.py` (신규, ~50줄)

```python
"""통합 config 로더. 우선순위: env var > yaml > DB properties."""
import os, re, yaml
from pathlib import Path
from utils.project_paths import PROJECT_ROOT, DB_PATH

_config_cache = None

def load_config() -> dict:
    global _config_cache
    if _config_cache:
        return _config_cache

    config = {}
    yaml_path = PROJECT_ROOT / 'oma-config.yaml'
    if yaml_path.exists():
        with open(yaml_path) as f:
            config = yaml.safe_load(f) or {}

    # env var 치환: ${VAR_NAME}
    config = _resolve_env_vars(config)

    # env var override (기존 호환)
    if os.environ.get('OMA_OUTPUT_DIR'):
        config.setdefault('project', {})['output_dir'] = os.environ['OMA_OUTPUT_DIR']
    if os.environ.get('TARGET_DBMS_TYPE'):
        config.setdefault('project', {})['target_dbms'] = os.environ['TARGET_DBMS_TYPE']

    _config_cache = config
    return config

def _resolve_env_vars(obj):
    """${VAR} → os.environ[VAR] 재귀 치환."""
    if isinstance(obj, str):
        return re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), m.group(0)), obj)
    if isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env_vars(v) for v in obj]
    return obj
```

---

## 11. Implementation Guide

### 11.1 구현 순서

```
Phase 1 (M1 → M5):
  1. M1-logger: PipelineLogger 클래스 구현
  2. M5-java: Java sqlState/errorCode (독립 작업)
  3. M4-fix-link: convert_sql set_step + fix_history 파일명
  4. M3-db-step: current_step 컬럼 + migration
  5. M2-test-log: run_sql_test.py + test_tools.py 통합
     → summary.md 자동 생성 검증

Phase 2 (M6 → M7):
  6. M6-other-logs: Transform, Review, Validate, Merge 로그
  7. M7-step-migrate: flag → current_step 전환 (20곳+)

Phase 3 (M8 → M10):
  8. M10-config: oma-config.yaml + config.py
  9. M9-orchestrator: pipeline.md + run_pipeline.py
  10. M8-dashboard: Next.js 프로젝트 초기화 + API + 페이지
      → Overview → SQL Explorer → SQL Detail → FAIL Analysis
      → Run History → Pipeline Control → Settings
```

### 11.2 예상 파일 수

| Phase | 신규 | 수정 | 합계 |
|:-----:|:----:|:----:|:----:|
| 1 | 3 | 5 | 8 |
| 2 | 0 | 5 | 5 |
| 3 | ~30 | 2 | ~32 |
| **합계** | **~33** | **~12** | **~45** |

### 11.3 Session Guide

| Session | Scope | Module | 예상 시간 |
|:-------:|-------|--------|:--------:|
| S1 | Phase 1 기반 | M1-logger + M4-fix-link + M5-java | 2h |
| S2 | Phase 1 DB+Test | M3-db-step + M2-test-log | 3h |
| S3 | Phase 2 | M6-other-logs + M7-step-migrate | 3h |
| S4 | Phase 3 기반 | M10-config + M9-orchestrator | 2h |
| S5 | Phase 3 대시보드 API | M8 API Routes | 3h |
| S6 | Phase 3 대시보드 UI | M8 Pages + Components | 4h |

---

## 12. Test Plan

### 12.1 Phase 1 검증

```bash
# 1. PipelineLogger 단위 테스트
python -c "
from core.pipeline_logger import PipelineLogger
logger = PipelineLogger('test')
logger.log_sql_result('master/UserMapper.xml', 'selectUser', 'fail', 1200,
                      fail_category='parameter', sql_state='42883')
logger.log_summary(total=1, pass_=0, fail=1, skip=0, duration_ms=1200)
path = logger.generate_summary_md()
print(open(path).read())
"

# 2. Test runner 통합 (example/ 프로젝트)
cd src && PYTHONPATH=. python3 run_sql_test.py --workers 1
# 확인: output/logs/test/{timestamp}/events.jsonl 생성
jq 'select(.status=="fail")' output/logs/test/*/events.jsonl
cat output/logs/test/*/summary.md

# 3. fix_history 파일명 확인
ls output/logs/fix_history/*_test.log

# 4. current_step 확인
sqlite3 output/oma_control.db "SELECT current_step, COUNT(*) FROM transform_target_list GROUP BY current_step"
```

### 12.2 Phase 3 검증

```bash
# 대시보드 실행
cd dashboard && npm run dev
# http://localhost:3000 → Overview 페이지
# /sql → SQL Explorer → 행 클릭 → SQL Detail 여정 타임라인
# /analysis → FAIL 사유 차트
# /control → Transform 실행 버튼 클릭
```

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-04-18 | Initial design — Option C (Pragmatic), 10 Modules, 4 Phases | Design |
