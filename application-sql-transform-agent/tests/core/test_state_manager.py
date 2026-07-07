"""Tests for core.state_manager.StateManager — core ORM layer."""
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from core.models import Base, TransformTargetList, Properties, SourceXmlList
from core.state_manager import StateManager


@pytest.fixture
def sm(tmp_path):
    """Create a StateManager with a fresh in-memory-style tmp DB."""
    db = tmp_path / "test.db"
    # Create schema via SQLAlchemy
    engine = create_engine(f"sqlite:///{db}", connect_args={"timeout": 10})
    Base.metadata.create_all(engine)

    # Seed data
    with sqlite3.connect(str(db), timeout=10) as conn:
        conn.execute("INSERT INTO source_xml_list (file_path, file_name) VALUES (?,?)",
                     ("/src/A.xml", "A.xml"))
        conn.execute("INSERT INTO source_xml_list (file_path, file_name) VALUES (?,?)",
                     ("/src/B.xml", "B.xml"))
        rows = [
            ("A.xml", "q1", "select", 1, "ns", "/src/a.xml"),
            ("A.xml", "q2", "insert", 2, "ns", "/src/a.xml"),
            ("B.xml", "q3", "select", 1, "ns", "/src/b.xml"),
        ]
        for mf, sid, st, seq, ns, src in rows:
            conn.execute(
                "INSERT INTO transform_target_list "
                "(mapper_file, sql_id, sql_type, seq_no, namespace, source_file) "
                "VALUES (?,?,?,?,?,?)",
                (mf, sid, st, seq, ns, src))
        conn.commit()

    return StateManager(db)


def test_get_step_counts_initial(sm):
    counts = sm.get_step_counts()
    assert counts['source_analyzed'] == 2
    assert counts['extracted'] == 3
    assert counts['transformed'] == 0
    assert counts['transform_complete'] is False


def test_update_sql_status(sm):
    sm.update_sql_status("A.xml", "q1", transformed='Y')
    info = sm.get_sql_info("A.xml", "q1")
    assert info['transformed'] == 'Y'
    assert info['reviewed'] == 'N'


def test_update_sql_status_rejects_invalid_column(sm):
    with pytest.raises(ValueError, match="Invalid column names"):
        sm.update_sql_status("A.xml", "q1", hacked='Y')


def test_get_pending_tasks(sm):
    pending = sm.get_pending_tasks('transform')
    assert len(pending) == 3

    sm.update_sql_status("A.xml", "q1", transformed='Y')
    pending = sm.get_pending_tasks('transform')
    assert len(pending) == 2
    assert ("A.xml", "q1") not in pending


def test_reset_step_status(sm):
    sm.update_sql_status("A.xml", "q1", transformed='Y')
    sm.update_sql_status("A.xml", "q2", transformed='Y')

    reset = sm.reset_step_status('transform')
    assert reset == 2

    pending = sm.get_pending_tasks('transform')
    assert len(pending) == 3


def test_increment_transform_count(sm):
    sm.increment_transform_count("A.xml", "q1")
    sm.increment_transform_count("A.xml", "q1")
    info = sm.get_sql_info("A.xml", "q1")
    assert info is not None
    # transform_count may not be in info dict, query directly
    with sm._get_session() as session:
        row = session.query(TransformTargetList).filter_by(
            mapper_file="A.xml", sql_id="q1").first()
        assert row.transform_count == 2


def test_get_sql_info_not_found(sm):
    assert sm.get_sql_info("NoSuch.xml", "missing") is None


def test_property_get_set(sm):
    assert sm.get_property("NO_KEY") is None
    sm.set_property("MY_KEY", "hello")
    assert sm.get_property("MY_KEY") == "hello"
    sm.set_property("MY_KEY", "updated")
    assert sm.get_property("MY_KEY") == "updated"


def test_search_sqls(sm):
    results = sm.search_sqls("q")
    assert len(results) == 3
    results = sm.search_sqls("A.xml")
    assert len(results) == 2


def test_auto_migrate_adds_missing_column(tmp_path):
    """_auto_migrate adds test_notes if missing."""
    db = tmp_path / "migrate_test.db"
    # Create table WITHOUT test_notes column
    with sqlite3.connect(str(db), timeout=10) as conn:
        conn.execute("""
            CREATE TABLE transform_target_list (
                id INTEGER PRIMARY KEY, mapper_file TEXT NOT NULL,
                sql_id TEXT NOT NULL, sql_type TEXT NOT NULL,
                seq_no INTEGER NOT NULL, namespace TEXT,
                source_file TEXT NOT NULL, target_file TEXT,
                transformed TEXT DEFAULT 'N', reviewed TEXT DEFAULT 'N',
                validated TEXT DEFAULT 'N', tested TEXT DEFAULT 'N',
                completed TEXT DEFAULT 'N',
                created_at DATETIME, updated_at DATETIME,
                review_notes TEXT, transform_count INTEGER,
                review_result TEXT, validation_result TEXT,
                test_result TEXT, current_step TEXT DEFAULT 'pending'
            )
        """)
        conn.execute("""
            CREATE TABLE properties (key TEXT PRIMARY KEY, value TEXT NOT NULL,
                                     description TEXT, created_at DATETIME, updated_at DATETIME)
        """)
        conn.commit()

    # StateManager should add test_notes via _auto_migrate
    sm = StateManager(db)
    with sqlite3.connect(str(db), timeout=10) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(transform_target_list)")]
    assert 'test_notes' in cols


def test_table_exists(sm):
    assert sm.table_exists('transform_target_list') is True
    assert sm.table_exists('nonexistent_table') is False
