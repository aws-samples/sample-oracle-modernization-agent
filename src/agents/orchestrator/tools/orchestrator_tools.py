"""Orchestrator tools - pipeline status check and step execution"""
import sys
from pathlib import Path
from strands import tool
from utils.project_paths import PROJECT_ROOT, DB_PATH, REPORTS_DIR, LOGS_DIR, OUTPUT_DIR, STRATEGY_DIR
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

    print(f"✅ Setup OK: {values}")
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
    
    print("🔍 Generating project strategy...")
    
    import io, contextlib, importlib
    buf = io.StringIO()
    try:
        import run_source_analyzer
        importlib.reload(run_source_analyzer)
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
    print(f"🔄 Refining strategy with {feedback_type}...")

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
    
    import io, contextlib, importlib
    buf = io.StringIO()
    try:
        import run_strategy
        importlib.reload(run_strategy)
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            run_strategy.run(task="compact_strategy")
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
        'validated': counts['validated'],
        'tested': counts['tested'],
        'merged': counts['merged'],
        'transform_complete': counts['transform_complete'],
        'review_complete': counts['review_complete'],
        'validate_complete': counts['validate_complete'],
        'test_complete': counts['test_complete'],
        'merge_complete': counts['merge_complete']
    }

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
def run_step(step_name: str) -> dict:
    """Execute a pipeline step.

    Args:
        step_name: 'analyze', 'transform', 'validate', 'test', 'merge'
    
    Returns:
        Dict with status, step, output, and needs_merge flag (for test step)
    """
    modules = {
        'analyze':   ('run_source_analyzer', 'run'),
        'transform': ('run_sql_transform',   'run'),
        'review':    ('run_sql_review',      'run'),
        'validate':  ('run_sql_validate',    'run'),
        'test':      ('run_sql_test',        'run'),
        'merge':     ('run_sql_merge',       'run'),
    }

    if step_name not in modules:
        return {'status': 'error', 'error': f'Unknown step: {step_name}. Valid: {list(modules.keys())}'}

    module_name, func_name = modules[step_name]
    print(f"\n🚀 Running: {step_name} ({module_name})...\n", flush=True)

    import io, contextlib, importlib

    output_lines = []

    class TeeStream(io.TextIOBase):
        """Write to both real stdout and capture buffer."""
        def __init__(self, real_stdout):
            self._real = real_stdout

        def write(self, s):
            self._real.write(s)
            self._real.flush()
            output_lines.append(s)
            return len(s)

    try:
        import importlib
        mod = importlib.import_module(module_name)
        func = getattr(mod, func_name)
        tee = TeeStream(sys.stdout)
        with contextlib.redirect_stdout(tee), contextlib.redirect_stderr(tee):
            func()

        output = ''.join(output_lines[-100:]) if len(output_lines) > 100 else ''.join(output_lines)
        print(f"\n✅ {step_name} 완료\n", flush=True)
        if step_name == 'transform':
            print("💡 Tip: 변환 결과를 확인하려면 → 'diff 리포트 생성' 또는 '[SQL ID] 비교해줘'", flush=True)
        result = {'status': 'success', 'step': step_name, 'output': output}

        if step_name == 'test' and 'Phase 2:' in output and '건 실패 SQL 수정' in output:
            result['needs_merge'] = True
            result['details'] = 'Test Agent modified SQL files. Run merge to apply changes to final XML.'

        return result

    except Exception as e:
        output = ''.join(output_lines)
        print(f"\n❌ {step_name} 실패: {e}\n", flush=True)
        return {'status': 'error', 'step': step_name, 'output': output, 'error': str(e)}


@tool
def get_summary() -> dict:
    """Get full pipeline summary.

    Returns:
        Dict with all counts, output files, and completion status
    """
    status = check_step_status()

    # Output files
    output_dir = OUTPUT_DIR
    files = {}
    for sub in ['origin', 'extract', 'transform', 'merge']:
        d = output_dir / sub
        files[sub] = len(list(d.rglob("*.xml"))) if d.exists() else 0

    # Reports
    reports = list(REPORTS_DIR.glob("*.md")) if REPORTS_DIR.exists() else []

    # Logs
    log_dirs = ['transform', 'review', 'validate', 'test']
    logs = {}
    for ld in log_dirs:
        d = LOGS_DIR / ld
        logs[ld] = len(list(d.glob("*.log"))) if d.exists() else 0

    summary = {
        'pipeline_status': status,
        'output_files': files,
        'reports': [str(r.name) for r in reports],
        'logs': logs,
        'complete': status.get('next_step') == 'complete'
    }

    print(f"\n{'='*60}")
    print(f"📊 OMA Pipeline Summary")
    print(f"{'='*60}")
    print(f"  Source Analyzed: {'✅' if status['source_analyzed'] else '❌'}")
    print(f"  Transformed:    {status['transformed']}/{status['transform_total']}")
    print(f"  Reviewed:       {status['reviewed']}/{status['review_total']}")
    print(f"  Validated:      {status['validated']}/{status['validate_total']}")
    print(f"  Tested:         {status['tested']}/{status['test_total']}")
    print(f"  Merged:         {files.get('merge', 0)} files")
    print(f"  Output:         {files}")
    print(f"  Complete:       {'✅' if summary['complete'] else '❌ Next: ' + str(status.get('next_step'))}")
    print(f"{'='*60}")

    return summary
