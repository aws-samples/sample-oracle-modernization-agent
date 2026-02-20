from utils.project_paths import MODEL_ID
"""OMA Orchestrator Agent - Pipeline controller"""
from pathlib import Path
from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.types.content import SystemContentBlock

from .tools.orchestrator_tools import (
    check_setup, check_step_status, reset_step, run_step, get_summary, search_sql_ids,
    generate_project_strategy, refine_project_strategy, compact_strategy
)
from agents.sql_test.tools.test_tools import run_single_test
from agents.sql_test.tools.single_test_fix import test_and_fix_single_sql
from agents.sql_transform.tools.single_transform import transform_single_sql
from agents.sql_validate.tools.single_validate import validate_single_sql
from .tools.diff_tools import (
    show_sql_diff, generate_diff_report, get_review_candidates,
    approve_conversion, suggest_revision
)


def _load_system_prompt():
    prompt_path = Path(__file__).parent / "prompt.md"
    text = prompt_path.read_text(encoding='utf-8')
    return [
        SystemContentBlock(text=text),
        SystemContentBlock(cachePoint={"type": "default"})
    ]


def create_orchestrator_agent() -> Agent:
    model = BedrockModel(
        model_id=MODEL_ID,
        max_tokens=32000
    )
    return Agent(
        name="OMAOrchestrator",
        model=model,
        system_prompt=_load_system_prompt(),
        tools=[
            check_setup, check_step_status, reset_step, run_step, get_summary, search_sql_ids,
            generate_project_strategy, refine_project_strategy, compact_strategy,
            transform_single_sql, validate_single_sql, run_single_test, test_and_fix_single_sql,
            show_sql_diff, generate_diff_report, get_review_candidates,
            approve_conversion, suggest_revision
        ]
    )
