"""Orchestrator tools - pipeline status check and step execution"""
from pathlib import Path
from strands import tool
from utils.project_paths import PROJECT_ROOT, DB_PATH, OUTPUT_DIR, STRATEGY_DIR
from core.state_manager import StateManager
from agents.orchestrator.schemas import (
    SetupCheckResult, StepStatusResult, RunStepResult, ResetStepResult,
    SummaryResult, SearchSqlResult, GetFailuresResult
)


@tool
def check_setup() -> SetupCheckResult:
    """Check if oma_control.db exists and has required properties.

    Returns:
        SetupCheckResult with ready status and missing items
    """
    if not DB_PATH.exists():
        result: SetupCheckResult = {
            'ready': False,
            'missing': ['oma_control.db not found. Run: python3 src/run_setup.py'],
            'values': None
        }
        return result

    state = StateManager(DB_PATH)

    # Check properties table
    if not state.table_exists('properties'):
        result: SetupCheckResult = {
            'ready': False,
            'missing': ['properties table not found. Run: python3 src/run_setup.py'],
            'values': None
        }
        return result

    # Check required properties
    required = ['JAVA_SOURCE_FOLDER', 'SOURCE_DBMS_TYPE', 'TARGET_DBMS_TYPE']
    missing = []
    values = {}

    for key in required:
        value = state.get_property(key)
        if not value:
            missing.append(key)
        else:
            values[key] = value

    if missing:
        result: SetupCheckResult = {
            'ready': False,
            'missing': missing,
            'values': values if values else None
        }
        return result

    # Check source folder exists
    src = Path(values['JAVA_SOURCE_FOLDER'])
    if not src.exists():
        result: SetupCheckResult = {
            'ready': False,
            'missing': [f"JAVA_SOURCE_FOLDER path not found: {src}"],
            'values': values
        }
        return result

    from core.display import print_step_result
    print_step_result("Setup Check", [
        ("Status", "[green]Ready[/green]"),
        ("Source DBMS", values.get('SOURCE_DBMS_TYPE', '-')),
        ("Target DBMS", values.get('TARGET_DBMS_TYPE', '-')),
        ("Source Path", values.get('JAVA_SOURCE_FOLDER', '-')),
    ])
    result: SetupCheckResult = {
        'ready': True,
        'missing': None,
        'values': values
    }
    return result


@tool
def generate_project_strategy() -> str:
    """
    Generate project-specific transformation strategy.
    
    Analyzes SQL patterns and creates output/strategy/transform_strategy.md
    with project-specific conversion rules that complement static rules.
    
    Returns:
        JSON string with:
        - status: success/failed
        - file_path: strategy file path
        - file_size_kb: file size
        - pattern_count: number of project-specific patterns
        - needs_compression: true if compression recommended
    """
    import json
    
    from core.display import console_err
    console_err.rule("[bold blue]Generating project strategy[/bold blue]")
    
    import io, contextlib
    buf = io.StringIO()
    try:
        import run_source_analyzer
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            run_source_analyzer.run()
        stdout = buf.getvalue()
    except Exception as e:
        return json.dumps({'status': 'failed', 'error': str(e)})
    
    lines = stdout.strip().split('\n')
    for line in reversed(lines):
        if line.startswith('📋 결과:'):
            try:
                import ast
                result_dict = ast.literal_eval(line.replace('📋 결과:', '').strip())
                return json.dumps(result_dict, ensure_ascii=False)
            except:
                pass
    
    strategy_file = STRATEGY_DIR / "transform_strategy.md"
    if strategy_file.exists():
        return json.dumps({'status': 'success', 'file_path': str(strategy_file), 'message': 'Strategy generated'})
    return json.dumps({'status': 'failed', 'error': 'Strategy file not created'})


