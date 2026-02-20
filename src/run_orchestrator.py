"""OMA Orchestrator - Interactive chatbot mode"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agents.orchestrator.agent import create_orchestrator_agent
from utils.project_paths import MODEL_ID, DEFAULT_MODEL_ID


def run():
    print("=" * 70)
    print("🎯 OMA Orchestrator - Oracle → PostgreSQL 마이그레이션 파이프라인")
    print("=" * 70)
    print()
    print("💬 명령 패턴: (단계) (동사)")
    print()
    print("  단계: 분석 | 변환 | 리뷰 | 검증 | 테스트 | 병합 | 전체")
    print("  동사: 수행 | 재수행 | 상태확인")
    print()
    print("  예시: 변환 수행  /  테스트 재수행  /  전체 수행")
    print("  파이프: 변환 수행 후 리뷰 수행  /  분석부터 테스트까지 수행")
    print()
    print("📌 추가 기능:")
    print("  비교: [Mapper명] [SQL ID] 비교  (Oracle vs PostgreSQL Diff)")
    print("  검색: [키워드] SQL 찾아줘")
    print("  단일: [SQL ID] 재변환 / 재검증 / 재테스트")
    print("  리포트: 전체 변환 리포트 / 실패 목록 / 통계")
    print("  전략: 전략 압축 / 전략 보강")
    print()
    print("  'quit' 또는 'exit'로 종료")
    print("=" * 70)

    # 현재 모델 표시
    model_label = f"{MODEL_ID}" + (" (기본값)" if MODEL_ID == DEFAULT_MODEL_ID else " (변경됨)")
    print(f"\n🤖 현재 모델: {model_label}")
    print("   변경하려면: python3 src/run_setup.py  →  OMA_MODEL_ID 항목 수정")
    print("   또는 환경변수: export OMA_MODEL_ID='<model_id>'")
    print()

    agent = create_orchestrator_agent()

    # 시작 시 상태 확인
    agent("현재 파이프라인 상태를 확인해줘.")

    while True:
        try:
            user_input = input("\n🧑 > ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 종료합니다.")
            break

        if not user_input:
            continue
        if user_input.lower() in ('quit', 'exit', 'q'):
            print("👋 종료합니다.")
            break

        agent(user_input)


if __name__ == "__main__":
    run()
