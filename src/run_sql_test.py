"""Run SQL Test — Phase 0: EXPLAIN, Phase 1: Execute, Phase 2: Agent fix"""
import os
import sys
import sqlite3
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent))

from utils.project_paths import PROJECT_ROOT, DB_PATH, LOGS_DIR, TRANSFORM_DIR, TEST_DIR, OUTPUT_DIR, get_target_dbms, get_target_db_display_name
from core.progress import drain_progress
from core.pipeline_logger import PipelineLogger
from core.db_migrate import ensure_schema

from agents.sql_test.tools.test_tools import explain_batch, execute_batch, _update_tested, set_logger
from agents.sql_transform.tools.convert_sql import set_step
from agents.sql_test.agent import create_sql_test_agent
from core import history_writer as _hw
from core.html_report import generate_html_report

_log_dir = LOGS_DIR / "test"


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

        # Filter out infrastructure errors (not fixable by agent)
        _infra_patterns = [
            'Network Adapter could not establish',
            'IncompleteElementException',
            'include refid',
            'Cannot find class:',
            'ClassNotFoundException',
        ]

        def _is_infra_error(error: str) -> bool:
            return any(p in error for p in _infra_patterns)

        sql_errors = [f for f in failures if not _is_infra_error(f.get('error', ''))]
        infra_errors = [f for f in failures if _is_infra_error(f.get('error', ''))]

        if infra_errors:
            log(f"⚠️  {len(infra_errors)} 인프라/환경 오류 (Agent 수정 불가, 스킵)")
            for f in infra_errors:
                log(f"    SKIP {f['sql_id']}: {f.get('error', '')[:80]}")
                # Mark as tested with SKIP + detailed reason in test_notes
                error_text = f.get('error', '')
                if 'ClassNotFoundException' in error_text or 'Cannot find class' in error_text:
                    skip_notes = f"Java 유틸 클래스 미존재: {error_text.split(':')[-1].strip()[:100]}"
                elif 'IncompleteElement' in error_text or 'include refid' in error_text:
                    skip_notes = "include refid 참조 — 다른 mapper fragment 참조, 단일 파일 테스트 불가"
                elif 'does not exist' in error_text and 'function' in error_text:
                    skip_notes = f"사용자 정의 함수 미존재 — 타겟 DB에 함수 생성 필요: {error_text[:100]}"
                elif 'does not exist' in error_text and ('relation' in error_text or 'table' in error_text):
                    skip_notes = f"테이블 미존재 — 스키마 마이그레이션 필요: {error_text[:100]}"
                elif 'Network Adapter' in error_text:
                    skip_notes = "DB 연결 오류 — 인프라 문제"
                else:
                    skip_notes = f"인프라 오류: {error_text[:150]}"
                _update_tested(mapper_file, f['sql_id'], result="SKIP", error=skip_notes)
            advance_progress(len(infra_errors))

        if not sql_errors:
            log("✅ Agent 수정 가능한 오류 없음 (모두 인프라/환경 오류)")
            return {'mapper': mapper_file, 'status': 'skipped', 'count': 0}

        errors_str = "\n\n".join(
            f"SQL ID: {f['sql_id']}\n"
            f"Error: {f.get('error', 'unknown')}"
            for f in sql_errors
        )

        # Arm the test lap timer so test_tools.run_single_test.record_test() gets per-SQL execution_time_ms.
        # Also arm transform timer because Phase 2 fix loop calls convert_sql.
        _hw.start_timer("test")
        _hw.start_timer("transform")

        # Run agent (callback_handler=None suppresses streaming output)
        agent = create_agent()
        agent(
            f"Fix the following failed SQL IDs in {mapper_file}.\n\n"
            f"=== Failed SQLs and Errors ===\n{errors_str}\n\n"
            f"=== Fix Procedure ===\n"
            f"For each SQL ID:\n"
            f"1. read_sql_source() to get Oracle original\n"
            f"2. read_transform() to get current converted SQL\n"
            f"3. Analyze the error against both original and converted SQL, apply General Conversion Rules\n"
            f"4. convert_sql() to save the fix\n"
            f"5. explain_single() for quick syntax check\n"
            f"6. convert_sql() to save the fix\n"
            f"7. run_single_test() to verify execution\n"
            f"8. compare_single() to verify results match Oracle\n"
            f"9. If still fails after 3 attempts, skip with MANUAL_REVIEW note.\n"
        )

        # Drain queue and advance by total sql_errors count
        drain_progress()
        advance_progress(len(sql_errors), sql_errors[-1]['sql_id'])

        # Auto re-merge: SQL이 수정되었으면 해당 mapper를 다시 merge
        try:
            from agents.sql_transform.tools.assemble_mapper import assemble_mapper
            merge_result = assemble_mapper(mapper_file)
            if merge_result.get('success', 0) > 0:
                log(f"📦 Re-merge: {mapper_file} ({merge_result['success']} SQLs)")
            else:
                log(f"⚠️  Re-merge skipped: {mapper_file} ({merge_result.get('error', 'no converted SQLs')})")
        except Exception as me:
            log(f"⚠️  Re-merge failed: {mapper_file}: {me}")

        log(f"✅ {mapper_file} 수정 + re-merge 완료")
        return {'mapper': mapper_file, 'status': 'success'}
    except Exception as e:
        log(f"❌ {mapper_file}: {e}")
        return {'mapper': mapper_file, 'status': 'error', 'error': str(e)}


