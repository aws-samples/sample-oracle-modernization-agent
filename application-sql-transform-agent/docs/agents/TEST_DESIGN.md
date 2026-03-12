# SQL Test Agent Design Document

## 1. Agent 개요

### 1.1 목적
- **주요 목표**: 변환된 PostgreSQL SQL을 실제 DB에서 실행 테스트하여 에러 검증 및 자동 수정
- **사용자**: Oracle → PostgreSQL 마이그레이션 수행 팀
- **사용 시나리오**: Transform → Review → Validate 완료 후, 변환된 SQL의 실제 실행 가능성 검증

### 1.2 입력/출력
```
입력: validated_sql_list (DB) + 변환된 Mapper XML 파일 + PostgreSQL 접속 정보
출력: 테스트 결과 (DB) + 수정된 Mapper XML 파일 + 테스트 보고서 + 보강된 전략
```

### 1.3 성공 기준
- [ ] Phase 1: Java + MyBatis로 모든 SQL 일괄 실행 테스트
- [ ] Phase 2: 실패한 SQL에 대해 Agent가 에러 분석 및 자동 수정
- [ ] 테스트 결과를 DB에 저장 (SUCCESS/FAILED/ERROR)
- [ ] 실패 패턴을 전략에 자동 반영하여 학습 효과 제공
- [ ] 최종 테스트 보고서 생성

---

## 2. 아키텍처

### 2.1 2-Phase 처리 구조

```
┌─────────────────────────────────────────────────────────────────┐
│                    SQL Test Agent                               │
└─────────────────────┬───────────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        ▼                           ▼
┌──────────────────┐        ┌──────────────────┐
│    Phase 1       │   →    │    Phase 2       │
│  Java 일괄 테스트  │        │  Agent 개별 수정  │
│                  │        │                  │
│ ┌──────────────┐ │        │ ┌──────────────┐ │
│ │ Java Runner  │ │        │ │ Error Agent  │ │
│ │ + MyBatis    │ │        │ │ + Fix Logic  │ │
│ │ + PostgreSQL │ │        │ │ + Strategy   │ │
│ └──────────────┘ │        │ └──────────────┘ │
└──────────────────┘        └──────────────────┘
         │                           │
         ▼                           ▼
   전체 실행 결과              개별 SQL 수정 결과
   (SUCCESS/FAILED)           (재변환 + 재테스트)
```

### 2.2 Phase별 처리 흐름

```
Phase 1: 일괄 테스트
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Validated SQLs  │ →  │ Java Test       │ →  │ Execution       │
│ (86개)          │    │ Runner          │    │ Results         │
│                 │    │ (MyBatis)       │    │ (70 OK, 16 ERR) │
└─────────────────┘    └─────────────────┘    └─────────────────┘

Phase 2: 개별 수정
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ Failed SQLs     │ →  │ Agent Analysis  │ →  │ Fixed SQLs      │
│ (16개)          │    │ + Auto Fix      │    │ + Strategy      │
│                 │    │                 │    │ Update          │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### 2.3 디렉토리 구조

```
src/agents/sql_test/
├── agent.py
├── prompt.md
├── README.md
├── java_runner/
│   ├── TestRunner.java         # MyBatis 테스트 실행기
│   ├── pom.xml                 # Maven 설정
│   └── src/main/resources/
│       └── mybatis-config.xml  # MyBatis 설정
└── tools/
    ├── __init__.py
    ├── load_validated_list.py   # 검증된 SQL 목록 로드
    ├── run_java_test.py         # Phase 1: Java 일괄 테스트
    ├── analyze_test_error.py    # Phase 2: 에러 분석
    ├── fix_sql_error.py         # Phase 2: SQL 수정
    ├── retest_sql.py            # Phase 2: 개별 재테스트
    ├── update_strategy.py       # 전략 보강
    └── save_test_results.py     # 결과 저장
