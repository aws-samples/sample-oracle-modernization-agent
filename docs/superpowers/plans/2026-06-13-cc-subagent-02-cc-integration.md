# Plan 02/03: CC 통합 — Subagents + Skills + Settings

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Claude Code가 오케스트레이터가 되도록 `.claude/agents/`(5 subagent), `.claude/skills/`(파이프라인 skill), `settings.json`을 구축한다.

**Architecture:** 메인 세션이 skill 절차에 따라 `oma` CLI로 상태를 조회하고, mapper 배치를 subagent로 병렬 dispatch한다. subagent는 룰 파일을 Read로 로드 → LLM 변환/리뷰/검증 수행 → 결과를 `oma db` CLI로 기록한다. 체크포인트마다 AskUserQuestion으로 분기.

**Tech Stack:** Claude Code subagents (`.claude/agents/*.md`), 프로젝트 skills (`.claude/skills/*/SKILL.md`), 기존 prompt 자산 (`src/agents/*/prompt.md`) 이식

**전제:** Plan 01 완료 (`oma` CLI 동작). 스펙: `docs/superpowers/specs/2026-06-13-cc-subagent-architecture-design.md`

---

## 공통 규칙

- 이 Plan의 산출물은 markdown/JSON 파일 — pytest 불가. 검증은 (1) 파일 lint(frontmatter 필수 키), (2) example 기반 수동 smoke로 수행
- subagent 정의의 본문은 기존 `src/agents/*/prompt.md`를 **이식**하되, tool 호출 부분을 CLI 호출로 치환. 변환 규칙·체크리스트 본문은 절대 요약/생략하지 말 것 (production feedback으로 다듬어진 자산)
- `{{TARGET_DB}}` placeholder는 그대로 둔다 — dispatch prompt에서 메인 세션이 target DB를 명시하므로 subagent는 "dispatch prompt에 명시된 target DB"를 따른다는 안내로 대체
- 모든 subagent 공통 패턴: ① 룰 로드 (Read) → ② 작업 (LLM) → ③ 기록 (`oma db ...`) → ④ 최종 응답은 한 줄 요약만 (파싱하지 않으므로)

### Subagent가 룰을 로드하는 방법 (모든 정의에 포함)

```markdown
## 시작 절차 (작업 전 필수)

1. `oma db get-property TARGET_DBMS_TYPE` 실행 → 타겟 DB 확인 (postgresql | mysql)
2. Read: `src/reference/oracle_to_{타겟}_rules.md` — General Conversion Rules
3. Read: `output/strategy/transform_strategy.md` — Project-Specific Rules (없으면 생략)
4. 이후 모든 판단은 General Rules + Project Rules를 기준으로 한다. 충돌 시 Project Rules 우선.
```

---

### Task 1: 디렉토리 + settings.json

**Files:**
- Create: `.claude/settings.json`
- Create: `.claude/agents/` `.claude/skills/` 디렉토리

- [ ] **Step 1: settings.json 작성**

`.claude/settings.json` (기존 `.claude/settings.local.json`은 건드리지 않음):

```json
{
  "permissions": {
    "allow": [
      "Bash(oma:*)",
      "Bash(uv run oma:*)",
      "Bash(.venv/bin/oma:*)",
      "Read(./src/reference/**)",
      "Read(./output/**)",
      "Write(./output/**)"
    ]
  },
  "env": {
    "PYTHONPATH": "src"
  }
}
```

- [ ] **Step 2: 디렉토리 생성 + Commit**

```bash
mkdir -p .claude/agents .claude/skills
git add .claude/settings.json
git commit -m "feat(cc): settings.json — oma CLI permissions"
```

---

### Task 2: oma-transformer subagent

**Files:**
- Create: `.claude/agents/oma-transformer.md`
- Source: `src/agents/sql_transform/prompt.md` (이식 원본)

- [ ] **Step 1: 정의 파일 작성**

`.claude/agents/oma-transformer.md` — frontmatter:

```markdown
---
name: oma-transformer
description: >
  Oracle SQL을 Target DB(PostgreSQL/MySQL)로 변환하는 작업자.
  mapper 배치(sql_id 목록)를 받아 각 SQL을 변환하고 oma CLI로 결과를 기록한다.
  메인 세션의 OMA 파이프라인 Transform/재변환 단계에서만 dispatch된다.
tools: Read, Write, Bash
---
```

본문 구성 (순서대로):

1. **시작 절차** 섹션 — 위 공통 규칙의 4단계 그대로
2. **입출력 계약** 섹션 (신규 작성):

