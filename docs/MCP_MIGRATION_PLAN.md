# MCP 서버 전환 계획서

**작성일**: 2026-02-26
**버전**: 1.0
**현재 상태**: 계획 수립 단계
**선행 조건**: ORCHESTRATOR_IMPROVEMENT_PLAN.md P0 완료 후 진행

---

## 📋 목차

1. [전환 목표](#전환-목표)
2. [실행 모델 설계](#실행-모델-설계)
3. [MCP Tool 목록](#mcp-tool-목록)
4. [아키텍처 변경](#아키텍처-변경)
5. [구현 로드맵](#구현-로드맵)
6. [성공 지표](#성공-지표)

---

## 전환 목표

**현재**: CLI 직접 실행 (`python3 src/run_orchestrator.py`)
**목표**: MCP 서버로 노출 → Claude Desktop / Kiro에서 자연어로 마이그레이션 조작

### 기대 효과

- "3번 SQL 변환해줘", "UserMapper diff 보여줘" 같은 자연어 인터페이스
- 배치 실행 중에도 아무 때나 진행 상황 확인 가능
- diff 검토/승인을 대화형으로 처리

---

## 실행 모델 설계

핵심 원칙: **analyze는 동기, 나머지 배치는 백그라운드, 단일 SQL은 인터랙티브**

```
┌─────────────────────────────────────────────────────────────┐
│  MCP Client (Claude Desktop / Kiro)                         │
└──────────────────────┬──────────────────────────────────────┘
                       │ MCP Protocol
┌──────────────────────▼──────────────────────────────────────┐
│  OMA MCP Server                                             │
│                                                             │
│  analyze (동기 — 후속 단계의 전제조건)                       │
│    run_step('analyze') → subprocess.run() 완료까지 대기     │
│    → 완료 후 "transform 실행 가능" 반환                     │
│                                                             │
│  배치 실행 (fire & forget)                                   │
│    run_step('transform'|'review'|...) → Popen 백그라운드   │
│    → 즉시 "started" 반환                                    │
│                                                             │
│  상태 확인 (언제든지)                                        │
│    check_step_status() → SQLite 현재 진행률 반환            │
│                                                             │
│  인터랙티브 (동기)                                           │
│    transform_single_sql() / show_diff() / approve() 등      │
└─────────────────────────────────────────────────────────────┘
```

### run_step 실행 방식

```python
def run_step(step_name: str) -> RunStepResult:
    if step_name == 'analyze':
        # 동기 실행 — 후속 단계의 전제조건이므로 완료까지 대기
        # 주의: MCP 클라이언트 타임아웃(보통 60~120초) 안에 완료되어야 함
        # analyze 소요 시간이 타임아웃을 초과하면 옵션 B(백그라운드+폴링)로 전환 검토
        subprocess.run(['python3', 'src/run_source_analyzer.py'])
        return RunStepResult(status='completed', message='분석 완료. run_step("transform")을 실행하세요.')
    else:
        # 백그라운드 실행 — 즉시 반환
        script_map = {
            'transform': 'src/run_sql_transform.py',
            'review':    'src/run_sql_review.py',
            'validate':  'src/run_sql_validate.py',
            'test':      'src/run_sql_test.py',
            'merge':     'src/run_sql_merge.py',
        }
        subprocess.Popen(['python3', script_map[step_name]])
        return RunStepResult(
            status='started',
            message=f'{step_name} 백그라운드 실행 중. check_step_status()로 진행률을 확인하세요.',
        )
```

---

## MCP Tool 목록

### 배치 제어

| Tool | 실행 방식 | 설명 |
|------|-----------|------|
| `run_step('analyze')` | 동기 | 소스 분석 — 완료까지 대기 (전제조건) |
| `run_step('transform'\|'review'\|...)` | 백그라운드 | 나머지 배치 단계 — 즉시 반환 |
| `reset_step(step_name)` | 동기 | 단계 초기화 |

### 상태 조회 (언제든지)

| Tool | 설명 |
|------|------|
| `check_setup()` | 초기 설정 확인 |
| `check_step_status()` | 전체 파이프라인 진행률 |
| `get_summary()` | 최종 요약 리포트 |
| `search_sql_ids(keyword)` | SQL ID 검색 |

### 인터랙티브 — 단일 SQL (동기)

| Tool | 설명 |
|------|------|
| `transform_single_sql(mapper_file, sql_id)` | 단일 SQL 변환 |
| `validate_single_sql(mapper_file, sql_id)` | 단일 SQL 검증 |
| `test_and_fix_single_sql(mapper_file, sql_id)` | 단일 SQL 테스트+수정 |

### 인터랙티브 — Diff/승인 (ReviewManager, 동기)

| Tool | 설명 |
|------|------|
| `show_sql_diff(mapper_file, sql_id)` | Oracle vs PostgreSQL diff |
| `get_review_candidates(filter_type)` | 검토 대상 목록 |
| `approve_conversion(mapper_file, sql_id, notes)` | 변환 승인 |
| `suggest_revision(mapper_file, sql_id, revised_sql, reason)` | 수정 제안 적용 |
| `generate_diff_report(mapper_file)` | diff 리포트 생성 |

### 전략 관리

| Tool | 설명 |
|------|------|
| `generate_project_strategy()` | 프로젝트 전략 생성 |
| `refine_project_strategy(feedback_type)` | 실패 학습 기반 전략 개선 |
| `compact_strategy()` | 전략 파일 압축 |

---

## 아키텍처 변경

### 현재 구조

```
src/
├── run_orchestrator.py     # CLI 진입점 (Strands Agent)
├── run_sql_transform.py    # 배치 실행 스크립트
└── agents/orchestrator/
    └── agent.py
```

### 목표 구조

```
src/
├── server.py               # MCP 서버 진입점 (NEW)
├── run_orchestrator.py     # 기존 CLI 유지 (하위 호환)
├── run_sql_transform.py    # 배치 실행 스크립트 (유지)
└── agents/
    ├── orchestrator/tools/ # MCP tool로 직접 노출
    └── review_manager/     # ReviewManager (P0 선행 필요)
```

### server.py 구조

```python
# src/server.py
from mcp.server.fastmcp import FastMCP
from agents.orchestrator.tools.orchestrator_tools import (
    check_setup, check_step_status, reset_step, run_step, get_summary, search_sql_ids,
    generate_project_strategy, refine_project_strategy, compact_strategy,
)
from agents.review_manager.tools.diff_tools import (
    show_sql_diff, get_review_candidates, approve_conversion,
    suggest_revision, generate_diff_report,
)
from agents.sql_transform.tools.single_transform import transform_single_sql
from agents.sql_validate.tools.single_validate import validate_single_sql
from agents.sql_test.tools.single_test_fix import test_and_fix_single_sql

mcp = FastMCP("oma")

for fn in [
    check_setup, check_step_status, reset_step, run_step, get_summary, search_sql_ids,
    generate_project_strategy, refine_project_strategy, compact_strategy,
    show_sql_diff, get_review_candidates, approve_conversion, suggest_revision, generate_diff_report,
    transform_single_sql, validate_single_sql, test_and_fix_single_sql,
]:
    mcp.tool()(fn)

def main():
    mcp.run()
```

### MCP 클라이언트 설정

```json
{
  "mcpServers": {
    "oma": {
      "command": "python3",
      "args": ["/path/to/application-sql-transform-assistant/src/server.py"],
      "env": {
        "PYTHONPATH": "/path/to/application-sql-transform-assistant/src"
      }
    }
  }
}
```

---

## 구현 로드맵

> **선행 조건**: ORCHESTRATOR_IMPROVEMENT_PLAN.md P0 완료 필수
> - ReviewManager Agent 분리
> - StateManager 래퍼
> - Tool 반환값 TypedDict 정의

| 작업 | 소요 시간 | 내용 |
|------|-----------|------|
| **Day 1 오전** | 4시간 | `mcp` 의존성 추가, `server.py` 작성, tool 등록 |
| **Day 1 오후** | 4시간 | `run_step()` analyze 동기/나머지 백그라운드 분기 구현 |
| **Day 2** | 4시간 | Kiro/Claude Desktop 연결 테스트, 전체 워크플로우 검증 |

**총 소요 시간**: 2일

---

## 성공 지표

| 지표 | 확인 방법 |
|------|-----------|
| `run_step('analyze')` 완료 후 transform 실행 가능 상태 반환 | MCP 클라이언트에서 확인 |
| `run_step('transform')` 즉시 반환, 백그라운드 실행 확인 | 프로세스 목록 확인 |
| 배치 실행 중 `check_step_status()` 실시간 진행률 확인 | 카운트 증가 확인 |
| `show_sql_diff` → `approve_conversion` 대화형 워크플로우 | 엔드투엔드 테스트 |

---

## 문서 이력

| 날짜 | 버전 | 변경 내역 |
|------|------|-----------|
| 2026-02-26 | 1.0 | 초안 작성 |
