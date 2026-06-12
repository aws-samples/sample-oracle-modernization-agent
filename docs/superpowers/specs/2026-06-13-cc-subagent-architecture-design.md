# CC Subagent Architecture — 전면 재설계 스펙

- **날짜**: 2026-06-13
- **브랜치**: `feature/cc-subagent-architecture`
- **상태**: 설계 승인됨 (구현 전)

## 1. 배경과 목표

현재 Application SQL Transform Agent는 Strands Agents SDK + AWS Bedrock 기반 커스텀
멀티에이전트 파이프라인이다. 최근 운영에서 다음 문제가 반복됐다:

- Strands agent가 tool 호출을 건너뛰거나 출력 JSON 파싱이 깨짐 (fallback 파서까지 추가)
- FD 누수, worker pool 관리 등 인프라 코드를 직접 유지하는 부담
- 새 변환 패턴/예외 대응 시 코드 수정 필요 (유연성 부족)

**목표**: Claude Code를 런타임으로 삼아, LLM 작업은 CC subagent가 수행하고
사용자 인터랙션(옵션·분기)은 CC 대화에서 처리하는 구조로 전환한다.
Strands SDK 의존성을 완전히 제거한다.

## 2. 확정된 결정사항

| 결정 | 선택 |
|------|------|
| 재작성 범위 | **하이브리드** — LLM 작업만 subagent로, 결정적 인프라는 Python CLI 유지 |
| 대상 환경 | **Claude Code 전용** (Kiro CLI 호환 포기) |
| 인터랙션 모드 | **체크포인트 승인형** — 단계 사이마다 결과 요약 + AskUserQuestion 분기 |
| 작업 단위 | **적응형 배치** — mapper 1개 기본, SQL 15건 초과 시 분할, 재시도는 실패 SQL만 |
| 배포 형태 | **프로젝트 로컬** — repo clone 후 해당 디렉토리에서 `claude` 실행 |

## 3. 전체 아키텍처

```
고객: repo clone → claude 실행 → /oma:start
       │
┌─ CC 메인 세션 = 오케스트레이터 ───────────────────────────┐
│  • 파이프라인 진행 관리 (상태는 SQLite SSOT에서 읽음)        │
│  • 단계별 체크포인트: 결과 요약 + AskUserQuestion 분기      │
│  • mapper 배치를 subagent로 병렬 dispatch (최대 5개)       │
└──────────┬───────────────────────────┬──────────────────┘
           │ Agent tool (병렬)          │ Bash
           ▼                           ▼
┌─ Subagents (.claude/agents/) ─┐  ┌─ Python CLI (src/cli/) ─────┐
│  oma-transformer              │  │  oma analyze   (스캔/추출)   │
│  oma-reviewer                 │  │  oma db        (상태 조회/갱신)│
│  oma-validator                │  │  oma merge     (XML 재조립)  │
│  oma-test-fixer               │  │  oma test-exec (psql/mysql)  │
│  oma-strategy-refiner         │  │  oma report    (HTML 생성)   │
└───────────────────────────────┘  └─────────────────────────────┘
            양쪽 모두 SQLite (oma_control.db) 를 SSOT로 공유
```

### 핵심 원칙

1. **메인 세션 = 오케스트레이터.** 기존 `run_orchestrator.py`(Strands REPL)를 CC 대화가
   대체한다. 파이프라인 절차는 skill에 선언적으로 기술하고, 진행 판단과 사용자 분기는
   메인 세션이 수행한다.
2. **Subagent = 순수 LLM 작업자.** mapper 1개(또는 분할 배치)를 받아 변환/리뷰/검증하고
   결과를 `oma db` CLI로 DB에 기록만 한다. 상태 관리·재시도 정책은 메인 세션 몫.
3. **Python CLI = 결정적 인프라.** 기존 `core/` 모듈을 Strands 의존 없는 단일 `oma`
   CLI로 묶는다. XML 파싱/병합, DB 실행, TC 생성, 리포트는 LLM에 맡기지 않는다.

## 4. 파이프라인 흐름과 체크포인트

