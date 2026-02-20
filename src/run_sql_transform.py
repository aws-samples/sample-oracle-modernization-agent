"""Run SQL Transform Agent - parallel by mapper"""
import sys
import os
import io
import sqlite3
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent))

from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.types.content import SystemContentBlock
from utils.project_paths import PROJECT_ROOT, DB_PATH, LOGS_DIR, OUTPUT_DIR, MERGE_DIR, MODEL_ID

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
        prompt_text = (base_dir / "agents" / "sql_transform" / "prompt.md").read_text(encoding='utf-8')

        rules_path = base_dir / "reference" / "oracle_to_postgresql_rules.md"
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
        tools=[get_pending_transforms, read_sql_source, convert_sql, lookup_column_type, split_mapper]
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
    
    # Progress log for console display
    progress_log = LOGS_DIR / "transform_progress.log"

    def log(msg):
        timestamp = time.strftime('%H:%M:%S')
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {msg}\n")
    
    def console(sql_id, status):
        """Print real-time status with progress: [progress%] [MapperName] sqlId - status"""
        with progress_counter['lock']:
            if status == "🔄 변환중":
                progress_counter['started'] += 1
            elif status in ["✅ 완료", "✅ PASS", "✅ FIXED"]:
                progress_counter['done'] += 1
            current = progress_counter['started']
            pct = int(current * 100 / total) if total > 0 else 0
            msg = f"[{pct:3d}%] [{Path(mapper_file).stem}] {sql_id} - {status}"
            # Write to progress log instead of stderr
            with open(progress_log, 'a', encoding='utf-8') as f:
                f.write(f"{msg}\n")

    try:
        log(f"🚀 시작: {len(sql_ids)} SQL IDs")
        groups = _group_by_file_size(sql_ids)
        
        for g_num, group in enumerate(groups, 1):
            ids_str = ", ".join(s['sql_id'] for s in group)
            total_kb = sum(Path(s.get('source_file', '')).stat().st_size for s in group if Path(s.get('source_file', '')).exists()) // 1024
            log(f"📦 Group {g_num}/{len(groups)}: {len(group)} SQLs (~{total_kb}KB)")
            log(f"   SQL IDs: {ids_str}")
            
            # Show each SQL ID starting
            for s in group:
                console(s['sql_id'], "🔄 변환중")

            # Clear signal file before agent run
            signal_file = PROJECT_ROOT / "output" / "logs" / ".transform_signals"
            signal_file.parent.mkdir(parents=True, exist_ok=True)
            if signal_file.exists():
                signal_file.unlink()

            old_stdout = sys.stdout
            old_stderr = sys.stderr
            buf = io.StringIO()
            sys.stdout = buf
            sys.stderr = buf
            agent = create_agent()
            agent(
                f"{mapper_file}의 다음 SQL ID들을 PostgreSQL로 변환해줘: {ids_str}\n"
                f"각 SQL ID마다 read_sql_source로 원본을 읽고, 변환 후 convert_sql로 저장해줘."
            )
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            
            # Read completion signals from convert_sql tool
            if signal_file.exists():
                for line in signal_file.read_text(encoding='utf-8').strip().split('\n'):
                    if not line:
                        continue
                    parts = line.split('|', 2)
                    if len(parts) >= 2:
                        sig_mapper, sig_sql_id = parts[0], parts[1]
                        sig_notes = parts[2] if len(parts) > 2 else ""
                        for s in group:
                            if s['sql_id'] == sig_sql_id:
                                reason = sig_notes.strip()[:60] if sig_notes.strip() else ""
                                console(s['sql_id'], f"✅ 완료 - {reason}" if reason else "✅ 완료")
                                break
                signal_file.unlink(missing_ok=True)
            
            # Log agent output (errors only)
            agent_output = buf.getvalue().strip()
            for line in agent_output.split('\n'):
                line = line.strip()
                if line and '❌' in line:
                    log(line)

        log(f"✅ {mapper_file} 변환 완료")
        return {'mapper': mapper_file, 'status': 'success', 'count': len(sql_ids)}
    except Exception as e:
        log(f"❌ {mapper_file}: {e}")
        console("ERROR", f"❌ {str(e)}")
        return {'mapper': mapper_file, 'status': 'error', 'error': str(e)}