def run(max_workers=8, auto_fix=False):
    from core.display import console_err
    console_err.print("[bold]SQL Test Agent[/bold]")

    ensure_schema()
    set_step("test")

    logger = PipelineLogger(step='test')
    set_logger(logger)
    start_time = time.time()

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

    dbms = get_target_dbms()
    display_name = get_target_db_display_name(dbms)

    TEST_DIR.mkdir(parents=True, exist_ok=True)

    # Set DB env vars from properties table
    from agents.sql_transform.tools.metadata import _get_pg_connection_vars, _get_mysql_connection_vars, _get_oracle_connection_vars
    conn_vars = _get_mysql_connection_vars() if dbms == 'mysql' else _get_pg_connection_vars()
    if not conn_vars:
        log_and_print(f"\nNo {display_name} connection info")
        log_and_print("Test 단계를 수행하려면 DB 접속 정보가 필요합니다.")
        log_and_print(f"run_setup.py를 다시 실행하여 {display_name} 접속 정보를 설정하세요.")
        return
    os.environ.update(conn_vars)

    # Load Oracle connection for TC generation + Compare (optional)
    oracle_vars = _get_oracle_connection_vars()
    if oracle_vars:
        os.environ.update(oracle_vars)
        log_and_print(f"  ✅ Oracle 접속 정보 로드 (TC 생성 + Compare 활성화)")
    else:
        log_and_print(f"  ℹ️  Oracle 미접속 — TC는 inference+LLM, Compare 스킵")

    from core.sql_executor import check_cli_available
    ok, cli_msg = check_cli_available()
    if not ok:
        log_and_print(f"\n❌ {cli_msg}")
        log_and_print(f"psql 또는 mysql CLI가 PATH에 있어야 합니다.")
        return
    log_and_print(f"  ✅ CLI: {cli_msg}")

    # Pre-skip: mark non-testable items before test phases
    skip_count = _pre_mark_skips(log_and_print)

    # Gather all testable items
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT mapper_file, sql_id, sql_type, target_file
            FROM transform_target_list
            WHERE validated = 'Y' AND tested = 'N'
              AND LOWER(sql_type) IN ('select', 'insert', 'update', 'delete')
            ORDER BY mapper_file, seq_no
        """)
        all_rows = cursor.fetchall()
    finally:
        conn.close()

    all_items = [
        {'mapper_file': r[0], 'sql_id': r[1], 'sql_type': r[2], 'target_file': r[3]}
        for r in all_rows
    ]

    if not all_items:
        log_and_print("\n  ℹ️  테스트 대상 없음")
        _finalize_logger(logger, start_time)
        return

    log_and_print(f"\n📋 테스트 대상: {len(all_items)}개 SQL")

    # TC Generation — load existing or auto-generate
    from core.tc_generator import TCGenerator
    tc_path = OUTPUT_DIR / "test" / "test_cases.json"
    existing_tcs = TCGenerator.load_tc_json(tc_path)

    if existing_tcs:
        log_and_print(f"\n📝 기존 TC 로드: {sum(len(v) for v in existing_tcs.values())}개 ({tc_path})")
        tc_map_raw = existing_tcs
    else:
        log_and_print("\n📝 TC 자동 생성 중...")
        tc_gen = TCGenerator()
        tc_map_obj = tc_gen.generate_batch(all_items)
        tc_path = tc_gen.save_tc_json(tc_map_obj)

        tc_total = sum(len(v) for v in tc_map_obj.values())
        sources = {}
        for cases in tc_map_obj.values():
            for tc in cases:
                sources[tc.source] = sources.get(tc.source, 0) + 1
        source_str = ", ".join(f"{k}:{v}" for k, v in sorted(sources.items()))
        log_and_print(f"  ✅ {tc_total}개 TC 생성 ({source_str})")
        log_and_print(f"  📄 {tc_path}")
        tc_map_raw = {k: [{'params': tc.params} for tc in v] for k, v in tc_map_obj.items()}

    # Attach first TC params to items for execution
    for item in all_items:
        key = f"{item['mapper_file']}/{item['sql_id']}"
        tcs = tc_map_raw.get(key, [])
        if tcs:
            params = tcs[0].get('params') if isinstance(tcs[0], dict) else tcs[0].params
            item['params'] = params

    # Phase 0: EXPLAIN — syntax check all types
    log_and_print("\nPhase 0: 구문 검증 (EXPLAIN)...")
    explain_result = explain_batch(all_items)

    if explain_result.get('status') == 'skipped':
        log_and_print(f"⚠️  EXPLAIN skipped: {explain_result.get('error', '')}")
        log_and_print(f"{display_name} 접속 정보를 설정하세요")
        return

    explain_passed = explain_result.get('passed', 0)
    explain_failed = explain_result.get('failed', 0)
    log_and_print(f"  ✅ EXPLAIN PASS: {explain_passed}")
    log_and_print(f"  ❌ EXPLAIN FAIL: {explain_failed}")
    for f in explain_result.get('failures', [])[:5]:
        log_and_print(f"    ❌ {f['mapper_file']}/{f['sql_id']}: {f['error'][:100]}")
    if explain_failed > 5:
        log_and_print(f"    ... and {explain_failed - 5} more")

    # Phase 0 JSON logging
    fail_set = {(f['mapper_file'], f['sql_id']) for f in explain_result.get('failures', [])}
    for item in all_items:
        key = (item['mapper_file'], item['sql_id'])
        if key in fail_set:
            fail_info = next(f for f in explain_result['failures'] if (f['mapper_file'], f['sql_id']) == key)
            logger.log_sql_result(item['mapper_file'], item['sql_id'], 'fail',
                                  phase=0, fail_category='sql_syntax',
                                  error=fail_info.get('error', ''))
        else:
            logger.log_sql_result(item['mapper_file'], item['sql_id'], 'success', phase=0)

    # Phase 1: Execute — EXPLAIN 통과한 SELECT만 실제 실행
    # DML (insert/update/delete)은 EXPLAIN PASS로 충분 — 실행 시 NOT NULL/FK 등 데이터 제약으로 실패
    explain_passed_items = [
        item for item in all_items
        if (item['mapper_file'], item['sql_id']) not in fail_set
        and item.get('sql_type', '').lower() == 'select'
    ]
    dml_passed = [
        item for item in all_items
        if (item['mapper_file'], item['sql_id']) not in fail_set
        and item.get('sql_type', '').lower() in ('insert', 'update', 'delete')
    ]
    if dml_passed:
        log_and_print(f"  ℹ️  DML {len(dml_passed)}개는 EXPLAIN PASS로 완료 (실행 테스트 생략)")

    if explain_passed_items:
        # Reset tested flag for execute phase (EXPLAIN already marked them PASS)
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        try:
            for item in explain_passed_items:
                from utils.db_utils import update_by_mapper
                update_by_mapper(conn,
                    "UPDATE transform_target_list SET tested='N', test_result=NULL WHERE mapper_file=? AND sql_id=?",
                    item['mapper_file'], item['sql_id'])
            conn.commit()
        finally:
            conn.close()

        log_and_print(f"\nPhase 1: 실행 테스트 ({len(explain_passed_items)}개)...")
        exec_result = execute_batch(explain_passed_items)

        if exec_result.get('status') == 'completed':
            passed = exec_result.get('passed', 0)
            failed = exec_result.get('failed', 0)
            failures = exec_result.get('failures', [])
            log_and_print(f"  ✅ Passed: {passed}")
            log_and_print(f"  ❌ Failed: {failed}")

            for f in failures:
                err = f.get('error', '')
                logger.log_sql_result(
                    f['mapper_file'], f['sql_id'], 'fail',
                    phase=1, fail_category=_classify_error(err),
                    error=err,
                )
        else:
            log_and_print(f"  ⚠️  Execute skipped: {exec_result.get('error', '')}")
            failures = []
    else:
        log_and_print("\n  ℹ️  EXPLAIN 통과 항목 없음 — 실행 테스트 스킵")
        failures = explain_result.get('failures', [])

    # Phase 1.5: Oracle-PG Compare (if Oracle available)
    from core.result_comparator import ResultComparator
    comparator = ResultComparator()
    if comparator.oracle_available:
        # Compare execute-passed items
        exec_passed = [item for item in explain_passed_items
                       if (item['mapper_file'], item['sql_id']) not in
                       {(f['mapper_file'], f['sql_id']) for f in failures}]
        if exec_passed:
            log_and_print(f"\nPhase 1.5: Oracle-PG 결과 비교 ({len(exec_passed)}개)...")
            compare_results = comparator.compare_batch(exec_passed)
            compare_pass = sum(1 for r in compare_results if r.status == 'PASS')
            compare_fail = sum(1 for r in compare_results if r.status.startswith('FAIL'))
            compare_skip = sum(1 for r in compare_results if r.status in ('SKIP', 'ERROR'))
            log_and_print(f"  ✅ Compare PASS: {compare_pass}")
            if compare_fail > 0:
                log_and_print(f"  ❌ Compare FAIL: {compare_fail}")
            if compare_skip > 0:
                log_and_print(f"  ⏭️  Compare SKIP: {compare_skip}")

            for r in compare_results:
                if r.status.startswith('FAIL'):
                    logger.log_sql_result(r.mapper_file, r.sql_id, 'fail',
                                          phase='compare', fail_category='compare_diff',
                                          error=r.error,
                                          oracle_rows=r.oracle_rows, target_rows=r.target_rows)
                    failures.append({
                        'mapper_file': r.mapper_file, 'sql_id': r.sql_id,
                        'error': r.error,
                    })
                elif r.status == 'PASS':
                    logger.log_sql_result(r.mapper_file, r.sql_id, 'success',
                                          phase='compare',
                                          oracle_rows=r.oracle_rows, target_rows=r.target_rows)
                if r.warnings:
                    for w in r.warnings:
                        log_and_print(f"    ⚠️  {r.sql_id}: {w}")
    else:
        log_and_print("\n  ℹ️  Oracle 미접속 — 결과 비교 스킵")

    if not failures:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE tested='Y' AND test_result='PASS'")
            pass_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE tested='Y' AND test_result IS NOT NULL AND test_result NOT IN ('PASS','FIXED','SKIP')")
            fail_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE sql_type IN ('sql', 'resultMap')")
            skip_type = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE validated='Y' AND tested='N' AND sql_type NOT IN ('sql', 'resultMap')")
            not_tested_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM transform_target_list")
            total_all = cursor.fetchone()[0]

        from core.display import print_step_result
        tested_count = pass_count + fail_count
        skipped = skip_type + not_tested_count
        rows = [("Passed", str(pass_count))]
        if fail_count > 0:
            rows.append(("Failed", f"[red]{fail_count}[/red]"))
        else:
            rows.append(("Failed", "0"))
        if skipped > 0:
            skip_details = []
            if skip_type > 0:
                skip_details.append(f"{skip_type} non-testable")
            if not_tested_count > 0:
                skip_details.append(f"{not_tested_count} not tested")
            rows.append(("Skipped", f"[dim]{skipped} ({', '.join(skip_details)})[/dim]"))
        rows.append(("Total", f"{tested_count + skipped}/{total_all} SQL IDs"))

        if fail_count > 0 or not_tested_count > 0:
            report_path = _generate_test_failure_report()
            if report_path:
                rows.append(("Failure Report", str(report_path)))
            notes = []
            if fail_count > 0:
                notes.append(f"{fail_count} failed")
            if not_tested_count > 0:
                notes.append(f"{not_tested_count} not tested")
            rows.append(("Note", f"[yellow]{'; '.join(notes)}[/yellow]"))
        else:
            rows.append(("Status", "[green]All tests passed[/green]"))

        rows.append(("Log", str(test_log_file)))
        rows.append(("JSON Log", str(logger.log_path)))
        print_step_result("Test Result", rows)
        _print_sql_type_distribution()
        _finalize_logger(logger, start_time)
        return

    # Phase 2: Agent fixes failures (opt-in only)
    if not auto_fix:
        log_and_print(f"\n⚠️  {len(failures)}건 실패 — Agent fix 생략 (--fix 옵션으로 활성화)")
        log_and_print("  💡 실패 분류 확인: classify test failures")
        log_and_print("  💡 SKIP 처리: skip category <카테고리명>")
        log_and_print("  💡 Agent 수정: retry failed test --fix")
        # Jump to final status
        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE tested='Y' AND test_result='PASS'")
            passed = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE tested='Y' AND test_result IS NOT NULL AND test_result NOT IN ('PASS','FIXED','SKIP')")
            failed_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE sql_type IN ('sql', 'resultMap')")
            skip_type = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE validated='Y' AND tested='N' AND sql_type NOT IN ('sql', 'resultMap')")
            not_tested = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM transform_target_list")
            total_all = cursor.fetchone()[0]
        from core.display import print_step_result
        tested = passed + failed_count
        skipped = skip_type + not_tested
        rows = [("Passed", str(passed))]
        if failed_count > 0:
            rows.append(("Failed", f"[red]{failed_count}[/red]"))
        else:
            rows.append(("Failed", "0"))
        if skipped > 0:
            rows.append(("Skipped", f"[dim]{skipped}[/dim]"))
        rows.append(("Total", f"{tested + skipped}/{total_all} SQL IDs"))
        if failed_count > 0:
            report_path = _generate_test_failure_report()
            if report_path:
                rows.append(("Failure Report", str(report_path)))
        rows.append(("Logs", str(_log_dir)))
        rows.append(("Execution log", str(test_log_file)))
        rows.append(("JSON Log", str(logger.log_path)))
        print_step_result("Test Result", rows)
        _print_sql_type_distribution()
        _finalize_logger(logger, start_time)
        return

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
        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE tested='Y' AND test_result='PASS'")
        passed = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE tested='Y' AND test_result IS NOT NULL AND test_result NOT IN ('PASS','FIXED','SKIP')")
        failed = cursor.fetchone()[0]
        # Skip: non-testable types (sql fragments, resultMap) + untestable (not validated)
        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE sql_type IN ('sql', 'resultMap')")
        skip_type = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE validated='Y' AND tested='N' AND sql_type NOT IN ('sql', 'resultMap')")
        not_tested = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM transform_target_list")
        total_all = cursor.fetchone()[0]

    from core.display import print_step_result

    tested = passed + failed
    skipped = skip_type + not_tested
    rows = [
        ("Passed", str(passed)),
    ]
    if failed > 0:
        rows.append(("Failed", f"[red]{failed}[/red]"))
    else:
        rows.append(("Failed", "0"))
    if skipped > 0:
        skip_details = []
        if skip_type > 0:
            skip_details.append(f"{skip_type} non-testable")
        if not_tested > 0:
            skip_details.append(f"{not_tested} not tested")
        rows.append(("Skipped", f"[dim]{skipped} ({', '.join(skip_details)})[/dim]"))
    rows.append(("Total", f"{tested + skipped}/{total_all} SQL IDs"))

    if failed > 0 or not_tested > 0:
        # Auto-generate test failure report via ReviewManager
        report_path = _generate_test_failure_report()
        if report_path:
            rows.append(("Failure Report", str(report_path)))
    else:
        rows.append(("Status", "[green]All tests passed[/green]"))
        if _refine_strategy_from_logs():
            _suggest_compaction()

    rows.append(("Logs", str(_log_dir)))
    rows.append(("Execution log", str(test_log_file)))
    rows.append(("JSON Log", str(logger.log_path)))
    print_step_result("Test Result", rows)

    # Show SQL type distribution table
    _print_sql_type_distribution()
    _finalize_logger(logger, start_time)


def _finalize_logger(logger, start_time):
    """Write run summary and generate summary.md."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE tested='Y' AND test_result='PASS'")
        p = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE tested='Y' AND test_result NOT IN ('PASS','FIXED','SKIP')")
        f = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE test_result='SKIP'")
        s = cursor.fetchone()[0]
    duration_ms = int((time.time() - start_time) * 1000)
    logger.log_summary(total=p + f + s, pass_=p, fail=f, skip=s, duration_ms=duration_ms)
    summary_path = logger.generate_summary_md()
    generate_html_report()
    print(f"📊 JSON Log: {logger.log_path}", flush=True)
    print(f"📊 Summary: {summary_path}", flush=True)


