"""Single SQL transform tool"""
import sqlite3
from strands import tool, Agent
from strands.models.bedrock import BedrockModel
from strands.types.content import SystemContentBlock
from utils.project_paths import DB_PATH, PROJECT_ROOT, MODEL_ID, load_prompt_text, get_target_db_display_name


def _load_transform_prompt():
    prompt_path = PROJECT_ROOT / "src" / "agents" / "sql_transform" / "prompt.md"
    return [
        SystemContentBlock(text=load_prompt_text(prompt_path)),
        SystemContentBlock(cachePoint={"type": "default"})
    ]


@tool
def transform_single_sql(mapper_file: str, sql_id: str) -> dict:
    """Transform a single SQL ID with Agent (direct execution).

    Creates a Transform Agent to convert the SQL immediately.
    Uses DB state to determine success (not stdout parsing).

    Args:
        mapper_file: Mapper file name (e.g., 'UserMapper.xml')
        sql_id: SQL statement ID

    Returns:
        Status dict with result (SUCCESS/FAIL)
    """
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM transform_target_list WHERE mapper_file = ? AND sql_id = ?",
            (mapper_file, sql_id)
        )
        row = cursor.fetchone()

    if not row:
        return {
            'status': 'error',
            'message': f'SQL ID not found: {mapper_file}/{sql_id}'
        }

    # Import tools
    from agents.sql_transform.tools.load_mapper_list import read_sql_source
    from agents.sql_transform.tools.convert_sql import convert_sql
    from agents.sql_transform.tools.metadata import lookup_column_type

    # Create Agent with callback_handler=None to suppress streaming output
    agent = Agent(
        name="SQLTransform",
        model=BedrockModel(model_id=MODEL_ID, max_tokens=32000),
        system_prompt=_load_transform_prompt(),
        tools=[read_sql_source, convert_sql, lookup_column_type],
        callback_handler=None,
    )

    target_db = get_target_db_display_name()
    agent(
        f"{mapper_file}의 {sql_id}를 {target_db}로 변환해줘.\n"
        f"1. read_sql_source로 원본 읽기\n"
        f"2. Oracle → {target_db} 변환 (4-Phase 규칙 적용)\n"
        f"3. convert_sql로 저장"
    )

    # Check DB state for result (not stdout parsing)
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT transformed FROM transform_target_list WHERE mapper_file = ? AND sql_id = ?",
            (mapper_file, sql_id)
        )
        row = cursor.fetchone()

    if row and row[0] == 'Y':
        return {
            'status': 'SUCCESS',
            'mapper_file': mapper_file,
            'sql_id': sql_id,
            'message': f'Transform completed for {mapper_file}/{sql_id}'
        }
    else:
        return {
            'status': 'FAIL',
            'mapper_file': mapper_file,
            'sql_id': sql_id,
            'message': f'Transform failed for {mapper_file}/{sql_id}'
        }
