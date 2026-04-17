# Next-Gen SQL Test Framework Design Document

> **Summary**: SQL별 파라미터 프로파일 + `<choose>` 멀티세트 + Java Executor JSON 확장으로 동적 SQL 테스트 커버리지 극대화
>
> **Project**: Application SQL Transform Agent (OMA sub-module)
> **Author**: Design
> **Date**: 2026-04-17
> **Status**: Draft
> **Planning Doc**: [next-gen-test-framework.plan.md](../../01-plan/features/next-gen-test-framework.plan.md)

---

## 1. Overview

### 1.1 Design Goals

1. **Parameter 품질 극대화** — SQL별 최적 파라미터 세트를 자동 생성하여 동적 SQL 커버리지를 90%+ 달성
2. **`<choose>` 분기 완전 커버** — 분기별 멀티 파라미터 세트로 모든 코드 경로 검증
3. **Backward Compatible** — 기존 `parameters.properties` 방식과 병행, 점진적 전환
4. **일괄 Test → 오류 분류 → 선택 재테스트** 워크플로우 유지 강화

### 1.2 Design Principles

- **Incremental Enhancement**: 기존 Java executor를 확장, 전면 교체하지 않음
- **Python Generator + Java Executor**: 분석은 Python, 실행은 Java (각자 강점 활용)
- **Fail-Safe Defaults**: 프로파일 생성 실패 시 기존 `parameters.properties` fallback

---

## 2. Architecture

### 2.1 Component Diagram

```
┌─────────────────────────────────────────────────────────┐
│                  Python Layer (분석/생성)                  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  generate_parameters.py                                 │
│    ├── _extract_params_from_xmls()  ← 기존 (글로벌)     │
│    ├── generate_sql_profiles()      ← 신규 (SQL별)      │
│    │     ├── _analyze_sql_context()                     │
│    │     ├── _extract_choose_branches()                 │
│    │     ├── _resolve_param_types()                     │
│    │     └── _generate_multi_sets()                     │
│    └── generate_parameters_file()   ← 기존 유지          │
│                                                         │
│  출력: sql_parameters.json  (SQL별 프로파일)             │
│  출력: parameters.properties (글로벌 — backward compat)  │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                  Java Layer (실행)                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  MyBatisBulkExecutorWithJson.java                       │
│    ├── loadParameters()             ← 기존 (properties) │
│    ├── loadSqlProfiles()            ← 신규 (JSON)       │
│    ├── executeSingleSql()           ← 확장 (멀티 세트)   │
│    └── executeSingleSqlWithResults()← 확장 (멀티 세트)   │
│                                                         │
│  입력: sql_parameters.json (있으면 우선 사용)            │
│  입력: parameters.properties (fallback)                  │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                  Python Layer (결과 처리)                 │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  test_tools.py                                          │
│    ├── run_bulk_test()              ← 확장 (멀티 결과)   │
│    └── _update_tested()             ← 기존 유지          │
│                                                         │
│  run_sql_test.py                                        │
│    └── run()                        ← 프로파일 모드 통합 │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
1. Python: merge/ XML 분석 → sql_parameters.json 생성
                              ↓
2. Python: sql_parameters.json + parameters.properties → tmpdir 복사
                              ↓
3. Java:   sql_parameters.json 로드 → SQL별 파라미터 매핑
           (없으면 parameters.properties fallback)
                              ↓
4. Java:   SQL 실행 (멀티 세트인 경우 순차 실행, 하나라도 PASS면 OK)
                              ↓
5. Java:   test_results.json 출력 (멀티 세트 결과 포함)
                              ↓
6. Python: JSON 결과 파싱 → DB 업데이트 (PASS/FAIL/SKIP)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `generate_sql_profiles()` | merge/ XML files, oma_metadata.json | SQL별 파라미터 프로파일 생성 |
| `loadSqlProfiles()` (Java) | sql_parameters.json | 프로파일 로드 |
| `executeSingleSql()` 확장 | loadSqlProfiles() | 멀티 세트 실행 |
| `run_bulk_test()` 확장 | Java executor JSON 결과 | 멀티 세트 결과 처리 |

---

## 3. Data Model

### 3.1 sql_parameters.json 스키마

```json
{
  "_meta": {
    "generated_at": "2026-04-17 10:00:00",
    "source_dir": "output/merge",
    "total_sqls": 850,
    "profiled_sqls": 720,
    "multi_set_sqls": 45
  },
  "profiles": {
    "MapperName.xml": {
      "selectUserList": {
        "params": {
          "userId": {"value": "1", "type": "integer", "source": "metadata"},
          "startDate": {"value": "2025-01-01", "type": "date", "source": "cast"},
          "useYn": {"value": "Y", "type": "string", "source": "conditional"}
        },
        "sets": [
          {
            "name": "default",
            "description": "기본 파라미터 세트",
            "params": {"userId": "1", "startDate": "2025-01-01", "useYn": "Y"}
          }
        ]
      },
      "selectOrderByType": {
        "params": {
          "searchType": {"value": "NAME", "type": "string", "source": "choose_branch"},
          "keyword": {"value": "1", "type": "string", "source": "default"}
        },
        "sets": [
          {
            "name": "branch_NAME",
            "description": "choose: searchType == NAME",
            "params": {"searchType": "NAME", "keyword": "test"}
          },
          {
            "name": "branch_ID",
            "description": "choose: searchType == ID",
            "params": {"searchType": "ID", "keyword": "1"}
          },
          {
            "name": "branch_otherwise",
            "description": "choose: otherwise (no searchType)",
            "params": {"keyword": "1"}
          }
        ]
      }
    }
  }
}
```

### 3.2 Java 결과 JSON 확장 (test_results.json)

```json
{
  "successfulTests": [
    {
      "xmlFile": "UserMapper.xml",
      "sqlId": "selectUserList",
      "paramSet": "default",
      "executionTimeMs": 45
    }
  ],
  "failedTests": [
    {
      "xmlFile": "OrderMapper.xml",
      "sqlId": "selectOrderByType",
      "paramSet": "branch_ID",
      "errorMessage": "column \"order_id\" does not exist",
      "testedSets": ["branch_NAME:PASS", "branch_ID:FAIL", "branch_otherwise:PASS"]
    }
  ]
}
```

**멀티 세트 판정 기준**: 모든 세트 중 **하나라도 PASS**면 해당 SQL은 **PASS**. 전부 FAIL이어야 FAIL.

---

## 4. 상세 설계

### 4.1 Python: SQL별 프로파일 생성기

#### 4.1.1 `generate_sql_profiles()` — 신규 함수

```python
def generate_sql_profiles(output_path: str = "") -> dict:
    """Generate SQL-level parameter profiles from merge/ XML files.

    Returns:
        Dict with status, profile_count, multi_set_count
    """
