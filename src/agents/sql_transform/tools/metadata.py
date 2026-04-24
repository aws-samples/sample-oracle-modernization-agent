"""Target DB metadata extraction and lookup tool.

Extracts column metadata from target database (PostgreSQL or MySQL) and stores in oma_control.db.
Used by Phase 5 (Parameter Casting) to determine correct type casts.
Failure is non-fatal - transform continues without metadata.
"""
import os
import subprocess
import sqlite3
from strands import tool
from utils.project_paths import DB_PATH, OUTPUT_DIR, get_target_dbms, get_target_db_display_name

# --- PostgreSQL ---
_PG_SSM_PREFIX = "/oma/target_postgres/"
_PG_PARAM_MAP = {
    'PGHOST': 'host',
    'PGPORT': 'port',
    'PGDATABASE': 'database',
    'PGUSER': 'username',
    'PGPASSWORD': 'password',
}

# --- MySQL ---
_MYSQL_SSM_PREFIX = "/oma/target_mysql/"
_MYSQL_PARAM_MAP = {
    'MYSQL_HOST': 'host',
    'MYSQL_PORT': 'port',
    'MYSQL_DATABASE': 'database',
    'MYSQL_USER': 'username',
    'MYSQL_PASSWORD': 'password',
}


def _get_pg_connection_vars() -> dict:
    """Get PostgreSQL connection vars from env or AWS Parameter Store."""
    required = ['PGHOST', 'PGDATABASE', 'PGUSER']
    if all(os.environ.get(v) for v in required):
        return {k: os.environ[k] for k in _PG_PARAM_MAP if os.environ.get(k)}

    try:
        import boto3
        ssm = boto3.client('ssm')
        resp = ssm.get_parameters_by_path(Path=_PG_SSM_PREFIX, WithDecryption=True)
        params = {p['Name'].split('/')[-1]: p['Value'] for p in resp.get('Parameters', [])}
        if not params:
            return {}
        pg_vars = {}
        for env_key, ssm_key in _PG_PARAM_MAP.items():
            if ssm_key in params:
                pg_vars[env_key] = params[ssm_key]
        if all(pg_vars.get(v) for v in required):
            print(f"📡 PostgreSQL connection from Parameter Store ({_PG_SSM_PREFIX})")
            return pg_vars
        return {}
    except Exception as e:
        print(f"⚠️  Parameter Store lookup failed: {e}")
        return {}


def _get_mysql_connection_vars() -> dict:
    """Get MySQL connection vars from env or AWS Parameter Store."""
    required = ['MYSQL_HOST', 'MYSQL_DATABASE', 'MYSQL_USER']
    if all(os.environ.get(v) for v in required):
        return {k: os.environ[k] for k in _MYSQL_PARAM_MAP if os.environ.get(k)}

    try:
        import boto3
        ssm = boto3.client('ssm')
        resp = ssm.get_parameters_by_path(Path=_MYSQL_SSM_PREFIX, WithDecryption=True)
        params = {p['Name'].split('/')[-1]: p['Value'] for p in resp.get('Parameters', [])}
        if not params:
            return {}
        mysql_vars = {}
        for env_key, ssm_key in _MYSQL_PARAM_MAP.items():
            if ssm_key in params:
                mysql_vars[env_key] = params[ssm_key]
        if all(mysql_vars.get(v) for v in required):
            print(f"📡 MySQL connection from Parameter Store ({_MYSQL_SSM_PREFIX})")
            return mysql_vars
        return {}
    except Exception as e:
        print(f"⚠️  Parameter Store lookup failed: {e}")
        return {}


# --- Oracle (source DB for TC generation + Compare) ---
_ORACLE_PROP_MAP = {
    'ORACLE_HOST': 'ORACLE_HOST',
    'ORACLE_PORT': 'ORACLE_PORT',
    'ORACLE_SID': 'ORACLE_SERVICE_NAME',
    'ORACLE_USER': 'ORACLE_SVC_USER',
    'ORACLE_PASSWORD': 'ORACLE_SVC_PASSWORD',
}


