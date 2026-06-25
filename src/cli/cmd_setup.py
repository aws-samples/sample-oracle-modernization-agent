"""oma setup -- configure OMA environment (interactive or non-interactive).

Non-interactive mode (--non-interactive) stores provided flags as DB properties
without prompting. Interactive mode mirrors run_setup.py behavior but omits
OMA_MODEL_ID/OMA_LITE_MODEL_ID (no longer needed in CLI-only architecture).
"""
import sys


# Connection flag → DB property key. Passwords are intentionally excluded —
# they go via env vars (PGPASSWORD etc.) or interactive getpass only.
_CONN_FLAG_MAP = {
    "pg_host": "PGHOST", "pg_port": "PGPORT",
    "pg_database": "PGDATABASE", "pg_user": "PGUSER",
    "mysql_host": "MYSQL_HOST", "mysql_port": "MYSQL_PORT",
    "mysql_database": "MYSQL_DATABASE", "mysql_user": "MYSQL_USER",
    "oracle_host": "ORACLE_HOST", "oracle_port": "ORACLE_PORT",
    "oracle_service": "ORACLE_SERVICE_NAME", "oracle_user": "ORACLE_SVC_USER",
}


def register(sub):
    p = sub.add_parser("setup", help="Configure OMA (interactive or --non-interactive)")
    p.add_argument("--source", default="", help="Java source root -> JAVA_SOURCE_FOLDER")
    p.add_argument("--target-db", choices=["postgresql", "mysql"], default="",
                   help="Target DBMS type")
    p.add_argument("--non-interactive", action="store_true",
                   help="Set properties from flags without prompting")

    # Connection info (optional, for Test phase). Passwords NOT accepted as flags —
    # use env vars (PGPASSWORD/MYSQL_PASSWORD/ORACLE_SVC_PASSWORD) or interactive setup.
    pg = p.add_argument_group("PostgreSQL target (optional)")
    pg.add_argument("--pg-host", default="")
    pg.add_argument("--pg-port", default="")
    pg.add_argument("--pg-database", default="")
    pg.add_argument("--pg-user", default="")

    my = p.add_argument_group("MySQL target (optional)")
    my.add_argument("--mysql-host", default="")
    my.add_argument("--mysql-port", default="")
    my.add_argument("--mysql-database", default="")
    my.add_argument("--mysql-user", default="")

    ora = p.add_argument_group("Oracle source (optional)")
    ora.add_argument("--oracle-host", default="")
    ora.add_argument("--oracle-port", default="")
    ora.add_argument("--oracle-service", default="")
    ora.add_argument("--oracle-user", default="")

    p.set_defaults(func=run)


def _init_db():
    """Create DB and all tables via SQLAlchemy if not exists."""
    from utils.project_paths import OUTPUT_DIR, DB_PATH
    from sqlalchemy import create_engine
    from core.models import Base

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{DB_PATH}", echo=False,
                           connect_args={"timeout": 10})
    Base.metadata.create_all(engine)
    engine.dispose()


def _set_property(key: str, value: str, description: str = ""):
    """UPSERT a property into the DB."""
    import sqlite3
    from utils.project_paths import DB_PATH

    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        conn.execute("""
            INSERT INTO properties (key, value, description) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = CURRENT_TIMESTAMP
        """, (key, value, description, value))
        conn.commit()


def _get_property(key: str):
    """Get a property value or None."""
    import sqlite3
    from utils.project_paths import DB_PATH

    if not DB_PATH.exists():
        return None
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM properties WHERE key = ?", (key,))
        row = cursor.fetchone()
    return row[0] if row else None


def _run_non_interactive(args) -> int:
    """Store provided flags as DB properties without prompting."""
    _init_db()

    if args.source:
        _set_property("JAVA_SOURCE_FOLDER", args.source, "Java source code root path")
    if args.target_db:
        _set_property("TARGET_DBMS_TYPE", args.target_db, "Target database type")

    # Connection flags → properties (only those provided)
    conn_set = []
    for flag, prop_key in _CONN_FLAG_MAP.items():
        value = getattr(args, flag, "")
        if value:
            _set_property(prop_key, value, "Set via 'oma setup' connection flag")
            conn_set.append((prop_key, value))

    # Print summary
    print("setup: non-interactive complete", file=sys.stderr)
    if args.source:
        print(f"  JAVA_SOURCE_FOLDER={args.source}", file=sys.stderr)
    if args.target_db:
        print(f"  TARGET_DBMS_TYPE={args.target_db}", file=sys.stderr)
    for prop_key, value in conn_set:
        print(f"  {prop_key}={value}", file=sys.stderr)
    if conn_set:
        # Passwords are never set via flags — remind where they go.
        print("  (passwords: set via env vars — PGPASSWORD/MYSQL_PASSWORD/ORACLE_SVC_PASSWORD)",
              file=sys.stderr)
    return 0


