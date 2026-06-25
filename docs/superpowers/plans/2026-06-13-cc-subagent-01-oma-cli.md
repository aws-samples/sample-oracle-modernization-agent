# Plan 01/03: `oma` CLI — 결정적 인프라 통합

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 결정적 코드(상태 DB, XML 분할/병합, SQL 실행기, 리포트)를 Strands 의존 없는 단일 `oma` CLI로 통합한다.

**Architecture:** `src/cli/` 신규 패키지에 argparse 기반 서브커맨드를 구성. 각 커맨드는 기존 `core/`/`agents/*/tools/` 모듈의 함수를 호출하는 thin wrapper. 기존 tool 함수는 `@tool` 데코레이터와 `from strands import tool`만 제거하면 그대로 이식 가능 (조사 완료). subagent는 이 CLI를 Bash로 호출해 작업 대상 조회·결과 기록을 수행하므로 LLM 출력 파싱이 사라진다.

**Tech Stack:** Python 3.11, argparse, SQLAlchemy(기존 ORM 유지), sqlite3 parameterized query, pytest

**전제 (스펙):** `docs/superpowers/specs/2026-06-13-cc-subagent-architecture-design.md`

---

## 공통 규칙

- 모든 작업은 `feature/cc-subagent-architecture` 브랜치에서 수행
- 실행 위치: 항상 repo 루트. 테스트는 `PYTHONPATH=src pytest tests/cli/ -v`
- DB 접근: 신규 코드는 기존 패턴 유지 — StateManager(ORM) 또는 `sqlite3` + 파라미터화 쿼리. f-string SQL 금지
- 이식 규칙: `src/agents/*/tools/*.py`에서 가져올 때 (1) `from strands import tool` 줄 삭제, (2) `@tool` 데코레이터 삭제, (3) 나머지 로직 그대로. 이식 후 원본은 Plan 03에서 일괄 삭제하므로 이 Plan에서는 **복사**(이동 아님)
- `src/cli/` 내 모듈은 `core.*`, `utils.*`를 import할 수 있으나 `agents.*`는 import 금지 (Plan 03에서 삭제되므로)

### CLI 출력 규약 (모든 서브커맨드 공통)

- 기계 소비용 출력은 `--json` 플래그 시 stdout에 JSON 한 덩어리만 출력
- 사람용 메시지/진행 로그는 stderr
- 성공 시 exit 0, 실패 시 exit 1 + stderr에 사유

---

### Task 1: CLI 스켈레톤 + `oma status`

**Files:**
- Create: `src/cli/__init__.py`
- Create: `src/cli/main.py`
- Create: `src/cli/cmd_status.py`
- Create: `tests/__init__.py`, `tests/cli/__init__.py`
- Create: `tests/cli/conftest.py`
- Create: `tests/cli/test_status.py`
- Modify: `pyproject.toml` (script entry 추가)

- [ ] **Step 1: 테스트 fixture 작성**

`tests/cli/conftest.py`:

```python
"""Shared fixtures: temp OUTPUT_DIR with a seeded oma_control.db"""
import os
import sqlite3
import pytest


@pytest.fixture
def oma_env(tmp_path, monkeypatch):
    """Set OMA_OUTPUT_DIR to tmp and create a seeded DB.

    Returns the output dir path. DB contains:
    - transform_target_list: 4 rows (2 mappers), various states
    - source_xml_list: 2 rows
    - properties: TARGET_DBMS_TYPE=postgresql
    """
    out = tmp_path / "output"
    out.mkdir()
    monkeypatch.setenv("OMA_OUTPUT_DIR", str(out))

    # project_paths caches module-level constants — must reload after env change
    import importlib
    import utils.project_paths
    importlib.reload(utils.project_paths)

    db = out / "oma_control.db"
    with sqlite3.connect(str(db)) as conn:
        conn.executescript("""
        CREATE TABLE transform_target_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mapper_file TEXT NOT NULL, sql_id TEXT NOT NULL,
            sql_type TEXT NOT NULL, seq_no INTEGER NOT NULL,
            namespace TEXT, source_file TEXT NOT NULL, target_file TEXT,
            transformed TEXT DEFAULT 'N', reviewed TEXT DEFAULT 'N',
            validated TEXT DEFAULT 'N', tested TEXT DEFAULT 'N',
            completed TEXT DEFAULT 'N',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            review_notes TEXT, transform_count INTEGER,
            review_result TEXT, validation_result TEXT,
            test_result TEXT, test_notes TEXT,
            current_step TEXT DEFAULT 'pending'
        );
        CREATE TABLE source_xml_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL, file_name TEXT NOT NULL,
            relative_path TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE properties (
            key TEXT PRIMARY KEY, value TEXT NOT NULL, description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        rows = [
            ("UserMapper.xml", "selectUser", "select", 1, "user", "/src/u1.xml", str(out / "xmls/transform/UserMapper/selectUser.xml"), 'N'),
            ("UserMapper.xml", "insertUser", "insert", 2, "user", "/src/u2.xml", str(out / "xmls/transform/UserMapper/insertUser.xml"), 'N'),
            ("OrderMapper.xml", "selectOrder", "select", 1, "order", "/src/o1.xml", str(out / "xmls/transform/OrderMapper/selectOrder.xml"), 'Y'),
            ("OrderMapper.xml", "deleteOrder", "delete", 2, "order", "/src/o2.xml", str(out / "xmls/transform/OrderMapper/deleteOrder.xml"), 'N'),
        ]
        for m, sid, st, seq, ns, src, tgt, tr in rows:
            conn.execute(
                "INSERT INTO transform_target_list (mapper_file, sql_id, sql_type, seq_no, namespace, source_file, target_file, transformed) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (m, sid, st, seq, ns, src, tgt, tr))
        conn.execute("INSERT INTO source_xml_list (file_path, file_name, relative_path) VALUES (?,?,?)",
                     ("/src/UserMapper.xml", "UserMapper.xml", "UserMapper.xml"))
        conn.execute("INSERT INTO source_xml_list (file_path, file_name, relative_path) VALUES (?,?,?)",
                     ("/src/OrderMapper.xml", "OrderMapper.xml", "OrderMapper.xml"))
        conn.execute("INSERT INTO properties (key, value) VALUES ('TARGET_DBMS_TYPE', 'postgresql')")
        conn.commit()
    return out


@pytest.fixture
def run_cli(capsys):
    """Invoke oma CLI main() with args, return (exit_code, stdout, stderr)."""
    def _run(*args):
        from cli.main import main
        try:
            code = main(list(args))
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        out = capsys.readouterr()
        return code if code is not None else 0, out.out, out.err
    return _run
```

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/cli/test_status.py`:

```python
import json


def test_status_json_returns_step_counts(oma_env, run_cli):
    code, stdout, _ = run_cli("status", "--json")
    assert code == 0
    data = json.loads(stdout)
    assert data["extracted"] == 4
    assert data["transformed"] == 1
    assert data["transform_complete"] is False


