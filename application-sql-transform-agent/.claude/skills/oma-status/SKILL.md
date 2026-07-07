---
name: oma-status
description: >
  Use when the user asks about OMA pipeline progress: "status", "상태",
  "어디까지 했어", "진행 상황", "/oma:status".
---

# OMA Status

1. `oma status --json` 실행.
2. 단계별 카운트를 표로 요약 (extracted/transformed/reviewed/validated/merged/tested).
3. 실패 카운트(review_failed, validate_failed, test_failed)가 있으면 강조하고
   다음 행동 옵션을 제시한다. 진행 판단 절차는 oma-pipeline skill 참조.