def _get_oracle_connection_vars() -> dict:
    """Get Oracle connection vars from env or DB properties.

    Maps DB property keys (from run_setup.py) to env var keys expected by
    tc_generator/result_comparator: ORACLE_SERVICE_NAME → ORACLE_SID, etc.
    """
    required = ['ORACLE_HOST', 'ORACLE_SID', 'ORACLE_USER']
    if all(os.environ.get(v) for v in required):
        return {k: os.environ[k] for k in _ORACLE_PROP_MAP if os.environ.get(k)}

    # Load from DB properties table
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH), timeout=10)
            try:
                props = {}
                for row in conn.execute("SELECT key, value FROM properties WHERE key LIKE 'ORACLE%'"):
                    props[row[0]] = row[1]
            finally:
                conn.close()

            if not props:
                return {}

            oracle_vars = {}
            for env_key, prop_key in _ORACLE_PROP_MAP.items():
                val = props.get(prop_key, '')
                if val:
                    oracle_vars[env_key] = val

            # ORACLE_CONN_TYPE: always 'service' (run_setup uses SERVICE_NAME)
            oracle_vars['ORACLE_CONN_TYPE'] = 'service'

            if all(oracle_vars.get(v) for v in required):
                return oracle_vars
        except Exception:
            pass

    return {}


def _init_metadata_table(conn):
    """Create target_metadata table if not exists. Migrate from legacy pg_metadata if found."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS target_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_schema TEXT NOT NULL,
            table_name TEXT NOT NULL,
            column_name TEXT NOT NULL,
            data_type TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_target_meta_col ON target_metadata(table_name, column_name)")

    # Migrate legacy pg_metadata data if it exists and target_metadata is empty
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pg_metadata'")
    if cursor.fetchone():
        cursor.execute("SELECT COUNT(*) FROM target_metadata")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO target_metadata (table_schema, table_name, column_name, data_type) "
                           "SELECT table_schema, table_name, column_name, data_type FROM pg_metadata")
            migrated = cursor.rowcount
            if migrated > 0:
                print(f"📦 Migrated {migrated} rows from pg_metadata → target_metadata")
        conn.execute("DROP TABLE pg_metadata")
    conn.commit()


def _extract_pg_metadata(env: dict) -> list[tuple]:
    """Extract metadata from PostgreSQL via psql."""
    sql = """
SELECT table_schema, table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema NOT IN (
    'information_schema', 'pg_catalog', 'pg_toast',
    'aws_commons', 'aws_oracle_context', 'aws_oracle_data', 'aws_oracle_ext', 'public'
)
ORDER BY table_schema, table_name, ordinal_position;
"""
    result = subprocess.run(
        ['psql', '-t', '-A', '-F', '|', '-c', sql],
        capture_output=True, text=True, timeout=30, env=env
    )
    if result.returncode != 0:
        raise RuntimeError(f"psql error: {result.stderr.strip()}")

    lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
    rows = []
    for line in lines:
        parts = line.split('|')
        if len(parts) == 4:
            rows.append(tuple(p.strip() for p in parts))
    return rows


def _extract_mysql_metadata(conn_vars: dict) -> list[tuple]:
    """Extract metadata from MySQL via mysql CLI."""
    database = conn_vars.get('MYSQL_DATABASE', '')
    # Use mysql --database flag instead of interpolating into SQL
    sql = """
