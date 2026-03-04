"""Single SQL validate tool"""
import sqlite3
from strands import tool, Agent
from strands.models.bedrock import BedrockModel
from strands.types.content import SystemContentBlock
from utils.project_paths import DB_PATH, PROJECT_ROOT, MODEL_ID


def _load_validate_prompt():
    prompt_path = PROJECT_ROOT / "src" / "agents" / "sql_validate" / "prompt.md"
    return [
        SystemContentBlock(text=prompt_path.read_text(encoding='utf-8')),
        SystemContentBlock(cachePoint={"type": "default"})
    ]


@tool
def validate_single_sql(mapper_file: str, sql_id: str) -> dict:
    """Validate a single SQL ID with Agent (auto-fix if needed).

    Creates a Validate Agent to check the SQL and fix if necessary.
    Uses DB state to determine result (not stdout parsing).

    Args:
        mapper_file: Mapper file name (e.g., 'UserMapper.xml')
        sql_id: SQL statement ID

    Returns:
        Status dict with result (PASS/FIXED/FAIL)
    """
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, transformed, updated_at FROM transform_target_list WHERE mapper_file = ? AND sql_id = ?",
            (mapper_file, sql_id)
        )
        row = cursor.fetchone()

    if not row:
        return {
            'status': 'error',
            'message': f'SQL ID not found: {mapper_file}/{sql_id}'
        }

    if row[1] != 'Y':
        return {
            'status': 'error',
            'message': f'SQL ID not transformed yet: {mapper_file}/{sql_id}. Run transform first.'
        }

    # Save updated_at before agent run to detect if convert_sql was called (FIXED)
    updated_at_before = row[2]

    # Import tools
    from agents.sql_validate.tools.validate_tools import read_transform, set_validated
    from agents.sql_transform.tools.load_mapper_list import read_sql_source
    from agents.sql_transform.tools.convert_sql import convert_sql
    from agents.sql_transform.tools.metadata import lookup_column_type

    # Create Agent with callback_handler=None to suppress streaming output
    agent = Agent(
        name="SQLValidate",
        model=BedrockModel(model_id=MODEL_ID, max_tokens=32000),
        system_prompt=_load_validate_prompt(),
        tools=[read_sql_source, read_transform, convert_sql, set_validated, lookup_column_type],
        callback_handler=None,
    )

    agent(
        f"{mapper_file}의 {sql_id}를 검증해줘.\n"
        f"1. read_sql_source로 원본 읽기\n"
        f"2. read_transform으로 변환본 읽기\n"
        f"3. 비교 검증\n"
        f"4. PASS면 set_validated, FAIL이면 convert_sql로 수정 후 set_validated"
    )

    # Check DB state for result
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT validated, updated_at FROM transform_target_list WHERE mapper_file = ? AND sql_id = ?",
            (mapper_file, sql_id)
        )
        row = cursor.fetchone()

    if not row or row[0] != 'Y':
        return {
            'status': 'FAIL',
            'mapper_file': mapper_file,
            'sql_id': sql_id,
            'message': f'Validation failed for {mapper_file}/{sql_id}'
        }

    # Determine PASS vs FIXED: if updated_at changed, convert_sql was called
    updated_at_after = row[1]
    if updated_at_after != updated_at_before:
        return {
            'status': 'FIXED',
            'mapper_file': mapper_file,
            'sql_id': sql_id,
            'message': f'Validation failed but fixed for {mapper_file}/{sql_id}'
        }
    else:
        return {
            'status': 'PASS',
            'mapper_file': mapper_file,
            'sql_id': sql_id,
            'message': f'Validation passed for {mapper_file}/{sql_id}'
        }
