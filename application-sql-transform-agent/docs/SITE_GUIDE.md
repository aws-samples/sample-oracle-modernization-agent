# 현장 적용 가이드 (Site Runbook)

실제 고객 소스를 변환할 때의 처음~끝 절차. example이 아닌 **실 프로젝트** 기준이다.
(example 데모는 `example/README.md` 참조)

---

## 0. 사전 준비

| 항목 | 확인 방법 |
|------|-----------|
| Claude Code CLI | `claude --version` |
| Python 3.11+ | `python3 --version` |
| uv | `uv --version` |
| Claude Code 인증 | `claude --version` (subagent가 변환에 사용; Bedrock provider 설정 시 `aws sts get-caller-identity`도 확인) |
| 변환 대상 소스 | 고객 Java/MyBatis 프로젝트 (mapper XML 포함) |
| psql/mysql CLI | **Test 단계만 필요** — `psql --version` / `mysql --version` |

```bash
git clone <this-repo> && cd application-sql-transform-assistant
uv sync
```

---

## 1. 소스 위치 지정 (가장 먼저 결정할 것)

`oma`는 **mapper XML이 들어있는 소스 루트 디렉토리**를 스캔한다. 두 가지 방식 중 선택:

### 방식 A — 소스를 그 자리에 두고 절대경로로 가리키기 (권장)
고객 소스를 repo 밖 아무 곳에나 두고, 그 경로를 setup에 넘긴다. repo를 더럽히지 않음.

```bash
# 예: 고객 소스가 ~/work/customer-app 에 있을 때
SOURCE_ROOT=~/work/customer-app/src/main/resources    # mapper XML들이 이 아래에 있어야 함
```

> `SOURCE_ROOT`는 mapper `*.xml`이 (하위 디렉토리 포함) 들어있는 최상위 폴더면 된다.
> analyze가 그 아래를 재귀로 스캔한다. Java 소스 루트든 resources 폴더든, mapper만 그 안에 있으면 됨.

### 방식 B — repo 안으로 복사
```bash
cp -r ~/work/customer-app/src ./customer-src
SOURCE_ROOT=$(pwd)/customer-src
```

---

## 2. 작업 디렉토리(OMA_OUTPUT_DIR) 결정

변환 중간 산출물·상태 DB·리포트가 모두 여기 쌓인다. **프로젝트마다 분리**하는 걸 권장.

```bash
export OMA_OUTPUT_DIR=~/work/customer-app-oma-output
```

> 이 환경변수는 **세션 내내 유지**해야 한다. 모든 `oma` 명령과 subagent가 이걸 본다.
> 새 터미널 탭을 열면 다시 export.

---

## 3. Setup — 설정을 DB에 저장

### 3-1. 기본 설정 (소스 경로 + 타겟 DB)

```bash
uv run oma setup --non-interactive \
  --source "$SOURCE_ROOT" \
  --target-db postgresql     # 또는 mysql
```

이것만으로 Merge 단계까지(= 변환의 대부분) 진행 가능하다. DB 연결 불필요.

### 3-2. Test 단계까지 하려면 — DB 접속정보 추가

Test(실 DB 실행 검증)까지 하려면 접속정보가 필요하다. **비밀번호를 제외한** 접속정보
(host/port/database/user)는 `--non-interactive` 플래그로 한 번에 넣을 수 있다.
비밀번호는 보안상 플래그로 받지 않으며, 환경변수 또는 interactive 입력만 허용한다.

**(a) 플래그로 한 번에** (권장 — CI/자동화에 적합)
```bash
# PostgreSQL 타겟 + Oracle 소스를 한 번에 설정
uv run oma setup --non-interactive \
  --source "$SOURCE_ROOT" --target-db postgresql \
  --pg-host db.example.com --pg-port 5432 --pg-database appdb --pg-user svc_user \
  --oracle-host ora.example.com --oracle-port 1521 \
  --oracle-service ORCLPDB1 --oracle-user migr

# 비밀번호는 환경변수로 (플래그 없음)
export PGPASSWORD=...
export ORACLE_SVC_PASSWORD=...
```
MySQL 타겟이면 `--mysql-host/--mysql-port/--mysql-database/--mysql-user` + `export MYSQL_PASSWORD=...`.

> 사용 가능한 접속 플래그: `--pg-*`, `--mysql-*`, `--oracle-*` (각 host/port/database(또는 service)/user).
> 일부만 줘도 되고, 준 것만 저장된다 (기존 값은 보존).

**(b) interactive setup으로 입력** (모든 값을 프롬프트로, 비밀번호 포함)
```bash
uv run oma setup          # 프롬프트에서 "Configure DB connections now? y" 선택
# Oracle(소스) + PostgreSQL/MySQL(타겟) 접속정보를 차례로 입력 (비밀번호는 getpass)
```

**(c) 전부 환경변수로** (세션 한정 — 일회성)
```bash
export PGHOST=... PGPORT=5432 PGDATABASE=... PGUSER=... PGPASSWORD=...
export ORACLE_HOST=... ORACLE_PORT=1521 ORACLE_SID=... ORACLE_USER=... ORACLE_PASSWORD=...
```

