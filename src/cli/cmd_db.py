"""oma db — 상태 DB 조회/갱신. subagent와 메인 세션의 공용 인터페이스."""
import json
import sqlite3
import sys

# step → (해당 단계 flag 컬럼, 선행 조건 WHERE)
_STEP_FILTERS = {
    "transform": "transformed = 'N'",
    "review": "transformed = 'Y' AND reviewed = 'N'",
    "validate": "reviewed = 'Y' AND validated = 'N'",
}


def register(sub):
    p = sub.add_parser("db", help="Control-DB query/update")
    dbsub = p.add_subparsers(dest="db_command", required=True)

    pend = dbsub.add_parser("pending", help="List pending work as adaptive batches")
    pend.add_argument("--step", required=True, choices=list(_STEP_FILTERS))
    pend.add_argument("--json", action="store_true", dest="as_json")
    pend.add_argument("--max-batch", type=int, default=15)
    pend.add_argument("--only", default="",
                      help="comma list of mapper:sql_id to restrict (retry)")
    pend.set_defaults(func=run_pending)

    rd = dbsub.add_parser("read-sql", help="Read original SQL body for one sql_id")
    rd.add_argument("mapper_file")
    rd.add_argument("sql_id")
    rd.add_argument("--json", action="store_true", dest="as_json")
    rd.set_defaults(func=run_read_sql)

    sv = dbsub.add_parser("save-transform", help="Save converted SQL (file or stdin)")
    sv.add_argument("mapper_file")
    sv.add_argument("sql_id")
    sv.add_argument("--sql-file", default="-",
                    help="path to converted SQL file, or '-' for stdin (default)")
    sv.add_argument("--notes", default="")
    sv.add_argument("--step", default="transform",
                    help="pipeline step writing this (transform|review|test|validate)")
    sv.add_argument("--json", action="store_true", dest="as_json")
    sv.set_defaults(func=run_save_transform)

    for name, handler in (("set-reviewed", run_set_reviewed),
                          ("set-validated", run_set_validated),
                          ("set-tested", run_set_tested)):
        sp = dbsub.add_parser(name, help=f"Record {name.split('-')[1]} result")
        sp.add_argument("mapper_file")
        sp.add_argument("sql_id")
        sp.add_argument("--result", required=True,
                        choices=["PASS", "PASS_WITH_WARNINGS", "FAIL", "SKIP", "FIXED"])
        sp.add_argument("--feedback", default="", help="inline feedback text")
        sp.add_argument("--feedback-file", default="", help="JSON feedback file (overrides --feedback)")
        sp.add_argument("--notes", default="")
        sp.add_argument("--json", action="store_true", dest="as_json")
        sp.set_defaults(func=handler)

    gp = dbsub.add_parser("get-property", help="Read a property value")
    gp.add_argument("key")
    gp.add_argument("--json", action="store_true", dest="as_json")
    gp.set_defaults(func=run_get_property)

    rs = dbsub.add_parser("reset", help="Reset step status to N")
    rs.add_argument("--step", required=True, choices=["transform", "review", "validate", "test"])
    rs.add_argument("--only", default="", help="comma list mapper:sql_id (default: all Y/F)")
    rs.set_defaults(func=run_reset)

    fp = dbsub.add_parser("feedback-patterns", help="Dump review/validate failure feedback (for strategy refine)")
    fp.add_argument("--json", action="store_true", dest="as_json")
    fp.set_defaults(func=run_feedback_patterns)


def _connect():
    from utils.project_paths import DB_PATH
    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}", file=sys.stderr)
        raise SystemExit(1)
    return sqlite3.connect(str(DB_PATH), timeout=10)


def run_read_sql(args) -> int:
    from cli.transform_io import read_sql_source
    result = read_sql_source(args.mapper_file, args.sql_id)
    if "error" in result:
        print(result["error"], file=sys.stderr)
        return 1
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(result["sql_body"])
    return 0


def run_save_transform(args) -> int:
    if args.sql_file == "-":
        converted = sys.stdin.read()
    else:
        from pathlib import Path
        p = Path(args.sql_file)
        if not p.exists():
            print(f"SQL file not found: {p}", file=sys.stderr)
            return 1
        converted = p.read_text(encoding="utf-8")

    if not converted.strip():
        print("Converted SQL is empty", file=sys.stderr)
        return 1

    from cli import transform_io
    transform_io.set_step(args.step)
    result = transform_io.save_transform(
        sql_id=args.sql_id, converted_sql=converted,
        mapper_file=args.mapper_file, notes=args.notes)

    if result.get("status") == "error":
        print(result.get("message", "unknown error"), file=sys.stderr)
        return 1
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False))
    return 0


def _load_feedback(args) -> str:
    """Load feedback from --feedback-file (if given), else --feedback."""
    if args.feedback_file:
        from pathlib import Path
        p = Path(args.feedback_file)
        if not p.exists():
            print(f"Feedback file not found: {p}", file=sys.stderr)
            raise SystemExit(1)
        return p.read_text(encoding="utf-8")
    return args.feedback


def run_set_reviewed(args) -> int:
    from cli.result_io import set_reviewed
    feedback = _load_feedback(args)
    result = set_reviewed(
        mapper_file=args.mapper_file, sql_id=args.sql_id,
        result=args.result, violations=feedback, review_feedback=feedback)
    if result.get("status") == "error":
        print(result.get("message", result.get("result", "unknown error")), file=sys.stderr)
        return 1
    if getattr(args, "as_json", False):
        print(json.dumps(result, ensure_ascii=False))
    return 0


