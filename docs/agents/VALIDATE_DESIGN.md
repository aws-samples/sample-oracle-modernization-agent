# SQL Validate Agent Design Document

## 1. Agent 개요

### 1.1 목적
- **주요 목표**: 원본 Oracle SQL과 변환된 PostgreSQL SQL의 기능 동등성 검증
- **핵심 원칙**: 규칙 준수는 Review Agent(다관점: Syntax + Equivalence)가 담당. Validate는 "같은 입력에 같은 결과가 나오는가?"만 검증
- **사용 시나리오**: Transform → Review(PASS) 후, 의미론적 정확성 검증

### 1.2 입력/출력
```
입력: 원본 Oracle SQL + 변환된 PostgreSQL SQL (reviewed='Y'인 것만)
출력: 기능 동등성 판정 (PASS/FAIL) + FAIL 시 자동 수정 + 전략 보강
```

### 1.3 성공 기준
- [x] 원본 Oracle SQL과 변환된 PostgreSQL SQL의 기능 동등성 검증
- [x] Oracle/PostgreSQL 동작 차이 감지 ('' = NULL, DECODE NULL 비교, 암묵적 형변환)
- [x] FAIL 시 자동 수정 (convert_sql 호출)
- [x] 실패 패턴을 전략에 자동 반영
- [x] reviewed='Y' 전제 조건 확인

---

## 2. 아키텍처

### 2.1 전체 구조

```
┌─────────────────────────────────────────────────────────────────┐
│  배치 검증 (3~5개 SQL 그룹)                                      │
│  ※ reviewed='Y' (Review 통과)인 SQL만 검증 대상                  │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                │
│  │ SQL Group 1 │ │ SQL Group 2 │ │ SQL Group N │                │
│  │ (5개 SQL)   │ │ (4개 SQL)   │ │ (3개 SQL)   │                │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘                │
└─────────┼─────────────────┼─────────────────┼───────────────────┘
          ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  검증 결과 분석                                                  │
│  ✅ 성공: 45개    ❌ 실패: 12개    ⚠️  수동검토: 3개            │
└─────────────────────────┬───────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│  자동 수정 (실패건만)                                            │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                │
│  │ 함수 변환   │ │ JOIN 구문   │ │ XML 이스케이프│                │
│  │ 오류 수정   │ │ 오류 수정   │ │ 오류 수정   │                │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘                │
└─────────┼─────────────────┼─────────────────┼───────────────────┘
          ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  전략 보강                                                       │
│  - 실패 패턴 분석 → transform_strategy.md 업데이트              │
│  - 새로운 변환 규칙 추가                                         │
│  - 검증 기준 강화                                                │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 핵심 전략: 배치 검증 → 개별 수정

```
변환된 SQL 그룹 (3~5개)
    │
    ▼ 배치 검증
┌──────────────────────────┐
│ 검증 결과                │
│ ✅ SQL1: 성공            │
│ ❌ SQL2: 함수 변환 오류  │
│ ✅ SQL3: 성공            │
│ ❌ SQL4: JOIN 구문 오류  │
│ ⚠️  SQL5: 수동 검토 필요 │
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 자동 수정 (실패건만)     │
│ SQL2 → 함수 변환 재수행  │
│ SQL4 → JOIN 구문 재수행  │
└────────┬─────────────────┘
         ▼
┌──────────────────────────┐
│ 전략 보강                │
│ "NVL2 변환 시 주의"      │
│ "OUTER JOIN 우선순위"    │
└──────────────────────────┘
```

### 2.3 디렉토리 구조

```
src/agents/sql_validate/
├── agent.py
├── prompt.md
├── README.md
└── tools/
    ├── __init__.py
    ├── load_validation_targets.py    # 검증 대상 SQL 로드
    ├── validate_sql_batch.py         # 배치 검증 수행
    ├── fix_validation_errors.py      # 자동 수정 수행
    ├── update_strategy.py            # 전략 파일 보강
    └── save_validation_report.py     # 검증 보고서 저장
```

---

## 3. 검증 항목: 기능 동등성

### 3.1 Oracle/PostgreSQL 동작 차이 (핵심)

```markdown
## Oracle/PostgreSQL 동작 차이 체크

