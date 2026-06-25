"""SQL complexity scoring and Oracle pattern detection (strands-free).

Ported from agents/source_analyzer/tools/sql_extractor.py.
Used by cli/analyzer.py for pattern analysis during the analyze step.
"""
from typing import Dict, List
import re

# Oracle patterns to detect (name, regex, complexity_weight, postgresql_equivalent)
ORACLE_PATTERNS = [
    # Functions
    ('NVL()', r'\bNVL\s*\(', 1, 'COALESCE()'),
    ('NVL2()', r'\bNVL2\s*\(', 2, 'CASE WHEN ... IS NOT NULL'),
    ('DECODE()', r'\bDECODE\s*\(', 1, 'CASE WHEN'),
    ('TO_DATE()', r'\bTO_DATE\s*\(', 1, 'TO_TIMESTAMP() / ::date'),
    ('TO_CHAR()', r'\bTO_CHAR\s*\(', 0, 'TO_CHAR() (compatible)'),
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
    ('FROM DUAL', r'\bFROM\s+DUAL\b', 1, 'remove'),
    ('ROWNUM', r'\bROWNUM\b', 1, 'LIMIT/OFFSET'),
    # Syntax
    ('|| (string concat)', r'\|\|', 1, 'CONCAT()'),
    ('(+) Outer Join', r'\(\+\)', 2, 'LEFT/RIGHT JOIN'),
    ('Comma JOIN', r'\bFROM\s+\w+\s+\w+\s*,\s*\w+', 1, 'Explicit JOIN'),
    ('Oracle Hint /*+', r'/\*\+', 1, 'remove'),
    ('.NEXTVAL', r'\.\s*NEXTVAL\b', 1, "nextval()"),
    ('.CURRVAL', r'\.\s*CURRVAL\b', 1, "currval()"),
    ('DB Link @', r'\w+@\w+', 1, 'remove'),
    # Advanced
    ('CONNECT BY', r'\bCONNECT\s+BY\b', 4, 'WITH RECURSIVE'),
    ('MERGE INTO', r'\bMERGE\s+INTO\b', 3, 'INSERT ... ON CONFLICT'),
    ('OVER()', r'\bOVER\s*\(', 2, 'Window Function (compatible)'),
]


def _calculate_complexity(sql_text: str, elem) -> tuple:
    """Calculate SQL complexity score and detect Oracle patterns.

    Args:
        sql_text: Raw SQL text content
        elem: XML element (used to count MyBatis dynamic tags)

    Returns:
        (score, pattern_counts_dict)
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
    """Get complexity level from score."""
    if score <= 3:
        return 'Simple'
    elif score <= 7:
        return 'Medium'
    elif score <= 12:
        return 'Complex'
    else:
        return 'Very Complex'


def _get_distribution(scores: List[int]) -> Dict:
    """Calculate complexity distribution."""
    distribution = {
        'Simple': 0,
        'Medium': 0,
        'Complex': 0,
        'Very Complex': 0,
    }

    for score in scores:
        level = _get_complexity_level(score)
        distribution[level] += 1

    return distribution
