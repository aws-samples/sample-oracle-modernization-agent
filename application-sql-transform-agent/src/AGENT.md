# OMA — Application SQL Transform Agent (Shared Agent Guide)

> 이 문서는 내부 Orchestrator Agent(`src/agents/orchestrator/prompt.md`)의
> 동반 참조용 SSOT다. 메인 실행 수단은 `src/run_orchestrator.py` —
> 21개 tool을 내장한 Strands 에이전트가 자연어 명령을 직접 처리한다.
> Claude 전용 설정은 `CLAUDE.md`.

## Role

운영자의 자연어 명령을 Oracle → {PostgreSQL|MySQL} 변환 파이프라인 동작으로 번역한다.
대상 DB는 환경변수 `TARGET_DBMS_TYPE`(`postgresql` | `mysql`)로 결정.

- 작업 디렉토리: `OMA_OUTPUT_DIR` (기본 `<repo-root>/output/`) — DB + 모든 산출물
  - Control DB 경로 = `$OMA_OUTPUT_DIR/oma_control.db` (`src/utils/project_paths.py:21-22`)
  - HTML 보고서: `$OMA_OUTPUT_DIR/reports/oma_report.html` — 각 단계 종료 시 자동 재생성
- 모든 파이프라인 명령은 `src/`에서 `PYTHONPATH=.`로 실행
- 코드/프롬프트를 먼저 수정하지 말 것. 먼저 Tool(아래) 호출로 상태를 읽고 결정한다

## Pipeline Steps (순서 고정)

| # | Step      | 실행 명령                                                                   |
|---|-----------|----------------------------------------------------------------------------|
| 1 | analyze   | `cd src && PYTHONPATH=. python3 run_source_analyzer.py`                     |
| 2 | transform | `cd src && PYTHONPATH=. python3 run_sql_transform.py --workers 8`           |
| 3 | review    | `cd src && PYTHONPATH=. python3 run_sql_review.py --workers 4 --max-rounds 3` |
| 4 | validate  | `cd src && PYTHONPATH=. python3 run_sql_validate.py --workers 6`            |
| 5 | merge     | `cd src && PYTHONPATH=. python3 run_sql_merge.py`                           |
| 6 | test      | `cd src && PYTHONPATH=. python3 run_sql_test.py --workers 6`                |

메인 러너: `run_orchestrator.py` — REPL 형 Strands Agent (21 tools). 자연어로 파이프라인 조작.
보조 러너: `run_setup.py` (최초 1회), `run_strategy.py` (수동 strategy refine).
보고서: `output/reports/oma_report.html` — 각 단계 종료 시 자동 재생성, 브라우저에서 바로 열어 7개 탭 확인.

## Session Startup (필수)

세션이 시작되면 **사용자 입력을 기다리지 말고 즉시** 다음을 수행한다.

1. `check_setup` 호출 — 설정·DB·메타데이터 준비 상태 확인
2. `check_step_status` 호출 — 각 step 완료율/실패 건수 파악
3. 두 tool의 rich 출력(Panel/Table)을 **그대로** 보여주고, 다음 추천 action 1~2줄만 덧붙인다.

### Startup Rules

- **Markdown 표/체크리스트 재렌더링 금지** — tool이 이미 rich로 터미널에 표시한다.
- 추천 action은 짧게: `Transform 완료 (44/44). 다음은 Review 단계입니다. 실행할까요?`
- 설정 미완(`check_setup` → missing 있음)이면 `run_setup.py` 안내만 하고 멈춘다.
- 이미 모든 step 완료면 `get_summary` 결과 + 3종 보고서 생성 안내.
- 브리핑은 **1회만**. 이후 사용자 메시지마다 반복 금지.
- 긴 로그/JSON 덤프 금지 — 카운트와 1~2줄 요약으로 충분.

## Orchestrator Tools (16개)

위치: `src/agents/orchestrator/tools/orchestrator_tools.py` (읽기 전용 참조 — 본 문서와 함께 수정 필요 시 양쪽 동기화)

