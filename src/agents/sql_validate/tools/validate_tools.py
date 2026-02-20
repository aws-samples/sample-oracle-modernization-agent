"""Read transformed SQL and update validation flag"""
import re
import sqlite3
import time
from pathlib import Path
from strands import tool
from utils.project_paths import DB_PATH, PROJECT_ROOT


@tool
def read_transform(mapper_file: str, sql_id: str) -> dict:
    """Read the transformed PostgreSQL SQL from transform/ file.

    Args:
        mapper_file: Mapper file name
        sql_id: SQL statement ID

    Returns:
        Dict with sql_id, sql_type, sql_body (transformed SQL)
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT target_file, sql_type FROM transform_target_list WHERE mapper_file = ? AND sql_id = ?",
        (mapper_file, sql_id)
    )
    row = cursor.fetchone()
    conn.close()

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
    for i in range(5):
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            conn.execute("""
                UPDATE transform_target_list
                SET validated = 'Y', updated_at = CURRENT_TIMESTAMP
                WHERE mapper_file = ? AND sql_id = ?
            """, (mapper_file, sql_id))
            conn.commit()
            conn.close()
            flag = "✅ PASS" if result == 'PASS' else "🔄 FIXED"
            print(f"  {flag} {mapper_file}/{sql_id} {notes}")
            # Write signal for progress tracking
            try:
                signal_file = PROJECT_ROOT / "output" / "logs" / ".validate_signals"
                with open(signal_file, 'a', encoding='utf-8') as f:
                    f.write(f"{mapper_file}|{sql_id}|{result}|{notes}\n")
            except:
                pass
            return {'status': 'ok', 'sql_id': sql_id, 'result': result}
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and i < 4:
                time.sleep(0.5 * (i + 1))
            else:
                raise


@tool
def get_pending_validations() -> dict:
    """Get SQL IDs where transformed='Y' AND validated='N'.

    Returns:
        Dict with pending list grouped by mapper_file
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
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
    print(f"📋 Pending validations: {total} SQL IDs across {len(pending)} mappers")
    return {'total': total, 'mappers_count': len(pending), 'pending': pending}