@tool
def refine_project_strategy(feedback_type: str = "validation_failures") -> str:
    """
    Refine existing strategy with learning data from failures.

    Args:
        feedback_type: Type of feedback to collect
            - 'validation_failures': Failed validation cases
            - 'test_failures': Failed test cases
            - 'all_failures': Both validation and test failures

    Returns:
        Success message
    """
    from core.display import console_err
    console_err.print(f"[blue]Refining strategy with {feedback_type}...[/blue]")

    state = StateManager(DB_PATH)
    feedback = {'type': feedback_type, 'cases': []}

    # Collect feedback data using StateManager
    if feedback_type in ['validation_failures', 'all_failures']:
        for row in state.get_validation_failures(limit=20):
            feedback['cases'].append({
                'stage': 'validate',
                'mapper': row[0],
                'sql_id': row[1],
                'attempts': row[3]
            })

    if feedback_type in ['test_failures', 'all_failures']:
        for row in state.get_test_failures(limit=20):
            feedback['cases'].append({
                'stage': 'test',
                'mapper': row[0],
                'sql_id': row[1],
                'result': row[3]
            })

    if not feedback['cases']:
        return "ℹ️ No failure cases found to learn from"

    # Call Strategy Refine Agent
    try:
        from agents.strategy_refine.agent import create_strategy_refine_agent
        agent = create_strategy_refine_agent()
        agent("Refine: collect feedback patterns and add as Before/After examples to strategy.")
        return "✅ Strategy refined with failure patterns"
    except Exception as e:
        return f"⚠️ Strategy refinement failed: {e}"


@tool
def compact_strategy() -> str:
    """Compact transform strategy file by removing duplicates and summarizing patterns.
    
    Returns:
        Success message with compression stats
    """
    strategy_file = OUTPUT_DIR / "strategy" / "transform_strategy.md"
    if not strategy_file.exists():
        return "❌ 전략 파일이 없습니다."
    
    import io, contextlib
    buf = io.StringIO()
    try:
        import run_strategy
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            run_strategy.compact_strategy()
        return f"✅ 전략 압축 완료\n{buf.getvalue()}"
    except Exception as e:
        return f"❌ 압축 실패: {e}"


@tool
def check_step_status() -> StepStatusResult:
    """Check current pipeline status from DB.

    Returns:
        StepStatusResult with step completion counts and flags
    """
    state = StateManager(DB_PATH)
    counts = state.get_step_counts()

    result: StepStatusResult = {
        'source_analyzed': counts['source_analyzed'],
        'extracted': counts['extracted'],
        'transformed': counts['transformed'],
        'reviewed': counts['reviewed'],
        'review_failed': counts['review_failed'],
        'review_warnings': counts.get('review_warnings', 0),
        'validated': counts['validated'],
        'validate_failed': counts.get('validate_failed', 0),
        'tested': counts['tested'],
        'test_failed': counts.get('test_failed', 0),
        'test_skipped': counts.get('test_skipped', 0),
        'merged': counts['merged'],
        'transform_complete': bool(counts['transform_complete']),
        'review_complete': bool(counts['review_complete']),
        'validate_complete': bool(counts['validate_complete']),
        'test_complete': bool(counts['test_complete']),
        'merge_complete': bool(counts['merge_complete'])
    }

    from core.display import print_pipeline_status
    print_pipeline_status(result)

    return result


@tool
def search_sql_ids(keyword: str = "") -> SearchSqlResult:
    """Search SQL IDs by keyword in mapper_file or sql_id.

    Args:
        keyword: Search term (e.g., "User", "select", "Order")
                 If empty, returns first 50 SQL IDs

    Returns:
        SearchSqlResult with matching SQL IDs grouped by mapper_file
    """
    state = StateManager(DB_PATH)
    rows = state.search_sqls(keyword, limit=50)

    # Group by mapper
    results = {}
    for mapper, sql_id, sql_type in rows:
        if mapper not in results:
            results[mapper] = []
        results[mapper].append({'sql_id': sql_id, 'sql_type': sql_type})

    total = sum(len(v) for v in results.values())

    result: SearchSqlResult = {
        'total': total,
        'mappers_count': len(results),
        'results': results
    }
    return result