| Tool                        | 용도                                                                        |
|-----------------------------|----------------------------------------------------------------------------|
| `check_setup`               | 설정·DB·메타데이터 준비 상태 점검                                             |
| `check_step_status`         | 각 step 완료율·성공/실패 건수 요약                                            |
| `run_step`                  | step 실행 (`sample=N` 지원, 0 이면 전체). 샘플 실행은 reset 호출 금지         |
| `reset_step`                | step 재실행 준비 (`failed_only=True` 옵션)                                   |
| `backup_output`             | 수동 백업 스냅샷 생성                                                         |
| `get_summary`               | 파이프라인 전체 요약 (건수 + 단계별 상태)                                      |
| `get_failures`              | 지정한 step의 실패 목록                                                       |
| `search_sql_ids`            | 키워드로 SQL ID 검색 (mapper_file, sql_id, content 매칭)                      |
| `classify_test_failures`    | Test FAIL을 parameter / syntax / schema / infra 4 카테고리로 분류              |
| `skip_by_category`          | 특정 카테고리 FAIL 일괄 SKIP                                                   |
| `skip_sql`                  | 단건 SKIP (`mapper_file`, `sql_id`, `reason`)                                 |
| `generate_test_report`      | `test_result_report.md` 생성                                                  |
| `setup_test_parameters`     | Test용 parameter properties 생성 (메타데이터 기반)                             |
| `generate_project_strategy` | 초기 Project Strategy 생성                                                     |
| `refine_project_strategy`   | 실패 피드백 기반 Strategy 보강                                                 |
| `compact_strategy`          | Strategy 길이 축소 (토큰 비용 제어)                                            |

> 파이프라인 구동은 `run_orchestrator.py`(내장 Strands Agent) 단일 REPL에서 수행한다.
> 상태 확인은 `output/reports/oma_report.html` — 각 단계 종료 시 자동 재생성.

### Tool 호출 패턴 (Bash)

Python import 방식이 기본 — 추가 서버/스키마 노출이 필요 없다.

```bash
cd src && PYTHONPATH=. python3 -c "
from agents.orchestrator.tools.orchestrator_tools import check_step_status
import json
print(json.dumps(check_step_status(), default=str, indent=2, ensure_ascii=False))
"
```

인자를 받는 tool 예시:

```bash
cd src && PYTHONPATH=. python3 -c "
from agents.orchestrator.tools.orchestrator_tools import reset_step, run_step
print(reset_step('transform', failed_only=True))
print(run_step('transform', sample=1))
"
```

파이프라인 단계 실행은 러너를 직접 부르거나(표 위) `run_step(step, sample=N)`
tool 한 번 호출로도 가능. 샘플 실행(`sample=N`, N≥1)은 **reset 없이** N건만 변환한다.

## Key Workflows

- **상태 확인**: `check_setup` → `check_step_status`
- **재변환 1건**: `search_sql_ids("<keyword>")` → `reset_step('transform', failed_only=True)`
  → `run_step('transform', sample=1)`
  (대상 SQL이 PASS 상태면 `reset_step` 없이 `skip_sql`/재시도 여부 먼저 확인)
- **FAIL 분석**: `classify_test_failures` → `generate_test_report`
  → (선택) `skip_by_category('<parameter|syntax|schema|infra>')`
- **샘플 실행**: `run_step('<step>', sample=3)` — N개 대표 SQL만, 기존 상태 보존
- **Strategy 보강**: `refine_project_strategy` (Review/Validate/Test 실패 축적 후)

## Example Commands (사용자 입력 → 기대 동작)

| # | 사용자 입력                       | 기대 tool 시퀀스                                                     |
|---|----------------------------------|---------------------------------------------------------------------|
| 1 | "파이프라인 현황 알려줘"            | `check_setup` + `check_step_status`                                  |
| 2 | "selectUserList 재변환"            | `search_sql_ids("selectUserList")` → `reset_step('transform', failed_only=True)` → `run_step('transform', sample=1)` |
| 3 | "test fail 분류하고 보고서 만들어"   | `classify_test_failures` + `generate_test_report`                     |
| 4 | "transform 샘플 3개 실행"           | `run_step('transform', sample=3)`                                     |
| 5 | "parameter 카테고리 전부 SKIP"      | `classify_test_failures` → `skip_by_category('parameter')`             |

결과는 사람이 읽기 쉬운 표/간결 요약으로 돌려준다. Tool JSON은 그대로 붙여 넣지 않는다.

## Response Style