```

**처리 흐름**:

```
merge/ XML 순회
  ↓
각 XML에서 SQL ID별로:
  1. SQL body + 동적 태그 추출
  2. 사용된 #{param} 목록 수집
  3. <if>, <choose>, <foreach>, <bind> 분석
  4. 파라미터 세트 생성
  ↓
sql_parameters.json 출력
```

#### 4.1.2 `_analyze_sql_context()` — SQL 단위 분석

```python
def _analyze_sql_context(sql_id: str, full_tag: str, metadata: dict) -> dict:
    """Analyze a single SQL's XML context for parameter profiling.

    Args:
        sql_id: SQL ID
        full_tag: Full XML tag content (including dynamic tags)
        metadata: DB metadata dict

    Returns:
        {
            'params': {name: {value, type, source}},
            'branches': [{condition, params}],
            'has_foreach': bool,
            'has_choose': bool,
        }
    """
```

**분석 항목**:

| XML 패턴 | 추출 정보 | 파라미터 결정 |
|----------|----------|-------------|
| `#{param}::type` | param명, cast 타입 | 타입 기반 값 생성 |
| `<if test="x != null">` | nullable param | 빈값 (블록 skip) |
| `<if test="x != null and x != ''">` | nullable param | 빈값 |
| `<if test="flag == 'Y'">` | param명, 비교값 | `flag=Y` |
| `<if test="a != null and b == 'Y'">` | 복합 조건 | a=빈값 OR (a=값, b=Y) |
| `<choose><when test="t == 'A'">` | 분기 키, 분기값 목록 | 분기별 세트 |
| `<foreach collection="list">` | collection명 | `__LIST__` |
| `<bind name="x" value="...">` | bind 변수 | 소스 param 추적 |
| `to_date(#{p}, 'FMT')` | param명, 포맷 | 포맷 기반 날짜값 |

#### 4.1.3 `_extract_choose_branches()` — choose 분기 분석

```python
def _extract_choose_branches(full_tag: str) -> list[dict]:
    """Extract all branches from <choose><when>...<otherwise> blocks.

    Returns:
        [
            {'condition': "searchType == 'NAME'", 'key': 'searchType', 'value': 'NAME',
             'inner_params': ['keyword']},
            {'condition': "searchType == 'ID'", 'key': 'searchType', 'value': 'ID',
             'inner_params': ['keyword']},
            {'condition': 'otherwise', 'key': 'searchType', 'value': None,
             'inner_params': []}
        ]
    """
```