```markdown
## 입출력 계약

dispatch prompt에는 다음이 명시된다:
- `mapper_file`: 대상 mapper (예: `UserMapper.xml`)
- `sql_ids`: 변환할 SQL ID 목록
- 재변환인 경우: SQL별 리뷰 피드백 (이 이슈를 반드시 수정)

각 sql_id 처리 절차:
1. `oma db read-sql <mapper_file> <sql_id> --json` → 원본 Oracle SQL 획득
2. 변환 수행 (룰 적용, 아래 SELF-CHECK 통과 필수)
3. 변환 결과를 임시 파일에 Write (예: `output/tmp/<mapper_stem>_<sql_id>.sql`)
   — SQL을 CLI 인자로 직접 넘기지 말 것 (shell escaping 문제)
4. `oma db save-transform <mapper_file> <sql_id> --sql-file <임시파일> --notes "<적용한 변환 요약>"`
5. exit code 0 확인. 실패 시 stderr 내용을 보고 1회 재시도, 그래도 실패면 해당 SQL은 건너뛰고 계속

모든 sql_id 처리 후 최종 응답은 딱 한 줄:
`done: <성공 수>/<전체 수> (failed: <실패한 sql_id들 또는 none>)`
SQL 본문이나 변환 설명을 응답에 포함하지 말 것 — 결과는 모두 DB에 있다.
```

3. **변환 규칙 본문** — `src/agents/sql_transform/prompt.md`의 다음 섹션을 그대로 복사:
   - `## ABSOLUTE RULES` 전체 (PRESERVE 목록, PKG_* flatten, CDATA, XML escaping 포함)
   - `### Step 4d: SELF-CHECK` 전체 체크리스트 (단, "convert_sql() 호출 전" 표현을 "save-transform 호출 전"으로 치환)
   - `## Handling resultMap / sql fragments` 전체
   - `## CRITICAL Rules` 전체 (tool 이름 치환: convert_sql → oma db save-transform)
   - 기존 `## Available Tools`/`## Workflow` 섹션은 복사하지 **않음** (입출력 계약이 대체)

- [ ] **Step 2: frontmatter lint**

Run: `python3 -c "
import pathlib, sys
t = pathlib.Path('.claude/agents/oma-transformer.md').read_text()
assert t.startswith('---'), 'no frontmatter'
fm = t.split('---')[1]
for key in ('name:', 'description:', 'tools:'):
    assert key in fm, f'missing {key}'
assert 'SELF-CHECK' in t and 'ABSOLUTE RULES' in t, 'rules body missing'
assert 'save-transform' in t, 'CLI contract missing'
assert 'convert_sql(' not in t, 'stale strands tool reference'
print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .claude/agents/oma-transformer.md
git commit -m "feat(cc): oma-transformer subagent — ported transform rules + CLI contract"
```

---

### Task 3: oma-reviewer subagent

기존 다관점(Syntax + Equivalence 병렬 + Facilitator) 구조를 단일 reviewer가 2-pass로 수행하는 구조로 통합 (스펙 결정사항).

**Files:**
- Create: `.claude/agents/oma-reviewer.md`
- Source: `src/agents/sql_review/prompt.md` + `src/agents/sql_review/perspectives.py`의 관점 정의

- [ ] **Step 1: perspectives.py에서 Equivalence 관점 프롬프트 확인**

Run: `grep -n "equivalence\|EQUIVALENCE" src/agents/sql_review/perspectives.py | head -20`

perspectives.py 내 Equivalence agent의 시스템 프롬프트 텍스트를 찾아 Step 2에서 본문에 포함한다.

- [ ] **Step 2: 정의 파일 작성**

`.claude/agents/oma-reviewer.md`:

```markdown
---
name: oma-reviewer
description: >
  변환된 SQL의 룰 준수(Syntax)와 기능 동등성(Equivalence)을 2-pass로 검토하는 리뷰어.
  위반을 보고만 하고 수정하지 않는다. OMA 파이프라인 Review 단계에서만 dispatch된다.
tools: Read, Bash
---
```

본문 구성:

1. **시작 절차** (공통 4단계)
2. **입출력 계약**:

```markdown
## 입출력 계약

dispatch prompt: `mapper_file` + `sql_ids` 목록.

각 sql_id 처리 절차:
1. `oma db read-sql <mapper_file> <sql_id> --json` → 원본 Oracle SQL
2. 변환 파일 Read: `oma db pending`이 아닌 transform 파일 경로는
   `output/xmls/transform/<mapper_stem>/<sql_id>.xml` (Read tool로 직접 읽기)
3. Pass 1 — Syntax 리뷰 (아래 Review Checklist 전체)
4. Pass 2 — Equivalence 리뷰 (아래 Equivalence Checklist 전체)
5. 판정 결정:
   - CRITICAL 이슈 1개 이상 → FAIL
   - WARNING만 있음 → PASS_WITH_WARNINGS
   - 이슈 없음 → PASS
6. 피드백 JSON을 임시 파일에 Write:
   `{"result": "...", "issues": [{"severity": "CRITICAL|WARNING", "description": "..."}], "feedback": "재변환 시 정확히 무엇을 고쳐야 하는지"}`
7. `oma db set-reviewed <mapper_file> <sql_id> --result <판정> --feedback-file <임시파일>`

최종 응답 한 줄: `done: PASS=<n> WARN=<n> FAIL=<n>`
```

3. **Review Checklist** — `src/agents/sql_review/prompt.md`의 Phase 1/2/3/4 체크리스트 전체 복사 (tool 표 제외)
4. **Equivalence Checklist** — `src/agents/sql_validate/prompt.md`의 "Functional Equivalence Checklist" 중 **결과가 달라지는 CRITICAL 패턴** 섹션 복사 (Oracle `''`=NULL, DECODE NULL 매칭, outer join WHERE, 암시적 형변환). Validate가 더 깊게 보므로 여기서는 명백한 동등성 깨짐만 CRITICAL로 분류
5. **severity 기준** — 기존 prompt.md의 severity 정의 복사 (CRITICAL = 결과 상이/구문 오류, WARNING = 스타일/잠재 위험)

- [ ] **Step 3: lint + Commit**

Run: 위 Task 2 Step 2와 동일 패턴으로 (`name:`, `set-reviewed`, `Review Checklist`, `Equivalence` 존재 확인)

```bash
git add .claude/agents/oma-reviewer.md
git commit -m "feat(cc): oma-reviewer subagent — unified syntax+equivalence 2-pass review"
```

---

### Task 4: oma-validator subagent

**Files:**
- Create: `.claude/agents/oma-validator.md`
- Source: `src/agents/sql_validate/prompt.md`

- [ ] **Step 1: 정의 파일 작성**

frontmatter (`name: oma-validator`, `tools: Read, Write, Bash`), 본문:

1. **시작 절차** (공통)
2. **입출력 계약** — reviewer와 동일 패턴이되 결과 기록이 다름:

```markdown
각 sql_id 처리 절차:
1. 원본/변환 SQL 읽기 (reviewer와 동일)
2. Functional Equivalence Checklist 전체 검증
3. PASS → `oma db set-validated <mapper_file> <sql_id> --result PASS`
4. FAIL이지만 직접 수정 가능 → 수정한 SQL을 임시 파일에 Write 후:
   a. `oma db save-transform <mapper_file> <sql_id> --sql-file <파일> --step validate --notes "FIXED: <사유>"`
   b. `oma db set-validated <mapper_file> <sql_id> --result PASS --notes "FIXED: <사유>"`
5. FAIL이고 수정 불확실(원본 의도 모호, 데이터 의존) → `--result FAIL --notes "<사유>"`
   — 메인 세션이 체크포인트에서 사용자에게 분기를 물을 수 있도록 사유를 구체적으로

최종 응답 한 줄: `done: PASS=<n> FIXED=<n> FAIL=<n>`
```

3. `src/agents/sql_validate/prompt.md`의 Functional Equivalence Checklist 전체 복사 (tool 섹션 제외, convert_sql 언급은 save-transform으로 치환)

- [ ] **Step 2: lint + Commit**

```bash
git add .claude/agents/oma-validator.md
git commit -m "feat(cc): oma-validator subagent"
```

---

### Task 5: oma-test-fixer subagent

**Files:**
- Create: `.claude/agents/oma-test-fixer.md`
- Source: `src/agents/sql_test/prompt.md` + `src/run_sql_test.py`의 Phase 2 로직

- [ ] **Step 1: 정의 파일 작성**

frontmatter (`name: oma-test-fixer`, `tools: Read, Write, Bash`), 본문:

1. **시작 절차** (공통)
2. **입출력 계약**:

