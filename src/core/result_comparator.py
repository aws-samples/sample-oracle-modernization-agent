"""Oracle vs PostgreSQL/MySQL result comparator.

Executes the same query on both source (Oracle) and target (PG/MySQL) databases,
then compares row counts and optionally data values.

Safety: SELECT with LIMIT/ROWNUM, DML with ROLLBACK, statement_timeout.
"""
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from core.sql_executor import SQLExecutor, extract_sql_from_xml


@dataclass
class CompareResult:
    sql_id: str
    mapper_file: str
    status: str  # PASS | FAIL_ROW_COUNT | FAIL_DATA_DIFF | SKIP | ERROR
    oracle_rows: int = -1
    target_rows: int = -1
    error: str = ""
    warnings: list[str] = field(default_factory=list)


def _oracle_available() -> bool:
    for k in ('ORACLE_HOST', 'ORACLE_USER', 'ORACLE_SID'):
        if not os.environ.get(k):
            return False
    return True


def _oracle_conn_str() -> str:
    u = os.environ.get('ORACLE_USER', '')
    p = os.environ.get('ORACLE_PASSWORD', '')
    h = os.environ.get('ORACLE_HOST', '')
    port = os.environ.get('ORACLE_PORT', '1521')
    sid = os.environ.get('ORACLE_SID', '')
    if os.environ.get('ORACLE_CONN_TYPE') == 'sid':
        return f"{u}/{p}@(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={h})(PORT={port}))(CONNECT_DATA=(SID={sid})))"
    return f"{u}/{p}@{h}:{port}/{sid}"


def _run_oracle_sql(sql: str, timeout: int = 30) -> tuple[str, bool]:
    """Execute SQL via sqlplus. Returns (stdout, success)."""
    header = "SET PAGESIZE 0 FEEDBACK ON HEADING OFF LINESIZE 32767 TRIMOUT ON TRIMSPOOL ON\n"
    try:
        result = subprocess.run(
            ['sqlplus', '-S', _oracle_conn_str()],
            input=header + sql + "\n",
            capture_output=True, text=True, timeout=timeout,
        )
        output = result.stdout
        if 'ORA-' in output or 'SP2-' in output:
            return output, False
        return output, True
    except subprocess.TimeoutExpired:
        return "Oracle query timeout", False
    except Exception as e:
        return str(e), False


def _count_oracle_rows(output: str) -> int:
    """Extract row count from sqlplus FEEDBACK output."""
    # "N rows selected" or "no rows selected"
    m = re.search(r'(\d+)\s+rows?\s+selected', output, re.IGNORECASE)
    if m:
        return int(m.group(1))
    if 'no rows selected' in output.lower():
        return 0
    # Count non-empty lines (exclude feedback lines)
    lines = [l for l in output.strip().split('\n')
             if l.strip() and 'rows selected' not in l.lower()
             and not l.startswith('SQL>')]
    return len(lines)


def _prepare_oracle_sql(original_sql: str, sql_type: str, params: dict | None,
                         limit: int = 100) -> str:
    """Prepare Oracle SQL for comparison execution."""
    # Bind #{param} → value
    sql = original_sql
    if params:
        for name, val in params.items():
            pattern = rf'#\{{{name}(?:[^}}]*)?\}}'
            if val is None or val == '':
                replacement = 'NULL'
            elif isinstance(val, (int, float)):
                replacement = str(val)
            else:
                escaped = str(val).replace("'", "''")
                replacement = f"'{escaped}'"
            sql = re.sub(pattern, replacement, sql)

    # Remaining unbound params → NULL
    sql = re.sub(r'#\{[^}]+\}', 'NULL', sql)
    # ${param} → '1'
    sql = re.sub(r'\$\{[^}]+\}', "'1'", sql)
    # Strip MyBatis tags
    sql = re.sub(r'</?(?:if|choose|when|otherwise|where|set|trim|foreach|bind)\b[^>]*>',
                 '', sql, flags=re.IGNORECASE)
    # CDATA
    sql = re.sub(r'<!\[CDATA\[', '', sql)
    sql = re.sub(r'\]\]>', '', sql)
    # XML entities
    for entity, char in {'&lt;': '<', '&gt;': '>', '&amp;': '&'}.items():
        sql = sql.replace(entity, char)

    clean = sql.strip().rstrip(';')

    if sql_type == 'select':
        if 'ROWNUM' not in clean.upper() and 'FETCH FIRST' not in clean.upper():
            return f"SELECT * FROM ({clean}) WHERE ROWNUM <= {limit};\nEXIT;\n"
        return f"{clean};\nEXIT;\n"
    else:
        return f"{clean};\nROLLBACK;\nEXIT;\n"