**파싱 전략**:
```
<choose>                     ← 시작
  <when test="X == 'A'">     ← 분기 1: key=X, value=A
    SQL with #{param1}       ← 이 분기에서 사용하는 param
  </when>
  <when test="X == 'B'">     ← 분기 2: key=X, value=B
    SQL with #{param2}       ← 이 분기에서 사용하는 param
  </when>
  <otherwise>                ← 분기 3: key=X, value=null
    SQL                      ← param 없을 수도 있음
  </otherwise>
</choose>                    ← 끝
```

정규식으로 `<choose>...</choose>` 블록을 추출한 후 내부 `<when>` 태그를 순차 파싱.

#### 4.1.4 `_generate_multi_sets()` — 멀티 파라미터 세트 조합

```python
def _generate_multi_sets(base_params: dict, branches: list[dict],
                         nullable_params: set) -> list[dict]:
    """Generate multiple parameter sets from branch analysis.

    Strategy:
    - Base set: 모든 non-nullable param에 기본값
    - Branch sets: choose 분기별 키값 변경 + 기본값 유지
    - Nullable variations: nullable param이 있으면 활성화/비활성화 세트

    Max sets per SQL: 5 (분기 수가 5 초과 시 대표 분기만)
    """
```

**멀티 세트 생성 규칙**:

| 조건 | 세트 수 | 생성 방식 |
|------|:-------:|----------|
| `<choose>` 없음, nullable 없음 | 1 | 기본 세트만 |
| `<choose>` 없음, nullable 있음 | 1 | nullable=빈값 (기존 동작) |
| `<choose>` 2분기 | 2~3 | 분기별 + otherwise |
| `<choose>` 5분기+ | 5 | 대표 5개 (나머지 skip) |
| 중첩 `<choose>` | 최대 5 | 외부 분기 × 내부 1개 |

### 4.2 Java: JSON 파라미터 프로파일 로드

#### 4.2.1 `loadSqlProfiles()` — 신규 메서드

```java
/**
 * Load SQL-level parameter profiles from sql_parameters.json.
 * Falls back to loadParameters() if JSON not found.
 */
private Map<String, Map<String, List<Map<String, String>>>> loadSqlProfiles() {
    String testFolder = System.getenv("TEST_FOLDER");
    String jsonPath = testFolder != null
        ? testFolder + "/sql_parameters.json"
        : "sql_parameters.json";

    File jsonFile = new File(jsonPath);
    if (!jsonFile.exists()) {
        System.out.println("sql_parameters.json not found — using parameters.properties fallback");
        return null;  // Caller uses Properties fallback
    }

    // Parse JSON → Map<xmlFile, Map<sqlId, List<paramSet>>>
    // Each paramSet is Map<paramName, paramValue>
}
```

**반환 구조**: `Map<xmlFile, Map<sqlId, List<Map<String, String>>>>`
- 1차 키: XML 파일명 (e.g., `UserMapper.xml`)
- 2차 키: SQL ID (e.g., `selectUserList`)
- 값: 파라미터 세트 리스트 (1~5개)

#### 4.2.2 `executeSingleSql()` 확장 — 멀티 세트 실행

```java
// 기존 시그니처 유지
private int executeSingleSql(SqlTestInfo testInfo, Properties parameters,
                              String dbType, boolean verbose) throws Exception {
    // 1. sqlProfiles에서 이 SQL의 파라미터 세트 조회
    List<Map<String, String>> paramSets = getSqlParamSets(testInfo);

    if (paramSets == null || paramSets.isEmpty()) {
        // Fallback: 기존 Properties 기반 실행 (변경 없음)
        return executeSingleSqlLegacy(testInfo, parameters, dbType, verbose);
    }

    // 2. 멀티 세트 실행: 하나라도 성공하면 PASS
    Exception lastError = null;
    for (Map<String, String> paramSet : paramSets) {
        try {
            Map<String, Object> paramMap = buildParamMap(paramSet, testInfo);
            int result = executeWithParams(testInfo, paramMap, dbType, verbose);
            // 성공 → 즉시 리턴
            return result;
        } catch (Exception e) {
            lastError = e;
            // 다음 세트 시도
            if (verbose) {
                System.out.printf("  ⚠️ Set failed: %s — trying next set%n",
                    e.getMessage().substring(0, Math.min(80, e.getMessage().length())));
            }
        }
    }
    // 모든 세트 실패 → 마지막 에러로 throw
    throw lastError;
}
```

