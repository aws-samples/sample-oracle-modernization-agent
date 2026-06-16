"""Tests for oma db reset and oma db feedback-patterns subcommands."""
import json
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
    assert others == 4  # seed: 3 rows already N + this 1 reset


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


def test_feedback_patterns_json_structured_output(oma_env, run_cli):
    db = oma_env / "oma_control.db"
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "UPDATE transform_target_list SET reviewed='F', "
            "review_result='{\"result\":\"FAIL\",\"issues\":[\"comma join wrong\"]}' "
            "WHERE mapper_file='OrderMapper.xml' AND sql_id='selectOrder'")
        conn.commit()
    code, stdout, _ = run_cli("db", "feedback-patterns", "--json")
    assert code == 0
    items = json.loads(stdout)
    assert isinstance(items, list)
    assert len(items) == 1
    assert items[0]["source"] == "review"
    assert items[0]["mapper_file"] == "OrderMapper.xml"
    assert items[0]["sql_id"] == "selectOrder"
    assert "comma join wrong" in items[0]["issues"]