### 핵심 차이
- Oracle에서 '' = NULL이지만 PostgreSQL에서 '' ≠ NULL
- DECODE는 NULL을 = 로 비교하지만 CASE WHEN은 IS NULL 필요
- Oracle OUTER JOIN (+) + WHERE 조건 → PostgreSQL에서 결과 다를 수 있음
- Oracle 암묵적 형변환 (문자→숫자) → PostgreSQL에서 명시적 캐스팅 필요

### 검증 관점
- 같은 입력 데이터에 같은 결과가 나오는가?
- 컬럼 출력 순서와 개수가 동일한가?
- 필터링 조건이 동일한 행을 반환하는가?
- JOIN 관계가 동일한 결과를 만드는가?
```

### 3.2 함수 변환 검증

```markdown
## 함수 변환 품질 검증

### Oracle → PostgreSQL 함수 매핑
- NVL → COALESCE 변환 정확성
- NVL2 → CASE WHEN 변환 정확성
- DECODE → CASE WHEN 변환 정확성
- TO_CHAR, TO_DATE → TO_TIMESTAMP 변환
- SUBSTR → SUBSTRING 변환
- INSTR → POSITION 변환

### 함수 매개변수
- 매개변수 순서 및 개수 확인
- 날짜 포맷 문자열 호환성
- NULL 처리 로직 일관성
```

### 3.3 JOIN 변환 검증

```markdown
## JOIN 구문 검증

### Oracle (+) → ANSI JOIN
- LEFT JOIN 변환 정확성
- RIGHT JOIN 변환 정확성
- FULL OUTER JOIN 변환
- JOIN 조건 위치 및 논리

### 복잡한 JOIN
- 다중 테이블 JOIN 순서
- 서브쿼리 내 JOIN 처리
- UNION과 JOIN 조합
```

### 3.4 MyBatis 태그 보존 검증

```markdown
## MyBatis 동적 SQL 검증

### 동적 태그 보존
- <if test="..."> 태그 완전성
- <choose><when><otherwise> 구조
- <foreach> 태그 및 속성
- <where>, <set>, <trim> 태그

### 매개변수 바인딩
- #{param} 바인딩 보존
- ${param} 바인딩 보존 (주의사항 포함)
- 매개변수 타입 매핑
```

### 3.5 XML 이스케이프 검증

```markdown
## XML 구조 검증

### XML 이스케이프
- < → &lt; 변환 확인
- > → &gt; 변환 확인
- & → &amp; 변환 확인
- CDATA 섹션 보존

### XML 구조
- 태그 중첩 및 닫기
- 속성 인용 및 이스케이프
- 네임스페이스 보존
```

### 3.6 주석 보존 검증

```markdown
## 주석 및 메타데이터 보존

### SQL 주석
- -- 단일 라인 주석 보존
- /* */ 블록 주석 보존
- 변환 과정에서 추가된 주석 확인

### XML 주석
- <!-- --> XML 주석 보존
- 개발자 메모 및 설명 유지
```

---

## 4. Tools 설계

### 4.1 Tool 목록

| Tool | 목적 | 입력 | 출력 |
|------|------|------|------|
| load_validation_targets | 검증 대상 로드 | 없음 | `{sql_groups: [{group_id, sqls: []}]}` |
| validate_sql_batch | 배치 검증 수행 | group_id, sqls | `{results: [{sql_id, status, errors}]}` |
| fix_validation_errors | 자동 수정 수행 | sql_id, errors | `{fixed_sql, status}` |
| update_strategy | 전략 파일 보강 | error_patterns | `{updated_rules}` |
| save_validation_report | 보고서 저장 | results | `{report_path, summary}` |

### 4.2 핵심: validate_sql_batch는 검증만

LLM이 검증 로직을 수행하고, Tool은 결과를 구조화하여 반환합니다.

```python
@tool
def validate_sql_batch(group_id: str, sqls: List[dict]) -> dict:
    """Validate a batch of converted SQLs.
    
    LLM performs validation using rules in the prompt.
    This tool structures and returns the results.
    """
    # 검증 결과 구조화
    return {
        'group_id': group_id,
        'results': [
            {'sql_id': 'selectUser', 'status': 'success', 'errors': []},
            {'sql_id': 'insertUser', 'status': 'failed', 'errors': ['NVL2 conversion error']},
        ]
    }