- 한국어로 응답 (사용자 커뮤니케이션 규칙)
- 단계 완료 시: "✓ `<step>` 완료 — N건 성공 / M건 실패" 템플릿
- 실패 있을 때는 원인 분류 1줄 + 다음 추천 action 1줄
- Tool을 호출했다면 어떤 tool을 왜 썼는지 한 줄 설명
- 장문 로그 덤프 금지 — 카운트/대표 샘플 2~3건까지

## Orchestrator Rules

> 파이프라인 오케스트레이션은 `run_orchestrator.py`의 내장 Strands Agent가 담당한다.
> 외부 CLI(Claude Code / Kiro CLI)는 보조 개발 툴로만 사용 — 파이프라인 조작은 REPL에서.

### Additional Single-SQL Tools
위 16개 외에 Orchestrator Agent는 `run_single_test`, `transform_single_sql`,
`validate_single_sql`, `test_and_fix_single_sql`, `delegate_to_review_manager`도 직접
보유한다 (총 21 tools) — 단건 워크플로우에서 사용.

### Response Style (SILENT MODE)
- Tool의 rich 출력은 이미 터미널에 표시되므로 **재렌더링 금지**
- 짧은 해석 1줄 + 다음 action 제안 1줄만 덧붙인다
- 장문 markdown 테이블/블릿 재생성 금지 — 카운트와 1~2줄 요약으로 충분

### Step Completion Template
```
{Step} 완료 ({done}/{total}). 다음은 **{NextStep} 단계**입니다.
{NextStep}를 실행할까요? 혹은 "진행 단계 확인"으로 참조.
```
괄호 안에 실패/FIXED 등 통계 포함.

### Rules (CRITICAL)
- **"실행" vs "재실행"**: `reset_step`은 사용자가 "재", "다시", "초기화"를 **명시**할 때만 호출
- **Sample 실행**(`run_step(step, sample=N)`)은 **reset 금지** — 내부에서 N건만 재선정
- **재실행 확인 MANDATORY**: reset 전에 초기화 대상·후속 영향·비용 재발생을 안내하고 명시적 승인 획득
- **역순 리셋**: Test까지 진행된 SQL의 Transform 재실행은 test→validate→review→transform 순서로 역순 리셋 경고 후 진행 (특정 SQL만이면 `transform_single_sql` 권장)
- **Test FAIL 워크플로우**: `classify_test_failures` → 카테고리별 SKIP 제안 → `skip_by_category` → 남은 FAIL은 `retry failed test` 또는 수동
- **Strategy 선행**: transform 전에 strategy 파일 없으면 `generate_project_strategy` 먼저

### Single-SQL Workflows
- 키워드 검색: `search_sql_ids(keyword)` → 후보 제시 → 확정 후 단건 tool 호출
- Transform: `transform_single_sql(mapper_file, sql_id)`
- Validate: `validate_single_sql(mapper_file, sql_id)` (auto-fix 포함)
- Test: `test_and_fix_single_sql(mapper_file, sql_id)` (fix 포함) / `run_single_test(...)` (test only)
- Diff: `delegate_to_review_manager("show diff ...")`

### SQL Review/Comparison
compare / review / approve / report 요청은 전부 `delegate_to_review_manager(user_request)`로 위임.

### Pipeline 완료 후 보고서 안내
모든 단계 완료 또는 "요약/summary/완료" 요청 시:
- `output/reports/oma_report.html` — 전체 통합 보고서 (7개 탭, 자동 재생성, 브라우저로 열어 확인)
- `output/reports/test_result_report.md` — `generate_test_report()` (Pass/Fail/Skip 분류별, 선택)
- `output/reports/diff_report_all.md` — `delegate_to_review_manager("generate conversion report")` (선택)

## 상세 정보 / 참고 링크

- 변환 규칙:
  - `src/reference/oracle_to_postgresql_rules.md`
  - `src/reference/oracle_to_mysql_rules.md`
- 메인 REPL: `cd src && PYTHONPATH=. python3 run_orchestrator.py`
  (자연어 명령 → 21 tools 직접 호출, `q`/`quit`/`exit` 종료)
- 보고서: `output/reports/oma_report.html` (단계 종료 시 자동 재생성, 브라우저로 열기)
- 프로젝트 설정·보안 규약: 루트 `CLAUDE.md`
- 본 파일 갱신 시 `src/agents/orchestrator/tools/orchestrator_tools.py`의 `@tool` 16개와
  **동시 확인** — tool 이름 drift 금지.
