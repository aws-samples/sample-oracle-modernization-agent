"""Run SQL Transform Agent - parallel by mapper"""
import sys
import sqlite3
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent))

from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.types.content import SystemContentBlock
from utils.project_paths import PROJECT_ROOT, DB_PATH, LOGS_DIR, OUTPUT_DIR, MODEL_ID, get_rules_path, get_target_db_display_name, load_prompt_text
from core.progress import drain_progress

from agents.sql_transform.tools.load_mapper_list import load_mapper_list, get_pending_transforms, read_sql_source
from agents.sql_transform.tools.split_mapper import split_mapper
from agents.sql_transform.tools.convert_sql import convert_sql
from agents.sql_transform.tools.save_conversion import save_conversion_report
from agents.sql_transform.tools.metadata import generate_metadata, lookup_column_type

_prompt_cache = None
_model_profiles = [MODEL_ID]
_agent_counter = 0
_counter_lock = threading.Lock()
_log_dir = LOGS_DIR / "transform"


def load_prompt():
    global _prompt_cache
    if _prompt_cache is None:
        base_dir = Path(__file__).parent
        prompt_text = load_prompt_text(base_dir / "agents" / "sql_transform" / "prompt.md")

        rules_path = get_rules_path()
        rules_text = rules_path.read_text(encoding='utf-8') if rules_path.exists() else ""

        strategy_path = base_dir.parent / "output" / "strategy" / "transform_strategy.md"
        strategy_text = strategy_path.read_text(encoding='utf-8') if strategy_path.exists() else ""

        _prompt_cache = [
            SystemContentBlock(text=prompt_text),
            SystemContentBlock(cachePoint={"type": "default"}),
            SystemContentBlock(text=f"\n---\n\n## General Conversion Rules (Static)\n\n{rules_text}"),
            SystemContentBlock(cachePoint={"type": "default"}),
            SystemContentBlock(text=f"\n---\n\n## Project-Specific Conversion Rules (Dynamic)\n\n{strategy_text}"),
            SystemContentBlock(cachePoint={"type": "default"}),
        ]
    return _prompt_cache


def create_agent():
    global _agent_counter
    with _counter_lock:
        model_id = _model_profiles[_agent_counter % len(_model_profiles)]
        _agent_counter += 1
    return Agent(
        name="SQLTransform",
        model=BedrockModel(model_id=model_id, max_tokens=64000),
        system_prompt=load_prompt(),
        tools=[get_pending_transforms, read_sql_source, convert_sql, lookup_column_type, split_mapper],
        callback_handler=None,
    )


def _group_by_file_size(sql_ids: list, max_group_bytes=30000) -> list:
    groups, current, size = [], [], 0
    for s in sql_ids:
        src = Path(s.get('source_file', ''))
        fs = src.stat().st_size if src.exists() else 1000
        if current and size + fs > max_group_bytes:
            groups.append(current)
            current, size = [], 0
        current.append(s)
        size += fs
    if current:
        groups.append(current)
    return groups


def transform_mapper(mapper_file: str, sql_ids: list, progress_counter: dict, total: int) -> dict:
    """Transform pending SQL IDs, logging to file."""
    _log_dir.mkdir(parents=True, exist_ok=True)
    log_path = _log_dir / f"{Path(mapper_file).stem}.log"
    log_path.write_text('', encoding='utf-8')

    progress = progress_counter.get('progress')
    task_id = progress_counter.get('task_id')

    def log(msg):
        timestamp = time.strftime('%H:%M:%S')
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {msg}\n")

    def advance_progress(count, last_sql_id=""):
        """Advance rich progress bar by count."""
        with progress_counter['lock']:
            progress_counter['done'] += count
            if progress and task_id is not None:
                desc = f"Transform: {Path(mapper_file).stem}:{last_sql_id}" if last_sql_id else "Transform"
                progress.update(task_id, advance=count, description=desc)

    try:
        log(f"🚀 시작: {len(sql_ids)} SQL IDs")
        groups = _group_by_file_size(sql_ids)

        for g_num, group in enumerate(groups, 1):
            ids_str = ", ".join(s['sql_id'] for s in group)
            total_kb = sum(Path(s.get('source_file', '')).stat().st_size for s in group if Path(s.get('source_file', '')).exists()) // 1024
            log(f"📦 Group {g_num}/{len(groups)}: {len(group)} SQLs (~{total_kb}KB)")
            log(f"   SQL IDs: {ids_str}")

            # Run agent (callback_handler=None suppresses streaming output)
            agent = create_agent()
            agent(
                f"{mapper_file}의 다음 SQL ID들을 {get_target_db_display_name()}로 변환해줘: {ids_str}\n"
                f"각 SQL ID마다 read_sql_source로 원본을 읽고, 변환 후 convert_sql로 저장해줘."
            )

            # Drain queue (best-effort) but advance by group size regardless
            drain_progress()
            advance_progress(len(group), group[-1]['sql_id'])

        log(f"✅ {mapper_file} 변환 완료")
        return {'mapper': mapper_file, 'status': 'success', 'count': len(sql_ids)}
    except Exception as e:
        log(f"❌ {mapper_file}: {e}")
        return {'mapper': mapper_file, 'status': 'error', 'error': str(e)}


