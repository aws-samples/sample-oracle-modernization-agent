"""Run SQL Test - Phase 1: Java bulk test, Phase 2: Agent fixes failures"""
import sys
import sqlite3
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent))

from utils.project_paths import PROJECT_ROOT, DB_PATH, LOGS_DIR, TRANSFORM_DIR, TEST_DIR
from core.progress import drain_progress

from agents.sql_test.tools.test_tools import run_bulk_test, explain_dml_batch
from agents.sql_test.agent import create_sql_test_agent

_log_dir = LOGS_DIR / "test"


def create_agent():
    return create_sql_test_agent(suppress_streaming=True)


def fix_mapper_failures(mapper_file: str, failures: list, progress_counter: dict, total: int) -> dict:
    """Agent fixes failed SQL IDs for a single mapper."""
    _log_dir.mkdir(parents=True, exist_ok=True)
    log_path = _log_dir / f"{Path(mapper_file).stem}.log"
    log_path.write_text('', encoding='utf-8')

    def log(msg):
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

    def advance_progress(count, last_sql_id=""):
        with progress_counter['lock']:
            progress_counter['done'] += count
            progress_obj = progress_counter.get('progress')
            tid = progress_counter.get('task_id')
            if progress_obj and tid is not None:
                desc = f"Test fix: {Path(mapper_file).stem}:{last_sql_id}" if last_sql_id else "Test fix"
                progress_obj.update(tid, advance=count, description=desc)

    try:
        ids_str = ", ".join(f['sql_id'] for f in failures)
        log(f"🔧 시작: {len(failures)} failures")
        log(f"   SQL IDs: {ids_str}")

        # Filter out DB connection errors
        sql_errors = [f for f in failures if 'Network Adapter could not establish' not in f.get('error', '')]
        connection_errors = [f for f in failures if 'Network Adapter could not establish' in f.get('error', '')]

        if connection_errors:
            log(f"⚠️  {len(connection_errors)} DB 연결 오류 (인프라 문제, 스킵)")
            advance_progress(len(connection_errors))

        if not sql_errors:
            log("✅ SQL 구문 오류 없음 (모두 DB 연결 오류)")
            return {'mapper': mapper_file, 'status': 'skipped', 'count': 0}

        errors_str = "\n\n".join(
            f"SQL ID: {f['sql_id']}\n"
            f"Error: {f.get('error', 'unknown')}"
            for f in sql_errors
        )

        # Run agent (callback_handler=None suppresses streaming output)
        agent = create_agent()
        agent(
            f"Fix the following failed SQL IDs in {mapper_file}.\n\n"
            f"=== Failed SQLs and Errors ===\n{errors_str}\n\n"
            f"=== Fix Procedure ===\n"
            f"For each SQL ID:\n"
            f"1. read_sql_source() to get Oracle original\n"
            f"2. read_transform() to get current PostgreSQL SQL\n"
            f"3. Analyze the error against both original and converted SQL, apply General Conversion Rules\n"
            f"4. convert_sql() to save the fix\n"
            f"5. run_single_test() to verify\n"
            f"6. If still fails, try once more. After 2 attempts, skip with MANUAL_REVIEW note.\n"
        )

        # Drain queue and advance by total sql_errors count
        drain_progress()
        advance_progress(len(sql_errors), sql_errors[-1]['sql_id'])

        log(f"✅ {mapper_file} 수정 완료")
        return {'mapper': mapper_file, 'status': 'success'}
    except Exception as e:
        log(f"❌ {mapper_file}: {e}")
        return {'mapper': mapper_file, 'status': 'error', 'error': str(e)}


