"""CLI-based SQL executor — replaces Java MyBatis bulk executor.

Supports PostgreSQL (psql), MySQL (mysql), and Oracle (sqlplus) via
batch-marker pattern: all queries in one CLI session, delimited by
echo markers, parsed after execution.

Safety: SELECT with LIMIT, DML with BEGIN/ROLLBACK, statement_timeout.
"""
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from utils.project_paths import get_target_dbms, get_target_db_display_name


@dataclass
class SQLResult:
    sql_id: str
    mapper_file: str
    status: str  # PASS | FAIL | SKIP | TIMEOUT
    error: str = ""
    sql_state: str = ""
    rows: int = -1
    duration_ms: int = 0


# ── MyBatis tag/param stripping (reused from old test_tools) ──

_MYBATIS_TAG_RE = re.compile(
    r'</?(?:if|choose|when|otherwise|where|set|trim|foreach|bind)\b[^>]*>',
    re.IGNORECASE,
)
_PARAM_RE = re.compile(r'#\{[^}]+\}(?:::(\w+))?')
_DOLLAR_PARAM_RE = re.compile(r'\$\{[^}]+\}')
_XML_ENTITIES = {'&lt;': '<', '&gt;': '>', '&amp;': '&', '&quot;': '"', '&apos;': "'"}

_SQL_TAG_RE = re.compile(
    r'<(select|insert|update|delete|sql)\s+[^>]*id\s*=\s*["\'][^"\']+["\'][^>]*>(.*?)</\1>',
    re.DOTALL | re.IGNORECASE,
)


def extract_sql_from_xml(target_file: str, params: dict | None = None) -> tuple[str, str] | None:
    """Extract SQL from converted MyBatis XML and prepare for execution.

    Returns (sql_type, prepared_sql) or None.
    If params is provided, binds #{param} → value; otherwise #{param} → NULL.
    """
    path = Path(target_file)
    if not path.exists():
        return None

    content = path.read_text(encoding='utf-8')
    m = _SQL_TAG_RE.search(content)
    if not m:
        return None

    sql_type = m.group(1).lower()
    sql_body = m.group(2).strip()

    # Strip CDATA
    sql_body = re.sub(r'<!\[CDATA\[', '', sql_body)
    sql_body = re.sub(r'\]\]>', '', sql_body)

    # Strip MyBatis dynamic tags
    sql_body = _MYBATIS_TAG_RE.sub('', sql_body)

    # Bind parameters
    if params:
        def _bind(match):
            full = match.group(0)
            cast = match.group(1)
            name_match = re.search(r'#\{(\w+)', full)
            name = name_match.group(1) if name_match else ''
            val = params.get(name)
            if val is None:
                return f'NULL::{cast}' if cast else 'NULL'
            if isinstance(val, (int, float)):
                return f'{val}::{cast}' if cast else str(val)
            escaped = str(val).replace("'", "''")
            return f"'{escaped}'::{cast}" if cast else f"'{escaped}'"
        sql_body = _PARAM_RE.sub(_bind, sql_body)
    else:
        def _null_bind(match):
            cast = match.group(1)
            return f'NULL::{cast}' if cast else 'NULL'
        sql_body = _PARAM_RE.sub(_null_bind, sql_body)

    # ${param} → '1'
    sql_body = _DOLLAR_PARAM_RE.sub("'1'", sql_body)

    # Decode XML entities
    for entity, char in _XML_ENTITIES.items():
        sql_body = sql_body.replace(entity, char)

    sql_body = re.sub(r'\n\s*\n', '\n', sql_body).strip()
    if not sql_body:
        return None

    return sql_type, sql_body