def run(max_workers=8, sample=0):
    from core.display import console_err
    label = f" [cyan](sample={sample})[/cyan]" if sample > 0 else ""
    console_err.print(f"[bold]SQL Transform Agent[/bold]{label}")

    # 1. 전처리 (extract 파일이 없으면 실행)
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transform_target_list'")
        table_exists = cursor.fetchone()
        if table_exists:
            # Check for NULL transformed flags (caused by missing server_default)
            cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE transformed IS NULL")
            null_count = cursor.fetchone()[0]
            if null_count > 0:
                cursor.execute("UPDATE transform_target_list SET transformed='N' WHERE transformed IS NULL")
                cursor.execute("UPDATE transform_target_list SET reviewed='N' WHERE reviewed IS NULL")
                cursor.execute("UPDATE transform_target_list SET validated='N' WHERE validated IS NULL")
                cursor.execute("UPDATE transform_target_list SET tested='N' WHERE tested IS NULL")
                cursor.execute("UPDATE transform_target_list SET completed='N' WHERE completed IS NULL")
                conn.commit()
                print(f"🔧 Fixed {null_count} rows with NULL status flags", flush=True)

    # Check if extract files exist
    extract_exists = (PROJECT_ROOT / "output" / "extract").exists()

    if not table_exists or not extract_exists:
        print("📂 전처리: Extract + Metadata (1회)...", flush=True)
        result = load_mapper_list()
        for m in result['mappers']:
            split_mapper(m['file_path'])
        generate_metadata()
        print(flush=True)

    # 2. Pending 확인
    pending = get_pending_transforms(sample=sample)
    if pending['total'] == 0:
        print("✅ 모든 SQL이 이미 변환 완료!", flush=True)
        save_conversion_report()
        return

    mapper_list = list(pending['pending'].items())
    console_err.print(f"  Pending: {pending['total']} SQL IDs / {len(mapper_list)} mappers / workers={max_workers}")

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # 3. Parallel execution with rich progress bar
    from core.display import create_step_progress

    results = []
    with create_step_progress() as progress:
        task_id = progress.add_task("Transform", total=pending['total'])
        progress_counter = {
            'started': 0, 'done': 0, 'lock': threading.Lock(),
            'progress': progress, 'task_id': task_id,
        }

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(transform_mapper, m, s, progress_counter, pending['total']): m for m, s in mapper_list}
            for future in as_completed(futures):
                results.append(future.result())

    # 4. Generate report
    print(f"\n📊 Generating report...", flush=True)
    save_conversion_report()

    # 최종 완료 판단: DB 기준
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM transform_target_list")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE transformed='Y'")
        done = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE transformed='N'")
        remaining = cursor.fetchone()[0]

    from core.display import print_step_result

    rows = [("Transformed", f"{done}/{total} SQL IDs")]

    if remaining == 0:
        rows.append(("Status", "[green]All complete[/green]"))
    else:
        rows.append(("Remaining", f"[yellow]{remaining} SQL IDs (re-run to continue)[/yellow]"))

    failed = [r for r in results if r['status'] != 'success']
    if failed:
        for r in failed:
            rows.append(("Failed", f"[red]{r['mapper']}: {r.get('error', 'unknown')}[/red]"))

    rows.append(("Logs", str(_log_dir)))
    print_step_result("Transform Result", rows)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--sample', type=int, default=0, help='N개만 샘플 변환 (0=전체)')
    parser.add_argument('--reset', action='store_true', help='전체 초기화 후 재실행')
    args = parser.parse_args()

    if args.reset:
        import shutil
        print("🗑️  Reset: DB + output 초기화...", flush=True)
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute("DROP TABLE IF EXISTS transform_target_list")
            conn.commit()
        output_dir = OUTPUT_DIR
        if output_dir.exists():
            shutil.rmtree(output_dir)
        print("✅ 초기화 완료\n", flush=True)

    run(max_workers=args.workers, sample=args.sample)
