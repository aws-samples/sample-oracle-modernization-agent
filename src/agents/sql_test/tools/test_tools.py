"""SQL Test tools - Java executor wrapper + DB flag management"""
import os
import json
import subprocess
import sqlite3
import time
from pathlib import Path
from strands import tool
from utils.project_paths import PROJECT_ROOT, DB_PATH, TRANSFORM_DIR
from agents.sql_transform.tools.metadata import _get_pg_connection_vars


REFERENCE_DIR = PROJECT_ROOT / "src" / "reference"


def _ensure_pg_env():
    """Set PostgreSQL env vars from Parameter Store if not already set."""
    pg_vars = _get_pg_connection_vars()
    if pg_vars:
        os.environ.update(pg_vars)
        return True
    return False


@tool
def run_bulk_test(test_folder: str = "") -> dict:
    """Run Java MyBatis bulk executor on all transform/ XML files.

    Executes run_postgresql.sh against the transform/ directory.
    Returns JSON results with pass/fail per SQL ID.

    Args:
        test_folder: Override test folder path (default: output/transform/main/)
    """
    if not _ensure_pg_env():
        return {'status': 'skipped', 'error': 'No PostgreSQL connection info'}

    if not test_folder:
        test_folder = str(TRANSFORM_DIR / "main")

    # Run Java test
    try:
        # Convert to absolute path to prevent Java from creating relative directories
        test_folder_abs = str(Path(test_folder).resolve())
        
        print(f"  🔧 Executing: bash run_postgresql.sh {test_folder_abs}", flush=True)
        print(f"  📂 Working directory: {REFERENCE_DIR}", flush=True)
        print(f"  ⏱️  Timeout: 600s\n", flush=True)
        
        result = subprocess.run(
            ['bash', 'run_postgresql.sh', test_folder_abs],
            capture_output=True, text=True, timeout=600,
            cwd=str(REFERENCE_DIR),
            env={**os.environ, 'TEST_FOLDER': test_folder_abs}
        )
        
        # Print Java output for debugging
        if result.stdout:
            print("  📋 Java execution log (last 50 lines):", flush=True)
            lines = result.stdout.split('\n')
            for line in lines[-50:]:
                if line.strip():
                    print(f"    {line}", flush=True)
        
        if result.stderr:
            print("  ⚠️  Java stderr:", flush=True)
            for line in result.stderr.split('\n')[:20]:
                if line.strip():
                    print(f"    {line}", flush=True)

        # Parse JSON results if available
        json_result_file = Path(test_folder) / "test_results.json"
        if json_result_file.exists():
            print(f"  📄 Found JSON result file: {json_result_file}", flush=True)
            with open(json_result_file, 'r') as f:
                test_results = json.load(f)
        else:
            print(f"  📄 No JSON file, parsing stdout...", flush=True)
            # Parse stdout for results
            test_results = _parse_stdout_results(result.stdout)

        # Update DB flags
        success_count = 0
        fail_count = 0
        failures = []

        print(f"\n  📊 Parsing {len(test_results.get('results', []))} test results...", flush=True)

        with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
            cursor = conn.cursor()

            for item in test_results.get('results', []):
                sql_id = item.get('sqlId', '')
                filename = item.get('filename', '')  # Just the XML filename
                status = item.get('status', 'UNKNOWN')
                error = item.get('error', '')

                if status == 'SUCCESS':
                    # Match by filename in target_file path (ends with filename)
                    cursor.execute("""
                        UPDATE transform_target_list
                        SET tested = 'Y', updated_at = CURRENT_TIMESTAMP
                        WHERE target_file LIKE ? AND sql_id = ?
                    """, (f'%/{filename}', sql_id))

                    if cursor.rowcount > 0:
                        success_count += 1
                        if success_count <= 5:  # Show first 5
                            print(f"    ✅ {filename}:{sql_id}", flush=True)
                    else:
                        # Try without leading slash for Windows paths
                        cursor.execute("""
                            UPDATE transform_target_list
                            SET tested = 'Y', updated_at = CURRENT_TIMESTAMP
                            WHERE target_file LIKE ? AND sql_id = ?
                        """, (f'%{filename}', sql_id))
                        if cursor.rowcount > 0:
                            success_count += 1
                            if success_count <= 5:
                                print(f"    ✅ {filename}:{sql_id}", flush=True)
                        else:
                            print(f"    ⚠️  No DB match: {filename} / {sql_id}", flush=True)
                else:
                    # Find mapper_file from target_file for failure reporting
                    cursor.execute("""
                        SELECT mapper_file FROM transform_target_list
                        WHERE (target_file LIKE ? OR target_file LIKE ?) AND sql_id = ?
                    """, (f'%/{filename}', f'%{filename}', sql_id))
                    row = cursor.fetchone()
                    mapper_file = row[0] if row else filename

                    fail_count += 1
                    failures.append({
                        'mapper_file': mapper_file,
                        'sql_id': sql_id,
                        'error': error
                    })
                    if fail_count <= 5:  # Show first 5 failures
                        print(f"    ❌ {mapper_file}:{sql_id} - {error[:100]}", flush=True)

            if success_count > 5:
                print(f"    ... and {success_count - 5} more passed", flush=True)
            if fail_count > 5:
                print(f"    ... and {fail_count - 5} more failed", flush=True)

            conn.commit()

        print(f"\n  📊 Test results: {success_count} passed, {fail_count} failed", flush=True)
        return {
            'status': 'completed',
            'total': success_count + fail_count,
            'passed': success_count,
            'failed': fail_count,
            'failures': failures
        }

    except subprocess.TimeoutExpired:
        return {'status': 'timeout', 'error': 'Test execution timed out (600s)'}
    except FileNotFoundError:
        return {'status': 'error', 'error': 'Java or run_postgresql.sh not found'}
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


