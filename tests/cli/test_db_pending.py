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
