"""Tests for oma merge — deterministic mapper assembly."""
import json
import sqlite3
from pathlib import Path

# Origin XML with Oracle SQL
ORIGIN = """\
<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="order">
<select id="selectOrder" resultType="map">
SELECT NVL(A,1) FROM T
</select>
</mapper>
"""

# Transformed SQL file (single <select> element)
TRANSFORMED = """\
<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="order">
<select id="selectOrder" resultType="map">
SELECT COALESCE(a,1) FROM t
</select>
</mapper>
"""


def test_merge_assembles_completed_mappers_only(oma_env, run_cli):
    """Only mappers where ALL rows have transformed='Y' are merged."""
    # Set up a fully-transformed mapper: origin file + transform file + DB rows
    origin = oma_env / "xmls" / "origin" / "DoneMapper.xml"
    origin.parent.mkdir(parents=True, exist_ok=True)
    origin.write_text(ORIGIN, encoding="utf-8")

    tfile = oma_env / "xmls" / "transform" / "DoneMapper" / "selectOrder.xml"
    tfile.parent.mkdir(parents=True, exist_ok=True)
    tfile.write_text(TRANSFORMED, encoding="utf-8")

    db = oma_env / "oma_control.db"
    with sqlite3.connect(str(db)) as conn:
        # DoneMapper has 1 SQL, fully transformed
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
    # DoneMapper merged; UserMapper (0/2) and OrderMapper (1/2) skipped
    assert data["merged"] >= 1
    assert data["skipped"] >= 2

    merged_dir = oma_env / "xmls" / "merge"
    files = list(merged_dir.rglob("DoneMapper.xml"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "COALESCE" in content
    # Original Oracle syntax no longer present
    assert "NVL" not in content


def test_merge_single_mapper_option(oma_env, run_cli):
    """--mapper re-merges a specific mapper without all-complete check."""
    origin = oma_env / "xmls" / "origin" / "OrderMapper.xml"
    origin.parent.mkdir(parents=True, exist_ok=True)
    origin.write_text(ORIGIN, encoding="utf-8")

    tfile = oma_env / "xmls" / "transform" / "OrderMapper" / "selectOrder.xml"
    tfile.parent.mkdir(parents=True, exist_ok=True)
    tfile.write_text(TRANSFORMED, encoding="utf-8")

    # OrderMapper in seed has only 1 of 2 transformed ('Y'), but --mapper bypasses check
    code, stdout, _ = run_cli("merge", "--mapper", "OrderMapper.xml", "--json")
    assert code == 0
    data = json.loads(stdout)
    assert data["merged"] == 1

    merged_file = oma_env / "xmls" / "merge" / "OrderMapper.xml"
    assert merged_file.exists()
    assert "COALESCE" in merged_file.read_text(encoding="utf-8")
