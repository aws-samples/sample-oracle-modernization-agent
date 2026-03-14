# Plan: oma_metadata.txt를 OUTPUT_DIR로 이동

## Executive Summary

| Perspective | Description |
|-------------|-------------|
| **Problem** | `oma_metadata.txt`가 소스 디렉토리(`src/agents/sql_transform/`)에 존재하며, 실제 고객 DB 스키마가 git에 커밋될 위험이 있다. |
| **Solution** | metadata txt 파일 생성을 `OUTPUT_DIR` 하위로 이동하고, Java 테스트 도구도 해당 경로를 참조하도록 통일한다. |
| **Function UX Effect** | 별도 조치 없이 실행 결과물이 자동으로 output 디렉토리에 정리된다. |
| **Core Value** | 소스와 실행 결과물의 분리로 보안 위험 제거 및 프로젝트 구조 일관성 확보. |

---

## 1. 현황 분석

### oma_metadata.txt의 역할
- PostgreSQL `information_schema.columns`에서 추출한 컬럼 메타데이터 (table_name, column_name, data_type)
- Transform 시 파라미터 타입 캐스팅에 사용

### 현재 저장 경로 (2곳 중복)

| 저장소 | 위치 | 생성 주체 | 사용 주체 |
|--------|------|-----------|-----------|
| **DB 테이블** `pg_metadata` | `OUTPUT_DIR/oma_control.db` | `metadata.py:generate_metadata()` | `metadata.py:lookup_column_type()` |
| **txt 파일** `oma_metadata.txt` | `src/agents/sql_transform/` (과거 잔존) | 현재 코드에서 **생성하지 않음** | `MyBatisBulkPreparator.java` (Java 테스트) |

### 문제점
1. **txt 파일은 생성 코드가 없다** — 과거 버전의 잔존물이 소스에 남아 있었음 (이미 git에서 제거)
2. **Java 테스트 도구가 txt 파일을 참조** — `APP_TRANSFORM_FOLDER/oma_metadata.txt` 또는 mapper 경로에서 찾음
3. **DB 테이블과 txt 파일이 이중 관리** — 어느 것이 진실인지 불명확

---

## 2. 목표

- `generate_metadata()`가 DB 저장과 함께 `OUTPUT_DIR/metadata/oma_metadata.txt`도 생성
- Java 테스트 도구가 `OUTPUT_DIR/metadata/oma_metadata.txt`를 참조
- 소스 디렉토리에는 실행 결과물 없음

---

## 3. 수정 범위

| File | Change |
|------|--------|
| `src/agents/sql_transform/tools/metadata.py` | `generate_metadata()` 끝에 txt 파일을 `OUTPUT_DIR/metadata/oma_metadata.txt`로 저장 |
| `src/agents/sql_transform/README.md` | `oma_metadata.txt` 항목 제거 (더 이상 이 디렉토리에 없음) |
| `.gitignore` | `src/agents/sql_transform/oma_metadata.txt` → 불필요 (파일 자체가 없으니) |

---

## 4. 수정하지 않는 것

| File | Reason |
|------|--------|
| `MyBatisBulkPreparator.java` | 이미 `APP_TRANSFORM_FOLDER` 환경변수로 경로를 받음. `run_sql_test.py`에서 설정하면 됨 |
| DB 테이블 (`pg_metadata`) | 변경 없음 — Python에서의 lookup은 그대로 DB 사용 |

---

*Created: 2026-03-15*
*Status: Draft*
