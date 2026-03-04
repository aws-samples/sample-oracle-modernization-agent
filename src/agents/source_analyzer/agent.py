"""Source Analyzer Agent - Strands Framework"""
from pathlib import Path
from strands import Agent
from strands.models.bedrock import BedrockModel
from utils.project_paths import MODEL_ID

# Import tools - analysis
from .tools.db_manager import get_java_source_folder, save_xml_list
from .tools.file_scanner import scan_mybatis_mappers, scan_java_files
from .tools.framework_analyzer import analyze_framework
from .tools.sql_extractor import analyze_sql_complexity
from .tools.report_generator import generate_markdown_report

# Import tools - strategy generation
from .tools.pattern_analyzer import analyze_sql_patterns
from .tools.strategy_generator import generate_strategy, write_strategy_file


def create_source_analyzer_agent() -> Agent:
    """Create and configure Source Analyzer Agent."""
    prompt_path = Path(__file__).parent / "prompt.md"
    system_prompt = prompt_path.read_text(encoding='utf-8')

    model = BedrockModel(
        model_id=MODEL_ID,
        max_tokens=16000
    )

    return Agent(
        name="SourceAnalyzer",
        model=model,
        system_prompt=system_prompt,
        tools=[
            get_java_source_folder,
            scan_mybatis_mappers,
            scan_java_files,
            analyze_framework,
            analyze_sql_complexity,
            generate_markdown_report,
            save_xml_list,
            # Strategy tools
            analyze_sql_patterns,
            generate_strategy,
            write_strategy_file,
        ]
    )


def run_analysis():
    """Run source code analysis + strategy generation"""
    print("🚀 Source Analyzer Agent 시작...\n")

    agent = create_source_analyzer_agent()

    result = agent(
        "Analyze Java source code: scan mappers, analyze complexity, generate report, save to DB. "
        "Then generate transform strategy: call analyze_sql_patterns(), generate_strategy(), write_strategy_file()."
    )

    print("\n" + "=" * 60)
    print(result)
    print("=" * 60)

    from utils.project_paths import STRATEGY_DIR
    strategy_file = STRATEGY_DIR / "transform_strategy.md"
    if strategy_file.exists():
        size_kb = strategy_file.stat().st_size / 1024
        print(f"\n📄 전략 파일: {strategy_file} ({size_kb:.1f}KB)")
    print("\n✅ 분석 + 전략 생성 완료")


if __name__ == "__main__":
    run_analysis()
