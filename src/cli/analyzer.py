"""Deterministic analyze pipeline — scan/split/metadata/strategy-draft.

Ported from source_analyzer + split_mapper agent tools, minus @tool/strands deps.
This module is the single entry point: run_analyze(source_folder) -> summary dict.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import defusedxml.ElementTree as ET


# ---------------------------------------------------------------------------
# 1. scan_mybatis_mappers — from source_analyzer/tools/file_scanner.py
# ---------------------------------------------------------------------------

def scan_mybatis_mappers(source_folder: str) -> Dict:
    """Scan and identify MyBatis Mapper XML files under source_folder."""
    source_path = Path(source_folder)
    mappers: List[Dict] = []

    xml_files = list(source_path.rglob("*.xml"))

    for xml_file in xml_files:
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            if root.tag == "mapper" or "mapper" in root.tag:
                namespace = root.get("namespace", "Unknown")
                sql_count = len(root.findall(".//*[@id]"))
                mappers.append({
                    "path": str(xml_file),
                    "name": xml_file.name,
                    "relative": str(xml_file.relative_to(source_path)),
                    "namespace": namespace,
                    "sql_count": sql_count,
                })
        except Exception:
            continue

    return {
        "total": len(mappers),
        "valid": len([m for m in mappers if m["sql_count"] > 0]),
        "empty": len([m for m in mappers if m["sql_count"] == 0]),
        "mappers": mappers,
    }


# ---------------------------------------------------------------------------
# 2. save_xml_list — from source_analyzer/tools/db_manager.py
#    Adapted: accepts a list directly (not JSON string).
# ---------------------------------------------------------------------------

def save_xml_list(mappers: List[Dict]) -> str:
    """Save mapper list to source_xml_list table (drop & recreate)."""
    from utils.project_paths import DB_PATH

    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS source_xml_list")
        cursor.execute("""
            CREATE TABLE source_xml_list (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                file_name TEXT NOT NULL,
                relative_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for m in mappers:
            cursor.execute(
                "INSERT INTO source_xml_list (file_path, file_name, relative_path) VALUES (?,?,?)",
                (m["path"], m["name"], m["relative"]),
            )
        conn.commit()
    return f"Saved {len(mappers)} XML files to database"


# ---------------------------------------------------------------------------
# 3. split_mapper — from sql_transform/tools/split_mapper.py
#    Ported: removed @tool, strands imports; uses function-level project_paths.
#    history_writer usage preserved (non-fatal).
# ---------------------------------------------------------------------------

import re
import shutil


def _extract_level1_elements(xml_content: str):
    """Extract all Level1 elements from mapper content."""
    header_match = re.search(r'(<\?xml.*?\?>)', xml_content, re.DOTALL)
    doctype_match = re.search(r'(<!DOCTYPE.*?>)', xml_content, re.DOTALL)
    xml_header = header_match.group(1) if header_match else '<?xml version="1.0" encoding="UTF-8"?>'
    xml_doctype = doctype_match.group(1) if doctype_match else ''

    namespace_match = re.search(r'<mapper\s+namespace\s*=\s*["\']([^"\']+)["\']', xml_content)
    namespace = namespace_match.group(1) if namespace_match else ''

    mapper_start = re.search(r'<mapper\s+namespace\s*=\s*["\'][^"\']+["\'][^>]*>', xml_content)
    mapper_end = re.search(r'</mapper>\s*$', xml_content)

    if not mapper_start or not mapper_end:
        return [], namespace, xml_header, xml_doctype

    mapper_content = xml_content[mapper_start.end():mapper_end.start()]

    comments = []
    for m in re.finditer(r'<!--.*?-->', mapper_content, re.DOTALL):
        comments.append((m.start(), m.end(), m.group(0)))

    elements = []
    pos = 0
    while pos < len(mapper_content) and mapper_content[pos].isspace():
        pos += 1

    while pos < len(mapper_content):
        is_comment = False
        for cs, ce, ct in comments:
            if pos == cs:
                pos = ce
                is_comment = True
                while pos < len(mapper_content) and mapper_content[pos].isspace():
                    pos += 1
                break
        if is_comment:
            continue

        if pos >= len(mapper_content) or mapper_content[pos] != '<' or \
           (pos + 1 < len(mapper_content) and mapper_content[pos + 1] == '!'):
            pos += 1
            continue

        tag_end = mapper_content.find(' ', pos)
        if tag_end == -1:
            tag_end = mapper_content.find('>', pos)
        if tag_end == -1:
            pos += 1
            continue

        tag_name = mapper_content[pos + 1:tag_end]
        nesting = 1
        search_pos = tag_end

        while nesting > 0 and search_pos < len(mapper_content):
            open_match = mapper_content.find(f'<{tag_name}', search_pos)
            close_match = mapper_content.find(f'</{tag_name}>', search_pos)
            if close_match == -1:
                break
            if open_match != -1 and open_match < close_match:
                nesting += 1
                search_pos = open_match + len(tag_name) + 1
            else:
                nesting -= 1
                search_pos = close_match + len(tag_name) + 3

        if nesting == 0:
            element_content = mapper_content[pos:search_pos]
            preceding_comment = ""
            for cs, ce, ct in reversed(comments):
                if ce <= pos:
                    preceding_comment = ct
                    break
            id_match = re.search(r'id\s*=\s*["\']([^"\']+)["\']', element_content)
            element_id = id_match.group(1) if id_match else f"{tag_name}_{len(elements) + 1}"
            elements.append({
                'id': element_id, 'type': tag_name, 'full_tag': element_content,
                'preceding_comment': preceding_comment,
                'line_count': element_content.count('\n') + 1
            })
            pos = search_pos
        else:
            pos += 1

    return elements, namespace, xml_header, xml_doctype


def split_mapper(file_path: str) -> dict:
    """Split a MyBatis Mapper XML into individual SQL IDs.

    Creates:
      - output/origin/{sub_dir}/Mapper.xml (origin copy)
      - output/extract/{sub_dir}/Mapper-NN-type-sqlId.xml (per-SQL files)
      - DB records in transform_target_list
    """
    from utils.project_paths import DB_PATH, ORIGIN_DIR, EXTRACT_DIR, TRANSFORM_DIR

    path = Path(file_path)
    if not path.exists():
        return {'error': f'File not found: {file_path}', 'sql_ids': [], 'total': 0}

    content = path.read_text(encoding='utf-8')
    elements, namespace, xml_header, xml_doctype = _extract_level1_elements(content)

    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        cursor = conn.cursor()

        # Validate: only accept files registered in source_xml_list
        resolved = str(path.resolve())
        cursor.execute(
            "SELECT 1 FROM source_xml_list WHERE file_path IN (?, ?)",
            (resolved, str(path))
        )
        if not cursor.fetchone():
            return {
                'error': f'Not a registered source mapper: {file_path}',
                'sql_ids': [], 'total': 0
            }

        # Get sub_dir from source_xml_list
        cursor.execute("SELECT relative_path FROM source_xml_list WHERE file_path = ?", (str(path),))
        row = cursor.fetchone()
        relative_path = row[0] if row else ''
        sub_dir = str(Path(relative_path).parent) if relative_path else ''
        if sub_dir == '.':
            sub_dir = ''

        # Ensure transform_target_list table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transform_target_list (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mapper_file TEXT NOT NULL, sql_id TEXT NOT NULL,
                sql_type TEXT NOT NULL, seq_no INTEGER NOT NULL,
                namespace TEXT, source_file TEXT NOT NULL, target_file TEXT,
                transformed TEXT DEFAULT 'N', validated TEXT DEFAULT 'N',
                tested TEXT DEFAULT 'N', completed TEXT DEFAULT 'N',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed TEXT DEFAULT 'N', review_notes TEXT,
                transform_count INTEGER, review_result TEXT,
                validation_result TEXT, test_result TEXT, test_notes TEXT,
                current_step TEXT DEFAULT 'pending'
            )
        """)

        mapper_key = f"{sub_dir}/{path.name}" if sub_dir else path.name

        # Preserve existing status flags
        cursor.execute(
            "SELECT sql_id, transformed, reviewed, validated, tested, completed, "
            "review_result, validation_result, test_result, review_notes, transform_count "
            "FROM transform_target_list WHERE mapper_file IN (?, ?)",
            (mapper_key, path.name)
        )
        existing = {row[0]: row for row in cursor.fetchall()}
        cursor.execute("DELETE FROM transform_target_list WHERE mapper_file IN (?, ?)", (mapper_key, path.name))

        # 1. Copy original to origin/
        origin_dir = ORIGIN_DIR / sub_dir if sub_dir else ORIGIN_DIR
        origin_dir.mkdir(parents=True, exist_ok=True)
        dest = origin_dir / path.name
        if path.resolve() != dest.resolve():
            shutil.copy2(str(path), str(dest))

        # 2. Extract each SQL ID
        sql_ids = []
        for seq, elem in enumerate(elements, 1):
            file_name = f"{path.stem}-{seq:02d}-{elem['type']}-{elem['id']}.xml"
            extract_file = str(EXTRACT_DIR / sub_dir / file_name) if sub_dir else str(EXTRACT_DIR / file_name)
            target_file = str(TRANSFORM_DIR / sub_dir / file_name) if sub_dir else str(TRANSFORM_DIR / file_name)

            extract_path = Path(extract_file)
            extract_path.parent.mkdir(parents=True, exist_ok=True)
            comment = f"\n{elem['preceding_comment']}" if elem['preceding_comment'] else ""
            extract_path.write_text(
                f"{xml_header}\n<mapper namespace=\"{namespace}\">\n{comment}\n{elem['full_tag']}\n</mapper>\n",
                encoding='utf-8'
            )

            prev = existing.get(elem['id'])
            if prev:
                cursor.execute("""
                    INSERT INTO transform_target_list
                    (mapper_file, sql_id, sql_type, seq_no, namespace, source_file, target_file,
                     transformed, reviewed, validated, tested, completed,
                     review_result, validation_result, test_result, review_notes, transform_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (mapper_key, elem['id'], elem['type'], seq, namespace, extract_file, target_file,
                      prev[1], prev[2], prev[3], prev[4], prev[5],
                      prev[6], prev[7], prev[8], prev[9], prev[10]))
            else:
                cursor.execute("""
                    INSERT INTO transform_target_list
                    (mapper_file, sql_id, sql_type, seq_no, namespace, source_file, target_file,
                     transformed, reviewed, validated, tested, completed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'N', 'N', 'N', 'N', 'N')
                """, (mapper_key, elem['id'], elem['type'], seq, namespace, extract_file, target_file))

            sql_ids.append({
                'id': elem['id'], 'type': elem['type'], 'seq_no': seq,
                'line_count': elem['line_count'],
            })

            # history_writer record (non-fatal)
            try:
                from core import history_writer as _hw
                _hw.record_extract(
                    mapper_file=mapper_key,
                    sql_id=elem['id'],
                    sql_type=elem['type'],
                    namespace=namespace,
                    seq_no=seq,
                    original_sql=elem['full_tag'],
                    mapper_path=_hw.resolve_mapper_path(mapper_key, absolute_path=str(path)),
                    conn=conn,
                )
            except Exception:
                pass

        conn.commit()
    finally:
        conn.close()

    return {
        'mapper': mapper_key, 'namespace': namespace,
        'total': len(sql_ids), 'sql_ids': sql_ids
    }


