"""Split Mapper XML into individual SQL IDs.

Core XML parsing logic adapted from xmlExtractor.py (oma-origin).
Outputs:
  - output/origin/{sub_dir}/MapperName.xml (원본 복사)
  - output/extract/{sub_dir}/MapperName-01-select-sqlId.xml (분리 파일)
  - DB: transform_target_list (source_file=extract/, target_file=transform/)
"""
import re
import shutil
import sqlite3
from pathlib import Path
from strands import tool
from utils.project_paths import PROJECT_ROOT, DB_PATH, ORIGIN_DIR, EXTRACT_DIR, TRANSFORM_DIR


def _extract_level1_elements(xml_content: str):
    """Extract all Level1 elements from mapper content.
    Adapted from xmlExtractor.extract_level1_elements() - proven logic.
    """
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


def _init_table(conn):
    """Create transform_target_list table with complete schema (all 20 columns)"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transform_target_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mapper_file TEXT NOT NULL,
            sql_id TEXT NOT NULL,
            sql_type TEXT NOT NULL,
            seq_no INTEGER NOT NULL,
            namespace TEXT,
            source_file TEXT NOT NULL,
            target_file TEXT,
            transformed TEXT DEFAULT 'N',
            validated TEXT DEFAULT 'N',
            tested TEXT DEFAULT 'N',
            completed TEXT DEFAULT 'N',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed TEXT DEFAULT 'N',
            review_notes TEXT,
            transform_count INTEGER,
            review_result TEXT,
            validation_result TEXT,
            test_result TEXT
        )
    """)
    conn.commit()


def _get_sub_dir(cursor, file_path: str) -> str:
    cursor.execute("SELECT relative_path FROM source_xml_list WHERE file_path = ?", (file_path,))
    row = cursor.fetchone()
    relative_path = row[0] if row else ''
    return str(Path(relative_path).parent) if relative_path else ''


@tool
def split_mapper(file_path: str) -> dict:
    """Split a MyBatis Mapper XML into individual SQL IDs.

    Creates:
      - output/origin/{sub_dir}/Mapper.xml (원본 복사)
      - output/extract/{sub_dir}/Mapper-01-type-sqlId.xml (분리 파일)
      - DB records with source_file=extract path, target_file=transform path

    Args:
        file_path: Full path to the mapper XML file
    """
    path = Path(file_path)
    if not path.exists():
        return {'error': f'File not found: {file_path}', 'sql_ids': []}

    content = path.read_text(encoding='utf-8')
    elements, namespace, xml_header, xml_doctype = _extract_level1_elements(content)

    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        cursor = conn.cursor()
        sub_dir = _get_sub_dir(cursor, str(path))

        _init_table(conn)
        cursor.execute("DELETE FROM transform_target_list WHERE mapper_file = ?", (path.name,))

        # 1. Copy original to output/origin/
        origin_dir = ORIGIN_DIR / sub_dir if sub_dir else ORIGIN_DIR
        origin_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(path), str(origin_dir / path.name))

        # 2. Extract each SQL ID to output/extract/
        sql_ids = []
        for seq, elem in enumerate(elements, 1):
            body_match = re.search(r'>(.+)</', elem['full_tag'], re.DOTALL)
            sql_body = body_match.group(1).strip() if body_match else ''

            file_name = f"{path.stem}-{seq:02d}-{elem['type']}-{elem['id']}.xml"
            extract_file = str(EXTRACT_DIR / sub_dir / file_name) if sub_dir else str(EXTRACT_DIR / file_name)
            target_file = str(TRANSFORM_DIR / sub_dir / file_name) if sub_dir else str(TRANSFORM_DIR / file_name)

            # Write extract file
            extract_path = Path(extract_file)
            extract_path.parent.mkdir(parents=True, exist_ok=True)
            comment = f"\n{elem['preceding_comment']}" if elem['preceding_comment'] else ""
            extract_path.write_text(
                f"{xml_header}\n<mapper namespace=\"{namespace}\">\n{comment}\n{elem['full_tag']}\n</mapper>\n",
                encoding='utf-8'
            )

            cursor.execute("""
                INSERT INTO transform_target_list
                (mapper_file, sql_id, sql_type, seq_no, namespace, source_file, target_file,
                 transformed, reviewed, validated, tested, completed)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'N', 'N', 'N', 'N', 'N')
            """, (path.name, elem['id'], elem['type'], seq, namespace, extract_file, target_file))

            sql_ids.append({
                'id': elem['id'], 'type': elem['type'], 'seq_no': seq,
                'sql': sql_body, 'full_tag': elem['full_tag'],
                'preceding_comment': elem['preceding_comment'],
                'line_count': elem['line_count'], 'target_file': target_file
            })

        conn.commit()
    finally:
        conn.close()

    print(f"✂️  Split {path.name}: {len(sql_ids)} SQL IDs → origin/ + extract/ + DB")
    return {
        'mapper': path.name, 'namespace': namespace,
        'xml_header': xml_header, 'xml_doctype': xml_doctype, 'sql_ids': sql_ids
    }
