"""Tests for oma db read-sql and save-transform subcommands."""
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
