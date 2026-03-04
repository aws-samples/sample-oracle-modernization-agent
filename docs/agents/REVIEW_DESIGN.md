# SQL Review Agent Design Document

## 1. Agent 개요

### 1.1 목적
- **주요 목표**: Transform Agent가 변환한 PostgreSQL SQL이 General Rules를 준수하고 기능적으로 동등한지 체크
- **핵심 원칙**: 규칙 위반을 발견만 하고, 직접 수정하지 않음 (PASS/FAIL 판정만)
- **사용 시나리오**: Transform → **Review** → Validate 사이에서 품질 게이트 역할

### 1.2 입력/출력
```
입력: 원본 Oracle SQL + 변환된 PostgreSQL SQL + General Rules
출력: PASS/FAIL 판정 + 구체적 위반 사항 JSON (수정은 하지 않음)
```

### 1.3 왜 다관점 리뷰인가?

| 문제 | 단일 Agent 리뷰 | 다관점 리뷰 |
|------|----------------|------------|
| FAIL 피드백 | "rule violations" (모호) | "[Syntax] NVL(status, 'N') on line 5 not converted" (구체적) |
| 동일 실수 반복 | Transform이 무엇을 고칠지 모름 | 구체적 이슈 목록으로 정확한 재변환 |
| 기능 동등성 누락 | 구문만 체크, 의미 변화 놓침 | Equivalence Agent가 별도 체크 |
| FAIL 재발률 | 높음 (모호한 피드백) | 낮음 (구체적 수정 지침) |

---

## 2. 아키텍처

### 2.1 파이프라인 위치

```
Transform ──→ Review ──→ Validate ──→ Test
  변환         다관점 리뷰   의미 검증     DB 실행
               ↓ FAIL (구체적 피드백)
            Transform
             재호출 (최대 2라운드)
```

### 2.2 다관점 토의 구조

```
Transform 결과 →
  Step 1: 두 Agent가 독립적으로 리뷰 (ThreadPoolExecutor(2), 병렬)
    ├── Syntax Agent: PostgreSQL 문법 규칙 준수 체크 → JSON
    └── Equivalence Agent: Oracle 원본과 기능 동등성 체크 → JSON
  Step 2: Facilitator (Python 함수)가 결과 통합
    ├── 두 관점의 issues 병합
    ├── PASS/FAIL 판정 (하나라도 FAIL → FAIL)
    └── JSON 파싱 실패 시 → FAIL (안전 측)
  → set_reviewed() + review_result 컬럼에 피드백 JSON 저장
  → FAIL 시 구체적 수정 지침과 함께 재변환
```

**핵심 결정**: Facilitator는 LLM Agent가 아닌 **Python 함수**로 구현.
- 두 Agent의 JSON 출력을 병합하는 것은 결정론적 로직이므로 LLM 불필요
- LLM 호출 1회 절약 (비용/지연 감소)

### 2.3 디렉토리 구조

```
src/agents/sql_review/
├── agent.py                # Agent 팩토리 (단일 + 다관점 re-export)
├── perspectives.py         # 다관점 리뷰 핵심 로직 + Facilitator
├── prompt.md               # 기존 단일 Agent 프롬프트 (하위 호환)
├── prompt_syntax.md        # Syntax Agent 전용 프롬프트
├── prompt_equivalence.md   # Equivalence Agent 전용 프롬프트
├── README.md
└── tools/
    ├── __init__.py
    └── review_tools.py     # get_pending_reviews, set_reviewed

src/run_sql_review.py       # 병렬 실행 (8 workers), 다관점 리뷰, FAIL→재변환 루프
```

---

## 3. Prompt 설계

### 3.1 2-Block Caching (각 Perspective Agent)

```python
# perspectives.py - _load_prompt_with_rules()
system_blocks = [
    SystemContentBlock(text=perspective_prompt),  # prompt_syntax.md 또는 prompt_equivalence.md
    SystemContentBlock(cachePoint={"type": "default"}),
    SystemContentBlock(text=general_rules),       # oracle_to_postgresql_rules.md
    SystemContentBlock(cachePoint={"type": "default"}),
]
```

각 Perspective Agent는 집중된 프롬프트 + General Rules로 구성. Strategy 불필요.

### 3.2 Syntax Agent 프롬프트 (prompt_syntax.md)

- Phase 1~4 체크리스트 (구조, 문법, 함수 40+, 고급)
- Common WRONG conversions 패턴
- NOT a violation 목록
- **JSON 출력 형식 강제**: `{perspective: "syntax", results: {sql_id: {result, issues[], summary}}}`
- 도구: `read_sql_source`, `read_transform` (읽기 전용)

### 3.3 Equivalence Agent 프롬프트 (prompt_equivalence.md)

- Oracle/PG 동작 차이 ('' = NULL, DECODE NULL, OUTER JOIN + WHERE)
- 컬럼 출력, 데이터 필터링, JOIN 관계, 정렬, 서브쿼리, MyBatis 무결성
- **JSON 출력 형식 강제**: `{perspective: "equivalence", results: {sql_id: {result, issues[], summary}}}`
- 도구: `read_sql_source`, `read_transform` (읽기 전용)

### 3.4 판정 기준

```
Facilitator (_facilitate 함수):
  - 둘 다 PASS → PASS
  - 하나라도 FAIL → FAIL + 두 관점의 issues 병합
  - JSON 파싱 실패 → FAIL (안전 측) + 원본 텍스트를 피드백으로 저장
  - 각 SQL ID별 구체적 feedback 문자열 생성
```

---

## 4. Tools 설계

### 4.1 Perspective Agent 도구 (읽기 전용)