def _run_interactive(args) -> int:
    """Interactive setup — prompts for values. Mirrors run_setup.py minus model config."""
    import getpass
    from pathlib import Path
    from utils.project_paths import OUTPUT_DIR, DB_PATH

    print("OMA Environment Setup\n", file=sys.stderr)
    print(f"  Output dir: {OUTPUT_DIR}", file=sys.stderr)

    _init_db()
    print(f"  DB: {DB_PATH}", file=sys.stderr)

    # -- Project settings --
    print("\nProject settings:\n", file=sys.stderr)

    # JAVA_SOURCE_FOLDER
    current_source = _get_property("JAVA_SOURCE_FOLDER") or ""
    prompt_src = f"  JAVA_SOURCE_FOLDER [{current_source}]: " if current_source else "  JAVA_SOURCE_FOLDER: "
    java_source = input(prompt_src).strip() or current_source
    if not java_source:
        print("  ERROR: JAVA_SOURCE_FOLDER required", file=sys.stderr)
        return 1

    # TARGET_DBMS_TYPE
    current_target = _get_property("TARGET_DBMS_TYPE") or "postgresql"
    prompt_tgt = f"  TARGET_DBMS_TYPE (postgresql/mysql) [{current_target}]: "
    target_dbms = input(prompt_tgt).strip() or current_target
    if target_dbms not in ("postgresql", "mysql"):
        print(f"  ERROR: invalid target DB: {target_dbms}", file=sys.stderr)
        return 1

    # Save
    _set_property("JAVA_SOURCE_FOLDER", java_source, "Java source code root path")
    _set_property("SOURCE_DBMS_TYPE", "oracle", "Source database type")
    _set_property("TARGET_DBMS_TYPE", target_dbms, "Target database type")

    # DB connection info — optional
    print(f"\n  DB connection info is only needed for Test phase.", file=sys.stderr)
    setup_db = input("  Configure DB connections now? (y/n) [n]: ").strip().lower()
    if setup_db == "y":
        _setup_connections(target_dbms)

    print(f"\nSetup complete. DB: {DB_PATH}", file=sys.stderr)
    return 0


def _setup_connections(target_dbms: str):
    """Interactive DB connection prompts (Oracle + Target)."""
    import getpass

    print("\n  Oracle (Source DB):", file=sys.stderr)
    ora_host = input("    ORACLE_HOST: ").strip()
    ora_port = input("    ORACLE_PORT [1521]: ").strip() or "1521"
    ora_service = input("    ORACLE_SERVICE_NAME: ").strip()
    ora_user = input("    ORACLE_SVC_USER: ").strip()
    ora_password = getpass.getpass("    ORACLE_SVC_PASSWORD: ")

    if ora_host:
        _set_property("ORACLE_HOST", ora_host, "Oracle host")
    if ora_port:
        _set_property("ORACLE_PORT", ora_port, "Oracle port")
    if ora_service:
        _set_property("ORACLE_SERVICE_NAME", ora_service, "Oracle service name")
    if ora_user:
        _set_property("ORACLE_SVC_USER", ora_user, "Oracle user")
    if ora_password:
        _set_property("ORACLE_SVC_PASSWORD", ora_password, "Oracle password")

    if target_dbms == "postgresql":
        print("\n  PostgreSQL (Target DB):", file=sys.stderr)
        pg_host = input("    PGHOST: ").strip()
        pg_port = input("    PGPORT [5432]: ").strip() or "5432"
        pg_db = input("    PGDATABASE: ").strip()
        pg_user = input("    PGUSER: ").strip()
        pg_pass = getpass.getpass("    PGPASSWORD: ")
        if pg_host:
            _set_property("PGHOST", pg_host, "PostgreSQL host")
        if pg_port:
            _set_property("PGPORT", pg_port, "PostgreSQL port")
        if pg_db:
            _set_property("PGDATABASE", pg_db, "PostgreSQL database")
        if pg_user:
            _set_property("PGUSER", pg_user, "PostgreSQL user")
        if pg_pass:
            _set_property("PGPASSWORD", pg_pass, "PostgreSQL password")
    else:
        print("\n  MySQL (Target DB):", file=sys.stderr)
        my_host = input("    MYSQL_HOST: ").strip()
        my_port = input("    MYSQL_PORT [3306]: ").strip() or "3306"
        my_db = input("    MYSQL_DATABASE: ").strip()
        my_user = input("    MYSQL_USER: ").strip()
        my_pass = getpass.getpass("    MYSQL_PASSWORD: ")
        if my_host:
            _set_property("MYSQL_HOST", my_host, "MySQL host")
        if my_port:
            _set_property("MYSQL_PORT", my_port, "MySQL port")
        if my_db:
            _set_property("MYSQL_DATABASE", my_db, "MySQL database")
        if my_user:
            _set_property("MYSQL_USER", my_user, "MySQL user")
        if my_pass:
            _set_property("MYSQL_PASSWORD", my_pass, "MySQL password")


def run(args) -> int:
    if args.non_interactive:
        return _run_non_interactive(args)
    return _run_interactive(args)
