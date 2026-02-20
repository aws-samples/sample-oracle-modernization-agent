# SQL Review Agent

General Rules 준수 여부를 체크하는 리뷰 Agent.

## 역할
- 변환된 SQL이 General Conversion Rules를 모두 따르는지 검사
- 위반 사항만 보고 (수정하지 않음)
- FAIL 시 Transform Agent가 재변환

## 도구
| 도구 | 설명 |
|------|------|
| `get_pending_reviews()` | reviewed='N'인 SQL 목록 |
| `read_sql_source()` | 원본 Oracle SQL 읽기 |
| `read_transform()` | 변환된 PostgreSQL SQL 읽기 |
| `set_reviewed()` | PASS/FAIL 결과 기록 |

## 파이프라인 위치
```
Transform → [Review] → Validate → Test
              ↓ FAIL
           Transform 재호출
```

## 실행
```bash
python3 src/run_sql_review.py --workers 8
python3 src/run_sql_review.py --reset --workers 8  # 리뷰 초기화 후 재실행
```