```markdown
## 입출력 계약

dispatch prompt: `mapper_file` + 실패 목록 `[{sql_id, phase, error}]`.

각 실패 SQL 처리 절차 (최대 3회 시도):
1. `oma db read-sql`로 원본, Read로 변환 파일 확인
2. 에러 메시지 분석 → 수정 SQL 작성
3. 임시 파일 Write → `oma db save-transform <mapper> <sql_id> --sql-file <f> --step test --notes "fix: <사유>"`
4. 검증: `oma test-exec --only "<mapper>:<sql_id>" --json` 실행 → 통과 확인
5. 통과 → `oma db set-tested <mapper> <sql_id> --result FIXED --notes "<수정 요약>"`
6. 3회 실패 → `oma db set-tested <mapper> <sql_id> --result FAIL --notes "<최종 에러>"`

인프라성 에러(missing table/function, 권한)는 수정 대상이 아님:
→ `oma db set-tested <mapper> <sql_id> --result SKIP --notes "infra: <사유>"`

모든 SQL 처리 후: `oma merge --mapper <mapper_file>` 실행 (재병합).
최종 응답 한 줄: `done: FIXED=<n> SKIP=<n> FAIL=<n>`
```

3. `src/agents/sql_test/prompt.md`의 수정 가이드 본문 복사 + 변환 규칙 준수 안내 (transformer의 ABSOLUTE RULES를 동일하게 따른다는 1줄 + 핵심 PRESERVE 항목 요약 5줄)

- [ ] **Step 2: lint + Commit**

```bash
git add .claude/agents/oma-test-fixer.md
git commit -m "feat(cc): oma-test-fixer subagent — Phase 2 fix loop via CLI"
```

---

### Task 6: oma-strategy-refiner subagent

**Files:**
- Create: `.claude/agents/oma-strategy-refiner.md`
- Source: `src/agents/strategy_refine/prompt.md`

- [ ] **Step 1: 정의 파일 작성**

frontmatter (`name: oma-strategy-refiner`, `tools: Read, Write, Bash`), 본문:

```markdown
## 입출력 계약

dispatch 시점: Review round 2+ 에서 지속 실패가 있을 때, 재변환 전에 호출된다.

절차:
1. `oma db feedback-patterns` 실행 → 실패 피드백 덤프 수집
2. Read: `output/strategy/transform_strategy.md` (현재 전략)
3. 실패 패턴을 분석해 Before/After 예시 형태의 규칙으로 정리
4. 기존 전략 파일에 새 규칙을 추가한 전체 내용을 Write로 저장
   (`output/strategy/transform_strategy.md` 덮어쓰기)

규칙 작성 기준은 아래 원본 가이드를 따른다.
최종 응답 한 줄: `done: <추가한 규칙 수> patterns added`
```

이어서 `src/agents/strategy_refine/prompt.md` 본문 복사 (패턴 추출 기준, Before/After 형식, 중복 방지/압축 가이드).

- [ ] **Step 2: lint + 5개 일괄 검증 + Commit**

Run: `python3 -c "
import pathlib
agents = ['oma-transformer', 'oma-reviewer', 'oma-validator', 'oma-test-fixer', 'oma-strategy-refiner']
for a in agents:
    t = pathlib.Path(f'.claude/agents/{a}.md').read_text()
    assert t.startswith('---') and f'name: {a}' in t, a
    assert 'oma db' in t or 'oma ' in t, f'{a}: no CLI usage'
print('all 5 OK')"`
Expected: `all 5 OK`

```bash
git add .claude/agents/oma-strategy-refiner.md
git commit -m "feat(cc): oma-strategy-refiner subagent"
```

---

### Task 7: 파이프라인 skill — oma-pipeline (오케스트레이션 절차)

단계별 skill을 잘게 쪼개는 대신, 파이프라인 전체 절차를 담은 skill 1개 + 진입 명령용 얇은 skill들로 구성한다. 절차 SSOT는 oma-pipeline 하나.

**Files:**
- Create: `.claude/skills/oma-pipeline/SKILL.md`

- [ ] **Step 1: SKILL.md 작성**

`.claude/skills/oma-pipeline/SKILL.md`:

````markdown
---
name: oma-pipeline
description: >
  Use when the user wants to run/continue the OMA SQL transform pipeline
  (Oracle→PostgreSQL/MySQL MyBatis mapper conversion), check its status,
  or handle a specific step: analyze, transform, review, validate, merge, test.
---

# OMA Pipeline Orchestration

너(메인 세션)는 OMA 파이프라인의 오케스트레이터다. LLM 작업은 subagent에게,
결정적 작업은 `oma` CLI에 위임한다. 직접 SQL을 변환하지 마라.

