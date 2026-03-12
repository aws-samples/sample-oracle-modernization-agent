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

    progress = progress_counter.get('progress')
    task_id = progress_counter.get('task_id')

    def log(msg):
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

    def advance_progress(count, last_sql_id=""):
        with progress_counter['lock']:
            progress_counter['done'] += count
            if progress and task_id is not None:
                desc = f"Validate: {Path(mapper_file).stem}:{last_sql_id}" if last_sql_id else "Validate"
                progress.update(task_id, advance=count, description=desc)

    try:
        log(f"🔍 시작: {len(sql_ids)} SQL IDs")
        groups = _group_by_file_size(sql_ids)

        for g_num, group in enumerate(groups, 1):
            ids_str = ", ".join(s['sql_id'] for s in group)
            log(f"📦 Group {g_num}/{len(groups)}: {len(group)} SQLs")
            log(f"   SQL IDs: {ids_str}")

            # Run agent (callback_handler=None suppresses streaming output)
            agent = create_agent()
            agent(
                f"Validate the following SQL IDs in {mapper_file}: {ids_str}\n"
                f"For each SQL ID: read_sql_source for original, read_transform for converted, compare and validate.\n"
                f"If PASS: call set_validated. If FAIL: fix with convert_sql then call set_validated."
            )

            # Drain queue (best-effort) but advance by group size regardless
            drain_progress()
            advance_progress(len(group), group[-1]['sql_id'])

        log(f"✅ {mapper_file} 검증 완료")
        return {'mapper': mapper_file, 'status': 'success', 'count': len(sql_ids)}
    except Exception as e:
        log(f"❌ {mapper_file}: {e}")
        return {'mapper': mapper_file, 'status': 'error', 'error': str(e)}


def run(max_workers=8):
    from core.display import console_err
    console_err.print("[bold]SQL Validate Agent[/bold]")

    pending = get_pending_validations()
    if pending['total'] == 0:
        print("✅ 모든 SQL이 이미 검증 완료!", flush=True)
        return

    mapper_list = list(pending['pending'].items())
    console_err.print(f"  Pending: {pending['total']} SQL IDs / {len(mapper_list)} mappers / workers={max_workers}")

    from core.display import create_step_progress

    results = []
    with create_step_progress() as progress:
        task_id = progress.add_task("Validate", total=pending['total'])
        progress_counter = {
            'started': 0, 'done': 0, 'lock': threading.Lock(),
            'progress': progress, 'task_id': task_id,
        }

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(validate_mapper, m, s, progress_counter, pending['total']): m for m, s in mapper_list}
            for future in as_completed(futures):
                results.append(future.result())

    # 결과
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE validated='Y'")
        validated = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM transform_target_list")
        total = cursor.fetchone()[0]

    from core.display import print_step_result

    rows = [("Validated", f"{validated}/{total} SQL IDs")]

    failed = [r for r in results if r['status'] != 'success']
    if failed:
        for r in failed:
            rows.append(("Failed", f"[red]{r['mapper']}: {r.get('error', 'unknown')}[/red]"))

    remaining = total - validated
    if remaining > 0:
        rows.append(("Remaining", f"[yellow]{remaining} SQL IDs[/yellow]"))
    else:
        rows.append(("Status", "[green]All validated[/green]"))
        if _refine_strategy_from_logs():
            _suggest_compaction()

    rows.append(("Logs", str(_log_dir)))
    print_step_result("Validate Result", rows)


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
