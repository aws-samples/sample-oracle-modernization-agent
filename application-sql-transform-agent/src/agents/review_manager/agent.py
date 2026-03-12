"""ReviewManager Agent - SQL comparison and approval"""
from pathlib import Path
from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.types.content import SystemContentBlock
from utils.project_paths import MODEL_ID

from .tools.diff_tools import (
    show_sql_diff, generate_diff_report, get_review_candidates,
    approve_conversion, suggest_revision
)


def _load_system_prompt():
    """Load ReviewManager system prompt"""
    prompt_path = Path(__file__).parent / "prompt.md"
    text = prompt_path.read_text(encoding='utf-8')
    return [
        SystemContentBlock(text=text),
        SystemContentBlock(cachePoint={"type": "default"})
    ]


def create_review_manager_agent() -> Agent:
    """Create ReviewManager Agent for SQL review and approval"""
    model = BedrockModel(
        model_id=MODEL_ID,
        max_tokens=16000
    )
    return Agent(
        name="ReviewManager",
        model=model,
        system_prompt=_load_system_prompt(),
        tools=[
            show_sql_diff,
            generate_diff_report,
            get_review_candidates,
            approve_conversion,
            suggest_revision
        ]
    )