def test_unknown_command_exits_nonzero(oma_env, run_cli):
    code, _, _ = run_cli("no-such-command")
    assert code != 0
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `PYTHONPATH=src pytest tests/cli/test_status.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cli'`

- [ ] **Step 4: CLI 스켈레톤 구현**

`src/cli/__init__.py`: 빈 파일

`src/cli/main.py`:

```python
"""oma — Application SQL Transform CLI (deterministic infrastructure).

Claude Code 메인 세션과 subagent가 Bash로 호출하는 단일 진입점.
LLM 작업(변환/리뷰/검증)은 하지 않는다 — 그것은 CC subagent의 몫.
"""
import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oma", description="Application SQL Transform CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    from cli import cmd_status
    cmd_status.register(sub)
    # 이후 Task에서 각 모듈의 register()가 여기에 추가된다:
    # cmd_db.register(sub), cmd_analyze.register(sub), cmd_merge.register(sub),
    # cmd_test.register(sub), cmd_report.register(sub), cmd_setup.register(sub)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
```

`src/cli/cmd_status.py`:

```python
"""oma status — pipeline step counts (StateManager 래핑)"""
import json
import sys


def register(sub):
    p = sub.add_parser("status", help="Show pipeline step counts")
    p.add_argument("--json", action="store_true", dest="as_json")
    p.set_defaults(func=run)


def run(args) -> int:
    from utils.project_paths import DB_PATH
    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH} — run 'oma setup' first", file=sys.stderr)
        return 1
    from core.state_manager import StateManager
    counts = StateManager(DB_PATH).get_step_counts()
    if args.as_json:
        print(json.dumps(counts, ensure_ascii=False))
    else:
        for k, v in counts.items():
            print(f"{k:24s} {v}", file=sys.stderr)
    return 0
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `PYTHONPATH=src pytest tests/cli/test_status.py -v`
Expected: PASS (2 tests)

주의: `StateManager.get_step_counts()`가 `utils.project_paths.MERGE_DIR`을 모듈 레벨에서 import하므로, conftest의 `importlib.reload`가 동작하지 않으면 `state_manager._count_merge_files`가 stale 경로를 볼 수 있다. 테스트가 이 이유로 실패하면 `core/state_manager.py:340`의 `from utils.project_paths import MERGE_DIR`이 함수 내부 import인지 확인 (현재 함수 내부 import라 reload만으로 충분).

- [ ] **Step 6: pyproject에 script entry 추가**

`pyproject.toml`의 `[project]` 아래에 추가:

```toml
[project.scripts]
oma = "cli.main:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

기존 `[project]`, `[dependency-groups]`는 유지. `uv sync` 후 `oma status` 동작 확인:

Run: `uv sync && OMA_OUTPUT_DIR=/tmp/oma-smoke .venv/bin/oma status; echo "exit=$?"`
Expected: stderr에 "DB not found" 메시지, exit=1 (DB 없는 디렉토리이므로 정상)

- [ ] **Step 7: Commit**

```bash
git add src/cli/ tests/ pyproject.toml uv.lock
git commit -m "feat(cli): oma CLI skeleton + status command"
```

---

### Task 2: `oma db pending` — 배치 목록 (적응형 배치)

메인 세션이 subagent dispatch 목록을 만들 때 사용하는 핵심 커맨드.

**Files:**
- Create: `src/cli/cmd_db.py`
- Create: `src/cli/batching.py`
- Test: `tests/cli/test_db_pending.py`
- Modify: `src/cli/main.py` (register 추가)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/cli/test_db_pending.py`:

```python
import json


def test_pending_transform_groups_by_mapper(oma_env, run_cli):
    code, stdout, _ = run_cli("db", "pending", "--step", "transform", "--json")
    assert code == 0
    data = json.loads(stdout)
    # seeded: UserMapper 2건 N, OrderMapper deleteOrder 1건 N (selectOrder는 Y)
    assert data["total"] == 3
    mappers = {b["mapper_file"] for b in data["batches"]}
    assert mappers == {"UserMapper.xml", "OrderMapper.xml"}


def test_pending_splits_large_mapper_into_batches(oma_env, run_cli):
    # BigMapper에 SQL 20건 추가 → max-batch 15 기준 2개 배치로 분할
    import sqlite3
    db = oma_env / "oma_control.db"
    with sqlite3.connect(str(db)) as conn:
        for i in range(20):
            conn.execute(
                "INSERT INTO transform_target_list (mapper_file, sql_id, sql_type, seq_no, source_file) "
                "VALUES ('BigMapper.xml', ?, 'select', ?, '/src/big.xml')",
                (f"q{i:02d}", i + 1))
        conn.commit()

    code, stdout, _ = run_cli("db", "pending", "--step", "transform", "--json")
    data = json.loads(stdout)
    big_batches = [b for b in data["batches"] if b["mapper_file"] == "BigMapper.xml"]
    assert len(big_batches) == 2
    assert sum(len(b["sql_ids"]) for b in big_batches) == 20
    assert all(len(b["sql_ids"]) <= 15 for b in big_batches)


