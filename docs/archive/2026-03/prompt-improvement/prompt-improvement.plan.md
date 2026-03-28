# Prompt & Rules Quality Improvement Planning Document

> **Summary**: 8개 에이전트 프롬프트와 2개 변환 규칙 파일의 품질을 체계적으로 개선
>
> **Project**: Application SQL Transform Agent (OMA sub-module)
> **Version**: -
> **Author**: CTO Lead
> **Date**: 2026-03-28
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 프롬프트/룰 파일이 점진적으로 성장하면서 구조 불일치, 중복, 누락 패턴이 발생. 에이전트 간 일관성이 부족하고 MySQL 규칙이 PostgreSQL 대비 덜 성숙함 |
| **Solution** | 10개 파일(8 프롬프트 + 2 룰)을 체계적으로 분석하고, 구조 표준화/누락 보완/중복 제거/일관성 확보 작업 수행 |
| **Function/UX Effect** | 변환 정확도 향상, 리뷰 라운드 감소, 에이전트 간 충돌(ping-pong) 감소 |
| **Core Value** | 프롬프트 품질이 곧 변환 품질 -- 룰 커버리지와 명확성이 전체 파이프라인 성공률을 좌우함 |

---

## 1. Overview

### 1.1 Purpose

프롬프트와 규칙 파일의 품질을 개선하여 SQL 변환 정확도를 높이고, 에이전트 간 리뷰 ping-pong을 줄인다.

### 1.2 Background

- 최근 PostgreSQL 식별자 소문자 규칙(Phase 1 Section 1-1)을 추가함
- 프롬프트/룰이 기능 추가 시마다 점진적으로 성장해 구조적 정리가 필요한 시점
- MySQL 룰 파일은 PostgreSQL 대비 후발 작성되어 일부 패턴이 누락됨

### 1.3 Related Documents

- `src/reference/oracle_to_postgresql_rules.md` (611줄, 성숙)
- `src/reference/oracle_to_mysql_rules.md` (565줄, 후발)
- `src/agents/*/prompt.md` (8개 에이전트)

---

## 2. Current State Analysis

### 2.1 프롬프트 파일 구조 비교

| Agent | 줄수 | ABSOLUTE RULES | Available Tools | Workflow | Self-Check | Silent Mode |
|-------|------|:-:|:-:|:-:|:-:|:-:|
| **sql_transform** | 119 | O (상세) | O (9개) | O (7단계) | O (5항목) | O |
| **sql_review** | 128 | O (4항목) | O (4개) | O (5단계) | - (체크리스트로 대체) | O |
| **sql_validate** | 93 | O (7항목) | O (6개) | O (5단계) | - | O |
| **sql_test** | 73 | O (6항목) | O (6개) | O (7단계) | - | O |
| **orchestrator** | 166 | - (Rules 섹션) | O (9개+) | O (7단계) | - | - |
| **source_analyzer** | 238 | - | O (6+3개) | O (6+3단계) | - | - |
| **strategy_refine** | 83 | O (4항목) | O (4개) | O (4단계) | - | O |
| **review_manager** | 142 | - (Rules 섹션) | O (5개) | O (4 workflow) | - | - |

### 2.2 식별된 문제 영역

#### P1: 구조적 문제 (높은 영향)

| ID | 문제 | 위치 | 영향도 |
|----|------|------|--------|
| S-01 | MySQL 룰에 Identifier Case Folding 섹션 없음 | mysql_rules Phase 1 | 변환 일관성 |
| S-02 | MySQL 룰에 Common Wrong Conversions 항목 불균형 (7개 vs PG 8개) | mysql_rules | 리뷰 누락 |
| S-03 | sql_review 프롬프트 체크리스트가 PostgreSQL 전용 함수 하드코딩 | sql_review prompt | MySQL 리뷰 실패 |
| S-04 | sql_validate의 "Oracle vs {{TARGET_DB}} Behavioral Differences"가 1번에 CRITICAL이지만 DB별 차이 미반영 | sql_validate prompt | 검증 누락 |

