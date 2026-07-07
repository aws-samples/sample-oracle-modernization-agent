"""Tests for oma analyze — deterministic scan/split/strategy-draft."""
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
