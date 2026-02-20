"""Run SQL Review Agent — check rule compliance, re-transform failures"""
import sys
import io
import sqlite3
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent))

from utils.project_paths import PROJECT_ROOT, DB_PATH, LOGS_DIR
from agents.sql_review.agent import create_sql_review_agent
from agents.sql_review.tools.review_tools import get_pending_reviews

_log_dir = LOGS_DIR / "review"


def _ensure_reviewed_column():
    """Add 'reviewed' column if not exists."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(transform_target_list)")
    cols = [r[1] for r in cursor.fetchall()]
    if 'reviewed' not in cols:
        conn.execute("ALTER TABLE transform_target_list ADD COLUMN reviewed TEXT DEFAULT 'N'")
        conn.commit()
    conn.close()


def _group_by_file_size(sql_ids: list, max_group_bytes=30000) -> list:
    """Group SQL IDs by estimated token size. Review reads both source + transform."""
    groups, current, size = [], [], 0
    for s in sql_ids:
        src = Path(s.get('source_file', ''))
        tgt = Path(s.get('target_file', ''))
        fs = 0
        if src.exists():
            fs += src.stat().st_size
        if tgt.exists():
            fs += tgt.stat().st_size
        else:
            fs += src.stat().st_size if src.exists() else 2000
        if current and size + fs > max_group_bytes:
            groups.append(current)
            current, size = [], 0
        current.append(s)
        size += fs
    if current:
        groups.append(current)
    return groups


def review_mapper(mapper_file: str, sql_ids: list, progress_counter: dict, total: int) -> dict:
    _log_dir.mkdir(parents=True, exist_ok=True)
    log_path = _log_dir / f"{Path(mapper_file).stem}.log"
    log_path.write_text('', encoding='utf-8')
    progress_log = _log_dir.parent / "review_progress.log"

    def log(msg):
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")

    def console(sql_id, status):
        with progress_counter['lock']:
            if status == "🔍 리뷰중":
                progress_counter['started'] += 1
            elif "✅" in status or "❌" in status:
                progress_counter['done'] += 1
            pct = int(progress_counter['started'] * 100 / total) if total > 0 else 0
            msg = f"[{pct:3d}%] [{Path(mapper_file).stem}] {sql_id} - {status}"
            with open(progress_log, 'a', encoding='utf-8') as f:
                f.write(f"{msg}\n")

    try:
        log(f"🔍 시작: {len(sql_ids)} SQL IDs")
        groups = _group_by_file_size(sql_ids)

        for g_num, group in enumerate(groups, 1):
            ids_str = ", ".join(s['sql_id'] for s in group)
            log(f"📦 Group {g_num}/{len(groups)}: {ids_str}")

            for s in group:
                console(s['sql_id'], "🔍 리뷰중")

            signal_file = PROJECT_ROOT / "output" / "logs" / ".review_signals"
            signal_file.parent.mkdir(parents=True, exist_ok=True)
            if signal_file.exists():
                signal_file.unlink()

            old_stdout, old_stderr = sys.stdout, sys.stderr
            buf = io.StringIO()
            sys.stdout = buf
            sys.stderr = buf
            try:
                agent = create_sql_review_agent()
                agent(
                    f"Review the following SQL IDs in {mapper_file}: {ids_str}\n"
                    f"For each: read_sql_source for original, read_transform for converted, "
                    f"check ALL General Rules compliance, then set_reviewed with PASS or FAIL."
                )
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr

            if signal_file.exists():
                for line in signal_file.read_text(encoding='utf-8').strip().split('\n'):
                    if not line:
                        continue
                    parts = line.split('|', 3)
                    if len(parts) >= 3:
                        sid, res = parts[1], parts[2]
                        notes = parts[3] if len(parts) > 3 else ""
                        for s in group:
                            if s['sql_id'] == sid:
                                if res == 'PASS':
                                    console(sid, "✅ PASS")
                                    log(f"  ✅ PASS {sid}")
                                else:
                                    console(sid, f"❌ FAIL - {notes[:60]}")
                                    log(f"  ❌ FAIL {sid}: {notes}")
                                break
                signal_file.unlink(missing_ok=True)

        log(f"✅ {mapper_file} 리뷰 완료")
        return {'mapper': mapper_file, 'status': 'success', 'count': len(sql_ids)}
    except Exception as e:
        log(f"❌ {mapper_file}: {e}")
        console("ERROR", f"❌ {str(e)}")
        return {'mapper': mapper_file, 'status': 'error', 'error': str(e)}


def _retransform_failures():
    """Re-transform SQL IDs that failed review."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT mapper_file, sql_id FROM transform_target_list
        WHERE reviewed = 'F'
    """)
    failures = cursor.fetchall()
    conn.close()

    if not failures:
        return 0

    print(f"\n🔄 Re-transforming {len(failures)} failed SQL IDs...", flush=True)

    from agents.sql_transform.agent import create_sql_transform_agent

    # Group by mapper
    by_mapper = {}
    for mapper, sql_id in failures:
        by_mapper.setdefault(mapper, []).append(sql_id)

    fixed = 0
    for mapper, sql_ids in by_mapper.items():
        ids_str = ", ".join(sql_ids)
        log_path = _log_dir / f"{Path(mapper).stem}.log"
        old_stdout, old_stderr = sys.stdout, sys.stderr
        buf = io.StringIO()
        sys.stdout = buf
        sys.stderr = buf
        try:
            agent = create_sql_transform_agent()
            agent(
                f"Re-transform the following SQL IDs in {mapper}: {ids_str}\n"
                f"These FAILED review due to rule violations. "
                f"Read each with read_sql_source, convert carefully applying ALL rules, save with convert_sql."
            )
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        # Log re-transform
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] 🔄 Re-transform: {ids_str}\n")

        # Reset reviewed flag for re-review
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        for sid in sql_ids:
            conn.execute(
                "UPDATE transform_target_list SET reviewed='N' WHERE mapper_file=? AND sql_id=?",
                (mapper, sid)
            )
        conn.commit()
        conn.close()
        fixed += len(sql_ids)
        print(f"  🔄 {mapper}: {len(sql_ids)} SQL IDs re-transformed", flush=True)

    return fixed


def _tail_progress_log(progress_log: Path, stop_event: threading.Event, stderr):
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


def run(max_workers=8, max_rounds=2):
    print("🔍 SQL Review Agent 시작...\n", flush=True)
    _ensure_reviewed_column()

    for round_num in range(1, max_rounds + 1):
        if round_num > 1:
            print(f"\n{'='*40} Round {round_num} {'='*40}", flush=True)

        pending = get_pending_reviews()
        if pending['total'] == 0:
            print("✅ 모든 SQL 리뷰 완료!", flush=True)
            break

        mapper_list = list(pending['pending'].items())
        print(f"📋 Pending: {pending['total']} SQL IDs across {len(mapper_list)} mappers (workers={max_workers})", flush=True)

        progress_log = _log_dir.parent / "review_progress.log"
        _log_dir.parent.mkdir(parents=True, exist_ok=True)
        progress_log.write_text('', encoding='utf-8')

        original_stderr = sys.stderr
        stop_monitor = threading.Event()
        monitor = threading.Thread(target=_tail_progress_log, args=(progress_log, stop_monitor, original_stderr), daemon=True)
        monitor.start()

        progress_counter = {'started': 0, 'done': 0, 'lock': threading.Lock()}

        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(review_mapper, m, s, progress_counter, pending['total']): m for m, s in mapper_list}
            for future in as_completed(futures):
                results.append(future.result())

        stop_monitor.set()
        monitor.join(timeout=2)

        # Check failures and re-transform
        retransformed = _retransform_failures()
        if retransformed == 0:
            break  # No failures, done

    # Final summary
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE reviewed='Y'")
    passed = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE reviewed='F'")
    failed = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE transformed='Y'")
    total = cursor.fetchone()[0]
    conn.close()

    print(f"\n{'='*60}", flush=True)
    print(f"📊 Review 결과: {passed} PASS / {failed} FAIL / {total} total", flush=True)
    if failed > 0:
        print(f"⚠️  {failed}개 SQL은 수동 검토 필요", flush=True)
    else:
        print(f"✅ 전체 리뷰 통과!", flush=True)
    print(f"📁 Logs: {_log_dir}/", flush=True)
    print(f"{'='*60}", flush=True)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--max-rounds', type=int, default=2, help='Max review-retransform rounds')
    parser.add_argument('--reset', action='store_true', help='Reset review status')
    args = parser.parse_args()

    if args.reset:
        _ensure_reviewed_column()
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        conn.execute("UPDATE transform_target_list SET reviewed='N' WHERE transformed='Y'")
        conn.commit()
        conn.close()
        print("🗑️  Review 상태 초기화 완료\n", flush=True)

    run(max_workers=args.workers, max_rounds=args.max_rounds)
