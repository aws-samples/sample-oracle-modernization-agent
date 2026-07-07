"""Target DB metadata extraction and lookup (strands-free).

Ported from agents/sql_transform/tools/metadata.py.
Extracts column metadata from target database (PostgreSQL or MySQL) and stores in oma_control.db.
Used by cli/analyzer.py (Phase 5: Parameter Casting) to determine correct type casts.
Failure is non-fatal - transform continues without metadata.
"""
import os
import sqlite3
import subprocess
import sys


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
                print(f"Migrated {migrated} rows from pg_metadata -> target_metadata", file=sys.stderr)
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


def generate_metadata() -> dict:
    """Extract target DB column metadata and store in oma_control.db.

    Connects to PostgreSQL (psql) or MySQL (mysql) based on TARGET_DBMS_TYPE.
    Stores schema, table_name, column_name, data_type in target_metadata table.
    Non-fatal: returns error info but does not raise exceptions.

    Returns:
        Dict with status, row_count, or error message
    """
    from utils.project_paths import DB_PATH, OUTPUT_DIR, get_target_dbms, get_target_db_display_name
    from core.db_conn import get_pg_connection_vars, get_mysql_connection_vars

    dbms = get_target_dbms()
    display_name = get_target_db_display_name(dbms)

    if dbms == 'mysql':
        conn_vars = get_mysql_connection_vars()
        cli_name = 'mysql'
    else:
        conn_vars = get_pg_connection_vars()
        cli_name = 'psql'

    if not conn_vars:
        msg = f"No {display_name} connection info (env vars or Parameter Store). Skipping metadata."
        print(f"WARNING: {msg}", file=sys.stderr)
        return {'status': 'skipped', 'error': msg, 'row_count': 0}

    try:
        if dbms == 'mysql':
            rows = _extract_mysql_metadata(conn_vars)
        else:
            env = os.environ.copy()
            env.update(conn_vars)
            rows = _extract_pg_metadata(env)

        if not rows:
            print("WARNING: No metadata rows returned", file=sys.stderr)
            return {'status': 'empty', 'error': 'No rows returned', 'row_count': 0}

        with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
            _init_metadata_table(conn)
            conn.execute("DELETE FROM target_metadata")
            conn.executemany(
                "INSERT INTO target_metadata (table_schema, table_name, column_name, data_type) VALUES (?,?,?,?)",
                rows
            )
            conn.commit()

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

        print(f"Metadata: {len(rows)} columns saved to target_metadata + {txt_path}", file=sys.stderr)
        return {'status': 'success', 'row_count': len(rows)}

    except FileNotFoundError:
        msg = f"{cli_name} not found. Install {display_name} client or skip metadata."
        print(f"WARNING: {msg}", file=sys.stderr)
        return {'status': 'skipped', 'error': msg, 'row_count': 0}
    except Exception as e:
        msg = f"Metadata generation failed: {e}"
        print(f"WARNING: {msg}", file=sys.stderr)
        return {'status': 'error', 'error': msg, 'row_count': 0}


def lookup_column_type(table_name: str, column_name: str) -> dict:
    """Lookup column data type from target_metadata table.

    Args:
        table_name: Table name (case-insensitive)
        column_name: Column name (case-insensitive)

    Returns:
        Dict with data_type or 'unknown' if not found
    """
    from utils.project_paths import DB_PATH

    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='target_metadata'")
        if not cursor.fetchone():
            return {'table_name': table_name, 'column_name': column_name, 'data_type': 'unknown', 'reason': 'no metadata table'}

        cursor.execute(
            "SELECT data_type FROM target_metadata WHERE LOWER(table_name) = LOWER(?) AND LOWER(column_name) = LOWER(?)",
            (table_name, column_name)
        )
        row = cursor.fetchone()

    if row:
        return {'table_name': table_name, 'column_name': column_name, 'data_type': row[0]}
    return {'table_name': table_name, 'column_name': column_name, 'data_type': 'unknown'}
