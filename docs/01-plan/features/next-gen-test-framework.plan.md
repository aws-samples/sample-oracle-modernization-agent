# Next-Gen SQL Test Framework Planning Document

> **Summary**: Java Test Framework의 Parameter/동적SQL 제약 해소 + Production 수준 자동 테스트 체계 구축
>
> **Project**: Application SQL Transform Agent (OMA sub-module)
> **Author**: Plan
> **Date**: 2026-03-28
> **Status**: Active (Phase 1.5 완료, Phase 2 설계 중)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | Java Test Framework는 Parameter 처리 한계(타입 추론, 동적 분기), 동적 SQL 핸들링 미흡(`<foreach>`, `<choose>`, `${param}`), 단일 파라미터 세트로 모든 SQL 테스트 — **Parameter 품질이 Test 결과 품질을 결정**하는데 현재 구조에서는 한계 |
| **Solution** | 3단계 접근: (1) Smart Parameter Generator 고도화 — XML 컨텍스트 기반 파라미터 품질 극대화, (2) 동적 SQL 완전 해석 엔진 — `<choose>` 분기별 멀티 파라미터 세트, `<foreach>` native 지원, (3) Production 자동 Test — 일괄 실행 + PASS/FAIL 분류 + 오류만 선택적 재테스트 + CI/CD |
| **Function/UX Effect** | 일괄 Test → Pass 처리, 오류만 따로 모아서 수정 가능. SKIP 대폭 감소, Test Pass Rate 95%+ 달성 |
| **Core Value** | "변환된 SQL이 실제 운영 환경에서 동작하는가"를 자동 검증 — **Parameter가 잘 구성되면 동적 SQL을 더 정확히 처리하고, 이것이 결과 품질을 결정** |

---

## 1. 핵심 인사이트

### 1.1 Parameter 품질 = Test 품질

```
Parameter 구성 품질
  ↓ 결정
동적 SQL 해석 정확도 (<if>, <choose>, <foreach>, <where>)
  ↓ 결정
Test 실행 결과 품질 (Pass Rate, SKIP 감소)
  ↓ 결정
전체 변환 신뢰도
```

현재 시스템에서 Test FAIL/SKIP의 대부분은 **SQL 변환 오류가 아니라 Parameter 부족/부정확**에서 발생한다.
따라서 Parameter 품질을 극대화하는 것이 Test Framework 개선의 핵심이다.

### 1.2 현재 Parameter 처리 구조 (Phase 1.5 완료 기준)

| 우선순위 | 소스 | 처리 방식 | 상태 |
|:--------:|------|----------|:----:|
| 1 | `<foreach collection="list">` | `__LIST__` 마커 → Java ArrayList | ✅ |
| 2 | `<if test="x != null">`, `@Util@isNotEmpty(x)` | 빈값 (동적 블록 skip) | ✅ |
| 3 | `<if test="flag == 'Y'">` | XML에서 비교값 추출 → `flag=Y` | ✅ |
| 4 | `to_date(#{p}, 'YYYYMMDD')` | 포맷 추론 → `20250101` | ✅ |
| 5 | DB 메타데이터 (oma_metadata.json) | 컬럼 타입 기반 값 생성 | ✅ |
| 6 | SQL `::cast` 타입 | `#{p}::date` → `2025-01-01` | ✅ |
| 7 | 기본값 | `'1'` | ✅ |

### 1.3 남은 제약 (Phase 2에서 해결)

| 제약 | 현재 영향 | 해결 방향 |
|------|----------|----------|
| `<choose><when>` 분기별 파라미터 | 하나의 파라미터 세트로 일부 분기만 테스트 | 분기별 멀티 파라미터 세트 |
| 복합 조건 `<if test="a != null and b == 'Y'">` | 단순 매칭만 | 조건 조합 파서 |
| `${param}` SQL 구조 파라미터 | 빈값 → SKIP | 테이블명/컬럼명 추론 |
| `#{param}` SQL 구조 파라미터 (비교연산자 없이 독립 사용) | `?` 바인딩 → syntax error | 테스트 전 XML 전처리로 제거 |
| 동일 param, 다른 용도 (SQL마다 다른 타입) | 글로벌 1개 값 | SQL별 파라미터 프로파일 |
| `<bind>` 표현식 | 미처리 | bind 값 추출/평가 |

#### #{param} SQL 구조 파라미터 문제 (Phase 2)

