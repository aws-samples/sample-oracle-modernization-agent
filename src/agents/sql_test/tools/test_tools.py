"""SQL Test tools — Python CLI executor (psql/mysql) replacing Java MyBatis executor."""
import os
import re
import sqlite3
import time
from pathlib import Path
from strands import tool
from utils.project_paths import PROJECT_ROOT, DB_PATH, TRANSFORM_DIR, MERGE_DIR, get_target_dbms, get_target_db_display_name
from agents.sql_transform.tools.metadata import _get_pg_connection_vars, _get_mysql_connection_vars
from core.sql_executor import SQLExecutor, extract_sql_from_xml, check_cli_available, SQLResult
from core import history_writer as _hw

_logger = None


def set_logger(logger):
    global _logger
    _logger = logger


def _ensure_db_env() -> bool:
    dbms = get_target_dbms()
    if dbms == 'mysql':
        mysql_vars = _get_mysql_connection_vars()
        if mysql_vars:
            os.environ.update(mysql_vars)
            return True
        return False
    else:
        pg_vars = _get_pg_connection_vars()
        if pg_vars:
            os.environ.update(pg_vars)
            return True
        return False


def _extract_sql_state(error_msg: str) -> str:
    if not error_msg:
        return ""
    m = re.search(r'SQLState:\s*([0-9A-Z]{5})', error_msg)
    if m:
        return m.group(1)
    m = re.search(r'\b([0-9]{5})\b', error_msg)
    if m:
        return m.group(1)
    m = re.search(r'\b(42[A-Z0-9]{3})\b', error_msg)
    return m.group(1) if m else ""


def _update_tested(mapper_file: str, sql_id: str, result: str = "PASS", error: str = ""):
    for i in range(5):
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            try:
                test_result_val = result
                test_notes_val = error if result != "PASS" else ""
                if result == "FAIL":
                    test_result_val = "FAIL"
                    test_notes_val = error[:500] if error else "Unknown error"
                next_step = 'completed' if result == 'PASS' else 'test'
                from utils.db_utils import update_by_mapper
                update_by_mapper(conn,
                    "UPDATE transform_target_list SET tested='Y', test_result=?, test_notes=?, current_step=?, updated_at=CURRENT_TIMESTAMP WHERE mapper_file=? AND sql_id=?",
                    mapper_file, sql_id, extra_params=(test_result_val, test_notes_val, next_step))
                conn.commit()
            finally:
                conn.close()
            from core.progress import emit_progress
            emit_progress(mapper_file, sql_id, result)
            return
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and i < 4:
                time.sleep(0.5 * (i + 1))
            else:
                raise


def _record_test_history(mapper_file: str, sql_id: str, phase: str, result: str,
                          error: str = "", sql_state: str = "",
                          execution_time_ms: int | None = None,
                          rows_affected: int | None = None,
                          tested_sql: str = "", bind_parameters=None):
    attempt_no = 1
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        try:
            n_prior = conn.execute(
                "SELECT COUNT(*) FROM test_history WHERE mapper_file=? AND sql_id=? AND phase=?",
                (mapper_file, sql_id, phase),
            ).fetchone()[0]
            attempt_no = int(n_prior or 0) + 1

            if not tested_sql:
                from utils.db_utils import query_by_mapper
                row = query_by_mapper(
                    conn.cursor(),
                    "SELECT target_file FROM transform_target_list WHERE mapper_file=? AND sql_id=?",
                    mapper_file, sql_id,
                )
                if row and Path(row[0]).exists():
                    tested_sql = Path(row[0]).read_text(encoding='utf-8')
        finally:
            conn.close()
    except Exception:
        pass

    _hw.record_test(
        mapper_file=mapper_file,
        sql_id=sql_id,
        phase=phase,
        attempt_no=attempt_no,
        tested_sql=tested_sql,
        bind_parameters=bind_parameters,
        test_result=result,
        sql_state=sql_state or None,
        error_message=error or None,
        execution_time_ms=execution_time_ms,
        rows_affected=rows_affected,
        mapper_path=_hw.resolve_mapper_path(mapper_file),
    )


# ── Phase 0: EXPLAIN all testable SQL types ──