```

---

## 3. Phase 1 상세: Java 일괄 테스트

### 3.1 Java Test Runner 구조

```java
// TestRunner.java
public class TestRunner {
    private SqlSessionFactory sqlSessionFactory;
    
    public void testAllMappers() {
        // 1. 모든 Mapper XML 로드
        // 2. 각 SQL ID별 실행 테스트
        // 3. 결과를 JSON으로 출력
        
        for (MapperFile mapper : mappers) {
            for (SqlId sqlId : mapper.getSqlIds()) {
                try {
                    executeSql(sqlId);
                    results.add(new TestResult(sqlId, "SUCCESS", null));
                } catch (Exception e) {
                    results.add(new TestResult(sqlId, "FAILED", e.getMessage()));
                }
            }
        }
    }
}
```

### 3.2 MyBatis 설정

```xml
<!-- mybatis-config.xml -->
<configuration>
    <environments default="postgresql">
        <environment id="postgresql">
            <transactionManager type="JDBC"/>
            <dataSource type="POOLED">
                <property name="driver" value="org.postgresql.Driver"/>
                <property name="url" value="${db.url}"/>
                <property name="username" value="${db.username}"/>
                <property name="password" value="${db.password}"/>
            </dataSource>
        </environment>
    </environments>
    
    <mappers>
        <!-- 변환된 모든 Mapper XML 자동 로드 -->
        <mapper resource="output/mapper/**/*.xml"/>
    </mappers>
</configuration>
```

### 3.3 Phase 1 출력 형식

```json
{
    "test_summary": {
        "total_mappers": 11,
        "total_sqls": 86,
        "success_count": 70,
        "failed_count": 16,
        "execution_time": "45.2s"
    },
    "results": [
        {
            "mapper_file": "UserMapper.xml",
            "sql_id": "selectUserList",
            "status": "SUCCESS",
            "execution_time": "12ms",
            "error": null
        },
        {
            "mapper_file": "OrderMapper.xml", 
            "sql_id": "selectOrderDetail",
            "status": "FAILED",
            "execution_time": null,
            "error": "ERROR: function nvl(character varying, character varying) does not exist"
        }
    ]
}
```

---

## 4. Phase 2 상세: Agent 에러 분석 및 수정

### 4.1 에러 분석 프로세스

```
실패한 SQL
    │
    ▼ analyze_test_error
┌─────────────────────────────────────┐
│ 에러 패턴 분석                       │
│ - 함수 미변환 (NVL, DECODE 등)       │
│ - 문법 오류 (JOIN, SUBQUERY 등)      │
│ - 데이터 타입 불일치                 │
│ - 스키마 차이 (테이블/컬럼명)        │
└─────────────────┬───────────────────┘
                  │
                  ▼ fix_sql_error
┌─────────────────────────────────────┐
│ 자동 수정 적용                       │
│ - 변환 규칙 재적용                   │
│ - 에러별 맞춤 수정                   │
│ - 전략 패턴 참조                     │
└─────────────────┬───────────────────┘
                  │
                  ▼ retest_sql
┌─────────────────────────────────────┐
│ 개별 재테스트                        │
│ - 수정된 SQL 단건 실행               │
│ - 성공 시 DB 업데이트               │
│ - 실패 시 수동 검토 플래그           │
└─────────────────────────────────────┘
```

### 4.2 에러 패턴별 수정 전략

| 에러 패턴 | 원인 | 자동 수정 방법 |
|-----------|------|----------------|
| `function nvl(...) does not exist` | NVL 미변환 | `NVL(a,b)` → `COALESCE(a,b)` |
| `function decode(...) does not exist` | DECODE 미변환 | `DECODE(a,b,c,d)` → `CASE WHEN a=b THEN c ELSE d END` |
| `syntax error at or near "+"` | Outer Join 미변환 | `(+)` → `LEFT/RIGHT JOIN` |
| `relation "dual" does not exist` | DUAL 테이블 미제거 | `FROM DUAL` → 제거 |
| `column "rownum" does not exist` | ROWNUM 미변환 | `ROWNUM <= n` → `LIMIT n` |
| `function to_date(...) does not exist` | 날짜 함수 미변환 | `TO_DATE(...)` → `TO_TIMESTAMP(...)` |
| `function substr(...) does not exist` | 문자열 함수 미변환 | `SUBSTR(s,p,l)` → `SUBSTRING(s FROM p FOR l)` |

### 4.3 Phase 2 Tools 상세

```python
@tool
def analyze_test_error(mapper_file: str, sql_id: str, error_message: str) -> dict:
    """Analyze test error and determine fix strategy."""
    return {
        'error_type': 'FUNCTION_NOT_EXISTS',
        'error_pattern': 'nvl(...)',
        'fix_strategy': 'REPLACE_WITH_COALESCE',
        'confidence': 0.95
    }

