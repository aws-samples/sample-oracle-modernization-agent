"""oma test-exec — deterministic DB test: Phase 0 EXPLAIN / Phase 1 Execute / Phase 1.5 Compare.

Phase 2 (Agent fix) is NOT included here — that's the CC test-fixer subagent's job.
"""
import json
import os
import sqlite3
import sys
import time
from pathlib import Path


def register(sub):
    p = sub.add_parser("test-exec",
                       help="Run DB tests: Phase 0 EXPLAIN / 1 Execute / 1.5 Compare")
    p.add_argument("--phase", choices=["0", "1", "1.5", "all"], default="all",
                   help="Which phases to run (0=EXPLAIN, 1=EXPLAIN+Execute, 1.5/all=full)")
    p.add_argument("--only", default="",
                   help="Comma list of mapper:sql_id pairs to retest")
    p.add_argument("--json", action="store_true", dest="as_json",
                   help="Output JSON summary to stdout")
    p.set_defaults(func=run)


def _classify_error(error_msg: str) -> str:
    """Classify error message into a FAIL category."""
    if not error_msg:
        return 'unknown'
    e = error_msg.lower()

    if any(p in e for p in ['invalid input syntax', 'operator does not exist',
                             'type mismatch', 'cannot cast']):
        return 'parameter'
    if any(p in e for p in ['syntax error', 'unexpected token', 'near "',
                             'missing keyword']):
        return 'sql_syntax'
    if any(p in e for p in ['relation "', 'does not exist', 'column "',
                             'table "', 'unknown column']):
        return 'schema'
    if any(p in e for p in ['classnotfound', 'connection refused', 'timeout',
                             'could not connect', 'java.lang.']):
        return 'infra'
    return 'other'


def _pre_mark_skips(db_path: Path, log_fn) -> int:
    """Pre-mark non-testable SQL IDs (sql fragments, resultMap) as SKIP."""
    total_marked = 0
    with sqlite3.connect(str(db_path), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, sql_type FROM transform_target_list
            WHERE tested = 'N'
              AND LOWER(sql_type) NOT IN ('select', 'insert', 'update', 'delete')
        """)
        for record_id, sql_type in cursor.fetchall():
            reason = ('SQL fragment — 단독 실행 불가' if sql_type == 'sql'
                      else f'{sql_type} — 매핑 정의, SQL 아님')
            cursor.execute(
                "UPDATE transform_target_list SET tested='Y', test_result='SKIP', test_notes=? WHERE id=?",
                (reason, record_id)
            )
            total_marked += 1
        conn.commit()

    if total_marked > 0:
        log_fn(f"pre-skip: {total_marked} non-testable types")
    return total_marked


def _generate_failure_report(db_path: Path) -> str | None:
    """Generate a test failure report file. Returns path or None."""
    try:
        from utils.project_paths import OUTPUT_DIR
        report_dir = OUTPUT_DIR / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "test_failure_report.md"

        with sqlite3.connect(str(db_path), timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT mapper_file, sql_id, test_result, test_notes
                FROM transform_target_list
                WHERE tested='Y' AND test_result NOT IN ('PASS', 'FIXED', 'SKIP')
                ORDER BY mapper_file, sql_id
            """)
            failures = cursor.fetchall()

        if not failures:
            return None

        lines = ["# Test Failure Report\n"]
        lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        lines.append(f"Total failures: {len(failures)}\n")
        lines.append("| Mapper | SQL ID | Result | Error |\n|---|---|---|---|\n")
        for mapper, sql_id, result, notes in failures:
            note_short = (notes or '')[:100].replace('|', '\\|').replace('\n', ' ')
            lines.append(f"| {mapper} | {sql_id} | {result} | {note_short} |\n")

        report_path.write_text(''.join(lines), encoding='utf-8')
        return str(report_path)
    except Exception:
        return None