| Tool | 목적 | 사용 Agent |
|------|------|-----------|
| read_sql_source | 원본 Oracle SQL 읽기 | Syntax, Equivalence |
| read_transform | 변환된 PG SQL 읽기 | Syntax, Equivalence |

### 4.2 Runner 레벨 도구

| Tool | 목적 | 사용처 |
|------|------|-------|
| get_pending_reviews | 리뷰 대기 SQL 조회 | run_sql_review.py |
| set_reviewed | 리뷰 결과 + 피드백 저장 | run_sql_review.py |

### 4.3 set_reviewed 상세

```python
@tool
def set_reviewed(mapper_file, sql_id, result, violations="", review_feedback=""):
    """Save review result with detailed feedback.

    - reviewed 컬럼: 'Y' (PASS) or 'F' (FAIL)
    - review_result 컬럼: 상세 피드백 JSON (재변환 시 활용)
    """
```

---

## 5. 실행 스크립트 (run_sql_review.py)

### 5.1 review_mapper() — 다관점 리뷰

```python
from agents.sql_review.perspectives import run_multi_perspective_review

# 기존: 단일 Agent 호출
# 변경: 다관점 리뷰 (Syntax + Equivalence 병렬)
result = run_multi_perspective_review(mapper_file, ids_str)

# 결과를 SQL ID별로 처리하여 set_reviewed() 호출
for sql_id in group:
    sql_result = result['per_sql'][sql_id]
    set_reviewed(mapper_file, sql_id, sql_result['result'],
                 violations=issues, review_feedback=feedback_json)
```

### 5.2 FAIL → 재변환 루프 (구체적 피드백 전달)

```python
# review_result 컬럼에서 구체적 피드백 읽기
SELECT mapper_file, sql_id, review_result FROM transform_target_list WHERE reviewed = 'F'

# Transform Agent에 구체적 이슈 전달
agent(f"Re-transform {ids_str}. SPECIFIC issues found:\n"
      f"  [sql_id_1] [Syntax] NVL(status, 'N') on line 5 not converted to COALESCE\n"
      f"  [sql_id_1] [Equivalence] INNER JOIN where Oracle had (+) outer join\n"
      f"For each: fix the listed issues, apply ALL rules, save with convert_sql.")
```

### 5.3 병렬 처리 + 그룹핑

```python
# Mapper 레벨: 8개 Worker 병렬 실행
with ThreadPoolExecutor(max_workers=8) as executor:
    futures = [executor.submit(review_mapper, m, s, ...) for m, s in mapper_list]

# Group 내부: Syntax + Equivalence Agent 2개 병렬 (perspectives.py)
with ThreadPoolExecutor(max_workers=2) as executor:
    syntax_future = executor.submit(_run_single_perspective, ...)
    equiv_future = executor.submit(_run_single_perspective, ...)
```

---

## 6. DB 스키마

### 6.1 관련 컬럼

```sql
-- 값: 'N' (미리뷰), 'Y' (PASS), 'F' (FAIL)
reviewed TEXT DEFAULT 'N'

-- 상세 피드백 JSON (재변환 시 활용)
review_result TEXT  -- 기존 컬럼, 이번에 활용 시작
```

### 6.2 상태 전이

```
transformed='Y', reviewed='N'  →  Review 대기
transformed='Y', reviewed='Y'  →  PASS → Validate 가능
transformed='Y', reviewed='F'  →  FAIL → review_result에서 피드백 읽어 재변환
```

---

## 7. 로그

```
output/logs/review/[Mapper].log
```

각 SQL ID별 PASS/FAIL 결과, [Syntax]/[Equivalence] 태그가 붙은 구체적 이슈 기록.

---

## 8. 다른 Agent와의 연계

```
Transform Agent
    │
    ├── 변환된 SQL (output/transform/) ──→ Review 입력
    └── FAIL 시 구체적 피드백(review_result) 받아서 재변환

Review (Multi-Perspective)
    │
    ├── Syntax Agent: 구문 규칙 준수 체크
    ├── Equivalence Agent: 기능 동등성 체크
    ├── Facilitator: 결과 통합 (Python 함수)
    ├── PASS → reviewed='Y' ──→ Validate Agent 입력 조건
    ├── FAIL → reviewed='F' + review_result에 피드백 JSON 저장
    └── logs/review/ ──→ 리뷰 상세 로그

Validate Agent
    │
    └── reviewed='Y' 조건으로 검증 대상 필터링
```

---

## 9. 설정

| 항목 | 값 | 설명 |
|------|-----|------|
| max_tokens (각 Perspective) | 16000 | 집중된 관점으로 충분 |
| workers (Mapper 레벨) | 8 | 병렬 처리 수 |
| workers (Perspective) | 2 | Syntax + Equivalence 병렬 |
| max_rounds | 2 | FAIL→재변환 최대 라운드 |
| group_size | 30KB | 배치 그룹 최대 크기 |
| model | Claude Sonnet 4.5 | AWS Bedrock |
| Facilitator | Python 함수 | LLM 호출 없음 |

---

## 10. 비용 영향

- **변경 전**: SQL 그룹당 LLM 1회 호출 (max_tokens=32000)
- **변경 후**: SQL 그룹당 LLM 2회 호출 (각 max_tokens=16000, 병렬)
- **Facilitator**: Python 함수 → LLM 호출 0회
- **절감 요소**: 구체적 피드백으로 Round 2 FAIL 감소 → Transform 재호출 감소
- **Prompt Caching**: 규칙 파일(~15KB)이 캐시되므로 2회 호출의 실제 비용 증가는 제한적

---

**문서 버전**: 2.0
**작성일**: 2026-02-14
**최종 업데이트**: 2026-03-04