class SQLExecutor:
    """CLI-based SQL executor with batch-marker pattern."""

    def __init__(self, db_type: str | None = None):
        self._db_type = db_type or get_target_dbms()

    def _build_env(self) -> dict:
        env = dict(os.environ)
        if self._db_type == 'mysql':
            env['MYSQL_HOST'] = os.environ.get('MYSQL_HOST', 'localhost')
            env['MYSQL_TCP_PORT'] = os.environ.get('MYSQL_PORT', '3306')
            env['MYSQL_PWD'] = os.environ.get('MYSQL_PASSWORD', '')
        elif self._db_type == 'oracle':
            pass  # sqlplus uses conn string
        else:
            env['PGHOST'] = os.environ.get('PGHOST', 'localhost')
            env['PGPORT'] = os.environ.get('PGPORT', '5432')
            env['PGDATABASE'] = os.environ.get('PGDATABASE', 'postgres')
            env['PGUSER'] = os.environ.get('PGUSER', '')
            env['PGPASSWORD'] = os.environ.get('PGPASSWORD', '')
        return env

    def _cli_cmd(self) -> list[str]:
        if self._db_type == 'mysql':
            return ['mysql', '--batch', '--raw',
                    '-u', os.environ.get('MYSQL_USER', ''),
                    '-D', os.environ.get('MYSQL_DATABASE', 'test')]
        if self._db_type == 'oracle':
            u = os.environ.get('ORACLE_USER', '')
            p = os.environ.get('ORACLE_PASSWORD', '')
            h = os.environ.get('ORACLE_HOST', '')
            port = os.environ.get('ORACLE_PORT', '1521')
            sid = os.environ.get('ORACLE_SID', '')
            conn_type = os.environ.get('ORACLE_CONN_TYPE', 'service')
            if conn_type == 'sid':
                conn = f"(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST={h})(PORT={port}))(CONNECT_DATA=(SID={sid})))"
            else:
                conn = f"{h}:{port}/{sid}"
            return ['sqlplus', '-S', f'{u}/{p}@{conn}']
        return ['psql']

    def _marker(self, test_id: str) -> str:
        if self._db_type == 'mysql':
            return f"SELECT '=== {test_id} ===' AS marker;\n"
        if self._db_type == 'oracle':
            return f"PROMPT === {test_id} ===\n"
        return f"\\echo === {test_id} ===\n"

    def _parse_marker_output(self, output: str) -> dict[str, str]:
        """Parse batch output into {test_id: output_text}."""
        results = {}
        marker_re = re.compile(r'=== (.+?) ===')
        parts = marker_re.split(output)
        # parts: [preamble, id1, output1, id2, output2, ...]
        for i in range(1, len(parts) - 1, 2):
            test_id = parts[i].strip()
            text = parts[i + 1].strip() if i + 1 < len(parts) else ''
            results[test_id] = text
        return results

    def _is_error(self, output: str) -> tuple[bool, str, str]:
        """Check if output indicates an error. Returns (is_error, message, sql_state)."""
        if not output:
            return False, '', ''
        error_patterns = [
            (r'ERROR:\s*(.*?)(?:\n|$)', r'(?:SQLSTATE|State):\s*(\w{5})'),
            (r'Error Code:\s*\d+.*?Message:\s*(.*?)(?:\n|$)', r'(\d{5})'),
        ]
        for err_pat, state_pat in error_patterns:
            m = re.search(err_pat, output, re.IGNORECASE)
            if m:
                msg = m.group(1).strip()
                sm = re.search(state_pat, output)
                state = sm.group(1) if sm else ''
                return True, msg[:500], state
        if 'ORA-' in output:
            m = re.search(r'(ORA-\d+:.*?)(?:\n|$)', output)
            return True, (m.group(1) if m else output[:200]), ''
        return False, '', ''

    def _count_rows(self, output: str) -> int:
        """Extract row count from CLI output."""
        if self._db_type == 'oracle':
            m = re.search(r'(\d+)\s+rows?\s+selected', output, re.IGNORECASE)
            return int(m.group(1)) if m else 0
        # psql: (N rows) at the end
        m = re.search(r'\((\d+)\s+rows?\)', output)
        if m:
            return int(m.group(1))
        # mysql: count non-header lines
        lines = [l for l in output.strip().split('\n') if l.strip() and 'marker' not in l.lower()]
        return max(0, len(lines) - 1)  # subtract header

    # ── Public API ──

    def explain_batch(self, items: list[dict]) -> list[SQLResult]:
        """Run EXPLAIN on all items in a single CLI session."""
        if not items:
            return []

        sql_script = ""
        if self._db_type == 'postgresql':
            sql_script += "SET statement_timeout = '15s';\n"

        for item in items:
            test_id = f"{item['mapper_file']}/{item['sql_id']}"
            extracted = extract_sql_from_xml(item['target_file'], item.get('params'))
            if not extracted:
                continue
            sql_type, sql_body = extracted

            sql_script += self._marker(test_id)
            if self._db_type == 'mysql':
                sql_body_clean = re.sub(r'NULL::\w+', 'NULL', sql_body)
                sql_script += f"EXPLAIN {sql_body_clean};\n"
            else:
                sql_script += f"EXPLAIN {sql_body};\n"

        return self._run_batch(sql_script, items, 'explain')

    def execute_batch(self, items: list[dict], limit: int = 100) -> list[SQLResult]:
        """Execute all items in a single CLI session.
        SELECT: adds LIMIT. DML: wraps in BEGIN/ROLLBACK.
        """
        if not items:
            return []

        sql_script = ""
        if self._db_type == 'postgresql':
            sql_script += "SET statement_timeout = '30s';\n"

        for item in items:
            test_id = f"{item['mapper_file']}/{item['sql_id']}"
            extracted = extract_sql_from_xml(item['target_file'], item.get('params'))
            if not extracted:
                continue
            sql_type, sql_body = extracted
            clean = sql_body.rstrip(';')

            sql_script += self._marker(test_id)

            if sql_type == 'select':
                if 'LIMIT' not in clean.upper():
                    sql_script += f"{clean} LIMIT {limit};\n"
                else:
                    sql_script += f"{clean};\n"
            else:
                sql_script += f"BEGIN;\n{clean};\nROLLBACK;\n"

        return self._run_batch(sql_script, items, 'execute')

    def execute_single(self, sql: str, sql_type: str = 'select',
                       limit: int = 100) -> SQLResult:
        """Execute a single prepared SQL string."""
        clean = sql.rstrip(';')
        if sql_type == 'select' and 'LIMIT' not in clean.upper():
            script = f"SET statement_timeout = '30s';\n{clean} LIMIT {limit};\n"
        elif sql_type in ('insert', 'update', 'delete'):
            script = f"SET statement_timeout = '30s';\nBEGIN;\n{clean};\nROLLBACK;\n"
        else:
            script = f"SET statement_timeout = '30s';\n{clean};\n"

        env = self._build_env()
        try:
            # nosemgrep: dangerous-subprocess-use-audit
            proc = subprocess.run(
                self._cli_cmd(), input=script,
                capture_output=True, text=True, timeout=45, env=env,
            )
            output = proc.stdout + proc.stderr
            is_err, msg, state = self._is_error(output)
            if is_err:
                return SQLResult(sql_id='', mapper_file='', status='FAIL',
                                 error=msg, sql_state=state)
            return SQLResult(sql_id='', mapper_file='', status='PASS',
                             rows=self._count_rows(proc.stdout))
        except subprocess.TimeoutExpired:
            return SQLResult(sql_id='', mapper_file='', status='TIMEOUT',
                             error='Execution timeout (45s)')
        except Exception as e:
            return SQLResult(sql_id='', mapper_file='', status='FAIL', error=str(e))

    def _run_batch(self, sql_script: str, items: list[dict],
                   mode: str) -> list[SQLResult]:
        """Execute batch script and parse results."""
        env = self._build_env()
        timeout = max(120, len(items) * 5)

        # Write to temp file for large scripts
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False,
                                          encoding='utf-8')
        try:
            tmp.write(sql_script)
            tmp.close()

            if self._db_type == 'postgresql':
                cmd = self._cli_cmd() + ['-f', tmp.name]
            elif self._db_type == 'mysql':
                cmd = self._cli_cmd()
                # mysql reads from stdin for temp file
                cmd = None  # will use input instead
            else:
                cmd = self._cli_cmd()

            if cmd:
                # nosemgrep: dangerous-subprocess-use-audit
                proc = subprocess.run(
                    cmd, capture_output=True, text=True,
                    timeout=timeout, env=env,
                )
            else:
                # nosemgrep: dangerous-subprocess-use-audit
                proc = subprocess.run(
                    self._cli_cmd(), input=sql_script,
                    capture_output=True, text=True,
                    timeout=timeout, env=env,
                )

            output = proc.stdout
            if proc.stderr:
                output += '\n' + proc.stderr

        except subprocess.TimeoutExpired:
            return [SQLResult(
                sql_id=item['sql_id'], mapper_file=item['mapper_file'],
                status='TIMEOUT', error=f'Batch timeout ({timeout}s)',
            ) for item in items]
        except Exception as e:
            return [SQLResult(
                sql_id=item['sql_id'], mapper_file=item['mapper_file'],
                status='FAIL', error=str(e),
            ) for item in items]
        finally:
            os.unlink(tmp.name)

        # Parse marker-delimited output
        parsed = self._parse_marker_output(output)

        results = []
        for item in items:
            test_id = f"{item['mapper_file']}/{item['sql_id']}"
            section = parsed.get(test_id, '')

            is_err, msg, state = self._is_error(section)
            if is_err:
                results.append(SQLResult(
                    sql_id=item['sql_id'], mapper_file=item['mapper_file'],
                    status='FAIL', error=msg, sql_state=state,
                ))
            else:
                rows = self._count_rows(section) if mode == 'execute' else -1
                results.append(SQLResult(
                    sql_id=item['sql_id'], mapper_file=item['mapper_file'],
                    status='PASS', rows=rows,
                ))

        return results


def check_cli_available(db_type: str | None = None) -> tuple[bool, str]:
    """Check if the CLI tool for the given DB type is available."""
    dbms = db_type or get_target_dbms()
    tool_map = {'postgresql': 'psql', 'mysql': 'mysql', 'oracle': 'sqlplus'}
    tool_name = tool_map.get(dbms, 'psql')
    if shutil.which(tool_name):
        return True, tool_name
    return False, f'{tool_name} not found in PATH'
