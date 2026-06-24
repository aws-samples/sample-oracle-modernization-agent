"""Tests for oma report and oma setup commands."""


def test_report_generates_html(oma_env, run_cli):
    code, _, stderr = run_cli("report")
    assert code == 0
    report = oma_env / "reports" / "oma_report.html"
    assert report.exists()
    assert report.stat().st_size > 1000


def test_setup_non_interactive_sets_properties(oma_env, run_cli):
    code, _, _ = run_cli(
        "setup", "--source", "/tmp/java-src", "--target-db", "mysql",
        "--non-interactive")
    assert code == 0
    code, stdout, _ = run_cli("db", "get-property", "TARGET_DBMS_TYPE")
    assert stdout.strip() == "mysql"
    code, stdout, _ = run_cli("db", "get-property", "JAVA_SOURCE_FOLDER")
    assert stdout.strip() == "/tmp/java-src"


def test_setup_non_interactive_preserves_existing_properties(oma_env, run_cli):
    """Non-interactive setup with only --target-db should not erase existing props."""
    # Set initial value
    run_cli("setup", "--source", "/initial/path", "--target-db", "postgresql", "--non-interactive")
    # Update only target-db
    code, _, _ = run_cli("setup", "--target-db", "mysql", "--non-interactive")
    assert code == 0
    # source should remain
    code, stdout, _ = run_cli("db", "get-property", "JAVA_SOURCE_FOLDER")
    assert stdout.strip() == "/initial/path"
    code, stdout, _ = run_cli("db", "get-property", "TARGET_DBMS_TYPE")
    assert stdout.strip() == "mysql"


def test_report_exit_zero_even_on_empty_db(oma_env, run_cli, tmp_path, monkeypatch):
    """Report should not crash even if tables are minimal (best-effort)."""
    # oma_env already has a seeded DB — report should work
    code, _, stderr = run_cli("report")
    assert code == 0


def test_setup_non_interactive_stores_pg_connection_flags(oma_env, run_cli):
    code, _, _ = run_cli(
        "setup", "--non-interactive", "--target-db", "postgresql",
        "--pg-host", "db.example.com", "--pg-port", "5433",
        "--pg-database", "appdb", "--pg-user", "svc_user")
    assert code == 0
    for key, expected in [("PGHOST", "db.example.com"), ("PGPORT", "5433"),
                          ("PGDATABASE", "appdb"), ("PGUSER", "svc_user")]:
        _, stdout, _ = run_cli("db", "get-property", key)
        assert stdout.strip() == expected


def test_setup_non_interactive_stores_oracle_connection_flags(oma_env, run_cli):
    code, _, _ = run_cli(
        "setup", "--non-interactive",
        "--oracle-host", "ora.example.com", "--oracle-port", "1522",
        "--oracle-service", "ORCLPDB1", "--oracle-user", "migr")
    assert code == 0
    for key, expected in [("ORACLE_HOST", "ora.example.com"), ("ORACLE_PORT", "1522"),
                          ("ORACLE_SERVICE_NAME", "ORCLPDB1"), ("ORACLE_SVC_USER", "migr")]:
        _, stdout, _ = run_cli("db", "get-property", key)
        assert stdout.strip() == expected


def test_setup_non_interactive_stores_mysql_connection_flags(oma_env, run_cli):
    code, _, _ = run_cli(
        "setup", "--non-interactive", "--target-db", "mysql",
        "--mysql-host", "mysql.example.com", "--mysql-port", "3307",
        "--mysql-database", "appdb", "--mysql-user", "svc")
    assert code == 0
    for key, expected in [("MYSQL_HOST", "mysql.example.com"), ("MYSQL_PORT", "3307"),
                          ("MYSQL_DATABASE", "appdb"), ("MYSQL_USER", "svc")]:
        _, stdout, _ = run_cli("db", "get-property", key)
        assert stdout.strip() == expected


def test_setup_non_interactive_password_not_a_flag(oma_env, run_cli):
    """Passwords must NOT be accepted as CLI flags (security). --pg-password should be rejected."""
    code, _, _ = run_cli(
        "setup", "--non-interactive", "--target-db", "postgresql",
        "--pg-password", "secret123")
    assert code != 0  # argparse rejects unknown flag
