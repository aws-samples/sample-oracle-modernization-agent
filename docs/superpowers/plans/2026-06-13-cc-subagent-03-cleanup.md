# Plan 03/03: 레거시 제거 + 문서 + E2E

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) 구문으로 추적.

**Goal:** Strands 기반 구 코드와 Kiro 호환 구조를 제거하고, 문서를 CC 전용 사용법으로 재작성하며, example E2E로 전체 파이프라인을 검증한다.

**Architecture:** Plan 01/02 산출물이 모두 동작하는 상태에서 시작. 삭제 → 의존성 정리 → 문서 → E2E 순서. 삭제는 grep으로 잔존 참조 0건을 확인하며 진행.

**전제:** Plan 01, 02 완료. 스펙: `docs/superpowers/specs/2026-06-13-cc-subagent-architecture-design.md`

---

### Task 1: 잔존 의존 확인 후 구 코드 삭제

**Files:**
- Delete: `src/agents/` 전체, `src/mcp_server/` 전체, `src/run_*.py` 전체, `src/migrate_mapper_key.py`
- Delete: `src/skills/` (구 Strands용 skill — `.claude/skills/`가 대체)
- Delete: `.kiro/` 전체
- Modify: `src/core/progress.py` 사용처 확인 후 삭제 여부 결정

- [ ] **Step 1: 신규 코드의 구 코드 의존 0건 확인**

Run: `grep -rn "from agents\.\|import agents\.\|from mcp_server\|run_sql_\|run_source_\|run_orchestrator\|run_setup" src/cli/ src/core/ src/utils/ tests/ --include="*.py" | grep -v __pycache__`
Expected: 출력 없음. 출력이 있으면 해당 참조를 먼저 제거(이식)하고 진행.

- [ ] **Step 2: 삭제 실행**

```bash
git rm -r src/agents src/mcp_server src/skills .kiro
git rm src/run_orchestrator.py src/run_setup.py src/run_source_analyzer.py \
       src/run_sql_merge.py src/run_sql_review.py src/run_sql_test.py \
       src/run_sql_transform.py src/run_sql_validate.py src/run_strategy.py \
       src/migrate_mapper_key.py
```

- [ ] **Step 3: core 모듈 dead code 정리**

Run: `grep -rn "core.progress\|core\.display" src/ tests/ --include="*.py" | grep -v __pycache__ | grep -v "src/core/progress.py\|src/core/display.py"`

- `core/progress.py` (drain/emit queue): 사용처가 없으면 `git rm src/core/progress.py`
- `core/display.py` (Rich UI): `oma` CLI가 stderr 텍스트만 쓰므로 사용처가 없으면 `git rm src/core/display.py`. 사용처가 있으면 유지
- `core/config.py`: 동일 기준으로 판단

- [ ] **Step 4: 테스트 전체 회귀**

Run: `PYTHONPATH=src pytest tests/ -v`
Expected: 전체 PASS

Run: `grep -rn "strands" src/ tests/ --include="*.py" | grep -v __pycache__`
Expected: 출력 없음

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor!: remove Strands pipeline (agents/, mcp_server/, run_*.py) and Kiro compat

LLM 작업은 .claude/agents/ subagent가, 결정적 인프라는 oma CLI가 대체.
BREAKING CHANGE: run_*.py 진입점 제거 — 사용법은 README 참조."
```

---

### Task 2: 의존성 정리 (pyproject)

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock` (uv sync로 갱신)

- [ ] **Step 1: strands-agents, boto3, rich 제거**

`pyproject.toml`의 dependencies를 다음으로 교체:

```toml
dependencies = [
    "defusedxml>=0.7.1",
    "sqlalchemy>=2.0.0",
]
```

주의: 제거 전 확인 — `grep -rn "import rich\|from rich\|import boto3\|from botocore" src/ --include="*.py" | grep -v __pycache__`
출력이 있으면 해당 모듈을 stderr print로 교체 후 제거. (Plan 01에서 display 의존을 안 남겼다면 출력 없음)

- [ ] **Step 2: sync + 전체 테스트**

Run: `uv sync && PYTHONPATH=src pytest tests/ -v && uv run oma --help`
Expected: 테스트 전체 PASS, oma 서브커맨드 7개 표시

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: drop strands-agents/boto3/rich — CC subagents replace Bedrock calls"
```

---

### Task 3: example 디렉토리 CC 전용으로 갱신

**Files:**
- Modify: `example/setup.sh`, `example/run.sh`, `example/README.md`
- Delete: `example/skills`, `example/AGENT.md`, `example/CLAUDE.md` (Kiro/구 구조 잔재 — 내용 확인 후)

- [ ] **Step 1: 현재 example 스크립트 확인**

Run: `cat example/setup.sh example/run.sh | head -60`

기존 스크립트가 무엇을 하는지 파악 (symlink 생성, kiro-cli 호출 등).

- [ ] **Step 2: setup.sh 재작성**

CC 전용으로 교체 — 핵심 동작: example 소스로 `oma setup` 비대화식 실행:

```bash
#!/usr/bin/env bash
# OMA example setup — CC subagent 구조용
set -euo pipefail
cd "$(dirname "$0")/.."