def test_pending_only_filter_restricts_to_listed_sqls(oma_env, run_cli):
    """재시도용: --only 'mapper:sql_id' 쉼표 목록으로 제한"""
    code, stdout, _ = run_cli(
        "db", "pending", "--step", "transform", "--json",
        "--only", "UserMapper.xml:selectUser")
    data = json.loads(stdout)
    assert data["total"] == 1
    assert data["batches"][0]["sql_ids"] == ["selectUser"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `PYTHONPATH=src pytest tests/cli/test_db_pending.py -v`
Expected: FAIL — argparse가 `db` 커맨드를 모름 (SystemExit 2)

- [ ] **Step 3: batching 모듈 구현**

`src/cli/batching.py`:

```python
"""Adaptive batching: mapper 단위 기본, 大 mapper는 분할."""

MAX_BATCH_SQLS = 15


def make_batches(rows: list[dict], max_batch: int = MAX_BATCH_SQLS) -> list[dict]:
    """rows: [{mapper_file, sql_id, sql_type, seq_no}] (mapper_file, seq_no 정렬 가정)

    Returns: [{mapper_file, part, parts, sql_ids: [...]}]
    part/parts는 분할 시 1-based 인덱스와 총 분할 수 (미분할이면 1/1).
    """
    by_mapper: dict[str, list[str]] = {}
    for r in rows:
        by_mapper.setdefault(r["mapper_file"], []).append(r["sql_id"])

    batches = []
    for mapper, sql_ids in by_mapper.items():
        chunks = [sql_ids[i:i + max_batch] for i in range(0, len(sql_ids), max_batch)]
        for idx, chunk in enumerate(chunks, 1):
            batches.append({
                "mapper_file": mapper,
                "part": idx,
                "parts": len(chunks),
                "sql_ids": chunk,
            })
    return batches
```

- [ ] **Step 4: cmd_db 구현 (pending 서브커맨드)**

`src/cli/cmd_db.py`:

```python
"""oma db — 상태 DB 조회/갱신. subagent와 메인 세션의 공용 인터페이스."""
import json
import sqlite3
import sys

# step → (해당 단계 flag 컬럼, 선행 조건 WHERE)
_STEP_FILTERS = {
    "transform": "transformed = 'N'",
    "review": "transformed = 'Y' AND reviewed = 'N'",
    "validate": "reviewed = 'Y' AND validated = 'N'",
}


def register(sub):
    p = sub.add_parser("db", help="Control-DB query/update")
    dbsub = p.add_subparsers(dest="db_command", required=True)

    pend = dbsub.add_parser("pending", help="List pending work as adaptive batches")
    pend.add_argument("--step", required=True, choices=list(_STEP_FILTERS))
    pend.add_argument("--json", action="store_true", dest="as_json")
    pend.add_argument("--max-batch", type=int, default=15)
    pend.add_argument("--only", default="",
                      help="comma list of mapper:sql_id to restrict (retry)")
    pend.set_defaults(func=run_pending)


def _connect():
    from utils.project_paths import DB_PATH
    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}", file=sys.stderr)
        raise SystemExit(1)
    return sqlite3.connect(str(DB_PATH), timeout=10)


def run_pending(args) -> int:
    where = _STEP_FILTERS[args.step]
    conn = _connect()
    try:
        # nosemgrep: 컬럼 조건은 코드 내 고정 화이트리스트(_STEP_FILTERS), 사용자 입력 아님
        rows = conn.execute(
            f"SELECT mapper_file, sql_id, sql_type, seq_no FROM transform_target_list "
            f"WHERE {where} ORDER BY mapper_file, seq_no"
        ).fetchall()
    finally:
        conn.close()

    items = [{"mapper_file": m, "sql_id": s, "sql_type": t, "seq_no": q}
             for m, s, t, q in rows]

    if args.only:
        allowed = set(x.strip() for x in args.only.split(",") if x.strip())
        items = [i for i in items if f"{i['mapper_file']}:{i['sql_id']}" in allowed]

    from cli.batching import make_batches
    batches = make_batches(items, max_batch=args.max_batch)
    result = {"step": args.step, "total": len(items), "batches": batches}

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"pending[{args.step}]: {len(items)} SQLs / {len(batches)} batches", file=sys.stderr)
    return 0
```

`src/cli/main.py`의 `build_parser()`에 추가:

```python
    from cli import cmd_status, cmd_db
    cmd_status.register(sub)
    cmd_db.register(sub)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `PYTHONPATH=src pytest tests/cli/test_db_pending.py -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add src/cli/ tests/cli/test_db_pending.py
git commit -m "feat(cli): oma db pending — adaptive mapper batching"
```

---

### Task 3: `oma db read-sql` + `oma db save-transform`

transformer subagent의 입출력 인터페이스. `read-sql`은 원본 SQL 조회, `save-transform`은 기존 `convert_sql` tool의 이식 (파일 저장 + flag 갱신 + history 기록).

**Files:**
- Create: `src/cli/transform_io.py` (convert_sql.py에서 이식)
- Modify: `src/cli/cmd_db.py`
- Test: `tests/cli/test_db_transform_io.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/cli/test_db_transform_io.py`:

```python
import json
import sqlite3
from pathlib import Path

SRC_XML = """<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="user">
<select id="selectUser" resultType="map">
SELECT NVL(NAME, 'X') FROM USERS WHERE ID = #{id}
</select>
</mapper>
"""


def _prepare_source(oma_env):
    src = oma_env / "xmls" / "extract" / "UserMapper" / "selectUser.xml"
    src.parent.mkdir(parents=True)
    src.write_text(SRC_XML, encoding="utf-8")
    db = oma_env / "oma_control.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "UPDATE transform_target_list SET source_file=? WHERE mapper_file='UserMapper.xml' AND sql_id='selectUser'",
            (str(src),))
        conn.commit()
    return src


def test_read_sql_returns_body(oma_env, run_cli):
    _prepare_source(oma_env)
    code, stdout, _ = run_cli("db", "read-sql", "UserMapper.xml", "selectUser", "--json")
    assert code == 0
    data = json.loads(stdout)
    assert "NVL(NAME, 'X')" in data["sql_body"]
    assert data["sql_type"] == "select"


def test_save_transform_writes_file_and_flags(oma_env, run_cli, tmp_path):
    _prepare_source(oma_env)
    converted = tmp_path / "converted.sql"
    converted.write_text(
        "/* [OMA] NVL->COALESCE */\nSELECT COALESCE(name, 'X') FROM users WHERE id = #{id}::numeric",
        encoding="utf-8")

    code, stdout, _ = run_cli(
        "db", "save-transform", "UserMapper.xml", "selectUser",
        "--sql-file", str(converted), "--notes", "NVL->COALESCE", "--json")
    assert code == 0
    data = json.loads(stdout)
    assert data["status"] == "saved"

    # target file written with mapper wrapper
    target = Path(data["target_file"])
    content = target.read_text(encoding="utf-8")
    assert "<select id=\"selectUser\"" in content
    assert "COALESCE" in content

    # DB flag updated
    db = oma_env / "oma_control.db"
    with sqlite3.connect(str(db)) as conn:
        row = conn.execute(
            "SELECT transformed, current_step FROM transform_target_list "
            "WHERE mapper_file='UserMapper.xml' AND sql_id='selectUser'").fetchone()
    assert row == ("Y", "review")


def test_save_transform_missing_sql_errors(oma_env, run_cli, tmp_path):
    f = tmp_path / "x.sql"
    f.write_text("SELECT 1", encoding="utf-8")
    code, _, stderr = run_cli("db", "save-transform", "NoMapper.xml", "nope", "--sql-file", str(f))
    assert code == 1
    assert "Not found" in stderr
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `PYTHONPATH=src pytest tests/cli/test_db_transform_io.py -v`
Expected: FAIL — `read-sql` 서브커맨드 없음

- [ ] **Step 3: transform_io 모듈 이식**

`src/cli/transform_io.py` — `src/agents/sql_transform/tools/convert_sql.py`와 `load_mapper_list.py`의 `read_sql_source`를 복사해 작성. 변경점:

1. `from strands import tool` 줄과 `@tool` 데코레이터 제거
2. `convert_sql()` 함수명 → `save_transform()` (시그니처 동일: `sql_id, converted_sql, mapper_file, notes`)
3. `from core.progress import emit_progress` 호출 블록(convert_sql.py:236-238) 제거 — Rich progress는 CC 구조에서 불필요
4. `set_step()` / `_current_step` 전역은 유지 (fix history 로그 구분용 — test-fixer가 `--step test`로 전달)
5. `read_sql_source()`는 그대로 복사 (이름/시그니처 유지)
6. history 기록(`_hw.record_transform`)과 `_save_fix_history`는 그대로 유지