# ---------------------------------------------------------------------------
# 4. generate_metadata — from sql_transform/tools/metadata.py
#    Non-fatal wrapper; skipped in test (no DB connection expected).
# ---------------------------------------------------------------------------

def generate_metadata() -> dict:
    """Extract target DB metadata. Non-fatal: returns status dict.

    Suppresses stdout from the original tool (it uses print for status messages).
    """
    import io
    import contextlib
    try:
        from agents.sql_transform.tools.metadata import generate_metadata as _gen
        with contextlib.redirect_stdout(io.StringIO()):
            return _gen()
    except Exception as e:
        return {'status': 'skipped', 'error': str(e), 'row_count': 0}


# ---------------------------------------------------------------------------
# 5. Pattern analysis + strategy draft — from source_analyzer/tools
#    pattern_analyzer returns JSON string; strategy_generator expects LLM.
#    We generate a deterministic strategy draft from pattern statistics.
# ---------------------------------------------------------------------------

def _analyze_patterns_from_db() -> dict:
    """Analyze SQL patterns from extract_record table. Returns parsed dict."""
    from utils.project_paths import DB_PATH

    if not DB_PATH.exists():
        return {}

    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        # Check if extract_record table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='extract_record'")
        if not cursor.fetchone():
            return {}
        cursor.execute("""
            SELECT mapper_file, sql_id, sql_type, original_sql
            FROM extract_record
            WHERE original_sql IS NOT NULL AND original_sql != ''
        """)
        rows = cursor.fetchall()

    if not rows:
        return {}

    # Import complexity helpers
    from agents.source_analyzer.tools.sql_extractor import (
        _calculate_complexity, _get_complexity_level, _get_distribution, ORACLE_PATTERNS
    )

    class _EmptyElem:
        def findall(self, _xpath):
            return []

    scored = []
    pattern_totals: Dict[str, int] = {}
    for mapper_file, sql_id, sql_type, original_sql in rows:
        score, patterns = _calculate_complexity(original_sql, _EmptyElem())
        scored.append({
            'mapper': mapper_file, 'sql_id': sql_id,
            'sql_type': sql_type, 'score': score,
            'level': _get_complexity_level(score),
        })
        for name, count in patterns.items():
            pattern_totals[name] = pattern_totals.get(name, 0) + count

    all_scores = [s['score'] for s in scored]
    distribution = _get_distribution(all_scores)
    top_complex = sorted(scored, key=lambda x: x['score'], reverse=True)[:10]

    return {
        'statistics': {
            'total_sqls': len(rows),
            'complexity': {k.lower().replace(' ', '_'): v for k, v in distribution.items()},
        },
        'top_complex_sqls': top_complex,
        'pattern_totals': dict(sorted(pattern_totals.items(), key=lambda x: x[1], reverse=True)),
    }


