"""Assemble converted SQLs back into Mapper XML.

Reads transform/ files and reassembles into output/merge/.
Core merge logic adapted from xmlMerger.py (oma-origin).
"""
import re
import sqlite3
from pathlib import Path
from strands import tool
from utils.project_paths import PROJECT_ROOT, DB_PATH, ORIGIN_DIR, MERGE_DIR


@tool
def assemble_mapper(mapper_file: str) -> dict:
    """Reassemble converted SQL statements from transform/ into merge/.

    Reads the original mapper from origin/, replaces SQL bodies with
    converted versions from transform/, saves to merge/.

    Args:
        mapper_file: Mapper file name (e.g. 'SellerMapper.xml')
    """
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()

        # Get all converted SQL IDs for this mapper
        cursor.execute("""
            SELECT sql_id, target_file FROM transform_target_list
            WHERE mapper_file = ? AND transformed = 'Y'
            ORDER BY seq_no
        """, (mapper_file,))
        rows = cursor.fetchall()

        # Get relative_path for output directory
        # mapper_file may include sub_dir prefix (e.g., "master/Mapper.xml")
        file_name_only = Path(mapper_file).name
        cursor.execute("SELECT relative_path FROM source_xml_list WHERE file_name = ?", (file_name_only,))
        src_rows = cursor.fetchall()

    if not rows:
        return {'error': f'No converted SQLs for {mapper_file}', 'output_path': '', 'total': 0, 'success': 0}

    # If mapper_file has sub_dir prefix, use it; otherwise derive from source_xml_list
    if '/' in mapper_file:
        sub_dir = str(Path(mapper_file).parent)
    elif src_rows:
        relative_path = src_rows[0][0] if src_rows else ''
        sub_dir = str(Path(relative_path).parent) if relative_path else ''
    else:
        sub_dir = ''

    # Read original from origin/
    if sub_dir:
        origin_path = ORIGIN_DIR / sub_dir / file_name_only
    else:
        origin_path = ORIGIN_DIR / file_name_only

    if not origin_path.exists():
        return {'error': f'Origin file not found: {origin_path}', 'output_path': '', 'total': 0, 'success': 0}

    content = origin_path.read_text(encoding='utf-8')

    # Read converted SQL bodies from transform/ files
    conv_map = {}
    for sql_id, target_file in rows:
        tf = Path(target_file)
        if tf.exists():
            tc = tf.read_text(encoding='utf-8')
            # Extract SQL body from the transform file
            body_match = re.search(
                r'<(select|insert|update|delete|sql)\s+[^>]*id\s*=\s*["\'][^"\']+["\'][^>]*>(.*?)</\1>',
                tc, re.DOTALL | re.IGNORECASE
            )
            if body_match:
                conv_map[sql_id] = body_match.group(2).strip()

    # Replace SQL bodies in original content
    sql_pattern = re.compile(
        r'(<(select|insert|update|delete|sql)\s+[^>]*id\s*=\s*["\'])([^"\']+)(["\'][^>]*>)(.*?)(</\2>)',
        re.DOTALL | re.IGNORECASE
    )

    success = 0
    def replace_sql(match):
        nonlocal success
        sql_id = match.group(3)
        if sql_id in conv_map:
            success += 1
            return match.group(1) + sql_id + match.group(4) + '\n' + conv_map[sql_id] + '\n' + match.group(6)
        return match.group(0)

    converted_content = sql_pattern.sub(replace_sql, content)

    # Write to output/merge/
    if sub_dir:
        merge_dir = MERGE_DIR / sub_dir
    else:
        merge_dir = MERGE_DIR
    merge_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize HTML comments: <!-- ... --> → /* ... */ (remove <> inside)
    # Origin XML may have <!-- 주석 with <sql id="..."> --> which breaks MyBatis DTD validation
    import re as _re
    converted_content = _re.sub(
        r'<!--\s*(.*?)\s*-->',
        lambda m: '/* ' + m.group(1).replace('<', '').replace('>', '') + ' */',
        converted_content, flags=_re.DOTALL
    )

    output_path = merge_dir / file_name_only
    output_path.write_text(converted_content, encoding='utf-8')

    print(f"📦 Merged: {output_path} ({success}/{len(conv_map)} SQLs)")
    return {'output_path': str(output_path), 'total': len(conv_map), 'success': success}
