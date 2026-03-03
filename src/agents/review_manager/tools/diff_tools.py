"""Diff tools — SQL comparison, approval, and reporting"""
import sqlite3
import difflib
import re
from datetime import datetime
from pathlib import Path
from strands import tool
from utils.project_paths import DB_PATH, PROJECT_ROOT, REPORTS_DIR


def _extract_sql(content):
    """Extract SQL body from XML"""
    sql = re.sub(r'<\?xml.*?\?>', '', content)
    sql = re.sub(r'<!DOCTYPE.*?>', '', sql)
    sql = re.sub(r'<mapper.*?>', '', sql)
    sql = re.sub(r'</mapper>', '', sql)
    sql = re.sub(r'<(select|insert|update|delete|sql)[^>]*>', '', sql)
    sql = re.sub(r'</(select|insert|update|delete|sql)>', '', sql)
    sql = re.sub(r'<!--.*?-->', '', sql, flags=re.DOTALL)
    return sql.strip()


def _get_sql_diff_internal(source_file, target_file):
    """Internal: get diff between source and target SQL files"""
    source_path, target_path = Path(source_file), Path(target_file)
    if not source_path.exists() or not target_path.exists():
        return {'status': 'error', 'message': 'File not found'}

    source_sql = _extract_sql(source_path.read_text(encoding='utf-8'))
    target_sql = _extract_sql(target_path.read_text(encoding='utf-8'))

    diff = list(difflib.unified_diff(
        source_sql.splitlines(keepends=True),
        target_sql.splitlines(keepends=True),
        fromfile='Oracle', tofile='PostgreSQL', lineterm=''
    ))
    return {
        'status': 'success',
        'diff': '\n'.join(diff) if diff else 'No changes',
    }


@tool
def get_review_candidates(filter_type: str = 'all') -> dict:
    """Get list of SQLs that need review.

    Args:
        filter_type: 'all', 'failed_validation', 'failed_test', 'not_tested'

    Returns:
        Dict with candidates grouped by priority
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    cursor = conn.cursor()

    queries = {
        'failed_validation': "SELECT mapper_file, sql_id, sql_type FROM transform_target_list WHERE transformed='Y' AND validated='N' ORDER BY mapper_file, seq_no",
        'failed_test': "SELECT mapper_file, sql_id, sql_type FROM transform_target_list WHERE transformed='Y' AND validated='Y' AND tested='N' ORDER BY mapper_file, seq_no",
        'not_tested': "SELECT mapper_file, sql_id, sql_type FROM transform_target_list WHERE transformed='Y' AND (tested IS NULL OR tested='N') ORDER BY mapper_file, seq_no",
        'all': "SELECT mapper_file, sql_id, sql_type, validated, tested FROM transform_target_list WHERE transformed='Y' ORDER BY mapper_file, seq_no",
    }
    cursor.execute(queries.get(filter_type, queries['all']))
    rows = cursor.fetchall()
    conn.close()

    candidates = [{'mapper_file': r[0], 'sql_id': r[1], 'sql_type': r[2]} for r in rows]
    return {'status': 'success', 'total': len(candidates), 'candidates': candidates, 'filter_type': filter_type}


@tool
def show_sql_diff(mapper_file: str, sql_id: str) -> dict:
    """Show diff between Oracle original and PostgreSQL converted SQL.

    Args:
        mapper_file: Mapper file name
        sql_id: SQL statement ID

    Returns:
        Dict with diff output
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT source_file, target_file FROM transform_target_list WHERE mapper_file=? AND sql_id=?",
        (mapper_file, sql_id)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {'status': 'error', 'message': f'Not found: {mapper_file}/{sql_id}'}

    result = _get_sql_diff_internal(row[0], row[1])
    result['mapper_file'] = mapper_file
    result['sql_id'] = sql_id
    return result


