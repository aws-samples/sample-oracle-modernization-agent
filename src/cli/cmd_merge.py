"""oma merge — assemble transformed SQLs into final mapper XMLs (LLM-free)."""
import json
import sqlite3
import sys
import time


def register(sub):
    p = sub.add_parser("merge", help="Assemble transformed SQLs into final mapper XMLs")
    p.add_argument("--mapper", default="",
                   help="merge only this mapper (re-merge after fix, skips all-complete check)")
    p.add_argument("--json", action="store_true", dest="as_json")
    p.set_defaults(func=run)


def run(args) -> int:
    from utils.project_paths import DB_PATH, MERGE_DIR
    from cli.merger import assemble_mapper

    if not DB_PATH.exists():
        print("DB not found — run 'oma analyze' first", file=sys.stderr)
        return 1

    start_time = time.time()

    # Single-mapper mode: bypass all-complete check
    if args.mapper:
        result = assemble_mapper(args.mapper)
        if result.get('error'):
            print(f"error: {result['error']}", file=sys.stderr)
            summary = {"merged": 0, "skipped": 0, "files": 0, "error": result['error']}
        else:
            merge_count = len(list(MERGE_DIR.rglob("*.xml"))) if MERGE_DIR.exists() else 0
            summary = {"merged": 1, "skipped": 0, "files": merge_count}
        if args.as_json:
            print(json.dumps(summary, ensure_ascii=False))
        return 0 if summary["merged"] > 0 else 1

    # Full mode: check all mappers
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT mapper_file,
               COUNT(*) as total,
               SUM(CASE WHEN transformed='Y' THEN 1 ELSE 0 END) as transformed
        FROM transform_target_list
        GROUP BY mapper_file ORDER BY mapper_file
    """)
    mappers = cursor.fetchall()
    conn.close()

    if not mappers:
        print("transform_target_list is empty", file=sys.stderr)
        summary = {"merged": 0, "skipped": 0, "files": 0}
        if args.as_json:
            print(json.dumps(summary, ensure_ascii=False))
        return 0

    merged = 0
    skipped = 0

    for mapper_file, total, transformed in mappers:
        if transformed < total:
            print(f"  skip: {mapper_file} ({transformed}/{total} transformed)",
                  file=sys.stderr)
            skipped += 1
            continue

        result = assemble_mapper(mapper_file)
        if result.get('error'):
            print(f"  error: {mapper_file}: {result['error']}", file=sys.stderr)
            skipped += 1
        else:
            merged += 1

    merge_count = len(list(MERGE_DIR.rglob("*.xml"))) if MERGE_DIR.exists() else 0
    duration_ms = int((time.time() - start_time) * 1000)

    # Pipeline logger (non-fatal)
    try:
        from core.pipeline_logger import PipelineLogger
        logger = PipelineLogger(step='merge')
        logger.log_summary(merged=merged, skipped=skipped,
                           total_files=merge_count, duration_ms=duration_ms)
    except Exception:
        pass

    # HTML report generation (non-fatal)
    try:
        from core.html_report import generate_html_report
        generate_html_report()
    except Exception as e:
        print(f"[merge] report generation skipped: {e}", file=sys.stderr)

    summary = {"merged": merged, "skipped": skipped, "files": merge_count}
    if args.as_json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(f"merged={merged} skipped={skipped} files={merge_count}", file=sys.stderr)
    return 0
