# Next-Gen SQL Test Framework Planning Document

> **Summary**: 현재 Java Test Framework의 제약을 해소하고 Production 수준의 자동 테스트 체계 구축
>
> **Project**: Application SQL Transform Agent (OMA sub-module)
> **Author**: Plan
> **Date**: 2026-04-17
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 Java Test Framework는 파라미터 처리 한계(타입 추론 불가), 동적 SQL 핸들링 미흡(`<foreach>`, `<choose>`, `${param}`), 단일 파일 테스트 구조로 Production 활용 불가 |
| **Solution** | MyBatis-native 테스트 엔진으로 전환 — 실제 MyBatis SqlSession으로 동적 SQL을 완전 해석하고, 메타데이터 기반 파라미터 자동 생성, 일괄 테스트 + 오류 분류 + 선택적 재테스트 워크플로우 |
| **Function/UX Effect** | Test Pass Rate 향상 (파라미터/동적SQL 오류 감소), Skip 대폭 감소, Production 환경에서도 동일한 테스트 수행 가능 |
| **Core Value** | "변환된 SQL이 실제 운영 환경에서 동작하는가"를 자동으로 검증할 수 있는 신뢰성 확보 |

---

## 1. 현재 제약 분석

### 1.1 Parameter 처리 한계

| 문제 | 현재 동작 | 영향 |
|------|----------|------|
| 타입 추론 불가 | `::cast`나 메타데이터 없으면 기본값 `'1'` | date 컬럼 에러, 풀스캔 |
| `${param}` 직접 치환 | `${tableName}` → `'1'` → `FROM 1` | SQL 에러 |
| Collection 파라미터 | `<foreach collection="list">` → String `'1'` | NPE |
| 조건 제어 파라미터 | `<if test="flag == 'Y'">` → `'1'` ≠ `'Y'` | 분기 미실행 |

### 1.2 동적 SQL 핸들링 미흡

| 문제 | 현재 동작 | 영향 |
|------|----------|------|
| `<foreach>` | Java NPE → SKIP | 해당 SQL 미검증 |
| `<choose><when>` | 파라미터 따라 분기 → 일부만 테스트 | 커버리지 불완전 |
| `<where>` 동적 생성 | 파라미터 null이면 WHERE 자체 없음 | 의도와 다른 SQL 실행 |
| `<include refid>` (cross-mapper) | dependency mapper 복사로 해결 중 | 부분 해결 |

### 1.3 Production 활용 불가

| 문제 | 현재 | Production 요구 |
|------|------|---------------|
| 파라미터 소스 | `parameters.properties` (고정) | 실제 데이터 / API 요청 기반 |
| 테스트 범위 | 개별 SQL 파일 또는 Merge XML | 전체 Mapper + 트랜잭션 |
| 결과 비교 | 실행 가능 여부만 | Oracle vs PostgreSQL 결과 비교 |
| 반복 실행 | 수동 (`retry failed test`) | CI/CD 통합 자동화 |

---

## 2. 목표 아키텍처

### 2.1 테스트 레벨 3단계

```
Level 1: Syntax Validation (현재 Phase 0 — EXPLAIN)
  ├── DML: EXPLAIN으로 구문 검증
  ├── SELECT: EXPLAIN으로 구문 검증
  └── 파라미터 불필요, 가장 빠름

Level 2: Execution Test (현재 Phase 1 — Java executor 개선)
  ├── MyBatis SqlSession으로 실제 실행
  ├── 메타데이터 기반 Smart Parameter 생성
  ├── 동적 SQL 완전 해석 (<foreach>, <choose>, <where>)
  ├── Query timeout 5s → PASS
  └── RowBounds(0,1) 결과 제한

Level 3: Equivalence Test (향후 — Oracle vs Target 비교)
  ├── Oracle에서 실행 → src_result
  ├── Target DB에서 실행 → tgt_result
  ├── JSON 결과 비교 (정규화 후)
  └── 컬럼별 diff 리포트
```

### 2.2 Smart Parameter Generator

```
파라미터 결정 우선순위:
1. 사용자 제공 (parameters.properties) — 있으면 최우선
2. DB 메타데이터 (oma_metadata.json) — 컬럼 타입 기반
3. SQL ::cast 타입 — #{param}::date → date 값
4. MyBatis XML 컨텍스트 분석:
   - <if test="flag == 'Y'"> → flag = 'Y'
   - <foreach collection="list"> → list = ['1']
   - ${tableName} → 실제 테이블명 (메타데이터에서)
5. 기본값 '1'
```

### 2.3 동적 SQL 처리 전략