@tool  
def fix_sql_error(mapper_file: str, sql_id: str, original_sql: str, fix_strategy: str) -> dict:
    """Apply automatic fix based on error analysis."""
    return {
        'fixed_sql': 'SELECT COALESCE(name, \'Unknown\') FROM users',
        'changes_made': ['NVL → COALESCE'],
        'confidence': 0.95
    }

@tool
def retest_sql(mapper_file: str, sql_id: str, fixed_sql: str) -> dict:
    """Test individual fixed SQL."""
    return {
        'status': 'SUCCESS',
        'execution_time': '8ms',
        'error': null
    }
```

---

## 5. Tools 설계

### 5.1 Tool 목록

| Tool | Phase | 목적 | 입력 | 출력 |
|------|-------|------|------|------|
| load_validated_list | 1 | 검증된 SQL 목록 | 없음 | `{sqls: [{mapper, sql_id, status}]}` |
| run_java_test | 1 | Java 일괄 테스트 | 없음 | `{summary, results: []}` |
| analyze_test_error | 2 | 에러 분석 | mapper, sql_id, error | `{error_type, fix_strategy}` |
| fix_sql_error | 2 | SQL 자동 수정 | sql_id, sql, strategy | `{fixed_sql, changes}` |
| retest_sql | 2 | 개별 재테스트 | mapper, sql_id, sql | `{status, error}` |
| update_strategy | 2 | 전략 보강 | error_patterns | `{updated_rules}` |
| save_test_results | 1,2 | 결과 저장 | results | `{report_path}` |

### 5.2 Java Test Runner 통합

```python
@tool
def run_java_test() -> dict:
    """Run Java MyBatis test for all validated SQLs."""
    
    # 1. Java 프로젝트 빌드
    subprocess.run(['mvn', 'compile'], cwd='java_runner/')
    
    # 2. 테스트 실행
    result = subprocess.run([
        'java', '-cp', 'target/classes:lib/*',
        'TestRunner'
    ], capture_output=True, text=True, cwd='java_runner/')
    
    # 3. JSON 결과 파싱
    test_results = json.loads(result.stdout)
    
    return test_results
```

---

## 6. 데이터 흐름

### 6.1 Phase 1 데이터 흐름

```
1. load_validated_list()
   → {sqls: [
       {mapper_file: 'UserMapper.xml', sql_id: 'selectUser', status: 'VALIDATED'},
       {mapper_file: 'OrderMapper.xml', sql_id: 'selectOrder', status: 'VALIDATED'}
     ]}

2. run_java_test()
   → {summary: {total: 86, success: 70, failed: 16},
      results: [
        {mapper: 'UserMapper.xml', sql_id: 'selectUser', status: 'SUCCESS'},
        {mapper: 'OrderMapper.xml', sql_id: 'selectOrder', status: 'FAILED', 
         error: 'function nvl(...) does not exist'}
      ]}

3. save_test_results(phase1_results)
   → {report_path: 'reports/test_phase1_report.md'}
```

### 6.2 Phase 2 데이터 흐름

```
4. analyze_test_error('OrderMapper.xml', 'selectOrder', 'function nvl(...)')
   → {error_type: 'FUNCTION_NOT_EXISTS', fix_strategy: 'REPLACE_WITH_COALESCE'}

