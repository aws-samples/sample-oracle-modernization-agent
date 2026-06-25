"""Shared fixtures: temp OUTPUT_DIR with a seeded oma_control.db"""
import os
import sys
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

    # project_paths caches module-level constants — must reload after env change.
    # Modules that derive paths at import-time must also be reloaded.
    import importlib
    import utils.project_paths
    importlib.reload(utils.project_paths)
    if "core.html_report" in sys.modules:
        importlib.reload(sys.modules["core.html_report"])
    if "core.db_migrate" in sys.modules:
        importlib.reload(sys.modules["core.db_migrate"])

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