`#{GRIDPAGING_ROWNUMTYPE_TOP}`, `#{SEARCH_CONDITION}` 등 — 데이터 값이 아니라 SQL 구조를 조립하는 파라미터가 `#{}` (prepared statement)로 바인딩됨. `<if>`로 감싸져 있지 않아 파라미터를 empty로 해도 MyBatis가 `?`로 치환 → syntax error 발생.

**패턴 예시:**
```sql
-- GRIDPAGING: Oracle ROWNUM 페이징 래퍼 (sql_pagingTop/Bottom fragment)
#{GRIDPAGING_ROWNUMTYPE_TOP}
SELECT B.* FROM (
  -- 실제 SQL
) B
#{GRIDPAGING_ROWNUMTYPE_BOTTOM}

-- SEARCH_CONDITION: 동적 WHERE 조건 주입
WHERE 1=1 AND #{SEARCH_CONDITION}
```

**해결 방향:** 테스트 전 XML 전처리 — tmpdir 복사 후 Java 실행 전에 구조 파라미터를 감지하여 제거/치환. 판별 기준: `#{param}` 주변에 비교 연산자(`=`, `LIKE`, `IN`, `>`, `<`)가 없으면 구조 파라미터.

---

## 2. 현재 아키텍처 (Phase 1.5 완료)

### 2.1 Test Pipeline

```
Pre-skip (non-testable: sql, resultMap)
  ↓
Phase 0: EXPLAIN DML (INSERT/UPDATE/DELETE)
  ├── Parameter 불필요 (NULL 치환)
  ├── 구문 검증 + 테이블/컬럼 존재 확인
  └── FAIL → DB 업데이트
  ↓
Phase 1: Java Bulk Test (SELECT + DML from MERGE_DIR)
  ├── MyBatis SqlSession 기반 실행
  ├── parameters.properties 기반 파라미터 주입
  ├── Query timeout 5s → PASS
  ├── RowBounds(0,1) 결과 제한
  └── JSON 결과 → DB 업데이트 (PASS/FAIL/SKIP)
  ↓
Phase 2: Agent Fix (opt-in, --fix)
  └── FAIL만 Agent가 수정 시도
```

### 2.2 Parameter Generator 구현 파일

| 파일 | 역할 |
|------|------|
| `src/agents/sql_test/tools/generate_parameters.py` | Smart Parameter Generator (Python) |
| `src/reference/com/test/mybatis/MyBatisBulkExecutorWithJson.java` | Java Test Executor |
| `src/reference/run_postgresql.sh` / `run_mysql.sh` | Test 실행 스크립트 |
| `parameters.properties` | 생성된 파라미터 파일 |

### 2.3 Java Executor 핵심 기능

- `__LIST__` 마커 → `ArrayList` 자동 변환 (`<foreach>` 지원)
- `cleanParameterValue`: 빈값 유지 (빈문자열 → '1' 변환하지 않음)
- `executeSingleSqlWithResults`: XML auto-fill (파라미터 자동 스캔)
- Query timeout 5s → PASS (valid SQL, slow execution)
- RowBounds(0,1) for SELECT
- `--select-only`, `--json-file` 옵션

---

## 3. 구현 범위 (3 Phase)

### Phase 1: Smart Parameter Generator — ✅ 완료 (v1.0 ~ v1.5)

**v1.0** (기본): `::cast` 타입, 메타데이터 매칭, 기본값 '1'
**v1.5** (완료): nullable 추론, conditional 값 추출, `<foreach>` List, date format, `@Util@` 패턴

### Phase 2: 동적 SQL 완전 해석 엔진 (현재 계획 중)

**핵심 목표**: Parameter 품질을 극대화하여 동적 SQL 커버리지를 90%+로 올림

#### 2.1 SQL별 파라미터 프로파일 (FR-01)

현재: 전체 XML에서 추출한 글로벌 파라미터 1세트
목표: **SQL ID별 최적 파라미터 세트** 생성

```python
# 현재: parameters.properties (글로벌)
userId=1
startDate=20250101
flag=Y

# 목표: SQL별 파라미터 프로파일 (JSON)
{
  "selectUserList": {
    "params": {"userId": "1", "startDate": "2025-01-01", "useYn": "Y"},
    "dynamic_branches": ["if_userId", "if_startDate"],
    "coverage": "2/3 branches"
  },
  "selectOrderDetail": {
    "params": {"ordNo": "1", "itemList": ["1", "2"]},
    "dynamic_branches": ["foreach_itemList"],
    "coverage": "1/1 branches"
  }
}
```

