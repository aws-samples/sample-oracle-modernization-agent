# SQL Review Agent Design Document

## 1. Agent 개요

### 1.1 목적
- **주요 목표**: Transform Agent가 변환한 PostgreSQL SQL이 General Rules를 준수하는지 체크
- **핵심 원칙**: 규칙 위반을 발견만 하고, 직접 수정하지 않음 (PASS/FAIL 판정만)
- **사용 시나리오**: Transform → **Review** → Validate 사이에서 품질 게이트 역할

### 1.2 입력/출력
```
입력: 원본 Oracle SQL + 변환된 PostgreSQL SQL + General Rules
출력: PASS/FAIL 판정 + 위반 사항 목록 (수정은 하지 않음)
```

### 1.3 왜 Review Agent가 필요한가?

| 문제 | Review 없이 | Review 있으면 |
|------|------------|---------------|
| TO_DATE 잔재 | Validate에서 발견 → 수정 시도 | Review에서 FAIL → Transform 재호출 |
| COALESCE+OR IS NULL | Test에서 중복 조건 발견 | Review에서 즉시 감지 |
| 잘못된 interval 변환 | DB 에러로 발견 | Review에서 패턴 매칭 |

**핵심**: 규칙 위반은 Transform이 고쳐야 함. Validate/Test가 규칙까지 체크하면 역할이 겹침.

---

## 2. 아키텍처

### 2.1 파이프라인 위치

```
Transform ──→ Review ──→ Validate ──→ Test
  변환         규칙 체크    의미 검증     DB 실행
               ↓ FAIL
            Transform
             재호출 (최대 2라운드)
```

### 2.2 처리 흐름

```
┌─────────────────────────────────────────────────────────────────┐
│  배치 리뷰 (Mapper별 그룹, 30KB 이하)                            │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                │
│  │ SQL Group 1 │ │ SQL Group 2 │ │ SQL Group N │                │
│  │ (원본+변환)  │ │ (원본+변환)  │ │ (원본+변환)  │                │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘                │
└─────────┼─────────────────┼─────────────────┼───────────────────┘
          ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  결과 분류                                                       │
│  ✅ PASS: 81개    ❌ FAIL: 5개                                   │
└─────────────────────────┬───────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│  FAIL 처리 (run_sql_review.py)                                   │
│  ├─ Transform Agent 재호출 (violations 전달)                     │
│  ├─ 재변환된 SQL 재리뷰                                          │
│  └─ 최대 2라운드 후 중단                                         │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 디렉토리 구조

```
src/agents/sql_review/
├── agent.py                # 3-Block: prompt + General Rules (Strategy 불필요)
├── prompt.md               # 체크리스트 + 잘못된 변환 패턴 + NOT violations
├── README.md
└── tools/
    ├── __init__.py
    └── review_tools.py     # get_pending_reviews, set_reviewed

src/run_sql_review.py       # 병렬 실행 (8 workers), FAIL→재변환 루프
```

---

## 3. Prompt 설계

### 3.1 2-Block Caching (Strategy 불필요)

```python
system_blocks = [
    SystemContentBlock(
        text=prompt_md,           # 체크리스트 + 판정 기준
        cache_control={"type": "ephemeral"}
    ),
    SystemContentBlock(
        text=general_rules,       # oracle_to_postgresql_rules.md
        cache_control={"type": "ephemeral"}
    ),
]
```

Review는 General Rules 준수만 체크하므로 프로젝트 전략(Strategy)은 불필요.

### 3.2 체크리스트 구조 (prompt.md)

```markdown
## Oracle Function Checklist

### Phase 1: Structural
- [ ] 스키마 접두사 제거
- [ ] Oracle Hint 제거
- [ ] FROM DUAL 제거
- [ ] DB Link 제거

### Phase 2: Syntax
- [ ] Comma JOIN → 명시적 JOIN
- [ ] (+) → LEFT/RIGHT JOIN
- [ ] 서브쿼리 alias

### Phase 3: Functions (30+ 항목)
- [ ] NVL → COALESCE
- [ ] DECODE → CASE WHEN
- [ ] SYSDATE → CURRENT_TIMESTAMP
- [ ] TO_DATE → TO_DATE (PostgreSQL 호환)
- [ ] SUBSTR → SUBSTRING
- [ ] REGEXP_LIKE → ~ 연산자
- [ ] WM_CONCAT → STRING_AGG
- [ ] LENGTHB → OCTET_LENGTH
- [ ] ... (40+ 함수)

### Phase 4: Advanced
- [ ] CONNECT BY → WITH RECURSIVE
- [ ] ROWNUM → LIMIT/OFFSET
- [ ] MINUS → EXCEPT
- [ ] MERGE → INSERT ON CONFLICT

## Common WRONG Conversions (반드시 체크)
1. COALESCE + OR IS NULL 중복
2. date + '1 day'::interval (문자열 interval 오류)
3. ROUND(integer, n) → ROUND(integer::numeric, n) 누락
4. 날짜 포맷 불일치
5. || 를 CONCAT으로 불필요 변환

