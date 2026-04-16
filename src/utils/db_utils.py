"""Common DB query utilities for mapper_file resolution.

mapper_file may be stored as 'sub_dir/filename.xml' or 'filename.xml'.
These helpers handle both formats transparently.
"""
import sqlite3
from pathlib import Path


def resolve_mapper_file(cursor, mapper_file: str, sql_id: str) -> str:
    """Resolve the actual mapper_file key in DB.

    Tries exact match first, then filename-only, then LIKE with path suffix.
    Returns the matched mapper_file or the original if no match.
    """
    # Exact match
    cursor.execute(
        "SELECT mapper_file FROM transform_target_list WHERE mapper_file = ? AND sql_id = ? LIMIT 1",
        (mapper_file, sql_id)
    )
    row = cursor.fetchone()
    if row:
        return row[0]

    # Filename-only match (only if unique — skip if duplicates exist)
    file_name = Path(mapper_file).name
    cursor.execute(
        "SELECT DISTINCT mapper_file FROM transform_target_list WHERE (mapper_file = ? OR mapper_file LIKE ?) AND sql_id = ?",
        (file_name, f'%/{file_name}', sql_id)
    )
    rows = cursor.fetchall()
    if len(rows) == 1:
        return rows[0][0]
    # Multiple matches or no match — return original (caller will get 'not found')

    return mapper_file


def query_by_mapper(cursor, sql: str, mapper_file: str, sql_id: str, extra_params: tuple = ()):
    """Execute a query with mapper_file + sql_id, with automatic fallback resolution.

    Args:
        cursor: sqlite3 cursor
        sql: SQL with mapper_file=? AND sql_id=? placeholders (first two ? params)
        mapper_file: mapper file name (may or may not include path)
        sql_id: SQL statement ID
        extra_params: additional parameters after mapper_file and sql_id

    Returns:
        cursor.fetchone() result or None
    """
    # Try exact match
    cursor.execute(sql, (mapper_file, sql_id) + extra_params)
    row = cursor.fetchone()
    if row:
        return row

    # Resolve and retry
    resolved = resolve_mapper_file(cursor, mapper_file, sql_id)
    if resolved != mapper_file:
        cursor.execute(sql, (resolved, sql_id) + extra_params)
        return cursor.fetchone()

    return None


def update_by_mapper(conn, sql: str, mapper_file: str, sql_id: str, extra_params: tuple = ()) -> int:
    """Execute an UPDATE with mapper_file + sql_id, with automatic fallback resolution.

    Returns:
        Number of rows updated
    """
    cursor = conn.cursor()

    # Try exact match
    cursor.execute(sql, extra_params + (mapper_file, sql_id))
    if cursor.rowcount > 0:
        return cursor.rowcount

    # Resolve and retry
    resolved = resolve_mapper_file(cursor, mapper_file, sql_id)
    if resolved != mapper_file:
        cursor.execute(sql, extra_params + (resolved, sql_id))
        return cursor.rowcount

    return 0
