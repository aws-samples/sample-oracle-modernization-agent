import json


def test_status_json_returns_step_counts(oma_env, run_cli):
    code, stdout, _ = run_cli("status", "--json")
    assert code == 0
    data = json.loads(stdout)
    assert data["extracted"] == 4
    assert data["transformed"] == 1
    assert data["transform_complete"] is False


def test_unknown_command_exits_nonzero(oma_env, run_cli):
    code, _, _ = run_cli("no-such-command")
    assert code != 0
