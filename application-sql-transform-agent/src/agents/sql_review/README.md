# SQL Review Agent

다관점 리뷰로 변환 품질을 검증하는 Agent. Syntax + Equivalence 두 관점에서 독립 리뷰 후 Facilitator가 결과를 통합한다.

## 역할
- 변환된 SQL이 General Conversion Rules를 모두 따르는지 검사 (Syntax Agent)
- 원본 Oracle SQL과 기능적으로 동등한지 검사 (Equivalence Agent)
- 위반 사항만 보고 (수정하지 않음)
- FAIL 시 구체적 피드백과 함께 Transform Agent가 재변환

## 다관점 리뷰 구조

```
Transform 결과 →
  ├── Syntax Agent (병렬)     → JSON {perspective, results}
  └── Equivalence Agent (병렬) → JSON {perspective, results}
  → Facilitator (Python 함수) → 통합 PASS/FAIL + 피드백 JSON
  → set_reviewed() + review_result 컬럼 저장
```

## 파일 구조

| 파일 | 설명 |
|------|------|
| `agent.py` | Agent 팩토리 (단일 + 다관점 re-export) |
| `perspectives.py` | 다관점 리뷰 핵심 로직 + Facilitator |
| `prompt_syntax.md` | Syntax Agent 전용 프롬프트 |
| `prompt_equivalence.md` | Equivalence Agent 전용 프롬프트 |
| `prompt.md` | 기존 단일 Agent 프롬프트 (하위 호환) |
| `tools/review_tools.py` | `get_pending_reviews`, `set_reviewed` |

## 도구 (Perspective Agent용, 읽기 전용)

| 도구 | 설명 |
|------|------|
| `read_sql_source()` | 원본 Oracle SQL 읽기 |
| `read_transform()` | 변환된 PostgreSQL SQL 읽기 |

## 파이프라인 위치
```
Transform → [Review: Syntax + Equivalence] → Validate → Test
                     ↓ FAIL (구체적 피드백)
                  Transform 재호출
```

## 실행
```bash
python3 src/run_sql_review.py --workers 8
python3 src/run_sql_review.py --reset --workers 8  # 리뷰 초기화 후 재실행
```
