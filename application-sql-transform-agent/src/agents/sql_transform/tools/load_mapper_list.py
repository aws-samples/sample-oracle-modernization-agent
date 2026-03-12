"""Load mapper file list from database"""
import sqlite3
from pathlib import Path
from strands import tool
from utils.project_paths import DB_PATH


@tool
def load_mapper_list() -> dict:
    """Load mapper file list from source_xml_list table.

    Returns:
        Dict with mappers list containing file_path, file_name, relative_path
    """
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_path, file_name, relative_path FROM source_xml_list ORDER BY id")
        rows = cursor.fetchall()

    mappers = [{'file_path': r[0], 'file_name': r[1], 'relative_path': r[2]} for r in rows]
    print(f"📋 Loaded {len(mappers)} mapper files from DB")
    return {'total': len(mappers), 'mappers': mappers}


@tool
def get_pending_transforms(sample: int = 0) -> dict:
    """Get SQL IDs that have not been transformed yet (transformed='N').

    Args:
        sample: If > 0, return at most N items using representative sampling:
                1) one per sql_type (SELECT > INSERT > UPDATE > DELETE),
                2) remaining slots filled by mapper round-robin.

    Returns:
        Dict with pending list grouped by mapper_file
    """
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT mapper_file, sql_id, sql_type, seq_no, source_file, target_file
            FROM transform_target_list
            WHERE transformed = 'N'
            ORDER BY mapper_file, seq_no
        """)
        rows = cursor.fetchall()

    all_items = []
    for mapper, sql_id, sql_type, seq, source, target in rows:
        all_items.append({
            'mapper_file': mapper, 'sql_id': sql_id, 'sql_type': sql_type,
            'seq_no': seq, 'source_file': source, 'target_file': target
        })

    # Sample re-transform: if no pending items but sample requested,
    # pick N from ALL items and reset only those
    if sample > 0 and len(all_items) == 0:
        all_items = _pick_and_reset_sample(sample)

    if sample > 0 and len(all_items) > sample:
        all_items = _sample_representative(all_items, sample)

    pending = {}
    for item in all_items:
        mapper = item['mapper_file']
        if mapper not in pending:
            pending[mapper] = []
        pending[mapper].append({
            'sql_id': item['sql_id'], 'sql_type': item['sql_type'],
            'seq_no': item['seq_no'], 'source_file': item['source_file'],
            'target_file': item['target_file']
        })

    total = sum(len(v) for v in pending.values())
    label = f" (sample={sample})" if sample > 0 else ""
    print(f"📋 Pending transforms: {total} SQL IDs across {len(pending)} mappers{label}")
    return {'total': total, 'mappers_count': len(pending), 'pending': pending}


def _pick_and_reset_sample(n: int) -> list:
    """Pick N representative items from ALL SQLs and reset only those to transformed='N'."""
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT mapper_file, sql_id, sql_type, seq_no, source_file, target_file
            FROM transform_target_list
            ORDER BY mapper_file, seq_no
        """)
        rows = cursor.fetchall()

    all_items = [
        {'mapper_file': m, 'sql_id': sid, 'sql_type': st, 'seq_no': seq,
         'source_file': src, 'target_file': tgt}
        for m, sid, st, seq, src, tgt in rows
    ]

    sampled = _sample_representative(all_items, n)

    # Reset only sampled items (and their downstream: reviewed, validated, tested)
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        for item in sampled:
            conn.execute(
                "UPDATE transform_target_list SET transformed='N', reviewed='N', validated='N', tested='N' "
                "WHERE mapper_file=? AND sql_id=?",
                (item['mapper_file'], item['sql_id'])
            )
        conn.commit()

    print(f"🔄 Sample re-transform: reset {len(sampled)} SQL IDs for re-processing")
    return sampled


def _sample_representative(items: list, n: int) -> list:
    """Select N representative items: sql_type coverage first, then mapper round-robin."""
    selected = []
    used = set()

    # Phase 1: one per sql_type (priority order), spread across mappers
    type_priority = ['select', 'insert', 'update', 'delete']
    used_mappers_per_type = set()
    for sql_type in type_priority:
        if len(selected) >= n:
            break
        # Prefer a mapper not yet used in phase 1
        best = None
        for item in items:
            if item['sql_type'] == sql_type and id(item) not in used:
                if item['mapper_file'] not in used_mappers_per_type:
                    best = item
                    break
                if best is None:
                    best = item
        if best:
            selected.append(best)
            used.add(id(best))
            used_mappers_per_type.add(best['mapper_file'])

    # Phase 2: fill remaining slots by mapper round-robin
    if len(selected) < n:
        mappers = []
        mapper_queues = {}
        for item in items:
            if id(item) in used:
                continue
            m = item['mapper_file']
            if m not in mapper_queues:
                mapper_queues[m] = []
                mappers.append(m)
            mapper_queues[m].append(item)

        idx = 0
        while len(selected) < n and mapper_queues:
            mapper = mappers[idx % len(mappers)]
            if mapper_queues.get(mapper):
                selected.append(mapper_queues[mapper].pop(0))
            else:
                mappers.remove(mapper)
                if not mappers:
                    break
                idx = idx % len(mappers) if mappers else 0
                continue
            idx += 1

    return selected


@tool
def read_sql_source(mapper_file: str, sql_id: str) -> dict:
    """Read the extracted SQL source file for a given SQL ID.

    Args:
        mapper_file: Mapper file name (e.g. 'SellerMapper.xml')
        sql_id: SQL statement ID

    Returns:
        Dict with sql_id, sql_type, sql_body (original SQL content)
    """
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT source_file, sql_type FROM transform_target_list WHERE mapper_file = ? AND sql_id = ?",
            (mapper_file, sql_id)
        )
        row = cursor.fetchone()

    if not row:
        return {'error': f'Not found: {mapper_file}/{sql_id}'}

    source_file, sql_type = row
    path = Path(source_file)
    if not path.exists():
        return {'error': f'File not found: {source_file}'}

    content = path.read_text(encoding='utf-8')
    # Extract SQL body from between tags
    import re
    body_match = re.search(
        r'<(select|insert|update|delete|sql)\s+[^>]*id\s*=\s*["\'][^"\']+["\'][^>]*>(.*?)</\1>',
        content, re.DOTALL | re.IGNORECASE
    )
    sql_body = body_match.group(2).strip() if body_match else content

    return {'sql_id': sql_id, 'sql_type': sql_type, 'sql_body': sql_body}
