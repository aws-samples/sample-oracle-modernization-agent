from utils.project_paths import MODEL_ID, load_prompt_text
"""OMA Orchestrator Agent - Pipeline controller"""
from pathlib import Path
from strands import Agent, tool
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


def _load_system_prompt():
    prompt_path = Path(__file__).parent / "prompt.md"
    text = load_prompt_text(prompt_path)
    return [
        SystemContentBlock(text=text),
        SystemContentBlock(cachePoint={"type": "default"})
    ]


@tool
def delegate_to_review_manager(user_request: str) -> dict:
    """Delegate SQL review/comparison requests to ReviewManager Agent.

    Use this when user asks to:
    - Compare SQL conversions ("show diff", "compare selectUser")
    - Review failed conversions ("show me failed validations")
    - Approve conversions ("approve this conversion")
    - Generate reports ("create conversion report")
    - Suggest revisions ("use CONCAT instead")

    Args:
        user_request: User's review-related request

    Returns:
        Dict with status and ReviewManager's response
    """
    from agents.review_manager.agent import create_review_manager_agent

    review_manager = create_review_manager_agent()
    result = review_manager(user_request)

    # Convert AgentResult to dict for tool response
    return {
        'status': 'success',
        'response': str(result) if result else 'ReviewManager completed the request'
    }


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
            # Pipeline control (6 tools)
            check_setup, check_step_status, reset_step, run_step, get_summary, search_sql_ids,
            # Strategy management (3 tools)
            generate_project_strategy, refine_project_strategy, compact_strategy,
            # Single SQL operations (4 tools)
            transform_single_sql, validate_single_sql, run_single_test, test_and_fix_single_sql,
            # Review delegation (1 tool)
            delegate_to_review_manager
        ]
    )
