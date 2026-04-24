"""Test Case Generator — 7-source priority chain for automatic TC generation.

Sources (priority order):
  1. custom_binds.json — project-specific custom bind values
  2. Oracle sample data — real rows from source tables
  3. V$SQL_BIND_CAPTURE — captured bind values from production
  4. ALL_TAB_COL_STATISTICS — MIN/MAX boundary values
  5. FK sampling — referential integrity values
  6. Name/type inference — from XML param patterns + metadata
  7. LLM (Sonnet 4.6) — SQL context-based generation

Falls back gracefully when Oracle is unavailable (sources 2-5 skipped).
"""
import json
import os
import re
import subprocess
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from utils.project_paths import (
    DB_PATH, OUTPUT_DIR, TRANSFORM_DIR, LITE_MODEL_ID,
    get_target_dbms,
)


@dataclass
class TestCase:
    name: str
    source: str  # CUSTOM | SAMPLE | BIND_CAPTURE | COL_STATS | FK | INFERENCE | LLM
    params: dict = field(default_factory=dict)


# ── Oracle helpers ──

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


def _run_oracle_sql(sql: str, timeout: int = 30) -> str:
    """Execute SQL via sqlplus CLI. Returns stdout."""
    header = "SET PAGESIZE 0 FEEDBACK OFF HEADING OFF LINESIZE 32767 TRIMOUT ON TRIMSPOOL ON\n"
    try:
        result = subprocess.run(
            ['sqlplus', '-S', _oracle_conn_str()],
            input=header + sql + "\nEXIT;\n",
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout
    except Exception:
        return ""


def _parse_pipe(output: str, min_cols: int = 2):
    for line in output.split('\n'):
        parts = [p.strip() for p in line.strip().split('|')]
        if len(parts) >= min_cols and parts[0]:
            yield parts


def _oracle_schema() -> str:
    return os.environ.get('ORACLE_SCHEMA', os.environ.get('ORACLE_USER', '')).upper()


# ── Source 2: Oracle Sample Data ──

def _get_sample_data(tables: set[str]) -> dict[str, list[dict]]:
    """Sample rows from Oracle tables. Returns {TABLE: [{col: val, ...}]}."""
    if not _oracle_available() or not tables:
        return {}
    schema = _oracle_schema()
    samples = {}
    for tbl in tables:
        sql = f"SELECT * FROM {schema}.{tbl} SAMPLE(1) WHERE ROWNUM <= 3;\n"
        out = _run_oracle_sql(sql, 15)
        if out and 'ORA-' not in out:
            rows = [l.strip() for l in out.strip().split('\n') if l.strip()]
            if rows:
                samples[tbl] = rows  # raw pipe-separated
    if samples:
        print(f"  Source-Sample: {len(samples)} tables")
    return samples


# ── Source 3: V$SQL_BIND_CAPTURE ──

def _get_bind_captures() -> dict[str, list[str]]:
    """Get captured bind values from Oracle production. Returns {param_name: [values]}."""
    if not _oracle_available():
        return {}
    sql = ("SELECT DISTINCT NAME||'|'||NVL(TO_CHAR(VALUE_STRING),'NULL')"
           " FROM V$SQL_BIND_CAPTURE WHERE VALUE_STRING IS NOT NULL"
           " AND ROWNUM<=5000 ORDER BY 1;\n")
    out = _run_oracle_sql(sql, 30)
    caps = {}
    for parts in _parse_pipe(out):
        name = parts[0].lstrip(':').lower()
        val = parts[1]
        if name and val != 'NULL':
            caps.setdefault(name, []).append(val)
    for k in caps:
        caps[k] = list(dict.fromkeys(caps[k]))[:5]
    if caps:
        print(f"  Source-BindCapture: {len(caps)} params, {sum(len(v) for v in caps.values())} values")
    return caps


# ── Source 4: ALL_TAB_COL_STATISTICS ──

def _get_column_stats() -> dict[str, dict]:
    """Get column stats from Oracle. Returns {COL_NAME: {low, high, distinct}}."""
    if not _oracle_available():
        return {}
    schema = _oracle_schema()
    sql = (f"SELECT TABLE_NAME||'|'||COLUMN_NAME||'|'||NVL(TO_CHAR(LOW_VALUE),'NULL')"
           f"||'|'||NVL(TO_CHAR(HIGH_VALUE),'NULL')||'|'||NVL(NUM_DISTINCT,0)"
           f" FROM ALL_TAB_COL_STATISTICS WHERE OWNER='{schema}' AND LOW_VALUE IS NOT NULL"
           f" AND ROWNUM<=10000 ORDER BY 1,2;\n")
    out = _run_oracle_sql(sql, 60)
    stats = {}
    for parts in _parse_pipe(out, 4):
        col = parts[1]
        low, high = parts[2], parts[3]
        dist = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0
        if low != 'NULL':
            info = {'low': low, 'high': high, 'distinct': dist}
            stats[col.lower()] = info
    if stats:
        print(f"  Source-ColStats: {len(stats)} columns")
    return stats


# ── Source 5: FK Sampling ──

def _get_fk_samples() -> dict[str, list[str]]:
    """Get FK reference values. Returns {col_name: [values]}."""
    if not _oracle_available():
        return {}
    schema = _oracle_schema()
    sql = (f"SELECT CC.COLUMN_NAME||'|'||RC.TABLE_NAME||'|'||RC.COLUMN_NAME"
           f" FROM ALL_CONS_COLUMNS CC"
           f" JOIN ALL_CONSTRAINTS C ON CC.CONSTRAINT_NAME=C.CONSTRAINT_NAME AND CC.OWNER=C.OWNER"
           f" JOIN ALL_CONS_COLUMNS RC ON C.R_CONSTRAINT_NAME=RC.CONSTRAINT_NAME AND C.R_OWNER=RC.OWNER"
           f" WHERE C.CONSTRAINT_TYPE='R' AND C.OWNER='{schema}' AND ROWNUM<=3000"
           f" ORDER BY 1;\n")
    out = _run_oracle_sql(sql, 60)

    fk_vals = {}
    for parts in _parse_pipe(out, 3):
        col, ref_tbl, ref_col = parts[0].lower(), parts[1], parts[2]
        sample_sql = f"SELECT DISTINCT {ref_col} FROM {schema}.{ref_tbl} WHERE {ref_col} IS NOT NULL AND ROWNUM<=3;\n"
        sample_out = _run_oracle_sql(sample_sql, 10)
        vals = [l.strip() for l in sample_out.split('\n') if l.strip() and 'ORA-' not in l][:3]
        if vals:
            fk_vals[col] = vals
    if fk_vals:
        print(f"  Source-FK: {len(fk_vals)} columns")
    return fk_vals


# ── Source 6: Inference (from existing generate_parameters logic) ──

_PARAM_WITH_CAST = re.compile(r'#\{([^},]+?)(?:::(\w+))?\s*[},]')
_IF_NULL_CHECK = re.compile(r'<if\s+test=["\'](\w+)\s*!=\s*null', re.IGNORECASE)
_IF_EQUALS_CHECK = re.compile(r'<(?:if|when)\s+test=["\'](\w+)\s*==\s*[\'"]([^\'"]+)[\'"]', re.IGNORECASE)
_FOREACH_COLLECTION = re.compile(r'<foreach\s+[^>]*collection=["\'](\w+)["\']', re.IGNORECASE)
_DATE_FUNC = re.compile(
    r'(?:to_date|to_timestamp|str_to_date)\s*\(\s*#\{(\w+)\}[^,]*,\s*[\'"]([^\'"]+)[\'"]',
    re.IGNORECASE,
)
_DATE_FORMATS = {
    'YYYYMMDD': '20250101', 'YYYY-MM-DD': '2025-01-01',
    'YYYYMMDDHH24MISS': '20250101000000', 'YYYY-MM-DD HH24:MI:SS': '2025-01-01 00:00:00',
}


def _infer_params(xml_content: str, metadata: dict) -> dict[str, str]:
    """Infer param values from XML patterns + metadata. Returns {param: value}."""
    values = {}
    nullable = set()
    conditionals = {}
    collections = set()
    date_vals = {}

    for m in _IF_NULL_CHECK.finditer(xml_content):
        nullable.add(m.group(1).strip())
    for m in _IF_EQUALS_CHECK.finditer(xml_content):
        conditionals[m.group(1).strip()] = m.group(2).strip()
    for m in _FOREACH_COLLECTION.finditer(xml_content):
        collections.add(m.group(1).strip())
    for m in _DATE_FUNC.finditer(xml_content):
        fmt = m.group(2).strip().upper()
        date_vals[m.group(1).strip()] = _DATE_FORMATS.get(fmt, '20250101')

    for m in _PARAM_WITH_CAST.finditer(xml_content):
        param = m.group(1).strip()
        cast = m.group(2)
        if '.' in param:
            param = param.split('.')[0].strip()
        if not param or param.startswith('_'):
            continue

        if param in collections:
            values[param] = '1,2,3'
        elif param in nullable:
            values[param] = ''
        elif param in conditionals:
            values[param] = conditionals[param]
        elif param in date_vals:
            values[param] = date_vals[param]
        elif param.lower() in metadata:
            values[param] = _value_from_type(metadata[param.lower()])
        elif cast:
            values[param] = _value_from_cast(cast)
        else:
            values[param] = '1'

    return values


def _value_from_type(data_type: str) -> str:
    dt = data_type.lower()
    if any(t in dt for t in ['int', 'serial', 'bigint']):
        return '1'
    if any(t in dt for t in ['numeric', 'decimal', 'float']):
        return '1.0'
    if 'bool' in dt:
        return 'true'
    if 'timestamp' in dt:
        return '2025-01-01 00:00:00'
    if 'date' in dt:
        return '2025-01-01'
    return '1'


def _value_from_cast(cast_type: str) -> str:
    ct = cast_type.lower()
    if ct in ('date',):
        return '2025-01-01'
    if ct in ('timestamp', 'timestamptz'):
        return '2025-01-01 00:00:00'
    if ct in ('integer', 'int', 'bigint', 'smallint', 'serial'):
        return '1'
    if ct in ('numeric', 'decimal', 'float', 'real'):
        return '1.0'
    if ct in ('boolean', 'bool'):
        return 'true'
    return '1'


# ── Source 7: LLM ──

def _llm_generate_tc(sql_body: str, param_names: list[str],
                      metadata: dict) -> dict[str, str] | None:
    """Use Sonnet 4.6 to generate test parameters based on SQL context."""
    try:
        from strands import Agent
        from strands.models.bedrock import BedrockModel
    except ImportError:
        return None

    if not param_names:
        return None

    meta_hint = ""
    for p in param_names[:10]:
        if p.lower() in metadata:
            meta_hint += f"  {p}: {metadata[p.lower()]}\n"

    meta_section = f"Column types:\n{meta_hint}\n" if meta_hint else ""
    prompt = (
        f"Generate realistic test parameter values for this SQL query.\n\n"
        f"SQL:\n{sql_body[:2000]}\n\n"
        f"Parameters: {', '.join(param_names[:20])}\n"
        f"{meta_section}"
        f"Output ONLY a JSON object mapping parameter names to test values.\n"
        f'Example: {{"userId": "USR001", "status": "ACTIVE", "startDate": "20250101"}}\n'
        f"Use realistic values that would return rows. No explanation."
    )

    try:
        model = BedrockModel(model_id=LITE_MODEL_ID, max_tokens=500)
        agent = Agent(model=model, callback_handler=None)
        result = str(agent(prompt))

        # Parse JSON from response
        brace_start = result.find('{')
        brace_end = result.rfind('}')
        if brace_start >= 0 and brace_end > brace_start:
            return json.loads(result[brace_start:brace_end + 1])
    except Exception:
        pass
    return None


# ── Metadata loader ──

def _load_metadata() -> dict[str, str]:
    """Load target DB column metadata. Returns {col_name_lower: data_type}."""
    columns = {}
    json_path = OUTPUT_DIR / "metadata" / "oma_metadata.json"
    if json_path.exists():
        try:
            meta = json.loads(json_path.read_text(encoding='utf-8'))
            for table_info in meta.values():
                for col_name, col_type in table_info.get('columns', {}).items():
                    columns[col_name.lower()] = col_type.lower()
            return columns
        except Exception:
            pass

    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            try:
                for col_name, col_type in conn.execute("SELECT column_name, data_type FROM target_metadata"):
                    columns[col_name.lower()] = col_type.lower()
            finally:
                conn.close()
        except Exception:
            pass
    return columns


# ── Table extraction from SQL ──

def _extract_tables(sql_body: str) -> set[str]:
    """Extract table names from SQL for sample data."""
    tables = set()
    for m in re.finditer(r'\bFROM\s+(\w+)', sql_body, re.IGNORECASE):
        tables.add(m.group(1).upper())
    for m in re.finditer(r'\bJOIN\s+(\w+)', sql_body, re.IGNORECASE):
        tables.add(m.group(1).upper())
    return tables


# ── Main Generator ──

class TCGenerator:
    """7-source priority chain TC generator."""

    def __init__(self):
        self._metadata = _load_metadata()
        self._bind_captures: dict | None = None
        self._col_stats: dict | None = None
        self._fk_samples: dict | None = None
        self._oracle_loaded = False

    def _load_oracle_sources(self):
        if self._oracle_loaded:
            return
        self._oracle_loaded = True
        if _oracle_available():
            print("  Loading Oracle sources...")
            self._bind_captures = _get_bind_captures()
            self._col_stats = _get_column_stats()
            self._fk_samples = _get_fk_samples()
        else:
            print("  Oracle not available — skipping sources 2-5")
            self._bind_captures = {}
            self._col_stats = {}
            self._fk_samples = {}

    def generate_for_query(self, mapper_file: str, sql_id: str,
                           target_file: str) -> list[TestCase]:
        """Generate test cases for one SQL query."""
        path = Path(target_file) if target_file else None
        if not path or not path.is_file():
            return [TestCase(name='default', source='INFERENCE', params={'_dummy': '1'})]

        content = path.read_text(encoding='utf-8')
        # Extract SQL body
        m = re.search(
            r'<(select|insert|update|delete|sql)\s+[^>]*>(.*?)</\1>',
            content, re.DOTALL | re.IGNORECASE,
        )
        sql_body = m.group(2) if m else content

        # Extract param names
        param_names = list(dict.fromkeys(
            p.group(1).split('.')[0].strip()
            for p in re.finditer(r'#\{([^},]+)', content)
            if not p.group(1).strip().startswith('_')
        ))

        if not param_names:
            return [TestCase(name='no_params', source='INFERENCE', params={})]

        self._load_oracle_sources()
        cases = []

        # Source 1: custom_binds.json
        custom_path = OUTPUT_DIR / "custom_binds.json"
        if custom_path.exists():
            try:
                custom = json.loads(custom_path.read_text(encoding='utf-8'))
                key = f"{mapper_file}::{sql_id}"
                if key in custom:
                    cases.append(TestCase(name='custom', source='CUSTOM', params=custom[key]))
                elif sql_id in custom:
                    cases.append(TestCase(name='custom', source='CUSTOM', params=custom[sql_id]))
            except Exception:
                pass

        # Source 2-5: Oracle-based (if available)
        if self._bind_captures:
            bc_params = {}
            for p in param_names:
                if p.lower() in self._bind_captures:
                    bc_params[p] = self._bind_captures[p.lower()][0]
            if bc_params:
                cases.append(TestCase(name='bind_capture', source='BIND_CAPTURE', params=bc_params))

        if self._col_stats:
            boundary_params = {}
            for p in param_names:
                if p.lower() in self._col_stats:
                    boundary_params[p] = self._col_stats[p.lower()]['low']
            if boundary_params:
                cases.append(TestCase(name='boundary_low', source='COL_STATS', params=boundary_params))

        if self._fk_samples:
            fk_params = {}
            for p in param_names:
                if p.lower() in self._fk_samples:
                    fk_params[p] = self._fk_samples[p.lower()][0]
            if fk_params:
                cases.append(TestCase(name='fk_sample', source='FK', params=fk_params))

        # Source 6: Inference (always available)
        inferred = _infer_params(content, self._metadata)
        if inferred:
            cases.append(TestCase(name='inferred', source='INFERENCE', params=inferred))

        # Source 7: LLM (if < 3 cases so far)
        if len(cases) < 3:
            llm_params = _llm_generate_tc(sql_body, param_names, self._metadata)
            if llm_params:
                cases.append(TestCase(name='llm_generated', source='LLM', params=llm_params))

        # Ensure at least 1 case
        if not cases:
            cases.append(TestCase(name='default', source='INFERENCE', params={p: '1' for p in param_names}))

        return cases[:5]  # Max 5 per query

    def generate_batch(self, items: list[dict]) -> dict[str, list[TestCase]]:
        """Generate TCs for all items. Returns {mapper/sql_id: [TestCase]}."""
        result = {}
        for item in items:
            key = f"{item['mapper_file']}/{item['sql_id']}"
            tcs = self.generate_for_query(
                item['mapper_file'], item['sql_id'], item['target_file'],
            )
            result[key] = tcs
        return result

    def save_tc_json(self, tcs: dict[str, list[TestCase]], output_path: Path | None = None) -> Path:
        """Save generated TCs to JSON file."""
        if output_path is None:
            output_path = OUTPUT_DIR / "test" / "test_cases.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = {}
        for key, cases in tcs.items():
            data[key] = [
                {'name': tc.name, 'source': tc.source, 'params': tc.params}
                for tc in cases
            ]

        output_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8',
        )
        return output_path

    @staticmethod
    def load_tc_json(path: Path | None = None) -> dict[str, list[dict]]:
        """Load TCs from JSON. Returns {mapper/sql_id: [{name, source, params}]}."""
        if path is None:
            path = OUTPUT_DIR / "test" / "test_cases.json"
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding='utf-8'))
