---
name: oma-start
description: >
  Use when the user says "start", "시작", "/oma:start", "변환 시작",
  or asks to begin/continue the Oracle SQL transformation project.
---

# OMA Start

1. oma-pipeline skill을 먼저 로드하라 (Skill tool) — 전체 절차가 거기 있다.
2. `oma status --json` 실행.
3. 결과에 따라:
   - DB 없음 → Setup부터 (oma-pipeline §0)
   - 진행 중 → 현재 단계 요약 + 해당 단계 체크포인트 제시
   - 전부 완료 → 최종 산출물 안내 (oma-pipeline §7)
