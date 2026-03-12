"""PostgreSQL metadata extraction and lookup tool.

Extracts column metadata from target PostgreSQL database and stores in oma_control.db.
Used by Phase 5 (Parameter Casting) to determine correct type casts.
Failure is non-fatal - transform continues without metadata.
"""
import os
import subprocess
import sqlite3
from strands import tool
from utils.project_paths import DB_PATH

# Parameter Store prefix
_SSM_PREFIX = "/oma/target_postgres/"
_PG_PARAM_MAP = {
    'PGHOST': 'host',
    'PGPORT': 'port',
    'PGDATABASE': 'database',
    'PGUSER': 'username',
    'PGPASSWORD': 'password',
}


def _get_pg_connection_vars() -> dict:
    """Get PostgreSQL connection vars from env or AWS Parameter Store."""
    # 1. Check env vars first
    required = ['PGHOST', 'PGDATABASE', 'PGUSER']
    if all(os.environ.get(v) for v in required):
        return {k: os.environ[k] for k in _PG_PARAM_MAP if os.environ.get(k)}

    # 2. Fallback to Parameter Store
    try:
        import boto3
        ssm = boto3.client('ssm')
        resp = ssm.get_parameters_by_path(
            Path=_SSM_PREFIX, WithDecryption=True
        )
        params = {p['Name'].split('/')[-1]: p['Value'] for p in resp.get('Parameters', [])}

        if not params:
            return {}

        pg_vars = {}
        for env_key, ssm_key in _PG_PARAM_MAP.items():
            if ssm_key in params:
                pg_vars[env_key] = params[ssm_key]

        if all(pg_vars.get(v) for v in required):
            print(f"📡 PostgreSQL connection from Parameter Store ({_SSM_PREFIX})")
            return pg_vars
        return {}
    except Exception as e:
        print(f"⚠️  Parameter Store lookup failed: {e}")
        return {}


def _init_metadata_table(conn):
    """Create pg_metadata table if not exists."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pg_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_schema TEXT NOT NULL,
            table_name TEXT NOT NULL,
            column_name TEXT NOT NULL,
            data_type TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pg_meta_col ON pg_metadata(table_name, column_name)")
    conn.commit()


@tool
def generate_metadata() -> dict:
    """Extract PostgreSQL column metadata and store in oma_control.db.

    Connects using PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD env vars.
    Stores schema, table_name, column_name, data_type in pg_metadata table.
    Non-fatal: returns error info but does not raise exceptions.

    Returns:
        Dict with status, row_count, or error message
    """
    # Check env vars, fallback to Parameter Store
    pg_vars = _get_pg_connection_vars()
    if not pg_vars:
        msg = "No PostgreSQL connection info (env vars or Parameter Store). Skipping metadata."
        print(f"⚠️  {msg}")
        return {'status': 'skipped', 'error': msg, 'row_count': 0}

    env = os.environ.copy()
    env.update(pg_vars)

    sql = """
SELECT table_schema, table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema NOT IN (
    'information_schema', 'pg_catalog', 'pg_toast',
    'aws_commons', 'aws_oracle_context', 'aws_oracle_data', 'aws_oracle_ext', 'public'
)
ORDER BY table_schema, table_name, ordinal_position;
"""

    try:
        result = subprocess.run(
            ['psql', '-t', '-A', '-F', '|', '-c', sql],
            capture_output=True, text=True, timeout=30, env=env
        )

        if result.returncode != 0:
            msg = f"psql error: {result.stderr.strip()}"
            print(f"⚠️  {msg}")
            return {'status': 'error', 'error': msg, 'row_count': 0}

        lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
        if not lines:
            print("⚠️  No metadata rows returned")
            return {'status': 'empty', 'error': 'No rows returned', 'row_count': 0}

        # Parse and insert
        rows = []
        for line in lines:
            parts = line.split('|')
            if len(parts) == 4:
                rows.append(tuple(p.strip() for p in parts))

        with sqlite3.connect(str(DB_PATH)) as conn:
            _init_metadata_table(conn)
            conn.execute("DELETE FROM pg_metadata")  # Clean refresh
            conn.executemany(
                "INSERT INTO pg_metadata (table_schema, table_name, column_name, data_type) VALUES (?,?,?,?)",
                rows
            )
            conn.commit()

        print(f"📊 Metadata: {len(rows)} columns saved to pg_metadata table")
        return {'status': 'success', 'row_count': len(rows)}

    except FileNotFoundError:
        msg = "psql not found. Install PostgreSQL client or skip metadata."
        print(f"⚠️  {msg}")
        return {'status': 'skipped', 'error': msg, 'row_count': 0}
    except Exception as e:
        msg = f"Metadata generation failed: {e}"
        print(f"⚠️  {msg}")
        return {'status': 'error', 'error': msg, 'row_count': 0}


@tool
def lookup_column_type(table_name: str, column_name: str) -> dict:
    """Lookup column data type from pg_metadata table.

    Args:
        table_name: Table name (case-insensitive)
        column_name: Column name (case-insensitive)

    Returns:
        Dict with data_type or 'unknown' if not found
    """
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pg_metadata'")
        if not cursor.fetchone():
            return {'table_name': table_name, 'column_name': column_name, 'data_type': 'unknown', 'reason': 'no metadata table'}

        cursor.execute(
            "SELECT data_type FROM pg_metadata WHERE LOWER(table_name) = LOWER(?) AND LOWER(column_name) = LOWER(?)",
            (table_name, column_name)
        )
        row = cursor.fetchone()

    if row:
        return {'table_name': table_name, 'column_name': column_name, 'data_type': row[0]}
    return {'table_name': table_name, 'column_name': column_name, 'data_type': 'unknown'}
