# Plan: Multi-Target DB Support (MySQL 추가)

## Executive Summary

| Perspective | Description |
|-------------|-------------|
| **Problem** | 현재 Target DB가 PostgreSQL로 하드코딩되어 있어 MySQL 등 다른 타겟 DB를 지원할 수 없다. 코드/프롬프트/룰/문서 전체에 ~55개 파일에서 PostgreSQL이 참조됨. |
| **Solution** | TARGET_DBMS_TYPE 설정값을 기반으로 변환 룰, 프롬프트, 메타데이터, 테스트 도구가 동적으로 타겟 DB에 맞게 동작하도록 추상화한다. |
| **Function UX Effect** | `run_setup.py`에서 TARGET_DBMS_TYPE=mysql 선택 시, 동일한 파이프라인으로 Oracle→MySQL 변환이 수행된다. |
| **Core Value** | 하나의 도구로 PostgreSQL과 MySQL 두 타겟을 지원하여 OMA의 적용 범위를 확장한다. |

---

## 1. 현황: PostgreSQL 하드코딩 전수 조사 (55개 파일)

### High Impact (새 코드 필요 — 12개)

| Category | File | What is PG-specific |
|----------|------|---------------------|
| **Rules** | `reference/oracle_to_postgresql_rules.md` | 전체 변환 룰 (545줄) |
| **Metadata** | `agents/sql_transform/tools/metadata.py` | `psql` CLI, PG env vars, `pg_metadata` 테이블, PG 시스템 스키마 |
| **Test** | `agents/sql_test/tools/test_tools.py` | `psql EXPLAIN`, `run_postgresql.sh`, PG env vars |
| **Test** | `run_sql_test.py` | `pg_connection.properties` 생성 |
| **Setup** | `run_setup.py` | PG env var 프롬프트, `psql` 접속 테스트, SSM path `/oma/target_postgres/` |
| **ORM** | `core/models.py` | `pg_metadata` 테이블명 |
| **Analyzer** | `source_analyzer/tools/sql_extractor.py` | `ORACLE_PATTERNS`의 4번째 필드 (PG equivalent) |
| **Shell** | `reference/run_postgresql.sh` | 전체 PG 테스트 스크립트 |
| **Shell** | `reference/setup_oma_control.sh` | `TARGET_DBMS_TYPE='postgres'` 하드코딩 |
| **Config** | `reference/pg_connection.properties` | PG 접속 설정 |
| **Orch** | `orchestrator/tools/orchestrator_tools.py:389` | "No PostgreSQL connection info" 문자열 매칭 |
| **Java** | `reference/com/test/mybatis/` (4개 파일) | PG JDBC (이미 부분적으로 multi-target) |

### Medium Impact (프롬프트 재작성 — 9개)

| File | What needs to change |
|------|---------------------|
| `agents/sql_transform/prompt.md` | "PostgreSQL migration expert" → 타겟 DB별 전문가 |
| `agents/sql_review/prompt.md` | PG-specific 체크리스트 |
| `agents/sql_review/prompt_syntax.md` | PG 구문 체크리스트 |
| `agents/sql_review/prompt_equivalence.md` | Oracle vs PG 동작 차이 → Oracle vs MySQL 동작 차이 |
| `agents/sql_validate/prompt.md` | Oracle vs PG 동작 차이 |
| `agents/sql_test/prompt.md` | "PostgreSQL migration expert" |
| `agents/orchestrator/prompt.md` | "Test against PostgreSQL" |
| `agents/review_manager/prompt.md` | "Oracle and PostgreSQL" |
| `agents/strategy_refine/prompt.md` | PG 예시 |

### Low Impact (문자열 교체 — ~34개)

README.md, CLAUDE.md, PROJECT_OVERVIEW.md, docs/ 디렉토리 전체, docstring, 배너 텍스트 등.

---

## 2. 설계 방향

### 2.1 핵심 원칙

```
TARGET_DBMS_TYPE (DB properties에 저장)
  → 변환 룰 파일 선택
  → 프롬프트 동적 로딩
  → 메타데이터 추출 도구 분기
  → 테스트 도구 분기
  → 문서/배너 동적 표시
```

### 2.2 변환 룰 구조

