---
name: oma-pipeline
description: >
  Use when the user wants to run/continue the OMA SQL transform pipeline
  (Oracle→PostgreSQL/MySQL MyBatis mapper conversion), check its status,
  or handle a specific step: analyze, transform, review, validate, merge, test.
---

# OMA Pipeline Orchestration

너(메인 세션)는 OMA 파이프라인의 오케스트레이터다. LLM 작업은 subagent에게,
결정적 작업은 `oma` CLI에 위임한다. 직접 SQL을 변환하지 마라.

## 불변 원칙

1. **상태의 SSOT는 DB다.** 진행 판단은 항상 `oma status --json`으로 시작한다.
2. **체크포인트 승인형.** 각 단계가 끝나면 결과를 요약하고 사용자에게
   다음 행동을 묻는다. 사용자 승인 없이 다음 단계로 자동 진행하지 않는다.
3. **병렬 dispatch는 최대 5개.** 배치가 더 많으면 5개 단위로 나눠 순차 dispatch.
4. **subagent 응답은 파싱하지 않는다.** dispatch 후 결과 집계는 `oma status --json`
   재조회로 한다. subagent의 한 줄 응답은 참고용일 뿐이다.
5. **모든 oma CLI 호출은 `OMA_OUTPUT_DIR`가 설정된 환경에서 실행한다.** 세션 시작 시
   사용자가 지정한 작업 디렉토리를 유지한다 (예: `example/output`).

## 단계별 절차

### 0. Setup
`oma status` 실행이 "DB not found"면: 사용자에게 소스 경로·타겟 DB를
물은 뒤 `oma setup --non-interactive --source <path> --target-db <db>`.
DB 접속 정보는 Test 단계 전까지 불필요하다고 안내.

### 1. Analyze
```
oma analyze --json
```
완료 후 요약 표시 (mapper 수, SQL 수, 메타데이터 상태) +
`output/strategy/transform_strategy.md` 초안 존재 안내.
체크포인트: [전체 변환 진행 / 샘플 N건만 / 전략 파일 검토·수정 / 중단]

### 2. Transform
```
oma db pending --step transform --json
```
batches 배열의 각 항목마다 oma-transformer를 dispatch (병렬, 최대 5):

> dispatch prompt 템플릿:
> "mapper_file: {mapper_file} (part {part}/{parts})
>  sql_ids: {sql_ids 쉼표 목록}
>  target DB: {TARGET_DBMS_TYPE 값}
>  OMA_OUTPUT_DIR={현재 작업 디렉토리}
>  위 SQL들을 변환하고 oma db save-transform으로 기록하라."

전체 완료 후 `oma status --json`으로 집계.
체크포인트: 성공/실패 요약 → [Review 진행 / 실패 건 재시도 / 중단]
실패 재시도: `oma db pending --step transform --only "<실패 목록>"`으로 배치 재생성.

### 3. Review (최대 3 라운드)
```
oma db pending --step review --json
```
각 배치를 oma-reviewer로 dispatch (transform과 동일 패턴).
라운드 종료 후 `oma status --json`의 review_failed 확인:

- review_failed == 0 → Validate로
- review_failed > 0 → 체크포인트: FAIL 목록 + 사유 요약 표시
  [자동 재변환 / 해당 SQL 건너뛰기 / 수동 확인]
  - 자동 재변환 선택 시:
    a. 라운드 2 이상이면 먼저 oma-strategy-refiner를 dispatch (1개, 직렬)
    b. FAIL 건의 피드백을 모아 oma-transformer dispatch
       (dispatch prompt에 SQL별 피드백 포함 — `oma db feedback-patterns --json`로 수집)
    c. `oma db reset --step review --only "<해당 건>"` 후 재리뷰
  - 3라운드 후에도 FAIL → 사용자에게 수동 처리 목록으로 보고

### 4. Validate
```
oma db pending --step validate --json
```
oma-validator dispatch (동일 패턴).
체크포인트: FAIL 건(validator가 수정 불가 판정) 목록 + 사유 →
건별 또는 일괄 [승인하고 진행 / 재변환 지시 / 중단]

### 5. Merge
```
oma merge --json
```
결정적 작업 — subagent 불필요. 완료 후 merged/skipped 요약.
체크포인트: [Test 진행 / 특정 mapper diff 확인 / 종료(Test 생략)]
diff 확인 요청 시: `output/xmls/origin/`과 `output/xmls/merge/`의 해당 파일을 Read해 비교 요약.

### 6. Test
```
oma test-exec --json
```
failures 배열이 비면 완료. 실패가 있으면 체크포인트:
[oma-test-fixer로 자동 수정 / SKIP 처리 / 수동]
- 자동 수정: mapper별로 failures를 묶어 oma-test-fixer dispatch
- SKIP: `oma db set-tested <m> <s> --result SKIP --notes "<사용자 사유>"`
test-fixer는 수정 후 자체적으로 `oma test-exec --only`로 재검증하고 `oma merge --mapper`로 재병합한다.

### 7. 종료
`oma report` 실행 → 사용자에게 안내:
- 최종 mapper: `output/xmls/merge/`
- HTML 리포트: `output/reports/oma_report.html`

## 중단/재개

세션이 끊겨도 상태는 DB에 있다. 사용자가 돌아오면 `oma status --json`으로
현재 위치를 파악하고 해당 단계의 체크포인트부터 재개한다.
