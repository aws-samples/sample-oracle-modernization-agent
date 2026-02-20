"""Save conversion report from DB status"""
import sqlite3
from pathlib import Path
from datetime import datetime
from strands import tool
from utils.project_paths import PROJECT_ROOT, DB_PATH, REPORTS_DIR


@tool
def save_conversion_report() -> dict:
    """Generate conversion report based on transform_target_list DB status.

    Returns:
        Dict with report_path and summary statistics
    """
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Summary stats
    cursor.execute("SELECT COUNT(*) FROM transform_target_list")
    total = cursor.fetchone()[0]

    if total == 0:
        conn.close()
        return {'error': 'No records in transform_target_list', 'report_path': ''}

    cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE transformed = 'Y'")
    transformed = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE transformed = 'N'")
    remaining = cursor.fetchone()[0]

    # Per-mapper stats
    cursor.execute("""
        SELECT mapper_file,
               COUNT(*) as total,
               SUM(CASE WHEN transformed='Y' THEN 1 ELSE 0 END) as done
        FROM transform_target_list
        GROUP BY mapper_file ORDER BY mapper_file
    """)
    mapper_stats = cursor.fetchall()

    # Detail list
    cursor.execute("""
        SELECT mapper_file, sql_id, sql_type, seq_no, transformed, target_file
        FROM transform_target_list ORDER BY mapper_file, seq_no
    """)
    all_records = cursor.fetchall()
    conn.close()

    # Build report
    lines = [
        "# SQL Transform Report",
        f"\n**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"\n## Summary",
        f"- Total SQL IDs: {total}",
        f"- Transformed: {transformed}",
        f"- Remaining: {remaining}",
        f"- Progress: {transformed}/{total} ({transformed*100//total if total else 0}%)",
        f"\n## Mapper Status\n",
        "| Mapper | Total | Transformed | Status |",
        "|--------|-------|-------------|--------|",
    ]

    for mapper, cnt, done in mapper_stats:
        status = "✅" if done == cnt else f"🔄 {done}/{cnt}"
        lines.append(f"| {mapper} | {cnt} | {done} | {status} |")

    lines.append(f"\n## Detail\n")
    lines.append("| Mapper | Seq | SQL ID | Type | Transformed |")
    lines.append("|--------|-----|--------|------|-------------|")
    for mapper, sql_id, sql_type, seq, flag, target in all_records:
        lines.append(f"| {mapper} | {seq:02d} | {sql_id} | {sql_type} | {flag} |")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / "transform_report.md"
    report_path.write_text('\n'.join(lines), encoding='utf-8')

    print(f"📊 Report: {report_path} ({transformed}/{total} transformed)")
    return {
        'report_path': str(report_path),
        'summary': {
            'total': total,
            'transformed': transformed,
            'remaining': remaining
        }
    }
