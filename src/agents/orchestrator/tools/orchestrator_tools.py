"""Orchestrator tools - pipeline status check and step execution"""
import sys
import sqlite3
from pathlib import Path
from strands import tool
from utils.project_paths import PROJECT_ROOT, DB_PATH, CONFIG_DIR, REPORTS_DIR, LOGS_DIR, OUTPUT_DIR, MERGE_DIR, STRATEGY_DIR


@tool
def check_setup() -> dict:
    """Check if oma_control.db exists and has required properties.

    Returns:
        Dict with ready status and missing items
    """
    if not DB_PATH.exists():
        return {'ready': False, 'missing': ['oma_control.db not found. Run: python3 src/run_setup.py']}

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Check properties table
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='properties'")
    if not cursor.fetchone():
        conn.close()
        return {'ready': False, 'missing': ['properties table not found. Run: python3 src/run_setup.py']}

    required = ['JAVA_SOURCE_FOLDER', 'SOURCE_DBMS_TYPE', 'TARGET_DBMS_TYPE']
    missing = []
    values = {}
    for key in required:
        cursor.execute("SELECT value FROM properties WHERE key = ?", (key,))
        row = cursor.fetchone()
        if not row:
            missing.append(key)
        else:
            values[key] = row[0]

    conn.close()

    if missing:
        return {'ready': False, 'missing': missing, 'values': values}

    # Check source folder exists
    src = Path(values['JAVA_SOURCE_FOLDER'])
    if not src.exists():
        return {'ready': False, 'missing': [f"JAVA_SOURCE_FOLDER path not found: {src}"], 'values': values}

    print(f"✅ Setup OK: {values}")
    return {'ready': True, 'values': values}


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
                result_dict = eval(line.replace('📋 결과:', '').strip())
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
    
    # Collect feedback data from DB
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    feedback = {'type': feedback_type, 'cases': []}
    
    if feedback_type in ['validation_failures', 'all_failures']:
        cursor.execute("""
            SELECT mapper_file, sql_id, validated, transform_count
            FROM transform_target_list
            WHERE validated = 'N' AND transform_count > 1
            LIMIT 20
        """)
        for row in cursor.fetchall():
            feedback['cases'].append({
                'stage': 'validate',
                'mapper': row[0],
                'sql_id': row[1],
                'attempts': row[3]
            })
    
    if feedback_type in ['test_failures', 'all_failures']:
        cursor.execute("""
            SELECT mapper_file, sql_id, tested, test_result
            FROM transform_target_list
            WHERE tested = 'N' AND test_result LIKE '%FAIL%'
            LIMIT 20
        """)
        for row in cursor.fetchall():
            feedback['cases'].append({
                'stage': 'test',
                'mapper': row[0],
                'sql_id': row[1],
                'result': row[3]
            })
    
    conn.close()
    
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
def check_step_status() -> dict:
    """Check current pipeline status from DB.

    Returns:
        Dict with step completion counts
    """
    result = {
        'source_analyzed': False,
        'extracted': 0, 'extract_total': 0,
        'transformed': 0, 'transform_total': 0,
        'reviewed': 0, 'review_total': 0,
        'validated': 0, 'validate_total': 0,
        'tested': 0, 'test_total': 0,
        'merged': 0,
        'next_step': None
    }

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Check source_xml_list
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='source_xml_list'")
    if cursor.fetchone():
        cursor.execute("SELECT COUNT(*) FROM source_xml_list")
        count = cursor.fetchone()[0]
        result['source_analyzed'] = count > 0
        result['source_count'] = count

    # Check transform_target_list
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transform_target_list'")
    if cursor.fetchone():
        cursor.execute("SELECT COUNT(*) FROM transform_target_list")
        result['extract_total'] = cursor.fetchone()[0]
        result['extracted'] = result['extract_total']

        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE transformed='Y'")
        result['transformed'] = cursor.fetchone()[0]
        result['transform_total'] = result['extract_total']

        # reviewed column may not exist yet
        try:
            cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE reviewed='Y'")
            result['reviewed'] = cursor.fetchone()[0]
        except:
            result['reviewed'] = 0
        result['review_total'] = result['transform_total']

        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE validated='Y'")
        result['validated'] = cursor.fetchone()[0]
        result['validate_total'] = result['extract_total']

        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE tested='Y'")
        result['tested'] = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM transform_target_list")
        result['test_total'] = cursor.fetchone()[0]

    conn.close()

    # Check merge output
    merge_dir = MERGE_DIR
    result['merged'] = len(list(merge_dir.rglob("*.xml"))) if merge_dir.exists() else 0

    # Check strategy file
    strategy_file = STRATEGY_DIR / "transform_strategy.md"
    result['strategy_exists'] = strategy_file.exists()

    # Add completion flags for each step
    result['transform_complete'] = result['transformed'] == result['transform_total'] and result['transform_total'] > 0
    result['review_complete'] = result['reviewed'] == result['review_total'] and result['review_total'] > 0
    result['validate_complete'] = result['validated'] == result['validate_total'] and result['validate_total'] > 0
    result['test_complete'] = result['tested'] == result['test_total'] and result['test_total'] > 0
    result['merge_complete'] = result['merged'] > 0

    # Determine next step
    if not result['source_analyzed']:
        result['next_step'] = 'analyze'
    elif not result['strategy_exists']:
        result['next_step'] = 'generate_strategy'
    elif result['transformed'] < result['transform_total'] or result['transform_total'] == 0:
        result['next_step'] = 'transform'
    elif result['reviewed'] < result['review_total']:
        result['next_step'] = 'review'
    elif result['validated'] < result['validate_total']:
        result['next_step'] = 'validate'
    elif result['tested'] < result['test_total']:
        result['next_step'] = 'test'
    elif result['merged'] == 0:
        result['next_step'] = 'merge'
    else:
        result['next_step'] = 'complete'

    print(f"📊 Status: analyzed={result['source_analyzed']}, "
          f"transformed={result['transformed']}/{result['transform_total']}, "
          f"reviewed={result['reviewed']}/{result['review_total']}, "
          f"validated={result['validated']}/{result['validate_total']}, "
          f"tested={result['tested']}/{result['test_total']}, "
          f"merged={result['merged']}")
    print(f"➡️  Next: {result['next_step']}")

    return result


