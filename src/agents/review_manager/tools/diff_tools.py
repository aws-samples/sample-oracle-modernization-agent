"""Diff tools — SQL comparison, approval, and reporting"""
import sqlite3
import difflib
import re
from datetime import datetime
from pathlib import Path
from strands import tool
from utils.project_paths import DB_PATH, PROJECT_ROOT, REPORTS_DIR


def _print_rich_diff(mapper_file: str, sql_id: str, diff_text: str):
    """Display unified diff with git-like coloring on stderr."""
    from rich.console import Console
    from rich.text import Text
    from rich.panel import Panel

    console = Console(stderr=True)
    colored = Text()
    for line in diff_text.splitlines():
        if line.startswith('---'):
            colored.append(line + "\n", style="bold red")
        elif line.startswith('+++'):
            colored.append(line + "\n", style="bold green")
        elif line.startswith('@@'):
            colored.append(line + "\n", style="bold cyan")
        elif line.startswith('-'):
            colored.append(line + "\n", style="red")
        elif line.startswith('+'):
            colored.append(line + "\n", style="green")
        else:
            colored.append(line + "\n")

    console.print(Panel(colored, title=f"[bold]{mapper_file} / {sql_id}[/bold]", border_style="blue"))


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
        fromfile='Oracle', tofile='Converted', lineterm=''
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
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()

        queries = {
            'failed_validation': "SELECT mapper_file, sql_id, sql_type FROM transform_target_list WHERE transformed='Y' AND validated='N' ORDER BY mapper_file, seq_no",
            'failed_test': "SELECT mapper_file, sql_id, sql_type FROM transform_target_list WHERE transformed='Y' AND validated='Y' AND tested='N' ORDER BY mapper_file, seq_no",
            'not_tested': "SELECT mapper_file, sql_id, sql_type FROM transform_target_list WHERE transformed='Y' AND (tested IS NULL OR tested='N') ORDER BY mapper_file, seq_no",
            'all': "SELECT mapper_file, sql_id, sql_type, validated, tested FROM transform_target_list WHERE transformed='Y' ORDER BY mapper_file, seq_no",
        }
        cursor.execute(queries.get(filter_type, queries['all']))
        rows = cursor.fetchall()

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
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT source_file, target_file FROM transform_target_list WHERE mapper_file=? AND sql_id=?",
            (mapper_file, sql_id)
        )
        row = cursor.fetchone()

    if not row:
        return {'status': 'error', 'message': f'Not found: {mapper_file}/{sql_id}'}

    result = _get_sql_diff_internal(row[0], row[1])
    result['mapper_file'] = mapper_file
    result['sql_id'] = sql_id

    # Display colored diff to terminal (stderr)
    if result.get('status') == 'success' and result.get('diff', '') != 'No changes':
        _print_rich_diff(mapper_file, sql_id, result['diff'])

    return result


