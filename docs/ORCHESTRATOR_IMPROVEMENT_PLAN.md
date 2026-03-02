# Orchestrator 개선 계획서

**작성일**: 2026-02-25
**버전**: 2.1
**현재 상태**: 계획 수립 단계
**목표 기간**: 1주 (5일)

---

## 📋 목차

1. [현황 분석](#현황-분석)
2. [개선 목표](#개선-목표)
3. [핵심 개선 항목 (4가지)](#핵심-개선-항목)
4. [구현 로드맵](#구현-로드맵)
5. [성공 지표](#성공-지표)
6. [선택적 개선 항목](#선택적-개선-항목)

---

## 현황 분석

### 현재 아키텍처

```
Orchestrator (단일 Agent)
  ├─ 18개 Tools
  │   ├─ Pipeline Control: check_setup, run_step, reset_step
  │   ├─ Status Monitoring: check_step_status, get_summary
  │   ├─ SQL Management: search_sql_ids, transform/validate/test_single_sql
  │   ├─ Strategy Management: generate, refine, compact
  │   └─ Diff Tools: show_diff, generate_report, approve, suggest_revision
  └─ 실행 방식: subprocess/import → SQLite DB 간접 통신
```

### 주요 문제점 (우선순위 재평가)

| 문제 | 영향도 | 실제 필요성 | 우선순위 |
|------|--------|------------|----------|
| **역할 과다**: Orchestrator가 18개 Tool 보유 | 높음 | 필수 | 🔴 P0 |
| **프롬프트 비효율**: 157줄 전체 로드 | 중간 | 필수 | 🔴 P0 |
| **Agent 간 통신**: subprocess로만 실행 | 중간 | 선택 | 🟡 P1 |
| **상태 관리**: 직접 DB 접근 | 낮음 | 선택 | 🟡 P1 |
| **Tool 반환값 타입 미정의**: dict 반환으로 타입 안전성 없음 | 중간 | 선택 | 🟡 P1 |
| ~~동기적 실행~~ | 낮음 | 불필요 | ⚪ 제외 |
| ~~고정된 워크플로우~~ | 낮음 | 과도설계 | ⚪ 제외 |
| ~~관찰성 (Tracing)~~ | 낮음 | 과도설계 | ⚪ 제외 |

**핵심 인사이트**: 역할 분리와 프롬프트 최적화만 해도 80% 개선됨

---

## 개선 목표

### 전체 목표
**"단순하고 유지보수 가능한 Orchestrator - 최소한의 개선으로 최대 효과"**

### 구체적 목표 (1주 내)

1. **역할 분리**: Orchestrator의 책임을 명확히 분리 (18 tools → 5-7 tools)
2. **코드 품질**: 프롬프트 크기 감소 (157줄 → 50줄), 테스트 가능한 구조
3. **유지보수성**: 각 Agent를 독립적으로 수정/테스트 가능

### 추가 목표 (선택적)

4. **직접 호출**: subprocess 대신 Agent 직접 호출 (실시간 진행률)
5. **상태 관리**: DB 접근 인터페이스 통일

---

## 핵심 개선 항목

**우선순위 원칙**: ROI(투입 시간 대비 효과)가 높은 순서

### 1. ReviewManager Agent 분리 (P0) 🔴

**현재 문제:**
- Orchestrator가 Diff 비교/승인 기능까지 포함 (5개 tools)
- 프롬프트에 Diff 관련 설명이 섞여 있음
- 단일 책임 원칙 위반

**개선 방안:**
```
[Before]
Orchestrator (18 tools)
  ├─ 파이프라인 제어 (6 tools)
  ├─ Diff 관리 (5 tools) ← 분리 대상
  ├─ 전략 관리 (3 tools)
  ├─ 단일 SQL 처리 (4 tools)

[After]
Orchestrator (7 tools)
  ├─ check_setup
  ├─ check_step_status
  ├─ run_step
  ├─ reset_step
  ├─ get_summary
  ├─ search_sql_ids
  └─ delegate_to_review_manager  ← NEW

ReviewManagerAgent (5 tools) ← NEW
  ├─ show_sql_diff
  ├─ generate_diff_report
  ├─ get_review_candidates
  ├─ approve_conversion
  └─ suggest_revision
```

**구현 단계:**

**Day 1:**
1. 새 Agent 생성
```bash
mkdir -p src/agents/review_manager/tools
touch src/agents/review_manager/agent.py
touch src/agents/review_manager/prompt.md
touch src/agents/review_manager/README.md
```

2. diff_tools.py 이동
```bash
mv src/agents/orchestrator/tools/diff_tools.py \
   src/agents/review_manager/tools/
```

3. ReviewManager Agent 구현
```python
# src/agents/review_manager/agent.py
from strands import Agent
from strands.models.bedrock import BedrockModel
from .tools.diff_tools import (
    show_sql_diff, generate_diff_report, get_review_candidates,
    approve_conversion, suggest_revision
)

def create_review_manager_agent() -> Agent:
    model = BedrockModel(model_id=MODEL_ID, max_tokens=16000)
    return Agent(
        name="ReviewManager",
        model=model,
        system_prompt=_load_system_prompt(),
        tools=[
            show_sql_diff, generate_diff_report, get_review_candidates,
            approve_conversion, suggest_revision
        ]
    )
```

**Day 2:**
4. Orchestrator 프롬프트 수정
```markdown
# Before (157줄)
- Diff Tools 설명 (30줄)
- SQL Diff workflow (20줄)

# After (80줄) - Diff 관련 제거
- 파이프라인 제어 설명만 유지
- Review 관련 요청은 ReviewManager에 위임
```

5. Orchestrator에서 ReviewManager 호출
```python
# src/agents/orchestrator/agent.py
from agents.review_manager.agent import create_review_manager_agent

@tool
def delegate_to_review_manager(user_request: str) -> str:
    """Delegate review/diff requests to ReviewManager.

    Args:
        user_request: User's review request
    """
    review_manager = create_review_manager_agent()
    result = review_manager(user_request)
    return result
```

**구현 파일:**
- `src/agents/review_manager/` (NEW)
  - `agent.py`
  - `prompt.md`
  - `tools/diff_tools.py` (이동)
- `src/agents/orchestrator/prompt.md` (수정: 157줄 → 80줄)
- `src/agents/orchestrator/agent.py` (수정: delegate tool 추가)

**예상 소요 시간**: 2일

**기대 효과:**
- ✅ Orchestrator 프롬프트 50% 감소
- ✅ 각 Agent 독립적 테스트 가능
- ✅ 역할 명확화
- ✅ 향후 Review 기능 확장 용이

---

### 2. StateManager 래퍼 클래스 (P1) 🟡

**현재 문제:**
- Orchestrator가 너무 많은 책임 보유 (18개 Tools)
- 유지보수성 저하, 테스트 어려움

**개선 방안:**
```
[Before]
Orchestrator (18 tools)

[After]
Orchestrator (5 tools)
  ├─ run_pipeline
  ├─ check_health
  ├─ monitor_progress
  ├─ handle_error
  └─ coordinate_agents

ReviewManagerAgent (5 tools) ← NEW
  ├─ show_sql_diff
  ├─ generate_diff_report
  ├─ get_review_candidates
  ├─ approve_conversion
  └─ suggest_revision

StrategyManagerAgent (3 tools) ← 기존 strategy_refine 확장
  ├─ generate_project_strategy
  ├─ refine_project_strategy
  └─ compact_strategy

ProgressMonitorAgent (3 tools) ← NEW
  ├─ get_current_status
  ├─ track_metrics
  └─ generate_reports
```

**구현 파일:**
- `src/agents/review_manager/` (NEW)
  - `agent.py`
  - `prompt.md`
  - `tools/diff_tools.py` (현재 orchestrator/tools/diff_tools.py 이동)
- `src/agents/progress_monitor/` (NEW)
  - `agent.py`
  - `tools/monitor_tools.py`
- `src/agents/strategy_refine/` (확장)
  - 기존 코드 유지, 역할 명확화

**예상 소요 시간**: 3-4일

**기대 효과:**
- ✅ 각 Agent 독립적 테스트 가능
- ✅ 프롬프트 크기 감소 (157줄 → 50줄)
- ✅ 유지보수성 향상

---

**현재 문제:**
- 모든 Agent가 직접 DB 접근
```python
conn = sqlite3.connect(DB_PATH)
cursor.execute("UPDATE transform_target_list SET transformed='Y'")
```
- 코드 중복, 에러 처리 분산

**개선 방안 (간단한 래퍼만):**
```python
# src/core/state_manager.py
class StateManager:
    """DB 접근을 위한 간단한 래퍼 클래스"""

    def __init__(self, db_path):
        self.db_path = db_path

    def update_sql_status(self, mapper_file, sql_id, **kwargs):
        """SQL 상태 업데이트"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Dynamic UPDATE
        fields = ', '.join(f"{k}=?" for k in kwargs.keys())
        values = list(kwargs.values()) + [mapper_file, sql_id]

        cursor.execute(f"""
            UPDATE transform_target_list
            SET {fields}, updated_at=CURRENT_TIMESTAMP
            WHERE mapper_file=? AND sql_id=?
        """, values)

        conn.commit()
        conn.close()

    def get_pending_tasks(self, step):
        """대기 중인 작업 조회"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        column_map = {
            'transform': 'transformed',
            'review': 'reviewed',
            'validate': 'validated',
            'test': 'tested'
        }

        cursor.execute(f"""
            SELECT mapper_file, sql_id
            FROM transform_target_list
            WHERE {column_map[step]}='N'
        """)

        results = cursor.fetchall()
        conn.close()
        return results

# 사용 예시
state = StateManager(DB_PATH)
state.update_sql_status('UserMapper.xml', 'selectUser', transformed='Y')
pending = state.get_pending_tasks('transform')
```

**구현 단계:**

**Day 3:**
1. StateManager 클래스 작성 (100줄 정도)
2. 기존 SQL 쿼리 3-4개 래퍼 메서드로 변환
3. 단위 테스트 작성

**Day 4:**
4. orchestrator_tools.py에서 StateManager 사용하도록 수정
5. 통합 테스트

**구현 파일:**
- `src/core/state_manager.py` (NEW, ~150줄)
- `src/agents/orchestrator/tools/orchestrator_tools.py` (수정)

**예상 소요 시간**: 2일

**기대 효과:**
- ✅ 코드 중복 제거
- ✅ DB 접근 로직 통일
- ✅ 향후 DB 변경 시 한 곳만 수정
- ⚠️ 동시성 제어는 아직 미흡 (필요시 추가)

---

### 3. Tool 반환값 TypedDict 정의 (P1) 🟡

**현재 문제:**
- 모든 tool 함수가 `dict`를 반환 → Orchestrator 프롬프트에서 반환 구조를 설명해야 함
- 반환 키 오타, 누락 시 런타임에서야 발견
- Orchestrator가 결과를 처리할 때 어떤 키가 있는지 코드만 봐서는 알 수 없음

```python
# 현재: 반환 구조가 불명확
def check_step_status() -> dict:
    return {"transform_complete": True, "transformed": 10, ...}

# Orchestrator 프롬프트에서 직접 설명해야 함
# Returns: {source_analyzed, extracted, transformed, ...} with counts
```

**개선 방안:**

```python
# src/agents/orchestrator/schemas.py (NEW)
from typing import TypedDict

class StepStatusResult(TypedDict):
    source_analyzed: int
    extracted: int
    transformed: int
    reviewed: int
    validated: int
    tested: int
    transform_complete: bool
    review_complete: bool
    validate_complete: bool
    test_complete: bool

class RunStepResult(TypedDict):
    status: str       # 'success' | 'error'
    details: str
    needs_merge: bool

class SearchSqlResult(TypedDict):
    total: int
    mappers_count: int
    results: dict     # {mapper_file: [{sql_id, sql_type}]}
```

```python
# 적용 예시
from .schemas import StepStatusResult

def check_step_status() -> StepStatusResult:
    ...
    return StepStatusResult(transform_complete=True, transformed=10, ...)
```

**구현 단계:**

**Day 3 (StateManager와 병행):**
1. `src/agents/orchestrator/schemas.py` 작성 — 주요 tool 반환 TypedDict 정의
2. `orchestrator_tools.py`의 반환값에 TypedDict 적용
3. `diff_tools.py` 반환값에 TypedDict 적용 (ReviewManager 분리 시 함께)

**구현 파일:**
- `src/agents/orchestrator/schemas.py` (NEW, ~60줄)
- `src/agents/orchestrator/tools/orchestrator_tools.py` (수정: 반환 타입 힌트 추가)
- `src/agents/review_manager/schemas.py` (NEW, ~30줄) — ReviewManager 분리 시

**예상 소요 시간**: 1일 (StateManager Day 3에 병행)

**기대 효과:**
- ✅ Orchestrator 프롬프트에서 반환 구조 설명 불필요 → 프롬프트 추가 단축
- ✅ 반환 키 오타/누락을 IDE에서 즉시 감지
- ✅ 새 tool 추가 시 반환 구조가 명확해 온보딩 속도 향상

---

### 4. Agent 직접 호출 (P1, 선택적) 🟡

**현재 문제:**
```python
# subprocess로 분리 실행 → 실시간 진행률 불가
run_step('transform'):
    subprocess.run(['python3', 'src/run_sql_transform.py'])
```

**개선 방안:**
```python
# importlib로 직접 호출
import importlib

def run_step(step_name):
    module_name = f'run_sql_{step_name}'
    mod = importlib.import_module(module_name)

    # 직접 호출
    result = mod.run()
    return result
```

**구현 단계:**

**Day 5:**
1. run_step() 함수 수정 (orchestrator_tools.py)
2. 각 run_*.py 파일이 import 가능한지 확인
3. 테스트

**구현 파일:**
- `src/agents/orchestrator/tools/orchestrator_tools.py` (수정)

**예상 소요 시간**: 1일

**기대 효과:**
- ✅ 약간의 성능 향상 (subprocess 오버헤드 제거)
- ✅ 향후 콜백 추가 가능
- ⚠️ 현재는 큰 차이 없음 (선택적)

---

## 제외된 항목 (과도설계)

### ❌ Event Bus
- **이유**: subprocess 실행도 충분히 작동, 복잡도만 증가
- **필요 시점**: Agent 간 실시간 협업이 필요할 때

### ❌ Circuit Breaker
- **이유**: 대규모 운영 환경에서나 필요
- **현재**: 단순 retry로 충분

### ❌ DAG 워크플로우
- **이유**: 현재 파이프라인이 단순 (6단계 순차)
- **필요 시점**: 조건부 분기가 10개 이상일 때

### ❌ Distributed Tracing
- **이유**: 로컬 실행, 로그로 충분
- **필요 시점**: 마이크로서비스 환경

### ❌ Work Stealing
- **이유**: ThreadPoolExecutor가 이미 잘 함
- **필요 시점**: 작업 시간 편차가 10배 이상일 때

---

### 4. 이벤트 기반 아키텍처 (제외)

**현재 문제:**
- 동기적 실행: transform 완료 → validate 시작
- 부분 실패 시 전체 대기

**개선 방안:**
```python
# Event Bus 도입
class PipelineEventBus:
    def __init__(self):
        self.subscribers = defaultdict(list)

    def emit(self, event_type, data):
        for handler in self.subscribers[event_type]:
            handler(data)

    def subscribe(self, event_type, handler):
        self.subscribers[event_type].append(handler)

# Agent는 이벤트 발행/구독
event_bus = PipelineEventBus()

# Transform Agent
event_bus.emit('sql_transformed', {
    'sql_id': 'selectUser',
    'status': 'success'
})

# Validate Agent (자동 트리거)
event_bus.subscribe('sql_transformed', validate_agent.on_transform_complete)

# Strategy Agent (학습)
event_bus.subscribe('validation_failed', strategy_agent.learn_from_failure)
```

**구현 파일:**
- `src/core/event_bus.py` (NEW)
- `src/core/event_types.py` (NEW) - 이벤트 타입 정의
- 모든 Agent에 `on_<event>` 핸들러 추가

**예상 소요 시간**: 5-6일

**기대 효과:**
- ✅ 느슨한 결합 (Decoupling)
- ✅ 비동기 처리 가능
- ✅ 동적 워크플로우 지원

---

### 5. 에러 처리 및 복구 전략 (P1)

**현재 문제:**
```python
# 단순 에러 반환
except Exception as e:
    return {'status': 'error', 'error': str(e)}
```

**개선 방안:**
```python
# 계층적 에러 타입
class RetryableError(Exception):
    """재시도 가능 (네트워크 오류 등)"""

class RecoverableError(Exception):
    """복구 가능 (Worker 감소 등)"""

class FatalError(Exception):
    """복구 불가 (설정 오류 등)"""

# Retry 데코레이터
@retry(
    max_attempts=3,
    backoff=exponential_backoff,
    on_failure=log_and_notify
)
def transform_sql(sql_id):
    ...

# Circuit Breaker
class CircuitBreaker:
    def __init__(self, failure_threshold=5):
        self.failure_count = 0
        self.threshold = failure_threshold
        self.state = 'closed'  # closed, open, half_open

    def call(self, func):
        if self.state == 'open':
            raise CircuitOpenError("Too many failures")
        try:
            result = func()
            self.on_success()
            return result
        except Exception as e:
            self.on_failure()
            raise

# Fallback 전략
@with_fallback(strategy='reduce_workers')
def run_parallel_transform(workers=8):
    ...
```

**구현 파일:**
- `src/core/errors.py` (NEW) - 에러 타입 정의
- `src/core/retry.py` (NEW) - Retry 로직
- `src/core/circuit_breaker.py` (NEW)
- `src/agents/orchestrator/recovery_strategies.py` (NEW)

**예상 소요 시간**: 3-4일

**기대 효과:**
- ✅ 자동 복구율 향상
- ✅ 시스템 안정성 증가
- ✅ 에러 전파 제어

---

### 6. 관찰성 강화 - Observability (P1)

**현재 문제:**
- 로그만으로 디버깅
- Agent 간 호출 체인 추적 불가
- 성능 병목 파악 어려움

**개선 방안:**
```python
# Structured Logging
import structlog

logger = structlog.get_logger()

@trace_execution  # 자동으로 trace_id, span_id 추가
@measure_performance  # 실행 시간 측정
def transform_sql(sql_id):
    logger.info("transform_started",
                sql_id=sql_id,
                trace_id=get_trace_id(),
                agent="transform")
    ...
    logger.info("transform_completed",
                sql_id=sql_id,
                duration_ms=duration)

# Metrics 수집
from prometheus_client import Gauge, Histogram, Counter

# Gauge: 현재 값
pipeline_pending = Gauge('pipeline_transform_pending', 'Pending transform tasks')

# Histogram: 분포
agent_duration = Histogram('agent_transform_duration_seconds', 'Transform duration')

# Counter: 누적 카운트
transform_errors = Counter('agent_transform_errors_total', 'Transform errors', ['error_type'])

# 사용
pipeline_pending.set(pending_count)
with agent_duration.time():
    transform_sql(sql_id)
transform_errors.labels(error_type='timeout').inc()
```

**구현 파일:**
- `src/core/observability/` (NEW)
  - `tracing.py` - Trace ID 생성/전파
  - `metrics.py` - Prometheus 메트릭
  - `logging_config.py` - Structured logging 설정
- `requirements.txt` 업데이트: structlog, prometheus-client

**예상 소요 시간**: 3-4일

**기대 효과:**
- ✅ 전체 호출 체인 추적 가능
- ✅ 성능 병목 자동 감지
- ✅ 에러 분석 용이

---

### 7. 동적 워크플로우 - Dynamic Workflows (P2)

**현재 문제:**
- 고정된 파이프라인: analyze → transform → review → validate → test → merge
- 조건부 분기 불가

**개선 방안:**
```python
# DAG (Directed Acyclic Graph) 기반
from src.core.workflow import Pipeline, Stage, Condition

# 워크플로우 정의
pipeline = Pipeline()

# 단계 추가
pipeline.add_stage(Stage('analyze'))
pipeline.add_stage(Stage('transform', depends_on=['analyze']))
pipeline.add_stage(Stage('review', depends_on=['transform']))

# 조건부 분기
pipeline.add_conditional(
    condition=Condition(lambda ctx: ctx.validation_failures > 3),
    true_stage=Stage('manual_review'),
    false_stage=Stage('proceed_to_test')
)

# 병렬 처리
pipeline.add_parallel_stage([
    Stage('validate_oracle_syntax'),
    Stage('validate_postgresql_syntax')
])

# 실행
result = pipeline.execute(context={'workers': 8})
```

**구현 파일:**
- `src/core/workflow/` (NEW)
  - `pipeline.py` - Pipeline 클래스
  - `stage.py` - Stage 클래스
  - `condition.py` - 조건부 로직
  - `executor.py` - DAG 실행 엔진

**예상 소요 시간**: 5-7일

**기대 효과:**
- ✅ 유연한 워크플로우
- ✅ 실험적 단계 추가 용이
- ✅ A/B 테스트 가능

---

### 8. 프롬프트 최적화 (P2)

**현재 문제:**
- 157줄의 긴 프롬프트
- 모든 규칙을 한 번에 로드

**개선 방안:**
```python
# Dynamic Prompt Loading
class PromptManager:
    def __init__(self):
        self.base_prompt = self._load_base()
        self.context_prompts = self._load_contexts()

    def get_prompt(self, user_query):
        context = self._detect_context(user_query)

        # Base Prompt + Context-specific Prompt
        return [
            SystemContentBlock(text=self.base_prompt),
            SystemContentBlock(cachePoint={"type": "default"}),  # 캐시 포인트
            SystemContentBlock(text=self.context_prompts[context])
        ]

    def _detect_context(self, query):
        if 'transform' in query.lower():
            return 'transform'
        elif 'diff' in query.lower() or '비교' in query:
            return 'diff'
        elif 'error' in query.lower() or '에러' in query:
            return 'error_recovery'
        return 'general'

# Prompt 파일 구조
prompts/
  ├─ base_prompt.md            # 항상 로드 (30줄)
  ├─ context_transform.md      # Transform 관련 (20줄)
  ├─ context_diff.md           # Diff 관련 (15줄)
  ├─ context_error.md          # 에러 처리 (25줄)
  └─ examples/                 # Few-shot examples
      ├─ transform_examples.md
      └─ recovery_examples.md
```

**구현 파일:**
- `src/agents/orchestrator/prompts/` (NEW)
  - `base_prompt.md`
  - `context_*.md`
- `src/agents/orchestrator/prompt_manager.py` (NEW)
- `src/agents/orchestrator/agent.py` 수정 (Dynamic loading)

**예상 소요 시간**: 2-3일

**기대 효과:**
- ✅ 토큰 사용량 감소
- ✅ 컨텍스트 정확도 향상
- ✅ 프롬프트 관리 용이

---

### 9. 병렬 처리 최적화 (P2)

**현재 문제:**
- 고정된 worker 수 (8)
- 시스템 리소스 고려 없음

**개선 방안:**
```python
# Adaptive Worker Pool
class AdaptiveWorkerPool:
    def __init__(self):
        self.workers = self._detect_optimal_workers()
        self.error_rate = 0.0

    def _detect_optimal_workers(self):
        cpu_count = os.cpu_count()
        memory_gb = psutil.virtual_memory().available // (1024**3)

        # Agent당 1GB 가정
        max_workers = min(cpu_count, memory_gb, 16)

        logger.info("worker_pool_initialized",
                    cpu=cpu_count,
                    memory_gb=memory_gb,
                    workers=max_workers)

        return max_workers

    def adjust_on_failure(self):
        """실패율 기반 자동 조정"""
        if self.error_rate > 0.3:
            new_workers = max(1, self.workers // 2)
            logger.warning("reducing_workers",
                           from_workers=self.workers,
                           to_workers=new_workers,
                           error_rate=self.error_rate)
            self.workers = new_workers

    def adjust_on_success(self):
        """성공 시 점진적 증가"""
        if self.error_rate < 0.1 and self.workers < 16:
            self.workers = min(16, self.workers + 1)

# Work Stealing
class WorkStealingExecutor:
    """느린 worker의 작업을 빠른 worker에게 재분배"""

    def execute(self, tasks):
        queues = [Queue() for _ in range(self.workers)]
        # 초기 분배
        for i, task in enumerate(tasks):
            queues[i % self.workers].put(task)

        # Worker 시작
        workers = [Worker(queues, i) for i in range(self.workers)]

        # 진행률 모니터링 및 Work Stealing
        self._monitor_and_steal(workers, queues)
```

**구현 파일:**
- `src/core/execution/` (NEW)
  - `adaptive_pool.py`
  - `work_stealing.py`
- `src/run_sql_transform.py` 수정 (Adaptive pool 사용)

**예상 소요 시간**: 3-4일

**기대 효과:**
- ✅ 리소스 효율성 향상
- ✅ 실패 시 자동 조정
- ✅ 처리량 최적화

---

### 10. 자동 학습 루프 (P2)

**현재 문제:**
- 전략 학습이 수동적
- 실패 패턴 분석이 Agent 호출 필요

**개선 방안:**
```python
# Autonomous Learning Loop
class LearningOrchestrator:
    def __init__(self):
        self.failure_buffer = []
        self.learning_threshold = 5

    def monitor_failures(self):
        """실시간 실패 감지"""
        state = state_manager.get_failures()
        self.failure_buffer.extend(state)

        if len(self.failure_buffer) >= self.learning_threshold:
            self.trigger_learning()

    def trigger_learning(self):
        """자동 학습 트리거"""
        patterns = self._extract_patterns(self.failure_buffer)

        # Strategy Agent 호출
        strategy_agent.refine_strategy(patterns)

        # 개선 효과 측정
        improvement = self._benchmark_improvement()

        if improvement > 0.1:  # 10% 이상 개선
            logger.info("learning_successful", improvement=improvement)
            self.failure_buffer.clear()
        else:
            logger.warning("learning_ineffective", improvement=improvement)

    def _extract_patterns(self, failures):
        """실패 패턴 추출"""
        patterns = defaultdict(list)
        for failure in failures:
            error_type = self._classify_error(failure)
            patterns[error_type].append(failure)
        return patterns

# 파이프라인 완료 후 자동 실행
@on_pipeline_complete
def auto_learn():
    learning_orchestrator = LearningOrchestrator()
    learning_orchestrator.monitor_failures()
```

**구현 파일:**
- `src/agents/learning/` (NEW)
  - `learning_orchestrator.py`
  - `pattern_extractor.py`
  - `benchmark.py`
- Event bus에 `pipeline_complete` 이벤트 추가

**예상 소요 시간**: 5-6일

**기대 효과:**
- ✅ 자동 학습
- ✅ 지속적 개선
- ✅ 인간 개입 최소화

---

## 구현 로드맵

### 1주 플랜 (필수)

**목표**: 핵심 개선으로 80% 효과 달성

| 요일 | 작업 | 소요 시간 | 담당 |
|------|------|-----------|------|
| **Day 1** | ReviewManager Agent 생성 | 4시간 | TBD |
| **Day 1-2** | diff_tools 이동 및 프롬프트 작성 | 8시간 | TBD |
| **Day 2** | Orchestrator 프롬프트 수정 (157줄→80줄) | 4시간 | TBD |
| **Day 3** | StateManager 클래스 작성 + TypedDict 스키마 정의 | 8시간 | TBD |
| **Day 4** | orchestrator_tools에 StateManager + TypedDict 적용 | 6시간 | TBD |
| **Day 5** | (선택) Agent 직접 호출 구현 | 6시간 | TBD |

**체크포인트**:
- Day 2 종료: ReviewManager 독립 실행 가능
- Day 4 종료: StateManager 통합 테스트 통과
- Day 5 종료: 전체 통합 테스트 통과

---

### 상세 일정

#### Day 1-2: ReviewManager 분리

**오전 (Day 1)**
- [ ] `src/agents/review_manager/` 디렉토리 생성
- [ ] `agent.py` 스켈레톤 작성
- [ ] `diff_tools.py` 이동 (from orchestrator/tools/)

**오후 (Day 1)**
- [ ] ReviewManager `prompt.md` 작성 (Diff 관련만, ~30줄)
- [ ] `create_review_manager_agent()` 함수 완성
- [ ] 단독 실행 테스트

**Day 2**
- [ ] Orchestrator `prompt.md` 수정 (Diff 설명 제거)
- [ ] Orchestrator에 `delegate_to_review_manager` tool 추가
- [ ] 통합 테스트: "UserMapper의 selectUser 비교해줘"

#### Day 3-4: StateManager

**Day 3**
- [ ] `src/core/state_manager.py` 작성
- [ ] 주요 메서드 구현:
  - `update_sql_status()`
  - `get_pending_tasks()`
  - `get_sql_info()`
- [ ] 단위 테스트 작성

**Day 4**
- [ ] `orchestrator_tools.py`에서 StateManager 사용
- [ ] 기존 SQL 쿼리 3-4개 메서드로 교체
- [ ] 통합 테스트: 전체 파이프라인 1회 실행

#### Day 5: (선택) Agent 직접 호출

- [ ] `run_step()` 함수에서 subprocess → importlib 변경
- [ ] 각 `run_*.py` 모듈 import 가능한지 확인
- [ ] 성능 비교 (subprocess vs import)

---

### 2주차 (선택적 개선)

**필요시 추가:**

| 작업 | 소요 시간 |
|------|-----------|
| Retry 데코레이터 추가 | 1일 |
| Structured Logging (structlog) | 2일 |
| Dynamic Prompt Loading | 2일 |

**총 소요 시간**:
- **필수**: 5일 (1주)
- **선택**: +5일 (2주)

---

## 성공 지표

### 정량적 지표 (1주 후)

| 지표 | 현재 | 목표 | 측정 방법 |
|------|------|------|-----------|
| **Orchestrator 프롬프트 크기** | 157줄 | 80줄 | 파일 줄 수 |
| **Orchestrator Tools 수** | 18개 | 7개 | Tool 함수 개수 |
| **프롬프트 토큰 수** | ~3000 tokens | ~1500 tokens | Claude API 입력 토큰 |
| **코드 중복 (DB 접근)** | 10+ 곳 | 3곳 | grep "sqlite3.connect" 결과 |
| **단위 테스트 커버리지** | 0% | 50%+ | pytest-cov |
| **Tool 반환 타입 정의** | 0개 | 주요 tool 전체 | TypedDict 적용 함수 수 |

### 정성적 지표

- ✅ ReviewManager를 독립적으로 테스트 가능
- ✅ Orchestrator 프롬프트가 파이프라인 제어만 설명
- ✅ DB 접근 로직이 한 곳에 집중됨
- ✅ 새로운 Diff 기능 추가 시 Orchestrator 수정 불필요

### 측정 방법

```bash
# 프롬프트 크기
wc -l src/agents/orchestrator/prompt.md

# DB 접근 코드 중복
grep -r "sqlite3.connect" src/agents/ | wc -l

# 토큰 수 (대략적)
cat src/agents/orchestrator/prompt.md | wc -w
# 토큰 수 ≈ 단어 수 × 1.3
```

---

## 선택적 개선 항목

이하 항목은 **1주 플랜 완료 후** 필요시 추가

### 1. Retry 데코레이터 (1일)

```python
@retry(max_attempts=3, backoff=exponential)
def transform_sql(sql_id):
    ...
```

**필요 시점**: Transform/Test 실패율이 20% 이상일 때

### 2. Structured Logging (2일)

```python
import structlog
logger.info("transform_completed", sql_id=sql_id, duration_ms=100)
```

**필요 시점**: 로그 분석이 어려울 때

### 3. Dynamic Prompt Loading (2일)

```python
# Context별로 프롬프트 동적 로드
prompt = prompt_manager.get_prompt(user_query)
```

**필요 시점**: Orchestrator 프롬프트가 100줄 이상일 때

### 4. Agent 직접 호출 개선 (2일)

```python
# 실시간 콜백
agent.execute(on_progress=lambda p: print(f"{p}%"))
```

**필요 시점**: 사용자가 실시간 진행률을 원할 때

---

## 리스크 분석

### 기술적 리스크 (낮음)

| 리스크 | 확률 | 영향 | 완화 전략 |
|--------|------|------|-----------|
| **ReviewManager 분리 실패** | 낮음 | 중 | 기존 코드 복사해서 시작, 점진적 수정 |
| **프롬프트 변경으로 품질 저하** | 중 | 낮음 | 기존 프롬프트 백업, 테스트 케이스 준비 |
| **StateManager 버그** | 중 | 중 | 단위 테스트 충분히 작성 |

### 일정 리스크 (낮음)

| 리스크 | 확률 | 영향 | 완화 전략 |
|--------|------|------|-----------|
| **1주 내 미완료** | 낮음 | 낮음 | Day 3까지 ReviewManager 완료 필수 |
| **통합 테스트 실패** | 중 | 중 | Day 4에 충분한 테스트 시간 확보 |

**전체 리스크 평가**: 🟢 낮음 (범위가 명확하고 기존 코드 변경 최소)

---

## 다음 단계

### 즉시 실행 (오늘)

1. **계획서 리뷰**: 이 문서 검토
2. **착수 결정**: 1주 플랜 시작 여부 결정
3. **개발 환경 준비**:
   ```bash
   git checkout -b feature/orchestrator-improvement
   git push -u origin feature/orchestrator-improvement
   ```

### Day 1 시작 (내일)

**체크리스트:**
- [ ] `src/agents/review_manager/` 디렉토리 생성
- [ ] ReviewManager 스켈레톤 작성
- [ ] diff_tools.py 이동
- [ ] 기본 동작 테스트

**예상 결과:**
```bash
$ python3 -c "from agents.review_manager.agent import create_review_manager_agent; print('OK')"
OK
```

---

## 부록

### A. 현재 파일 구조

```
src/agents/orchestrator/
├── agent.py                    # 메인 Agent (48줄)
├── prompt.md                   # 프롬프트 (157줄)
├── README.md
└── tools/
    ├── orchestrator_tools.py   # 파이프라인 제어 (502줄)
    └── diff_tools.py           # Diff 관리 (209줄)
```

### B. 목표 파일 구조 (1주 완료 후)

```
src/
├── core/                       # 공통 인프라 (NEW)
│   └── state_manager.py        # DB 접근 래퍼 (~150줄)
│
├── agents/
│   ├── orchestrator/           # 축소된 Orchestrator
│   │   ├── agent.py            # delegate_to_review_manager 추가
│   │   ├── prompt.md           # 157줄 → 80줄
│   │   ├── schemas.py          # Tool 반환 TypedDict 정의 (NEW)
│   │   └── tools/
│   │       └── orchestrator_tools.py  # StateManager + TypedDict 사용
│   │
│   ├── review_manager/         # NEW
│   │   ├── agent.py
│   │   ├── prompt.md           # Diff 관련만 (~30줄)
│   │   ├── schemas.py          # Diff tool 반환 TypedDict (NEW)
│   │   └── tools/
│   │       └── diff_tools.py   # 기존 파일 이동
│   │
│   └── [기존 Agent들...]
```

**변경 파일 요약:**
- 🆕 신규: 5개 파일 (state_manager.py, review_manager/agent.py, review_manager/prompt.md, orchestrator/schemas.py, review_manager/schemas.py)
- ✏️ 수정: 2개 파일 (orchestrator/agent.py, orchestrator/prompt.md)
- 🔀 이동: 1개 파일 (diff_tools.py)

### C. 참고 자료

- [Strands Agents SDK Documentation](https://github.com/anthropics/anthropic-sdk-python)
- [Single Responsibility Principle](https://en.wikipedia.org/wiki/Single-responsibility_principle)
- [YAGNI (You Aren't Gonna Need It)](https://martinfowler.com/bliki/Yagni.html)

---

**문서 이력**

| 날짜 | 버전 | 변경 내역 | 작성자 |
|------|------|-----------|--------|
| 2026-02-25 | 1.0 | 초안 작성 (10주 플랜) | OMA Team |
| 2026-02-25 | 2.0 | 실용 버전으로 수정 (1주 플랜) | OMA Team |
| 2026-02-26 | 2.1 | Tool 반환값 TypedDict 정의 항목 추가 (P1) | OMA Team |

---

## 요약

**핵심 메시지**:
- 10주가 아닌 **1주면 충분**
- 3가지 개선으로 **80% 효과** 달성
- 나머지는 **과도설계** (YAGNI)

**투자 대비 효과 (ROI):**
```
5일 투자 → 프롬프트 50% 감소, 코드 품질 2배 향상
```