@tool
def search_sql_ids(keyword: str = "") -> dict:
    """Search SQL IDs by keyword in mapper_file or sql_id.
    
    Args:
        keyword: Search term (e.g., "User", "select", "Order")
                 If empty, returns all SQL IDs
    
    Returns:
        Dict with matching SQL IDs grouped by mapper_file
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if keyword:
        cursor.execute("""
            SELECT mapper_file, sql_id, sql_type
            FROM transform_target_list
            WHERE mapper_file LIKE ? OR sql_id LIKE ?
            ORDER BY mapper_file, seq_no
        """, (f'%{keyword}%', f'%{keyword}%'))
    else:
        cursor.execute("""
            SELECT mapper_file, sql_id, sql_type
            FROM transform_target_list
            ORDER BY mapper_file, seq_no
            LIMIT 50
        """)
    
    rows = cursor.fetchall()
    conn.close()
    
    # Group by mapper
    results = {}
    for mapper, sql_id, sql_type in rows:
        if mapper not in results:
            results[mapper] = []
        results[mapper].append({'sql_id': sql_id, 'sql_type': sql_type})
    
    total = sum(len(v) for v in results.values())
    
    return {
        'total': total,
        'mappers_count': len(results),
        'results': results,
        'message': f"Found {total} SQL IDs across {len(results)} mappers"
    }


@tool
def reset_step(step_name: str) -> dict:
    """Reset a pipeline step by clearing its completion flags in DB and removing output files.
    
    Args:
        step_name: 'transform', 'validate', or 'test'
    
    Returns:
        dict with status and reset count
    """
    import shutil
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if step_name == 'transform':
        cursor.execute("UPDATE transform_target_list SET transformed='N'")
        count = cursor.rowcount
        # Delete output files
        for d in ['extract', 'transform', 'origin']:
            dir_path = PROJECT_ROOT / "output" / d
            if dir_path.exists():
                shutil.rmtree(dir_path)
    elif step_name == 'review':
        cursor.execute("UPDATE transform_target_list SET reviewed='N' WHERE transformed='Y'")
        count = cursor.rowcount
    elif step_name == 'validate':
        cursor.execute("UPDATE transform_target_list SET validated='N'")
        count = cursor.rowcount
    elif step_name == 'test':
        cursor.execute("UPDATE transform_target_list SET tested='N'")
        count = cursor.rowcount
        # Delete test output
        test_dir = PROJECT_ROOT / "output" / "test"
        if test_dir.exists():
            shutil.rmtree(test_dir)
    else:
        conn.close()
        return {'status': 'error', 'message': f'Unknown step: {step_name}'}
    
    conn.commit()
    conn.close()
    
    return {'status': 'success', 'step': step_name, 'reset_count': count}


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
