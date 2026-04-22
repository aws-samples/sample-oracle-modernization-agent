"""History writer — append-only recording for each pipeline stage.

All functions are non-fatal: a failure to record history must never break the pipeline.
Caller side should pass already-resolved values (no DB lookups performed here beyond insert).

mapper_path convention: project-root-relative POSIX path
    (e.g. "src/main/resources/mybatis/sqlmap/oracle/UserMapper.xml")
"""
from __future__ import annotations

import json
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Any

from utils.project_paths import DB_PATH, PROJECT_ROOT


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=15, isolation_level=None)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=15000")
    except sqlite3.OperationalError:
        pass
    return conn


def _execute_with_retry(conn: sqlite3.Connection, sql: str, params: tuple, retries: int = 8) -> None:
    for i in range(retries):
        try:
            conn.execute(sql, params)
            return
        except sqlite3.OperationalError as err:
            if "locked" in str(err) and i < retries - 1:
                time.sleep(0.05 * (2 ** i))
                continue
            raise


# Global stage timers keyed by mapper_file so that lap timing survives
# cross-thread tool invocation (Strands executes tools in worker threads
# distinct from the runner's ThreadPoolExecutor worker).
#
# Structure: {(stage, mapper_file or "_default"): monotonic_start}
_timers_lock = threading.Lock()
_timers_map_global: dict[tuple[str, str], float] = {}


def _key(stage: str, mapper_file: str | None = None) -> tuple[str, str]:
    return (stage, mapper_file or "_default")


def start_timer(stage: str, mapper_file: str | None = None) -> None:
    """Mark the start of a pipeline stage (or new lap).

    stage: 'transform' | 'review' | 'validate' | 'test'
    mapper_file: optional scoping key so parallel mappers don't stomp each other.
                 When omitted, a shared default slot is used.
    """
    with _timers_lock:
        _timers_map_global[_key(stage, mapper_file)] = time.monotonic()


def pop_duration_ms(stage: str, mapper_file: str | None = None) -> int | None:
    """Return elapsed ms since the last start_timer/pop_duration_ms for this stage.

    Lap semantics — after returning the elapsed time, the timer is re-armed with
    the current timestamp so subsequent items in the same agent run (e.g. the
    next SQL in a group) can be measured individually.

    Lookup order: (stage, mapper_file) → (stage, "_default"). This lets callers
    that don't know which mapper scope they're in still read the nearest lap.
    """
    now = time.monotonic()
    with _timers_lock:
        key_specific = _key(stage, mapper_file)
        key_default = _key(stage, None)
        start = _timers_map_global.get(key_specific)
        used_key = key_specific
        if start is None and mapper_file is not None:
            start = _timers_map_global.get(key_default)
            used_key = key_default
        _timers_map_global[used_key] = now  # arm next lap at the found slot
    if start is None:
        return None
    return max(0, int((now - start) * 1000))


def resolve_mapper_path(mapper_file: str | None, absolute_path: str | Path | None = None) -> str | None:
    """Best-effort conversion to project-root-relative POSIX path.

    Priority:
      1. absolute_path: convert to PROJECT_ROOT-relative if possible
      2. mapper_file: return as-is (already relative in many call sites)
    """
    if absolute_path:
        p = Path(absolute_path)
        try:
            return p.resolve().relative_to(PROJECT_ROOT).as_posix()
        except (ValueError, OSError):
            return str(absolute_path).replace("\\", "/")
    if mapper_file:
        return str(mapper_file).replace("\\", "/")
    return None


