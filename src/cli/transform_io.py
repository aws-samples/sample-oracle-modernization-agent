"""Transform I/O — ported from Strands agent tools for CLI subagent use.

Origins:
  - save_transform() ← src/agents/sql_transform/tools/convert_sql.py::convert_sql()
  - read_sql_source() ← src/agents/sql_transform/tools/load_mapper_list.py::read_sql_source()

Changes from originals:
  - @tool decorator + strands import removed
  - DB_PATH / OUTPUT_DIR / PROJECT_ROOT imported inside functions (reload-safe)
  - MODEL_ID replaced with "cc-subagent" literal
  - Rich progress emit removed
  - _save_fix_history uses OUTPUT_DIR for fix_history path
"""
import sqlite3
import time
from pathlib import Path

_current_step = "transform"


def set_step(step: str):
    """Runner calls this before invocation to set the current pipeline step."""
    global _current_step
    _current_step = step


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
    from utils.project_paths import DB_PATH, OUTPUT_DIR

    if not target_path.exists():
        return
    fix_dir = OUTPUT_DIR / "logs" / "fix_history"
    fix_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{Path(mapper_file).stem}_{sql_id}"
    existing = list(fix_dir.glob(f"{stem}_v*.log"))
    ver = len(existing) + 1
    log_path = fix_dir / f"{stem}_v{ver}_{_current_step}.log"
    old_sql = target_path.read_text(encoding='utf-8')

    # Read original Oracle SQL for reference
    original = ""
    try:
        _conn = sqlite3.connect(str(DB_PATH), timeout=5)
        try:
            _row = _conn.execute(
                "SELECT source_file FROM transform_target_list WHERE mapper_file=? AND sql_id=?",
                (mapper_file, sql_id)
            ).fetchone()
        finally:
            _conn.close()
        if _row and Path(_row[0]).exists():
            original = Path(_row[0]).read_text(encoding='utf-8')
    except Exception:
        pass

    content = (
        f"=== FIX v{ver} [{_current_step}] | {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
        f"Notes: {notes}\n\n"
    )
    if original:
        content += f"--- ORIGINAL (Oracle) ---\n{original}\n\n"
    content += f"--- BEFORE (PG) ---\n{old_sql}\n\n--- AFTER (PG) ---\n{new_sql}\n"
    log_path.write_text(content, encoding='utf-8')


def save_transform(sql_id: str, converted_sql: str, mapper_file: str, notes: str = "") -> dict:
    """Save a converted SQL result to file and update DB flag.

    The LLM performs the actual Oracle->Target DB conversion.
    This tool saves the converted result to the target file and sets transformed='Y'.

    Args:
        sql_id: SQL statement ID
        converted_sql: Converted target DB SQL
        mapper_file: Source mapper file name
        notes: Conversion notes (e.g. 'MANUAL_REVIEW')
    """
    from utils.project_paths import DB_PATH
    from core import history_writer as _hw

    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        from utils.db_utils import query_by_mapper
        row = query_by_mapper(
            conn.cursor(),
            "SELECT id, target_file, source_file, namespace, sql_type, seq_no FROM transform_target_list WHERE mapper_file = ? AND sql_id = ?",
            mapper_file, sql_id
        )
    finally:
        conn.close()

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

    # Sanitize: remove <> from SQL comments to prevent XML parsing errors
    import re

    def _sanitize_sql_comments(sql: str) -> str:
        """Remove angle brackets and nested comments from SQL to prevent parse errors.

        Handles nested /* */ by stripping inner delimiters before outer comment closes.
        e.g., /* [OMA] selectInvnList - /* ... */ NVL->COALESCE */ -> single comment
        """
        # First pass: flatten nested comments
        # Find outermost /* ... */ allowing nested ones
        result = []
        i = 0
        while i < len(sql):
            if sql[i:i+2] == '/*':
                depth = 1
                start = i
                i += 2
                while i < len(sql) and depth > 0:
                    if sql[i:i+2] == '/*':
                        depth += 1
                        i += 2
                    elif sql[i:i+2] == '*/':
                        depth -= 1
                        if depth == 0:
                            i += 2
                            break
                        i += 2
                    else:
                        i += 1
                inner = sql[start+2:i-2]
                inner = inner.replace('/*', '').replace('*/', '')
                inner = inner.replace('<', '[').replace('>', ']')
                result.append(f"/*{inner}*/")
            else:
                result.append(sql[i])
                i += 1
        return ''.join(result)

    converted_sql = _sanitize_sql_comments(converted_sql)

    # Build individual XML file (same format as xmlExtractor output)
    sanitized_notes = notes.replace('<', '[').replace('>', ']') if notes else ""
    note_comment = f"\n<!-- NOTES: {sanitized_notes} -->" if sanitized_notes else ""
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
        from utils.project_paths import DB_PATH as _dbp
        conn2 = sqlite3.connect(str(_dbp), timeout=10)
        try:
            conn2.execute("""
                UPDATE transform_target_list
                SET transformed = 'Y', current_step = 'review', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (record_id,))
            conn2.commit()
        finally:
            conn2.close()

    _db_execute_with_retry(_update_db)

    # Append-only transform history (non-fatal on failure)
    attempt_no = 1
    try:
        from utils.project_paths import DB_PATH as _dbp2
        hist_conn = sqlite3.connect(str(_dbp2), timeout=10)
        try:
            n_prior = hist_conn.execute(
                "SELECT COUNT(*) FROM transform_history WHERE mapper_file=? AND sql_id=?",
                (mapper_file, sql_id),
            ).fetchone()[0]
            attempt_no = int(n_prior or 0) + 1
        finally:
            hist_conn.close()
    except Exception:
        pass

    original_sql_body = ""
    try:
        if source_path.exists():
            original_sql_body = source_path.read_text(encoding='utf-8')
    except Exception:
        pass

    single_tag_sql = (
        f'<{sql_type} id="{sql_id}"{tag_attrs}>\n{converted_sql}\n</{sql_type}>'
    )
    _hw.record_transform(
        mapper_file=mapper_file,
        sql_id=sql_id,
        attempt_no=attempt_no,
        original_sql=original_sql_body,
        transformed_sql=single_tag_sql,
        transform_log=notes,
        model_id="cc-subagent",
        status='success',
        mapper_path=_hw.resolve_mapper_path(mapper_file),
    )

    return {'status': 'saved', 'sql_id': sql_id, 'target_file': target_file}


def read_sql_source(mapper_file: str, sql_id: str) -> dict:
    """Read the extracted SQL source file for a given SQL ID.

    Args:
        mapper_file: Mapper file name (e.g. 'SellerMapper.xml')
        sql_id: SQL statement ID

    Returns:
        Dict with sql_id, sql_type, sql_body (original SQL content)
    """
    from utils.project_paths import DB_PATH

    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        cursor = conn.cursor()
        from utils.db_utils import query_by_mapper
        row = query_by_mapper(
            cursor,
            "SELECT source_file, sql_type FROM transform_target_list WHERE mapper_file = ? AND sql_id = ?",
            mapper_file, sql_id
        )
    finally:
        conn.close()

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
