from utils.project_paths import MODEL_ID
"""Strategy Refine Agent — pattern addition, dedup, compaction"""
from pathlib import Path
from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.types.content import SystemContentBlock

from .tools.refine_tools import read_strategy, get_feedback_patterns, append_patterns, write_strategy


def _load_system_prompt():
    prompt_path = Path(__file__).parent / "prompt.md"
    rules_path = Path(__file__).parents[2] / "reference" / "oracle_to_postgresql_rules.md"
    return [
        SystemContentBlock(text=prompt_path.read_text(encoding='utf-8')),
        SystemContentBlock(cachePoint={"type": "default"}),
        SystemContentBlock(text=rules_path.read_text(encoding='utf-8')),
        SystemContentBlock(cachePoint={"type": "default"}),
    ]


def create_strategy_refine_agent() -> Agent:
    return Agent(
        name="StrategyRefine",
        model=BedrockModel(
            model_id=MODEL_ID,
            max_tokens=16000
        ),
        system_prompt=_load_system_prompt(),
        tools=[read_strategy, get_feedback_patterns, append_patterns, write_strategy]
    )
