"""SQL Review Agent — rule compliance checker (single + multi-perspective)"""
from pathlib import Path
from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.types.content import SystemContentBlock

from utils.project_paths import MODEL_ID, get_rules_path, load_prompt_text
from .tools.review_tools import get_pending_reviews, set_reviewed
from agents.sql_transform.tools.load_mapper_list import read_sql_source
from agents.sql_validate.tools.validate_tools import read_transform

# Multi-perspective review agents
from .perspectives import (
    create_syntax_review_agent,
    create_equivalence_review_agent,
    run_multi_perspective_review,
)


def _load_system_prompt():
    prompt_path = Path(__file__).parent / "prompt.md"
    rules_path = get_rules_path()
    blocks = [
        SystemContentBlock(text=load_prompt_text(prompt_path)),
        SystemContentBlock(cachePoint={"type": "default"}),
        SystemContentBlock(text=rules_path.read_text(encoding='utf-8')),
        SystemContentBlock(cachePoint={"type": "default"}),
    ]
    return blocks


def create_sql_review_agent() -> Agent:
    """Create the original single-perspective review agent (backward compatible)."""
    model = BedrockModel(
        model_id=MODEL_ID,
        max_tokens=32000
    )
    return Agent(
        name="SQLReview",
        model=model,
        system_prompt=_load_system_prompt(),
        tools=[get_pending_reviews, read_sql_source, read_transform, set_reviewed]
    )