## 불변 원칙

1. **상태의 SSOT는 DB다.** 진행 판단은 항상 `oma status --json`으로 시작한다.
2. **체크포인트 승인형.** 각 단계가 끝나면 결과를 요약하고 AskUserQuestion으로
   다음 행동을 묻는다. 사용자 승인 없이 다음 단계로 자동 진행하지 않는다.
3. **병렬 dispatch는 최대 5개.** 배치가 더 많으면 5개 단위로 나눠 순차 dispatch.
4. **subagent 응답은 파싱하지 않는다.** dispatch 후 결과 집계는 `oma status --json`
   재조회로 한다. subagent의 한 줄 응답은 참고용일 뿐이다.

## 단계별 절차

### 0. Setup
`oma status` 실행이 "DB not found"면: 사용자에게 소스 경로·타겟 DB를
AskUserQuestion으로 물은 뒤 `oma setup --non-interactive --source <path> --target-db <db>`.
DB 접속 정보는 Test 단계 전까지 불필요하다고 안내.

### 1. Analyze
```
oma analyze --json
```
완료 후 요약 표시 (mapper 수, SQL 수, 메타데이터 상태) +
`output/strategy/transform_strategy.md` 초안 존재 안내.
체크포인트: [전체 변환 진행 / 샘플 N건만 / 전략 파일 검토·수정 / 중단]

### 2. Transform
```
oma db pending --step transform --json
```
batches 배열의 각 항목마다 oma-transformer를 dispatch (병렬, 최대 5):

> dispatch prompt 템플릿:
> "mapper_file: {mapper_file} (part {part}/{parts})
>  sql_ids: {sql_ids 쉼표 목록}
>  target DB: {TARGET_DBMS_TYPE 값}
>  위 SQL들을 변환하고 oma db save-transform으로 기록하라."

전체 완료 후 `oma status --json`으로 집계.
체크포인트: 성공/실패 요약 → [Review 진행 / 실패 건 재시도 / 중단]
실패 재시도: `oma db pending --step transform --only "<실패 목록>"`으로 배치 재생성.

### 3. Review (최대 3 라운드)
```
oma db pending --step review --json
```
각 배치를 oma-reviewer로 dispatch (transform과 동일 패턴).
라운드 종료 후 `oma status --json`의 review_failed 확인:

- review_failed == 0 → Validate로
- review_failed > 0 → 체크포인트: FAIL 목록 + 사유 요약 표시
  [자동 재변환 / 해당 SQL 건너뛰기 / 수동 확인]
  - 자동 재변환 선택 시:
    a. 라운드 2 이상이면 먼저 oma-strategy-refiner를 dispatch (1개, 직렬)
    b. FAIL 건의 review_result 피드백을 모아 oma-transformer dispatch
       (dispatch prompt에 SQL별 피드백 포함)
    c. `oma db reset --step review --only "<해당 건>"` 후 재리뷰
  - 3라운드 후에도 FAIL → 사용자에게 수동 처리 목록으로 보고

### 4. Validate
```
oma db pending --step validate --json
```
oma-validator dispatch (동일 패턴).
체크포인트: FAIL 건(validator가 수정 불가 판정) 목록 + 사유 →
건별 또는 일괄 [승인하고 진행 / 재변환 지시 / 중단]

### 5. Merge
```
oma merge --json
```
결정적 작업 — subagent 불필요. 완료 후 merged/skipped 요약.
체크포인트: [Test 진행 / 특정 mapper diff 확인 / 종료(Test 생략)]
diff 확인 요청 시: origin/과 merge/의 해당 파일을 Read해 비교 요약.

### 6. Test
```
oma test-exec --json
```
failures 배열이 비면 완료. 실패가 있으면 체크포인트:
[oma-test-fixer로 자동 수정 / SKIP 처리 / 수동]
- 자동 수정: mapper별로 failures를 묶어 oma-test-fixer dispatch
- SKIP: `oma db set-tested <m> <s> --result SKIP --notes "<사용자 사유>"`
수정 후 `oma test-exec --only "..."`로 재검증.

### 7. 종료
`oma report` 실행 → 사용자에게 안내:
- 최종 mapper: `output/xmls/merge/`
- HTML 리포트: `output/reports/oma_report.html`

## 중단/재개

