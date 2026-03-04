"""SQL extraction and complexity analysis tool"""
from pathlib import Path
from typing import Dict, List
import re
import defusedxml.ElementTree as ET
from strands import tool

# Oracle patterns to detect (name, regex, complexity_weight, postgresql_equivalent)
ORACLE_PATTERNS = [
    # Functions
    ('NVL()', r'\bNVL\s*\(', 1, 'COALESCE()'),
    ('NVL2()', r'\bNVL2\s*\(', 2, 'CASE WHEN ... IS NOT NULL'),
    ('DECODE()', r'\bDECODE\s*\(', 1, 'CASE WHEN'),
    ('TO_DATE()', r'\bTO_DATE\s*\(', 1, 'TO_TIMESTAMP() / ::date'),
    ('TO_CHAR()', r'\bTO_CHAR\s*\(', 0, 'TO_CHAR() (호환)'),
    ('TO_NUMBER()', r'\bTO_NUMBER\s*\(', 1, 'CAST(... AS NUMERIC)'),
    ('SUBSTR()', r'\bSUBSTR\s*\(', 1, 'SUBSTRING()'),
    ('INSTR()', r'\bINSTR\s*\(', 1, 'POSITION(... IN ...)'),
    ('LISTAGG()', r'\bLISTAGG\s*\(', 2, 'STRING_AGG()'),
    ('TRUNC(date)', r'\bTRUNC\s*\(', 1, 'DATE_TRUNC()'),
    ('ADD_MONTHS()', r'\bADD_MONTHS\s*\(', 1, 'date + INTERVAL'),
    ('MONTHS_BETWEEN()', r'\bMONTHS_BETWEEN\s*\(', 2, 'EXTRACT(... FROM AGE(...))'),
    ('LPAD()', r'\bLPAD\s*\(', 0, 'LPAD(::text)'),
    ('SYS_GUID()', r'\bSYS_GUID\s*\(', 1, 'gen_random_uuid()'),
    # Keywords
    ('SYSDATE', r'\bSYSDATE\b', 1, 'CURRENT_TIMESTAMP'),
    ('SYSTIMESTAMP', r'\bSYSTIMESTAMP\b', 1, 'CURRENT_TIMESTAMP'),
    ('FROM DUAL', r'\bFROM\s+DUAL\b', 1, '제거'),
    ('ROWNUM', r'\bROWNUM\b', 1, 'LIMIT/OFFSET'),
    # Syntax
    ('|| (문자열 연결)', r'\|\|', 1, 'CONCAT()'),
    ('(+) Outer Join', r'\(\+\)', 2, 'LEFT/RIGHT JOIN'),
    ('Comma JOIN', r'\bFROM\s+\w+\s+\w+\s*,\s*\w+', 1, 'Explicit JOIN'),
    ('Oracle Hint /*+', r'/\*\+', 1, '제거'),
    ('.NEXTVAL', r'\.\s*NEXTVAL\b', 1, "nextval()"),
    ('.CURRVAL', r'\.\s*CURRVAL\b', 1, "currval()"),
    ('DB Link @', r'\w+@\w+', 1, '제거'),
    # Advanced
    ('CONNECT BY', r'\bCONNECT\s+BY\b', 4, 'WITH RECURSIVE'),
    ('MERGE INTO', r'\bMERGE\s+INTO\b', 3, 'INSERT ... ON CONFLICT'),
    ('OVER()', r'\bOVER\s*\(', 2, 'Window Function (호환)'),
]