나머지 코드(XML 헤더 추출, CDATA/주석 sanitize, retry, UPSERT)는 원본 그대로.

- [ ] **Step 4: cmd_db에 서브커맨드 추가**

`src/cli/cmd_db.py`의 `register()` 안에 추가:

```python
    rd = dbsub.add_parser("read-sql", help="Read original SQL body for one sql_id")
    rd.add_argument("mapper_file")
    rd.add_argument("sql_id")
    rd.add_argument("--json", action="store_true", dest="as_json")
    rd.set_defaults(func=run_read_sql)

    sv = dbsub.add_parser("save-transform", help="Save converted SQL (file or stdin)")
    sv.add_argument("mapper_file")
    sv.add_argument("sql_id")
    sv.add_argument("--sql-file", default="-",
                    help="path to converted SQL file, or '-' for stdin (default)")
    sv.add_argument("--notes", default="")
    sv.add_argument("--step", default="transform",
                    help="pipeline step writing this (transform|review|test)")
    sv.add_argument("--json", action="store_true", dest="as_json")
    sv.set_defaults(func=run_save_transform)
```

같은 파일에 핸들러 추가:

```python
def run_read_sql(args) -> int:
    from cli.transform_io import read_sql_source
    result = read_sql_source(args.mapper_file, args.sql_id)
    if "error" in result:
        print(result["error"], file=sys.stderr)
        return 1
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(result["sql_body"])
    return 0


def run_save_transform(args) -> int:
    if args.sql_file == "-":
        converted = sys.stdin.read()
    else:
        from pathlib import Path
        p = Path(args.sql_file)
        if not p.exists():
            print(f"SQL file not found: {p}", file=sys.stderr)
            return 1
        converted = p.read_text(encoding="utf-8")

    if not converted.strip():
        print("Converted SQL is empty", file=sys.stderr)
        return 1

    from cli import transform_io
    transform_io.set_step(args.step)
    result = transform_io.save_transform(
        sql_id=args.sql_id, converted_sql=converted,
        mapper_file=args.mapper_file, notes=args.notes)

    if result.get("status") == "error":
        print(result.get("message", "unknown error"), file=sys.stderr)
        return 1
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False))
    return 0
```

설계 노트: SQL 본문을 CLI 인자가 아닌 **파일/stdin**으로 받는 이유 — SQL에 포함된 따옴표·`$`·개행이 shell escaping을 깨는 것을 원천 차단. subagent는 변환 결과를 임시 파일에 Write 후 `--sql-file`로 전달한다.

- [ ] **Step 5: 테스트 통과 확인**

Run: `PYTHONPATH=src pytest tests/cli/test_db_transform_io.py -v`
Expected: PASS (3 tests)

history 테이블(`transform_history`)이 없어 `_hw.record_transform`이 실패할 수 있음 — `history_writer`는 비치명(try/except) 설계이므로 통과해야 정상. 실패 시 conftest에 `core.db_migrate.ensure_schema()` 호출 추가.

- [ ] **Step 6: Commit**

```bash
git add src/cli/ tests/cli/test_db_transform_io.py
git commit -m "feat(cli): oma db read-sql / save-transform — transformer subagent I/O"
```

---

### Task 4: `oma db set-reviewed` / `set-validated` / `set-tested` / `get-property`

reviewer/validator/test-fixer subagent의 결과 기록 인터페이스.

**Files:**
- Create: `src/cli/result_io.py` (review_tools.py의 set_reviewed, validate_tools.py의 set_validated 이식)
- Modify: `src/cli/cmd_db.py`
- Test: `tests/cli/test_db_result_io.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/cli/test_db_result_io.py`:

```python
import json
import sqlite3


def _flags(oma_env, mapper, sql_id):
    db = oma_env / "oma_control.db"
    with sqlite3.connect(str(db)) as conn:
        return conn.execute(
            "SELECT reviewed, validated, tested, review_result, validation_result, test_result "
            "FROM transform_target_list WHERE mapper_file=? AND sql_id=?",
            (mapper, sql_id)).fetchone()


def test_set_reviewed_pass(oma_env, run_cli, tmp_path):
    fb = tmp_path / "fb.json"
    fb.write_text(json.dumps({"result": "PASS", "issues": [], "feedback": ""}), encoding="utf-8")
    code, _, _ = run_cli("db", "set-reviewed", "OrderMapper.xml", "selectOrder",
                         "--result", "PASS", "--feedback-file", str(fb))
    assert code == 0
    reviewed, _, _, review_result, _, _ = _flags(oma_env, "OrderMapper.xml", "selectOrder")
    assert reviewed == "Y"
    assert json.loads(review_result)["result"] == "PASS"


def test_set_reviewed_fail_marks_F(oma_env, run_cli):
    code, _, _ = run_cli("db", "set-reviewed", "OrderMapper.xml", "selectOrder",
                         "--result", "FAIL", "--feedback", "comma join converted to LEFT JOIN")
    assert code == 0
    reviewed = _flags(oma_env, "OrderMapper.xml", "selectOrder")[0]
    assert reviewed == "F"


def test_set_validated_and_tested(oma_env, run_cli):
    code, _, _ = run_cli("db", "set-validated", "OrderMapper.xml", "selectOrder",
                         "--result", "PASS")
    assert code == 0
    code, _, _ = run_cli("db", "set-tested", "OrderMapper.xml", "selectOrder",
                         "--result", "FIXED", "--notes", "phase2 fix: cast added")
    assert code == 0
    _, validated, tested, _, validation_result, test_result = _flags(
        oma_env, "OrderMapper.xml", "selectOrder")
    assert validated == "Y"
    assert tested == "Y"
    assert test_result == "FIXED"


def test_get_property(oma_env, run_cli):
    code, stdout, _ = run_cli("db", "get-property", "TARGET_DBMS_TYPE")
    assert code == 0
    assert stdout.strip() == "postgresql"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `PYTHONPATH=src pytest tests/cli/test_db_result_io.py -v`
Expected: FAIL — 서브커맨드 없음

- [ ] **Step 3: result_io 모듈 이식 + 구현**

`src/cli/result_io.py` — 이식 원본과 변경점:

- `set_reviewed`: `src/agents/sql_review/tools/review_tools.py:45`에서 복사. `@tool` 제거. 시그니처 유지 (`mapper_file, sql_id, result, violations, review_feedback`). 내부의 history 기록(`_hw.record_review`) 유지
- `set_validated`: `src/agents/sql_validate/tools/validate_tools.py:50`에서 복사. 동일 처리
- `set_tested(mapper_file, sql_id, result, notes)`: 신규 작성 — 기존 test tool들의 DB 갱신 패턴을 따름:

```python
def set_tested(mapper_file: str, sql_id: str, result: str, notes: str = "") -> dict:
    """Record test result. result: PASS|FAIL|SKIP|FIXED → tested flag Y (FAIL은 N 유지)"""
    import sqlite3
    from utils.project_paths import DB_PATH
    from utils.db_utils import update_by_mapper

    tested_flag = "N" if result == "FAIL" else "Y"
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        updated = update_by_mapper(
            conn,
            "UPDATE transform_target_list SET tested=?, test_result=?, test_notes=?, "
            "updated_at=CURRENT_TIMESTAMP WHERE mapper_file=? AND sql_id=?",
            (tested_flag, result, notes), mapper_file, sql_id)
        conn.commit()
    finally:
        conn.close()
    if not updated:
        return {"status": "error", "message": f"Not found: {mapper_file}/{sql_id}"}
    return {"status": "ok", "tested": tested_flag, "test_result": result}