@tool
def get_failures(step_name: str = "all") -> GetFailuresResult:
    """Get failed SQL IDs for a specific pipeline step or all steps.

    Use this when user asks: "어떤 SQL이 실패했어?", "FAIL된 거 보여줘",
    "review 실패 목록", "test 실패한 SQL ID", etc.

    Args:
        step_name: 'review', 'validate', 'test', or 'all' (default: all)

    Returns:
        GetFailuresResult with failed SQL IDs, mapper files, and reasons
    """
    import sqlite3

    failures = []

    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()

        if step_name in ('review', 'all'):
            cursor.execute("""
                SELECT mapper_file, sql_id, sql_type, review_result
                FROM transform_target_list
                WHERE reviewed = 'F'
                ORDER BY mapper_file, seq_no
            """)
            for mapper, sql_id, sql_type, result in cursor.fetchall():
                reason = _extract_review_reason(result)
                failures.append({
                    'mapper_file': mapper, 'sql_id': sql_id,
                    'sql_type': sql_type, 'reason': f"[Review] {reason}"
                })

        if step_name in ('validate', 'all'):
            cursor.execute("""
                SELECT mapper_file, sql_id, sql_type, validation_result
                FROM transform_target_list
                WHERE validated = 'Y' AND validation_result IS NOT NULL AND validation_result != 'PASS'
                ORDER BY mapper_file, seq_no
            """)
            for mapper, sql_id, sql_type, result in cursor.fetchall():
                failures.append({
                    'mapper_file': mapper, 'sql_id': sql_id,
                    'sql_type': sql_type, 'reason': f"[Validate] {(result or '')[:100]}"
                })

        if step_name in ('test', 'all'):
            cursor.execute("""
                SELECT mapper_file, sql_id, sql_type, test_result
                FROM transform_target_list
                WHERE tested = 'Y' AND test_result IS NOT NULL AND test_result != 'PASS'
                ORDER BY mapper_file, seq_no
            """)
            for mapper, sql_id, sql_type, result in cursor.fetchall():
                failures.append({
                    'mapper_file': mapper, 'sql_id': sql_id,
                    'sql_type': sql_type, 'reason': f"[Test] {(result or '')[:100]}"
                })

    # Print as Rich table
    if failures:
        from rich.table import Table
        from core.display import console_err

        title = f"Failed SQLs ({step_name})" if step_name != 'all' else "Failed SQLs (all steps)"
        table = Table(title=title, show_lines=True)
        table.add_column("Step", style="bold", no_wrap=True)
        table.add_column("XML", style="cyan")
        table.add_column("SQL ID", style="bold")
        table.add_column("Reason", style="red")

        for f in failures:
            step_tag = f['reason'].split(']')[0] + ']'
            reason = f['reason'].split('] ', 1)[-1]
            table.add_row(step_tag, f['mapper_file'], f['sql_id'], reason[:80])

        console_err.print(table)
    else:
        print(f"✅ No failures found for step: {step_name}")

    return {
        'step': step_name,
        'total': len(failures),
        'failures': failures
    }


def _extract_review_reason(review_result: str) -> str:
    """Extract human-readable reason from review_result JSON."""
    if not review_result:
        return "Review failed"
    try:
        import json
        parsed = json.loads(review_result)
        issues = parsed.get('issues', [])
        if issues:
            first = issues[0]
            if isinstance(first, dict):
                return first.get('description', '')[:100]
            return str(first)[:100]
    except (ValueError, TypeError):
        pass
    return review_result[:100]