#### 4.2.3 `--params-json` 옵션 추가

```java
// main() 옵션 파싱에 추가
case "--params-json":
    if (i + 1 < args.length) {
        paramsJsonFile = args[++i];
    }
    break;
```

**동작**: `--params-json sql_parameters.json` 지정 시 해당 파일을 파라미터 소스로 사용. 미지정 시 `TEST_FOLDER/sql_parameters.json` 자동 탐색.

### 4.3 Python: run_sql_test.py 통합

```python
# run() 함수 내 Phase 1 전 단계 추가
def run(max_workers=8, auto_fix=False):
    # ... 기존 코드 ...

    # Smart Parameter Generation (기존 + 신규)
    from agents.sql_test.tools.generate_parameters import (
        generate_parameters_file, generate_sql_profiles
    )

    # 글로벌 파라미터 (backward compat)
    generate_parameters_file()

    # SQL별 프로파일 (Phase 2 신규)
    profile_result = generate_sql_profiles()
    if profile_result['status'] == 'success':
        print(f"  📋 SQL profiles: {profile_result['profile_count']} SQLs, "
              f"{profile_result['multi_set_count']} multi-set")

    # ... Phase 0, Phase 1 실행 (기존 코드) ...
```

### 4.4 test_tools.py: 멀티 세트 결과 처리

Java가 `test_results.json`에 `paramSet`, `testedSets` 필드를 추가.
Python은 이를 파싱하여:

```python
# 멀티 세트 결과 처리
for item in test_results.get('failedTests', []):
    tested_sets = item.get('testedSets', [])
    # 하나라도 PASS 있으면 → 전체 PASS (Java에서 이미 처리)
    # 전부 FAIL인 경우만 여기에 도달
    # test_notes에 실패한 세트 정보 기록
    notes = f"All {len(tested_sets)} sets failed: {', '.join(tested_sets)}"
    _update_tested(mapper_file, sql_id, result="FAIL", error=notes[:500])
```

---

## 5. 파일 구조 및 수정 대상

### 5.1 수정 파일

```
src/agents/sql_test/tools/
├── generate_parameters.py          ← 확장: generate_sql_profiles() 추가
├── test_tools.py                   ← 확장: sql_parameters.json tmpdir 복사, 멀티 결과 처리
└── (기존 파일 유지)

src/reference/com/test/mybatis/
├── MyBatisBulkExecutorWithJson.java ← 확장: loadSqlProfiles(), 멀티 세트 실행
└── (기존 파일 유지)

src/
├── run_sql_test.py                 ← 확장: profile 생성 단계 추가
└── (기존 파일 유지)
```

### 5.2 신규 파일

```
output/ (런타임 생성)
├── transform/
│   ├── parameters.properties        ← 기존 유지
│   └── sql_parameters.json          ← 신규: SQL별 프로파일
└── ...
```

---

## 6. 구현 순서 (Implementation Order)

### Step 1: SQL별 프로파일 생성기 (Python) — 핵심

1. [ ] `generate_sql_profiles()` 함수 구현 (generate_parameters.py)
2. [ ] `_analyze_sql_context()` — SQL 단위 XML 컨텍스트 분석
3. [ ] `_extract_choose_branches()` — choose/when 분기 파싱
4. [ ] `_generate_multi_sets()` — 멀티 파라미터 세트 조합
5. [ ] `sql_parameters.json` 출력 (스키마 3.1 준수)

### Step 2: Java Executor JSON 파라미터 로드

6. [ ] `loadSqlProfiles()` 메서드 구현
7. [ ] `--params-json` 옵션 추가
8. [ ] `executeSingleSql()` 멀티 세트 실행 루프

### Step 3: 통합

9. [ ] `run_sql_test.py`에 프로파일 생성 단계 통합
10. [ ] `test_tools.py`에서 `sql_parameters.json` tmpdir 복사
11. [ ] 멀티 세트 결과 JSON 파싱 + DB 업데이트

### Step 4: 검증

12. [ ] 실제 프로젝트 (1000+ SQL) 프로파일 생성 검증
13. [ ] `<choose>` 분기 커버리지 확인
14. [ ] 기존 `parameters.properties` fallback 동작 확인

---

## 7. Error Handling

### 7.1 Fail-Safe 체인

