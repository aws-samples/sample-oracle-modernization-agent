"""One-time migration: update mapper_file from filename-only to sub_dir/filename.

Usage:
    cd src && PYTHONPATH=. python migrate_mapper_key.py

This reads source_file paths to derive the sub_dir, then updates mapper_file
from "Mapper.xml" to "sub_dir/Mapper.xml" for duplicate filename resolution.
Safe to run multiple times — skips already-migrated records (containing '/').
"""
import sqlite3
import re
from pathlib import Path
from utils.project_paths import DB_PATH


def migrate():
    if not DB_PATH.exists():
        print(f"❌ DB not found: {DB_PATH}")
        return

    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()

        # Get all records
        cursor.execute("SELECT id, mapper_file, source_file FROM transform_target_list")
        rows = cursor.fetchall()

        updated = 0
        skipped = 0
        for record_id, mapper_file, source_file in rows:
            # Skip if already migrated (contains '/')
            if '/' in mapper_file:
                skipped += 1
                continue

            if not source_file:
                continue

            # Extract sub_dir from source_file path
            # source_file: .../extract/{sub_dir}/MapperName-01-type-sqlId.xml
            # We need to find the part between 'extract/' and the filename
            match = re.search(r'/extract/(.+)/[^/]+$', source_file)
            if match:
                sub_dir = match.group(1)
                new_mapper_file = f"{sub_dir}/{mapper_file}"
            else:
                # No sub_dir (files directly in extract/)
                continue

            cursor.execute(
                "UPDATE transform_target_list SET mapper_file = ? WHERE id = ?",
                (new_mapper_file, record_id)
            )
            updated += 1

        conn.commit()

    print(f"✅ Migration complete: {updated} updated, {skipped} already migrated")


if __name__ == "__main__":
    migrate()
