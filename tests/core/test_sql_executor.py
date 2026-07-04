"""Tests for core.sql_executor — SQL extraction, parameter handling, and command building."""
import os
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from core.sql_executor import (
    SQLExecutor, SQLResult, extract_sql_from_xml,
    _MYBATIS_TAG_RE, _PARAM_RE, _DOLLAR_PARAM_RE,
)


# ── extract_sql_from_xml ──

@pytest.fixture
def xml_file(tmp_path):
    """Create a sample MyBatis XML file."""
    content = '''<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="com.example">
  <select id="findUser" resultType="User">
    SELECT u.id, u.name
    FROM users u
    <where>
      <if test="name != null">
        AND u.name = #{name}::text
      </if>
    </where>
    ORDER BY u.id
  </select>

  <insert id="addUser">
    INSERT INTO users (name, email)
    VALUES (#{name}, #{email}::varchar)
  </insert>
</mapper>'''
    f = tmp_path / "UserMapper.xml"
    f.write_text(content)
    return str(f)


def test_extract_sql_from_xml_select(xml_file):
    result = extract_sql_from_xml(xml_file)
    assert result is not None
    sql_type, sql = result
    assert sql_type == 'select'
    assert 'SELECT' in sql
    assert '#{' not in sql  # params replaced
    assert 'NULL::text' in sql  # cast preserved


def test_extract_sql_from_xml_with_sql_id(xml_file):
    result = extract_sql_from_xml(xml_file, sql_id='addUser')
    assert result is not None
    sql_type, sql = result
    assert sql_type == 'insert'
    assert 'INSERT INTO users' in sql


def test_extract_sql_from_xml_with_params(xml_file):
    result = extract_sql_from_xml(xml_file, params={'name': "Alice", 'email': 'a@b.com'},
                                   sql_id='addUser')
    assert result is not None
    _, sql = result
    assert "'Alice'" in sql
    assert "'a@b.com'::varchar" in sql


def test_extract_sql_from_xml_nonexistent_file():
    assert extract_sql_from_xml("/no/such/path.xml") is None


def test_extract_sql_from_xml_no_match(tmp_path):
    f = tmp_path / "empty.xml"
    f.write_text("<mapper></mapper>")
    assert extract_sql_from_xml(str(f)) is None


def test_extract_sql_cdata(tmp_path):
    """CDATA sections are stripped properly."""
    content = '''<mapper>
  <select id="q1">
    <![CDATA[SELECT * FROM t WHERE a < 10]]>
  </select>
</mapper>'''
    f = tmp_path / "cdata.xml"
    f.write_text(content)
    result = extract_sql_from_xml(str(f))
    assert result is not None
    _, sql = result
    assert 'SELECT * FROM t WHERE a < 10' in sql
    assert 'CDATA' not in sql


def test_extract_sql_dollar_param(tmp_path):
    content = '''<mapper>
  <select id="q1">SELECT * FROM ${tableName} WHERE id = #{id}</select>
</mapper>'''
    f = tmp_path / "dollar.xml"
    f.write_text(content)
    result = extract_sql_from_xml(str(f))
    _, sql = result
    assert "'1'" in sql  # ${} replaced with '1'
    assert 'NULL' in sql  # #{} replaced with NULL


# ── SQLExecutor command building ──

def test_cli_cmd_postgresql():
    executor = SQLExecutor(db_type='postgresql')
    cmd = executor._cli_cmd()
    assert cmd == ['psql']


def test_cli_cmd_mysql(monkeypatch):
    monkeypatch.setenv('MYSQL_USER', 'root')
    monkeypatch.setenv('MYSQL_DATABASE', 'testdb')
    executor = SQLExecutor(db_type='mysql')
    cmd = executor._cli_cmd()
    assert 'mysql' in cmd
    assert '--batch' in cmd


def test_cli_cmd_oracle():
    executor = SQLExecutor(db_type='oracle')
    cmd = executor._cli_cmd()
    assert cmd == ['sqlplus', '-S', '/nolog']


def test_oracle_connect_preamble_no_password_in_cmd(monkeypatch):
    """Oracle credentials are in stdin preamble, not CLI args."""
    monkeypatch.setenv('ORACLE_USER', 'scott')
    monkeypatch.setenv('ORACLE_PASSWORD', 'tiger')
    monkeypatch.setenv('ORACLE_HOST', 'db.example.com')
    monkeypatch.setenv('ORACLE_PORT', '1521')
    monkeypatch.setenv('ORACLE_SID', 'ORCL')
    monkeypatch.setenv('ORACLE_CONN_TYPE', 'service')

    executor = SQLExecutor(db_type='oracle')
    preamble = executor._oracle_connect_preamble()
    assert 'CONNECT scott/tiger@db.example.com:1521/ORCL' in preamble

    # CLI command must NOT contain credentials
    cmd = executor._cli_cmd()
    for arg in cmd:
        assert 'scott' not in arg
        assert 'tiger' not in arg