def _write_strategy_draft(patterns: dict) -> None:
    """Write a deterministic strategy draft from pattern statistics."""
    from utils.project_paths import STRATEGY_DIR

    STRATEGY_DIR.mkdir(parents=True, exist_ok=True)
    output_path = STRATEGY_DIR / "transform_strategy.md"

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    stats = patterns.get('statistics', {})
    total = stats.get('total_sqls', 0)
    complexity = stats.get('complexity', {})
    top_sqls = patterns.get('top_complex_sqls', [])
    pattern_totals = patterns.get('pattern_totals', {})

    lines = [
        f"# Transform Strategy (Draft)",
        f"",
        f"> Auto-generated: {timestamp}",
        f"> This is a statistics-based draft. Refine with domain-specific patterns after first transform round.",
        f"",
        f"## Summary",
        f"",
        f"- Total SQLs: {total}",
        f"- Complexity distribution: {json.dumps(complexity)}",
        f"",
        f"## Top Oracle Patterns",
        f"",
    ]

    if pattern_totals:
        lines.append("| Pattern | Count |")
        lines.append("|---------|-------|")
        for name, count in list(pattern_totals.items())[:15]:
            lines.append(f"| {name} | {count} |")
    else:
        lines.append("*(No Oracle patterns detected)*")

    lines.append("")
    lines.append("## Top Complex SQLs")
    lines.append("")

    if top_sqls:
        for i, item in enumerate(top_sqls[:10], 1):
            lines.append(f"{i}. **{item.get('mapper', '?')}** / `{item.get('sql_id', '?')}` "
                         f"(score={item.get('score', 0)}, type={item.get('sql_type', '?')})")
    else:
        lines.append("*(No complex SQLs found)*")

    lines.append("")
    lines.append("## Project-Specific Patterns")
    lines.append("")
    lines.append("*(To be filled after first transform/review round)*")
    lines.append("")

    output_path.write_text("\n".join(lines), encoding='utf-8')


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_analyze(source_folder: str) -> dict:
    """Scan -> save list -> split -> metadata -> strategy draft. Returns summary dict."""
    from core.db_migrate import ensure_schema
    ensure_schema()

    # 1. Scan
    scan = scan_mybatis_mappers(source_folder)
    mappers = scan.get("mappers", [])
    save_xml_list(mappers)

    # 2. Split each mapper
    total_sqls = 0
    for m in mappers:
        result = split_mapper(m["path"])
        total_sqls += result.get("total", 0)

    # 3. Metadata (non-fatal)
    meta = generate_metadata()

    # 4. Pattern analysis + strategy draft
    patterns = _analyze_patterns_from_db()
    _write_strategy_draft(patterns)

    return {
        "mappers": len(mappers),
        "sqls": total_sqls,
        "metadata": meta.get("status", "skipped"),
    }