```

---

## 5. 데이터 흐름

```
1. load_validation_targets()
   → {sql_groups: [
       {group_id: 'UserMapper_group1', 
        sqls: [
          {sql_id: 'selectUser', original_sql: '...', converted_sql: '...'},
          {sql_id: 'insertUser', original_sql: '...', converted_sql: '...'}
        ]},
       ...
     ]}

2. validate_sql_batch('UserMapper_group1', sqls)
   → {group_id: 'UserMapper_group1',
      results: [
        {sql_id: 'selectUser', status: 'success', errors: []},
        {sql_id: 'insertUser', status: 'failed', 
         errors: ['NVL2(status, active_date, null) conversion incorrect']},
        {sql_id: 'updateUser', status: 'warning', 
         errors: ['Complex JOIN requires manual review']}
      ]}

3. fix_validation_errors('insertUser', ['NVL2 conversion error'])
   → {sql_id: 'insertUser',
      fixed_sql: 'SELECT CASE WHEN status IS NOT NULL THEN active_date ELSE null END...',
      status: 'fixed'}

4. update_strategy(['NVL2 conversion patterns', 'Complex JOIN patterns'])
   → {updated_rules: ['Added NVL2 conversion rule', 'Enhanced JOIN validation'],
      strategy_file: 'output/strategy/transform_strategy.md'}

5. save_validation_report(all_results)
   → {report_path: 'reports/validation_report.md',
      summary: {total_sqls: 86, success: 78, fixed: 6, manual_review: 2}}
```

---

## 6. 자동 수정 로직

### 6.1 수정 가능한 오류 유형

```markdown
## 자동 수정 가능한 오류

### 함수 변환 오류
- NVL → COALESCE 누락
- NVL2 → CASE WHEN 구문 오류
- DECODE → CASE WHEN 변환 오류
- 날짜 함수 변환 오류

### JOIN 구문 오류
- (+) → LEFT/RIGHT JOIN 변환 오류
- JOIN 조건 위치 오류
- ON vs WHERE 절 혼동

### 구문 오류
- 세미콜론 누락/추가
- 괄호 매칭 오류
- 키워드 대소문자 오류
- 인용 부호 오류
```

### 6.2 수정 프로세스

```
검증 실패 SQL
    │
    ▼ 오류 유형 분석
┌──────────────────────────┐
│ 함수 변환 오류           │
│ - NVL2 구문 잘못됨       │
│ - 매개변수 순서 오류     │
└────────┬─────────────────┘
         ▼ 자동 수정 적용
┌──────────────────────────┐
│ 수정된 SQL               │
│ - CASE WHEN 구문 적용    │
│ - 매개변수 순서 수정     │
└────────┬─────────────────┘
         ▼ 재검증
┌──────────────────────────┐
│ 수정 결과                │
│ ✅ 성공 → 완료           │
│ ❌ 실패 → 수동 검토 플래그│
└──────────────────────────┘
```

### 6.3 수정 한계 및 수동 검토

```markdown
## 수동 검토가 필요한 경우

### 복잡한 로직
- 복잡한 CONNECT BY 구문
- 다중 레벨 서브쿼리
- 복잡한 DECODE 중첩

### 비즈니스 로직
- 도메인 특화 함수
- 커스텀 프로시저 호출
- 복잡한 데이터 변환

### 성능 관련
- 힌트 구문 변환
- 인덱스 전략 변경
- 대용량 데이터 처리
```

---

## 7. 전략 보강 프로세스

### 7.1 실패 패턴 분석

```markdown
## 패턴 분석 및 학습

### 실패 패턴 수집
- 함수 변환 실패 유형별 분류
- JOIN 변환 실패 패턴 분석
- MyBatis 태그 손실 패턴
- XML 구조 오류 패턴

### 빈도 분석
- 가장 자주 발생하는 오류 TOP 10
- 프로젝트별 특화 오류 패턴
- 복잡도별 오류 분포
```

### 7.2 전략 파일 업데이트

```markdown
## transform_strategy.md 보강

### 새로운 규칙 추가
```
## 검증에서 발견된 추가 규칙

### NVL2 함수 변환 강화
- NVL2(expr1, expr2, expr3) 변환 시 주의사항
- expr1이 복잡한 표현식일 때 괄호 처리
- NULL 체크 로직 정확성 확인

### OUTER JOIN 변환 우선순위
- (+) 위치에 따른 LEFT/RIGHT JOIN 결정
- 다중 테이블 JOIN 시 순서 고려
- WHERE 절 조건과 ON 절 조건 분리
```

