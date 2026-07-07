# Large-Scale Processing Guide

**대규모 프로젝트 운영 가이드 (수백~수천 SQL)**

OMA로 대규모 MyBatis Mapper 변환을 수행할 때의 권장 전략과 운영 팁.

---

## 목차

1. [규모 판단 기준](#규모-판단-기준)
2. [샘플 변환 전략](#샘플-변환-전략)
3. [배치 Dispatch 운영](#배치-dispatch-운영)
4. [체크포인트와 중단/재개](#체크포인트와-중단재개)
5. [Claude Code 세션 관리](#claude-code-세션-관리)
6. [DB 백업](#db-백업)
7. [문제 해결](#문제-해결)

---

## 규모 판단 기준

| 규모 | SQL 수 | 예상 소요 | 권장 전략 |
|------|--------|-----------|-----------|
| 소규모 | ~50 | 1 세션 | 전체 변환 한 번에 진행 |
| 중규모 | 50~300 | 2~5 세션 | 샘플 10건 → 전략 보정 → 전체 |
| 대규모 | 300~1000+ | 다수 세션 | 샘플 15건 → 전략 확정 → 배치별 진행 + 세션 분할 |

> **핵심**: 규모가 커질수록 **샘플 검증 → 전략 보정** 단계가 중요하다.
> 잘못된 전략으로 1000건을 돌리면 재변환 비용이 막대하다.

---

## 샘플 변환 전략

### 목적

대규모 프로젝트에서는 전체 변환 전에 대표 SQL을 먼저 변환하여:
- 전략 파일(`output/strategy/transform_strategy.md`)의 완성도 검증
- Tier 1 룰의 누락/오류 조기 발견
- 예상 PASS율 추정

### 실행 방법

Analyze 완료 후 체크포인트에서 "샘플 N건" 선택:

```
체크포인트 응답: "샘플 15건으로 먼저 해보자"
```

오케스트레이터가 sql_type별 분산 + mapper round-robin으로 대표 SQL을 선정한다.
샘플 결과가 만족스러우면 전체 변환으로 진행.

### 샘플 결과 활용

- PASS율 80%+ → 전략 파일 미조정, 전체 진행
- PASS율 60~80% → FAIL 패턴 분석 후 전략 파일 보강, 재샘플
- PASS율 60% 미만 → Tier 1 룰 자체 검토 필요 (프로젝트 특수 패턴 다수)

---

## 배치 Dispatch 운영

### 병렬 dispatch 제한

파이프라인 스킬에 정의된 불변 원칙:
- **동시 dispatch 최대 5개** (subagent 5개 병렬)
- 대기 배치가 더 있으면 5개 단위로 순차 dispatch

### 배치 크기 제어

`oma db pending --step <step> --max-batch <N>` 로 배치당 SQL 수 제한:
- 기본값: 15 (mapper 1개 기본, 15건 초과 시 분할)
- 대규모 프로젝트에서는 기본값 유지 권장

### 실패 재시도

실패한 SQL만 선택적으로 재dispatch:

```bash
oma db pending --step transform --only "mapper_a.xml:selectUser,mapper_b.xml:insertOrder"
```

전체를 reset하지 않고 실패 건만 골라서 재시도할 수 있다.

---

## 체크포인트와 중단/재개

### 상태는 DB가 SSOT

모든 파이프라인 진행 상태는 `output/oma_control.db`에 기록된다.
세션이 중단되어도 상태가 유실되지 않는다.

### 재개 방법

새 세션에서:

```bash
uv run oma status --json
```

이 명령으로 현재 위치를 파악하고, 해당 단계의 체크포인트부터 재개한다.

### 단계별 재개 예시

| 상황 | 확인 방법 | 재개 |
|------|-----------|------|
| Transform 중 중단 | `status`에 transformed=N 잔여 | "변환 계속" |
| Review 2라운드 중 중단 | `status`에 reviewed=N + feedback 존재 | "리뷰 계속" |
| Test 실패 수정 중 | `status`에 tested=N | "테스트 계속" |
| Merge까지 완료 | all merged | "테스트 진행" |

### 부분 reset

특정 단계만 초기화하고 재수행:

```bash
oma db reset --step review --only "mapper_a.xml:selectUser"
```

---

## Claude Code 세션 관리

### 긴 세션 대응

대규모 변환은 단일 세션으로 완료되지 않을 수 있다:

- **컨텍스트 한도 접근 시**: `/clear` 로 컨텍스트 리셋 후 "변환 계속" (DB 상태 유지)
- **작업 분할**: Transform 완료 후 세션 종료 → 새 세션에서 Review부터 시작
- **진행 확인**: 매 세션 시작 시 `oma status`로 현 위치 파악

### 권장 세션 단위

| 단계 | 세션 1회 처리 권장량 |
|------|---------------------|
| Analyze | 전체 (1회로 충분) |
| Transform | 100~150 SQL |
| Review | Transform과 동일 범위 |
| Validate → Merge → Test | 나머지 한 세션에 |

### 세션 간 인수인계

별도 인수인계 문서 불필요 — `oma status --json`이 모든 상태를 포함.
새 세션에서 "변환 시작" 또는 "상태 확인" 하면 자동으로 현 위치 파악.

---

## DB 백업

### 자동 백업 없음

현재 OMA CLI는 자동 백업을 수행하지 않는다.
대규모 프로젝트에서는 단계 전환점마다 수동 백업을 권장:

```bash
cp output/oma_control.db output/oma_control.db.bak_$(date +%Y%m%d_%H%M)
```

### 권장 백업 시점

- Analyze 완료 직후
- Transform 전체 완료 직후
- Review 3라운드 종료 후
- Test 전체 완료 후 (최종 상태)

---

## 문제 해결

### Transform이 느린 경우

- 원인: mapper당 SQL 수가 많아 배치 분할이 많음
- 대응: `--max-batch 10` 으로 배치를 더 작게 분할 (subagent 작업량 감소)

### Review FAIL이 반복되는 패턴

- 원인: Tier 1 룰에 누락된 프로젝트 특수 패턴
- 대응:
  1. `oma db feedback-patterns --json` 으로 실패 사유 수집
  2. oma-strategy-refiner subagent가 자동 보강 (3라운드 초과 시)
  3. 필요 시 `output/strategy/transform_strategy.md` 수동 편집

### 세션 복구 불가

- 원인: DB 파일 손상 (극히 드묾)
- 대응: 백업에서 복구 후 `oma status`로 상태 확인

### Test 실패율이 높은 경우

- Target DB에 필요한 테이블/함수가 누락되었을 수 있음
- `oma test-exec --phase 0` (EXPLAIN만)으로 먼저 syntax 검증
- schema 관련 실패는 인프라 문제 — DB 환경 점검 필요