#### P2: 중복/불일치 (중간 영향)

| ID | 문제 | 위치 | 영향도 |
|----|------|------|--------|
| D-01 | sql_review Phase 3 함수 목록이 룰 파일과 일부 불일치 | sql_review prompt vs rules | 오검출/미검출 |
| D-02 | sql_transform SELF-CHECK 항목 vs sql_review 체크리스트 항목 불일치 | transform vs review | ping-pong |
| D-03 | sql_test의 Common SQL Errors가 룰 파일 Common Wrong Conversions와 중복 | sql_test prompt vs rules | 유지보수 |

#### P3: 누락 패턴 (낮은~중간 영향)

| ID | 문제 | 위치 | 영향도 |
|----|------|------|--------|
| M-01 | MySQL: `CUBE` 미지원 대체 패턴이 상세하지 않음 | mysql_rules | 변환 실패 |
| M-02 | MySQL: `NULLS FIRST/LAST` 대체 패턴의 MyBatis 동적 SQL 조합 예제 없음 | mysql_rules | 변환 오류 |
| M-03 | PostgreSQL: `XMLTYPE`/`XMLELEMENT` 구체적 변환 예제 없음 (Review에만 체크 항목 존재) | pg_rules | 변환 누락 |
| M-04 | 두 룰 파일 모두: `BULK COLLECT`, `RETURNING INTO` 변환 예제 부족 | rules | 변환 실패 |

#### P4: 일관성 문제

| ID | 문제 | 위치 | 영향도 |
|----|------|------|--------|
| C-01 | sql_review에서 `(+)` Phase 2인데 "double-check here"로 Phase 3에도 등장 | sql_review prompt | 혼란 |
| C-02 | 에이전트마다 SILENT EXECUTION 규칙 표현이 다름 | 전체 prompt | 일관성 |
| C-03 | sql_validate 섹션 번호 오류 (4.가 두 번 나옴: JOIN과 Ordering) | sql_validate prompt | 가독성 |

---

## 3. Scope

### 3.1 In Scope

- [x] P1: MySQL 룰 파일 구조적 보완 (Identifier Case, Common Wrong Conversions)
- [x] P2: sql_review 프롬프트의 DB별 분기 처리 확인/개선
- [x] P2: transform SELF-CHECK와 review 체크리스트 정합성 확보
- [x] P3: 누락 변환 패턴 보완 (MySQL CUBE/NULLS FIRST, XML 함수)
- [x] P4: 에이전트 프롬프트 일관성 개선 (섹션 번호, SILENT MODE 표현)

### 3.2 Out of Scope

- 프롬프트 구조의 근본적 재설계 (현재 구조 유지)
- 새 에이전트 추가
- 테스트/벤치마크 수행 (변환 후 별도 진행)
- Dynamic strategy (output/strategy/) 수정 -- 이는 런타임에 자동 생성됨

---

## 4. Requirements

### 4.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | MySQL 룰에 Identifier Case 규칙 추가 (lower_case_table_names 고려) | High | Pending |
| FR-02 | sql_review 체크리스트를 {{TARGET_DB}} 범용으로 정리 (PostgreSQL 전용 함수 → DB별 분기 설명) | High | Pending |
| FR-03 | sql_validate 섹션 번호 오류 수정 (4번 중복) | High | Pending |
| FR-04 | sql_transform SELF-CHECK와 sql_review 체크리스트 정합성 맞춤 | High | Pending |
| FR-05 | MySQL Common Wrong Conversions에 누락 항목 추가 | Medium | Pending |
| FR-06 | 룰 파일에 BULK COLLECT, RETURNING INTO 변환 예제 보강 | Medium | Pending |
| FR-07 | PostgreSQL 룰에 XML 함수 변환 예제 추가 | Medium | Pending |
| FR-08 | 에이전트 프롬프트 SILENT MODE 표현 통일 | Low | Pending |

