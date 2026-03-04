"""Single SQL test with auto-fix"""
import sqlite3
from strands import tool, Agent
from strands.models.bedrock import BedrockModel
from strands.types.content import SystemContentBlock
from utils.project_paths import PROJECT_ROOT, DB_PATH, MODEL_ID
from .test_tools import run_single_test


def _load_test_prompt():
    prompt_path = PROJECT_ROOT / "src" / "agents" / "sql_test" / "prompt.md"
    return [
        SystemContentBlock(text=prompt_path.read_text(encoding='utf-8')),
        SystemContentBlock(cachePoint={"type": "default"})
    ]


@tool
def test_and_fix_single_sql(mapper_file: str, sql_id: str) -> dict:
    """Test a single SQL ID and auto-fix if it fails.

    1. Runs the SQL test against PostgreSQL
    2. If it fails, creates a Test Agent to analyze and fix the error
    3. Checks DB state to determine final result (not stdout parsing)

    Args:
        mapper_file: Mapper file name (e.g., 'UserMapper.xml')
        sql_id: SQL statement ID

    Returns:
        Status dict with result (SUCCESS/FIXED/FAIL)
    """
    # First attempt: run test
    result = run_single_test(mapper_file, sql_id)

    if result['status'] == 'SUCCESS':
        return {
            'status': 'SUCCESS',
            'mapper_file': mapper_file,
            'sql_id': sql_id,
            'message': f'Test passed for {mapper_file}/{sql_id}'
        }

    if result['status'] != 'FAIL':
        return result  # Error or skipped

    # Test failed - use Agent to fix
    error_msg = result.get('error', 'Unknown error')

    # Import tools
    from agents.sql_transform.tools.load_mapper_list import read_sql_source
    from agents.sql_validate.tools.validate_tools import read_transform
    from agents.sql_transform.tools.convert_sql import convert_sql
    from agents.sql_transform.tools.metadata import lookup_column_type

    # Create Agent with callback_handler=None to suppress streaming output
    agent = Agent(
        name="SQLTest",
        model=BedrockModel(model_id=MODEL_ID, max_tokens=32000),
        system_prompt=_load_test_prompt(),
        tools=[read_sql_source, read_transform, convert_sql, run_single_test, lookup_column_type],
        callback_handler=None,
    )

    agent(
        f"{mapper_file}의 {sql_id}가 PostgreSQL 테스트에서 실패했습니다.\n\n"
        f"=== 에러 메시지 ===\n{error_msg}\n\n"
        f"=== 수정 절차 ===\n"
        f"1. read_transform으로 현재 PostgreSQL SQL 읽기\n"
        f"2. 에러 메시지 분석\n"
        f"3. convert_sql로 수정된 SQL 저장\n"
        f"4. run_single_test로 재테스트\n"
        f"5. 여전히 실패하면 1회 더 시도, 그래도 실패하면 MANUAL_REVIEW"
    )

    # Check DB state for result — if tested='Y', agent succeeded
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT tested FROM transform_target_list WHERE mapper_file = ? AND sql_id = ?",
            (mapper_file, sql_id)
        )
        row = cursor.fetchone()

    if row and row[0] == 'Y':
        return {
            'status': 'FIXED',
            'mapper_file': mapper_file,
            'sql_id': sql_id,
            'message': f'Test failed but fixed for {mapper_file}/{sql_id}'
        }
    else:
        return {
            'status': 'FAIL',
            'mapper_file': mapper_file,
            'sql_id': sql_id,
            'message': f'Test failed and could not fix {mapper_file}/{sql_id}. Manual review needed.',
            'error': error_msg
        }
