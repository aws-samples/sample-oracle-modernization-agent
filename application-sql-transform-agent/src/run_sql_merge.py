"""Merge transformed SQL files back into Mapper XMLs.
No LLM needed - pure Python file operation.
Only merges mappers where all SQL IDs are completed (tested='Y' or transformed='Y').
"""
import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from utils.project_paths import PROJECT_ROOT, DB_PATH, MERGE_DIR
from agents.sql_transform.tools.assemble_mapper import assemble_mapper


def run():
    print("📦 SQL Merge 시작...\n", flush=True)

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Mapper별 상태 확인
    cursor.execute("""
        SELECT mapper_file,
               COUNT(*) as total,
               SUM(CASE WHEN transformed='Y' THEN 1 ELSE 0 END) as transformed
        FROM transform_target_list
        GROUP BY mapper_file ORDER BY mapper_file
    """)
    mappers = cursor.fetchall()
    conn.close()

    if not mappers:
        print("⚠️  transform_target_list가 비어있습니다.", flush=True)
        return

    merged = 0
    skipped = 0

    for mapper_file, total, transformed in mappers:
        if transformed < total:
            print(f"  ⏭️  {mapper_file}: {transformed}/{total} transformed - 스킵", flush=True)
            skipped += 1
            continue

        result = assemble_mapper(mapper_file)
        if result.get('error'):
            print(f"  ❌ {mapper_file}: {result['error']}", flush=True)
        else:
            print(f"  📦 {mapper_file}: {result['success']}/{result['total']} SQLs merged", flush=True)
            merged += 1

    # 결과
    merge_dir = MERGE_DIR
    merge_count = len(list(merge_dir.rglob("*.xml"))) if merge_dir.exists() else 0

    print(f"\n{'='*60}", flush=True)
    print(f"📦 Merged: {merged} mappers ({merge_count} files)", flush=True)
    if skipped:
        print(f"⏭️  Skipped: {skipped} mappers (변환 미완료)", flush=True)
    print(f"📁 Output: {merge_dir}/", flush=True)
    print(f"{'='*60}", flush=True)


if __name__ == "__main__":
    run()
