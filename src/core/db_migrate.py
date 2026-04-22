"""Database migration utilities for schema evolution."""
import sqlite3
from utils.project_paths import DB_PATH


# Expanded columns per history table (v2 — 2026-04-20).
# Used to ALTER existing DBs created before the history schema expansion.
_HISTORY_COLUMN_ADDITIONS = {
    'extract_record': [
        ('mapper_path', 'TEXT'),
        ('sql_type', 'TEXT'),
        ('namespace', 'TEXT'),
        ('seq_no', 'INTEGER'),
        ('original_sql', 'TEXT'),
    ],
    'transform_history': [
        ('mapper_path', 'TEXT'),
        ('attempt_no', 'INTEGER'),
        ('original_sql', 'TEXT'),
        ('transformed_sql', 'TEXT'),
        ('transform_log', 'TEXT'),
        ('model_id', 'TEXT'),
        ('status', 'TEXT'),
        ('error_message', 'TEXT'),
        ('duration_ms', 'INTEGER'),
    ],
    'review_history': [
        ('mapper_path', 'TEXT'),
        ('round_no', 'INTEGER'),
        ('reviewed_sql', 'TEXT'),
        ('syntax_result', 'TEXT'),
        ('equivalence_result', 'TEXT'),
        ('facilitator_verdict', 'TEXT'),
        ('review_log', 'TEXT'),
        ('duration_ms', 'INTEGER'),
    ],
    'validation_history': [
        ('mapper_path', 'TEXT'),
        ('round_no', 'INTEGER'),
        ('validated_sql', 'TEXT'),
        ('verdict', 'TEXT'),
        ('validation_log', 'TEXT'),
        ('issues_found', 'TEXT'),
        ('duration_ms', 'INTEGER'),
    ],
    'test_history': [
        ('mapper_path', 'TEXT'),
        ('phase', 'TEXT'),
        ('attempt_no', 'INTEGER'),
        ('tested_sql', 'TEXT'),
        ('bind_parameters', 'TEXT'),
        ('execution_log', 'TEXT'),
        ('sql_state', 'TEXT'),
        ('error_message', 'TEXT'),
        ('stack_trace', 'TEXT'),
        ('execution_time_ms', 'INTEGER'),
        ('rows_affected', 'INTEGER'),
    ],
}

_HISTORY_INDEXES = {
    # extract_record needs UNIQUE — master record semantics (one row per mapper_file+sql_id).
    # UPSERT (INSERT OR REPLACE) relies on this to detect conflicts.
    'extract_record': ('idx_extract_record_sql', 'mapper_file, sql_id', True),
    'transform_history': ('idx_transform_hist_sql', 'mapper_file, sql_id', False),
    'review_history': ('idx_review_hist_sql', 'mapper_file, sql_id', False),
    'validation_history': ('idx_validation_hist_sql', 'mapper_file, sql_id', False),
    'test_history': ('idx_test_hist_sql', 'mapper_file, sql_id', False),
}