@tool
def generate_diff_report(mapper_file: str = None) -> dict:
    """Generate diff report for all transformed SQLs.

    Args:
        mapper_file: Optional — specific mapper only

    Returns:
        Dict with report path
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    cursor = conn.cursor()
    if mapper_file:
        cursor.execute(
            "SELECT mapper_file, sql_id, sql_type, source_file, target_file FROM transform_target_list WHERE transformed='Y' AND mapper_file=? ORDER BY mapper_file, seq_no",
            (mapper_file,)
        )
    else:
        cursor.execute(
            "SELECT mapper_file, sql_id, sql_type, source_file, target_file FROM transform_target_list WHERE transformed='Y' ORDER BY mapper_file, seq_no"
        )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return {'status': 'error', 'message': 'No transformed SQLs found'}

    lines = [
        "# SQL Transformation Diff Report",
        f"\n**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Total SQLs**: {len(rows)}\n\n---\n"
    ]

    current_mapper = None
    for mapper, sql_id, sql_type, source_file, target_file in rows:
        if mapper != current_mapper:
            current_mapper = mapper
            lines.append(f"\n## {mapper}\n")
        lines.append(f"### `{sql_id}` ({sql_type})\n")
        diff = _get_sql_diff_internal(source_file, target_file)
        if diff['status'] == 'success' and diff['diff'] != 'No changes':
            oracle_sql = Path(source_file).read_text(encoding='utf-8') if Path(source_file).exists() else ''
            pg_sql = Path(target_file).read_text(encoding='utf-8') if Path(target_file).exists() else ''
            lines.append("**Oracle (Before)**\n```sql")
            lines.append(oracle_sql.strip())
            lines.append("```\n")
            lines.append("**PostgreSQL (After)**\n```sql")
            lines.append(pg_sql.strip())
            lines.append("```\n")
        else:
            lines.append("_No changes_\n")

    report_dir = REPORTS_DIR
    report_dir.mkdir(parents=True, exist_ok=True)
    name = f"diff_report_{Path(mapper_file).stem}.md" if mapper_file else "diff_report_all.md"
    report_path = report_dir / name
    report_path.write_text('\n'.join(lines), encoding='utf-8')

    return {'status': 'success', 'report_path': str(report_path), 'total_sqls': len(rows)}


@tool
def approve_conversion(mapper_file: str, sql_id: str, notes: str = "") -> dict:
    """Approve SQL conversion after manual review.

    Args:
        mapper_file: Mapper file name
        sql_id: SQL statement ID
        notes: Optional review notes
    """
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM transform_target_list WHERE mapper_file=? AND sql_id=?",
        (mapper_file, sql_id)
    )
    if not cursor.fetchone():
        conn.close()
        return {'status': 'error', 'message': f'Not found: {mapper_file}/{sql_id}'}

    # Schema now includes 'review_notes' column from initial CREATE TABLE
    cursor.execute(
        "UPDATE transform_target_list SET reviewed='Y', review_notes=?, updated_at=CURRENT_TIMESTAMP WHERE mapper_file=? AND sql_id=?",
        (notes, mapper_file, sql_id)
    )
    conn.commit()
    conn.close()
    return {'status': 'success', 'message': f'Approved: {mapper_file}/{sql_id}'}


@tool
def suggest_revision(mapper_file: str, sql_id: str, revised_sql: str, reason: str) -> dict:
    """Apply revised SQL suggested by user.

    Args:
        mapper_file: Mapper file name
        sql_id: SQL statement ID
        revised_sql: Improved PostgreSQL SQL
        reason: Reason for revision
    """
    from agents.sql_transform.tools.convert_sql import convert_sql
    result = convert_sql(sql_id, revised_sql, mapper_file, f"REVISION: {reason}")
    if result.get('status') == 'success':
        return {'status': 'success', 'message': f'Revision applied: {mapper_file}/{sql_id}', 'reason': reason}
    return {'status': 'error', 'message': f'Failed: {result}'}
