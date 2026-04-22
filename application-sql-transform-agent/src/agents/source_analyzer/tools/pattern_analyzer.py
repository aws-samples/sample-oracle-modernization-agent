"""Strategy Agent Tools - SQL Pattern Analysis (DB-based)"""
import json
import sqlite3
import sys
from pathlib import Path
from strands import tool

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from utils.project_paths import DB_PATH
from .sql_extractor import _calculate_complexity, _get_complexity_level, _get_distribution


@tool
def analyze_sql_patterns() -> str:
    """
    Analyze Oracle SQL patterns directly from extract_record table.

    Returns:
        JSON string with:
        - Statistics (total SQLs, complexity distribution)
        - Top 10 complex SQLs with full content for Agent analysis
    """
    if not DB_PATH.exists():
        return json.dumps({'error': f'DB not found: {DB_PATH}. Run analyze step first.'})

    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT mapper_file, sql_id, sql_type, original_sql
            FROM extract_record
            WHERE original_sql IS NOT NULL AND original_sql != ''
        """)
        rows = cursor.fetchall()

    if not rows:
        return json.dumps({'error': 'extract_record is empty. Run split_mapper first.'})

    scored = []
    for mapper_file, sql_id, sql_type, original_sql in rows:
        score, _patterns = _calculate_complexity(original_sql, _EmptyElem())
        scored.append({
            'mapper': mapper_file,
            'sql_id': sql_id,
            'sql_type': sql_type,
            'score': score,
            'level': _get_complexity_level(score),
            'sql_content': original_sql,
        })

    all_scores = [s['score'] for s in scored]
    distribution = _get_distribution(all_scores)

    top_complex = sorted(scored, key=lambda x: x['score'], reverse=True)[:10]
    top_complex_out = [
        {
            'rank': i + 1,
            'mapper': item['mapper'],
            'sql_id': item['sql_id'],
            'sql_type': item['sql_type'],
            'score': item['score'],
            'level': item['level'],
            'sql_content': item['sql_content'],
        }
        for i, item in enumerate(top_complex)
    ]

    result = {
        'source': 'extract_record',
        'statistics': {
            'total_sqls': len(rows),
            'complexity': {k.lower().replace(' ', '_'): v for k, v in distribution.items()},
        },
        'top_complex_sqls': top_complex_out,
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


class _EmptyElem:
    """Stub for _calculate_complexity which expects an XML element.

    We've already extracted raw SQL text, so MyBatis dynamic-tag counts
    are not available here — findall returns [].
    """
    def findall(self, _xpath):
        return []
