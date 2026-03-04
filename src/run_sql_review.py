"""Run SQL Review Agent — multi-perspective review + re-transform failures"""
import sys
import json
import sqlite3
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent))

from utils.project_paths import DB_PATH, LOGS_DIR
from agents.sql_review.perspectives import run_multi_perspective_review
from agents.sql_review.tools.review_tools import get_pending_reviews, set_reviewed

_log_dir = LOGS_DIR / "review"


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
            elif "✅" in status or "❌" in status or "⚠️" in status:
                progress_counter['done'] += 1
            pct = int(progress_counter['started'] * 100 / total) if total > 0 else 0
            msg = f"[{pct:3d}%] [{Path(mapper_file).stem}] {sql_id} - {status}"
            with open(progress_log, 'a', encoding='utf-8') as f:
                f.write(f"{msg}\n")

    try:
        log(f"🔍 시작: {len(sql_ids)} SQL IDs (multi-perspective review)")
        groups = _group_by_file_size(sql_ids)

        for g_num, group in enumerate(groups, 1):
            ids_str = ", ".join(s['sql_id'] for s in group)
            log(f"📦 Group {g_num}/{len(groups)}: {ids_str}")

            for s in group:
                console(s['sql_id'], "🔍 리뷰중")

            # Run multi-perspective review (Syntax + Equivalence in parallel)
            result = run_multi_perspective_review(mapper_file, ids_str)

            # Process results and update DB via set_reviewed
            for s in group:
                sid = s['sql_id']
                sql_result = result.get('per_sql', {}).get(sid, {})
                res = sql_result.get('result', 'FAIL')
                issues = sql_result.get('issues', [])
                feedback = sql_result.get('feedback', '')

                # Serialize issues — may contain severity dicts
                serialized_issues = []
                for issue in issues:
                    if isinstance(issue, dict):
                        serialized_issues.append(issue)
                    else:
                        serialized_issues.append(str(issue))

                feedback_json = json.dumps({
                    'result': res,
                    'issues': serialized_issues,
                    'feedback': feedback,
                }, ensure_ascii=False)

                # Build violations string for display
                issue_strs = []
                for issue in issues:
                    if isinstance(issue, dict):
                        sev = issue.get('severity', 'CRITICAL')
                        desc = issue.get('description', '')
                        issue_strs.append(f"[{sev}] {desc}")
                    else:
                        issue_strs.append(str(issue))

                set_reviewed(
                    mapper_file=mapper_file,
                    sql_id=sid,
                    result=res,
                    violations="; ".join(issue_strs) if issue_strs else "",
                    review_feedback=feedback_json,
                )

                if res == 'PASS':
                    console(sid, "✅ PASS")
                    log(f"  ✅ PASS {sid}")
                elif res == 'PASS_WITH_WARNINGS':
                    summary = "; ".join(issue_strs[:2]) if issue_strs else ""
                    console(sid, f"⚠️  PASS_WITH_WARNINGS - {summary[:80]}")
                    log(f"  ⚠️  PASS_WITH_WARNINGS {sid}: {summary}")
                else:
                    summary = "; ".join(issue_strs[:2]) if issue_strs else "review failed"
                    console(sid, f"❌ FAIL - {summary[:80]}")
                    log(f"  ❌ FAIL {sid}: {summary}")

        log(f"✅ {mapper_file} 리뷰 완료")
        return {'mapper': mapper_file, 'status': 'success', 'count': len(sql_ids)}
    except Exception as e:
        log(f"❌ {mapper_file}: {e}")
        console("ERROR", f"❌ {str(e)}")
        return {'mapper': mapper_file, 'status': 'error', 'error': str(e)}


def _retransform_failures():
    """Re-transform SQL IDs that failed review (FAIL only, not PASS_WITH_WARNINGS)."""
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT mapper_file, sql_id, review_result FROM transform_target_list
            WHERE reviewed = 'F'
        """)
        failures = cursor.fetchall()

    if not failures:
        return 0

    print(f"\n🔄 Re-transforming {len(failures)} failed SQL IDs with specific feedback...", flush=True)

    from agents.sql_transform.agent import create_sql_transform_agent

    by_mapper = {}
    for mapper, sql_id, review_result in failures:
        if mapper not in by_mapper:
            by_mapper[mapper] = []
        by_mapper[mapper].append({'sql_id': sql_id, 'review_result': review_result or ''})

    fixed = 0
    for mapper, sql_entries in by_mapper.items():
        ids_str = ", ".join(e['sql_id'] for e in sql_entries)
        log_path = _log_dir / f"{Path(mapper).stem}.log"

        feedback_lines = []
        for entry in sql_entries:
            sid = entry['sql_id']
            review_result = entry['review_result']
            if review_result:
                try:
                    parsed = json.loads(review_result)
                    issues = parsed.get('issues', [])
                    if issues:
                        for issue in issues:
                            if isinstance(issue, dict):
                                # Only include CRITICAL issues in re-transform feedback
                                if issue.get('severity') == 'CRITICAL':
                                    feedback_lines.append(f"  [{sid}] {issue.get('description', '')}")
                            else:
                                feedback_lines.append(f"  [{sid}] {issue}")
                    else:
                        feedback_lines.append(f"  [{sid}] Review failed (no specific issues recorded)")
                except (ValueError, TypeError):
                    feedback_lines.append(f"  [{sid}] {review_result}")
            else:
                feedback_lines.append(f"  [{sid}] Review failed (no feedback available)")

        feedback_text = "\n".join(feedback_lines)

        # Use callback_handler=None to suppress streaming output
        agent = create_sql_transform_agent()
        agent.callback_handler = None
        agent(
            f"Re-transform the following SQL IDs in {mapper}: {ids_str}\n"
            f"These FAILED review. Here are the SPECIFIC issues found:\n"
            f"{feedback_text}\n"
            f"For each: fix the listed issues, apply ALL rules, "
            f"read with read_sql_source, save with convert_sql."
        )

        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] 🔄 Re-transform: {ids_str}\n")
            f.write(f"  Feedback:\n{feedback_text}\n")

        # Reset reviewed flag for re-review
        with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
            for entry in sql_entries:
                conn.execute(
                    "UPDATE transform_target_list SET reviewed='N' WHERE mapper_file=? AND sql_id=?",
                    (mapper, entry['sql_id'])
                )
            conn.commit()
        fixed += len(sql_entries)
        print(f"  🔄 {mapper}: {len(sql_entries)} SQL IDs re-transformed", flush=True)

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

        # Check failures and re-transform (FAIL only, not PASS_WITH_WARNINGS)
        retransformed = _retransform_failures()
        if retransformed == 0:
            break

    # Final summary
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE reviewed='Y'")
        passed = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE reviewed='F'")
        failed = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM transform_target_list WHERE transformed='Y'")
        total = cursor.fetchone()[0]

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
        with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
            conn.execute("UPDATE transform_target_list SET reviewed='N' WHERE transformed='Y'")
            conn.commit()
        print("🗑️  Review 상태 초기화 완료\n", flush=True)

    run(max_workers=args.workers, max_rounds=args.max_rounds)