```

주의: `utils/db_utils.py`의 `update_by_mapper` 시그니처를 먼저 확인하고 (Read), 위 호출이 실제 시그니처와 맞지 않으면 거기에 맞춰 조정할 것. 맞는 형태가 없으면 `query_by_mapper`로 id 조회 후 id로 UPDATE하는 2단계로 구현.

`src/cli/cmd_db.py`의 `register()`에 추가:

```python
    for name, handler in (("set-reviewed", run_set_reviewed),
                          ("set-validated", run_set_validated),
                          ("set-tested", run_set_tested)):
        sp = dbsub.add_parser(name, help=f"Record {name.split('-')[1]} result")
        sp.add_argument("mapper_file")
        sp.add_argument("sql_id")
        sp.add_argument("--result", required=True,
                        choices=["PASS", "PASS_WITH_WARNINGS", "FAIL", "SKIP", "FIXED"])
        sp.add_argument("--feedback", default="", help="inline feedback text")
        sp.add_argument("--feedback-file", default="", help="JSON feedback file (overrides --feedback)")
        sp.add_argument("--notes", default="")
        sp.set_defaults(func=handler)

    gp = dbsub.add_parser("get-property", help="Read a property value")
    gp.add_argument("key")
    gp.set_defaults(func=run_get_property)
```

핸들러 (`cmd_db.py`):

```python
def _load_feedback(args) -> str:
    if args.feedback_file:
        from pathlib import Path
        return Path(args.feedback_file).read_text(encoding="utf-8")
    return args.feedback


def run_set_reviewed(args) -> int:
    from cli.result_io import set_reviewed
    fb = _load_feedback(args)
    result = set_reviewed(args.mapper_file, args.sql_id, args.result,
                          violations=args.notes, review_feedback=fb)
    if result.get("status") == "error":
        print(result.get("message"), file=sys.stderr)
        return 1
    return 0


def run_set_validated(args) -> int:
    from cli.result_io import set_validated
    result = set_validated(args.mapper_file, args.sql_id, args.result,
                           notes=_load_feedback(args) or args.notes)
    if result.get("status") == "error":
        print(result.get("message"), file=sys.stderr)
        return 1
    return 0


def run_set_tested(args) -> int:
    from cli.result_io import set_tested
    result = set_tested(args.mapper_file, args.sql_id, args.result, notes=args.notes)
    if result.get("status") == "error":
        print(result.get("message"), file=sys.stderr)
        return 1
    return 0


def run_get_property(args) -> int:
    conn = _connect()
    try:
        row = conn.execute("SELECT value FROM properties WHERE key=?", (args.key,)).fetchone()
    finally:
        conn.close()
    if not row:
        print(f"Property not found: {args.key}", file=sys.stderr)
        return 1
    print(row[0])
    return 0
```

이식 시 `set_reviewed`/`set_validated` 원본이 result 값에 따라 flag를 'Y'/'F'로 분기하는 로직 확인 필수 — 원본 로직 그대로 유지 (FAIL → reviewed='F').

- [ ] **Step 4: 테스트 통과 확인**

Run: `PYTHONPATH=src pytest tests/cli/test_db_result_io.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/cli/ tests/cli/test_db_result_io.py
git commit -m "feat(cli): oma db set-reviewed/set-validated/set-tested/get-property"
```

---

### Task 5: `oma analyze` — 스캔/분할/전략 (결정적 부분)

기존 Source Analyzer agent의 tool들이 사실상 결정적이므로 LLM 없이 순차 실행으로 재구성. 전략 초안은 `pattern_analyzer`의 통계 기반 생성 사용 (LLM 다듬기는 메인 세션이 결과를 보고 선택적으로 수행).

**Files:**
- Create: `src/cli/cmd_analyze.py`
- Create: `src/cli/analyzer.py` (source_analyzer tools + split_mapper + metadata 이식)
- Test: `tests/cli/test_analyze.py`
- Modify: `src/cli/main.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/cli/test_analyze.py`:

```python
import json
import sqlite3

