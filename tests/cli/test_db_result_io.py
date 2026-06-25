"""Tests for oma db set-reviewed / set-validated / set-tested / get-property."""
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


def test_set_tested_fail_marks_N(oma_env, run_cli):
    code, _, _ = run_cli("db", "set-tested", "OrderMapper.xml", "selectOrder",
                         "--result", "FAIL", "--notes", "phase0 explain error")
    assert code == 0
    db = oma_env / "oma_control.db"
    with sqlite3.connect(str(db)) as conn:
        row = conn.execute(
            "SELECT tested, test_result, current_step "
            "FROM transform_target_list WHERE mapper_file=? AND sql_id=?",
            ("OrderMapper.xml", "selectOrder")).fetchone()
    tested, test_result, current_step = row
    assert tested == "N"
    assert test_result == "FAIL"
    assert current_step == "test"


def test_get_property(oma_env, run_cli):
    code, stdout, _ = run_cli("db", "get-property", "TARGET_DBMS_TYPE")
    assert code == 0
    assert stdout.strip() == "postgresql"
