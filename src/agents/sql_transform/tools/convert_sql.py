"""Store converted SQL results and update DB flags"""
import sqlite3
import time
from pathlib import Path
from strands import tool
from utils.project_paths import PROJECT_ROOT, DB_PATH


def _db_execute_with_retry(func, max_retries=5):
    """Execute DB operation with retry for concurrent access."""
    for i in range(max_retries):
        try:
            return func()
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and i < max_retries - 1:
                time.sleep(0.5 * (i + 1))
            else:
                raise


def _save_fix_history(mapper_file, sql_id, target_path, new_sql, notes):
    """Save original/before/after log when overwriting an existing transform file."""
    if not target_path.exists():
        return
    fix_dir = PROJECT_ROOT / "output" / "logs" / "fix_history"
    fix_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{Path(mapper_file).stem}_{sql_id}"
    existing = list(fix_dir.glob(f"{stem}_v*.log"))
    ver = len(existing) + 1
    log_path = fix_dir / f"{stem}_v{ver}.log"
    old_sql = target_path.read_text(encoding='utf-8')

    # Read original Oracle SQL for reference
    original = ""
    try:
        with sqlite3.connect(str(DB_PATH), timeout=5) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT source_file FROM transform_target_list WHERE mapper_file=? AND sql_id=?",
                (mapper_file, sql_id)
            )
            row = cursor.fetchone()
        if row and Path(row[0]).exists():
            original = Path(row[0]).read_text(encoding='utf-8')
    except Exception:
        pass

    content = (
        f"=== FIX v{ver} | {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
        f"Notes: {notes}\n\n"
    )
    if original:
        content += f"--- ORIGINAL (Oracle) ---\n{original}\n\n"
    content += f"--- BEFORE (PG) ---\n{old_sql}\n\n--- AFTER (PG) ---\n{new_sql}\n"
    log_path.write_text(content, encoding='utf-8')


@tool
def convert_sql(sql_id: str, converted_sql: str, mapper_file: str, notes: str = "") -> dict:
    """Save a converted SQL result to file and update DB flag.

    The LLM performs the actual Oracle→PostgreSQL conversion.
    This tool saves the converted result to the target file and sets transformed='Y'.

    Args:
        sql_id: SQL statement ID
        converted_sql: Converted PostgreSQL SQL
        mapper_file: Source mapper file name
        notes: Conversion notes (e.g. 'MANUAL_REVIEW')
    """
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()

        # Get target_file and source info from DB
        cursor.execute("""
            SELECT id, target_file, source_file, namespace, sql_type, seq_no
            FROM transform_target_list
            WHERE mapper_file = ? AND sql_id = ?
        """, (mapper_file, sql_id))
        row = cursor.fetchone()

    if not row:
        return {'status': 'error', 'message': f'Not found in DB: {mapper_file}/{sql_id}'}

    record_id, target_file, source_file, namespace, sql_type, seq_no = row

    # Read original XML to get header/doctype and tag attributes
    source_path = Path(source_file)
    if source_path.exists():
        import re
        content = source_path.read_text(encoding='utf-8')
        header_match = re.search(r'(<\?xml.*?\?>)', content, re.DOTALL)
        doctype_match = re.search(r'(<!DOCTYPE.*?>)', content, re.DOTALL)
        xml_header = header_match.group(1) if header_match else '<?xml version="1.0" encoding="UTF-8"?>'
        xml_doctype = doctype_match.group(1) if doctype_match else ''
        
        # Extract original tag attributes (resultType, parameterType, etc.)
        tag_pattern = rf'<{sql_type}\s+([^>]+)>'
        tag_match = re.search(tag_pattern, content)
        if tag_match:
            # Parse attributes from original tag
            attrs_str = tag_match.group(1)
            # Remove id attribute and keep others
            attrs_str = re.sub(r'id\s*=\s*["\'][^"\']*["\']', '', attrs_str).strip()
            tag_attrs = f' {attrs_str}' if attrs_str else ''
        else:
            tag_attrs = ''
    else:
        xml_header = '<?xml version="1.0" encoding="UTF-8"?>'
        xml_doctype = ''
        tag_attrs = ''

    # Write converted SQL to target file
    target_path = Path(target_file)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Save fix history log (before overwrite) for Test/Validate phase debugging
    _save_fix_history(mapper_file, sql_id, target_path, converted_sql, notes)

    # Build individual XML file (same format as xmlExtractor output)
    note_comment = f"\n<!-- NOTES: {notes} -->" if notes else ""
    output_content = f"""{xml_header}
{xml_doctype}
<mapper namespace="{namespace}">
{note_comment}
<{sql_type} id="{sql_id}"{tag_attrs}>
{converted_sql}
</{sql_type}>
</mapper>
"""
    target_path.write_text(output_content, encoding='utf-8')

    # Update DB flag
    def _update_db():
        with sqlite3.connect(str(DB_PATH), timeout=10) as conn2:
            conn2.execute("""
                UPDATE transform_target_list
                SET transformed = 'Y', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (record_id,))
            conn2.commit()

    _db_execute_with_retry(_update_db)

    flag = f" ⚠️ {notes}" if notes else ""
    print(f"  💾 {mapper_file}/{sql_id} → {target_path.name} [transformed=Y]{flag}")
    
    # Write completion signal to progress callback file (for run_sql_transform.py)
    try:
        signal_file = PROJECT_ROOT / "output" / "logs" / ".transform_signals"
        signal_file.parent.mkdir(parents=True, exist_ok=True)
        with open(signal_file, 'a', encoding='utf-8') as f:
            f.write(f"{mapper_file}|{sql_id}|{notes}\n")
    except Exception:
        pass

    return {'status': 'saved', 'sql_id': sql_id, 'target_file': target_file}


def clear_conversions():
    """Clear signal file from previous runs."""
    signal_file = PROJECT_ROOT / "output" / "logs" / ".transform_signals"
    if signal_file.exists():
        signal_file.unlink()