### 4.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Consistency | 8개 프롬프트 간 공통 패턴(SILENT MODE, Tool 섹션 등) 동일 표현 | 수동 diff |
| Coverage | PostgreSQL/MySQL 룰의 기능 커버리지 대등 | 섹션별 비교표 |
| Clarity | 규칙 당 최소 1개 Before/After 예제 포함 | 수동 확인 |

---

## 5. Implementation Plan

### 5.1 작업 순서 (의존성 기반)

```
Phase A: 룰 파일 보강 (독립 작업)
  ├─ A-1: MySQL Identifier Case 규칙 추가 (FR-01)
  ├─ A-2: MySQL Common Wrong Conversions 보강 (FR-05)
  ├─ A-3: 양쪽 룰에 BULK COLLECT/RETURNING INTO 예제 추가 (FR-06)
  └─ A-4: PostgreSQL XML 함수 예제 추가 (FR-07)

Phase B: 프롬프트 정합성 (룰 파일 확정 후)
  ├─ B-1: sql_validate 섹션 번호 수정 (FR-03)
  ├─ B-2: sql_review 체크리스트 DB별 범용화 (FR-02)
  ├─ B-3: sql_transform SELF-CHECK ↔ sql_review 정합성 (FR-04)
  └─ B-4: SILENT MODE 표현 통일 (FR-08)

Phase C: 검증
  └─ C-1: 전체 파일 cross-check (룰 ↔ 프롬프트 ↔ 체크리스트)
```

### 5.2 파일별 변경 범위 예상

| 파일 | 변경 유형 | 예상 줄수 변경 |
|------|----------|--------------|
| `oracle_to_mysql_rules.md` | 추가 (Identifier Case, Wrong Conversions) | +30~50줄 |
| `oracle_to_postgresql_rules.md` | 추가 (XML 함수, BULK COLLECT) | +20~30줄 |
| `sql_review/prompt.md` | 수정 (DB별 범용화) | ~10줄 변경 |
| `sql_validate/prompt.md` | 수정 (섹션 번호) | ~3줄 |
| `sql_transform/prompt.md` | 수정 (SELF-CHECK 정합성) | ~5줄 |
| `sql_test/prompt.md` | 미변경 또는 경미 | ~0줄 |
| 기타 4개 프롬프트 | SILENT MODE 표현 통일 | 각 ~2줄 |

---

## 6. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 룰 변경으로 기존 정상 변환 결과가 달라짐 | High | Low | 규칙 추가만, 기존 규칙 변경 최소화 |
| 프롬프트 토큰 증가로 Prompt Caching 효율 저하 | Medium | Medium | 추가 줄수 50줄 이내 유지, 불필요한 중복 제거로 상쇄 |
| MySQL 룰 변경이 실제 프로젝트에서 미검증 | Medium | Medium | 변경 후 example/ 데모로 기본 검증 |

---

## 7. Success Criteria

### 7.1 Definition of Done

- [ ] MySQL 룰과 PostgreSQL 룰의 구조적 대칭성 확보 (Phase 1~4 섹션 대등)
- [ ] sql_review 체크리스트가 {{TARGET_DB}}로 범용화
- [ ] sql_validate 섹션 번호 정확
- [ ] sql_transform SELF-CHECK 항목이 sql_review 주요 체크리스트와 일치
- [ ] 모든 SILENT MODE 에이전트의 표현 통일

### 7.2 Quality Criteria

- [ ] 기존 변환 결과에 영향 없음 (규칙 추가만, 변경 없음)
- [ ] 프롬프트 토큰 증가가 전체 대비 5% 이내
- [ ] 모든 {{TARGET_DB}} placeholder 정상 동작

---

## 8. Next Steps

1. [ ] Plan 승인 후 Design 단계 진행 (상세 변경사항 명세)
2. [ ] Phase A (룰 파일 보강) 먼저 실행
3. [ ] Phase B (프롬프트 정합성) 실행
4. [ ] Phase C (cross-check 검증) 실행

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-03-28 | Initial draft | CTO Lead |