@tool
def classify_test_failures() -> dict:
    """Classify test failures by category and show SKIP recommendations.

    Use after test phase when user asks: "실패 분류해줘", "skip 대상 보여줘",
    "test 결과 분류", "어떤 걸 skip할까"

    Returns:
        Dict with categories, counts, skip_candidates, and actionable advice
    """
    import sqlite3
    from rich.table import Table
    from core.display import console_err

    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT sql_id, mapper_file, test_result, test_notes
            FROM transform_target_list
            WHERE tested = 'Y' AND test_result NOT IN ('PASS', 'FIXED', 'SKIP')
        """)
        failures = cursor.fetchall()

    # Categorize
    categories = {}
    for sql_id, mapper, result, notes in failures:
        error = notes or result or ''
        error_lower = error.lower()
        if 'does not exist' in error_lower and 'function' in error_lower:
            cat = 'Missing Function'
        elif 'does not exist' in error_lower and ('relation' in error_lower or 'table' in error_lower):
            cat = 'Missing Table'
        elif 'does not exist' in error_lower and 'column' in error_lower:
            cat = 'Missing Column'
        elif 'syntax error' in error_lower:
            cat = 'Syntax Error'
        elif 'type' in error_lower and ('mismatch' in error_lower or 'cast' in error_lower or 'operator' in error_lower):
            cat = 'Type Mismatch'
        elif 'timeout' in error_lower or 'cancel' in error_lower:
            cat = 'Timeout'
        elif 'null' in error_lower and ('entrySet' in error or 'NullPointer' in error):
            cat = 'Parameter Binding'
        elif 'SAXParse' in error or 'xml' in error_lower:
            cat = 'XML Parse Error'
        elif 'IncompleteElement' in error or 'include refid' in error_lower:
            cat = 'Include Refid'
        elif 'ClassNotFoundException' in error or 'Cannot find class' in error:
            cat = 'Missing Java Class'
        else:
            cat = 'Other'

        if cat not in categories:
            categories[cat] = []
        categories[cat].append({'sql_id': sql_id, 'mapper_file': mapper, 'error': error[:100]})

    # Determine skip-able categories
    skip_categories = {'Missing Function', 'Missing Table', 'Missing Column', 'Timeout',
                       'Parameter Binding', 'Include Refid', 'Missing Java Class'}

    # Display
    table = Table(title="Test 실패 분류", show_lines=True)
    table.add_column("#", justify="right")
    table.add_column("카테고리", style="bold")
    table.add_column("건수", justify="right")
    table.add_column("SKIP 가능", justify="center")
    table.add_column("권고 조치")

    actions = {
        'Missing Function': '타겟 DB에 함수 생성 후 재테스트',
        'Missing Table': '스키마 마이그레이션 후 재테스트',
        'Missing Column': '스키마 확인 필요',
        'Syntax Error': '재변환 필요 (변환 규칙 보강)',
        'Type Mismatch': '메타데이터 기반 파라미터 캐스팅 확인',
        'Timeout': 'SQL은 정상 — 성능 최적화 필요',
        'Parameter Binding': '테스트 파라미터 보강 필요',
        'XML Parse Error': '변환 시 XML 이스케이프 확인',
        'Include Refid': 'cross-mapper fragment 참조 — dependency mapper 확인',
        'Missing Java Class': '테스트 환경에 stub 클래스 추가',
        'Other': '수동 확인 필요',
    }

    total_skip = 0
    for idx, (cat, items) in enumerate(sorted(categories.items(), key=lambda x: -len(x[1])), 1):
        is_skip = cat in skip_categories
        if is_skip:
            total_skip += len(items)
        table.add_row(
            str(idx), cat, str(len(items)),
            "[green]Yes[/green]" if is_skip else "[red]No[/red]",
            actions.get(cat, '수동 확인')
        )

    console_err.print(table)

    if total_skip > 0:
        console_err.print(f"\n💡 [yellow]{total_skip}건[/yellow] SKIP 가능. "
                         f"\"skip category Missing Function\" 등으로 카테고리별 SKIP 처리")

    return {
        'total_failures': len(failures),
        'categories': {cat: len(items) for cat, items in categories.items()},
        'skip_candidates': total_skip,
        'details': categories,
    }


@tool
def skip_by_category(category: str) -> dict:
    """Mark test failures of a specific category as SKIP.

    Use when user says: "Missing Function skip해줘", "skip category Timeout",
    "테이블 없는 거 skip"

    Args:
        category: Category name from classify_test_failures output
                  e.g., 'Missing Function', 'Missing Table', 'Timeout', etc.
    """
    import sqlite3

    import sqlite3

    # Category → error pattern mapping for DB matching
    category_patterns = {
        'Missing Function': ['does not exist', 'function'],
        'Missing Table': ['does not exist', 'relation'],
        'Missing Column': ['does not exist', 'column'],
        'Timeout': ['timeout', 'cancel'],
        'Parameter Binding': ['entrySet', 'NullPointer'],
        'Include Refid': ['IncompleteElement', 'include refid'],
        'Missing Java Class': ['ClassNotFoundException', 'Cannot find class'],
    }

    patterns = category_patterns.get(category)
    if not patterns:
        # Try fuzzy match
        for cat, pats in category_patterns.items():
            if category.lower() in cat.lower():
                category = cat
                patterns = pats
                break
        if not patterns:
            return {'status': 'error', 'message': f'SKIP 가능 카테고리: {", ".join(category_patterns.keys())}'}

    skip_count = 0
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        # Get all non-PASS/SKIP failures
        cursor.execute("""
            SELECT id, test_result, test_notes FROM transform_target_list
            WHERE tested = 'Y' AND test_result NOT IN ('PASS', 'FIXED', 'SKIP')
        """)
        for record_id, result, notes in cursor.fetchall():
            error_text = (notes or result or '').lower()
            if all(p.lower() in error_text for p in patterns):
                cursor.execute(
                    "UPDATE transform_target_list SET test_result='SKIP', test_notes=? WHERE id=?",
                    (f'{category} — SKIP 처리 (사용자 선택)', record_id)
                )
                skip_count += 1
        conn.commit()

    print(f"  ⏭️  {category}: {skip_count}건 SKIP 처리 완료")
    return {'status': 'success', 'category': category, 'skipped': skip_count}


@tool
def generate_test_report() -> dict:
    """Generate test result report (종합 보고서) without re-running tests.

    Use when: "test 보고서 생성", "리포트 만들어줘", "skip 처리 후 보고서 갱신"

    Returns:
        Dict with report_path and summary
    """
    from run_sql_test import _generate_test_result_report
    _generate_test_result_report()

    import sqlite3
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE tested='Y' AND test_result='PASS'")
        passed = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE tested='Y' AND test_result='FIXED'")
        fixed = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE tested='Y' AND test_result='SKIP'")
        skipped = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE tested='Y' AND test_result NOT IN ('PASS','FIXED','SKIP')")
        failed = cursor.fetchone()[0]

    total = passed + fixed + skipped + failed
    rate = ((passed + fixed) * 100 // total) if total else 0
    print(f"📊 Test Report 생성 완료 (Pass: {passed + fixed}, Fail: {failed}, Skip: {skipped}, Rate: {rate}%)")

    return {
        'status': 'success',
        'passed': passed + fixed,
        'failed': failed,
        'skipped': skipped,
        'pass_rate': rate,
        'report_path': str(OUTPUT_DIR / "reports" / "test_result_report.md"),
    }


@tool
def skip_sql(mapper_file: str, sql_id: str, reason: str = "") -> dict:
    """Mark a single SQL ID as SKIP in test results.

    Use when: "selectXxx skip해줘", "이거 skip", "skip sql selectXxx"

    Args:
        mapper_file: Mapper file name (with or without path)
        sql_id: SQL statement ID
        reason: Skip reason (optional)
    """
    import sqlite3
    from utils.db_utils import update_by_mapper

    skip_reason = reason or "사용자 요청에 의한 SKIP"
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        count = update_by_mapper(conn,
            "UPDATE transform_target_list SET tested='Y', test_result='SKIP', test_notes=? WHERE mapper_file=? AND sql_id=?",
            mapper_file, sql_id, extra_params=(skip_reason,))
        conn.commit()

    if count > 0:
        print(f"  ⏭️  SKIP: {mapper_file}/{sql_id} — {skip_reason}")
        return {'status': 'success', 'mapper_file': mapper_file, 'sql_id': sql_id, 'reason': skip_reason}
    return {'status': 'error', 'message': f'Not found: {mapper_file}/{sql_id}'}


@tool
def reset_step(step_name: str, failed_only: bool = False) -> ResetStepResult:
    """Reset a pipeline step by clearing its completion flags in DB and removing output files.

    Args:
        step_name: 'transform', 'review', 'validate', or 'test'
        failed_only: If True, only reset failed items (not passed ones).
                     Use when user says "실패만 재테스트", "retry failed", "failed만 다시"

    Returns:
        ResetStepResult with status and reset count
    """
    import shutil

    state = StateManager(DB_PATH)

    try:
        if failed_only:
            # Reset only failed items for re-test/re-review
            import sqlite3
            with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
                cursor = conn.cursor()
                if step_name == 'test':
                    cursor.execute("""
                        UPDATE transform_target_list
                        SET tested='N', test_result=NULL
                        WHERE tested='Y' AND test_result IS NOT NULL AND test_result NOT IN ('PASS', 'FIXED', 'SKIP')
                    """)
                elif step_name == 'validate':
                    cursor.execute("""
                        UPDATE transform_target_list
                        SET validated='N', validation_result=NULL
                        WHERE validated='Y' AND validation_result IS NOT NULL AND validation_result NOT IN ('PASS', 'FIXED')
                    """)
                elif step_name == 'review':
                    cursor.execute("UPDATE transform_target_list SET reviewed='N' WHERE reviewed='F'")
                else:
                    cursor.execute("""
                        UPDATE transform_target_list SET transformed='N'
                        WHERE transformed='Y' AND reviewed='F'
                    """)
                count = cursor.rowcount
                conn.commit()
            print(f"  🔄 {count}개 실패 항목만 리셋 ({step_name})")
            result: ResetStepResult = {'status': 'success', 'step': step_name, 'reset_count': count}
            return result

        # Full reset
        count = state.reset_step_status(step_name)

        # Delete output files
        if step_name == 'transform':
            for d in ['extract', 'transform', 'origin']:
                dir_path = PROJECT_ROOT / "output" / d
                if dir_path.exists():
                    shutil.rmtree(dir_path)
        elif step_name == 'test':
            test_dir = PROJECT_ROOT / "output" / "test"
            if test_dir.exists():
                shutil.rmtree(test_dir)

        result: ResetStepResult = {
            'status': 'success',
            'step': step_name,
            'reset_count': count
        }
        return result

    except ValueError as e:
        result: ResetStepResult = {
            'status': 'error',
            'step': step_name,
            'reset_count': 0
        }
        return result


@tool
def backup_output(step_name: str = "manual") -> dict:
    """Create a backup of DB and output files.

    Use when user asks: "백업", "backup", "저장", "스냅샷"
    Also called automatically before each pipeline step.

    Args:
        step_name: Label for the backup (default: 'manual')

    Returns:
        Dict with backup_path and size info
    """
    path = _backup_before_step(step_name)
    if path:
        import os
        total_size = sum(
            os.path.getsize(os.path.join(dp, f))
            for dp, _, fns in os.walk(path) for f in fns
        )
        return {'status': 'success', 'backup_path': path, 'size_mb': round(total_size / 1024 / 1024, 1)}
    return {'status': 'error', 'message': 'Nothing to backup (DB not found)'}


def _backup_before_step(step_name: str) -> str:
    """Create a backup of DB and key output files before executing a pipeline step.

    Backup location: output/backup/{step}_{YYYYMMDD_HHMMSS}/
    """
    import shutil
    from datetime import datetime

    if not DB_PATH.exists():
        return ""

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = OUTPUT_DIR / "backup" / f"{step_name}_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Always backup DB
    shutil.copy2(str(DB_PATH), str(backup_dir / DB_PATH.name))

    # Backup step-specific directories
    dirs_to_backup = {
        'transform': ['xmls/transform', 'strategy'],
        'review': ['xmls/transform'],  # review may trigger re-transform
        'validate': ['xmls/transform'],  # validate may fix SQL
        'merge': ['xmls/merge'],
        'test': ['xmls/transform', 'xmls/merge'],  # test may fix SQL + auto re-merge
    }

    for rel_dir in dirs_to_backup.get(step_name, []):
        src_dir = OUTPUT_DIR / rel_dir
        if src_dir.exists():
            dst_dir = backup_dir / rel_dir
            shutil.copytree(str(src_dir), str(dst_dir), dirs_exist_ok=True)

    # Backup reports
    reports_dir = OUTPUT_DIR / "reports"
    if reports_dir.exists():
        shutil.copytree(str(reports_dir), str(backup_dir / "reports"), dirs_exist_ok=True)

    return str(backup_dir)


@tool
def run_step(step_name: str, sample: int = 0) -> RunStepResult:
    """Execute a pipeline step via direct Agent invocation (importlib).

    Uses importlib.import_module() to directly invoke pipeline step modules
    instead of subprocess.run(). This provides better performance and enables
    future callback support for real-time progress updates.

    Args:
        step_name: Pipeline step to execute
            - 'analyze': Source analysis and strategy generation
            - 'transform': SQL transformation (Oracle → Target DB)
            - 'review': Rule compliance check
            - 'validate': Functional equivalence validation
            - 'test': Database execution testing
            - 'merge': XML reassembly
        sample: If > 0, transform only N representative SQLs (transform step only).
                Selects one per sql_type first, then fills remaining by mapper round-robin.

    Returns:
        RunStepResult with status, details, and needs_merge flag
    """
    # Module mapping: step_name → (module_name, function_name)
    modules = {
        'analyze':   ('run_source_analyzer', 'run'),
        'transform': ('run_sql_transform',   'run'),
        'review':    ('run_sql_review',      'run'),
        'validate':  ('run_sql_validate',    'run'),
        'test':      ('run_sql_test',        'run'),
        'merge':     ('run_sql_merge',       'run'),
    }

    if step_name not in modules:
        result: RunStepResult = {
            'status': 'error',
            'details': f'Unknown step: {step_name}. Valid: {list(modules.keys())}',
            'needs_merge': False
        }
        return result

    module_name, func_name = modules[step_name]
    from core.display import console_err
    console_err.rule(f"[bold blue]Running: {step_name}[/bold blue]")

    import io, contextlib, importlib

    output_lines = []

    class CaptureStream(io.TextIOBase):
        """Capture stdout to buffer (discard from terminal — rich stderr is the display channel)."""
        def write(self, s):
            output_lines.append(s)
            return len(s)

    # Backup before execution
    backup_path = _backup_before_step(step_name)
    if backup_path:
        console_err.print(f"[dim]💾 Backup: {backup_path}[/dim]")

    try:
        # Direct Agent invocation via importlib
        mod = importlib.import_module(module_name)
        func = getattr(mod, func_name)

        # Capture stdout silently; stderr (rich output) goes to terminal directly
        capture = CaptureStream()
        with contextlib.redirect_stdout(capture):
            if step_name == 'transform' and sample > 0:
                func(sample=sample)
            else:
                func()

        # Keep last 100 lines if output is large
        output = ''.join(output_lines[-100:]) if len(output_lines) > 100 else ''.join(output_lines)

        console_err.rule(f"[bold green]{step_name} completed[/bold green]")

        # Check if merge is needed (test step may modify SQL files)
        needs_merge = False
        details = f'{step_name} step completed successfully'

        # Detect skipped test (no DB connection)
        if step_name == 'test' and 'connection info' in output and ('No ' in output or 'skipped' in output.lower()):
            result: RunStepResult = {
                'status': 'skipped',
                'details': 'Test skipped: DB 접속 정보가 설정되지 않았습니다. run_setup.py에서 DB 접속 정보를 설정하세요.',
                'needs_merge': False
            }
            console_err.print("[yellow]Test skipped: DB connection info required[/yellow]")
            return result

        if step_name == 'test' and 'Phase 2:' in output and '건 실패 SQL 수정' in output:
            needs_merge = True
            details = 'Test Agent modified SQL files. Run merge step to apply changes to final XML.'

        result: RunStepResult = {
            'status': 'success',
            'details': details,
            'needs_merge': needs_merge
        }
        return result

    except Exception as e:
        output = ''.join(output_lines)
        console_err.rule(f"[bold red]{step_name} failed: {e}[/bold red]")

        result: RunStepResult = {
            'status': 'error',
            'details': f'{step_name} failed: {str(e)}',
            'needs_merge': False
        }
        return result


@tool
def get_summary() -> SummaryResult:
    """Get full pipeline summary with counts, output files, and completion status.

    Returns:
        SummaryResult with complete pipeline information
    """
    # Get counts without printing (check_step_status prints a table)
    state = StateManager(DB_PATH)
    counts = state.get_step_counts()

    status = {
        'source_analyzed': counts['source_analyzed'],
        'extracted': counts['extracted'],
        'transformed': counts['transformed'],
        'reviewed': counts['reviewed'],
        'review_failed': counts['review_failed'],
        'review_warnings': counts.get('review_warnings', 0),
        'validated': counts['validated'],
        'validate_failed': counts.get('validate_failed', 0),
        'tested': counts['tested'],
        'test_failed': counts.get('test_failed', 0),
        'test_skipped': counts.get('test_skipped', 0),
        'merged': counts['merged'],
        'transform_complete': bool(counts['transform_complete']),
        'review_complete': bool(counts['review_complete']),
        'validate_complete': bool(counts['validate_complete']),
        'test_complete': bool(counts['test_complete']),
        'merge_complete': bool(counts['merge_complete']),
    }

    # Output files count
    output_dir = OUTPUT_DIR
    files = {}
    for sub in ['origin', 'extract', 'transform', 'merge']:
        d = output_dir / sub
        count = len(list(d.rglob("*.xml"))) if d.exists() else 0
        files[sub] = str(count)

    # Completion status
    completion = {
        'transform_complete': status['transform_complete'],
        'review_complete': status['review_complete'],
        'validate_complete': status['validate_complete'],
        'test_complete': status['test_complete'],
        'merge_complete': status['merge_complete']
    }

    # Build summary
    result: SummaryResult = {
        'total_sqls': status['extracted'],
        'transformed': status['transformed'],
        'reviewed': status['reviewed'],
        'review_failed': status['review_failed'],
        'validated': status['validated'],
        'tested': status['tested'],
        'merged': int(files.get('merge', '0')),
        'output_files': files,
        'completion_status': completion
    }

    # Print formatted summary (rich table to stderr)
    from core.display import print_pipeline_status
    print_pipeline_status({
        'extracted': status['extracted'],
        'transformed': status['transformed'],
        'reviewed': status['reviewed'],
        'review_failed': status['review_failed'],
        'validated': status['validated'],
        'tested': status['tested'],
        'merged': int(files.get('merge', '0')),
        'source_analyzed': status['source_analyzed'],
        'transform_complete': completion['transform_complete'],
        'review_complete': completion['review_complete'],
        'validate_complete': completion['validate_complete'],
        'test_complete': completion['test_complete'],
        'merge_complete': completion['merge_complete'],
    })

    return result
