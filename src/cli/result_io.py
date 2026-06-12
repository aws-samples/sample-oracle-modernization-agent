"""Result I/O — record review/validate/test results, read properties.

Origins:
  - set_reviewed() <- src/agents/sql_review/tools/review_tools.py::set_reviewed()
  - set_validated() <- src/agents/sql_validate/tools/validate_tools.py::set_validated()
  - set_tested() — new (no Strands tool equivalent)
  - get_property() — new utility

Changes from originals:
  - @tool decorator + strands import removed
  - DB_PATH imported inside functions (reload-safe)
  - Rich progress emit removed (CLI = JSON stdout)
  - print() cosmetic output removed (CLI uses stderr for messages)
  - history recording preserved
"""
import sqlite3
import time
from pathlib import Path


def set_reviewed(mapper_file: str, sql_id: str, result: str,
                 violations: str = "", review_feedback: str = "") -> dict:
    """Record review result for a SQL ID.

    Args:
        mapper_file: Mapper file name
        sql_id: SQL statement ID
        result: 'PASS', 'PASS_WITH_WARNINGS', or 'FAIL'
        violations: Specific violation descriptions (for FAIL)
        review_feedback: Detailed review feedback (JSON or text)
    """
    from utils.project_paths import DB_PATH
    from utils.db_utils import update_by_mapper, query_by_mapper
    from core import history_writer as _hw

    feedback_to_store = review_feedback if review_feedback else violations
    reviewed_flag = 'F' if result == 'FAIL' else 'Y'
    next_step = 'validate' if reviewed_flag == 'Y' else 'review'

    for i in range(5):
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            try:
                update_by_mapper(conn,
                    "UPDATE transform_target_list SET reviewed=?, review_result=?, current_step=?, updated_at=CURRENT_TIMESTAMP WHERE mapper_file=? AND sql_id=?",
                    mapper_file, sql_id, extra_params=(reviewed_flag, feedback_to_store, next_step))
                conn.commit()

                # History round_no + target_file in same connection
                round_no = 1
                try:
                    n_prior = conn.execute(
                        "SELECT COUNT(*) FROM review_history WHERE mapper_file=? AND sql_id=?",
                        (mapper_file, sql_id),
                    ).fetchone()[0]
                    round_no = int(n_prior or 0) + 1
                except Exception:
                    pass

                reviewed_sql_body = ""
                try:
                    row = query_by_mapper(
                        conn.cursor(),
                        "SELECT target_file FROM transform_target_list WHERE mapper_file=? AND sql_id=?",
                        mapper_file, sql_id,
                    )
                    if row and Path(row[0]).exists():
                        reviewed_sql_body = Path(row[0]).read_text(encoding='utf-8')
                except Exception:
                    pass
            finally:
                conn.close()

            _hw.record_review(
                mapper_file=mapper_file,
                sql_id=sql_id,
                round_no=round_no,
                reviewed_sql=reviewed_sql_body,
                facilitator_verdict=result,
                review_log=feedback_to_store,
                mapper_path=_hw.resolve_mapper_path(mapper_file),
            )

            return {'status': 'ok', 'sql_id': sql_id, 'result': result, 'violations': violations}
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and i < 4:
                time.sleep(0.5 * (i + 1))
            else:
                return {'status': 'error', 'sql_id': sql_id, 'result': 'DB_ERROR', 'message': str(e)}
    return {'status': 'error', 'sql_id': sql_id, 'result': 'DB_LOCKED',
            'message': f'Database locked after 5 retries: {mapper_file}/{sql_id}'}


def set_validated(mapper_file: str, sql_id: str, result: str, notes: str = "") -> dict:
    """Record validation result for a SQL ID.

    Args:
        mapper_file: Mapper file name
        sql_id: SQL statement ID
        result: 'PASS' or 'FAIL'
        notes: Validation notes
    """
    from utils.project_paths import DB_PATH
    from utils.db_utils import update_by_mapper, query_by_mapper
    from core import history_writer as _hw

    next_step = 'test' if result == 'PASS' else 'validate'

    for i in range(5):
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            try:
                update_by_mapper(conn,
                    "UPDATE transform_target_list SET validated='Y', validation_result=?, current_step=?, updated_at=CURRENT_TIMESTAMP WHERE mapper_file=? AND sql_id=?",
                    mapper_file, sql_id, extra_params=(result, next_step))
                conn.commit()

                round_no = 1
                try:
                    n_prior = conn.execute(
                        "SELECT COUNT(*) FROM validation_history WHERE mapper_file=? AND sql_id=?",
                        (mapper_file, sql_id),
                    ).fetchone()[0]
                    round_no = int(n_prior or 0) + 1
                except Exception:
                    pass

                validated_sql_body = ""
                try:
                    row = query_by_mapper(
                        conn.cursor(),
                        "SELECT target_file FROM transform_target_list WHERE mapper_file=? AND sql_id=?",
                        mapper_file, sql_id,
                    )
                    if row and Path(row[0]).exists():
                        validated_sql_body = Path(row[0]).read_text(encoding='utf-8')
                except Exception:
                    pass
            finally:
                conn.close()

            _hw.record_validate(
                mapper_file=mapper_file,
                sql_id=sql_id,
                round_no=round_no,
                validated_sql=validated_sql_body,
                verdict=result,
                validation_log=notes,
                mapper_path=_hw.resolve_mapper_path(mapper_file),
            )

            return {'status': 'ok', 'sql_id': sql_id, 'result': result}
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and i < 4:
                time.sleep(0.5 * (i + 1))
            else:
                return {'status': 'error', 'sql_id': sql_id, 'result': str(e)}
    return {'status': 'error', 'sql_id': sql_id,
            'result': f'Database locked after 5 retries: {mapper_file}/{sql_id}'}


def set_tested(mapper_file: str, sql_id: str, result: str, notes: str = "") -> dict:
    """Record test result for a SQL ID.

    Args:
        mapper_file: Mapper file name
        sql_id: SQL statement ID
        result: 'PASS', 'FAIL', 'SKIP', or 'FIXED'
        notes: Test notes (e.g. phase2 fix details)
    """
    from utils.project_paths import DB_PATH
    from utils.db_utils import update_by_mapper

    tested_flag = "N" if result == "FAIL" else "Y"

    for i in range(5):
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            try:
                update_by_mapper(conn,
                    "UPDATE transform_target_list SET tested=?, test_result=?, test_notes=?, current_step=?, updated_at=CURRENT_TIMESTAMP WHERE mapper_file=? AND sql_id=?",
                    mapper_file, sql_id, extra_params=(tested_flag, result, notes, 'done'))
                conn.commit()
            finally:
                conn.close()

            return {'status': 'ok', 'sql_id': sql_id, 'result': result}
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and i < 4:
                time.sleep(0.5 * (i + 1))
            else:
                return {'status': 'error', 'sql_id': sql_id, 'result': str(e)}
    return {'status': 'error', 'sql_id': sql_id,
            'result': f'Database locked after 5 retries: {mapper_file}/{sql_id}'}


def get_property(key: str) -> dict:
    """Read a property value from the properties table.

    Args:
        key: Property key name

    Returns:
        Dict with key and value, or error
    """
    from utils.project_paths import DB_PATH

    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        row = conn.execute(
            "SELECT value FROM properties WHERE key = ?", (key,)
        ).fetchone()

    if row is None:
        return {'status': 'error', 'message': f'Property not found: {key}'}
    return {'status': 'ok', 'key': key, 'value': row[0]}
