"""Load mapper file list from database"""
import sqlite3
from pathlib import Path
from strands import tool
from utils.project_paths import DB_PATH


@tool
def load_mapper_list() -> dict:
    """Load mapper file list from source_xml_list table.

    Returns:
        Dict with mappers list containing file_path, file_name, relative_path
    """
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_path, file_name, relative_path FROM source_xml_list ORDER BY id")
        rows = cursor.fetchall()

    mappers = [{'file_path': r[0], 'file_name': r[1], 'relative_path': r[2]} for r in rows]
    print(f"📋 Loaded {len(mappers)} mapper files from DB")
    return {'total': len(mappers), 'mappers': mappers}


@tool
def get_pending_transforms() -> dict:
    """Get SQL IDs that have not been transformed yet (transformed='N').

    Returns:
        Dict with pending list grouped by mapper_file
    """
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT mapper_file, sql_id, sql_type, seq_no, source_file, target_file
            FROM transform_target_list
            WHERE transformed = 'N'
            ORDER BY mapper_file, seq_no
        """)
        rows = cursor.fetchall()

    pending = {}
    for mapper, sql_id, sql_type, seq, source, target in rows:
        if mapper not in pending:
            pending[mapper] = []
        pending[mapper].append({
            'sql_id': sql_id, 'sql_type': sql_type,
            'seq_no': seq, 'source_file': source, 'target_file': target
        })

    total = sum(len(v) for v in pending.values())
    print(f"📋 Pending transforms: {total} SQL IDs across {len(pending)} mappers")
    return {'total': total, 'mappers_count': len(pending), 'pending': pending}


@tool
def read_sql_source(mapper_file: str, sql_id: str) -> dict:
    """Read the extracted SQL source file for a given SQL ID.

    Args:
        mapper_file: Mapper file name (e.g. 'SellerMapper.xml')
        sql_id: SQL statement ID

    Returns:
        Dict with sql_id, sql_type, sql_body (original SQL content)
    """
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT source_file, sql_type FROM transform_target_list WHERE mapper_file = ? AND sql_id = ?",
            (mapper_file, sql_id)
        )
        row = cursor.fetchone()

    if not row:
        return {'error': f'Not found: {mapper_file}/{sql_id}'}

    source_file, sql_type = row
    path = Path(source_file)
    if not path.exists():
        return {'error': f'File not found: {source_file}'}

    content = path.read_text(encoding='utf-8')
    # Extract SQL body from between tags
    import re
    body_match = re.search(
        r'<(select|insert|update|delete|sql)\s+[^>]*id\s*=\s*["\'][^"\']+["\'][^>]*>(.*?)</\1>',
        content, re.DOTALL | re.IGNORECASE
    )
    sql_body = body_match.group(2).strip() if body_match else content

    return {'sql_id': sql_id, 'sql_type': sql_type, 'sql_body': sql_body}