| 단계 | 실패 시 | Fallback |
|------|--------|----------|
| sql_parameters.json 생성 실패 | Python 에러 | parameters.properties 사용 (기존 동작) |
| sql_parameters.json 파싱 실패 | Java JSON 에러 | Properties fallback |
| SQL별 프로파일 없음 | 해당 SQL 미등록 | Properties에서 글로벌 파라미터 사용 |
| 멀티 세트 전부 실패 | 마지막 에러 전파 | FAIL + 모든 세트 에러 기록 |
| `<choose>` 파싱 실패 | 정규식 미매칭 | 단일 세트 (기본 동작) |

### 7.2 에러 리포트 강화

```
기존: ❌ OrderMapper.xml:selectOrderByType - column "order_id" does not exist
신규: ❌ OrderMapper.xml:selectOrderByType [3/3 sets failed]
        Set branch_NAME: PASS
        Set branch_ID: column "order_id" does not exist
        Set branch_otherwise: PASS
      → Overall: PASS (1+ set passed)
```

---

## 8. Test Plan

### 8.1 Unit Test Scenarios

| 시나리오 | 입력 | 기대 결과 |
|---------|------|----------|
| 단순 SQL (동적태그 없음) | `SELECT * FROM t WHERE id = #{id}::integer` | 단일 세트: `{id: 1}` |
| `<if>` nullable | `<if test="name != null">AND name = #{name}</if>` | 세트: `{name: ''}` |
| `<if>` conditional | `<if test="flag == 'Y'">AND flag = #{flag}</if>` | 세트: `{flag: 'Y'}` |
| `<choose>` 2분기 | `<when test="type == 'A'">...<when test="type == 'B'">` | 3세트: A, B, otherwise |
| `<foreach>` | `<foreach collection="ids" item="id">` | `{ids: __LIST__}` |
| 복합 조건 | `<if test="a != null and b == 'Y'">` | 2세트: (a='', b='') + (a='1', b='Y') |
| `<bind>` | `<bind name="kw" value="'%'+keyword+'%'"/>` | `{keyword: 'test'}` (kw는 bind 자동) |
| 프로파일 없음 fallback | sql_parameters.json에 해당 SQL 없음 | properties.properties 사용 |

### 8.2 Integration Test

- [ ] 실제 프로젝트 mapper XML로 프로파일 생성 → JSON 출력 검증
- [ ] Java executor가 JSON 프로파일 로드 → 멀티 세트 실행 확인
- [ ] 기존 `parameters.properties` only 모드 동작 확인 (regression)
- [ ] PASS/FAIL/SKIP 판정 정확성 (멀티 세트 결과 집계)

---

## 9. Security Considerations

- [x] `sql_parameters.json`에 민감 데이터 없음 (테스트 기본값만 포함)
- [x] Java executor: 기존 보안 모델 유지 (autoCommit=false, rollback)
- [x] 파일 I/O: 기존 `TRANSFORM_DIR`, `MERGE_DIR` 경계 내에서만 동작
- [x] subprocess: 기존 정적 cmd + stdin 방식 유지 (semgrep 호환)

---

## 10. Coding Convention

### 10.1 Python

| 항목 | 규칙 |
|------|------|
| 함수명 | `snake_case` — `generate_sql_profiles()`, `_extract_choose_branches()` |
| 모듈 위치 | `src/agents/sql_test/tools/generate_parameters.py` (기존 파일 확장) |
| 정규식 | 모듈 레벨 상수로 컴파일 (`_CHOOSE_PATTERN = re.compile(...)`) |
| 에러 | 개별 SQL 실패는 skip, 전체 실패는 빈 dict 반환 |

### 10.2 Java

| 항목 | 규칙 |
|------|------|
| 메서드명 | `camelCase` — `loadSqlProfiles()`, `getSqlParamSets()` |
| JSON 파싱 | Jackson `ObjectMapper` (기존 사용 중) |
| 옵션 | `--params-json <file>` (기존 옵션 스타일 유지) |
| fallback | JSON 없으면 Properties, 명시적 로그 출력 |

---

## 11. 성능 고려사항

| 항목 | 예상 영향 | 대응 |
|------|----------|------|
| 프로파일 생성 시간 | 1000 SQL → ~5초 (XML 파싱) | 충분히 빠름, 캐싱 불필요 |
| `sql_parameters.json` 크기 | 1000 SQL × 평균 3 param = ~200KB | 충분히 작음 |
| 멀티 세트 실행 시간 | `<choose>` 있는 SQL만 영향 (~5%) | 전체 테스트 시간 +10% 이내 |
| Java JSON 파싱 | 1회 파싱, 메모리 보유 | Jackson streaming 불필요 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-17 | Initial draft — Phase 2 상세 설계 | Design |
