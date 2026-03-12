# Strategy Refine Agent

전략 파일(`output/strategy/transform_strategy.md`)을 관리하는 Agent입니다.

## 역할

1. **패턴 추가** — Validate/Test 실패 패턴을 Before/After SQL 형식으로 정제하여 추가
2. **중복 제거** — General Rules와 중복되는 패턴 제거
3. **압축** — 유사 패턴 병합, 불필요한 항목 제거

## 도구

| 도구 | 설명 |
|------|------|
| `read_strategy()` | 현재 전략 파일 읽기 |
| `get_feedback_patterns(source)` | signal/log 파일에서 raw 패턴 수집 |
| `append_patterns(section, patterns_md)` | 특정 섹션에 패턴 추가 |
| `write_strategy(content)` | 전체 파일 덮어쓰기 (압축용) |

## 호출 시점

- `run_sql_validate.py` — Validate 완료 후 자동 호출
- `run_sql_test.py` — Test 완료 후 자동 호출
- `run_strategy.py --task compact_strategy` — 수동 압축
- `run_strategy.py --task refine` — 수동 보강

## 시스템 프롬프트

General Rules(`oracle_to_postgresql_rules.md`)를 캐시 블록으로 포함하여 중복 패턴 판별 가능.