@tool
def run_single_test(mapper_file: str, sql_id: str) -> dict:
    """Run Java test for a single SQL ID against PostgreSQL.

    Args:
        mapper_file: Mapper file name
        sql_id: SQL statement ID
    """
    if not _ensure_pg_env():
        return {'status': 'skipped', 'error': 'No PostgreSQL connection info'}

    # Find the transform file
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT target_file FROM transform_target_list WHERE mapper_file = ? AND sql_id = ?",
            (mapper_file, sql_id)
        )
        row = cursor.fetchone()

    if not row:
        return {'status': 'error', 'error': f'Not found: {mapper_file}/{sql_id}'}

    target_file = row[0]
    
    # Create a temporary directory with just this one SQL file
    import tempfile
    import shutil
    with tempfile.TemporaryDirectory() as tmpdir:
        # Copy the single XML file to temp directory maintaining structure
        src_path = Path(target_file)
        if not src_path.exists():
            return {'status': 'error', 'error': f'File not found: {target_file}'}
        
        # Maintain directory structure
        rel_path = src_path.relative_to(TRANSFORM_DIR)
        dst_path = Path(tmpdir) / rel_path
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)

        try:
            # Run bulk test on this single file
            result = subprocess.run(
                ['bash', 'run_postgresql.sh', tmpdir],
                capture_output=True, text=True, timeout=60,
                cwd=str(REFERENCE_DIR),
                env={**os.environ, 'TEST_FOLDER': tmpdir}
            )

            output = result.stdout + result.stderr
            
            # Parse result - look for this specific SQL ID in Progress line
            import re
            # Pattern: Progress: X% [n/m] filename.xml:sqlId ❌ Failed: error OR just filename
            progress_pattern = rf'Progress:.*?{re.escape(sql_id)}\s+(❌ Failed:|✅ Passed|Target execution)'
            match = re.search(progress_pattern, output)
            
            if match and '❌ Failed:' in match.group(0):
                # Extract error after "Failed:"
                error_pattern = rf'{re.escape(sql_id)}.*?❌ Failed:(.*?)(?=\n\rProgress:|\n  |\Z)'
                error_match = re.search(error_pattern, output, re.DOTALL)
                error_msg = error_match.group(1).strip() if error_match else "Unknown error"
                return {'status': 'FAIL', 'sql_id': sql_id, 'error': error_msg}
            elif match or f'{sql_id}' in output:
                # Check final summary line for this file
                # Pattern: filename.xml: 1/1 (100.0%) [skipped: 0]
                if '(100.0%)' in output or '✅ Passed' in output:
                    _update_tested(mapper_file, sql_id)
                    return {'status': 'SUCCESS', 'sql_id': sql_id}
                elif 'Error' in output or 'Exception' in output:
                    # Extract error
                    error_lines = [line for line in output.split('\n') if 'Error' in line or 'Exception' in line]
                    error_msg = '\n'.join(error_lines[-5:]) if error_lines else output[-1000:]
                    return {'status': 'FAIL', 'sql_id': sql_id, 'error': error_msg}
            
            # Default: assume success if no error found
            _update_tested(mapper_file, sql_id)
            return {'status': 'SUCCESS', 'sql_id': sql_id}

        except subprocess.TimeoutExpired:
            return {'status': 'FAIL', 'sql_id': sql_id, 'error': 'Timeout (60s)'}
        except Exception as e:
            return {'status': 'FAIL', 'sql_id': sql_id, 'error': str(e)}


