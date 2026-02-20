from utils.project_paths import MODEL_ID
"""SQL Transform Agent - Strands Framework"""
from pathlib import Path
from strands import Agent
from strands.models.bedrock import BedrockModel

from .tools.load_mapper_list import load_mapper_list, get_pending_transforms, read_sql_source
from .tools.split_mapper import split_mapper
from .tools.convert_sql import convert_sql
from .tools.assemble_mapper import assemble_mapper
from .tools.save_conversion import save_conversion_report
from .tools.metadata import generate_metadata, lookup_column_type


from strands.types.content import SystemContentBlock


def _load_system_prompt():
    """Load system prompt with static and dynamic rules."""
    # Base prompt
    prompt_path = Path(__file__).parent / "prompt.md"
    base_prompt = prompt_path.read_text(encoding='utf-8')
    
    # Static rules (general)
    static_rules_path = Path(__file__).parent.parent.parent / "reference" / "oracle_to_postgresql_rules.md"
    static_rules = static_rules_path.read_text(encoding='utf-8') if static_rules_path.exists() else ""
    
    # Dynamic rules (project-specific)
    dynamic_rules_path = Path(__file__).parent.parent.parent.parent / "output" / "strategy" / "transform_strategy.md"
    dynamic_rules = dynamic_rules_path.read_text(encoding='utf-8') if dynamic_rules_path.exists() else ""
    
    # 3-block caching: each block cached independently
    blocks = [
        # Block 1: Base prompt (rarely changes)
        SystemContentBlock(text=base_prompt),
        SystemContentBlock(cachePoint={"type": "default"}),
        # Block 2: General rules (static, never changes)
        SystemContentBlock(text=f"\n---\n\n## General Conversion Rules (Static)\n\n{static_rules}"),
        SystemContentBlock(cachePoint={"type": "default"}),
        # Block 3: Project strategy (dynamic, changes with learning)
        SystemContentBlock(text=f"\n---\n\n## Project-Specific Conversion Rules (Dynamic)\n\n{dynamic_rules}"),
        SystemContentBlock(cachePoint={"type": "default"}),
    ]
    
    return blocks


def create_sql_transform_agent() -> Agent:
    """Create and configure SQL Transform Agent."""
    model = BedrockModel(
        model_id=MODEL_ID,
        max_tokens=64000
    )

    return Agent(
        name="SQLTransform",
        model=model,
        system_prompt=_load_system_prompt(),
        tools=[load_mapper_list, get_pending_transforms, read_sql_source, split_mapper,
               convert_sql, assemble_mapper, save_conversion_report,
               generate_metadata, lookup_column_type]
    )


def run_transform():
    """Run SQL transformation."""
    print("🚀 SQL Transform Agent 시작...\n")

    # Clear previous results
    from .tools.convert_sql import clear_conversions
    clear_conversions()

    agent = create_sql_transform_agent()
    result = agent("모든 Mapper XML 파일의 Oracle SQL을 PostgreSQL로 변환해줘")

    print("\n" + "=" * 60)
    print(result)
    print("=" * 60)


if __name__ == "__main__":
    run_transform()