```
src/reference/
├── oracle_to_postgresql_rules.md   ← 기존 (PostgreSQL용)
├── oracle_to_mysql_rules.md        ← 신규 (MySQL용)
└── common_oracle_rules.md          ← 공통 (구조 변환 등, optional)
```

| 항목 | PostgreSQL | MySQL |
|------|-----------|-------|
| NVL | COALESCE | IFNULL or COALESCE |
| DECODE | CASE WHEN | CASE WHEN (동일) |
| SYSDATE | CURRENT_TIMESTAMP | NOW() or CURRENT_TIMESTAMP |
| (+) outer join | LEFT JOIN | LEFT JOIN (동일) |
| ROWNUM | LIMIT/OFFSET | LIMIT/OFFSET (동일) |
| CONNECT BY | WITH RECURSIVE | WITH RECURSIVE (MySQL 8.0+) |
| MERGE | INSERT ON CONFLICT | INSERT ON DUPLICATE KEY UPDATE |
| LISTAGG | STRING_AGG | GROUP_CONCAT |
| || (concat) | || (SQL standard) | CONCAT() (MySQL에서 ||은 OR) |
| SEQ.NEXTVAL | nextval('seq') | AUTO_INCREMENT 또는 별도 시퀀스 테이블 |
| TO_DATE | to_date() / ::date | STR_TO_DATE() |
| SUBSTR | SUBSTRING | SUBSTRING (동일) |
| MONTHS_BETWEEN | EXTRACT + AGE | TIMESTAMPDIFF(MONTH, ...) |
| MINUS | EXCEPT | NOT EXISTS subquery (MySQL 8.0 미만) 또는 EXCEPT (8.0.31+) |

### 2.3 수정 레이어별 계획

#### Layer 1: Rule System (새 파일)
- `oracle_to_mysql_rules.md` 작성 (~500줄 예상)
- MySQL 특유의 주의사항 포함 (backtick quoting, strict mode, sql_mode 등)

#### Layer 2: Rule Loader (코드 수정)
- `run_sql_transform.py:load_prompt()` — `TARGET_DBMS_TYPE`에 따라 룰 파일 선택
- `agents/sql_review/perspectives.py` — 룰 파일 경로 동적
- 다른 agent factory들도 동일 패턴

#### Layer 3: Prompt Templates (프롬프트 수정)
- 각 agent prompt.md에서 "PostgreSQL"을 `{TARGET_DBMS}` placeholder로 교체하는 대신,
  **프롬프트 로딩 시 TARGET_DBMS_TYPE을 주입**하는 방식
  ```python
  prompt_text = prompt_text.replace("{{TARGET_DB}}", target_dbms.upper())
  ```

#### Layer 4: Metadata (코드 분기)
- `metadata.py` — TARGET_DBMS_TYPE에 따라 `psql` vs `mysql` CLI 사용
- MySQL: `mysql -e "SELECT table_schema, table_name, column_name, data_type FROM information_schema.columns ..."`
- 테이블명: `pg_metadata` → `target_metadata` (범용)

#### Layer 5: Test Tools (코드 분기)
- `test_tools.py` — TARGET_DBMS_TYPE에 따라 psql vs mysql 사용
- `run_postgresql.sh` → `run_test.sh` (TARGET_DBMS_TYPE 파라미터)
- Java 도구는 이미 `--db mysql` 지원

#### Layer 6: Setup (코드 수정)
- `run_setup.py` — TARGET_DBMS_TYPE 선택에 따라 접속 정보 프롬프트 분기
  - PostgreSQL: PGHOST, PGPORT, ...
  - MySQL: MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE, MYSQL_USER, MYSQL_PASSWORD
- SSM path: `/oma/target_postgres/` → `/oma/target_{dbms}/`

#### Layer 7: Display Strings (일괄 치환)
- 배너, docstring, README 등에서 하드코딩된 "PostgreSQL" → 동적 또는 범용 표현

---

## 3. 수정 파일 요약 (우선순위순)

### Phase 1: Core (변환이 동작하려면 필수)

