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
        from utils.db_utils import query_by_mapper
        row = query_by_mapper(cursor,
            "SELECT source_file, target_file FROM transform_target_list WHERE mapper_file=? AND sql_id=?",
            mapper_file, sql_id)

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

        # Get failures with details (including test_notes)
        cursor.execute("""
            SELECT mapper_file, sql_id, sql_type, seq_no,
                   source_file, target_file, test_result,
                   test_notes, validation_result
            FROM transform_target_list
            WHERE tested = 'Y'
              AND test_result IS NOT NULL
              AND test_result NOT IN ('PASS', 'FIXED', 'SKIP')
            ORDER BY mapper_file, seq_no
        """)
        failures = cursor.fetchall()

    failed = len(failures)
    pass_rate = (passed * 100 // total_tested) if total_tested else 0

    # Build briefings per SQL
    briefings = []
    categories = {}
    for mapper, sql_id, sql_type, seq, source_file, target_file, test_result, test_notes, val_result in failures:
        # Read source and target SQL
        source_sql = ""
        target_sql = ""
        if source_file and Path(source_file).exists():
            source_sql = Path(source_file).read_text(encoding='utf-8').strip()
        if target_file and Path(target_file).exists():
            target_sql = Path(target_file).read_text(encoding='utf-8').strip()

        # Categorize — use test_notes for detail, test_result for status
        error_detail = test_notes or test_result or "Unknown"
        reason = _categorize_failure(test_result or "", error_detail)
        if reason not in categories:
            categories[reason] = []
        categories[reason].append(f"{mapper}/{sql_id}")

        briefings.append({
            'mapper_file': mapper,
            'sql_id': sql_id,
            'sql_type': sql_type,
            'category': reason,
            'error': error_detail,
            'source_sql': source_sql,
            'target_sql': target_sql,
        })

    # Build report — clean, human-readable format
    lines = [
        "# Test Failure Report",
        f"\n**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"\n## 실패 목록\n",
        "| XML | SQL ID | 오류 이유 |",
        "|-----|--------|----------|",
    ]

    for b in briefings:
        reason = _human_readable_reason(b['category'], b['error'])
        lines.append(f"| {b['mapper_file']} | {b['sql_id']} | {reason} |")

    lines.append(f"\n전체 {total_tested}개 SQL 중 {passed}개 통과, {failed}개 실패 (Pass Rate: {pass_rate}%)\n")

    # Actionable advice grouped by category
    for cat, sqls in sorted(categories.items(), key=lambda x: -len(x[1])):
        ids = ", ".join(s.split("/")[-1] for s in sqls)
        if "missing function" in cat.lower():
            lines.append(
                f"- {ids}: SQL 변환 자체는 정상이나, "
                f"Oracle 패키지 함수를 타겟 DB 함수로 별도 마이그레이션해야 합니다."
            )
        elif "missing table" in cat.lower():
            lines.append(
                f"- {ids}: SQL 문법은 정상이나, "
                f"테스트 DB에 해당 테이블이 없어서 실패한 케이스입니다."
            )
        elif "syntax" in cat.lower():
            lines.append(
                f"- {ids}: SQL 문법 오류 — 변환 규칙 확인 후 재변환이 필요합니다."
            )
        elif "type" in cat.lower():
            lines.append(
                f"- {ids}: 타입 불일치 — 메타데이터 기반 파라미터 캐스팅 확인이 필요합니다."
            )
        else:
            lines.append(f"- {ids}: {cat} — 수동 확인이 필요합니다.")

    # SKIP recommendation
    skip_candidates = 0
    skip_reasons = []
    for cat, sqls in categories.items():
        cat_lower = cat.lower()
        if any(k in cat_lower for k in ['missing function', 'missing table', 'missing column']):
            skip_candidates += len(sqls)
            skip_reasons.append(f"{cat}: {len(sqls)}건")

    if skip_candidates > 0:
        lines.append(f"\n## SKIP 권고\n")
        lines.append(f"**{skip_candidates}건**은 SQL 변환이 아닌 인프라/스키마 이슈로, SKIP 처리 권고:\n")
        for reason in skip_reasons:
            lines.append(f"- {reason}")
        lines.append(f"\nSKIP 처리 후 재테스트:")
        lines.append(f"```")
        lines.append(f"⚛️  > retry failed test")
        lines.append(f"```")

    # Per-SQL detail (collapsible)
    if briefings:
        lines.append(f"\n---\n\n## 상세 (변환된 SQL)\n")
        for b in briefings:
            lines.append(f"### {b['mapper_file']} / `{b['sql_id']}`\n")
            lines.append(f"**오류**: `{b['error'][:200]}`\n")
            if b['target_sql']:
                lines.append("<details>")
                lines.append(f"<summary>변환된 SQL 보기</summary>\n")
                lines.append("```sql")
                lines.append(b['target_sql'])
                lines.append("```")
                lines.append("</details>\n")

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


def _human_readable_reason(category: str, error: str) -> str:
    """Convert error message to human-readable Korean reason."""
    import re
    error_lower = error.lower()

    if "does not exist" in error_lower and "function" in error_lower:
        func_match = re.search(r'function\s+(\w+)', error_lower)
        func_name = func_match.group(1) if func_match else "unknown"
        return f"{func_name} 함수가 타겟 DB에 미존재 (패키지 함수 마이그레이션 필요)"

    if "does not exist" in error_lower and ("relation" in error_lower or "table" in error_lower):
        tbl_match = re.search(r'relation\s+"?(\w+)"?', error_lower) or re.search(r'table\s+"?(\w+)"?', error_lower)
        tbl_name = tbl_match.group(1) if tbl_match else "unknown"
        return f"테이블 {tbl_name}이 타겟 DB에 미존재 (스키마 마이그레이션 필요)"

    if "column" in error_lower and "does not exist" in error_lower:
        col_match = re.search(r'column\s+"?(\w+)"?', error_lower)
        col_name = col_match.group(1) if col_match else "unknown"
        return f"컬럼 {col_name} 미존재 — 스키마 확인 필요"

    if "syntax error" in error_lower:
        return "SQL 문법 오류 — 재변환 필요"

    if "type" in error_lower and ("mismatch" in error_lower or "cast" in error_lower):
        return "타입 불일치 — 파라미터 캐스팅 확인 필요"

    return error[:100] if len(error) > 100 else error


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
        from utils.db_utils import query_by_mapper, update_by_mapper
        row = query_by_mapper(cursor,
            "SELECT id FROM transform_target_list WHERE mapper_file=? AND sql_id=?",
            mapper_file, sql_id)
        if not row:
            return {'status': 'error', 'message': f'Not found: {mapper_file}/{sql_id}'}

        update_by_mapper(conn,
            "UPDATE transform_target_list SET reviewed='Y', review_notes=?, current_step='validate', updated_at=CURRENT_TIMESTAMP WHERE mapper_file=? AND sql_id=?",
            mapper_file, sql_id, extra_params=(notes,))
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