def _to_json(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(value)


def _warn(stage: str, err: Exception) -> None:
    # Best-effort: do not raise. Emit to stderr so operators can notice.
    print(f"[history_writer] {stage} record failed: {err}", file=sys.stderr)


def record_extract(
    *,
    mapper_file: str,
    sql_id: str,
    sql_type: str | None = None,
    namespace: str | None = None,
    seq_no: int | None = None,
    original_sql: str | None = None,
    mapper_path: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Upsert a row into extract_record (master record, one per mapper_file+sql_id).

    When `conn` is provided, reuse the caller's connection (and do not commit/close)
    so extract batches can run inside a single transaction — avoiding lock contention.

    Uses INSERT OR REPLACE on UNIQUE(mapper_file, sql_id) so re-extracting the same
    SQL updates the existing row instead of appending a duplicate.
    """
    sql = (
        "INSERT OR REPLACE INTO extract_record "
        "(mapper_path, mapper_file, sql_id, sql_type, namespace, seq_no, original_sql) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
    params = (mapper_path, mapper_file, sql_id, sql_type, namespace, seq_no, original_sql)
    try:
        if conn is not None:
            _execute_with_retry(conn, sql, params)
            return
        with _connect() as own:
            _execute_with_retry(own, sql, params)
    except Exception as err:
        _warn("extract", err)


def record_transform(
    *,
    mapper_file: str,
    sql_id: str,
    attempt_no: int | None = None,
    original_sql: str | None = None,
    transformed_sql: str | None = None,
    transform_log: str | None = None,
    model_id: str | None = None,
    status: str | None = None,
    error_message: str | None = None,
    duration_ms: int | None = None,
    mapper_path: str | None = None,
) -> None:
    if duration_ms is None:
        duration_ms = pop_duration_ms("transform")
    sql = (
        "INSERT INTO transform_history "
        "(mapper_path, mapper_file, sql_id, attempt_no, "
        " original_sql, transformed_sql, transform_log, "
        " model_id, status, error_message, duration_ms, transform_count) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    params = (
        mapper_path, mapper_file, sql_id, attempt_no,
        original_sql, transformed_sql, transform_log,
        model_id, status, error_message, duration_ms,
        attempt_no,  # legacy mirror of attempt_no
    )
    try:
        with _connect() as conn:
            _execute_with_retry(conn, sql, params)
    except Exception as err:
        _warn("transform", err)


def record_review(
    *,
    mapper_file: str,
    sql_id: str,
    round_no: int | None = None,
    reviewed_sql: str | None = None,
    syntax_result: Any = None,
    equivalence_result: Any = None,
    facilitator_verdict: str | None = None,
    review_log: str | None = None,
    duration_ms: int | None = None,
    mapper_path: str | None = None,
) -> None:
    if duration_ms is None:
        duration_ms = pop_duration_ms("review")
    sql = (
        "INSERT INTO review_history "
        "(mapper_path, mapper_file, sql_id, round_no, "
        " reviewed_sql, syntax_result, equivalence_result, "
        " facilitator_verdict, review_log, duration_ms, review_result) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    params = (
        mapper_path, mapper_file, sql_id, round_no,
        reviewed_sql,
        _to_json(syntax_result),
        _to_json(equivalence_result),
        facilitator_verdict,
        review_log, duration_ms,
        facilitator_verdict,  # legacy mirror
    )
    try:
        with _connect() as conn:
            _execute_with_retry(conn, sql, params)
    except Exception as err:
        _warn("review", err)


def record_validate(
    *,
    mapper_file: str,
    sql_id: str,
    round_no: int | None = None,
    validated_sql: str | None = None,
    verdict: str | None = None,
    validation_log: str | None = None,
    issues_found: Any = None,
    duration_ms: int | None = None,
    mapper_path: str | None = None,
) -> None:
    if duration_ms is None:
        duration_ms = pop_duration_ms("validate")
    sql = (
        "INSERT INTO validation_history "
        "(mapper_path, mapper_file, sql_id, round_no, "
        " validated_sql, verdict, validation_log, issues_found, "
        " duration_ms, validation_result) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    params = (
        mapper_path, mapper_file, sql_id, round_no,
        validated_sql, verdict, validation_log,
        _to_json(issues_found),
        duration_ms,
        verdict,  # legacy mirror
    )
    try:
        with _connect() as conn:
            _execute_with_retry(conn, sql, params)
    except Exception as err:
        _warn("validate", err)


def record_test(
    *,
    mapper_file: str,
    sql_id: str,
    phase: str,  # phase0_explain | phase1_java | phase2_fix
    attempt_no: int | None = None,
    tested_sql: str | None = None,
    bind_parameters: Any = None,
    test_result: str | None = None,
    execution_log: str | None = None,
    sql_state: str | None = None,
    error_message: str | None = None,
    stack_trace: str | None = None,
    execution_time_ms: int | None = None,
    rows_affected: int | None = None,
    mapper_path: str | None = None,
) -> None:
    if execution_time_ms is None:
        execution_time_ms = pop_duration_ms("test")
    sql = (
        "INSERT INTO test_history "
        "(mapper_path, mapper_file, sql_id, phase, attempt_no, "
        " tested_sql, bind_parameters, test_result, execution_log, "
        " sql_state, error_message, stack_trace, "
        " execution_time_ms, rows_affected) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    params = (
        mapper_path, mapper_file, sql_id, phase, attempt_no,
        tested_sql,
        _to_json(bind_parameters),
        test_result, execution_log,
        sql_state, error_message, stack_trace,
        execution_time_ms, rows_affected,
    )
    try:
        with _connect() as conn:
            _execute_with_retry(conn, sql, params)
    except Exception as err:
        _warn("test", err)