| Priority | File | Change |
|----------|------|--------|
| P0 | `reference/oracle_to_mysql_rules.md` | **신규** — MySQL 변환 룰 |
| P0 | `run_sql_transform.py:load_prompt()` | TARGET_DBMS_TYPE으로 룰 파일 선택 |
| P0 | 각 agent의 `agent.py` | 룰 파일 경로 동적 로딩 |
| P0 | 각 agent의 `prompt.md` (9개) | `{{TARGET_DB}}` placeholder + 로딩 시 치환 |

### Phase 2: Metadata & Test (검증이 동작하려면 필수)

| Priority | File | Change |
|----------|------|--------|
| P1 | `metadata.py` | MySQL 메타데이터 추출 분기 |
| P1 | `core/models.py` | `pg_metadata` → `target_metadata` 테이블명 |
| P1 | `test_tools.py` | MySQL EXPLAIN/테스트 분기 |
| P1 | `run_sql_test.py` | MySQL 접속 설정 생성 |
| P1 | `reference/run_test.sh` | 범용 테스트 스크립트 (또는 `run_mysql.sh` 추가) |

### Phase 3: Setup & Config

| Priority | File | Change |
|----------|------|--------|
| P2 | `run_setup.py` | MySQL 접속 정보 프롬프트 분기 |
| P2 | `source_analyzer/tools/sql_extractor.py` | MySQL equivalent 매핑 추가 |
| P2 | `orchestrator/tools/orchestrator_tools.py` | "No PostgreSQL" → 범용 메시지 |

### Phase 4: Display & Docs

| Priority | File | Change |
|----------|------|--------|
| P3 | README.md, CLAUDE.md, docs/ 등 (~34개) | "PostgreSQL" → "PostgreSQL/MySQL" 또는 동적 |

---

## 4. 주요 기술 결정

### 4.1 룰 파일 분리 vs 통합?
**분리 (추천)** — `oracle_to_postgresql_rules.md` + `oracle_to_mysql_rules.md`
- 이유: MySQL과 PostgreSQL의 동작 차이가 크므로 하나의 파일로 관리하면 복잡도 폭증
- 공통 부분 (Phase 1 구조 변환)은 중복되지만, 유지보수성이 더 중요

### 4.2 프롬프트 placeholder vs 조건 분기?
**Placeholder 치환 (추천)** — `{{TARGET_DB}}`를 로딩 시 교체
- 이유: 프롬프트 파일을 DB별로 복제하면 유지보수 불가
- 대부분의 프롬프트는 "PostgreSQL"을 "MySQL"로 바꾸면 됨
- DB별 동작 차이는 룰 파일에서 커버

### 4.3 DB별 메타데이터 테이블?
**하나의 테이블 (추천)** — `target_metadata` (현재 `pg_metadata` rename)
- 프로젝트 설정에 따라 PostgreSQL 또는 MySQL 메타데이터가 저장됨
- 동시에 두 DB를 타겟으로 하지 않으므로 분리 불필요

---

## 5. 작업량 추정

| Phase | 파일 수 | 예상 규모 |
|-------|---------|----------|
| Phase 1 (Core) | ~15개 | `oracle_to_mysql_rules.md` 신규 작성 + prompt placeholder |
| Phase 2 (Meta/Test) | ~6개 | metadata/test 분기 로직 |
| Phase 3 (Setup) | ~3개 | setup 분기 |
| Phase 4 (Docs) | ~34개 | 문자열 치환 (기계적) |

---

## 6. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| MySQL 변환 룰 품질 | 변환 실패 | PostgreSQL 룰을 base로 MySQL 차이점만 수정 |
| MySQL 8.0 미만 지원 | EXCEPT, WITH RECURSIVE 미지원 | MySQL 8.0+ 필수로 제한 |
| 프롬프트 placeholder 치환 누락 | Agent가 잘못된 DB 참조 | 치환 후 "PostgreSQL" grep으로 잔존 확인 |
| `||`가 MySQL에서 OR | 심각한 변환 오류 | MySQL 룰에서 `CONCAT()` 필수 변환으로 명시 |

---

## 7. 결론

**전체 55개 파일에 PostgreSQL 참조가 있지만, 핵심 수정은 Phase 1~2의 ~20개 파일**입니다. 특히 `oracle_to_mysql_rules.md` 신규 작성이 가장 큰 작업이고, 나머지는 분기 로직 + 문자열 치환입니다.

---

*Created: 2026-03-15*
*Status: Draft*