def _migrate_extract_history_to_record(conn: sqlite3.Connection) -> None:
    """Rename legacy extract_history → extract_record (master record).

    Idempotent. Handles three states:
      1. Neither table exists → caller will create extract_record via metadata.
      2. Only extract_history exists → dedupe (keep latest per mapper_file+sql_id),
         rename to extract_record.
      3. Both exist → merge extract_history rows into extract_record via
         INSERT OR REPLACE, then drop extract_history.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='extract_history'")
    has_old = cursor.fetchone() is not None
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='extract_record'")
    has_new = cursor.fetchone() is not None

    if not has_old:
        return

    if has_new:
        cursor.execute(
            "INSERT OR REPLACE INTO extract_record "
            "(mapper_path, mapper_file, sql_id, sql_type, namespace, seq_no, original_sql, created_at) "
            "SELECT mapper_path, mapper_file, sql_id, sql_type, namespace, seq_no, original_sql, created_at "
            "FROM extract_history "
            "WHERE id IN ("
            "  SELECT MAX(id) FROM extract_history GROUP BY mapper_file, sql_id"
            ")"
        )
        cursor.execute("DROP TABLE extract_history")
        conn.commit()
        return

    # Only old exists — dedupe in place then rename.
    cursor.execute(
        "DELETE FROM extract_history WHERE id NOT IN ("
        "  SELECT MAX(id) FROM extract_history GROUP BY mapper_file, sql_id"
        ")"
    )
    cursor.execute("ALTER TABLE extract_history RENAME TO extract_record")
    # Drop legacy index if it survives the rename (SQLite keeps it, but name is stale).
    cursor.execute("DROP INDEX IF EXISTS idx_extract_hist_sql")
    conn.commit()


def ensure_history_tables():
    """Create history tables + expand legacy schemas to current model.

    Strategy:
      0. Migrate legacy extract_history → extract_record (dedupe + rename).
      1. Base.metadata.create_all() creates any missing tables with the full schema.
      2. For tables that pre-existed with the minimal schema (id, mapper_file, sql_id,
         <result>, created_at), add any columns introduced in the expansion.
      3. Create per-table indexes if missing.
    """
    if not DB_PATH.exists():
        return

    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        _migrate_extract_history_to_record(conn)

    from sqlalchemy import create_engine
    from core.models import Base

    engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, connect_args={"timeout": 10})
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()

    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        for table, additions in _HISTORY_COLUMN_ADDITIONS.items():
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            if not cursor.fetchone():
                continue
            # nosemgrep: sqlalchemy-execute-raw-query
            cursor.execute(f"PRAGMA table_info({table})")
            existing = {row[1] for row in cursor.fetchall()}
            for col_name, col_type in additions:
                if col_name in existing:
                    continue
                # nosemgrep: sqlalchemy-execute-raw-query
                cursor.execute(
                    f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"
                )
        for table, (index_name, columns, is_unique) in _HISTORY_INDEXES.items():
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            )
            if not cursor.fetchone():
                continue
            if is_unique:
                # Drop non-unique variant if a prior migration created it, then add UNIQUE.
                cursor.execute(
                    "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
                    (index_name,),
                )
                row = cursor.fetchone()
                if row and row[0] and 'UNIQUE' not in row[0].upper():
                    # nosemgrep: sqlalchemy-execute-raw-query
                    cursor.execute(f"DROP INDEX {index_name}")
                # nosemgrep: sqlalchemy-execute-raw-query
                cursor.execute(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table} ({columns})"
                )
            else:
                # nosemgrep: sqlalchemy-execute-raw-query
                cursor.execute(
                    f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({columns})"
                )
        conn.commit()


def ensure_schema():
    """Run all schema migrations idempotently. Safe to call from any runner entrypoint."""
    ensure_current_step_column()
    ensure_history_tables()


def ensure_current_step_column():
    """Add current_step column if missing, then backfill from existing flags."""
    if not DB_PATH.exists():
        return
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transform_target_list'")
        if not cursor.fetchone():
            return
        cursor.execute("PRAGMA table_info(transform_target_list)")
        columns = {row[1] for row in cursor.fetchall()}
        if 'current_step' in columns:
            return
        cursor.execute(
            "ALTER TABLE transform_target_list ADD COLUMN current_step TEXT DEFAULT 'pending'"
        )
        cursor.execute(
            "UPDATE transform_target_list SET current_step = 'completed' "
            "WHERE tested='Y' AND test_result='PASS'"
        )
        cursor.execute(
            "UPDATE transform_target_list SET current_step = 'test' "
            "WHERE tested='Y' AND test_result IN ('FAIL','SKIP')"
        )
        cursor.execute(
            "UPDATE transform_target_list SET current_step = 'test' "
            "WHERE validated='Y' AND tested='N'"
        )
        cursor.execute(
            "UPDATE transform_target_list SET current_step = 'validate' "
            "WHERE reviewed='Y' AND validated='N'"
        )
        cursor.execute(
            "UPDATE transform_target_list SET current_step = 'review' "
            "WHERE transformed='Y' AND reviewed='N'"
        )
        cursor.execute(
            "UPDATE transform_target_list SET current_step = 'transform' "
            "WHERE transformed='N'"
        )
        conn.commit()