| 동적 태그 | 현재 | 개선 |
|----------|------|------|
| `<if test="x != null">` | 파라미터 있으면 true | ✅ 동일 (파라미터 품질 향상) |
| `<if test="x == 'Y'">` | '1' ≠ 'Y' → false | 컨텍스트에서 'Y' 추론 |
| `<choose><when>` | 첫 분기만 | 각 분기별 파라미터 세트 생성 |
| `<foreach>` | NPE → SKIP | List 타입 파라미터 생성 |
| `${param}` | '1' → SQL 에러 | 메타데이터에서 테이블/컬럼명 추론 |
| `<where>` | 조건 있으면 WHERE 생성 | ✅ 동일 |

---

## 3. 구현 범위 (3 Phase)

### Phase 1: Smart Parameter Generator (단기)
- **XML 컨텍스트 분석**: `<if test="flag == 'Y'">` → `flag=Y` 추론
- **`<foreach>` 감지**: Collection 파라미터 → `['1']` 리스트 생성
- **`${param}` 감지**: 사용 위치 분석 (FROM → 테이블명, ORDER BY → 숫자)
- **parameters.properties 고도화**: 타입별 적절한 값 자동 생성

### Phase 2: MyBatis-Native Test Engine (중기)
- **전체 Mapper 로딩**: 개별 SQL이 아닌 전체 mapper context로 테스트
- **SqlSession 기반**: 실제 MyBatis 동적 SQL 해석 엔진 활용
- **트랜잭션 관리**: 자동 rollback (데이터 변경 방지)
- **멀티 파라미터 세트**: 하나의 SQL에 여러 파라미터 조합 테스트

### Phase 3: Production Test Suite (장기)
- **CI/CD 통합**: Jenkins/GitHub Actions에서 자동 실행
- **Oracle ↔ Target 결과 비교**: 동일 파라미터로 양쪽 실행 + diff
- **Test Case 관리**: 프로젝트별 테스트 케이스 저장/재사용
- **성능 벤치마크**: 실행 시간 비교 리포트

---

## 4. Phase 1 상세 설계 (Smart Parameter Generator)

### 4.1 XML 컨텍스트 분석기

```python
# <if test="flag == 'Y'"> → flag = 'Y'
# <if test="type != null and type != ''"> → type = '1' (null 아닌 값)
# <foreach collection="list" item="item"> → list = ['1']
# ${tableName} in FROM clause → tableName = (메타데이터에서 첫 번째 테이블)
```

### 4.2 파라미터 프로파일

```json
{
  "startDate": {"type": "date", "source": "cast", "value": "2025-01-01"},
  "userId": {"type": "integer", "source": "metadata", "value": "1"},
  "flag": {"type": "string", "source": "context", "value": "Y"},
  "orderList": {"type": "list", "source": "context", "value": ["1"]},
  "tableName": {"type": "table_ref", "source": "dollar_param", "value": "actual_table"}
}
```

### 4.3 수정 대상

| 파일 | 변경 |
|------|------|
| `src/agents/sql_test/tools/generate_parameters.py` | 컨텍스트 분석기 추가 |
| Java `MyBatisBulkExecutorWithJson.java` | List 타입 파라미터 지원 |
| `parameters.properties` 형식 | 타입 힌트 추가 (`param.type=list`) |

---

## 5. 리스크

| 리스크 | 영향 | 대응 |
|--------|------|------|
| XML 컨텍스트 분석 정확도 | 잘못된 파라미터 → 의미 없는 테스트 | 메타데이터 교차 검증 |
| `<choose>` 모든 분기 커버리지 | 일부 분기 미테스트 | 각 분기별 파라미터 세트 생성 |
| Production 환경 차이 | 개발 DB vs 운영 DB 스키마 차이 | 메타데이터 갱신 주기 설정 |
| Java executor 복잡도 증가 | 유지보수 어려움 | Python wrapper로 복잡도 분리 |

---

## 6. 성공 기준

| 항목 | 현재 | 목표 |
|------|:----:|:----:|
| Parameter 관련 SKIP | ~50건 | <5건 |
| 동적 SQL SKIP | ~120건 | <20건 |
| Test Pass Rate | ~80% | >95% |
| Production 활용 가능 | ❌ | ✅ |
| CI/CD 통합 | ❌ | ✅ (Phase 3) |

---

## 7. 브랜치 전략

```
main (현재 안정 버전)
  └── feature/smart-parameter-gen (Phase 1)
        ├── XML 컨텍스트 분석기
        ├── 파라미터 프로파일 생성
        └── main merge 후 →
  └── feature/mybatis-native-test (Phase 2)
        ├── 전체 mapper 로딩
        ├── SqlSession 기반 테스트
        └── main merge 후 →
  └── feature/production-test-suite (Phase 3)
```

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-17 | Initial draft | Plan |
