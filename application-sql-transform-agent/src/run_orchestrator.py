"""OMA Orchestrator - Interactive chatbot mode"""
import os
import sys
from pathlib import Path

# Ensure UTF-8 for Korean input/output
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdin, "reconfigure") and sys.stdin.encoding and sys.stdin.encoding.lower() != "utf-8":
    sys.stdin.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

sys.path.insert(0, str(Path(__file__).parent))

from agents.orchestrator.agent import create_orchestrator_agent
from utils.project_paths import MODEL_ID, DEFAULT_MODEL_ID


def _print_banner():
    from rich.console import Console
    from rich.table import Table

    c = Console(stderr=True)

    # Title
    c.print()
    c.rule("[bold cyan]OMA · SQL Transform Agent[/bold cyan]")
    c.print("[dim]Oracle SQL Migration Pipeline[/dim]", justify="center")
    c.print()

    # Command reference table
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Category", style="bold cyan", width=10)
    table.add_column("Command", no_wrap=True)

    table.add_row("Pipeline", "[white]변환 수행[/white] · 리뷰 수행 · 전체 수행 · 테스트 재수행")
    table.add_row("", "[white]분석부터 테스트까지 수행[/white] · 변환 수행 후 리뷰 수행")
    table.add_row("Sample", "[white]샘플 변환 5개[/white] · 샘플 변환 10개")
    table.add_row("Compare", "[white]UserMapper selectUserList 비교[/white]")
    table.add_row("Search", "[white]User SQL 찾아줘[/white]  ·  [white]select 검색[/white]")
    table.add_row("Single", "[white]selectUserList 재변환[/white]  ·  [white]재검증[/white]  ·  [white]재테스트[/white]")
    table.add_row("Report", "[white]전체 변환 리포트[/white]  ·  실패 목록  ·  통계")
    table.add_row("Strategy", "[white]전략 압축[/white]  ·  전략 보강")
    table.add_row("Status", "[white]진행 단계 확인[/white]  ·  상태확인")
    table.add_row("Exit", "[dim]quit  ·  exit  ·  q[/dim]")

    c.print(table)

    # Model info
    model_label = MODEL_ID + (" [dim](default)[/dim]" if MODEL_ID == DEFAULT_MODEL_ID else " [yellow](custom)[/yellow]")
    c.print(f"\n  [dim]Model:[/dim] {model_label}")
    c.rule(style="dim")
    c.print()


def run():
    _print_banner()

    agent = create_orchestrator_agent()

    # 시작 시 상태 확인
    agent("현재 파이프라인 상태를 확인해줘.")

    while True:
        try:
            user_input = input("\n⚛️  > ").strip()
        except UnicodeDecodeError:
            print("⚠️  입력 인코딩 오류 — 한영 전환 후 다시 입력해주세요.")
            continue
        except (KeyboardInterrupt, EOFError):
            print("\n👋 종료합니다.")
            break

        if not user_input:
            continue
        if user_input.lower().strip('/') in ('quit', 'exit', 'q'):
            print("👋 종료합니다.")
            break

        agent(user_input)


if __name__ == "__main__":
    run()
