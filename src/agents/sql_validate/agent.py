"""SQL Validate Agent - Strands Framework"""
from utils.project_paths import MODEL_ID, get_rules_path, load_prompt_text
from pathlib import Path
from botocore.config import Config as BotocoreConfig
from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.types.content import SystemContentBlock

from .tools.validate_tools import read_transform, set_validated, get_pending_validations
from agents.sql_transform.tools.load_mapper_list import read_sql_source
from agents.sql_transform.tools.convert_sql import convert_sql
from agents.sql_transform.tools.metadata import lookup_column_type


def _load_system_prompt():
    prompt_path = Path(__file__).parent / "prompt.md"
    rules_path = get_rules_path()
    strategy_path = Path(__file__).parents[3] / "output" / "strategy" / "transform_strategy.md"
    blocks = [
        SystemContentBlock(text=load_prompt_text(prompt_path)),
        SystemContentBlock(cachePoint={"type": "default"}),
        SystemContentBlock(text=rules_path.read_text(encoding='utf-8')),
        SystemContentBlock(cachePoint={"type": "default"}),
    ]
    if strategy_path.exists():
        blocks.append(SystemContentBlock(text=strategy_path.read_text(encoding='utf-8')))
        blocks.append(SystemContentBlock(cachePoint={"type": "default"}))
    return blocks


def create_sql_validate_agent(*, suppress_streaming: bool = False) -> Agent:
    from strands.agent.conversation_manager import SlidingWindowConversationManager

    model = BedrockModel(
        model_id=MODEL_ID,
        max_tokens=64000,
        boto_client_config=BotocoreConfig(read_timeout=300),
    )
    kwargs: dict = {
        "name": "SQLValidate",
        "model": model,
        "system_prompt": _load_system_prompt(),
        "tools": [get_pending_validations, read_sql_source, read_transform,
                  convert_sql, set_validated, lookup_column_type],
        # Safety net: trim old messages on context overflow (primary fix: small group size)
        "conversation_manager": SlidingWindowConversationManager(
            window_size=180000,
            should_truncate_results=True,
        ),
    }
    if suppress_streaming:
        kwargs["callback_handler"] = None
    return Agent(**kwargs)
