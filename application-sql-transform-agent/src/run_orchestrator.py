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
    table.add_row("Status", "[white]status[/white]  ·  진행 단계 확인  ·  상태확인")
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

    # 시작 시 상태 확인 (tool이 rich 출력을 직접 표시)
    agent(
        "세션이 방금 시작됐어. `check_setup`과 `check_step_status`를 호출해줘. "
        "두 tool이 이미 rich panel/table로 터미널에 결과를 표시하니 "
        "**markdown 표나 체크리스트로 재렌더링하지 말고**, "
        "다음 추천 action 1~2줄만 덧붙여줘. (예: \"Transform 완료. 다음은 Review입니다.\")"
    )

    while True:
        try:
            raw_input = input("\n⚛️  > ")
            # Sanitize: remove non-printable chars and invalid UTF-8 surrogates
            user_input = raw_input.encode('utf-8', errors='ignore').decode('utf-8').strip()
        except UnicodeDecodeError:
            # Flush broken bytes from stdin buffer
            try:
                if hasattr(sys.stdin, 'buffer'):
                    while sys.stdin.buffer.readable():
                        chunk = sys.stdin.buffer.read1(4096) if hasattr(sys.stdin.buffer, 'read1') else sys.stdin.buffer.read(4096)
                        if len(chunk) < 4096:
                            break
            except Exception:
                pass
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

        try:
            agent(user_input)
        except Exception as e:
            error_str = str(e)
            if "ValidationException" in error_str or "not valid JSON" in error_str:
                print("⚠️  대화 내 잘못된 문자로 인해 에이전트를 리셋합니다.")
                agent = create_orchestrator_agent()
                agent("현재 파이프라인 상태를 확인해줘.")
                print("✅ 리셋 완료. 다시 입력해주세요.")
            else:
                print(f"⚠️  오류 발생: {e}")
                print("다시 입력해주세요.")


if __name__ == "__main__":
    run()
