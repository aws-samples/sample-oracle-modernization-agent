"""Strategy Agent Tools - SQL Pattern Analysis"""
import json
import sqlite3
import re
from pathlib import Path
from strands import tool

# Add parent to path for utils import
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from utils.project_paths import get_db_path, PROJECT_ROOT, REPORTS_DIR


@tool
def analyze_sql_patterns() -> str:
    """
    Analyze Oracle SQL patterns using Source Analysis report.
    
    Strategy:
    1. Read source_analysis.md for statistics
    2. Extract Top 10 complex SQLs (full content)
    3. Return to Agent for analysis
    
    Agent will determine:
    - Which patterns need project-specific strategy
    - Which patterns are covered by general rules
    
    Returns:
        JSON string with:
        - Statistics from source_analysis.md
        - Top 10 complex SQLs (full content for Agent analysis)
    """
    # Step 1: Read source_analysis.md
    analysis_report = REPORTS_DIR / "source_analysis.md"
    if not analysis_report.exists():
        return json.dumps({'error': 'source_analysis.md not found. Run analyze step first.'})
    
    report_content = analysis_report.read_text(encoding='utf-8')
    
    # Step 2: Extract statistics
    result = {
        'source': 'source_analysis.md',
        'statistics': _extract_statistics(report_content),
        'top_complex_sqls': []
    }
    
    # Step 3: Extract Top 10 complex SQLs (full content)
    top_complex = _extract_top_complex_sqls(report_content)
    result['top_complex_sqls'] = top_complex
    
    return json.dumps(result, ensure_ascii=False, indent=2)


def _extract_statistics(report_content: str) -> dict:
    """Extract statistics from source_analysis.md"""
    stats = {}
    
    # Extract total SQL count
    match = re.search(r'총 SQL 수[:\s]+(\d+)', report_content)
    if match:
        stats['total_sqls'] = int(match.group(1))
    
    # Extract complexity distribution
    complexity = {}
    for level in ['Simple', 'Medium', 'Complex', 'Very Complex']:
        match = re.search(rf'{level}[:\s]+(\d+)', report_content)
        if match:
            complexity[level.lower().replace(' ', '_')] = int(match.group(1))
    stats['complexity'] = complexity
    
    return stats


def _extract_top_complex_sqls(report_content: str) -> list:
    """
    Extract Top 10 complex SQLs from source_analysis.md report.
    Returns FULL SQL content for Agent to analyze.
    
    Note: Reads from original XML files (extract folder doesn't exist yet)
    """
    top_complex = []
    
    # Find "고복잡도 쿼리 Top 10" section
    match = re.search(r'고복잡도 쿼리 Top 10.*?(?=\n##|\Z)', report_content, re.DOTALL)
    if not match:
        return top_complex
    
    section = match.group(0)
    
    # Extract each SQL entry (format: ### N. [Mapper] - [SQL_ID])
    entries = re.findall(r'###\s+\d+\.\s+\[([^\]]+)\]\s+-\s+([^\n]+)', section)
    
    # Get Java source folder from DB
    db_path = get_db_path()
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM properties WHERE key = 'JAVA_SOURCE_FOLDER'")
        result = cursor.fetchone()
    
    if not result:
        return top_complex
    
    java_source = Path(result[0])
    
    for mapper, sql_id in entries[:10]:  # Top 10
        mapper_file = mapper.strip()
        sql_id_clean = sql_id.strip()
        
        # Find XML file in Java source
        xml_files = list(java_source.rglob(mapper_file))
        if not xml_files:
            top_complex.append({
                'rank': len(top_complex) + 1,
                'mapper': mapper_file,
                'sql_id': sql_id_clean,
                'sql_content': f"[XML file not found: {mapper_file}]"
            })
            continue
        
        xml_path = xml_files[0]
        
        # Extract SQL from XML
        sql_content = _extract_sql_from_xml(xml_path, sql_id_clean)
        
        top_complex.append({
            'rank': len(top_complex) + 1,
            'mapper': mapper_file,
            'sql_id': sql_id_clean,
            'sql_content': sql_content
        })
    
    return top_complex


def _extract_sql_from_xml(xml_path: Path, sql_id: str) -> str:
    """
    Extract SQL content from XML file by SQL ID.
    
    Searches for <select|insert|update|delete id="sql_id"> tag.
    """
    try:
        content = xml_path.read_text(encoding='utf-8')
    except Exception:
        return f"[Failed to read XML: {xml_path}]"
    
    # Find SQL tag with matching id
    # Pattern: <select|insert|update|delete id="sql_id" ...> ... </select|...>
    pattern = rf'<(select|insert|update|delete)\s+[^>]*id\s*=\s*["\']({re.escape(sql_id)})["\'][^>]*>(.*?)</\1>'
    
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    
    if match:
        sql_content = match.group(3).strip()
        return sql_content
    else:
        return f"[SQL ID '{sql_id}' not found in {xml_path.name}]"