def explain_batch(items: list[dict]) -> dict:
    """Run EXPLAIN on all SQL types (SELECT + DML) via CLI.

    Args:
        items: List of dicts with mapper_file, sql_id, target_file keys.
    Returns:
        Dict with passed/failed counts and failure details.
    """
    if not _ensure_db_env():
        display_name = get_target_db_display_name(get_target_dbms())
        return {'status': 'skipped', 'error': f'No {display_name} connection info'}

    ok, msg = check_cli_available()
    if not ok:
        return {'status': 'skipped', 'error': msg}

    executor = SQLExecutor()
    _hw.start_timer("test")

    results = executor.explain_batch(items)

    passed = 0
    failed = 0
    failures = []

    for item, res in zip(items, results):
        if res.status == 'PASS':
            passed += 1
            _update_tested(item['mapper_file'], item['sql_id'])
            _record_test_history(item['mapper_file'], item['sql_id'], 'explain',
                                 result='PASS')
        else:
            failed += 1
            _update_tested(item['mapper_file'], item['sql_id'],
                           result="FAIL", error=res.error)
            _record_test_history(item['mapper_file'], item['sql_id'], 'explain',
                                 result='FAIL', error=res.error,
                                 sql_state=res.sql_state or _extract_sql_state(res.error))
            failures.append({
                'mapper_file': item['mapper_file'],
                'sql_id': item['sql_id'],
                'error': res.error,
            })

    return {'status': 'completed', 'passed': passed, 'failed': failed, 'failures': failures}


# ── Phase 1: Execute all testable SQL types ──

def execute_batch(items: list[dict]) -> dict:
    """Execute all SQL types via CLI.
    SELECT: LIMIT 100. DML: BEGIN/ROLLBACK.

    Args:
        items: List of dicts with mapper_file, sql_id, target_file keys.
    Returns:
        Dict with passed/failed counts and failure details.
    """
    if not _ensure_db_env():
        display_name = get_target_db_display_name(get_target_dbms())
        return {'status': 'skipped', 'error': f'No {display_name} connection info'}

    ok, msg = check_cli_available()
    if not ok:
        return {'status': 'skipped', 'error': msg}

    executor = SQLExecutor()
    _hw.start_timer("test")

    results = executor.execute_batch(items)

    passed = 0
    failed = 0
    failures = []

    for item, res in zip(items, results):
        if res.status == 'PASS':
            passed += 1
            _update_tested(item['mapper_file'], item['sql_id'])
            _record_test_history(item['mapper_file'], item['sql_id'], 'execute',
                                 result='PASS', rows_affected=res.rows if res.rows >= 0 else None)
        else:
            failed += 1
            _update_tested(item['mapper_file'], item['sql_id'],
                           result="FAIL", error=res.error)
            _record_test_history(item['mapper_file'], item['sql_id'], 'execute',
                                 result='FAIL', error=res.error,
                                 sql_state=res.sql_state or _extract_sql_state(res.error))
            failures.append({
                'mapper_file': item['mapper_file'],
                'sql_id': item['sql_id'],
                'error': res.error,
            })

    return {'status': 'completed', 'passed': passed, 'failed': failed, 'failures': failures}


# ── @tool functions for Agent ──

@tool
def run_single_test(mapper_file: str, sql_id: str) -> dict:
    """Execute a single SQL against the target database.

    Args:
        mapper_file: Mapper file name
        sql_id: SQL statement ID
    """
    if not _ensure_db_env():
        display_name = get_target_db_display_name(get_target_dbms())
        return {'status': 'skipped', 'error': f'No {display_name} connection info'}

    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        from utils.db_utils import query_by_mapper
        row = query_by_mapper(conn.cursor(),
            "SELECT target_file FROM transform_target_list WHERE mapper_file = ? AND sql_id = ?",
            mapper_file, sql_id)
    finally:
        conn.close()

    if not row:
        return {'status': 'error', 'error': f'Not found: {mapper_file}/{sql_id}'}

    target_file = row[0]
    extracted = extract_sql_from_xml(target_file, sql_id=sql_id)
    if not extracted:
        return {'status': 'FAIL', 'sql_id': sql_id, 'error': 'Failed to extract SQL from XML'}

    sql_type, sql_body = extracted

    _hw.start_timer("test")
    executor = SQLExecutor()
    result = executor.execute_single(sql_body, sql_type=sql_type)

    if result.status == 'PASS':
        _update_tested(mapper_file, sql_id)
        _record_test_history(mapper_file, sql_id, 'execute',
                             result='PASS', rows_affected=result.rows if result.rows >= 0 else None)
        return {'status': 'SUCCESS', 'sql_id': sql_id}
    else:
        _update_tested(mapper_file, sql_id, result="FAIL", error=result.error)
        _record_test_history(mapper_file, sql_id, 'execute',
                             result='FAIL', error=result.error,
                             sql_state=result.sql_state or _extract_sql_state(result.error))
        return {'status': 'FAIL', 'sql_id': sql_id, 'error': result.error}


