"""SQL Review tools — check rule compliance, report violations"""
import sqlite3
import time
from strands import tool
from utils.project_paths import DB_PATH


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
    for i in range(5):
        try:
            with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
                conn.execute("""
                    UPDATE transform_target_list
                    SET reviewed = ?, review_result = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE mapper_file = ? AND sql_id = ?
                """, (reviewed_flag, feedback_to_store, mapper_file, sql_id))
                conn.commit()

            if result == 'PASS':
                flag = "✅ PASS"
            elif result == 'PASS_WITH_WARNINGS':
                flag = "⚠️  PASS_WITH_WARNINGS"
            else:
                flag = "❌ FAIL"
            print(f"  {flag} {mapper_file}/{sql_id} {violations}")

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
