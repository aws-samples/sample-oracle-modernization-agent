"""oma analyze — mapper scan/SQL extraction/metadata/strategy draft (LLM-free)"""
import json
import sys
from pathlib import Path


def register(sub):
    p = sub.add_parser("analyze", help="Scan mappers, extract SQLs, draft strategy")
    p.add_argument("--source", default="",
                   help="Java source root (default: JAVA_SOURCE_FOLDER property)")
    p.add_argument("--json", action="store_true", dest="as_json")
    p.set_defaults(func=run)


def run(args) -> int:
    source = args.source
    if not source:
        import sqlite3
        from utils.project_paths import DB_PATH
        if DB_PATH.exists():
            with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
                row = conn.execute(
                    "SELECT value FROM properties WHERE key='JAVA_SOURCE_FOLDER'"
                ).fetchone()
            source = row[0] if row else ""
    if not source:
        print("No source folder: pass --source or set JAVA_SOURCE_FOLDER via 'oma setup'",
              file=sys.stderr)
        return 1

    if not Path(source).is_dir():
        print(f"Source folder not found: {source}", file=sys.stderr)
        return 1

    from cli.analyzer import run_analyze
    summary = run_analyze(source)

    # HTML report generation (non-fatal)
    try:
        from core.html_report import generate_html_report
        generate_html_report()
    except Exception as e:
        print(f"[analyze] report generation skipped: {e}", file=sys.stderr)

    if args.as_json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(f"analyzed: {summary}", file=sys.stderr)
    return 0