def run_set_validated(args) -> int:
    from cli.result_io import set_validated
    feedback = _load_feedback(args)
    notes = args.notes or feedback
    result = set_validated(
        mapper_file=args.mapper_file, sql_id=args.sql_id,
        result=args.result, notes=notes)
    if result.get("status") == "error":
        print(result.get("message", result.get("result", "unknown error")), file=sys.stderr)
        return 1
    if getattr(args, "as_json", False):
        print(json.dumps(result, ensure_ascii=False))
    return 0


def run_set_tested(args) -> int:
    from cli.result_io import set_tested
    result = set_tested(
        mapper_file=args.mapper_file, sql_id=args.sql_id,
        result=args.result, notes=args.notes)
    if result.get("status") == "error":
        print(result.get("message", result.get("result", "unknown error")), file=sys.stderr)
        return 1
    if getattr(args, "as_json", False):
        print(json.dumps(result, ensure_ascii=False))
    return 0


def run_get_property(args) -> int:
    from cli.result_io import get_property
    result = get_property(args.key)
    if result.get("status") == "error":
        print(result.get("message", "unknown error"), file=sys.stderr)
        return 1
    if getattr(args, "as_json", False):
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(result["value"])
    return 0


def run_pending(args) -> int:
    where = _STEP_FILTERS[args.step]
    conn = _connect()
    try:
        # nosemgrep: python.lang.security.audit.formatted-sql-query
        # 컬럼 조건은 코드 내 고정 화이트리스트(_STEP_FILTERS), 사용자 입력 아님
        rows = conn.execute(
            f"SELECT mapper_file, sql_id, sql_type, seq_no FROM transform_target_list "
            f"WHERE {where} ORDER BY mapper_file, seq_no"
        ).fetchall()
    finally:
        conn.close()

    items = [{"mapper_file": m, "sql_id": s, "sql_type": t, "seq_no": q}
             for m, s, t, q in rows]

    if args.only:
        allowed = set(x.strip() for x in args.only.split(",") if x.strip())
        items = [i for i in items if f"{i['mapper_file']}:{i['sql_id']}" in allowed]

    from cli.batching import make_batches
    batches = make_batches(items, max_batch=args.max_batch)
    result = {"step": args.step, "total": len(items), "batches": batches}

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"pending[{args.step}]: {len(items)} SQLs / {len(batches)} batches", file=sys.stderr)
    return 0


def run_reset(args) -> int:
    """Reset step status. --only targets specific mapper:sql_id pairs; without it resets all."""
    if not args.only:
        from utils.project_paths import DB_PATH
        from core.state_manager import StateManager
        n = StateManager(DB_PATH).reset_step_status(args.step)
        print(f"reset[{args.step}]: {n} rows", file=sys.stderr)
        return 0

    col = {"transform": "transformed", "review": "reviewed",
           "validate": "validated", "test": "tested"}[args.step]
    pairs = [x.split(":", 1) for x in args.only.split(",") if ":" in x]
    conn = _connect()
    try:
        n = 0
        for mapper, sql_id in pairs:
            # nosemgrep: python.lang.security.audit.formatted-sql-query
            # col is from a code-internal fixed mapping, not user input
            cur = conn.execute(
                f"UPDATE transform_target_list SET {col}='N', updated_at=CURRENT_TIMESTAMP "
                f"WHERE mapper_file=? AND sql_id=?", (mapper.strip(), sql_id.strip()))
            n += cur.rowcount
        conn.commit()
    finally:
        conn.close()
    print(f"reset[{args.step}]: {n} rows", file=sys.stderr)
    return 0


def _parse_issues(result_text: str):
    """Parse issues from a JSON result string. Returns list or raw text."""
    try:
        data = json.loads(result_text)
        issues = data.get("issues", [])
        return issues if issues else result_text
    except (json.JSONDecodeError, TypeError):
        return result_text


def run_feedback_patterns(args) -> int:
    """Dump review/validate failure feedback for strategy refinement."""
    conn = _connect()
    try:
        # Collect review failures (reviewed='F' with review_result)
        rows = conn.execute(
            "SELECT mapper_file, sql_id, review_result FROM transform_target_list "
            "WHERE reviewed='F' AND review_result IS NOT NULL"
        ).fetchall()

        # Collect validation failures
        vrows = conn.execute(
            "SELECT mapper_file, sql_id, validation_result FROM transform_target_list "
            "WHERE validated='F' AND validation_result IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()

    if not rows and not vrows:
        if getattr(args, "as_json", False):
            print("[]")
        else:
            print("No failure feedback found.", file=sys.stderr)
        return 0

    # --json: structured output for strategy-refiner subagent
    if getattr(args, "as_json", False):
        items = []
        for mapper, sql_id, result_text in rows:
            issues = _parse_issues(result_text)
            items.append({"source": "review", "mapper_file": mapper,
                          "sql_id": sql_id, "issues": issues})
        for mapper, sql_id, result_text in vrows:
            issues = _parse_issues(result_text)
            items.append({"source": "validation", "mapper_file": mapper,
                          "sql_id": sql_id, "issues": issues})
        print(json.dumps(items, ensure_ascii=False))
        return 0

    # Human-readable text output
    if rows:
        print("=== Review Failures ===")
        for mapper, sql_id, result_text in rows:
            print(f"\n--- {mapper} : {sql_id} ---")
            issues = _parse_issues(result_text)
            if isinstance(issues, list):
                for issue in issues:
                    print(f"  - {issue}")
            else:
                print(f"  {issues}")

    if vrows:
        print("\n=== Validation Failures ===")
        for mapper, sql_id, result_text in vrows:
            print(f"\n--- {mapper} : {sql_id} ---")
            issues = _parse_issues(result_text)
            if isinstance(issues, list):
                for issue in issues:
                    print(f"  - {issue}")
            else:
                print(f"  {issues}")

    return 0