5. fix_sql_error('selectOrder', 'SELECT NVL(name, "Unknown")', 'REPLACE_WITH_COALESCE')
   → {fixed_sql: 'SELECT COALESCE(name, "Unknown")', changes: ['NVL → COALESCE']}

6. retest_sql('OrderMapper.xml', 'selectOrder', fixed_sql)
   → {status: 'SUCCESS', execution_time: '8ms'}

7. update_strategy([{pattern: 'NVL', fix: 'COALESCE'}])
   → {updated_rules: 1, strategy_file: 'output/strategy/test_strategy.md'}

8. save_test_results(phase2_results)
   → {report_path: 'reports/test_final_report.md'}
```

---

## 7. 전략 보강 프로세스

### 7.1 실패 패턴 학습

```python
# 실패 패턴 수집
error_patterns = [
    {
        'sql_id': 'selectUser',
        'original_error': 'function nvl(character varying, character varying) does not exist',
        'pattern': 'NVL(column, default_value)',
        'fix_applied': 'COALESCE(column, default_value)',
        'success': True
    },
    {
        'sql_id': 'selectOrder', 
        'original_error': 'syntax error at or near "+"',
        'pattern': 'table1 t1, table2 t2 WHERE t1.id = t2.id(+)',
        'fix_applied': 'table1 t1 LEFT JOIN table2 t2 ON t1.id = t2.id',
        'success': True
    }
]
```

### 7.2 전략 파일 업데이트

```markdown
# Test Strategy (자동 생성/업데이트)

## 학습된 에러 패턴

### 함수 변환 실패
- **패턴**: `NVL(a, b)` 미변환
- **에러**: function nvl(...) does not exist  
- **수정**: `COALESCE(a, b)`로 변환
- **발생 빈도**: 12회
- **성공률**: 100%

### JOIN 문법 실패  
- **패턴**: `(+)` outer join 미변환
- **에러**: syntax error at or near "+"
- **수정**: `LEFT/RIGHT JOIN` 명시적 변환
- **발생 빈도**: 8회
- **성공률**: 87.5%

## 자동 수정 규칙 (우선순위순)

1. `NVL(a, b)` → `COALESCE(a, b)` (신뢰도: 100%)
2. `DECODE(a,b,c,d)` → `CASE WHEN a=b THEN c ELSE d END` (신뢰도: 95%)
3. `(+)` → `LEFT/RIGHT JOIN` (신뢰도: 87%)
4. `FROM DUAL` → 제거 (신뢰도: 100%)
```

### 7.3 전략 압축 및 최적화

```python
@tool
def update_strategy(error_patterns: list) -> dict:
    """Update test strategy with learned error patterns."""
    
    # 1. 기존 전략 로드
    existing_strategy = load_strategy_file()
    
    # 2. 새 패턴 분석 및 통합
    updated_patterns = merge_patterns(existing_strategy, error_patterns)
    
    # 3. 중복 제거 및 우선순위 정렬
    optimized_patterns = optimize_patterns(updated_patterns)
    
    # 4. 전략 파일 업데이트
    save_strategy_file(optimized_patterns)
    
    return {
        'updated_rules': len(optimized_patterns),
        'strategy_file': 'output/strategy/test_strategy.md'
    }
```

---

## 8. 사용 예시

### 8.1 전체 파이프라인 실행

```python
# Phase 1: 일괄 테스트
validated_sqls = load_validated_list()
# → 86개 SQL 로드

java_results = run_java_test()  
# → 70개 성공, 16개 실패

save_test_results(java_results, phase="phase1")
# → reports/test_phase1_report.md

# Phase 2: 실패 SQL 개별 수정
failed_sqls = [r for r in java_results['results'] if r['status'] == 'FAILED']

