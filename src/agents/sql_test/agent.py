"""SQL Test Agent - Strands Framework"""
from utils.project_paths import MODEL_ID
from pathlib import Path
from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.types.content import SystemContentBlock

from .tools.test_tools import run_bulk_test, run_single_test, get_test_failures
from agents.sql_transform.tools.load_mapper_list import read_sql_source
from agents.sql_validate.tools.validate_tools import read_transform
from agents.sql_transform.tools.convert_sql import convert_sql
from agents.sql_transform.tools.metadata import lookup_column_type


def _load_system_prompt():
    prompt_path = Path(__file__).parent / "prompt.md"
    rules_path = Path(__file__).parents[2] / "reference" / "oracle_to_postgresql_rules.md"
    strategy_path = Path(__file__).parents[3] / "output" / "strategy" / "transform_strategy.md"
    blocks = [
        SystemContentBlock(text=prompt_path.read_text(encoding='utf-8')),
        SystemContentBlock(cachePoint={"type": "default"}),
        SystemContentBlock(text=rules_path.read_text(encoding='utf-8')),
        SystemContentBlock(cachePoint={"type": "default"}),
    ]
    if strategy_path.exists():
        blocks.append(SystemContentBlock(text=strategy_path.read_text(encoding='utf-8')))
        blocks.append(SystemContentBlock(cachePoint={"type": "default"}))
    return blocks


def create_sql_test_agent(*, suppress_streaming: bool = False) -> Agent:
    model = BedrockModel(
        model_id=MODEL_ID,
        max_tokens=64000
    )
    kwargs: dict = {
        "name": "SQLTest",
        "model": model,
        "system_prompt": _load_system_prompt(),
        "tools": [get_test_failures, read_sql_source, read_transform,
                  convert_sql, run_single_test, lookup_column_type],
    }
    if suppress_streaming:
        kwargs["callback_handler"] = None
    return Agent(**kwargs)
