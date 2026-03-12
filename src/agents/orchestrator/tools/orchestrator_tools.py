"""Orchestrator tools - pipeline status check and step execution"""
from pathlib import Path
from strands import tool
from utils.project_paths import PROJECT_ROOT, DB_PATH, OUTPUT_DIR, STRATEGY_DIR
from core.state_manager import StateManager
from agents.orchestrator.schemas import (
    SetupCheckResult, StepStatusResult, RunStepResult, ResetStepResult,
    SummaryResult, SearchSqlResult
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
        'validated': counts['validated'],
        'tested': counts['tested'],
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
def reset_step(step_name: str) -> ResetStepResult:
    """Reset a pipeline step by clearing its completion flags in DB and removing output files.

    Args:
        step_name: 'transform', 'review', 'validate', or 'test'

    Returns:
        ResetStepResult with status and reset count
    """
    import shutil

    state = StateManager(DB_PATH)

    try:
        # Reset status in DB
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
def run_step(step_name: str, sample: int = 0) -> RunStepResult:
    """Execute a pipeline step via direct Agent invocation (importlib).

    Uses importlib.import_module() to directly invoke pipeline step modules
    instead of subprocess.run(). This provides better performance and enables
    future callback support for real-time progress updates.

    Args:
        step_name: Pipeline step to execute
            - 'analyze': Source analysis and strategy generation
            - 'transform': SQL transformation (Oracle → PostgreSQL)
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
        if step_name == 'test' and 'No PostgreSQL connection info' in output:
            result: RunStepResult = {
                'status': 'skipped',
                'details': 'Test skipped: PostgreSQL 접속 정보가 설정되지 않았습니다. run_setup.py에서 DB 접속 정보를 설정하세요.',
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
    status = check_step_status()

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
