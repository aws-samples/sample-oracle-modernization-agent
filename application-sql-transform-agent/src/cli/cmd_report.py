"""oma report -- regenerate self-contained HTML report."""
import sys


def register(sub):
    p = sub.add_parser("report", help="Regenerate HTML report from current DB state")
    p.set_defaults(func=run)


def run(args) -> int:
    from core.db_migrate import ensure_schema

    ensure_schema()

    from core.html_report import generate_html_report

    path = generate_html_report()
    if path:
        print(f"report: {path}", file=sys.stderr)
    else:
        # Best-effort: warn but do not fail (may lack data).
        from utils.project_paths import REPORTS_DIR

        print(f"report: generation skipped (see warnings above)", file=sys.stderr)
        # Still return 0 — html_report is best-effort by design.
    return 0