### 검증 기준 강화
- 함수 매개변수 개수 체크 강화
- JOIN 조건 논리 검증 추가
- MyBatis 태그 중첩 검증 강화
```

### 7.3 전략 압축 및 최적화

```markdown
## 전략 파일 최적화

### 중복 제거
- 유사한 패턴 통합
- 중복 규칙 제거
- 예외 사항 정리

### 우선순위 정렬
- 빈발 패턴 우선 배치
- 복잡도별 규칙 그룹핑
- 프로젝트 특화 규칙 분리
```

---

## 8. 사용 예시

### 8.1 전체 파이프라인 실행

```bash
# Orchestrator를 통한 실행
python3 src/run_orchestrator.py

🧑 > 검증 단계 실행해줘
🤖 > [run_step('validate')]
     
     📊 검증 진행 상황:
     - 총 86개 SQL 검증 중
     - 성공: 78개 (90.7%)
     - 자동 수정: 6개 (7.0%)
     - 수동 검토: 2개 (2.3%)
     
     ✅ 검증 완료
```

### 8.2 단계별 수동 실행

```bash
# 검증 단계 실행 (병렬 8개 워커)
python3 src/run_sql_validate.py --workers 8

# 검증 결과 확인
cat reports/validation_report.md

# 실패한 SQL만 재검증
python3 src/run_sql_validate.py --retry-failed
```

### 8.3 특정 SQL 검증

```bash
# Orchestrator를 통한 개별 검증
🧑 > UserMapper.xml의 selectUserList 검증해봐
🤖 > [validate_single_sql("UserMapper.xml", "selectUserList")]
     
     검증 결과:
     ❌ 실패: NVL2 함수 변환 오류
     
     자동 수정을 시도하시겠습니까? (y/n)

🧑 > y
🤖 > [fix_validation_errors("selectUserList", ["NVL2 conversion error"])]
     
     ✅ 자동 수정 완료
     수정된 SQL: CASE WHEN status IS NOT NULL THEN active_date ELSE inactive_date END
```

### 8.4 전략 보강 확인

```bash
# 전략 파일 변경 사항 확인
git diff output/strategy/transform_strategy.md

# 새로 추가된 규칙 확인
grep -A 5 "검증에서 발견된 추가 규칙" output/strategy/transform_strategy.md
```

---

## 9. Transform Agent와의 연계

```
Transform Agent
    │
    ├── 변환된 Mapper XML ──→ Validate Agent 입력
    ├── 변환 전략 파일 ──→ 검증 기준 참조
    └── 변환 보고서 ──→ 검증 범위 결정
                                    
Validate Agent
    │
    ├── 검증된 Mapper XML ──→ Test Agent 입력
    ├── 보강된 전략 파일 ──→ Transform Agent 피드백
    ├── 검증 보고서 ──→ 품질 현황 보고
    └── 수동 검토 목록 ──→ 개발자 작업 가이드
```

---

## 10. 구현 체크리스트

### Phase 1: 디렉토리 & Prompt
- [ ] `src/agents/sql_validate/` 디렉토리 생성
- [ ] `prompt.md` 작성 (검증 규칙 포함)
- [ ] `README.md` 작성

### Phase 2: Tools
- [ ] `load_validation_targets.py`
- [ ] `validate_sql_batch.py`
- [ ] `fix_validation_errors.py`
- [ ] `update_strategy.py`
- [ ] `save_validation_report.py`

### Phase 3: 통합 & 테스트
- [ ] `agent.py` 작성
- [ ] `tests/test_sql_validate.py`
- [ ] Tool 단위 테스트
- [ ] Agent 통합 테스트

### Phase 4: 전략 보강 로직
- [ ] 실패 패턴 분석 로직
- [ ] 전략 파일 업데이트 로직
- [ ] 전략 압축 및 최적화
- [ ] Transform Agent와 피드백 루프

---

**문서 버전**: 1.1  
**작성일**: 2026-02-14  
**최종 업데이트**: 2026-02-20  
**작성자**: OMA Development Team