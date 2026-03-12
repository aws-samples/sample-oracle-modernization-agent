# Plan: Sample Transform

## Executive Summary

| Perspective | Description |
|-------------|-------------|
| **Problem** | OMA의 transform은 "전체(수백개)" 또는 "단일 SQL" 두 가지뿐이라 실제 프로젝트 투입 전 소규모 시운전이 불가능하다. |
| **Solution** | N개 SQL만 샘플 변환하는 기능을 추가하여 전략/규칙 품질을 빠르게 검증할 수 있게 한다. |
| **Function UX Effect** | `샘플 변환 5개` 한마디로 대표 SQL 5개를 변환하고 결과를 즉시 확인할 수 있다. |
| **Core Value** | 비용과 시간을 최소화하면서 변환 품질을 사전 검증하여, 전체 파이프라인 실행 전 확신을 준다. |

---

## 1. Background

현재 OMA transform 기능의 실행 단위:

| 방식 | 범위 | 용도 |
|------|------|------|
| `run_step('transform')` | 전체 pending SQL (수백~수천개) | 본격 실행 |
| `transform_single_sql(mapper, sql_id)` | 정확히 1개 | 특정 SQL 디버깅 |

**빈 영역**: 5~10개 정도의 대표 SQL을 빠르게 변환해서 전략/규칙의 품질을 확인하고 싶을 때 사용할 방법이 없다.

### Use Case

1. 새 프로젝트 최초 투입 시: analyze 후 strategy가 생성되면, 바로 전체 변환하기 전에 샘플로 품질 확인
2. strategy 수정 후: 전략 보강/압축 후 효과를 일부 SQL로 빠르게 검증
3. 대규모 프로젝트: 1000+개 SQL에서 비용 걱정 없이 소규모 시운전

---

## 2. Goal

- Orchestrator에서 `샘플 변환 N개` 명령으로 N개 SQL을 변환
- 변환 대상은 mapper별 균등 샘플링 (특정 mapper에 편중되지 않도록)
- 변환 결과를 즉시 요약 표시 (성공/실패, 주요 변환 패턴)
- 기존 전체 transform과 충돌 없이 공존 (샘플 변환된 SQL은 DB에 정상 반영)

---

## 3. Scope

### In Scope

| 항목 | 설명 |
|------|------|
| `run_sql_transform.py` 수정 | `run(max_workers, sample)` — sample 파라미터 추가 |
| `get_pending_transforms()` 수정 | `limit` 파라미터 추가, mapper별 균등 샘플링 |
| `run_step()` 수정 | sample 옵션 전달 |
| Orchestrator prompt 수정 | `샘플 변환 N개` 명령 패턴 인식 |
| 결과 요약 | 샘플 결과를 rich panel로 표시 |

### Out of Scope

- Review/Validate/Test의 샘플 실행 (향후 확장 가능하나 이번 scope 아님)
- 샘플 선택 기준의 고도화 (복잡도 기반 등 — 단순 균등 샘플링만)
- dry-run (실제 변환 없이 미리보기) — 별도 기능

---

## 4. Design Overview

### 4.1 흐름

```
User: "샘플 변환 5개"
  ↓
Orchestrator: run_step('transform', sample=5)
  ↓
run_sql_transform.run(sample=5)
  ↓
get_pending_transforms(limit=5)  ← mapper별 균등 분배
  ↓
Transform Agent: 5개 SQL 변환
  ↓
Rich panel: 샘플 결과 요약
```

### 4.2 샘플링 전략

**2단계 선택, 최대 N개 상한:**

1. **sql_type별 최소 1개 보장** — SELECT, INSERT, UPDATE, DELETE 중 존재하는 type에서 각 1개 선택 (N개 상한 내에서). N보다 type 수가 많으면 우선순위 적용: SELECT > INSERT > UPDATE > DELETE
2. **남은 슬롯은 mapper별 round-robin** — (N - 1단계 개수)만큼 mapper를 순회하며 채움. 각 mapper 내에서는 seq_no 순서로 선택

**예시:** N=5, 3 mappers, sql_type 4종
- 1단계: SELECT 1 + INSERT 1 + UPDATE 1 + DELETE 1 = 4개 (각기 다른 mapper에서)
- 2단계: 남은 1개를 mapper round-robin
- 합계: 5개

### 4.3 수정 파일

| File | Change |
|------|--------|
| `src/agents/sql_transform/tools/load_mapper_list.py` | `get_pending_transforms(limit=None)` — limit 시 균등 샘플링 |
| `src/run_sql_transform.py` | `run(max_workers=8, sample=None)` — sample 전달 |
| `src/agents/orchestrator/tools/orchestrator_tools.py` | `run_step(step_name, sample=None)` — sample 옵션 |
| `src/agents/orchestrator/prompt.md` | 샘플 변환 명령 패턴 추가 |

---

## 5. Success Criteria

| Criteria | Target |
|----------|--------|
| `샘플 변환 5개` 명령 동작 | 5개 SQL 변환 완료 |
| mapper별 균등 분배 | 편중 없음 |
| 기존 `변환 수행` 영향 없음 | sample=None이면 기존과 동일 |
| 샘플 결과 요약 표시 | rich panel 출력 |

---

## 6. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| 샘플 SQL이 대표성이 없을 수 있음 | 품질 판단 오류 | sql_type별 최소 1개 보장 + mapper별 균등 round-robin |
| sample 변환 후 전체 변환 시 중복 처리 | 없음 | pending 기반이므로 이미 변환된 건 skip |

---

*Created: 2026-03-13*
*Status: Draft*
