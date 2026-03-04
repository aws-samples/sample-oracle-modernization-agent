"""SQL Review tools — check rule compliance, report violations"""
import sqlite3
import time
from strands import tool
from utils.project_paths import DB_PATH, PROJECT_ROOT


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
        result: 'PASS' or 'FAIL'
        violations: Specific violation descriptions (for FAIL)
        review_feedback: Detailed review feedback JSON for re-transform guidance
    """
    feedback_to_store = review_feedback if review_feedback else violations
    for i in range(5):
        conn = None
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            conn.execute("""
                UPDATE transform_target_list
                SET reviewed = ?, review_result = ?, updated_at = CURRENT_TIMESTAMP
                WHERE mapper_file = ? AND sql_id = ?
            """, ('Y' if result == 'PASS' else 'F', feedback_to_store, mapper_file, sql_id))
            conn.commit()

            flag = "✅ PASS" if result == 'PASS' else "❌ FAIL"
            print(f"  {flag} {mapper_file}/{sql_id} {violations}")

            # Signal file for progress tracking
            try:
                signal_file = PROJECT_ROOT / "output" / "logs" / ".review_signals"
                with open(signal_file, 'a', encoding='utf-8') as f:
                    f.write(f"{mapper_file}|{sql_id}|{result}|{violations}\n")
            except Exception:
                pass
            return {'status': 'ok', 'sql_id': sql_id, 'result': result, 'violations': violations}
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and i < 4:
                time.sleep(0.5 * (i + 1))
            else:
                raise
        finally:
            if conn:
                conn.close()
