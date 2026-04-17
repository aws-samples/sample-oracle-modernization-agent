"""Database migration utilities for schema evolution."""
import sqlite3
from utils.project_paths import DB_PATH


def ensure_current_step_column():
    """Add current_step column if missing, then backfill from existing flags."""
    if not DB_PATH.exists():
        return
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
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
