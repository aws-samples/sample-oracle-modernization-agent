"""Database connection variable loaders (strands-free).

Loads connection info from environment variables or the DB properties table
(populated by `oma setup`). Used by cli/cmd_test.py and other CLI commands
that need DB access without depending on agents/.
"""
import os
import sqlite3

from utils.project_paths import DB_PATH

# --- PostgreSQL --- (env key == property key, so identity map of required+optional)
_PG_KEYS = ['PGHOST', 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGPASSWORD']

# --- MySQL ---
_MYSQL_KEYS = ['MYSQL_HOST', 'MYSQL_PORT', 'MYSQL_DATABASE', 'MYSQL_USER', 'MYSQL_PASSWORD']

# --- Oracle (source DB for TC generation + Compare) ---
_ORACLE_PROP_MAP = {
    'ORACLE_HOST': 'ORACLE_HOST',
    'ORACLE_PORT': 'ORACLE_PORT',
    'ORACLE_SID': 'ORACLE_SERVICE_NAME',
    'ORACLE_USER': 'ORACLE_SVC_USER',
    'ORACLE_PASSWORD': 'ORACLE_SVC_PASSWORD',
}


def _vars_from_env_or_props(keys: list[str], required: list[str]) -> dict:
    """Resolve connection vars: env vars first, then DB properties (oma setup)."""
    if all(os.environ.get(v) for v in required):
        return {k: os.environ[k] for k in keys if os.environ.get(k)}

    if not DB_PATH.exists():
        return {}
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        try:
            placeholders = ",".join("?" for _ in keys)
            # nosemgrep: placeholders are positional '?' only; keys are code-internal constants
            rows = conn.execute(
                f"SELECT key, value FROM properties WHERE key IN ({placeholders})",
                keys,
            ).fetchall()
        finally:
            conn.close()
    except Exception:
        return {}

    found = {k: v for k, v in rows if v}
    if all(found.get(v) for v in required):
        return found
    return {}


def get_pg_connection_vars() -> dict:
    """Get PostgreSQL connection vars from env or DB properties (oma setup)."""
    return _vars_from_env_or_props(_PG_KEYS, ['PGHOST', 'PGDATABASE', 'PGUSER'])


def get_mysql_connection_vars() -> dict:
    """Get MySQL connection vars from env or DB properties (oma setup)."""
    return _vars_from_env_or_props(_MYSQL_KEYS, ['MYSQL_HOST', 'MYSQL_DATABASE', 'MYSQL_USER'])


def get_oracle_connection_vars() -> dict:
    """Get Oracle connection vars from env or DB properties.

    Maps DB property keys (from run_setup.py) to env var keys expected by
    tc_generator/result_comparator: ORACLE_SERVICE_NAME -> ORACLE_SID, etc.
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