```
/oma:start (단계별 진입: /oma:analyze, /oma:transform, ...)
 │
 1. Setup ──── oma CLI로 설정 확인, 없으면 AskUserQuestion (타겟 DB, 소스 경로, 접속정보)
 2. Analyze ── Bash: oma analyze → mapper 스캔/SQL 추출/전략 초안
 │   ◆ 체크포인트: 분석 요약 → [전체 변환 / 샘플 N건 / 전략 수정]
 3. Transform ─ 배치 목록 생성 → oma-transformer 병렬 dispatch
 │   ◆ 체크포인트: 성공/실패 집계 → [Review 진행 / 실패 재시도 / 중단]
 4. Review ─── oma-reviewer 병렬 dispatch (syntax + equivalence 관점 통합)
 │   ◆ FAIL 건: [자동 재변환(피드백 포함) / 건너뛰기 / 수동 확인]
 │     — max 3 rounds, round 2+에는 oma-strategy-refiner 선행 실행
 5. Validate ── oma-validator 병렬 dispatch
 │   ◆ 체크포인트: 동등성 애매 케이스 → 건별/일괄 [승인 / 재변환 지시]
 6. Merge ──── Bash: oma merge (결정적 XML 재조립)
 │   ◆ 체크포인트: diff 요약 → [Test 진행 / 특정 mapper diff 상세]
 7. Test ───── Bash: oma test-exec (Phase 0 EXPLAIN / Phase 1 실행 / Phase 1.5 Oracle 비교)
     ◆ FAIL 건: [oma-test-fixer로 자동 수정 / SKIP / 수동] → fix 후 해당 mapper re-merge
 → 종료 시 oma report → HTML 리포트 안내
```

### 적응형 배치 규칙

- 메인 세션이 `oma db pending --step <step>` 결과로 배치 목록 구성
- mapper당 subagent 1개 기본, SQL 15건 초과 mapper는 분할
- 재시도는 실패한 SQL만 모아서 dispatch
- 동시 dispatch 최대 5개 (기존 worker 5와 동일한 보수적 기본값)

## 5. 디렉토리 구조

```
repo/
├── .claude/
│   ├── agents/         # 5개 subagent 정의 (markdown)
│   │   ├── oma-transformer.md
│   │   ├── oma-reviewer.md
│   │   ├── oma-validator.md
│   │   ├── oma-test-fixer.md
│   │   └── oma-strategy-refiner.md
│   ├── skills/         # 파이프라인 skill (oma-start, oma-analyze, ...)
│   └── settings.json   # oma CLI Bash 허용 등
├── src/
│   ├── cli/            # 신규: oma 단일 CLI (서브커맨드: analyze/db/merge/test-exec/report)
│   ├── core/           # 유지: state_manager, sql_executor, tc_generator, html_report 등
│   ├── reference/      # 유지: oracle_to_{postgresql,mysql}_rules.md (subagent가 읽음)
│   └── utils/          # 유지: project_paths, db_utils
└── output/             # 기존 동일: oma_control.db, transform/, merge/, reports/
```

### 제거 대상

- `src/agents/` (8개 Strands agent 전체)
- `src/mcp_server/` (18 tools — CC가 직접 오케스트레이터이므로 불필요)
- `src/run_*.py` (러너 전체)
- `strands-agents` 의존성 (pyproject.toml)
- Kiro 관련 symlink(`.kiro/`), 다중 CLI 호환 구조

### 자산 이식

- 기존 `src/agents/*/prompt.md`의 변환 규칙, SELF-CHECK 체크리스트, 리뷰 관점 정의는
  `.claude/agents/*.md` subagent 정의로 이식
- 2-Tier 룰 시스템 유지: Tier 1 static rules (`src/reference/`) + Tier 2 dynamic strategy
  (`output/strategy/transform_strategy.md`)
- SQLite 스키마, history 테이블, HTML 리포트 — 데이터 모델 변경 없음

## 6. 에러 처리와 신뢰성

- **Subagent 출력 파싱 제거**: subagent가 JSON을 출력하고 메인이 파싱하는 방식 대신,
  subagent가 `oma db update ...`를 직접 호출해 결과를 DB에 기록한다. 메인 세션은
  DB 조회로만 결과를 집계한다. 기존 "출력 파싱 깨짐" 문제의 구조적 해소.
- **CLI 입력 검증**: `oma db`는 파라미터화 쿼리만 사용 (f-string SQL 금지 규칙 유지).
- **중단/재개**: 모든 상태가 DB에 있으므로 세션 종료 후에도 `/oma:start`가 DB 상태를
  읽고 이어서 진행한다.
- **Subagent 실패**: dispatch 결과가 비거나 DB에 기록이 없으면 메인 세션이 해당 배치를
  실패로 간주하고 체크포인트에서 재시도 옵션 제시.

## 7. 테스트 전략

- **유닛**: 신규 `src/cli/` 서브커맨드는 pytest로 검증 (DB fixture 사용)
- **E2E**: `example/` (3 mapper, 44 SQL)을 기준 케이스로 전체 파이프라인 실행
- **회귀 기준**: 기존 Strands 파이프라인의 example 변환 결과와 산출물 비교

## 8. 마이그레이션 순서

1. 이 브랜치에서 `src/cli/` + `.claude/agents/` + `.claude/skills/` 신규 구축
2. example E2E 통과 확인
3. 구 코드 삭제 커밋 (`run_*.py`, `src/agents/`, `src/mcp_server/`, strands 의존성)
4. README, AGENT.md, CLAUDE.md 재작성 (CC 전용 사용법)
5. Kiro symlink·문서 정리