def run(max_workers=8):
    from core.display import console_err
    console_err.print("[bold]SQL Test Agent[/bold]")

    TRANSFORM_DIR.mkdir(parents=True, exist_ok=True)

    test_log_file = LOGS_DIR / "test_execution.log"
    test_log_file.parent.mkdir(parents=True, exist_ok=True)

    def log_and_print(msg):
        print(msg, flush=True)
        with open(test_log_file, 'a', encoding='utf-8') as f:
            f.write(f"{msg}\n")

    test_log_file.write_text('', encoding='utf-8')
    log_and_print(f"🧪 SQL Test 시작... [{time.strftime('%Y-%m-%d %H:%M:%S')}]")
    log_and_print("")

    # Generate parameters.properties from DB
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM properties WHERE key LIKE 'PG%'")
        pg_props = dict(cursor.fetchall())

    TEST_DIR.mkdir(parents=True, exist_ok=True)

    pg_params_file = PROJECT_ROOT / "src" / "reference" / "pg_connection.properties"
    with open(pg_params_file, 'w', encoding='utf-8') as f:
        f.write(f"# Auto-generated PostgreSQL connection parameters\n")
        f.write(f"PGHOST={pg_props.get('PGHOST', '')}\n")
        f.write(f"PGPORT={pg_props.get('PGPORT', '5432')}\n")
        f.write(f"PGDATABASE={pg_props.get('PGDATABASE', '')}\n")
        f.write(f"PGUSER={pg_props.get('PGUSER', '')}\n")
        f.write(f"PGPASSWORD={pg_props.get('PGPASSWORD', '')}\n")
    log_and_print(f"✅ Generated {pg_params_file}")

    # Pre-check: DB connection available?
    from agents.sql_transform.tools.metadata import _get_pg_connection_vars
    if not _get_pg_connection_vars():
        log_and_print("\n⚠️  No PostgreSQL connection info")
        log_and_print("Test 단계를 수행하려면 DB 접속 정보가 필요합니다.")
        log_and_print("→ run_setup.py를 다시 실행하여 PostgreSQL 접속 정보를 설정하세요.")
        return

    # Phase 0: EXPLAIN-based DML validation (no execution, no PK/NULL issues)
    log_and_print("\nPhase 0: DML 구문 검증 (EXPLAIN)...")
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT mapper_file, sql_id, sql_type, target_file
            FROM transform_target_list
            WHERE validated = 'Y' AND tested = 'N'
              AND sql_type IN ('insert', 'update', 'delete')
            ORDER BY mapper_file, seq_no
        """)
        dml_rows = cursor.fetchall()

    if dml_rows:
        dml_items = [
            {'mapper_file': r[0], 'sql_id': r[1], 'sql_type': r[2], 'target_file': r[3]}
            for r in dml_rows
        ]
        log_and_print(f"  📋 DML 대상: {len(dml_items)}개 (INSERT/UPDATE/DELETE)")
        explain_result = explain_dml_batch(dml_items)

        if explain_result.get('status') == 'completed':
            log_and_print(f"  ✅ EXPLAIN PASS: {explain_result['passed']}")
            log_and_print(f"  ❌ EXPLAIN FAIL: {explain_result['failed']}")
            for f in explain_result.get('failures', [])[:5]:
                log_and_print(f"    ❌ {f['mapper_file']}/{f['sql_id']}: {f['error'][:100]}")
            if explain_result['failed'] > 5:
                log_and_print(f"    ... and {explain_result['failed'] - 5} more")
        elif explain_result.get('status') == 'skipped':
            log_and_print(f"  ⚠️  DML EXPLAIN skipped: {explain_result.get('error', '')}")
    else:
        log_and_print("  ℹ️  DML 대상 없음")

    # Phase 1: Java bulk test (SELECT + remaining untested)
    log_and_print("\nPhase 1: Java 일괄 테스트 실행...")
    bulk_result = run_bulk_test()

    if bulk_result.get('status') == 'skipped':
        log_and_print(f"⚠️  {bulk_result['error']}")
        log_and_print("PostgreSQL 접속 정보를 설정하세요 (env vars 또는 Parameter Store)")
        return

    if bulk_result.get('status') == 'error':
        log_and_print(f"❌ Bulk test error: {bulk_result['error']}")
        return

    passed = bulk_result.get('passed', 0)
    failed = bulk_result.get('failed', 0)
    failures = bulk_result.get('failures', [])
    log_and_print(f"  ✅ Passed: {passed}")
    log_and_print(f"  ❌ Failed: {failed}")

    if not failures:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE tested='Y'")
            tested = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM transform_target_list")
            total_sql = cursor.fetchone()[0]

        from core.display import print_step_result
        print_step_result("Test Result", [
            ("Tested", f"{tested}/{total_sql} SQL IDs"),
            ("Status", "[green]All tests passed[/green]"),
            ("Log", str(test_log_file)),
        ])
        return

    # Phase 2: Agent fixes failures
    log_and_print(f"\nPhase 2: {len(failures)}건 실패 SQL 수정 (Agent)...\n")

    mapper_failures = {}
    for f in failures:
        mapper = f['mapper_file']
        if mapper not in mapper_failures:
            mapper_failures[mapper] = []
        mapper_failures[mapper].append(f)

    from core.display import create_step_progress

    results = []
    with create_step_progress() as progress:
        task_id = progress.add_task("Test Fix", total=len(failures))
        progress_counter = {
            'started': 0, 'done': 0, 'lock': threading.Lock(),
            'progress': progress, 'task_id': task_id,
        }

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fix_mapper_failures, m, f, progress_counter, len(failures)): m for m, f in mapper_failures.items()}
            for future in as_completed(futures):
                results.append(future.result())

    # Final status
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE tested='Y'")
        tested = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM transform_target_list")
        total_sql = cursor.fetchone()[0]

    from core.display import print_step_result

    rows = [("Tested", f"{tested}/{total_sql} SQL IDs")]
    remaining = total_sql - tested
    if remaining > 0:
        rows.append(("Remaining", f"[yellow]{remaining} SQL IDs[/yellow]"))
    else:
        rows.append(("Status", "[green]All tests passed[/green]"))
        if _refine_strategy_from_logs():
            _suggest_compaction()

    rows.append(("Logs", str(_log_dir)))
    rows.append(("Execution log", str(test_log_file)))
    print_step_result("Test Result", rows)


def _refine_strategy_from_logs():
    print(f"📝 전략 보강 중...", flush=True)
    try:
        from agents.strategy_refine.agent import create_strategy_refine_agent
        agent = create_strategy_refine_agent()
        agent("Refine: collect feedback patterns and add as Before/After examples to strategy.")
        print(f"✅ 전략 보강 완료", flush=True)
        return True
    except Exception as e:
        print(f"⚠️ 전략 보강 실패: {e}", flush=True)
        return False


def _suggest_compaction():
    strategy_file = PROJECT_ROOT / "output" / "strategy" / "transform_strategy.md"
    if not strategy_file.exists():
        return

    file_size = strategy_file.stat().st_size
    learning_count = strategy_file.read_text(encoding='utf-8').count('### ')

    if file_size > 50000 or learning_count > 10:
        print(f"\n🗜️ 전략 압축 시작 (크기: {file_size//1024}KB, 패턴: {learning_count}개)...", flush=True)
        try:
            from agents.strategy_refine.agent import create_strategy_refine_agent
            agent = create_strategy_refine_agent()
            agent("Compact: read strategy, remove duplicates and patterns covered by General Rules, merge similar patterns, rewrite.")
            new_size = strategy_file.stat().st_size
            print(f"✅ 압축 완료: {file_size//1024}KB → {new_size//1024}KB", flush=True)
        except Exception as e:
            print(f"⚠️ 압축 실패: {e}", flush=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--reset', action='store_true', help='Reset all tested flags before running')
    args = parser.parse_args()

    if args.reset:
        print("🔄 Resetting test flags...", flush=True)
        with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE transform_target_list SET tested='N' WHERE tested='Y'")
            reset_count = cursor.rowcount
            conn.commit()
        print(f"✅ Reset {reset_count} SQL IDs (SELECT + DML)\n", flush=True)

    run(max_workers=args.workers)
