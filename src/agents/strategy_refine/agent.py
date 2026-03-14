from utils.project_paths import MODEL_ID, get_rules_path, load_prompt_text
"""Strategy Refine Agent — pattern addition, dedup, compaction"""
from pathlib import Path
from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.types.content import SystemContentBlock

from .tools.refine_tools import read_strategy, get_feedback_patterns, append_patterns, write_strategy


def _load_system_prompt():
    prompt_path = Path(__file__).parent / "prompt.md"
    rules_path = get_rules_path()
    return [
        SystemContentBlock(text=load_prompt_text(prompt_path)),
        SystemContentBlock(cachePoint={"type": "default"}),
        SystemContentBlock(text=rules_path.read_text(encoding='utf-8')),
        SystemContentBlock(cachePoint={"type": "default"}),
    ]


def create_strategy_refine_agent(*, suppress_streaming: bool = False) -> Agent:
    kwargs: dict = {
        "name": "StrategyRefine",
        "model": BedrockModel(model_id=MODEL_ID, max_tokens=16000),
        "system_prompt": _load_system_prompt(),
        "tools": [read_strategy, get_feedback_patterns, append_patterns, write_strategy],
    }
    if suppress_streaming:
        kwargs["callback_handler"] = None
    return Agent(**kwargs)