for failed_sql in failed_sqls:
    # 에러 분석
    error_analysis = analyze_test_error(
        failed_sql['mapper_file'],
        failed_sql['sql_id'], 
        failed_sql['error']
    )
    
    # 자동 수정
    fix_result = fix_sql_error(
        failed_sql['sql_id'],
        failed_sql['original_sql'],
        error_analysis['fix_strategy']
    )
    
    # 재테스트
    retest_result = retest_sql(
        failed_sql['mapper_file'],
        failed_sql['sql_id'],
        fix_result['fixed_sql']
    )
    
    if retest_result['status'] == 'SUCCESS':
        print(f"✅ {failed_sql['sql_id']} 수정 성공")
    else:
        print(f"❌ {failed_sql['sql_id']} 수동 검토 필요")

# 전략 보강
update_strategy(collected_error_patterns)
# → output/strategy/test_strategy.md 업데이트

# 최종 보고서
save_test_results(all_results, phase="final")
# → reports/test_final_report.md
```

### 8.2 단일 SQL 테스트 (디버깅용)

```python
# 특정 SQL만 테스트
single_result = retest_sql(
    mapper_file="UserMapper.xml",
    sql_id="selectUserDetail", 
    fixed_sql="SELECT COALESCE(u.name, 'Unknown') FROM users u"
)

if single_result['status'] == 'SUCCESS':
    print("✅ 테스트 성공")
else:
    # 에러 재분석
    error_analysis = analyze_test_error(
        "UserMapper.xml",
        "selectUserDetail",
        single_result['error']
    )
    print(f"❌ 에러 타입: {error_analysis['error_type']}")
    print(f"🔧 권장 수정: {error_analysis['fix_strategy']}")
```

### 8.3 배치 처리 최적화

```python
# 실패 SQL을 그룹별로 배치 처리
failed_groups = group_failed_sqls_by_error_type(failed_sqls)

for error_type, sql_group in failed_groups.items():
    print(f"처리 중: {error_type} ({len(sql_group)}개)")
    
    # 같은 에러 타입은 동일한 수정 전략 적용
    fix_strategy = get_fix_strategy_for_error_type(error_type)
    
    for sql in sql_group:
        fix_and_retest(sql, fix_strategy)
```

---

## 9. Validate Agent와의 연계

```
Validate Agent
    │
    ├── validated_sql_list (DB) ──→ Test Agent가 읽음
    ├── 기능 동등성 검증 결과 ──→ 테스트 우선순위 참조
    └── reports/validate_report.md

Review Agent (선행 단계, 다관점: Syntax + Equivalence)
    │
    └── reviewed='Y' ──→ Validate Agent 입력 조건

Test Agent (Phase 1)
    │
    ├── validated_sql_list (DB) ←── 입력
    ├── Java + MyBatis 일괄 테스트
    └── 실행 결과 → Phase 2

Test Agent (Phase 2)  
    │
    ├── 실패 SQL 개별 분석 & 수정
    ├── 전략 보강 (test_strategy.md)
    ├── output/mapper/**/*.xml ──→ 수정된 파일
    └── reports/test_final_report.md ──→ 최종 보고서
```

---

## 10. 성능 및 확장성

### 10.1 처리 성능 목표

| 지표 | 목표 | 측정 방법 |
|------|------|----------|
| Phase 1 실행 시간 | < 60초 (86개 SQL) | Java 테스트 러너 |
| Phase 2 수정 시간 | < 5초/SQL | Agent 개별 처리 |
| 자동 수정 성공률 | > 80% | 재테스트 결과 |
| 전략 학습 효과 | 반복 실행 시 에러율 감소 | 통계 분석 |

### 10.2 확장 포인트

- **다양한 DB 지원**: MySQL, MariaDB 등 추가 가능
- **테스트 데이터 생성**: 실제 데이터 없이도 문법 검증
- **성능 테스트**: 실행 계획 비교 및 최적화 제안
- **병렬 처리**: Phase 2에서 실패 SQL 병렬 수정

---

**문서 버전**: 1.1  
**작성일**: 2026-02-14  
**최종 업데이트**: 2026-02-20  
**작성자**: OMA Development Team