@tool
def get_test_failures() -> dict:
    """Get SQL IDs that failed testing (validated='Y' AND tested='N').

    Returns:
        Dict with failures list grouped by mapper_file
    """
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT mapper_file, sql_id, sql_type, source_file, target_file
            FROM transform_target_list
            WHERE validated = 'Y' AND tested = 'N'
            ORDER BY mapper_file, seq_no
        """)
        rows = cursor.fetchall()

    pending = {}
    for mapper, sql_id, sql_type, source, target in rows:
        if mapper not in pending:
            pending[mapper] = []
        pending[mapper].append({
            'sql_id': sql_id, 'sql_type': sql_type,
            'source_file': source, 'target_file': target
        })

    total = sum(len(v) for v in pending.values())
    print(f"📋 Test failures: {total} SQL IDs across {len(pending)} mappers")
    return {'total': total, 'mappers_count': len(pending), 'pending': pending}


def _update_tested(mapper_file: str, sql_id: str):
    for i in range(5):
        try:
            with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
                conn.execute("""
                    UPDATE transform_target_list
                    SET tested = 'Y', updated_at = CURRENT_TIMESTAMP
                    WHERE mapper_file = ? AND sql_id = ?
                """, (mapper_file, sql_id))
                conn.commit()
            # Emit progress event via thread-safe queue
            from core.progress import emit_progress
            emit_progress(mapper_file, sql_id, "PASS")
            return
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and i < 4:
                time.sleep(0.5 * (i + 1))
            else:
                raise


def _parse_stdout_results(stdout: str) -> dict:
    """Parse test results from Java stdout when JSON file not available."""
    import re
    results = []
    
    # Try Progress line first (real-time output)
    pattern = r'Progress:.*?\[\d+/\d+\]\s+(.+?\.xml):(\w+)\s'
    for line in stdout.split('\n'):
        match = re.search(pattern, line)
        if match:
            filename = match.group(1)
            sql_id = match.group(2)
            filename = filename.replace('\\', '/').split('/')[-1]
            has_failed = '❌ Failed:' in line
            status = 'FAIL' if has_failed else 'SUCCESS'
            error_msg = ''
            if has_failed:
                parts = line.split('❌ Failed:', 1)
                if len(parts) > 1:
                    error_msg = parts[1].strip()
            results.append({
                'filename': filename,
                'sqlId': sql_id,
                'status': status,
                'error': error_msg
            })
    
    # If no Progress lines found, parse File Statistics section
    if not results:
        # Pattern: filename.xml: 1/1 (100.0%) or 0/1 (0.0%)
        stats_pattern = r'^\s+(.+?\.xml):\s+(\d+)/(\d+)\s+\([\d.]+%\)'
        for line in stdout.split('\n'):
            match = re.match(stats_pattern, line)
            if match:
                filename = match.group(1)
                success_count = int(match.group(2))
                total_count = int(match.group(3))
                
                # Extract SQL ID from filename (format: MapperName-NN-type-sqlId.xml)
                sql_id_match = re.search(r'-\d+-\w+-(.+)\.xml$', filename)
                if sql_id_match:
                    sql_id = sql_id_match.group(1)
                else:
                    # Fallback: use filename without extension
                    sql_id = filename.replace('.xml', '')
                
                status = 'SUCCESS' if success_count == total_count else 'FAIL'
                
                # For failures, try to find error message in preceding lines
                error_msg = ''
                if status == 'FAIL':
                    # Look for error messages before this stats line
                    lines = stdout.split('\n')
                    for i, l in enumerate(lines):
                        if filename in l and 'Error' in l:
                            # Extract error context
                            error_lines = []
                            for j in range(max(0, i-5), min(len(lines), i+5)):
                                if 'Error' in lines[j] or 'Exception' in lines[j]:
                                    error_lines.append(lines[j].strip())
                            error_msg = ' | '.join(error_lines[:3])  # First 3 error lines
                            break
                
                results.append({
                    'filename': filename,
                    'sqlId': sql_id,
                    'status': status,
                    'error': error_msg
                })
    
    return {'results': results}
