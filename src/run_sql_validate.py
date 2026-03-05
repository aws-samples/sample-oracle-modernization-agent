"""Run SQL Validate Agent - parallel by mapper"""
import sys
import sqlite3
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent))

from utils.project_paths import PROJECT_ROOT, DB_PATH, LOGS_DIR
from core.progress import drain_progress

from agents.sql_validate.agent import create_sql_validate_agent
from agents.sql_validate.tools.validate_tools import get_pending_validations

_log_dir = LOGS_DIR / "validate"


def create_agent():
    return create_sql_validate_agent(suppress_streaming=True)


def _group_by_file_size(sql_ids: list, max_group_bytes=30000) -> list:
    groups, current, size = [], [], 0
    for s in sql_ids:
        src = Path(s.get('source_file', ''))
        fs = src.stat().st_size if src.exists() else 1000
        # Validation reads both source + transform, so double the size estimate
        fs *= 2
        if current and size + fs > max_group_bytes:
            groups.append(current)
            current, size = [], 0
        current.append(s)
        size += fs
    if current:
        groups.append(current)
    return groups


def validate_mapper(mapper_file: str, sql_ids: list, progress_counter: dict, total: int) -> dict:
    _log_dir.mkdir(parents=True, exist_ok=True)
    log_path = _log_dir / f"{Path(mapper_file).stem}.log"
    log_path.write_text('', encoding='utf-8')

    # Progress log for console display
    progress_log = _log_dir.parent / "validate_progress.log"

    def log(msg):
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

    def console(sql_id, status):
        """Print real-time status with progress"""
        with progress_counter['lock']:
            if status == "🔍 검증중":
                progress_counter['started'] += 1
            elif status in ["✅ PASS", "🔧 FIXED"]:
                progress_counter['done'] += 1
            current = progress_counter['started']
            pct = int(current * 100 / total) if total > 0 else 0
            msg = f"[{pct:3d}%] [{Path(mapper_file).stem}] {sql_id} - {status}"
            # Write to progress log instead of stderr
            with open(progress_log, 'a', encoding='utf-8') as f:
                f.write(f"{msg}\n")

    try:
        log(f"🔍 시작: {len(sql_ids)} SQL IDs")
        groups = _group_by_file_size(sql_ids)

        for g_num, group in enumerate(groups, 1):
            ids_str = ", ".join(s['sql_id'] for s in group)
            log(f"📦 Group {g_num}/{len(groups)}: {len(group)} SQLs")
            log(f"   SQL IDs: {ids_str}")

            # Show each SQL ID starting
            for s in group:
                console(s['sql_id'], "🔍 검증중")

            # Run agent (callback_handler=None suppresses streaming output)
            agent = create_agent()
            agent(
                f"Validate the following SQL IDs in {mapper_file}: {ids_str}\n"
                f"For each SQL ID: read_sql_source for original, read_transform for converted, compare and validate.\n"
                f"If PASS: call set_validated. If FAIL: fix with convert_sql then call set_validated."
            )

            # Read completion events from thread-safe queue
            for event in drain_progress():
                sig_sql_id = event["sql_id"]
                sig_result = event.get("status", "")
                sig_notes = event.get("notes", "")
                for s in group:
                    if s['sql_id'] == sig_sql_id:
                        if sig_result == 'PASS':
                            reason = sig_notes.strip()[:60] if sig_notes.strip() else ""
                            console(s['sql_id'], f"✅ PASS - {reason}" if reason else "✅ PASS")
                        else:
                            reason = sig_notes.strip()[:60] if sig_notes.strip() else ""
                            console(s['sql_id'], f"🔧 FIXED - {reason}" if reason else "🔧 FIXED")
                        break

            # Log errors from agent output if any
            # (Agent output no longer captured via stdout; errors logged by agent tools)

        log(f"✅ {mapper_file} 검증 완료")
        return {'mapper': mapper_file, 'status': 'success', 'count': len(sql_ids)}
    except Exception as e:
        log(f"❌ {mapper_file}: {e}")
        console("ERROR", f"❌ {str(e)}")
        return {'mapper': mapper_file, 'status': 'error', 'error': str(e)}


def _tail_progress_log(progress_log: Path, stop_event: threading.Event, stderr):
    """Tail progress log file and display to console"""
    last_pos = 0
    while not stop_event.is_set():
        if progress_log.exists():
            with open(progress_log, 'r', encoding='utf-8') as f:
                f.seek(last_pos)
                new_lines = f.read()
                if new_lines:
                    stderr.write(new_lines)
                    stderr.flush()
                last_pos = f.tell()
        stop_event.wait(0.1)


def run(max_workers=8):
    print("🔍 SQL Validate Agent 시작...\n", flush=True)

    pending = get_pending_validations()
    if pending['total'] == 0:
        print("✅ 모든 SQL이 이미 검증 완료!", flush=True)
        return

    mapper_list = list(pending['pending'].items())
    print(f"🔍 Pending: {pending['total']} SQL IDs across {len(mapper_list)} mappers (workers={max_workers})", flush=True)
    print(f"📁 Logs: {_log_dir}/\n", flush=True)

    # Initialize progress log
    progress_log = _log_dir.parent / "validate_progress.log"
    progress_log.write_text('', encoding='utf-8')

    # Start tail monitor with original stderr
    original_stderr = sys.stderr
    stop_monitor = threading.Event()
    monitor = threading.Thread(target=_tail_progress_log, args=(progress_log, stop_monitor, original_stderr), daemon=True)
    monitor.start()

    progress_counter = {'started': 0, 'done': 0, 'lock': threading.Lock()}
    total_sql_count = pending['total']

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(validate_mapper, m, s, progress_counter, total_sql_count): m for m, s in mapper_list}
        for future in as_completed(futures):
            results.append(future.result())

    stop_monitor.set()
    monitor.join(timeout=2)

    # 결과
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE validated='Y'")
        validated = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM transform_target_list")
        total = cursor.fetchone()[0]

    print(f"\n{'='*60}", flush=True)
    print(f"📊 결과: {validated}/{total} SQL IDs validated", flush=True)

    failed = [r for r in results if r['status'] != 'success']
    if failed:
        for r in failed:
            print(f"  ❌ {r['mapper']}: {r.get('error', 'unknown')}", flush=True)

    remaining = total - validated
    if remaining > 0:
        print(f"⚠️  미완료: {remaining}개 SQL IDs", flush=True)
    else:
        print(f"✅ 전체 검증 완료!", flush=True)

        # 전략 보강: FIXED 패턴 수집
        if _refine_strategy_from_logs():
            # 압축 제안
            _suggest_compaction()

    print(f"📁 Logs: {_log_dir}/", flush=True)
    print(f"{'='*60}", flush=True)


def _refine_strategy_from_logs():
    """Collect fix patterns and refine strategy via Strategy Refine Agent.

    Returns:
        bool: True if patterns were added
    """
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
    """Auto-compact strategy file if it exceeds thresholds."""
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
    args = parser.parse_args()
    run(max_workers=args.workers)