SELECT table_schema, table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = DATABASE()
ORDER BY table_schema, table_name, ordinal_position;
"""
    cmd = [
        'mysql',
        '-h', conn_vars.get('MYSQL_HOST', 'localhost'),
        '-P', conn_vars.get('MYSQL_PORT', '3306'),
        '-u', conn_vars.get('MYSQL_USER', 'root'),
        '-D', database,
        '--batch', '--skip-column-names',
        '-e', sql,
    ]
    env = os.environ.copy()
    if conn_vars.get('MYSQL_PASSWORD'):
        env['MYSQL_PWD'] = conn_vars['MYSQL_PASSWORD']

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)  # nosemgrep: dangerous-subprocess-use-audit
    if result.returncode != 0:
        raise RuntimeError(f"mysql error: {result.stderr.strip()}")

    lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
    rows = []
    for line in lines:
        parts = line.split('\t')
        if len(parts) == 4:
            rows.append(tuple(p.strip() for p in parts))
    return rows


@tool
def generate_metadata() -> dict:
    """Extract target DB column metadata and store in oma_control.db.

    Connects to PostgreSQL (psql) or MySQL (mysql) based on TARGET_DBMS_TYPE.
    Stores schema, table_name, column_name, data_type in target_metadata table.
    Non-fatal: returns error info but does not raise exceptions.

    Returns:
        Dict with status, row_count, or error message
    """
    dbms = get_target_dbms()
    display_name = get_target_db_display_name(dbms)

    if dbms == 'mysql':
        conn_vars = _get_mysql_connection_vars()
        cli_name = 'mysql'
    else:
        conn_vars = _get_pg_connection_vars()
        cli_name = 'psql'

    if not conn_vars:
        msg = f"No {display_name} connection info (env vars or Parameter Store). Skipping metadata."
        print(f"⚠️  {msg}")
        return {'status': 'skipped', 'error': msg, 'row_count': 0}

    try:
        if dbms == 'mysql':
            rows = _extract_mysql_metadata(conn_vars)
        else:
            env = os.environ.copy()
            env.update(conn_vars)
            rows = _extract_pg_metadata(env)

        if not rows:
            print("⚠️  No metadata rows returned")
            return {'status': 'empty', 'error': 'No rows returned', 'row_count': 0}

        conn = sqlite3.connect(str(DB_PATH))
        try:
            _init_metadata_table(conn)
            conn.execute("DELETE FROM target_metadata")
            conn.executemany(
                "INSERT INTO target_metadata (table_schema, table_name, column_name, data_type) VALUES (?,?,?,?)",
                rows
            )
            conn.commit()
        finally:
            conn.close()

        # Also save as txt file for Java test tool
        metadata_dir = OUTPUT_DIR / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        txt_path = metadata_dir / "oma_metadata.txt"
        with open(txt_path, 'w', encoding='utf-8') as f:
            for row in rows:
                f.write('|'.join(row) + '\n')

        # Save as JSON for human readability
        import json
        json_path = metadata_dir / "oma_metadata.json"
        metadata_by_table = {}
        for schema, table, column, dtype in rows:
            key = f"{schema}.{table}"
            if key not in metadata_by_table:
                metadata_by_table[key] = {"schema": schema, "table": table, "columns": {}}
            metadata_by_table[key]["columns"][column] = dtype
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(metadata_by_table, f, indent=2, ensure_ascii=False)

        print(f"📊 Metadata: {len(rows)} columns saved to target_metadata table + {txt_path} + {json_path}")
        return {'status': 'success', 'row_count': len(rows)}

    except FileNotFoundError:
        msg = f"{cli_name} not found. Install {display_name} client or skip metadata."
        print(f"⚠️  {msg}")
        return {'status': 'skipped', 'error': msg, 'row_count': 0}
    except Exception as e:
        msg = f"Metadata generation failed: {e}"
        print(f"⚠️  {msg}")
        return {'status': 'error', 'error': msg, 'row_count': 0}


@tool
def lookup_column_type(table_name: str, column_name: str) -> dict:
    """Lookup column data type from target_metadata table.

    Args:
        table_name: Table name (case-insensitive)
        column_name: Column name (case-insensitive)

    Returns:
        Dict with data_type or 'unknown' if not found
    """
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='target_metadata'")
        if not cursor.fetchone():
            return {'table_name': table_name, 'column_name': column_name, 'data_type': 'unknown', 'reason': 'no metadata table'}

        cursor.execute(
            "SELECT data_type FROM target_metadata WHERE LOWER(table_name) = LOWER(?) AND LOWER(column_name) = LOWER(?)",
            (table_name, column_name)
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    if row:
        return {'table_name': table_name, 'column_name': column_name, 'data_type': row[0]}
    return {'table_name': table_name, 'column_name': column_name, 'data_type': 'unknown'}