@tool
def analyze_sql_complexity(mapper_files: list) -> dict:
    """Analyze SQL complexity and Oracle pattern usage for mapper files.
    
    Args:
        mapper_files: List of mapper dictionaries OR result dict from scan_mybatis_mappers.
    
    Returns:
        Dictionary with complexity analysis and Oracle pattern statistics
    """
    if isinstance(mapper_files, dict):
        if 'mappers' in mapper_files:
            mapper_files = mapper_files['mappers']
        else:
            return {'error': f"If dict is provided, it must have 'mappers' key. Got keys: {list(mapper_files.keys())}"}

    if not mapper_files:
        return _empty_result()
    if not isinstance(mapper_files, list):
        return {'error': f"mapper_files must be a list or dict, got {type(mapper_files)}"}
    if mapper_files and not isinstance(mapper_files[0], dict):
        return {'error': f"mapper_files items must be dictionaries, got {type(mapper_files[0])}"}
    if mapper_files and 'path' not in mapper_files[0]:
        return {'error': f"mapper_files items must have 'path' key, got keys: {list(mapper_files[0].keys())}"}
    
    complexity_scores = []
    complexity_details = []
    oracle_pattern_totals = {}
    
    for mapper in mapper_files:
        try:
            tree = ET.parse(mapper['path'])
            root = tree.getroot()
            
            for elem in root.findall('.//*[@id]'):
                sql_text = ET.tostring(elem, encoding='unicode', method='text')
                score, patterns = _calculate_complexity(sql_text, elem)
                level = _get_complexity_level(score)
                
                complexity_scores.append(score)
                complexity_details.append({
                    'file': mapper.get('name', 'Unknown'),
                    'id': elem.get('id'),
                    'type': elem.tag,
                    'score': score,
                    'level': level
                })
                
                for name, count in patterns.items():
                    oracle_pattern_totals[name] = oracle_pattern_totals.get(name, 0) + count
        except Exception as e:
            print(f"Warning: Failed to analyze {mapper.get('name', 'unknown')}: {e}")
            continue
    
    if not complexity_scores:
        return _empty_result()
    
    # Build sorted oracle_patterns list
    pattern_pg_map = {p[0]: p[3] for p in ORACLE_PATTERNS}
    total_patterns = sum(oracle_pattern_totals.values())
    oracle_patterns = []
    for name, count in sorted(oracle_pattern_totals.items(), key=lambda x: x[1], reverse=True):
        oracle_patterns.append({
            'pattern': name,
            'count': count,
            'percentage': round(count / total_patterns * 100, 1) if total_patterns > 0 else 0,
            'postgresql': pattern_pg_map.get(name, '')
        })
    
    all_scores = sorted(complexity_scores, reverse=True)
    return {
        'average': sum(complexity_scores) / len(complexity_scores),
        'max': max(complexity_scores),
        'min': min(complexity_scores),
        'total_queries': len(complexity_scores),
        'all_scores': all_scores,
        'details': sorted(complexity_details, key=lambda x: x['score'], reverse=True)[:20],
        'distribution': _get_distribution(complexity_scores),
        'oracle_patterns': oracle_patterns,
        'oracle_pattern_total': total_patterns
    }


def _empty_result() -> dict:
    return {
        'average': 0, 'max': 0, 'min': 0, 'total_queries': 0,
        'details': [],
        'distribution': {'Simple': 0, 'Medium': 0, 'Complex': 0, 'Very Complex': 0},
        'oracle_patterns': [],
        'oracle_pattern_total': 0
    }


def _calculate_complexity(sql_text: str, elem) -> tuple:
    """Calculate SQL complexity score and detect Oracle patterns.
    Returns: (score, pattern_counts_dict)
    """
    score = 1
    sql_upper = sql_text.upper()
    pattern_counts = {}
    
    # Detect Oracle patterns
    for name, regex, weight, _ in ORACLE_PATTERNS:
        count = len(re.findall(regex, sql_upper if name != 'DB Link @' else sql_text))
        if count > 0:
            pattern_counts[name] = count
            score += count * weight
    
    # Subqueries
    sub_count = max(0, sql_upper.count('SELECT') - 1)
    if sub_count > 0:
        score += sub_count * 3
    
    # Dynamic SQL (MyBatis)
    score += len(elem.findall('.//if'))
    score += len(elem.findall('.//choose')) * 2
    score += len(elem.findall('.//foreach')) * 2
    score += len(elem.findall('.//where'))
    score += len(elem.findall('.//set'))
    
    # UNION
    score += sql_upper.count('UNION') * 2
    
    # Aggregation
    for kw in ['GROUP BY', 'HAVING', 'ORDER BY']:
        if kw in sql_upper:
            score += 1
    
    # CASE WHEN
    score += sql_upper.count('CASE')
    
    return score, pattern_counts


def _get_complexity_level(score: int) -> str:
    """Get complexity level from score"""
    if score <= 3:
        return 'Simple'
    elif score <= 7:
        return 'Medium'
    elif score <= 12:
        return 'Complex'
    else:
        return 'Very Complex'


def _get_distribution(scores: List[int]) -> Dict:
    """Calculate complexity distribution"""
    distribution = {
        'Simple': 0,
        'Medium': 0,
        'Complex': 0,
        'Very Complex': 0
    }
    
    for score in scores:
        level = _get_complexity_level(score)
        distribution[level] += 1
    
    return distribution