def run(max_workers=8):
    print("🚀 SQL Transform Agent 시작...\n", flush=True)

    # 1. 전처리 (extract 파일이 없으면 실행)
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='transform_target_list'")
    table_exists = cursor.fetchone()
    conn.close()
    
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
    pending = get_pending_transforms()
    if pending['total'] == 0:
        print("✅ 모든 SQL이 이미 변환 완료!", flush=True)
        save_conversion_report()
        return

    mapper_list = list(pending['pending'].items())
    print(f"🔄 Pending: {pending['total']} SQL IDs across {len(mapper_list)} mappers (workers={max_workers})", flush=True)
    print(f"📁 Logs: {_log_dir}/\n", flush=True)

    # Initialize progress log
    progress_log = LOGS_DIR / "transform_progress.log"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    progress_log.write_text('', encoding='utf-8')
    
    # Start tail monitor with original stderr
    original_stderr = sys.stderr
    def tail_progress_log(progress_log: Path, stop_event: threading.Event, stderr):
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
    
    stop_monitor = threading.Event()
    monitor = threading.Thread(target=tail_progress_log, args=(progress_log, stop_monitor, original_stderr), daemon=True)
    monitor.start()

    # 3. Parallel execution with progress tracking
    progress_counter = {'started': 0, 'done': 0, 'lock': threading.Lock()}
    total_sql_count = pending['total']
    
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(transform_mapper, m, s, progress_counter, total_sql_count): m for m, s in mapper_list}
        for future in as_completed(futures):
            results.append(future.result())

    stop_monitor.set()
    monitor.join(timeout=2)

    # 4. Generate report
    print(f"\n📊 Generating report...", flush=True)
    save_conversion_report()

    # 최종 완료 판단: DB 기준
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM transform_target_list")
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE transformed='Y'")
    done = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE transformed='N'")
    remaining = cursor.fetchone()[0]
    conn.close()

    # merge 파일 확인
    merge_dir = MERGE_DIR
    merge_count = len(list(merge_dir.rglob("*.xml"))) if merge_dir.exists() else 0

    print(f"\n{'='*60}", flush=True)
    print(f"📊 결과: {done}/{total} SQL IDs transformed", flush=True)
    print(f"📦 Merge: {merge_count} mapper files", flush=True)

    if remaining == 0 and merge_count > 0:
        print(f"✅ 전체 완료!", flush=True)
    else:
        if remaining > 0:
            print(f"⚠️  미완료: {remaining}개 SQL IDs (재실행하면 이어서 처리)", flush=True)
        if merge_count == 0:
            print(f"⚠️  Merge 파일 없음", flush=True)

    failed = [r for r in results if r['status'] != 'success']
    if failed:
        print(f"❌ 실패 mappers:", flush=True)
        for r in failed:
            print(f"   - {r['mapper']}: {r.get('error', 'unknown')}", flush=True)

    print(f"📁 Logs: {_log_dir}/", flush=True)
    print(f"{'='*60}", flush=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--reset', action='store_true', help='전체 초기화 후 재실행')
    args = parser.parse_args()

    if args.reset:
        import shutil
        print("🗑️  Reset: DB + output 초기화...", flush=True)
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("DROP TABLE IF EXISTS transform_target_list")
        conn.commit()
        conn.close()
        output_dir = OUTPUT_DIR
        if output_dir.exists():
            shutil.rmtree(output_dir)
        print("✅ 초기화 완료\n", flush=True)

    run(max_workers=args.workers)
