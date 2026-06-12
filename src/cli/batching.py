"""Adaptive batching: mapper 단위 기본, 大 mapper는 분할."""

MAX_BATCH_SQLS = 15


def make_batches(rows: list[dict], max_batch: int = MAX_BATCH_SQLS) -> list[dict]:
    """rows: [{mapper_file, sql_id, sql_type, seq_no}] (mapper_file, seq_no 정렬 가정)

    Returns: [{mapper_file, part, parts, sql_ids: [...]}]
    part/parts는 분할 시 1-based 인덱스와 총 분할 수 (미분할이면 1/1).
    """
    by_mapper: dict[str, list[str]] = {}
    for r in rows:
        by_mapper.setdefault(r["mapper_file"], []).append(r["sql_id"])

    batches = []
    for mapper, sql_ids in by_mapper.items():
        chunks = [sql_ids[i:i + max_batch] for i in range(0, len(sql_ids), max_batch)]
        for idx, chunk in enumerate(chunks, 1):
            batches.append({
                "mapper_file": mapper,
                "part": idx,
                "parts": len(chunks),
                "sql_ids": chunk,
            })
    return batches
