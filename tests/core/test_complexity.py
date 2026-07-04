"""Tests for core.complexity — Oracle pattern detection and scoring."""
import pytest
from unittest.mock import MagicMock

from core.complexity import (
    ORACLE_PATTERNS, _calculate_complexity, _get_complexity_level, _get_distribution,
)


def _mock_elem(if_count=0, choose_count=0, foreach_count=0,
               where_count=0, set_count=0):
    """Create a mock XML element with findall returning the given counts."""
    elem = MagicMock()
    def findall(xpath):
        tag = xpath.split('//')[-1]
        counts = {'if': if_count, 'choose': choose_count,
                  'foreach': foreach_count, 'where': where_count, 'set': set_count}
        return [None] * counts.get(tag, 0)
    elem.findall = findall
    return elem


# ── Pattern detection ──

@pytest.mark.parametrize("name,sql", [
    ("NVL()", "SELECT NVL(col, 0) FROM t"),
    ("NVL2()", "SELECT NVL2(col, 'Y', 'N') FROM t"),
    ("DECODE()", "SELECT DECODE(status, 1, 'A', 'B') FROM t"),
    ("TO_DATE()", "SELECT TO_DATE('2024-01-01', 'YYYY-MM-DD') FROM dual"),
    ("LISTAGG()", "SELECT LISTAGG(name, ',') WITHIN GROUP (ORDER BY id) FROM t"),
    ("SYSDATE", "SELECT SYSDATE FROM dual"),
    ("FROM DUAL", "SELECT 1 FROM DUAL"),
    ("ROWNUM", "SELECT * FROM t WHERE ROWNUM <= 10"),
    ("(+) Outer Join", "SELECT * FROM a, b WHERE a.id = b.id(+)"),
    ("CONNECT BY", "SELECT * FROM t CONNECT BY PRIOR id = parent_id"),
    ("MERGE INTO", "MERGE INTO target t USING source s ON (t.id = s.id)"),
    (".NEXTVAL", "INSERT INTO t (id) VALUES (seq.NEXTVAL)"),
])
def test_pattern_detected(name, sql):
    """Each Oracle pattern is detected in its representative SQL."""
    elem = _mock_elem()
    score, patterns = _calculate_complexity(sql, elem)
    assert name in patterns, f"Expected '{name}' in patterns, got {patterns}"
    assert patterns[name] >= 1


def test_simple_select_low_score():
    """A trivial SELECT scores low (Simple)."""
    sql = "SELECT id, name FROM users WHERE id = 1"
    elem = _mock_elem()
    score, patterns = _calculate_complexity(sql, elem)
    assert score <= 3
    assert _get_complexity_level(score) == 'Simple'


def test_complex_query_high_score():
    """A query with CONNECT BY + subqueries + Oracle functions scores high."""
    sql = """
    SELECT NVL(a.name, 'UNKNOWN'), DECODE(a.status, 1, 'A', 2, 'B', 'C'),
           LISTAGG(b.tag, ',') WITHIN GROUP (ORDER BY b.seq)
    FROM emp a, dept b
    WHERE a.dept_id = b.id(+)
    START WITH a.mgr_id IS NULL
    CONNECT BY PRIOR a.id = a.mgr_id
    GROUP BY a.name, a.status
    HAVING COUNT(*) > 1
    ORDER BY a.name
    """
    elem = _mock_elem(if_count=2, choose_count=1)
    score, patterns = _calculate_complexity(sql, elem)
    assert score > 12
    assert _get_complexity_level(score) == 'Very Complex'
    assert 'CONNECT BY' in patterns
    assert 'NVL()' in patterns
    assert 'DECODE()' in patterns
    assert 'LISTAGG()' in patterns
    assert '(+) Outer Join' in patterns


def test_merge_into_complex():
    """MERGE INTO scores at least 3 + base."""
    sql = "MERGE INTO target t USING source s ON (t.id = s.id) WHEN MATCHED THEN UPDATE SET t.x = s.x"
    elem = _mock_elem()
    score, patterns = _calculate_complexity(sql, elem)
    assert 'MERGE INTO' in patterns
    assert score >= 4  # 1 base + 3 weight


def test_dynamic_tags_add_to_score():
    """MyBatis dynamic tags contribute to complexity."""
    sql = "SELECT * FROM t"
    elem = _mock_elem(if_count=5, foreach_count=2, choose_count=1)
    score, _ = _calculate_complexity(sql, elem)
    # 1 base + 5*1(if) + 2*2(foreach) + 1*2(choose) = 1+5+4+2 = 12
    assert score >= 12


def test_subqueries_add_to_score():
    """Subqueries (extra SELECTs) add 3 points each."""
    sql = "SELECT * FROM (SELECT id FROM (SELECT id FROM t))"
    elem = _mock_elem()
    score, _ = _calculate_complexity(sql, elem)
    # 2 extra SELECTs * 3 = 6 + 1 base = 7
    assert score >= 7


# ── Complexity level mapping ──

def test_complexity_levels():
    assert _get_complexity_level(1) == 'Simple'
    assert _get_complexity_level(3) == 'Simple'
    assert _get_complexity_level(4) == 'Medium'
    assert _get_complexity_level(7) == 'Medium'
    assert _get_complexity_level(8) == 'Complex'
    assert _get_complexity_level(12) == 'Complex'
    assert _get_complexity_level(13) == 'Very Complex'
    assert _get_complexity_level(50) == 'Very Complex'


# ── Distribution ──

def test_get_distribution():
    scores = [1, 2, 5, 8, 13, 20]
    dist = _get_distribution(scores)
    assert dist['Simple'] == 2
    assert dist['Medium'] == 1
    assert dist['Complex'] == 1
    assert dist['Very Complex'] == 2


# ── Negative tests: patterns should NOT match unrelated SQL ──

def test_no_false_positive_nvl():
    """NVL pattern should not match INTERVAL or similar."""
    sql = "SELECT INTERVAL '1' DAY FROM t"
    elem = _mock_elem()
    _, patterns = _calculate_complexity(sql, elem)
    assert 'NVL()' not in patterns


def test_string_concat_detected():
    """|| operator is detected."""
    sql = "SELECT first_name || ' ' || last_name FROM users"
    elem = _mock_elem()
    _, patterns = _calculate_complexity(sql, elem)
    assert '|| (string concat)' in patterns
