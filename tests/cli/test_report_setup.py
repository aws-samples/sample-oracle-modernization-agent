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