def test_build_env_pg_password_in_env(monkeypatch):
    monkeypatch.setenv('PGPASSWORD', 'secret123')
    monkeypatch.setenv('PGHOST', 'localhost')
    executor = SQLExecutor(db_type='postgresql')
    env = executor._build_env()
    assert env['PGPASSWORD'] == 'secret123'


def test_build_env_mysql_password_in_env(monkeypatch):
    monkeypatch.setenv('MYSQL_PASSWORD', 'my_secret')
    executor = SQLExecutor(db_type='mysql')
    env = executor._build_env()
    assert env['MYSQL_PWD'] == 'my_secret'


# ── Result parsing ──

def test_parse_marker_output():
    executor = SQLExecutor(db_type='postgresql')
    output = (
        "preamble stuff\n"
        "=== mapper/q1 ===\n"
        "QUERY PLAN\nSeq Scan on users\n"
        "=== mapper/q2 ===\n"
        "ERROR: relation \"foo\" does not exist\n"
    )
    parsed = executor._parse_marker_output(output)
    assert 'mapper/q1' in parsed
    assert 'QUERY PLAN' in parsed['mapper/q1']
    assert 'mapper/q2' in parsed
    assert 'ERROR' in parsed['mapper/q2']


def test_is_error_pg():
    executor = SQLExecutor(db_type='postgresql')
    is_err, msg, state = executor._is_error("ERROR: column \"x\" does not exist\nSQLSTATE: 42703")
    assert is_err is True
    assert 'column' in msg
    assert state == '42703'


def test_is_error_oracle():
    executor = SQLExecutor(db_type='oracle')
    is_err, msg, _ = executor._is_error("ORA-00942: table or view does not exist")
    assert is_err is True
    assert 'ORA-00942' in msg


def test_is_error_clean():
    executor = SQLExecutor(db_type='postgresql')
    is_err, _, _ = executor._is_error("(3 rows)")
    assert is_err is False


def test_count_rows_pg():
    executor = SQLExecutor(db_type='postgresql')
    assert executor._count_rows("id | name\n1 | foo\n2 | bar\n(2 rows)") == 2


def test_count_rows_oracle():
    executor = SQLExecutor(db_type='oracle')
    assert executor._count_rows("data\n5 rows selected.") == 5


# ── Batch execution with mocked subprocess ──

def test_explain_batch_mocked(tmp_path, monkeypatch):
    """explain_batch invokes subprocess and parses results."""
    # Create a minimal XML
    xml = tmp_path / "T.xml"
    xml.write_text('<mapper><select id="q1">SELECT 1</select></mapper>')

    items = [{'mapper_file': 'T.xml', 'sql_id': 'q1', 'sql_type': 'select',
              'target_file': str(xml)}]

    fake_proc = MagicMock()
    fake_proc.stdout = "=== T.xml/q1 ===\nQUERY PLAN\nSeq Scan\n"
    fake_proc.stderr = ""
    fake_proc.returncode = 0
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake_proc)

    monkeypatch.setenv('PGHOST', 'localhost')
    monkeypatch.setenv('PGDATABASE', 'test')
    monkeypatch.setenv('PGUSER', 'u')

    executor = SQLExecutor(db_type='postgresql')
    results = executor.explain_batch(items)
    assert len(results) == 1
    assert results[0].status == 'PASS'


def test_execute_single_oracle_nolog(monkeypatch):
    """execute_single for Oracle uses /nolog and passes credentials via stdin."""
    monkeypatch.setenv('ORACLE_USER', 'scott')
    monkeypatch.setenv('ORACLE_PASSWORD', 'tiger')
    monkeypatch.setenv('ORACLE_HOST', 'orahost')
    monkeypatch.setenv('ORACLE_PORT', '1521')
    monkeypatch.setenv('ORACLE_SID', 'XE')
    monkeypatch.setenv('ORACLE_CONN_TYPE', 'service')

    captured_args = {}

    def mock_run(*args, **kwargs):
        captured_args['cmd'] = args[0] if args else kwargs.get('args')
        captured_args['input'] = kwargs.get('input', '')
        proc = MagicMock()
        proc.stdout = "(1 row)"
        proc.stderr = ""
        return proc

    monkeypatch.setattr("subprocess.run", mock_run)

    executor = SQLExecutor(db_type='oracle')
    executor.execute_single("SELECT 1 FROM dual")

    # Verify /nolog in command
    assert '/nolog' in captured_args['cmd']
    # Verify CONNECT in stdin
    assert 'CONNECT scott/tiger@orahost:1521/XE' in captured_args['input']
    # Verify password NOT in command args
    for arg in captured_args['cmd']:
        assert 'tiger' not in arg