@tool
def generate_diff_report(mapper_file: str = None) -> dict:
    """Generate diff report for all transformed SQLs.

    Args:
        mapper_file: Optional — specific mapper only

    Returns:
        Dict with report path
    """
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
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
            lines.append("**Converted (After)**\n```sql")
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
def generate_test_failure_report() -> dict:
    """Generate test failure report with per-SQL briefing.

    After the Test phase, ReviewManager calls this to:
    1. Identify all SQLs that failed testing
    2. Read original Oracle SQL and converted SQL for each failure
    3. Categorize failure reasons (missing function, missing table, syntax error, etc.)
    4. Generate an MD report with per-SQL ID briefing (including XML file info)

    Returns:
        Dict with report_path, summary, and per-SQL failure briefings
    """
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()

        # Get all test results
        cursor.execute("""
            SELECT COUNT(*) FROM transform_target_list WHERE tested = 'Y'
        """)
        total_tested = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM transform_target_list
            WHERE tested = 'Y' AND test_result = 'PASS'
        """)
        passed = cursor.fetchone()[0]

        # Get failures with details
        cursor.execute("""
            SELECT mapper_file, sql_id, sql_type, seq_no,
                   source_file, target_file, test_result,
                   review_notes, validation_result
            FROM transform_target_list
            WHERE tested = 'Y' AND (test_result IS NULL OR test_result != 'PASS')
            ORDER BY mapper_file, seq_no
        """)
        failures = cursor.fetchall()

    failed = len(failures)
    pass_rate = (passed * 100 // total_tested) if total_tested else 0

    # Build briefings per SQL
    briefings = []
    categories = {}
    for mapper, sql_id, sql_type, seq, source_file, target_file, test_result, notes, val_result in failures:
        # Read source and target SQL
        source_sql = ""
        target_sql = ""
        if source_file and Path(source_file).exists():
            source_sql = Path(source_file).read_text(encoding='utf-8').strip()
        if target_file and Path(target_file).exists():
            target_sql = Path(target_file).read_text(encoding='utf-8').strip()

        # Categorize
        reason = _categorize_failure(test_result or "", notes or "")
        if reason not in categories:
            categories[reason] = []
        categories[reason].append(f"{mapper}/{sql_id}")

        briefings.append({
            'mapper_file': mapper,
            'sql_id': sql_id,
            'sql_type': sql_type,
            'category': reason,
            'error': test_result or "Unknown",
            'source_sql': source_sql,
            'target_sql': target_sql,
        })

    # Build report
    lines = [
        "# Test Failure Report",
        f"\n**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"\n## Summary",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Tested | {total_tested} |",
        f"| Passed | {passed} |",
        f"| **Failed** | **{failed}** |",
        f"| **Pass Rate** | **{pass_rate}%** |",
    ]

    # Failure categories
    if categories:
        lines.append(f"\n## Failure Categories\n")
        for reason, sqls in sorted(categories.items(), key=lambda x: -len(x[1])):
            lines.append(f"### {reason} ({len(sqls)} cases)")
            for sql in sqls:
                lines.append(f"- `{sql}`")
            lines.append("")

    # Per-SQL briefing
    if briefings:
        lines.append(f"\n## Per-SQL Failure Briefing\n")
        current_mapper = None
        for b in briefings:
            if b['mapper_file'] != current_mapper:
                current_mapper = b['mapper_file']
                lines.append(f"\n### {current_mapper}\n")

            lines.append(f"#### `{b['sql_id']}` ({b['sql_type']})")
            lines.append(f"- **Category**: {b['category']}")
            lines.append(f"- **Error**: `{b['error'][:200]}`")
            lines.append("")

            if b['target_sql']:
                lines.append("<details>")
                lines.append(f"<summary>Converted SQL (click to expand)</summary>\n")
                lines.append("```sql")
                lines.append(b['target_sql'])
                lines.append("```")
                lines.append("</details>\n")

    # Recommended actions
    lines.append(f"\n## Recommended Actions\n")
    for reason, sqls in sorted(categories.items(), key=lambda x: -len(x[1])):
        count = len(sqls)
        if "missing function" in reason.lower():
            lines.append(f"1. **{reason}** ({count} cases): Create user-defined functions in target DB, then re-test")
        elif "missing table" in reason.lower():
            lines.append(f"1. **{reason}** ({count} cases): Verify table migration or schema setup")
        elif "syntax" in reason.lower():
            lines.append(f"1. **{reason}** ({count} cases): Review conversion rules, fix SQL, re-transform")
        elif "type" in reason.lower():
            lines.append(f"1. **{reason}** ({count} cases): Check parameter casting with metadata lookup")
        else:
            lines.append(f"1. **{reason}** ({count} cases): Manual review required")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / "test_failure_report.md"
    report_path.write_text('\n'.join(lines), encoding='utf-8')

    print(f"📊 Test Failure Report: {report_path} (failed: {failed}/{total_tested}, rate: {pass_rate}%)")
    return {
        'report_path': str(report_path),
        'summary': {
            'total_tested': total_tested,
            'passed': passed,
            'failed': failed,
            'pass_rate': pass_rate,
        },
        'briefings': briefings,
    }


def _categorize_failure(result: str, notes: str) -> str:
    """Categorize failure reason from error message."""
    text = ((result or "") + " " + (notes or "")).lower()
    if "does not exist" in text and "function" in text:
        return "Missing Function"
    if "does not exist" in text and ("table" in text or "relation" in text):
        return "Missing Table/Relation"
    if "syntax error" in text:
        return "Syntax Error"
    if ("type" in text or "cast" in text) and ("mismatch" in text or "error" in text):
        return "Type Mismatch"
    if "column" in text and "does not exist" in text:
        return "Missing Column"
    if "permission" in text or "denied" in text:
        return "Permission Denied"
    if result:
        return "Other"
    return "Unknown"


@tool
def approve_conversion(mapper_file: str, sql_id: str, notes: str = "") -> dict:
    """Approve SQL conversion after manual review.

    Args:
        mapper_file: Mapper file name
        sql_id: SQL statement ID
        notes: Optional review notes
    """
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM transform_target_list WHERE mapper_file=? AND sql_id=?",
            (mapper_file, sql_id)
        )
        if not cursor.fetchone():
            return {'status': 'error', 'message': f'Not found: {mapper_file}/{sql_id}'}

        # Schema now includes 'review_notes' column from initial CREATE TABLE
        cursor.execute(
            "UPDATE transform_target_list SET reviewed='Y', review_notes=?, updated_at=CURRENT_TIMESTAMP WHERE mapper_file=? AND sql_id=?",
            (notes, mapper_file, sql_id)
        )
        conn.commit()
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