MAPPER = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="demo.user">
  <select id="selectUser" resultType="map">
    SELECT NVL(NAME, 'X') FROM USERS WHERE ROWNUM &lt;= 10
  </select>
  <insert id="insertUser">
    INSERT INTO USERS (ID, NAME) VALUES (SEQ_USER.NEXTVAL, #{name})
  </insert>
</mapper>
"""


def test_analyze_scans_splits_and_populates_db(oma_env, run_cli, tmp_path):
    src_root = tmp_path / "java-src"
    (src_root / "mappers").mkdir(parents=True)
    (src_root / "mappers" / "DemoMapper.xml").write_text(MAPPER, encoding="utf-8")

    code, stdout, _ = run_cli("analyze", "--source", str(src_root), "--json")
    assert code == 0
    data = json.loads(stdout)
    assert data["mappers"] == 1
    assert data["sqls"] == 2

    db = oma_env / "oma_control.db"
    with sqlite3.connect(str(db)) as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM transform_target_list WHERE mapper_file LIKE '%DemoMapper.xml'"
        ).fetchone()[0]
    assert n == 2

    # extract files created
    extract = oma_env / "xmls" / "extract"
    assert len(list(extract.rglob("*.xml"))) == 2

    # strategy draft created
    assert (oma_env / "strategy" / "transform_strategy.md").exists()
```

주의: conftest의 seed DB와 충돌하지 않도록 analyze는 `--source` 지정 시 source_xml_list/transform_target_list에 **추가**(insert)한다. seed 행 4개 + 신규 2개가 되어도 위 assert는 LIKE 필터라 안전.

- [ ] **Step 2: 테스트 실패 확인**

Run: `PYTHONPATH=src pytest tests/cli/test_analyze.py -v`
Expected: FAIL

- [ ] **Step 3: analyzer 모듈 이식**

`src/cli/analyzer.py` — 다음을 복사·통합 (각각 `@tool`/strands import 제거):

| 원본 | 함수 | 역할 |
|------|------|------|
| `agents/source_analyzer/tools/file_scanner.py` | `scan_mybatis_mappers` | mapper XML 스캔 |
| `agents/source_analyzer/tools/db_manager.py` | `save_xml_list` | source_xml_list 저장 |
| `agents/source_analyzer/tools/sql_extractor.py` | `analyze_sql_complexity` + private 함수들 | 복잡도 분석 |
| `agents/sql_transform/tools/split_mapper.py` | `split_mapper` + private 함수들 | SQL 추출/분할 + transform_target_list 채움 |
| `agents/source_analyzer/tools/pattern_analyzer.py` | `analyze_sql_patterns` | Oracle 패턴 통계 |
| `agents/source_analyzer/tools/strategy_generator.py` | `generate_strategy`, `write_strategy_file` | 전략 초안 생성/저장 |
| `agents/sql_transform/tools/metadata.py` | `generate_metadata`, `lookup_column_type` | 타겟 DB 메타데이터 (비치명) |

이식 시 `save_xml_list`가 JSON 문자열 인자를 받는 형태라면 list 인자를 받도록 시그니처 정리 가능 (내부 호출만 하므로). 함수 간 호출 순서를 묶는 진입점 작성:

```python
def run_analyze(source_folder: str) -> dict:
    """Scan → save list → split → metadata → strategy draft. Returns summary dict."""
    from core.db_migrate import ensure_schema
    ensure_schema()

    scan = scan_mybatis_mappers(source_folder)
    mappers = scan.get("mappers", [])
    save_xml_list(mappers)

    total_sqls = 0
    for m in mappers:
        result = split_mapper(m["file_path"])
        total_sqls += result.get("count", 0)

    meta = generate_metadata()  # non-fatal: returns {'status': 'skipped'} on failure

    patterns = analyze_sql_patterns()
    strategy_md = generate_strategy(patterns)
    write_strategy_file_default(strategy_md)

    return {"mappers": len(mappers), "sqls": total_sqls,
            "metadata": meta.get("status", "skipped")}
```

`generate_strategy`/`write_strategy_file` 원본 시그니처가 다르면 (Read로 확인 후) 그에 맞게 어댑터 작성. 핵심은 **LLM 호출 없이** 패턴 통계 → 전략 markdown 초안이 나오는 경로를 만드는 것. 원본 `strategy_generator.generate_strategy`가 인자로 분석 요약을 받는 순수 함수면 그대로 사용.

`src/cli/cmd_analyze.py`:

```python
"""oma analyze — mapper 스캔/SQL 추출/메타데이터/전략 초안 (LLM 없음)"""
import json
import sys


def register(sub):
    p = sub.add_parser("analyze", help="Scan mappers, extract SQLs, draft strategy")
    p.add_argument("--source", default="",
                   help="Java source root (default: JAVA_SOURCE_FOLDER property)")
    p.add_argument("--json", action="store_true", dest="as_json")
    p.set_defaults(func=run)


def run(args) -> int:
    source = args.source
    if not source:
        import sqlite3
        from utils.project_paths import DB_PATH
        if DB_PATH.exists():
            with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
                row = conn.execute(
                    "SELECT value FROM properties WHERE key='JAVA_SOURCE_FOLDER'").fetchone()
            source = row[0] if row else ""
    if not source:
        print("No source folder: pass --source or set JAVA_SOURCE_FOLDER via 'oma setup'",
              file=sys.stderr)
        return 1

    from cli.analyzer import run_analyze
    summary = run_analyze(source)

    from core.html_report import generate_html_report
    generate_html_report()

    if args.as_json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(f"analyzed: {summary}", file=sys.stderr)
    return 0
```

`main.py`에 `cmd_analyze.register(sub)` 추가.

- [ ] **Step 4: 테스트 통과 확인**

Run: `PYTHONPATH=src pytest tests/cli/test_analyze.py -v`
Expected: PASS

이식한 원본들이 추가 의존(`progress`, print 등)을 갖고 있으면: print → stderr로 변경, `core.progress` 의존 제거.

- [ ] **Step 5: Commit**

```bash
git add src/cli/ tests/cli/test_analyze.py
git commit -m "feat(cli): oma analyze — deterministic scan/split/strategy-draft"
```

---### Task 6: `oma merge`

**Files:**
- Create: `src/cli/cmd_merge.py`
- Create: `src/cli/merger.py` (assemble_mapper.py 이식)
- Test: `tests/cli/test_merge.py`
- Modify: `src/cli/main.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/cli/test_merge.py`:

```python
import json
import sqlite3
from pathlib import Path

ORIGIN = """<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="order">
<select id="selectOrder" resultType="map">
SELECT NVL(A,1) FROM T
</select>
</mapper>
"""

TRANSFORMED = """<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="order">
<select id="selectOrder" resultType="map">
SELECT COALESCE(a,1) FROM t
</select>
</mapper>
"""


def test_merge_assembles_completed_mappers_only(oma_env, run_cli):
    # OrderMapper: selectOrder만 transformed='Y', deleteOrder='N' → 미완료라 스킵
    # UserMapper도 미완료. 완료 mapper 1개를 새로 구성한다.
    origin = oma_env / "xmls" / "origin" / "DoneMapper.xml"
    origin.parent.mkdir(parents=True)
    origin.write_text(ORIGIN, encoding="utf-8")
    tfile = oma_env / "xmls" / "transform" / "DoneMapper" / "selectOrder.xml"
    tfile.parent.mkdir(parents=True)
    tfile.write_text(TRANSFORMED, encoding="utf-8")

    db = oma_env / "oma_control.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "INSERT INTO transform_target_list "
            "(mapper_file, sql_id, sql_type, seq_no, namespace, source_file, target_file, transformed) "
            "VALUES ('DoneMapper.xml','selectOrder','select',1,'order','/x',?, 'Y')",
            (str(tfile),))
        conn.execute(
            "INSERT INTO source_xml_list (file_path, file_name, relative_path) "
            "VALUES (?, 'DoneMapper.xml', 'DoneMapper.xml')", (str(origin),))
        conn.commit()

    code, stdout, _ = run_cli("merge", "--json")
    assert code == 0
    data = json.loads(stdout)
    assert data["merged"] >= 1
    assert data["skipped"] >= 2  # UserMapper, OrderMapper 미완료

    merged = oma_env / "xmls" / "merge"
    files = list(merged.rglob("DoneMapper.xml"))
    assert len(files) == 1
    assert "COALESCE" in files[0].read_text(encoding="utf-8")
```

주의: `assemble_mapper`가 origin 파일을 `ORIGIN_DIR`에서 찾는 경로 규칙을 이식 시 확인하고 테스트의 파일 배치를 그 규칙에 맞출 것 (위 코드는 `xmls/origin/DoneMapper.xml` 가정 — 실제 이식 코드 기준으로 조정).

- [ ] **Step 2: 테스트 실패 확인**

Run: `PYTHONPATH=src pytest tests/cli/test_merge.py -v`
Expected: FAIL

- [ ] **Step 3: merger 이식 + cmd_merge 구현**

`src/cli/merger.py`: `agents/sql_transform/tools/assemble_mapper.py` 전체 복사, `@tool`/strands 제거.

`src/cli/cmd_merge.py`: 기존 `run_sql_merge.py`의 run() 로직 이식 (mapper별 완료 체크 → assemble → 집계). PipelineLogger 사용 유지, 출력은 stderr, `--json`으로 `{"merged": n, "skipped": n, "files": n}` stdout 출력. 단일 mapper 재병합용 `--mapper <name>` 옵션 추가 (test-fixer가 fix 후 사용):

```python
def register(sub):
    p = sub.add_parser("merge", help="Assemble transformed SQLs into final mapper XMLs")
    p.add_argument("--mapper", default="", help="merge only this mapper (re-merge after fix)")
    p.add_argument("--json", action="store_true", dest="as_json")
    p.set_defaults(func=run)
```

`--mapper` 지정 시 해당 mapper만 `assemble_mapper()` 호출 (완료 체크 생략 — fix 후 재병합 용도).

- [ ] **Step 4: 테스트 통과 확인**

Run: `PYTHONPATH=src pytest tests/cli/test_merge.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/cli/ tests/cli/test_merge.py
git commit -m "feat(cli): oma merge — deterministic mapper assembly"
```

---

### Task 7: `oma test-exec` — Phase 0/1/1.5 (결정적 실행만)

기존 `run_sql_test.py`에서 Phase 2(Agent fix)를 제외한 결정적 부분 이식. Phase 2는 CC subagent(test-fixer) 몫.

**Files:**
- Create: `src/cli/cmd_test.py`
- Test: `tests/cli/test_test_exec.py` (DB 연결 없는 경로만 — 실제 DB 실행은 E2E에서)
- Modify: `src/cli/main.py`
- Modify: `src/core/tc_generator.py` (strands 의존 제거)

- [ ] **Step 1: tc_generator의 strands 의존 제거**

`src/core/tc_generator.py:336-` 의 `_llm_generate_tc()` 함수를 다음으로 교체:

```python
def _llm_generate_tc(sql_body: str, param_names: list[str],
                      metadata: dict) -> dict[str, str] | None:
    """LLM TC generation removed in CC-subagent architecture.

    Sources 1-6 (Oracle dict, metadata inference, etc.) cover most cases;
    SQLs that still fail due to missing params are handled by the
    test-fixer subagent in Phase 2.
    """
    return None
```

Run: `grep -rn "strands" src/core/ | grep -v __pycache__`
Expected: 출력 없음

- [ ] **Step 2: 실패하는 테스트 작성**

`tests/cli/test_test_exec.py`:

```python
def test_test_exec_without_db_cli_fails_gracefully(oma_env, run_cli, monkeypatch):
    """psql 미존재 환경에서 명확한 에러로 종료 (스택트레이스 금지)"""
    monkeypatch.setenv("PATH", "/nonexistent")
    code, _, stderr = run_cli("test-exec")
    assert code == 1
    assert "psql" in stderr or "CLI" in stderr


def test_test_exec_phase0_only_flag_parses(oma_env, run_cli, monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    code, _, _ = run_cli("test-exec", "--phase", "0")
    assert code == 1  # still fails on missing CLI, but flag parsing works
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `PYTHONPATH=src pytest tests/cli/test_test_exec.py -v`
Expected: FAIL — 커맨드 없음

- [ ] **Step 4: cmd_test 구현**

`src/cli/cmd_test.py` — `run_sql_test.py`의 `run()`에서 다음 블록들을 이식:

- 진입 시 `check_cli_available()` 체크 (실패 시 exit 1 + 명확한 메시지)
- `_pre_mark_skips()` (sql/resultMap → SKIP)
- TC 생성 (`core.tc_generator`)
- Phase 0: `SQLExecutor.explain_batch` 호출 블록 (run_sql_test.py:287-316)
- Phase 1: `execute_batch` 블록 (317-368)
- Phase 1.5: Oracle 비교 블록 (369-459) — Oracle property 없으면 자동 스킵
- 결과 DB 기록, `test_result_report.md` 생성(`_generate_test_failure_report`), HTML 리포트
- Phase 2 블록(460-)과 Strands agent import는 **이식하지 않음**

CLI 정의:

```python
def register(sub):
    p = sub.add_parser("test-exec", help="Run DB tests: Phase 0 EXPLAIN / 1 Execute / 1.5 Compare")
    p.add_argument("--phase", choices=["0", "1", "1.5", "all"], default="all")
    p.add_argument("--only", default="", help="comma list of mapper:sql_id (retest)")
    p.add_argument("--json", action="store_true", dest="as_json")
    p.set_defaults(func=run)
```

`--json` 출력: `{"phase0": {"pass": n, "fail": n}, "phase1": {...}, "phase15": {...}, "failures": [{"mapper_file":..., "sql_id":..., "phase":..., "error":...}]}` — 메인 세션이 failures를 보고 test-fixer dispatch 목록을 만든다.

- [ ] **Step 5: 테스트 통과 확인**

Run: `PYTHONPATH=src pytest tests/cli/test_test_exec.py -v && PYTHONPATH=src pytest tests/cli/ -v`
Expected: 전체 PASS

- [ ] **Step 6: Commit**

```bash
git add src/cli/ src/core/tc_generator.py tests/cli/test_test_exec.py
git commit -m "feat(cli): oma test-exec — deterministic Phase 0/1/1.5; drop strands from tc_generator"
```

---

### Task 8: `oma report` + `oma setup`

**Files:**
- Create: `src/cli/cmd_report.py`
- Create: `src/cli/cmd_setup.py`
- Test: `tests/cli/test_report_setup.py`
- Modify: `src/cli/main.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/cli/test_report_setup.py`:

```python
def test_report_generates_html(oma_env, run_cli):
    code, _, stderr = run_cli("report")
    assert code == 0
    report = oma_env / "reports" / "oma_report.html"
    assert report.exists()
    assert report.stat().st_size > 1000


def test_setup_non_interactive_sets_properties(oma_env, run_cli):
    code, _, _ = run_cli(
        "setup", "--source", "/tmp/java-src", "--target-db", "mysql",
        "--non-interactive")
    assert code == 0
    code, stdout, _ = run_cli("db", "get-property", "TARGET_DBMS_TYPE")
    assert stdout.strip() == "mysql"
    code, stdout, _ = run_cli("db", "get-property", "JAVA_SOURCE_FOLDER")
    assert stdout.strip() == "/tmp/java-src"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `PYTHONPATH=src pytest tests/cli/test_report_setup.py -v`
Expected: FAIL

- [ ] **Step 3: 구현**

`src/cli/cmd_report.py`:

```python
"""oma report — self-contained HTML report 재생성"""
import sys


def register(sub):
    p = sub.add_parser("report", help="Regenerate HTML report")
    p.set_defaults(func=run)


def run(args) -> int:
    from core.db_migrate import ensure_schema
    ensure_schema()
    from core.html_report import generate_html_report
    path = generate_html_report()
    print(f"report: {path}", file=sys.stderr)
    return 0
```

(`generate_html_report()` 반환값 유무는 이식 시 확인 — 없으면 `REPORTS_DIR / "oma_report.html"` 출력)

`src/cli/cmd_setup.py` — `run_setup.py` 이식. 변경점:

- 기존 interactive 흐름 유지 + `--non-interactive` 모드 추가
- 플래그: `--source`, `--target-db {postgresql,mysql}`, `--pg-host/--pg-port/--pg-database/--pg-user`, `--mysql-host/...`, `--oracle-host/...` (모두 optional)
- 비밀번호는 플래그로 받지 않음 — interactive `getpass` 또는 env(`PGPASSWORD` 등)만. `--non-interactive`에서 패스워드 미설정 시 경고만 출력하고 진행 (Test 단계에서야 필요하므로)
- DB 스키마 생성(`Base.metadata.create_all` 또는 `ensure_schema()`)과 properties 저장 로직은 원본 그대로
- CC 모델 ID 설정 항목(OMA_MODEL_ID 등)은 **제거** — 더 이상 Python에서 LLM 호출 없음

- [ ] **Step 4: 테스트 통과 확인**

Run: `PYTHONPATH=src pytest tests/cli/ -v`
Expected: 전체 PASS

- [ ] **Step 5: Commit**

```bash
git add src/cli/ tests/cli/test_report_setup.py
git commit -m "feat(cli): oma report + oma setup (non-interactive mode)"
```

---

### Task 9: `oma db reset` + `oma db feedback-patterns` (보조 커맨드)

재시도 분기와 strategy-refiner subagent 지원.

**Files:**
- Modify: `src/cli/cmd_db.py`
- Test: `tests/cli/test_db_misc.py`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/cli/test_db_misc.py`:

```python
import sqlite3


def test_reset_step_review(oma_env, run_cli):
    db = oma_env / "oma_control.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute("UPDATE transform_target_list SET reviewed='F' "
                     "WHERE mapper_file='OrderMapper.xml' AND sql_id='selectOrder'")
        conn.commit()
    code, _, _ = run_cli("db", "reset", "--step", "review")
    assert code == 0
    with sqlite3.connect(str(db)) as conn:
        v = conn.execute("SELECT reviewed FROM transform_target_list "
                         "WHERE mapper_file='OrderMapper.xml' AND sql_id='selectOrder'").fetchone()[0]
    assert v == "N"


def test_reset_only_specific_sqls(oma_env, run_cli):
    code, _, _ = run_cli("db", "reset", "--step", "transform",
                         "--only", "OrderMapper.xml:selectOrder")
    assert code == 0
    db = oma_env / "oma_control.db"
    with sqlite3.connect(str(db)) as conn:
        v = conn.execute("SELECT transformed FROM transform_target_list "
                         "WHERE mapper_file='OrderMapper.xml' AND sql_id='selectOrder'").fetchone()[0]
        others = conn.execute("SELECT COUNT(*) FROM transform_target_list "
                              "WHERE transformed='N'").fetchone()[0]
    assert v == "N"
    assert others == 4  # 기존 N 3건 + 리셋된 1건


def test_feedback_patterns_outputs_review_failures(oma_env, run_cli):
    db = oma_env / "oma_control.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "UPDATE transform_target_list SET reviewed='F', "
            "review_result='{\"result\":\"FAIL\",\"issues\":[\"comma join wrong\"]}' "
            "WHERE mapper_file='OrderMapper.xml' AND sql_id='selectOrder'")
        conn.commit()
    code, stdout, _ = run_cli("db", "feedback-patterns")
    assert code == 0
    assert "comma join wrong" in stdout
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `PYTHONPATH=src pytest tests/cli/test_db_misc.py -v`
Expected: FAIL

- [ ] **Step 3: 구현**

`cmd_db.py` register에 추가:

```python
    rs = dbsub.add_parser("reset", help="Reset step status to N")
    rs.add_argument("--step", required=True, choices=["transform", "review", "validate", "test"])
    rs.add_argument("--only", default="", help="comma list mapper:sql_id (default: all Y/F)")
    rs.set_defaults(func=run_reset)

    fp = dbsub.add_parser("feedback-patterns", help="Dump review/validate failure feedback (for strategy refine)")
    fp.set_defaults(func=run_feedback_patterns)
```

`run_reset`: `--only` 미지정 시 `StateManager.reset_step_status(step)` 호출 (보호 로직 포함된 기존 구현 재사용). `--only` 지정 시 해당 (mapper, sql_id)만 파라미터화 UPDATE:

```python
def run_reset(args) -> int:
    if not args.only:
        from utils.project_paths import DB_PATH
        from core.state_manager import StateManager
        n = StateManager(DB_PATH).reset_step_status(args.step)
        print(f"reset[{args.step}]: {n} rows", file=sys.stderr)
        return 0

    col = {"transform": "transformed", "review": "reviewed",
           "validate": "validated", "test": "tested"}[args.step]
    pairs = [x.split(":", 1) for x in args.only.split(",") if ":" in x]
    conn = _connect()
    try:
        n = 0
        for mapper, sql_id in pairs:
            # nosemgrep: col은 코드 내 고정 매핑, 사용자 입력 아님
            cur = conn.execute(
                f"UPDATE transform_target_list SET {col}='N', updated_at=CURRENT_TIMESTAMP "
                f"WHERE mapper_file=? AND sql_id=?", (mapper.strip(), sql_id.strip()))
            n += cur.rowcount
        conn.commit()
    finally:
        conn.close()
    print(f"reset[{args.step}]: {n} rows", file=sys.stderr)
    return 0
```

`run_feedback_patterns`: `agents/strategy_refine/tools/refine_tools.py`의 `get_feedback_patterns` 로직 이식 (reviewed='F' / validation 실패 건의 review_result/validation_result 텍스트 덤프를 stdout으로).

- [ ] **Step 4: 테스트 통과 확인 + 전체 회귀**

Run: `PYTHONPATH=src pytest tests/cli/ -v`
Expected: 전체 PASS

- [ ] **Step 5: Commit**

```bash
git add src/cli/ tests/cli/test_db_misc.py
git commit -m "feat(cli): oma db reset/feedback-patterns"
```

---

## Plan 01 완료 기준

- `PYTHONPATH=src pytest tests/cli/ -v` 전체 PASS
- `uv run oma --help`가 서브커맨드 전체 표시: `status, db, analyze, merge, test-exec, report, setup`
- `grep -rn "strands" src/cli/ src/core/` 출력 없음
- 다음 단계: Plan 02 (`docs/superpowers/plans/2026-06-13-cc-subagent-02-cc-integration.md`)
