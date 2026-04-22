"""SQL Review tools — check rule compliance, report violations"""
import sqlite3
import time
from pathlib import Path
from strands import tool
from utils.project_paths import DB_PATH
from core import history_writer as _hw


@tool
def get_pending_reviews() -> dict:
    """Get SQL IDs where transformed='Y' AND reviewed='N'.

    Returns:
        Dict with pending list grouped by mapper_file
    """
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT mapper_file, sql_id, sql_type, source_file, target_file
            FROM transform_target_list
            WHERE transformed = 'Y' AND reviewed = 'N'
            ORDER BY mapper_file, seq_no
        """)
        rows = cursor.fetchall()

    pending = {}
    for mapper, sql_id, sql_type, source, target in rows:
        if mapper not in pending:
            pending[mapper] = []
        pending[mapper].append({
            'sql_id': sql_id, 'sql_type': sql_type,
            'source_file': source, 'target_file': target
        })

    total = sum(len(v) for v in pending.values())
    print(f"📋 Pending reviews: {total} SQL IDs across {len(pending)} mappers")
    return {'total': total, 'mappers_count': len(pending), 'pending': pending}


@tool
def set_reviewed(mapper_file: str, sql_id: str, result: str, violations: str = "", review_feedback: str = "") -> dict:
    """Record review result for a SQL ID.

    Args:
        mapper_file: Mapper file name
        sql_id: SQL statement ID
        result: 'PASS', 'PASS_WITH_WARNINGS', or 'FAIL'
        violations: Specific violation descriptions (for FAIL)
        review_feedback: Detailed review feedback JSON for re-transform guidance
    """
    feedback_to_store = review_feedback if review_feedback else violations
    # PASS and PASS_WITH_WARNINGS both store reviewed='Y'; only FAIL stores 'F'
    reviewed_flag = 'F' if result == 'FAIL' else 'Y'
    next_step = 'validate' if reviewed_flag == 'Y' else 'review'
    for i in range(5):
        try:
            with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
                from utils.db_utils import update_by_mapper
                update_by_mapper(conn,
                    "UPDATE transform_target_list SET reviewed=?, review_result=?, current_step=?, updated_at=CURRENT_TIMESTAMP WHERE mapper_file=? AND sql_id=?",
                    mapper_file, sql_id, extra_params=(reviewed_flag, feedback_to_store, next_step))
                conn.commit()

            if result == 'PASS':
                flag = "✅ PASS"
            elif result == 'PASS_WITH_WARNINGS':
                flag = "⚠️  PASS_WITH_WARNINGS"
            else:
                flag = "❌ FAIL"
            print(f"  {flag} {mapper_file}/{sql_id} {violations}")

            # Append-only review history (non-fatal on failure)
            try:
                with sqlite3.connect(str(DB_PATH), timeout=10) as hist_conn:
                    n_prior = hist_conn.execute(
                        "SELECT COUNT(*) FROM review_history WHERE mapper_file=? AND sql_id=?",
                        (mapper_file, sql_id),
                    ).fetchone()[0]
                round_no = int(n_prior or 0) + 1
            except Exception:
                round_no = 1

            reviewed_sql_body = ""
            try:
                with sqlite3.connect(str(DB_PATH), timeout=5) as tgt_conn:
                    from utils.db_utils import query_by_mapper
                    row = query_by_mapper(
                        tgt_conn.cursor(),
                        "SELECT target_file FROM transform_target_list WHERE mapper_file=? AND sql_id=?",
                        mapper_file, sql_id,
                    )
                if row and Path(row[0]).exists():
                    reviewed_sql_body = Path(row[0]).read_text(encoding='utf-8')
            except Exception:
                pass

            _hw.record_review(
                mapper_file=mapper_file,
                sql_id=sql_id,
                round_no=round_no,
                reviewed_sql=reviewed_sql_body,
                facilitator_verdict=result,
                review_log=feedback_to_store,
                mapper_path=_hw.resolve_mapper_path(mapper_file),
            )

            # Emit progress event via thread-safe queue
            from core.progress import emit_progress
            emit_progress(mapper_file, sql_id, result, violations)
            return {'status': 'ok', 'sql_id': sql_id, 'result': result, 'violations': violations}
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and i < 4:
                time.sleep(0.5 * (i + 1))
            else:
                return {'status': 'error', 'sql_id': sql_id, 'result': 'DB_ERROR', 'violations': str(e)}
    return {'status': 'error', 'sql_id': sql_id, 'result': 'DB_LOCKED', 'violations': f'Database locked after 5 retries: {mapper_file}/{sql_id}'}