def run(args) -> int:
    from utils.project_paths import DB_PATH, OUTPUT_DIR
    from utils.db_utils import update_by_mapper
    from core.db_migrate import ensure_schema
    from core.db_conn import get_pg_connection_vars, get_mysql_connection_vars, get_oracle_connection_vars
    from core.sql_executor import SQLExecutor, check_cli_available
    from core.tc_generator import TCGenerator

    def log(msg):
        print(msg, file=sys.stderr, flush=True)

    # Ensure schema
    ensure_schema()

    if not DB_PATH.exists():
        print("DB not found — run 'oma analyze' first", file=sys.stderr)
        return 1

    # Determine target DBMS
    from utils.project_paths import get_target_dbms, get_target_db_display_name
    dbms = get_target_dbms()
    display_name = get_target_db_display_name(dbms)

    # Load target DB connection vars
    conn_vars = get_mysql_connection_vars() if dbms == 'mysql' else get_pg_connection_vars()
    if not conn_vars:
        print(f"No {display_name} connection info — "
              f"run setup to configure DB credentials", file=sys.stderr)
        return 1
    os.environ.update(conn_vars)

    # Load Oracle connection (optional — for TC gen + Compare)
    oracle_vars = get_oracle_connection_vars()
    if oracle_vars:
        os.environ.update(oracle_vars)
        log(f"Oracle connection loaded (TC gen + Compare enabled)")

    # Check CLI availability
    ok, cli_msg = check_cli_available()
    if not ok:
        print(f"CLI not available: {cli_msg}", file=sys.stderr)
        return 1
    log(f"CLI: {cli_msg}")

    # Pre-skip non-testable types
    _pre_mark_skips(DB_PATH, log)

    # Parse --only filter
    only_set = set()
    if args.only:
        for pair in args.only.split(","):
            pair = pair.strip()
            if ":" in pair:
                only_set.add(tuple(pair.split(":", 1)))

    # Gather testable items
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT mapper_file, sql_id, sql_type, target_file
            FROM transform_target_list
            WHERE validated = 'Y' AND tested = 'N'
              AND LOWER(sql_type) IN ('select', 'insert', 'update', 'delete')
            ORDER BY mapper_file, seq_no
        """)
        all_rows = cursor.fetchall()

    all_items = [
        {'mapper_file': r[0], 'sql_id': r[1], 'sql_type': r[2], 'target_file': r[3]}
        for r in all_rows
    ]

    # Apply --only filter
    if only_set:
        all_items = [it for it in all_items
                     if (it['mapper_file'], it['sql_id']) in only_set]

    if not all_items:
        log("No testable items")
        if args.as_json:
            print(json.dumps({"phase0": {"pass": 0, "fail": 0},
                              "phase1": {"pass": 0, "fail": 0},
                              "phase15": {"pass": 0, "fail": 0, "skip": 0},
                              "failures": []}))
        return 0

    log(f"Testable: {len(all_items)} SQL IDs")

    # TC Generation
    tc_path = OUTPUT_DIR / "test" / "test_cases.json"
    existing_tcs = TCGenerator.load_tc_json(tc_path)

    if existing_tcs:
        tc_map_raw = existing_tcs
        log(f"TC loaded: {sum(len(v) for v in existing_tcs.values())} cases")
    else:
        log("Generating TCs...")
        tc_gen = TCGenerator()
        tc_map_obj = tc_gen.generate_batch(all_items)
        tc_gen.save_tc_json(tc_map_obj)
        tc_total = sum(len(v) for v in tc_map_obj.values())
        log(f"TC generated: {tc_total} cases")
        tc_map_raw = {k: [{'params': tc.params} for tc in v] for k, v in tc_map_obj.items()}

    # Attach first TC params to items
    for item in all_items:
        key = f"{item['mapper_file']}/{item['sql_id']}"
        tcs = tc_map_raw.get(key, [])
        if tcs:
            params = tcs[0].get('params') if isinstance(tcs[0], dict) else tcs[0].params
            item['params'] = params

    # --- Phase 0: EXPLAIN ---
    executor = SQLExecutor()
    log("Phase 0: EXPLAIN...")
    explain_results = executor.explain_batch(all_items)

    phase0_pass = 0
    phase0_fail = 0
    explain_failures = []

    for item, res in zip(all_items, explain_results):
        if res.status == 'PASS':
            phase0_pass += 1
            # Mark PASS in DB
            _update_tested(DB_PATH, item['mapper_file'], item['sql_id'], 'PASS')
        else:
            phase0_fail += 1
            _update_tested(DB_PATH, item['mapper_file'], item['sql_id'], 'FAIL', res.error)
            explain_failures.append({
                'mapper_file': item['mapper_file'],
                'sql_id': item['sql_id'],
                'phase': '0',
                'error': res.error,
            })

    log(f"  EXPLAIN PASS={phase0_pass} FAIL={phase0_fail}")

    # If --phase 0, stop here
    phase_arg = args.phase
    all_failures = list(explain_failures)

    if phase_arg == "0":
        result = _build_result(phase0_pass, phase0_fail, 0, 0, 0, 0, 0, all_failures)
        _output(result, args.as_json, log)
        _try_report(DB_PATH)
        return 0

    # --- Phase 1: Execute (SELECT only, EXPLAIN-passed) ---
    fail_set = {(f['mapper_file'], f['sql_id']) for f in explain_failures}
    execute_items = [
        item for item in all_items
        if (item['mapper_file'], item['sql_id']) not in fail_set
        and item.get('sql_type', '').lower() == 'select'
    ]

    # DML items that passed EXPLAIN are done (mark PASS already happened)
    dml_passed = [
        item for item in all_items
        if (item['mapper_file'], item['sql_id']) not in fail_set
        and item.get('sql_type', '').lower() in ('insert', 'update', 'delete')
    ]
    if dml_passed:
        log(f"  DML {len(dml_passed)} passed via EXPLAIN (execute skipped)")

    phase1_pass = 0
    phase1_fail = 0

    if execute_items:
        # Reset tested flag for execute phase (EXPLAIN already marked PASS)
        with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
            for item in execute_items:
                update_by_mapper(conn,
                    "UPDATE transform_target_list SET tested='N', test_result=NULL WHERE mapper_file=? AND sql_id=?",
                    item['mapper_file'], item['sql_id'])
            conn.commit()

        log(f"Phase 1: Execute ({len(execute_items)} SELECTs)...")
        exec_results = executor.execute_batch(execute_items)

        for item, res in zip(execute_items, exec_results):
            if res.status == 'PASS':
                phase1_pass += 1
                _update_tested(DB_PATH, item['mapper_file'], item['sql_id'], 'PASS')
            else:
                phase1_fail += 1
                _update_tested(DB_PATH, item['mapper_file'], item['sql_id'], 'FAIL', res.error)
                all_failures.append({
                    'mapper_file': item['mapper_file'],
                    'sql_id': item['sql_id'],
                    'phase': '1',
                    'error': res.error,
                })
        log(f"  Execute PASS={phase1_pass} FAIL={phase1_fail}")
    else:
        log("  No SELECTs passed EXPLAIN — execute skipped")

    # If --phase 1, stop here
    if phase_arg == "1":
        result = _build_result(phase0_pass, phase0_fail, phase1_pass, phase1_fail,
                               0, 0, 0, all_failures)
        _output(result, args.as_json, log)
        _try_report(DB_PATH)
        return 0

    # --- Phase 1.5: Oracle-Target Compare ---
    from core.result_comparator import ResultComparator
    comparator = ResultComparator()

    phase15_pass = 0
    phase15_fail = 0
    phase15_skip = 0

    if comparator.oracle_available:
        # Compare items that passed execute
        exec_fail_set = {(f['mapper_file'], f['sql_id']) for f in all_failures if f['phase'] == '1'}
        compare_items = [item for item in execute_items
                         if (item['mapper_file'], item['sql_id']) not in exec_fail_set]

        if compare_items:
            log(f"Phase 1.5: Oracle-Target Compare ({len(compare_items)})...")
            compare_results = comparator.compare_batch(compare_items)

            for r in compare_results:
                if r.status == 'PASS':
                    phase15_pass += 1
                elif r.status.startswith('FAIL'):
                    phase15_fail += 1
                    all_failures.append({
                        'mapper_file': r.mapper_file,
                        'sql_id': r.sql_id,
                        'phase': '1.5',
                        'error': r.error,
                    })
                else:
                    phase15_skip += 1

            log(f"  Compare PASS={phase15_pass} FAIL={phase15_fail} SKIP={phase15_skip}")
        else:
            log("  No items for compare")
    else:
        log("  Oracle not available — compare skipped")
        phase15_skip = -1  # signal: not run

    result = _build_result(phase0_pass, phase0_fail, phase1_pass, phase1_fail,
                           phase15_pass, phase15_fail, phase15_skip, all_failures)
    _output(result, args.as_json, log)
    _try_report(DB_PATH)

    # Generate HTML report (non-fatal)
    try:
        from core.html_report import generate_html_report
        generate_html_report()
    except Exception:
        pass

    return 0


def _update_tested(db_path: Path, mapper_file: str, sql_id: str,
                   result: str = "PASS", error: str = ""):
    """Update test result in DB."""
    from utils.db_utils import update_by_mapper
    with sqlite3.connect(str(db_path), timeout=10) as conn:
        test_notes = error[:500] if result != "PASS" and error else ""
        next_step = 'completed' if result == 'PASS' else 'test'
        update_by_mapper(conn,
            "UPDATE transform_target_list SET tested='Y', test_result=?, test_notes=?, "
            "current_step=?, updated_at=CURRENT_TIMESTAMP WHERE mapper_file=? AND sql_id=?",
            mapper_file, sql_id, extra_params=(result, test_notes, next_step))
        conn.commit()


def _build_result(p0_pass, p0_fail, p1_pass, p1_fail,
                  p15_pass, p15_fail, p15_skip, failures):
    """Build the JSON-serializable result dict."""
    r = {
        "phase0": {"pass": p0_pass, "fail": p0_fail},
        "phase1": {"pass": p1_pass, "fail": p1_fail},
        "phase15": {"pass": p15_pass, "fail": p15_fail, "skip": p15_skip},
        "failures": failures,
    }
    return r


def _output(result: dict, as_json: bool, log_fn):
    """Output result to stdout (JSON) or stderr (human)."""
    if as_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        # DML items only go through Phase 0; SELECT items go 0→1→1.5.
        # Count DML PASS (phase0 only) + SELECT final pass (phase1 or phase15).
        dml_pass = result['phase0']['pass'] - result['phase1']['pass'] - result['phase1']['fail']
        select_pass = result['phase1']['pass'] + result['phase15']['pass']
        total_pass = max(dml_pass, 0) + select_pass
        total_fail = len(result['failures'])
        log_fn(f"\nResult: pass={total_pass} fail={total_fail}")
        if result['failures']:
            for f in result['failures'][:10]:
                log_fn(f"  FAIL {f['mapper_file']}:{f['sql_id']} (phase {f['phase']}): "
                       f"{f['error'][:80]}")
            if len(result['failures']) > 10:
                log_fn(f"  ... and {len(result['failures']) - 10} more")


def _try_report(db_path: Path):
    """Try to generate failure report (non-fatal)."""
    try:
        path = _generate_failure_report(db_path)
        if path:
            print(f"report: {path}", file=sys.stderr, flush=True)
    except Exception:
        pass
