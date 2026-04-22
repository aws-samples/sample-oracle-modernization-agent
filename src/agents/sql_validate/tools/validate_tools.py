"""Read transformed SQL and update validation flag"""
import re
import sqlite3
import time
from pathlib import Path
from strands import tool
from utils.project_paths import DB_PATH
from core import history_writer as _hw


@tool
def read_transform(mapper_file: str, sql_id: str) -> dict:
    """Read the transformed PostgreSQL SQL from transform/ file.

    Args:
        mapper_file: Mapper file name
        sql_id: SQL statement ID

    Returns:
        Dict with sql_id, sql_type, sql_body (transformed SQL)
    """
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        from utils.db_utils import query_by_mapper
        row = query_by_mapper(
            cursor,
            "SELECT target_file, sql_type FROM transform_target_list WHERE mapper_file = ? AND sql_id = ?",
            mapper_file, sql_id
        )

    if not row:
        return {'error': f'Not found: {mapper_file}/{sql_id}'}

    target_file, sql_type = row
    path = Path(target_file)
    if not path.exists():
        return {'error': f'File not found: {target_file}'}

    content = path.read_text(encoding='utf-8')
    body_match = re.search(
        r'<(select|insert|update|delete|sql)\s+[^>]*id\s*=\s*["\'][^"\']+["\'][^>]*>(.*?)</\1>',
        content, re.DOTALL | re.IGNORECASE
    )
    sql_body = body_match.group(2).strip() if body_match else content

    return {'sql_id': sql_id, 'sql_type': sql_type, 'sql_body': sql_body}


@tool
def set_validated(mapper_file: str, sql_id: str, result: str, notes: str = "") -> dict:
    """Update validation flag for a SQL ID.

    Args:
        mapper_file: Mapper file name
        sql_id: SQL statement ID
        result: 'PASS' or 'FAIL'
        notes: Validation notes
    """
    next_step = 'test' if result == 'PASS' else 'validate'
    for i in range(5):
        try:
            with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
                from utils.db_utils import update_by_mapper
                update_by_mapper(conn,
                    "UPDATE transform_target_list SET validated='Y', validation_result=?, current_step=?, updated_at=CURRENT_TIMESTAMP WHERE mapper_file=? AND sql_id=?",
                    mapper_file, sql_id, extra_params=(result, next_step))
                conn.commit()
            flag = "✅ PASS" if result == 'PASS' else "🔄 FIXED"
            print(f"  {flag} {mapper_file}/{sql_id} {notes}")

            # Append-only validation history (non-fatal on failure)
            try:
                with sqlite3.connect(str(DB_PATH), timeout=10) as hist_conn:
                    n_prior = hist_conn.execute(
                        "SELECT COUNT(*) FROM validation_history WHERE mapper_file=? AND sql_id=?",
                        (mapper_file, sql_id),
                    ).fetchone()[0]
                round_no = int(n_prior or 0) + 1
            except Exception:
                round_no = 1

            validated_sql_body = ""
            try:
                with sqlite3.connect(str(DB_PATH), timeout=5) as tgt_conn:
                    from utils.db_utils import query_by_mapper
                    row = query_by_mapper(
                        tgt_conn.cursor(),
                        "SELECT target_file FROM transform_target_list WHERE mapper_file=? AND sql_id=?",
                        mapper_file, sql_id,
                    )
                if row and Path(row[0]).exists():
                    validated_sql_body = Path(row[0]).read_text(encoding='utf-8')
            except Exception:
                pass

            _hw.record_validate(
                mapper_file=mapper_file,
                sql_id=sql_id,
                round_no=round_no,
                validated_sql=validated_sql_body,
                verdict=result,
                validation_log=notes,
                mapper_path=_hw.resolve_mapper_path(mapper_file),
            )

            # Emit progress event via thread-safe queue
            from core.progress import emit_progress
            emit_progress(mapper_file, sql_id, result, notes)
            return {'status': 'ok', 'sql_id': sql_id, 'result': result}
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and i < 4:
                time.sleep(0.5 * (i + 1))
            else:
                return {'status': 'error', 'sql_id': sql_id, 'result': str(e)}
    return {'status': 'error', 'sql_id': sql_id, 'result': f'Database locked after 5 retries: {mapper_file}/{sql_id}'}


@tool
def get_pending_validations() -> dict:
    """Get SQL IDs where transformed='Y' AND validated='N'.

    Returns:
        Dict with pending list grouped by mapper_file
    """
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        # Check if reviewed column exists
        cursor.execute("PRAGMA table_info(transform_target_list)")
        cols = [r[1] for r in cursor.fetchall()]
        if 'reviewed' in cols:
            cursor.execute("""
                SELECT mapper_file, sql_id, sql_type, source_file, target_file
                FROM transform_target_list
                WHERE transformed = 'Y' AND reviewed = 'Y' AND validated = 'N'
                ORDER BY mapper_file, seq_no
            """)
        else:
            cursor.execute("""
                SELECT mapper_file, sql_id, sql_type, source_file, target_file
                FROM transform_target_list
                WHERE transformed = 'Y' AND validated = 'N'
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
    print(f"📋 Pending validations: {total} SQL IDs across {len(pending)} mappers")
    return {'total': total, 'mappers_count': len(pending), 'pending': pending}