> 접속정보 해석 우선순위: **환경변수 > DB properties**. 둘 다 없으면 Test 단계에서 안내 후 중단.
> Oracle 접속정보가 없으면 Phase 1.5(Oracle-PG 결과 비교)는 자동 스킵되고 나머지는 진행.
> 비밀번호는 절대 DB properties에 플래그로 들어가지 않는다 — env var(권장) 또는 interactive getpass만.

### 3-3. 설정 확인
```bash
uv run oma status          # DB가 생겼는지, 추출 대상이 있는지(아직 0) 확인
```

---

## 4. 변환 실행 — Claude Code 세션

```bash
claude                     # OMA_OUTPUT_DIR이 export된 상태로 실행
```

세션 안에서:
```
변환 시작
```
(또는 `/oma:start`)

`oma-start` skill이 `oma status`로 현재 위치를 파악하고 파이프라인을 시작한다.

### 단계별 흐름 (각 단계 후 멈추고 승인을 물음)

```
Analyze → Transform → Review → Validate → Merge → Test
                        ↓ FAIL
                  재변환 (최대 3 라운드, 2라운드+엔 전략 학습 선행)
```

| 단계 | 하는 일 | 비고 |
|------|---------|------|
| Analyze | mapper 스캔, SQL 추출, 전략 초안 | DB 불필요 |
| Transform | Oracle→타겟 변환 (transformer subagent, mapper별 병렬 최대 5) | Bedrock 필요 |
| Review | 룰 준수 + 기능 동등성 2-pass 검토 | FAIL 시 재변환 분기 |
| Validate | 기능 동등성 검증 | 명백한 오류는 자동 수정 |
| Merge | 최종 mapper XML 재조립 (결정적, CLI) | DB 불필요 |
| Test | EXPLAIN + 실행 + Oracle 비교 | **DB 접속정보 필요** |

각 체크포인트에서 [다음 단계 진행 / 실패 건 재시도 / 특정 건 확인 / 중단] 중 선택한다.

---

## 5. 중단되면 — 이어서 하기

세션이 끊겨도 진행 상태는 `$OMA_OUTPUT_DIR/oma_control.db`에 SQL 1건 단위로 남는다.

```bash
export OMA_OUTPUT_DIR=~/work/customer-app-oma-output   # 같은 작업 디렉토리로
claude
# 세션에서: "변환 시작" → status를 읽고 끝난 단계는 건너뛰고 남은 것부터 재개
```

완료된 SQL은 다시 변환하지 않는다 (`pending`이 미완료 건만 반환).

---

## 6. 결과물

| 경로 | 내용 |
|------|------|
| `$OMA_OUTPUT_DIR/xmls/merge/` | **최종 변환된 mapper XML** (고객에게 전달할 산출물) |
| `$OMA_OUTPUT_DIR/reports/oma_report.html` | 통합 HTML 리포트 (단계별 결과) |
| `$OMA_OUTPUT_DIR/strategy/transform_strategy.md` | 이 프로젝트에서 학습된 변환 패턴 |
| `$OMA_OUTPUT_DIR/oma_control.db` | 상태 DB (진행/이력) |

```bash
open "$OMA_OUTPUT_DIR/reports/oma_report.html"
ls "$OMA_OUTPUT_DIR"/xmls/merge/**/*.xml
```

merge된 XML을 고객 프로젝트의 원래 mapper 위치에 적용하면 된다.

---

## 7. CLI 직접 사용 (참고)

claude 세션 없이 결정적 단계만 CLI로 돌릴 수도 있다 (변환·리뷰는 subagent가 필요하므로 세션에서):

```bash
uv run oma status --json                          # 진행 상황
uv run oma analyze --json                          # 스캔/추출
uv run oma db pending --step transform --json      # 변환 대상 배치 목록
uv run oma merge --json                            # 재조립
uv run oma test-exec --json                        # DB 실행 테스트
uv run oma report                                  # 리포트 재생성
uv run oma --help                                  # 전체 서브커맨드
```

---

## 8. 트러블슈팅

| 증상 | 원인 / 대응 |
|------|-------------|
| subagent가 변환을 안 함 | AWS Bedrock 자격증명 확인 (`aws sts get-caller-identity`) |
| `DB not found` | `OMA_OUTPUT_DIR`이 export됐는지, `oma setup`을 돌렸는지 확인 |
| analyze 결과 mapper 0건 | `--source` 경로 아래에 `*.xml` mapper가 있는지 확인 (경로 한 단계 위/아래일 수 있음) |
| Test가 "connection info" 안내 후 중단 | 3-2의 (a/b/c) 중 하나로 접속정보 입력 (비밀번호는 env var) |
| Phase 1.5(Oracle 비교)만 스킵됨 | Oracle 접속정보 없음 — 정상. 나머지는 진행됨 |
| 변환 품질이 아쉬움 | `src/reference/oracle_to_{db}_rules.md`(공통 룰)와 `strategy/transform_strategy.md`(학습 룰) 보강 |
| 대규모(mapper 수십+)에서 느림/lock | 병렬 수는 `oma-pipeline` skill의 "최대 5개" 기준. 필요 시 조정 |
