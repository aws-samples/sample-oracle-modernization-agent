# Pipeline Test After Merge Planning Document

> **Summary**: Test 단계를 Merge 이후로 이동하여 최종 XML 기반 테스트 체계 구축
>
> **Project**: Application SQL Transform Agent (OMA sub-module)
> **Author**: Plan Agent
> **Date**: 2026-04-15
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 Test → Merge 순서로, 개별 SQL 파일 기준 테스트 후 합치는 구조. Test에서 SQL 수정 시 Merge에 반영되나 역순이 부자연스럽고, Test 수정 후 Merge 재실행이 필요 |
| **Solution** | Merge → Test 순서로 변경. Test 실패 시 해당 SQL ID 기준으로 재Transform(convert_sql) → 해당 mapper 자동 Re-merge → Re-test 흐름 구현 |
| **Function/UX Effect** | 파이프라인이 자연스러운 흐름 (합치고 → 테스트). Test 실패 시 자동 re-merge로 최종 XML 항상 최신 |
| **Core Value** | 배포될 최종 XML에 대한 신뢰성 확보. Test가 "합쳐진 결과물"을 검증하는 본래 목적에 부합 |

---

## 1. 변경 범위

### 현재 vs 목표

```
현재: Analyze → Transform → Review → Validate → Test → Merge
목표: Analyze → Transform → Review → Validate → Merge → Test
```

### 핵심 설계 결정

- **Test 대상**: 여전히 `TRANSFORM_DIR`의 개별 SQL 파일 (EXPLAIN + Java executor)
- **Merge 역할**: 배포용 XML 조립 (Test와 독립적)
- **Test 실패 → Re-merge**: Agent가 SQL 수정 후 해당 mapper만 `assemble_mapper()` 자동 호출

---

## 2. 수정 대상 파일 (5개)

### FR-01: display.py — 테이블 행 순서 교체
- Merge와 Test 행 위치 교체
- 난이도: 낮음

### FR-02: orchestrator prompt.md — 파이프라인 순서 변경
- Pipeline Steps 5번/6번 교체
- Rules 섹션 순서 업데이트
- Test 실패 시 re-merge 워크플로우 안내 추가
- 난이도: 중간

### FR-03: orchestrator_tools.py — run_step 로직 변경
- test 후 `needs_remerge` 로직 (SQL 수정 시 해당 mapper re-merge 권고)
- backup_output: test 단계에 `xmls/merge` 추가
- 난이도: 중간

### FR-04: state_manager.py — completion flag 조정
- `test_complete` 전제조건 검토 (merge_complete 고려)
- 난이도: 낮음

### FR-05: run_sql_test.py — Phase 2 후 자동 re-merge
- `fix_mapper_failures()` 성공 시 `assemble_mapper(mapper_file)` 호출
- 수정된 mapper 목록으로 일괄 re-merge
- 난이도: 중간

---

## 3. 브랜치 전략

```
main (현재 안정 버전)
  └── feature/test-after-merge (구현 브랜치)
        ├── Step 1~5 구현 + 커밋
        ├── example/ 테스트 검증
        └── main으로 PR/merge
```

- 브랜치: `feature/test-after-merge`
- main에서 분기, 구현 완료 후 merge
- 실 프로젝트 적용 전 example/에서 검증

## 4. 구현 순서

```
Step 0: git checkout -b feature/test-after-merge
Step 1: display.py — Merge/Test 행 순서 교체
Step 2: orchestrator prompt.md — 파이프라인 순서 + 규칙
Step 3: orchestrator_tools.py — run_step + backup 변경
Step 4: state_manager.py — completion flag
Step 5: run_sql_test.py — Phase 2 후 해당 SQL ID 재Transform + auto re-merge
Step 6: example/ 테스트 검증
Step 7: git merge feature/test-after-merge → main
```

---

## 5. 리스크

| 리스크 | 영향 | 대응 |
|--------|------|------|
| 기존 DB 호환 | tested/merged 플래그 순서 변경 | Orchestrator가 check_step_status로 보호 |
| Test Phase 2 수정 후 merge 누락 | 최종 XML에 수정 미반영 | fix_mapper_failures 후 assemble_mapper 자동 호출 |
| Merge 없이 test 실행 | 순서 위반 | Orchestrator prompt에서 merge_complete 확인 |

---

## 6. 테스트 시나리오

1. 정상: Validate → Merge → Test (전체 PASS)
2. Test 실패: FAIL → Agent fix → re-merge → re-test PASS
3. retry failed test: 실패만 재테스트 + 해당 mapper re-merge
4. 기존 데이터: 이미 완료된 프로젝트에서 재실행

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-15 | Initial draft | Plan Agent |