#### 2.2 `<choose><when>` 멀티 파라미터 세트 (FR-02)

```xml
<choose>
  <when test="searchType == 'NAME'">
    AND user_name LIKE #{keyword}
  </when>
  <when test="searchType == 'ID'">
    AND user_id = #{keyword}::integer
  </when>
  <otherwise>
    AND 1=1
  </otherwise>
</choose>
```

현재: `searchType=NAME` 하나만 테스트
목표: `searchType=NAME`, `searchType=ID`, 빈값(otherwise) — **3세트 모두 테스트**

```
파라미터 세트 생성 전략:
1. <when test="..."> 조건에서 분기 키 추출 (searchType)
2. 각 분기별 값 생성 (NAME, ID, null)
3. 나머지 파라미터는 기본값 유지
4. 3세트 × 동일 SQL 실행 → 하나라도 PASS면 OK
```

#### 2.3 복합 조건 파서 (FR-03)

```xml
<if test="startDate != null and startDate != '' and endDate != null">
  AND reg_date BETWEEN #{startDate}::date AND #{endDate}::date
</if>
```

현재: `startDate != null` → nullable(빈값) → 이 블록 미실행
목표: 복합 조건 파싱 → `startDate=2025-01-01, endDate=2025-12-31` 세트 + 빈값 세트 2가지

#### 2.4 `${param}` 추론 개선 (FR-04)

```xml
FROM ${tableName}    → tableName = 'actual_table' (메타데이터에서 첫 번째 테이블)
${GRIDPAGING_TOP}    → 빈값 유지 (동적 페이징)
${columnName}        → columnName = 'col1' (메타데이터에서 추론)
```

#### 2.5 `<bind>` 표현식 처리 (FR-05)

```xml
<bind name="searchKeyword" value="'%' + keyword + '%'" />
AND user_name LIKE #{searchKeyword}
```

`searchKeyword`는 `<bind>`에서 생성됨 → `keyword` 파라미터만 제공하면 MyBatis가 자동 처리

#### 2.6 Java Executor 개선 (FR-06)

| 개선 항목 | 설명 |
|----------|------|
| 멀티 파라미터 세트 지원 | JSON 파일에서 SQL별 파라미터 배열 로드 |
| 분기 커버리지 리포트 | 어떤 `<when>` 분기가 실행됐는지 로그 |
| 파라미터 타입 힌트 | `param.type=list` → Java에서 정확한 타입 생성 |

### Phase 3: Production Test Suite (장기)

| 항목 | 설명 |
|------|------|
| CI/CD 통합 | Jenkins/GitHub Actions 자동 실행 |
| Oracle ↔ Target 결과 비교 | 동일 파라미터, 양쪽 실행 + diff |
| Test Case 관리 | 프로젝트별 파라미터 세트 저장/재사용 |
| 성능 벤치마크 | 실행 시간 비교 리포트 |
| 회귀 테스트 | 변환 재실행 시 기존 PASS 유지 확인 |

---

## 4. Phase 2 상세 설계

### 4.1 파라미터 프로파일 생성기

```
입력: merge/ 디렉토리의 Mapper XML
  ↓
Step 1: SQL ID별 XML 컨텍스트 분석
  - 사용된 #{param} 목록
  - <if>, <choose>, <foreach>, <bind> 태그 구조
  - 각 param의 용도 (WHERE, JOIN, LIMIT, ORDER BY)
  ↓
Step 2: 분기 분석 → 파라미터 세트 생성
  - <if>: 활성화 세트 + 비활성화 세트
  - <choose>: 분기 수만큼 세트
  - <foreach>: List 파라미터 자동 생성
  ↓
Step 3: 타입 결정 (우선순위)
  1. 사용자 지정 (parameters.properties override)
  2. DB 메타데이터 (oma_metadata.json)
  3. SQL ::cast 타입
  4. 날짜 함수 포맷
  5. 조건 비교값
  6. 기본값 '1'
  ↓
출력: sql_parameters.json (SQL별 파라미터 프로파일)
```

### 4.2 테스트 실행 흐름 (Phase 2)