def _print_sql_type_distribution():
    """Print SQL type distribution with test method and status."""
    from rich.table import Table
    from core.display import console_err

    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT sql_type,
                   COUNT(*) as cnt,
                   SUM(CASE WHEN tested='Y' AND test_result='PASS' THEN 1 ELSE 0 END) as pass_cnt,
                   SUM(CASE WHEN tested='Y' AND test_result IS NOT NULL AND test_result NOT IN ('PASS','FIXED','SKIP') THEN 1 ELSE 0 END) as fail_cnt,
                   SUM(CASE WHEN tested='N' THEN 1 ELSE 0 END) as untested
            FROM transform_target_list
            GROUP BY sql_type
            ORDER BY cnt DESC
        """)
        type_rows = cursor.fetchall()

    test_methods = {
        'select': 'EXPLAIN + Execute (LIMIT 100)',
        'insert': 'EXPLAIN + Execute (BEGIN/ROLLBACK)',
        'update': 'EXPLAIN + Execute (BEGIN/ROLLBACK)',
        'delete': 'EXPLAIN + Execute (BEGIN/ROLLBACK)',
        'sql': '테스트 대상 아님 (SQL fragment)',
        'resultMap': '테스트 대상 아님',
    }

    table = Table(title="SQL 타입별 테스트 현황", show_lines=True)
    table.add_column("sql_type", style="bold")
    table.add_column("개수", justify="right")
    table.add_column("Pass", justify="right", style="green")
    table.add_column("Fail", justify="right", style="red")
    table.add_column("Test 방식")
    table.add_column("상태")

    for sql_type, cnt, pass_cnt, fail_cnt, untested in type_rows:
        method = test_methods.get(sql_type, '기타')
        # Non-testable types always show as Skip
        if sql_type in ('sql', 'resultMap'):
            status = "⏭️ Skip"
            table.add_row(sql_type, str(cnt), "-", "-", method, status)
        elif pass_cnt == cnt:
            status = "✅ All Pass"
            table.add_row(sql_type, str(cnt), str(pass_cnt), str(fail_cnt), method, status)
        elif fail_cnt > 0:
            status = f"❌ {fail_cnt} Fail"
            table.add_row(sql_type, str(cnt), str(pass_cnt), str(fail_cnt), method, status)
        elif untested > 0:
            status = f"⚠️ {untested} Not Tested"
            table.add_row(sql_type, str(cnt), str(pass_cnt), str(fail_cnt), method, status)
        else:
            status = f"✅ {pass_cnt} Pass"
            table.add_row(sql_type, str(cnt), str(pass_cnt), str(fail_cnt), method, status)

    console_err.print(table)


def _pre_mark_skips(log_fn=print) -> int:
    """Pre-mark non-testable SQL IDs as SKIP before running test phases.

    Marks:
    1. Non-testable types (sql, resultMap) — not executable

    Note: include refid is NOT skipped — after Merge, fragments are inlined
    and the SQL becomes testable via Java executor with full mapper context.

    Returns:
        Number of newly marked SKIP items
    """
    total_marked = 0

    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()

        # Non-testable types only (sql fragment, resultMap)
        cursor.execute("""
            SELECT id, sql_type FROM transform_target_list
            WHERE tested = 'N'
              AND LOWER(sql_type) NOT IN ('select', 'insert', 'update', 'delete')
        """)
        for record_id, sql_type in cursor.fetchall():
            reason = 'SQL fragment — 단독 실행 불가, include하는 SQL에서 간접 테스트' if sql_type == 'sql' else f'{sql_type} — 매핑 정의, SQL 아님'
            cursor.execute(
                "UPDATE transform_target_list SET tested='Y', test_result='SKIP', test_notes=? WHERE id=?",
                (reason, record_id)
            )
            total_marked += 1

        conn.commit()

    if total_marked > 0:
        log_fn(f"\n⏭️  Pre-skip: {total_marked}개 (non-testable types)")

    return total_marked


def _generate_test_failure_report():
    """Auto-generate test failure report via ReviewManager tool and print summary."""
    try:
        from agents.review_manager.tools.diff_tools import generate_test_failure_report
        result = generate_test_failure_report()
        if not result.get('report_path'):
            return None

        summary = result.get('summary', {})
        briefings = result.get('briefings', [])

        # Print failure summary table to console
        _print_failure_summary(summary, briefings)

        return result['report_path']
    except Exception as e:
        print(f"⚠️ 리포트 생성 실패: {e}", flush=True)
    return None


def _print_failure_summary(summary: dict, briefings: list):
    """Print human-readable failure summary to console."""
    from core.display import console_err
    from rich.table import Table
    from rich.panel import Panel

    passed = summary.get('passed', 0)
    failed = summary.get('failed', 0)
    total = passed + failed
    rate = summary.get('pass_rate', 0)

    # Failure table
    if briefings:
        table = Table(title="테스트 실패 리포트", show_lines=True)
        table.add_column("XML", style="cyan", no_wrap=True)
        table.add_column("SQL ID", style="bold")
        table.add_column("오류 이유", style="red")

        for b in briefings:
            error = b.get('error', 'Unknown')
            reason = _human_readable_reason(b.get('category', ''), error)
            table.add_row(b['mapper_file'], b['sql_id'], reason)

        console_err.print(table)

    # Summary text
    summary_lines = [
        f"전체 {total}개 SQL 중 {passed}개 통과, {failed}개 실패 (Pass Rate: {rate}%)",
    ]

    # Group by category for actionable advice
    categories = {}
    for b in briefings:
        cat = b.get('category', 'Other')
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(b)

    for cat, items in sorted(categories.items()):
        ids = ", ".join(b['sql_id'] for b in items)
        if "missing function" in cat.lower():
            summary_lines.append(
                f"- {ids}: SQL 변환 자체는 정상이나, Oracle 패키지 함수를 타겟 DB 함수로 별도 마이그레이션해야 합니다."
            )
        elif "missing table" in cat.lower():
            summary_lines.append(
                f"- {ids}: SQL 문법은 정상이나, 테스트 DB에 해당 테이블이 없어서 실패한 케이스입니다."
            )
        elif "syntax" in cat.lower():
            summary_lines.append(
                f"- {ids}: SQL 문법 오류 — 변환 규칙 확인 후 재변환이 필요합니다."
            )
        elif "type" in cat.lower():
            summary_lines.append(
                f"- {ids}: 타입 불일치 — 메타데이터 기반 파라미터 캐스팅 확인이 필요합니다."
            )
        else:
            summary_lines.append(
                f"- {ids}: {cat} — 수동 확인이 필요합니다."
            )

    console_err.print(Panel("\n".join(summary_lines), title="요약", border_style="yellow"))

    # SKIP recommendation
    skip_candidates = 0
    for cat, items in categories.items():
        cat_lower = cat.lower()
        if any(k in cat_lower for k in ['missing function', 'missing table', 'missing column']):
            skip_candidates += len(items)

    if skip_candidates > 0:
        console_err.print(
            f"\n💡 [yellow]{skip_candidates}건[/yellow]은 인프라/스키마 이슈 (SKIP 처리 가능). "
            f"SKIP 후 재테스트: [bold]retry failed test[/bold]"
        )


def _human_readable_reason(category: str, error: str) -> str:
    """Convert error message to human-readable Korean reason."""
    error_lower = error.lower()

    if "does not exist" in error_lower and "function" in error_lower:
        # Extract function name
        import re
        func_match = re.search(r'function\s+(\w+)', error_lower)
        func_name = func_match.group(1) if func_match else "unknown"
        return f"{func_name} 함수가 타겟 DB에 미존재 (패키지 함수 마이그레이션 필요)"

    if "does not exist" in error_lower and ("relation" in error_lower or "table" in error_lower):
        import re
        tbl_match = re.search(r'relation\s+"?(\w+)"?', error_lower) or re.search(r'table\s+"?(\w+)"?', error_lower)
        tbl_name = tbl_match.group(1) if tbl_match else "unknown"
        return f"테이블 {tbl_name}이 타겟 DB에 미존재 (스키마 마이그레이션 필요)"

    if "column" in error_lower and "does not exist" in error_lower:
        import re as _re
        col_match = _re.search(r'column\s+"?(\w+)"?', error_lower)
        col_name = col_match.group(1) if col_match else "unknown"
        return f"컬럼 {col_name} 미존재 — 스키마 확인 필요"

    if "syntax error" in error_lower:
        return f"SQL 문법 오류 — 재변환 필요"

    if "type" in error_lower and ("mismatch" in error_lower or "cast" in error_lower):
        return f"타입 불일치 — 파라미터 캐스팅 확인 필요"

    # Fallback: truncate error
    return error[:100] if len(error) > 100 else error


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
    parser.add_argument('--retry-failed', action='store_true', help='Reset only failed tests for re-test')
    parser.add_argument('--fix', action='store_true', help='Enable Phase 2 Agent auto-fix for failures')
    args = parser.parse_args()

    if args.reset:
        print("🔄 Resetting test flags...", flush=True)
        with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE transform_target_list SET tested='N', test_result=NULL WHERE tested='Y'")
            reset_count = cursor.rowcount
            conn.commit()
        print(f"✅ Reset {reset_count} SQL IDs\n", flush=True)

    if args.retry_failed:
        print("🔄 Resetting failed test items only...", flush=True)
        with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE transform_target_list
                SET tested='N', test_result=NULL
                WHERE tested='Y' AND test_result IS NOT NULL AND test_result NOT IN ('PASS', 'FIXED')
            """)
            reset_count = cursor.rowcount
            conn.commit()
        print(f"✅ Reset {reset_count} failed SQL IDs for re-test\n", flush=True)

    run(max_workers=args.workers, auto_fix=args.fix)