uv sync
export OMA_OUTPUT_DIR="$(pwd)/example/output"
uv run oma setup --non-interactive \
  --source "$(pwd)/example/src" --target-db postgresql
echo ""
echo "Setup 완료. 다음 단계:"
echo "  cd $(pwd) && claude"
echo "  Claude Code에서: '변환 시작' 또는 /oma:start"
echo "  (OMA_OUTPUT_DIR=example/output 환경변수를 세션에서 유지하세요)"
```

`run.sh`는 `claude` 실행 안내만 남기거나 삭제 (kiro fallback 제거).

- [ ] **Step 3: example/README.md 재작성**

내용: example 구성(3 mapper, 44 SQL) 소개 → setup.sh 실행 → CC에서 `/oma:start` → 체크포인트 흐름 안내 → 결과물 위치. 분량 50줄 내외.

- [ ] **Step 4: Commit**

```bash
git add -A example/
git commit -m "docs(example): CC subagent 구조 기준으로 example 재작성"
```

---

### Task 4: 문서 재작성 — README, CLAUDE.md, AGENT.md

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md` (루트)
- Delete: `src/AGENT.md`, `src/CLAUDE.md` (src 워크스페이스 분리 구조 폐기 — 루트로 통합)
- Modify: `.gitignore` (`.claude/` 예외 확인)

- [ ] **Step 1: .gitignore 확인**

Run: `grep -n "claude\|kiro" .gitignore ~/.gitignore 2>/dev/null`

`.claude/agents/`, `.claude/skills/`, `.claude/settings.json`이 커밋 가능해야 한다.
글로벌 gitignore가 `.claude/`를 막으면 `.gitignore`에 예외 추가:

```gitignore
!.claude/
!.claude/agents/
!.claude/agents/**
!.claude/skills/
!.claude/skills/**
!.claude/settings.json
.claude/settings.local.json
.claude/agent-memory/
```

Run: `git check-ignore -v .claude/agents/oma-transformer.md; echo "exit=$?"`
Expected: exit=1 (ignore 안 됨)

- [ ] **Step 2: README.md 재작성**

구조 (기존 README의 프로젝트 소개·아키텍처 다이어그램 톤 유지하되 사용법 전면 교체):

1. 프로젝트 소개 (OMA 서브모듈, Oracle→PG/MySQL MyBatis 변환) — 기존 유지
2. **요구사항**: Claude Code CLI, Python 3.11+, uv
3. **Quick Start**:
   ```bash
   git clone <repo> && cd application-sql-transform-assistant
   uv sync
   claude          # Claude Code 실행
   # 대화: "변환 시작" 또는 /oma:start
   ```
4. **아키텍처**: 스펙의 다이어그램 (CC 메인 세션 / 5 subagents / oma CLI / SQLite SSOT)
5. **파이프라인**: 7단계 + 체크포인트 표
6. **oma CLI 레퍼런스**: 서브커맨드 표 (status/db/analyze/merge/test-exec/report/setup)
7. **example**: `example/README.md` 링크
8. Data Model 섹션: 기존 내용 유지 (`docs/db-schema.md` 링크)

- [ ] **Step 3: 루트 CLAUDE.md 재작성**

새 구조 기준으로 전면 교체. 포함할 내용:

```markdown
# CLAUDE.md

## Project Overview
Application SQL Transform Agent — CC subagent 기반 Oracle→PostgreSQL/MySQL
MyBatis mapper 변환 도구. 메인 세션이 오케스트레이터, .claude/agents/의
5개 subagent가 LLM 작업자, src/cli/의 oma CLI가 결정적 인프라.

## 사용자가 변환 작업을 요청하면
oma-pipeline skill을 로드해 그 절차를 따른다. 직접 SQL을 변환하지 않는다.

## Setup & Commands
- uv sync && source .venv/bin/activate
- oma --help  (status/db/analyze/merge/test-exec/report/setup)
- 테스트: PYTHONPATH=src pytest tests/ -v
- E2E: example/setup.sh 후 CC에서 /oma:start

## Architecture
(스펙 §3 다이어그램 + 디렉토리 표 — src/cli, src/core, src/reference,
 .claude/agents, .claude/skills)

## Critical Coding Rules
- DB 접근: StateManager(ORM) 또는 sqlite3 파라미터화 쿼리. f-string SQL 금지
- mapper_file 조회는 utils/db_utils.query_by_mapper 사용
- XML 파싱은 defusedxml
- subagent 정의 수정 시: 변환 규칙 본문은 요약 금지 (production 자산)
- CLI 출력 규약: 기계용 JSON은 stdout(--json), 사람용은 stderr

## Environment Variables
| OMA_OUTPUT_DIR | 작업 디렉토리 | ./output/ |
| TARGET_DBMS_TYPE | postgresql/mysql | DB property |
(Oracle/PG/MySQL 접속 변수는 기존 표 유지. OMA_MODEL_ID 관련 행 삭제)
```