@tool
def explain_single(mapper_file: str, sql_id: str) -> dict:
    """Run EXPLAIN on a single SQL — quick syntax check without execution.

    Args:
        mapper_file: Mapper file name
        sql_id: SQL statement ID
    """
    if not _ensure_db_env():
        return {'status': 'skipped', 'error': 'No DB connection info'}

    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        from utils.db_utils import query_by_mapper
        row = query_by_mapper(conn.cursor(),
            "SELECT target_file FROM transform_target_list WHERE mapper_file = ? AND sql_id = ?",
            mapper_file, sql_id)
    finally:
        conn.close()

    if not row:
        return {'status': 'error', 'error': f'Not found: {mapper_file}/{sql_id}'}

    item = {'mapper_file': mapper_file, 'sql_id': sql_id, 'target_file': row[0]}
    executor = SQLExecutor()
    results = executor.explain_batch([item])

    if not results:
        return {'status': 'FAIL', 'sql_id': sql_id, 'error': 'Extraction failed'}

    res = results[0]
    return {'status': res.status, 'sql_id': sql_id, 'error': res.error}


@tool
def compare_single(mapper_file: str, sql_id: str) -> dict:
    """Compare Oracle vs target DB results for a single SQL.

    Executes on both databases and compares row counts.
    Requires Oracle DB connection (ORACLE_HOST etc.).

    Args:
        mapper_file: Mapper file name
        sql_id: SQL statement ID
    """
    from core.result_comparator import ResultComparator

    if not _ensure_db_env():
        return {'status': 'skipped', 'error': 'No target DB connection info'}

    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        from utils.db_utils import query_by_mapper
        row = query_by_mapper(conn.cursor(),
            "SELECT target_file, source_file, sql_type FROM transform_target_list WHERE mapper_file = ? AND sql_id = ?",
            mapper_file, sql_id)
    finally:
        conn.close()

    if not row:
        return {'status': 'error', 'error': f'Not found: {mapper_file}/{sql_id}'}

    comparator = ResultComparator()
    result = comparator.compare_single(
        mapper_file=mapper_file, sql_id=sql_id,
        target_file=row[0], source_file=row[1] or '',
        sql_type=row[2] or 'select',
    )

    return {
        'status': result.status,
        'sql_id': sql_id,
        'oracle_rows': result.oracle_rows,
        'target_rows': result.target_rows,
        'error': result.error,
        'warnings': result.warnings,
    }


@tool
def get_test_failures() -> dict:
    """Get SQL IDs that need testing — excludes non-testable types (sql fragments, resultMap).

    Returns:
        Dict with failures list grouped by mapper_file
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT mapper_file, sql_id, sql_type, source_file, target_file
            FROM transform_target_list
            WHERE validated = 'Y' AND tested = 'N'
              AND LOWER(sql_type) IN ('select', 'insert', 'update', 'delete')
            ORDER BY mapper_file, seq_no
        """)
        rows = cursor.fetchall()
    finally:
        conn.close()

    pending = {}
    for mapper, sql_id, sql_type, source, target in rows:
        if mapper not in pending:
            pending[mapper] = []
        pending[mapper].append({
            'sql_id': sql_id, 'sql_type': sql_type,
            'source_file': source, 'target_file': target
        })

    total = sum(len(v) for v in pending.values())
    print(f"📋 Test targets: {total} SQL IDs across {len(pending)} mappers")
    return {'total': total, 'mappers_count': len(pending), 'pending': pending}
