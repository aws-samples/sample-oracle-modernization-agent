"""Database connection variable loaders (strands-free).

Loads connection info from environment variables, AWS Parameter Store,
or the DB properties table. Used by cli/cmd_test.py and other CLI commands
that need DB access without depending on agents/.
"""
import os
import sqlite3

from utils.project_paths import DB_PATH

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

# --- Oracle (source DB for TC generation + Compare) ---
_ORACLE_PROP_MAP = {
    'ORACLE_HOST': 'ORACLE_HOST',
    'ORACLE_PORT': 'ORACLE_PORT',
    'ORACLE_SID': 'ORACLE_SERVICE_NAME',
    'ORACLE_USER': 'ORACLE_SVC_USER',
    'ORACLE_PASSWORD': 'ORACLE_SVC_PASSWORD',
}


def get_pg_connection_vars() -> dict:
    """Get PostgreSQL connection vars from env or AWS Parameter Store."""
    required = ['PGHOST', 'PGDATABASE', 'PGUSER']
    if all(os.environ.get(v) for v in required):
        return {k: os.environ[k] for k in _PG_PARAM_MAP if os.environ.get(k)}

    # TODO(plan-03): remove SSM/boto3 fallback when boto3 dependency is dropped
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
            return pg_vars
        return {}
    except Exception:
        return {}


def get_mysql_connection_vars() -> dict:
    """Get MySQL connection vars from env or AWS Parameter Store."""
    required = ['MYSQL_HOST', 'MYSQL_DATABASE', 'MYSQL_USER']
    if all(os.environ.get(v) for v in required):
        return {k: os.environ[k] for k in _MYSQL_PARAM_MAP if os.environ.get(k)}

    # TODO(plan-03): remove SSM/boto3 fallback when boto3 dependency is dropped
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
            return mysql_vars
        return {}
    except Exception:
        return {}


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
