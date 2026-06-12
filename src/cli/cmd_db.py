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