- [ ] **Step 4: src/AGENT.md, src/CLAUDE.md 삭제**

```bash
git rm src/AGENT.md src/CLAUDE.md
```

(다중 CLI SSOT 구조 폐기 — CC 전용이므로 루트 CLAUDE.md + skills가 SSOT)

- [ ] **Step 5: docs 스테일 문서 처리**

`docs/agents/*.md` (구 Strands 에이전트 설계 문서)는 삭제하지 않고 헤더에 1줄 추가:

```markdown
> ⚠️ DEPRECATED (2026-06-13): Strands 기반 구조의 설계 문서.
> 현행 아키텍처는 `docs/superpowers/specs/2026-06-13-cc-subagent-architecture-design.md` 참조.
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "docs: rewrite README/CLAUDE.md for CC subagent architecture; deprecate stale design docs"
```

---

### Task 5: E2E — example 전체 파이프라인

CC 세션에서 사람이 (또는 메인 세션이) 수행하는 최종 검증.

- [ ] **Step 1: 클린 상태에서 setup + analyze**

```bash
rm -rf example/output
./example/setup.sh
OMA_OUTPUT_DIR=$(pwd)/example/output uv run oma status --json
```
Expected: extracted=44, transformed=0

- [ ] **Step 2: CC 세션에서 파이프라인 실행**

`OMA_OUTPUT_DIR=$(pwd)/example/output claude` 로 세션 시작 → `/oma:start`:

체크리스트 (각 항목을 세션에서 확인):
- [ ] Analyze 체크포인트가 AskUserQuestion으로 표시됨
- [ ] Transform: 배치별 subagent 병렬 dispatch, 완료 후 transformed=44
- [ ] Review: dispatch 후 review_failed 건이 있으면 재변환 분기 동작
- [ ] Validate: 완료 후 validated=44
- [ ] Merge: merge/ 에 3개 XML 생성, diff 체크포인트 동작
- [ ] (DB 있으면) Test: Phase 0/1 실행, 실패 시 test-fixer 분기
- [ ] `oma report` → HTML 리포트 생성 확인

- [ ] **Step 3: 회귀 비교**

main 브랜치의 기존 변환 결과가 있다면 (또는 example의 알려진 정답과):

```bash
ls example/output/xmls/merge/**/*.xml
grep -c "COALESCE\|LEFT JOIN" example/output/xmls/merge/**/*.xml
grep -rn "NVL(\|DECODE(\|SYSDATE" example/output/xmls/merge/ || echo "no oracle syntax remains"
```
Expected: 마지막 grep이 "no oracle syntax remains"

- [ ] **Step 4: E2E 중 발견된 이슈 수정 + Commit**

발견된 마찰(skill 절차 모호, subagent 규칙 누락, CLI 버그)을 수정하고 개별 커밋.

```bash
git add -A
git commit -m "fix: E2E feedback — <구체 내용>"
```

---

### Task 6: 보안 스캔 + 마무리

- [ ] **Step 1: 보안 스캔**

```bash
uvx semgrep scan --config auto src/ --error 2>/dev/null | tail -20
uvx bandit -r src/ -ll 2>/dev/null | tail -20
```
Expected: Critical 0건. 발견 시 수정 (nosemgrep은 정당한 사유 + 윗줄 주석 규칙)

- [ ] **Step 2: 최종 전체 테스트**

```bash
PYTHONPATH=src pytest tests/ -v
uv run oma --help
```
Expected: 전체 PASS

- [ ] **Step 3: Commit + 브랜치 정리 안내**

```bash
git add -A && git commit -m "chore: security scan fixes + final cleanup" --allow-empty
git log --oneline main..HEAD | head -30
```

사용자에게 보고: 커밋 목록 요약 + main 머지 전 검토 포인트
(BREAKING: run_*.py 제거, Kiro 지원 종료, GitHub subtree 동기화 영향).
머지는 사용자 승인 후.

---

## Plan 03 완료 기준

- `grep -rn "strands" src/ tests/` 0건, `src/agents/`·`src/mcp_server/`·`run_*.py` 부재
- `uv sync` 후 의존성: defusedxml, sqlalchemy (+dev pytest)만
- example E2E: 44 SQL 전체가 CC 파이프라인으로 변환 완료, Oracle 구문 잔존 0건
- README/CLAUDE.md가 새 구조만 설명 (run_*.py 언급 0회)
- semgrep/bandit Critical 0건
