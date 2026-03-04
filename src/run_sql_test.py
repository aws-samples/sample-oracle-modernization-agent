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

from agents.sql_test.tools.test_tools import run_bulk_test, get_test_failures
from agents.sql_test.agent import create_sql_test_agent

_log_dir = LOGS_DIR / "test"


def create_agent():
    agent = create_sql_test_agent()
    agent.callback_handler = None
    return agent


def fix_mapper_failures(mapper_file: str, failures: list, progress_counter: dict, total: int) -> dict:
    """Agent fixes failed SQL IDs for a single mapper."""
    _log_dir.mkdir(parents=True, exist_ok=True)
    log_path = _log_dir / f"{Path(mapper_file).stem}.log"
    log_path.write_text('', encoding='utf-8')

    # Progress log for console display
    progress_log = _log_dir.parent / "test_progress.log"
    reported = set()

    def log(msg):
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

    def console(sql_id, status):
        key = f"{sql_id}:{status}"
        if key in reported:
            return
        reported.add(key)

        with progress_counter['lock']:
            if status == "🔧 수정중":
                progress_counter['started'] += 1
            elif status in ["✅ PASS"]:
                progress_counter['done'] += 1
            current = progress_counter['started']
            pct = int(current * 100 / total) if total > 0 else 0
            msg = f"[{pct:3d}%] [{Path(mapper_file).stem}] {sql_id} - {status}"
            with open(progress_log, 'a', encoding='utf-8') as f:
                f.write(f"{msg}\n")

    try:
        ids_str = ", ".join(f['sql_id'] for f in failures)
        log(f"🔧 시작: {len(failures)} failures")
        log(f"   SQL IDs: {ids_str}")

        # Filter out DB connection errors
        sql_errors = [f for f in failures if 'Network Adapter could not establish' not in f.get('error', '')]
        connection_errors = [f for f in failures if 'Network Adapter could not establish' in f.get('error', '')]

        if connection_errors:
            log(f"⚠️  {len(connection_errors)} DB 연결 오류 (인프라 문제, 스킵)")
            for f in connection_errors:
                console(f['sql_id'], "⚠️  DB 연결 오류")

        if not sql_errors:
            log("✅ SQL 구문 오류 없음 (모두 DB 연결 오류)")
            return {'mapper': mapper_file, 'status': 'skipped', 'count': 0}

        for f in sql_errors:
            console(f['sql_id'], "🔧 수정중")

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

        # Read completion events from thread-safe queue
        for event in drain_progress():
            sig_sql_id = event["sql_id"]
            for f in sql_errors:
                if f['sql_id'] == sig_sql_id:
                    console(f['sql_id'], "✅ PASS")
                    break

        log(f"✅ {mapper_file} 수정 완료")
        return {'mapper': mapper_file, 'status': 'success'}
    except Exception as e:
        log(f"❌ {mapper_file}: {e}")
        return {'mapper': mapper_file, 'status': 'error', 'error': str(e)}


def run(max_workers=8):
    print("🧪 SQL Test 시작...\n", flush=True)

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

    # Phase 1: Java bulk test
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

        log_and_print(f"\n{'='*60}")
        log_and_print(f"📊 결과: {tested}/{total_sql} SQL IDs tested (select+DML)")
        log_and_print(f"✅ 전체 테스트 완료!")
        log_and_print(f"📁 Log: {test_log_file}")
        log_and_print(f"{'='*60}")
        return

    # Phase 2: Agent fixes failures
    log_and_print(f"\nPhase 2: {len(failures)}건 실패 SQL 수정 (Agent)...\n")

    mapper_failures = {}
    for f in failures:
        mapper = f['mapper_file']
        if mapper not in mapper_failures:
            mapper_failures[mapper] = []
        mapper_failures[mapper].append(f)

    # Initialize progress log
    progress_log = _log_dir.parent / "test_progress.log"
    progress_log.write_text('', encoding='utf-8')

    original_stderr = sys.stderr
    def tail_progress_log(progress_log_path: Path, stop_event: threading.Event, stderr):
        last_pos = 0
        while not stop_event.is_set():
            if progress_log_path.exists():
                with open(progress_log_path, 'r', encoding='utf-8') as fh:
                    fh.seek(last_pos)
                    new_lines = fh.read()
                    if new_lines:
                        stderr.write(new_lines)
                        stderr.flush()
                    last_pos = fh.tell()
            stop_event.wait(0.1)

    stop_monitor = threading.Event()
    monitor = threading.Thread(target=tail_progress_log, args=(progress_log, stop_monitor, original_stderr), daemon=True)
    monitor.start()

    progress_counter = {'started': 0, 'done': 0, 'lock': threading.Lock()}
    total_failures = len(failures)

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fix_mapper_failures, m, f, progress_counter, total_failures): m for m, f in mapper_failures.items()}
        for future in as_completed(futures):
            results.append(future.result())

    stop_monitor.set()
    monitor.join(timeout=2)

    # Final status
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE tested='Y'")
        tested = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM transform_target_list")
        total_sql = cursor.fetchone()[0]

    log_and_print(f"\n{'='*60}")
    log_and_print(f"📊 결과: {tested}/{total_sql} SQL IDs tested (select+DML)")
    remaining = total_sql - tested
    if remaining > 0:
        log_and_print(f"⚠️  미완료: {remaining}개 SQL IDs")
    else:
        log_and_print(f"✅ 전체 테스트 완료!")

        if _refine_strategy_from_logs():
            _suggest_compaction()

    log_and_print(f"📁 Logs: {_log_dir}/")
    log_and_print(f"📁 Execution log: {test_log_file}")
    log_and_print(f"{'='*60}")


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
            cursor.execute("UPDATE transform_target_list SET tested='N' WHERE sql_type='select'")
            reset_count = cursor.rowcount
            conn.commit()
        print(f"✅ Reset {reset_count} SQL IDs\n", flush=True)

    run(max_workers=args.workers)