## NOT a Violation
- || 연산자: PostgreSQL에서 유효한 문자열 연결 연산자
- COALESCE: NVL 대체로 올바른 변환
```

### 3.3 판정 기준

```markdown
## 판정 규칙

### PASS 조건
- General Rules의 모든 해당 항목이 올바르게 적용됨
- 잘못된 변환 패턴이 없음
- Oracle 잔재가 없음

### FAIL 조건 (하나라도 해당되면 FAIL)
- Oracle 함수/구문이 그대로 남아있음
- 잘못된 변환 패턴 발견
- Parameter casting 누락
- XML escaping 오류

### 중요: 수정하지 않음
- FAIL 판정 시 violations 목록만 작성
- 수정은 Transform Agent가 담당
- set_reviewed(sql_id, 'F', violations) 호출
```

---

## 4. Tools 설계

### 4.1 Tool 목록

| Tool | 목적 | 입력 | 출력 |
|------|------|------|------|
| get_pending_reviews | 리뷰 대기 SQL 조회 | 없음 | `{pending: [{mapper, sql_id}]}` |
| read_sql_source | 원본 Oracle SQL 읽기 | mapper, sql_id | `{sql_content}` |
| read_transform | 변환된 PG SQL 읽기 | mapper, sql_id | `{sql_content}` |
| set_reviewed | 리뷰 결과 저장 | sql_id, result, violations | `{status}` |

### 4.2 set_reviewed 상세

```python
@tool
def set_reviewed(mapper_file: str, sql_id: str, result: str, violations: str = "") -> str:
    """Save review result.
    
    Args:
        result: 'Y' (PASS) or 'F' (FAIL)
        violations: FAIL 사유 (FAIL일 때만)
    """
    # DB 업데이트: reviewed = result
    # Signal file 기록: mapper|sql_id|result|violations
```

---

## 5. 실행 스크립트 (run_sql_review.py)

### 5.1 병렬 처리

```python
# 8개 Worker 병렬 실행
with ThreadPoolExecutor(max_workers=8) as executor:
    futures = [executor.submit(process_mapper, mapper) for mapper in mappers]
```

### 5.2 FAIL → 재변환 루프

```python
for round_num in range(max_rounds):  # max_rounds=2
    # 1. Review 실행
    review_results = run_review(pending_sqls)
    
    # 2. FAIL 건 수집
    failures = [r for r in review_results if r['result'] == 'F']
    
    if not failures:
        break
    
    # 3. Transform Agent 재호출 (violations 전달)
    retransform(failures)
    
    # 4. reviewed='N'으로 리셋 → 다음 라운드에서 재리뷰
    reset_review_status(failures)
```

### 5.3 그룹핑

```python
def _group_by_file_size(sql_list):
    """원본+변환본 실제 크기 기준, 30KB 이하로 그룹핑"""
```

---

## 6. DB 스키마

### 6.1 reviewed 컬럼

```sql
ALTER TABLE transform_target_list ADD COLUMN reviewed TEXT DEFAULT 'N';
-- 값: 'N' (미리뷰), 'Y' (PASS), 'F' (FAIL)
```

### 6.2 상태 전이

```
transformed='Y', reviewed='N'  →  Review 대기
transformed='Y', reviewed='Y'  →  PASS → Validate 가능
transformed='Y', reviewed='F'  →  FAIL → 재변환 필요
```

---

## 7. Signal File

```
# .review_signals
mapper_file|sql_id|PASS|
mapper_file|sql_id|FAIL|TO_DATE not converted; COALESCE+OR IS NULL duplicate
```

---

## 8. 로그

```
output/logs/review/[Mapper].log
```

각 SQL ID별 PASS/FAIL 결과와 violations 상세 기록.

---

## 9. 다른 Agent와의 연계

```
Transform Agent
    │
    ├── 변환된 SQL (output/transform/) ──→ Review Agent 입력
    └── FAIL 시 violations 받아서 재변환

Review Agent
    │
    ├── PASS → reviewed='Y' ──→ Validate Agent 입력 조건
    ├── FAIL → reviewed='F' ──→ Transform Agent 재호출
    └── logs/review/ ──→ 리뷰 상세 로그

Validate Agent
    │
    └── reviewed='Y' 조건으로 검증 대상 필터링
```

---

## 10. 설정

| 항목 | 값 | 설명 |
|------|-----|------|
| max_tokens | 32000 | PASS/FAIL 판정에 충분 |
| workers | 8 | 병렬 처리 수 |
| max_rounds | 2 | FAIL→재변환 최대 라운드 |
| group_size | 30KB | 배치 그룹 최대 크기 |
| model | Claude Sonnet 4.5 | AWS Bedrock |

---

**문서 버전**: 1.1
**작성일**: 2026-02-14
**최종 업데이트**: 2026-02-20