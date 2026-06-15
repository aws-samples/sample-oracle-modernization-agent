"""Tests for oma test-exec command."""


def test_test_exec_without_db_connection_info_fails_gracefully(oma_env, run_cli):
    """No PG connection info in seed DB -> clear error, no stacktrace."""
    code, stdout, stderr = run_cli("test-exec")
    assert code == 1
    assert "connection" in stderr.lower() or "접속" in stderr


def test_test_exec_phase_flag_parses(oma_env, run_cli):
    """--phase flag is accepted (still fails on missing conn, but arg parsing works)."""
    code, _, _ = run_cli("test-exec", "--phase", "0")
    assert code == 1  # fails on missing connection info, but flag parsing succeeded


def test_test_exec_json_flag_parses(oma_env, run_cli):
    """--json flag is accepted."""
    code, _, _ = run_cli("test-exec", "--json")
    assert code == 1  # fails on missing connection info


def test_test_exec_only_flag_parses(oma_env, run_cli):
    """--only flag is accepted."""
    code, _, _ = run_cli("test-exec", "--only", "UserMapper.xml:selectUser")
    assert code == 1  # fails on missing connection info
