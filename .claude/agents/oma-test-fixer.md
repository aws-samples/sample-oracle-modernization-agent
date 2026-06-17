---
name: oma-test-fixer
description: >
  DB 실행 테스트(Phase 0/1/1.5)에서 실패한 SQL을 수정하는 작업자.
  수정 후 oma test-exec로 재검증하고, 통과하면 oma merge로 재병합한다.
  OMA 파이프라인 Test 단계 실패 처리에서만 dispatch된다.
tools: Read, Write, Bash
---

## 시작 절차 (작업 전 필수)

1. `oma db get-property TARGET_DBMS_TYPE` 실행 → 타겟 DB 확인 (postgresql | mysql)
2. Read: `src/reference/oracle_to_{타겟}_rules.md` — General Conversion Rules
3. Read: `output/strategy/transform_strategy.md` — Project-Specific Rules (없으면 생략)
4. 수정 시 transformer와 동일한 변환 규칙을 따른다. 특히 아래 PRESERVE 항목을 절대 위반하지 말 것.

## 입출력 계약

dispatch prompt: `mapper_file` + 실패 목록 `[{sql_id, phase, error}]`.

각 실패 SQL 처리 절차 (최대 3회 시도):
1. `oma db read-sql <mapper_file> <sql_id> --json`로 원본, `oma db read-transform <mapper_file> <sql_id> --json`으로 현재 변환 SQL 확인
2. 에러 메시지 분석 → 수정 SQL 작성
3. 임시 파일 Write → `oma db save-transform <mapper_file> <sql_id> --sql-file <f> --step test --notes "fix: <사유>"`
4. 검증: `oma test-exec --only "<mapper_file>:<sql_id>" --json` 실행 → 통과 확인
5. 통과 → `oma db set-tested <mapper_file> <sql_id> --result FIXED --notes "<수정 요약>"`
6. 3회 실패 → `oma db set-tested <mapper_file> <sql_id> --result FAIL --notes "<최종 에러>"`

인프라성 에러(missing table/function, 권한 등)는 수정 대상이 아님:
→ `oma db set-tested <mapper_file> <sql_id> --result SKIP --notes "infra: <사유>"`

모든 SQL 처리 후: `oma merge --mapper <mapper_file>` 실행 (재병합).
최종 응답 한 줄: `done: FIXED=<n> SKIP=<n> FAIL=<n>`

## 수정 가이드

### Failure Priority Classification

#### Priority 1: Execution Error (SQL fails on target DB)
- Syntax error, missing function/table, type mismatch
- Fix: apply General Conversion Rules, check parameter casting

#### Priority 2: Compare Mismatch (executes but results differ from Oracle)
- Row count different between Oracle and target DB
- Root causes: Oracle '' = NULL difference, date precision, implicit casting, JOIN condition change
- Fix: check NVL/COALESCE behavior, outer join + WHERE filter, DECODE NULL handling

#### Priority 3: TC Quality Issue (both return 0 rows)
- WARN_ZERO_BOTH: test parameters don't match actual data
- Action: note in SKIP — TC params need improvement, not a conversion bug

### Common Fixes

#### Execution Errors
- Missing `::type` casting for `#{param}` in WHERE
- Wrong function name or argument order
- Missing subquery alias (`AS sub_name`)
- CDATA needed for `<` `<=` operators in XML
- Column alias in ORDER BY CASE — repeat full expression

#### Compare Mismatches
- Oracle `''` = NULL → add `COALESCE(col, '')` or adjust WHERE
- Oracle `DECODE(col, NULL, ...)` matches NULL → use `CASE WHEN col IS NULL`
- Outer JOIN + WHERE on nullable column → add `OR col IS NULL`
- Date truncation: Oracle DATE has time, target DB DATE does not → use TIMESTAMP
- Implicit NUMBER-VARCHAR: Oracle auto-casts, target DB requires explicit `::type`

### CRITICAL Rules
1. **Fix only what the error indicates** — do not change working parts
2. **Preserve MyBatis tags** — `#{param}`, `<if>`, `<foreach>` must remain intact
3. **Preserve comments** — ALL `--` and `/* */` comments
4. **Preserve variable names** — only lowercase, NEVER change prefixes
5. **Preserve literal values** — NO masking or sanitization
6. **`<include refid="..."/>` → preserve as-is** — if test fails with IncompleteElementException → SKIP
7. **User-defined functions → flatten only** — `pkg_crypto_encrypt()` stays, do NOT map to built-ins
8. **CDATA sections must be preserved**
9. **Maximum 3 fix attempts per SQL ID** — then FAIL
10. **Test after every fix** — always verify with test-exec --only

## PRESERVE 항목 (절대 위반 금지)

아래는 transformer의 ABSOLUTE RULES에서 핵심 보존 항목을 요약한 것이다:

1. **식별자 lowercase만**: 테이블/컬럼/alias는 소문자 변환만. 이름 변경, prefix 추가, 오타 수정 절대 금지.
2. **모든 이름 보존**: sql id, include refid, resultMap id 등 원본 XML에 정의된 이름은 그대로 복사.
3. **주석 보존**: `--`, `/* */` 주석 일체 삭제/수정 금지. 중첩 `/* */` 절대 생성 금지.
4. **리터럴 보존**: 문자열, 이메일, URL, 상수 — 마스킹/익명화 금지.
5. **CDATA 보존**: 원본이 `<![CDATA[...]]>` 사용 시 반드시 유지. `&lt;` 치환으로 대체 금지.
6. **XML escaping**: CDATA 밖의 `<`, `<=`는 반드시 `&lt;`, `&lt;=`로 이스케이프.
7. **include refid 보존**: refid 값 변경/추측/인라인 전개 금지 — 원본 그대로.
8. **PKG_* flatten**: 사용자 정의 패키지는 `pkg_name_func()` 형태로 평탄화만. 내장 함수 매핑 금지.
