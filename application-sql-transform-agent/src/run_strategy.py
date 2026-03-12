"""Run Strategy tasks — compact or refine via Strategy Refine Agent"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agents.strategy_refine.agent import create_strategy_refine_agent
from utils.project_paths import PROJECT_ROOT


def compact_strategy():
    """Compact strategy file via Strategy Refine Agent."""
    strategy_file = PROJECT_ROOT / "output" / "strategy" / "transform_strategy.md"
    if not strategy_file.exists():
        print("❌ 전략 파일이 없습니다.")
        return
    size_kb = strategy_file.stat().st_size / 1024
    print(f"📄 현재 전략 파일: {size_kb:.1f}KB")
    print("🗜️ 압축 시작...\n")
    agent = create_strategy_refine_agent()
    agent("Compact: read strategy, remove duplicates and patterns covered by General Rules, merge similar patterns, rewrite.")
    new_size = strategy_file.stat().st_size / 1024
    print(f"\n✅ 압축 완료: {size_kb:.1f}KB → {new_size:.1f}KB")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Strategy management')
    parser.add_argument('--task', default='compact_strategy',
                        choices=['compact_strategy', 'refine'])
    args = parser.parse_args()

    if args.task == 'compact_strategy':
        compact_strategy()
    elif args.task == 'refine':
        agent = create_strategy_refine_agent()
        agent("Refine: collect feedback patterns and add as Before/After examples to strategy.")
        print("✅ 전략 보강 완료")