```
1. 일괄 테스트 (Batch Test)
   ├── sql_parameters.json 로드
   ├── SQL별 최적 파라미터 세트로 실행
   ├── <choose> 분기별 멀티 세트 실행
   └── 결과: PASS / FAIL / SKIP
       ↓
2. Pass 처리 (자동)
   └── PASS된 SQL → test_result='PASS', 완료
       ↓
3. 오류 분류 (Classify)
   ├── Parameter 오류 → 파라미터 조정 후 재테스트
   ├── SQL 변환 오류 → Transform Agent 재변환
   ├── 스키마 오류 → DDL 확인 필요
   └── 테스트 불가 → SKIP + 사유 기록
       ↓
4. 선택적 재테스트 (Retry Failed Only)
   ├── FAIL만 추출 → 수정 → 재테스트
   ├── 카테고리별 일괄 SKIP 가능
   └── 개별 SQL SKIP 가능
```

### 4.3 수정 대상 파일

| 파일 | 변경 내용 | 우선순위 |
|------|----------|:--------:|
| `generate_parameters.py` | SQL별 프로파일 생성, `<choose>` 멀티 세트, `<bind>` 처리 | High |
| 신규: `sql_parameters.json` | SQL별 파라미터 프로파일 포맷 | High |
| `MyBatisBulkExecutorWithJson.java` | JSON 파라미터 프로파일 로드, 멀티 세트 실행 | High |
| `run_sql_test.py` | Phase 1 JSON 파라미터 모드 통합 | Medium |
| `test_tools.py` | 멀티 세트 결과 처리, 분기 커버리지 | Medium |
| `orchestrator_tools.py` | 파라미터 프로파일 조회/수정 도구 | Low |

---

## 5. 성공 기준

| 항목 | Phase 1.5 (현재) | Phase 2 목표 | Phase 3 목표 |
|------|:----------------:|:------------:|:------------:|
| Parameter SKIP | ~30건 | <5건 | 0건 |
| 동적 SQL SKIP | ~80건 | <10건 | <5건 |
| Test Pass Rate | ~85% | >95% | >98% |
| `<choose>` 커버리지 | 1 분기만 | 전 분기 | 전 분기 |
| Production 활용 | ❌ | ⚠️ (수동) | ✅ (CI/CD) |
| 재테스트 워크플로우 | ✅ (FAIL만) | ✅ (카테고리별) | ✅ (자동) |

---

## 6. 리스크

| 리스크 | 영향 | 대응 |
|--------|------|------|
| `<choose>` 멀티 세트로 테스트 시간 증가 | SQL당 2~5배 | 병렬 실행, timeout 유지 |
| SQL별 프로파일 생성 정확도 | 잘못된 파라미터 → 무의미한 테스트 | 메타데이터 교차검증, 실패 시 fallback |
| Java executor 복잡도 증가 | 유지보수 부담 | Python 래퍼로 복잡도 분리 |
| 대규모 프로젝트 (1000+ SQL) 메모리 | JSON 프로파일 크기 | SQL 단위 스트리밍 처리 |

---

## 7. 구현 전략

### Phase 2 단계별 접근

```
Step 1: SQL별 파라미터 프로파일 JSON 생성기 (Python)
  → generate_parameters.py 확장 → sql_parameters.json 출력
  → 기존 parameters.properties와 병행 (backward compat)

Step 2: Java executor JSON 파라미터 로드
  → MyBatisBulkExecutorWithJson.java에 --params-json 옵션 추가
  → SQL ID별 파라미터 매핑

Step 3: <choose> 멀티 파라미터 세트
  → 분기 분석기 + 세트별 실행 루프
  → 하나라도 PASS면 해당 SQL PASS 처리

Step 4: 커버리지 리포트
  → 어떤 분기가 실행됐는지, 어떤 파라미터가 사용됐는지 리포트
```

### 브랜치 전략

```
main (현재 안정 버전, Phase 1.5 포함)
  └── feature/sql-param-profile (Phase 2 Step 1~2)
        └── main merge 후 →
  └── feature/choose-multi-set (Phase 2 Step 3~4)
        └── main merge 후 →
  └── feature/production-test-suite (Phase 3)
```

---

## 8. Next Steps

1. [ ] Phase 2 Design 문서 작성 (`/pdca design next-gen-test-framework`)
2. [ ] SQL별 파라미터 프로파일 JSON 포맷 확정
3. [ ] `<choose>` 분기 분석기 프로토타입
4. [ ] Java executor JSON 파라미터 로드 구현
5. [ ] 통합 테스트 (실제 프로젝트 1000+ SQL 검증)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-17 | Initial draft | Plan |
| 0.2 | 2026-04-17 | Phase 1 대부분 구현 완료 반영, 잔여 항목 정리 | - |
| 1.0 | 2026-03-28 | Phase 1.5 완료 반영, Phase 2 상세 설계, 핵심 인사이트(Parameter=품질) 추가 | Plan |