세션이 끊겨도 상태는 DB에 있다. 사용자가 돌아오면 `oma status --json`으로
현재 위치를 파악하고 해당 단계의 체크포인트부터 재개한다.
````

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/oma-pipeline/
git commit -m "feat(cc): oma-pipeline skill — orchestration procedure SSOT"
```

---

### Task 8: 진입 skill — oma-start / oma-status

**Files:**
- Create: `.claude/skills/oma-start/SKILL.md`
- Create: `.claude/skills/oma-status/SKILL.md`

- [ ] **Step 1: 두 skill 작성**

`.claude/skills/oma-start/SKILL.md`:

```markdown
---
name: oma-start
description: >
  Use when the user says "start", "시작", "/oma:start", "변환 시작",
  or asks to begin/continue the Oracle SQL transformation project.
---

# OMA Start

1. oma-pipeline skill을 먼저 로드하라 (Skill tool) — 전체 절차가 거기 있다.
2. `oma status --json` 실행.
3. 결과에 따라:
   - DB 없음 → Setup부터 (oma-pipeline §0)
   - 진행 중 → 현재 단계 요약 + 해당 단계 체크포인트 제시
   - 전부 완료 → 최종 산출물 안내 (oma-pipeline §7)
```

`.claude/skills/oma-status/SKILL.md`:

```markdown
---
name: oma-status
description: >
  Use when the user asks about OMA pipeline progress: "status", "상태",
  "어디까지 했어", "진행 상황", "/oma:status".
---

# OMA Status

1. `oma status --json` 실행.
2. 단계별 카운트를 표로 요약 (extracted/transformed/reviewed/validated/merged/tested).
3. 실패 카운트(review_failed, validate_failed, test_failed)가 있으면 강조하고
   다음 행동 옵션을 제시한다. 진행 판단 절차는 oma-pipeline skill 참조.
```

- [ ] **Step 2: skill frontmatter 일괄 lint**

Run: `python3 -c "
import pathlib
for p in pathlib.Path('.claude/skills').rglob('SKILL.md'):
    t = p.read_text()
    assert t.startswith('---') and 'name:' in t and 'description:' in t, p
print('skills OK')"`
Expected: `skills OK`

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/
git commit -m "feat(cc): oma-start / oma-status entry skills"
```

---

### Task 9: Smoke 검증 — example 1개 mapper 수동 dispatch

CC 구조가 실제로 동작하는지 example 데이터로 확인한다. 이 Task는 **이 repo의 CC 세션에서 사람(또는 메인 세션)이 직접 수행**하는 검증 절차다.

- [ ] **Step 1: example 데이터로 setup + analyze**

```bash
rm -rf /tmp/oma-smoke && mkdir -p /tmp/oma-smoke
OMA_OUTPUT_DIR=/tmp/oma-smoke uv run oma setup --non-interactive \
  --source "$(pwd)/example/src" --target-db postgresql
OMA_OUTPUT_DIR=/tmp/oma-smoke uv run oma analyze --json
```
Expected: JSON에 mappers=3, sqls=44 (example 기준)

- [ ] **Step 2: pending 배치 확인**

```bash
OMA_OUTPUT_DIR=/tmp/oma-smoke uv run oma db pending --step transform --json
```
Expected: batches 비어있지 않음, 15건 초과 mapper는 part/parts로 분할됨

- [ ] **Step 3: transformer subagent 1개 dispatch (CC 세션에서)**

메인 세션에서 Agent tool로 oma-transformer를 1개 배치에 대해 dispatch.
dispatch prompt에 `OMA_OUTPUT_DIR=/tmp/oma-smoke` 환경에서 CLI를 실행하라는 지시 포함.

검증:
```bash
OMA_OUTPUT_DIR=/tmp/oma-smoke uv run oma status --json
```
Expected: transformed 카운트가 해당 배치 크기만큼 증가, transform 파일 생성됨

- [ ] **Step 4: 발견된 마찰 기록**

dispatch 과정에서 발견한 문제(권한 프롬프트, 경로 혼동, CLI 사용법 오해 등)를
subagent 정의/skill에 반영해 수정 커밋.

```bash
git add -A .claude/
git commit -m "fix(cc): smoke test feedback — subagent/skill adjustments"
```

---

## Plan 02 완료 기준

- `.claude/agents/` 5개 정의 + lint 통과
- `.claude/skills/` 3개 (oma-pipeline, oma-start, oma-status) + lint 통과
- example smoke: transformer subagent가 CLI만으로 변환 1배치 완료 (출력 파싱 0회)
- 다음 단계: Plan 03 (`docs/superpowers/plans/2026-06-13-cc-subagent-03-cleanup.md`)
