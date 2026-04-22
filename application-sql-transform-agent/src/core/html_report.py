"""HTML Report Generator — single self-contained file, regenerated each pipeline step.

Reads the OMA control DB + merge outputs, builds REPORT_DATA dict, and injects it
into report_template.html. Best-effort: never raises, only warns on stderr.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from utils.project_paths import (
    DB_PATH,
    MERGE_DIR,
    REPORTS_DIR,
    get_target_db_display_name,
    get_target_dbms,
)

_TEMPLATE_PATH = Path(__file__).with_name("report_template.html")
_REPORT_PATH = REPORTS_DIR / "oma_report.html"
_PLACEHOLDER = "__REPORT_DATA__"
# Keep per-SQL history arrays bounded so a 2000-SQL pipeline stays readable.
_HISTORY_CAP = 10


def _warn(msg: str) -> None:
    print(f"[html_report] {msg}", file=sys.stderr)


def _row_to_dict(cursor: sqlite3.Cursor, row: tuple) -> Dict[str, Any]:
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


def _parse_json_field(s: str | None) -> Any:
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return s


def _summary(counts: Dict[str, int]) -> Dict[str, int]:
    extracted = counts.get("extracted", 0)
    return {
        "total": extracted,
        "extracted": extracted,
        "transformed": counts.get("transformed", 0),
        "reviewed": counts.get("reviewed", 0),
        "review_failed": counts.get("review_failed", 0),
        "review_warnings": counts.get("review_warnings", 0),
        "validated": counts.get("validated", 0),
        "validate_failed": counts.get("validate_failed", 0),
        "merged": counts.get("merged", 0),
        "tested": counts.get("tested", 0),
        "test_failed": counts.get("test_failed", 0),
        "test_skipped": counts.get("test_skipped", 0),
        "test_non_testable": counts.get("test_non_testable", 0),
        "testable_total": counts.get("testable_total", 0),
        "source_analyzed": counts.get("source_analyzed", 0),
        "transform_complete": bool(counts.get("transform_complete", False)),
        "review_complete": bool(counts.get("review_complete", False)),
        "validate_complete": bool(counts.get("validate_complete", False)),
        "merge_complete": bool(counts.get("merge_complete", False)),
        "test_complete": bool(counts.get("test_complete", False)),
    }


def _stage_analyze(conn: sqlite3.Connection) -> Dict[str, Any]:
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM source_xml_list")
        xml_count = cur.fetchone()[0] or 0
    except sqlite3.OperationalError:
        xml_count = 0

    by_type: Dict[str, int] = {}
    by_mapper: List[Dict[str, Any]] = []
    sql_count = 0
    try:
        cur.execute("SELECT COUNT(*) FROM extract_record")
        sql_count = cur.fetchone()[0] or 0
        cur.execute("SELECT sql_type, COUNT(*) FROM extract_record GROUP BY sql_type")
        by_type = {(r[0] or "unknown"): r[1] for r in cur.fetchall()}

        # Per-mapper SQL list with drill-down detail.
        cur.execute(
            "SELECT e.mapper_file, e.sql_id, e.sql_type, e.namespace, "
            "       t.current_step "
            "FROM extract_record e "
            "LEFT JOIN transform_target_list t "
            "       ON t.mapper_file = e.mapper_file AND t.sql_id = e.sql_id "
            "ORDER BY e.mapper_file, e.seq_no, e.sql_id"
        )
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for mf, sid, stype, ns, step in cur.fetchall():
            grouped[mf or ""].append({
                "sql_id": sid,
                "sql_type": stype,
                "namespace": ns,
                "current_step": step or "pending",
            })
        by_mapper = [
            {"mapper_file": mf, "sql_count": len(sqls), "sqls": sqls}
            for mf, sqls in sorted(grouped.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        ]
    except sqlite3.OperationalError:
        pass

    return {
        "xml_count": xml_count,
        "sql_count": sql_count,
        "by_type": by_type,
        "by_mapper": by_mapper,
    }


def _stage_transform(conn: sqlite3.Connection) -> Dict[str, Any]:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT status, COUNT(*) FROM transform_history GROUP BY status"
        )
        by_status = {r[0] or "unknown": r[1] for r in cur.fetchall()}
        cur.execute("SELECT COUNT(*) FROM transform_history")
        total_attempts = cur.fetchone()[0] or 0
        cur.execute(
            "SELECT AVG(duration_ms) FROM transform_history WHERE duration_ms IS NOT NULL"
        )
        avg_duration = cur.fetchone()[0]
    except sqlite3.OperationalError:
        by_status, total_attempts, avg_duration = {}, 0, None

    return {
        "attempts": total_attempts,
        "by_status": by_status,
        "avg_duration_ms": int(avg_duration) if avg_duration else None,
    }


def _stage_review(conn: sqlite3.Connection) -> Dict[str, Any]:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT facilitator_verdict, COUNT(*) FROM review_history GROUP BY facilitator_verdict"
        )
        by_verdict = {r[0] or "unknown": r[1] for r in cur.fetchall()}
        cur.execute("SELECT COUNT(*) FROM review_history")
        rounds_total = cur.fetchone()[0] or 0
        cur.execute(
            "SELECT COUNT(DISTINCT mapper_file || '|' || sql_id) FROM review_history"
        )
        distinct_sqls = cur.fetchone()[0] or 0
    except sqlite3.OperationalError:
        by_verdict, rounds_total, distinct_sqls = {}, 0, 0

    rounds_avg = round(rounds_total / distinct_sqls, 2) if distinct_sqls else 0
    return {
        "rounds_total": rounds_total,
        "distinct_sqls": distinct_sqls,
        "rounds_avg": rounds_avg,
        "by_verdict": by_verdict,
    }


def _stage_validate(conn: sqlite3.Connection) -> Dict[str, Any]:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT verdict, COUNT(*) FROM validation_history GROUP BY verdict"
        )
        by_verdict = {r[0] or "unknown": r[1] for r in cur.fetchall()}
        cur.execute("SELECT COUNT(*) FROM validation_history")
        rounds_total = cur.fetchone()[0] or 0
    except sqlite3.OperationalError:
        by_verdict, rounds_total = {}, 0

    return {"rounds_total": rounds_total, "by_verdict": by_verdict}


def _stage_merge() -> Dict[str, Any]:
    files: List[Dict[str, Any]] = []
    if MERGE_DIR.exists():
        for p in sorted(MERGE_DIR.rglob("*.xml")):
            try:
                size = p.stat().st_size
            except OSError:
                size = 0
            files.append({
                "path": str(p.relative_to(MERGE_DIR)),
                "size": size,
            })
    return {
        "files_written": files,
        "count": len(files),
    }


def _stage_test(conn: sqlite3.Connection) -> Dict[str, Any]:
    cur = conn.cursor()
    phases: Dict[str, Dict[str, int]] = {}
    failures_by_sqlstate: List[Dict[str, Any]] = []
    try:
        cur.execute(
            "SELECT phase, test_result, COUNT(*) FROM test_history "
            "GROUP BY phase, test_result"
        )
        for phase, result, count in cur.fetchall():
            phase = phase or "unknown"
            result = result or "unknown"
            phases.setdefault(phase, {})[result] = count

        cur.execute(
            "SELECT sql_state, COUNT(*) FROM test_history "
            "WHERE test_result NOT IN ('PASS','FIXED','SKIP') AND sql_state IS NOT NULL "
            "GROUP BY sql_state ORDER BY COUNT(*) DESC LIMIT 20"
        )
        failures_by_sqlstate = [
            {"sql_state": r[0], "count": r[1]} for r in cur.fetchall()
        ]
    except sqlite3.OperationalError:
        pass

    return {
        "phases": phases,
        "failures_by_sqlstate": failures_by_sqlstate,
    }


def _per_sql_rows(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    cur = conn.cursor()
    rows: List[Dict[str, Any]] = []

    # Base: transform_target_list joined with extract_record.
    try:
        cur.execute(
            "SELECT t.mapper_file, t.sql_id, t.sql_type, t.namespace, t.seq_no, "
            "       t.current_step, t.transformed, t.reviewed, t.validated, t.tested, "
            "       t.review_result, t.validation_result, t.test_result, t.test_notes, "
            "       e.original_sql "
            "FROM transform_target_list t "
            "LEFT JOIN extract_record e "
            "       ON e.mapper_file = t.mapper_file AND e.sql_id = t.sql_id "
            "ORDER BY t.mapper_file, t.seq_no, t.sql_id"
        )
        base = [_row_to_dict(cur, r) for r in cur.fetchall()]
    except sqlite3.OperationalError as e:
        _warn(f"base query failed: {e}")
        return rows

    # Bucket history by composite key.
    def _gather(table: str, order: str) -> Dict[tuple, List[Dict[str, Any]]]:
        bucket: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
        try:
            # nosemgrep: sqlalchemy-execute-raw-query
            cur.execute(
                f"SELECT * FROM {table} ORDER BY mapper_file, sql_id, {order}"
            )
            for row in cur.fetchall():
                d = _row_to_dict(cur, row)
                key = (d.get("mapper_file"), d.get("sql_id"))
                bucket[key].append(d)
        except sqlite3.OperationalError as e:
            _warn(f"{table} query failed: {e}")
        return bucket

    def _history_for(bucket: Dict[tuple, List[Dict[str, Any]]],
                     mapper_file: Any, sql_id: Any) -> List[Dict[str, Any]]:
        """Fetch history with fallback: try exact key, then bare filename, then any
        'sub_dir/filename' key whose basename matches. Handles mapper_file mismatch
        where some writers stored 'Mapper.xml' and others 'sub_dir/Mapper.xml'.
        """
        exact = bucket.get((mapper_file, sql_id), [])
        base_name = (mapper_file or "").rsplit("/", 1)[-1]
        fallback = bucket.get((base_name, sql_id), []) if base_name != mapper_file else []
        merged = exact + fallback
        if merged:
            # Dedup by id when rows have primary-key 'id'.
            seen = set()
            out: List[Dict[str, Any]] = []
            for d in merged:
                rid = d.get("id")
                if rid is None or rid not in seen:
                    if rid is not None:
                        seen.add(rid)
                    out.append(d)
            return out
        return []

    transforms = _gather("transform_history", "attempt_no")
    reviews = _gather("review_history", "round_no")
    validations = _gather("validation_history", "round_no")
    tests = _gather("test_history", "phase, attempt_no")

    def _shape_transform(d: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "attempt_no": d.get("attempt_no"),
            "status": d.get("status"),
            "duration_ms": d.get("duration_ms"),
            "model_id": d.get("model_id"),
            "transformed_sql": d.get("transformed_sql"),
            "transform_log": d.get("transform_log"),
            "error_message": d.get("error_message"),
            "created_at": d.get("created_at"),
        }

    def _shape_review(d: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "round_no": d.get("round_no"),
            "facilitator_verdict": d.get("facilitator_verdict"),
            "reviewed_sql": d.get("reviewed_sql"),
            "review_log": d.get("review_log"),
            "duration_ms": d.get("duration_ms"),
            "syntax_result": _parse_json_field(d.get("syntax_result")),
            "equivalence_result": _parse_json_field(d.get("equivalence_result")),
            "created_at": d.get("created_at"),
        }

    def _shape_validate(d: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "round_no": d.get("round_no"),
            "verdict": d.get("verdict"),
            "validated_sql": d.get("validated_sql"),
            "validation_log": d.get("validation_log"),
            "duration_ms": d.get("duration_ms"),
            "issues_found": _parse_json_field(d.get("issues_found")),
            "created_at": d.get("created_at"),
        }

    def _shape_test(d: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "phase": d.get("phase"),
            "attempt_no": d.get("attempt_no"),
            "test_result": d.get("test_result"),
            "sql_state": d.get("sql_state"),
            "execution_time_ms": d.get("execution_time_ms"),
            "rows_affected": d.get("rows_affected"),
            "error_message": d.get("error_message"),
            "tested_sql": d.get("tested_sql"),
            "bind_parameters": _parse_json_field(d.get("bind_parameters")),
            "execution_log": d.get("execution_log"),
            "created_at": d.get("created_at"),
        }

    total_sqls = len(base)
    cap = None if total_sqls <= 2000 else _HISTORY_CAP

    for b in base:
        mf, sid = b.get("mapper_file"), b.get("sql_id")
        t_list = [_shape_transform(d) for d in _history_for(transforms, mf, sid)]
        r_list = [_shape_review(d) for d in _history_for(reviews, mf, sid)]
        v_list = [_shape_validate(d) for d in _history_for(validations, mf, sid)]
        x_list = [_shape_test(d) for d in _history_for(tests, mf, sid)]
        if cap is not None:
            t_list = t_list[-cap:]
            r_list = r_list[-cap:]
            v_list = v_list[-cap:]
            x_list = x_list[-cap:]

        rows.append({
            "mapper_file": b.get("mapper_file"),
            "sql_id": b.get("sql_id"),
            "sql_type": b.get("sql_type"),
            "namespace": b.get("namespace"),
            "seq_no": b.get("seq_no"),
            "current_step": b.get("current_step"),
            "flags": {
                "transformed": b.get("transformed"),
                "reviewed": b.get("reviewed"),
                "validated": b.get("validated"),
                "tested": b.get("tested"),
            },
            "review_result": b.get("review_result"),
            "validation_result": b.get("validation_result"),
            "test_result": b.get("test_result"),
            "test_notes": b.get("test_notes"),
            "original_sql": b.get("original_sql"),
            "transforms": t_list,
            "reviews": r_list,
            "validations": v_list,
            "tests": x_list,
        })

    return rows


def _collect_report_data() -> Dict[str, Any]:
    # Step counts via StateManager (reuses existing aggregation logic).
    from core.state_manager import StateManager

    counts = StateManager(DB_PATH).get_step_counts()

    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=10) as conn:
        conn.row_factory = None
        stages = {
            "analyze": _stage_analyze(conn),
            "transform": _stage_transform(conn),
            "review": _stage_review(conn),
            "validate": _stage_validate(conn),
            "merge": _stage_merge(),
            "test": _stage_test(conn),
        }
        sqls = _per_sql_rows(conn)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "dbms": get_target_dbms(),
        "dbms_display": get_target_db_display_name(),
        "summary": _summary(counts),
        "stages": stages,
        "sqls": sqls,
    }


def generate_html_report() -> Path | None:
    """Generate self-contained HTML report. Best-effort: returns None on failure."""
    try:
        if not DB_PATH.exists():
            _warn(f"DB not found at {DB_PATH}; skipping report generation")
            return None
        if not _TEMPLATE_PATH.exists():
            _warn(f"template missing: {_TEMPLATE_PATH}")
            return None

        data = _collect_report_data()
        template = _TEMPLATE_PATH.read_text(encoding="utf-8")
        payload = json.dumps(data, ensure_ascii=False, default=str)
        if _PLACEHOLDER not in template:
            _warn(f"placeholder {_PLACEHOLDER} not found in template")
            return None
        html = template.replace(_PLACEHOLDER, payload)

        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        _REPORT_PATH.write_text(html, encoding="utf-8")
        return _REPORT_PATH
    except Exception as e:
        _warn(f"generation failed: {e}")
        return None


if __name__ == "__main__":
    path = generate_html_report()
    if path:
        print(f"Report: {path}")
    else:
        sys.exit(1)