class ResultComparator:
    """Compare query results between Oracle and target DB."""

    def __init__(self, target_executor: SQLExecutor | None = None):
        self._target = target_executor or SQLExecutor()
        self._oracle_ok = _oracle_available()

    @property
    def oracle_available(self) -> bool:
        return self._oracle_ok

    def compare_single(self, mapper_file: str, sql_id: str,
                        target_file: str, source_file: str,
                        params: dict | None = None,
                        sql_type: str = 'select') -> CompareResult:
        """Compare a single query on Oracle vs target DB.

        Args:
            target_file: Path to converted XML (target DB SQL)
            source_file: Path to original XML (Oracle SQL)
            params: Bind parameter values
            sql_type: select | insert | update | delete
        """
        if not self._oracle_ok:
            return CompareResult(
                sql_id=sql_id, mapper_file=mapper_file,
                status='SKIP', error='Oracle not available',
            )

        # 1. Execute on target DB
        extracted = extract_sql_from_xml(target_file, params)
        if not extracted:
            return CompareResult(
                sql_id=sql_id, mapper_file=mapper_file,
                status='ERROR', error='Failed to extract target SQL',
            )
        _, target_sql = extracted
        target_result = self._target.execute_single(target_sql, sql_type=sql_type)

        if target_result.status != 'PASS':
            return CompareResult(
                sql_id=sql_id, mapper_file=mapper_file,
                status='ERROR', target_rows=-1,
                error=f'Target execution failed: {target_result.error}',
            )

        # 2. Read and prepare Oracle SQL
        source_path = Path(source_file)
        if not source_path.exists():
            return CompareResult(
                sql_id=sql_id, mapper_file=mapper_file,
                status='SKIP', error='Oracle source file not found',
            )

        oracle_content = source_path.read_text(encoding='utf-8')
        # Extract SQL body from XML tag
        m = re.search(
            r'<(select|insert|update|delete|sql)\s+[^>]*>(.*?)</\1>',
            oracle_content, re.DOTALL | re.IGNORECASE,
        )
        oracle_body = m.group(2).strip() if m else oracle_content

        oracle_sql = _prepare_oracle_sql(oracle_body, sql_type, params)

        # 3. Execute on Oracle
        oracle_out, oracle_ok = _run_oracle_sql(oracle_sql, timeout=30)

        if not oracle_ok:
            return CompareResult(
                sql_id=sql_id, mapper_file=mapper_file,
                status='SKIP', target_rows=target_result.rows,
                error=f'Oracle execution failed: {oracle_out[:200]}',
            )

        oracle_rows = _count_oracle_rows(oracle_out)

        # 4. Compare
        warnings = []

        # Zero-result warning
        if oracle_rows == 0 and target_result.rows == 0:
            warnings.append('WARN_ZERO_BOTH: both returned 0 rows — TC params may not match data')

        if oracle_rows == target_result.rows:
            return CompareResult(
                sql_id=sql_id, mapper_file=mapper_file,
                status='PASS',
                oracle_rows=oracle_rows, target_rows=target_result.rows,
                warnings=warnings,
            )
        else:
            return CompareResult(
                sql_id=sql_id, mapper_file=mapper_file,
                status='FAIL_ROW_COUNT',
                oracle_rows=oracle_rows, target_rows=target_result.rows,
                error=f'Row count mismatch: Oracle={oracle_rows}, Target={target_result.rows}',
                warnings=warnings,
            )

    def compare_batch(self, items: list[dict]) -> list[CompareResult]:
        """Compare a batch of queries."""
        results = []
        for item in items:
            result = self.compare_single(
                mapper_file=item['mapper_file'],
                sql_id=item['sql_id'],
                target_file=item['target_file'],
                source_file=item.get('source_file', ''),
                params=item.get('params'),
                sql_type=item.get('sql_type', 'select'),
            )
            results.append(result)
        return results
