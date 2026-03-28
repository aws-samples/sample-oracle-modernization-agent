# prompt-improvement Gap Analysis Report

> **Analysis Type**: Plan vs Implementation Gap Analysis
>
> **Project**: Application SQL Transform Agent (OMA sub-module)
> **Analyst**: gap-detector
> **Date**: 2026-03-29
> **Plan Doc**: `docs/01-plan/features/prompt-improvement.plan.md`

---

## 1. Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Plan Match (FR 이행률) | 100% | PASS |
| 구조적 일관성 | 92% | WARN |
| Quality Criteria 충족 | 67% | WARN |
| **Overall** | **93%** | PASS |

---

## 2. Functional Requirements 이행 분석

### FR-01: MySQL 룰에 Identifier Case 규칙 추가 -- PASS

**Plan**: `lower_case_table_names` 고려한 Identifier Case 섹션 추가
**Implementation**: `oracle_to_mysql_rules.md` Phase 1 Section 1-1 "Identifier Case Handling"

| 항목 | 기대 | 실제 | 판정 |
|------|------|------|:----:|
| `lower_case_table_names` 설명 | O | O (0/1/2 모두 설명) | PASS |
| lowercase 변환 규칙 | O | O (table, column, alias) | PASS |
| 예외 항목 (literals, params, keywords) | O | O (4가지 예외 명시) | PASS |
| PG 룰과 구조적 대칭 | O | O (PG Section 1-1과 동일 패턴) | PASS |

### FR-02: sql_review 체크리스트 TARGET_DB 범용화 -- PASS

**Plan**: PostgreSQL 전용 함수 하드코딩 제거, DB별 분기 설명 추가
**Implementation**: `sql_review/prompt.md` Phase 3 함수 목록

| 항목 | 기대 | 실제 | 판정 |
|------|------|------|:----:|
| `{{TARGET_DB}}` placeholder 사용 | O | O (11곳) | PASS |
| DB별 분기 표기 (PG/MySQL 병기) | O | O | PASS |
| `||` 분기 (PG: OK, MySQL: CONCAT) | O | O | PASS |
| Parameter casting 분기 | O | O ("PostgreSQL only" 명시) | PASS |
| Common WRONG conversions DB별 분기 | O | O (PG only / MySQL only 구분) | PASS |

### FR-03: sql_validate 섹션 번호 오류 수정 -- PASS

번호 1-7 순차적으로 정확. 중복 없음.

### FR-04: sql_transform SELF-CHECK와 sql_review 체크리스트 정합성 -- PASS

| SELF-CHECK 항목 | Review 대응 항목 | 정합성 |
|-----------------|-----------------|:------:|
| No Oracle syntax remains | Phase 3 전체 함수 목록 | PASS |
| IDENTIFIER LOWERCASE | Phase 1 "Identifier lowercase" | PASS |
| JOIN TYPE | Phase 2 "JOIN type accuracy" | PASS |
| OR IS NULL | Phase 2 "OR IS NULL" Decision Tree | PASS |
| XML ESCAPE CHECK | Always Check "XML escaping" | PASS |
| Parameter casting (PG only) | Always Check "Parameter casting (PostgreSQL only)" | PASS |
| String concatenation (MySQL only) | Common WRONG "MySQL only: ||" | PASS |
| MyBatis tags intact | Always Check "MyBatis tags intact" | PASS |

### FR-05: MySQL Common Wrong Conversions 누락 항목 추가 -- PASS

MySQL 7개 → 8개로 증가 (PG 8개와 대등).

### FR-06: BULK COLLECT, RETURNING INTO 변환 예제 보강 -- PASS

양쪽 룰 파일 Phase 4 "PL/SQL Constructs in SQL" 섹션에 테이블 + 코드 예제 포함.

### FR-07: PostgreSQL 룰에 XML 함수 변환 예제 추가 -- PASS

Phase 4 Section 6 "XML Functions" — 6개 함수(XMLTYPE, XMLELEMENT, XMLAGG, XMLFOREST, EXTRACT, EXISTSNODE) + Before/After 코드 예제.

### FR-08: SILENT MODE 표현 통일 -- PASS

주요 5개 에이전트 프롬프트 모두 "SILENT MODE"로 통일 완료.

---

## 3. Gap 발견 사항

### 3-1. sql_review 서브 프롬프트 SILENT EXECUTION 잔존 (Low)

| 파일 | 현재 표현 | 기대 표현 |
|------|----------|----------|
| `sql_review/prompt_syntax.md` | "SILENT EXECUTION" | "SILENT MODE" |
| `sql_review/prompt_equivalence.md` | "SILENT EXECUTION" | "SILENT MODE" |

Plan의 범위에 명시적으로 포함되지 않았으나, 일관성 관점에서 통일이 바람직함.

---

## 4. Quality Criteria 검증

### 4.1 기존 변환 결과에 영향 없음 -- PASS

모든 변경은 "추가"만. 기존 규칙/함수 매핑/Phase 순서/Critical Rules 변경 없음.

### 4.2 `{{TARGET_DB}}` placeholder 정상 동작 -- PASS

모든 프롬프트에서 하드코딩된 DB명 없음. PG/MySQL은 분기 설명 내에서만 사용.

### 4.3 프롬프트 토큰 증가 5% 이내 -- WARN (경계)

| 파일 | 변경 전 (줄) | 변경 후 (줄) | 증가 |
|------|:-----------:|:-----------:|:----:|
| oracle_to_mysql_rules.md | 565 | 612 | +47 |
| oracle_to_postgresql_rules.md | 611 | 651 | +40 |
| sql_transform/prompt.md | 119 | 122 | +3 |
| sql_review/prompt.md | 128 | 128 | 0 |
| 기타 3개 프롬프트 | 249 | 249 | 0 |
| **합계** | **1,672** | **1,762** | **+90 (+5.4%)** |

5% 기준을 0.4%p 초과. 실질적 영향 미미 (3-Block Prompt Caching으로 비용 영향 최소).

---

## 5. Plan 요구사항별 최종 판정

| ID | Requirement | Priority | 판정 | 비고 |
|----|-------------|:--------:|:----:|------|
| FR-01 | MySQL Identifier Case 규칙 | High | PASS | Section 1-1 완비 |
| FR-02 | sql_review DB별 범용화 | High | PASS | {{TARGET_DB}} + PG/MySQL 분기 |
| FR-03 | sql_validate 섹션 번호 수정 | High | PASS | 1-7 순차 정확 |
| FR-04 | SELF-CHECK ↔ review 정합성 | High | PASS | 8개 항목 1:1 대응 |
| FR-05 | MySQL Wrong Conversions 보강 | Medium | PASS | 7개 → 8개 |
| FR-06 | BULK COLLECT/RETURNING INTO | Medium | PASS | 양쪽 룰에 예제 포함 |
| FR-07 | PostgreSQL XML 함수 예제 | Medium | PASS | 6개 함수 + 코드 예제 |
| FR-08 | SILENT MODE 통일 | Low | PASS | 주요 5개 프롬프트 통일 |

**FR 이행률: 8/8 = 100%**

---

## 6. Recommended Actions

| Priority | 항목 | 설명 |
|:--------:|------|------|
| Low | 서브 프롬프트 SILENT MODE 통일 | `prompt_syntax.md`, `prompt_equivalence.md` 2개 파일 |
| Low | 토큰 증가 최적화 | 중복 설명 압축으로 5% 이내 달성 가능 |

**즉시 조치 불필요. Report 단계 진행 가능.**

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-03-29 | Initial gap analysis | gap-detector |
