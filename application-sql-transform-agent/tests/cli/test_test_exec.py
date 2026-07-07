"""Tests for oma test-exec command."""
import sqlite3
from unittest.mock import MagicMock


def test_test_exec_without_db_connection_info_fails_gracefully(oma_env, run_cli):
    """No PG connection info in seed DB -> clear error, no stacktrace."""
    code, stdout, stderr = run_cli("test-exec")
    assert code == 1
    assert "connection" in stderr.lower() or "접속" in stderr


def test_test_exec_phase_flag_parses(oma_env, run_cli):
    """--phase flag is accepted (still fails on missing conn, but arg parsing works)."""
    code, _, _ = run_cli("test-exec", "--phase", "0")
    assert code == 1  # fails on missing connection info, but flag parsing succeeded


def test_test_exec_json_flag_parses(oma_env, run_cli):
    """--json flag is accepted."""
    code, _, _ = run_cli("test-exec", "--json")
    assert code == 1  # fails on missing connection info


def test_test_exec_only_flag_parses(oma_env, run_cli):
    """--only flag is accepted."""
    code, _, _ = run_cli("test-exec", "--only", "UserMapper.xml:selectUser")
    assert code == 1  # fails on missing connection info


# ── _classify_error unit tests ──

def test_classify_error_parameter():
    from cli.cmd_test import _classify_error
    assert _classify_error("invalid input syntax for type integer") == 'parameter'
    assert _classify_error("operator does not exist: text = integer") == 'parameter'


def test_classify_error_sql_syntax():
    from cli.cmd_test import _classify_error
    assert _classify_error("syntax error at or near \"FORM\"") == 'sql_syntax'
    assert _classify_error("unexpected token: END") == 'sql_syntax'


def test_classify_error_schema():
    from cli.cmd_test import _classify_error
    assert _classify_error('relation "users" does not exist') == 'schema'
    assert _classify_error('column "foo_bar" does not exist') == 'schema'


def test_classify_error_infra():
    from cli.cmd_test import _classify_error
    assert _classify_error("connection refused") == 'infra'
    assert _classify_error("java.lang.ClassNotFoundException") == 'infra'


def test_classify_error_unknown():
    from cli.cmd_test import _classify_error
    assert _classify_error("") == 'unknown'
    assert _classify_error("some random error") == 'other'


# ── _pre_mark_skips unit tests ──

def test_pre_mark_skips_marks_nontestable(oma_env):
    """Pre-skip marks sql fragments and resultMap as SKIP."""
    from cli.cmd_test import _pre_mark_skips

    db = oma_env / "oma_control.db"
    # Insert a 'sql' type (fragment) and a 'resultMap' type
    with sqlite3.connect(str(db), timeout=10) as conn:
        conn.execute(
            "INSERT INTO transform_target_list "
            "(mapper_file, sql_id, sql_type, seq_no, namespace, source_file, target_file, tested) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("FragMapper.xml", "baseColumns", "sql", 1, "ns", "/src/f.xml", None, 'N'))
        conn.execute(
            "INSERT INTO transform_target_list "
            "(mapper_file, sql_id, sql_type, seq_no, namespace, source_file, target_file, tested) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("MapMapper.xml", "userResult", "resultMap", 1, "ns", "/src/m.xml", None, 'N'))
        conn.commit()

    logs = []
    _pre_mark_skips(db, logs.append)

    assert any("2" in l for l in logs)  # 2 items marked

    with sqlite3.connect(str(db), timeout=10) as conn:
        row = conn.execute(
            "SELECT tested, test_result FROM transform_target_list WHERE sql_id='baseColumns'"
        ).fetchone()
        assert row == ('Y', 'SKIP')

        row2 = conn.execute(
            "SELECT tested, test_result FROM transform_target_list WHERE sql_id='userResult'"
        ).fetchone()
        assert row2 == ('Y', 'SKIP')


# ── Phase 0 integration test with monkeypatched subprocess ──

def test_phase0_explain_updates_db(oma_env, run_cli, monkeypatch):
    """Phase 0 with connection info runs EXPLAIN and updates tested flag."""
    db = oma_env / "oma_control.db"

    # Seed PG connection info + ensure rows are validated='Y' and tested='N'
    with sqlite3.connect(str(db), timeout=10) as conn:
        conn.execute("INSERT OR REPLACE INTO properties (key, value) VALUES ('PGHOST','localhost')")
        conn.execute("INSERT OR REPLACE INTO properties (key, value) VALUES ('PGDATABASE','testdb')")
        conn.execute("INSERT OR REPLACE INTO properties (key, value) VALUES ('PGUSER','user')")
        conn.execute("INSERT OR REPLACE INTO properties (key, value) VALUES ('PGPASSWORD','pass')")
        # Mark rows as validated to make them testable
        conn.execute("UPDATE transform_target_list SET validated='Y'")
        conn.commit()

    # Create dummy target XML files
    import os
    for row in [("UserMapper.xml", "selectUser", "select"), ("UserMapper.xml", "insertUser", "insert"),
                ("OrderMapper.xml", "selectOrder", "select"), ("OrderMapper.xml", "deleteOrder", "delete")]:
        mapper, sql_id, sql_type = row
        target_dir = oma_env / "xmls" / "transform" / mapper.replace(".xml", "")
        target_dir.mkdir(parents=True, exist_ok=True)
        xml_content = f'''<?xml version="1.0"?>
<mapper namespace="ns">
  <{sql_type} id="{sql_id}">SELECT 1 FROM dual</{sql_type}>
</mapper>'''
        (target_dir / f"{sql_id}.xml").write_text(xml_content)
        # Update target_file in DB
        with sqlite3.connect(str(db), timeout=10) as conn:
            conn.execute(
                "UPDATE transform_target_list SET target_file=? WHERE mapper_file=? AND sql_id=?",
                (str(target_dir / f"{sql_id}.xml"), mapper, sql_id))
            conn.commit()

    # Mock subprocess.run to simulate psql success
    fake_proc = MagicMock()
    fake_proc.stdout = (
        "=== UserMapper.xml/selectUser ===\nQUERY PLAN\n"
        "=== UserMapper.xml/insertUser ===\nQUERY PLAN\n"
        "=== OrderMapper.xml/selectOrder ===\nQUERY PLAN\n"
        "=== OrderMapper.xml/deleteOrder ===\nQUERY PLAN\n"
    )
    fake_proc.stderr = ""
    fake_proc.returncode = 0

    monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake_proc)
    # Mock shutil.which for check_cli_available
    monkeypatch.setattr("shutil.which", lambda x: "/usr/bin/psql")

    # Reload modules so they pick up the new env
    import importlib, sys as _sys
    if "core.db_conn" in _sys.modules:
        importlib.reload(_sys.modules["core.db_conn"])

    code, stdout, stderr = run_cli("test-exec", "--phase", "0", "--json")
    assert code == 0

    import json
    data = json.loads(stdout)
    assert data["phase0"]["pass"] == 4
    assert data["phase0"]["fail"] == 0

    # Verify DB updated
    with sqlite3.connect(str(db), timeout=10) as conn:
        rows = conn.execute(
            "SELECT tested, test_result FROM transform_target_list WHERE tested='Y'"
        ).fetchall()
    assert len(rows) == 4
    assert all(r[1] == 'PASS' for r in rows)
