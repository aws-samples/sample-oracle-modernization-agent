"""OMA Pipeline TUI — Terminal UI for pipeline control and monitoring."""
import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, Button, DataTable, RichLog, Input
from textual.reactive import reactive
from textual import work

from utils.project_paths import DB_PATH, SRC_DIR


STEPS = [
    ("analyze", "Analyze", "run_source_analyzer.py", True),
    ("transform", "Transform", "run_sql_transform.py --workers 8", True),
    ("review", "Review", "run_sql_review.py --workers 4 --max-rounds 3", False),
    ("validate", "Validate", "run_sql_validate.py --workers 6", False),
    ("merge", "Merge", "run_sql_merge.py", True),
    ("test", "Test", "run_sql_test.py --workers 6", True),
]


def query_db(sql: str, params: tuple = ()) -> list:
    if not DB_PATH.exists():
        return []
    try:
        with sqlite3.connect(str(DB_PATH), timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except Exception:
        return []


def get_pipeline_status() -> dict:
    rows = query_db("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN test_result='PASS' OR test_result='FIXED' THEN 1 ELSE 0 END) as passed,
            SUM(CASE WHEN test_result='FAIL' THEN 1 ELSE 0 END) as failed,
            SUM(CASE WHEN test_result='SKIP' THEN 1 ELSE 0 END) as skipped,
            SUM(CASE WHEN transformed='Y' THEN 1 ELSE 0 END) as transformed,
            SUM(CASE WHEN reviewed='Y' THEN 1 ELSE 0 END) as reviewed,
            SUM(CASE WHEN validated='Y' THEN 1 ELSE 0 END) as validated,
            SUM(CASE WHEN tested='Y' THEN 1 ELSE 0 END) as tested
        FROM transform_target_list
    """)
    if not rows:
        return {"total": 0, "passed": 0, "failed": 0, "skipped": 0,
                "transformed": 0, "reviewed": 0, "validated": 0, "tested": 0}
    return rows[0]


def get_step_counts() -> dict:
    rows = query_db("SELECT current_step, COUNT(*) as cnt FROM transform_target_list GROUP BY current_step")
    return {r["current_step"]: r["cnt"] for r in rows}


def get_sql_list(step: str = "", status: str = "", limit: int = 200) -> list:
    where = "1=1"
    params: list = []
    if step:
        where += " AND current_step = ?"
        params.append(step)
    if status:
        where += " AND test_result = ?"
        params.append(status)
    return query_db(
        f"SELECT mapper_file, sql_id, sql_type, current_step, test_result, test_notes "
        f"FROM transform_target_list WHERE {where} ORDER BY mapper_file, sql_id LIMIT ?",
        tuple(params + [limit])
    )


def get_fail_categories() -> dict:
    rows = query_db("SELECT test_notes FROM transform_target_list WHERE test_result='FAIL'")
    categories: dict[str, int] = {}
    for r in rows:
        notes = (r.get("test_notes") or "").lower()
        if any(p in notes for p in ["invalid input", "operator does not exist", "type mismatch"]):
            cat = "parameter"
        elif any(p in notes for p in ["syntax error", "unexpected"]):
            cat = "sql_syntax"
        elif any(p in notes for p in ["does not exist", "unknown column", "relation"]):
            cat = "schema"
        elif any(p in notes for p in ["class", "connection", "timeout", "java"]):
            cat = "infra"
        else:
            cat = "other"
        categories[cat] = categories.get(cat, 0) + 1
    return categories


class DashboardPanel(Static):
    """Left panel — compact stats + step status (text only, no buttons)."""

    running_step = reactive("")

    def compose(self) -> ComposeResult:
        yield Static("", id="dash-content")

    def refresh_data(self) -> None:
        stats = get_pipeline_status()
        total = stats.get("total", 0)
        passed = stats.get("passed", 0)
        failed = stats.get("failed", 0)
        skipped = stats.get("skipped", 0)
        rate = round(passed / total * 100) if total > 0 else 0

        color = "green" if rate >= 90 else "yellow" if rate >= 70 else "red"
        lines = [
            f"[bold]SQL:{total}[/] [green]P:{passed}[/] [red]F:{failed}[/] [yellow]S:{skipped}[/] [{color}]{rate}%[/]",
            "",
        ]

        step_counts = get_step_counts()
        if step_counts and total > 0:
            for sn in ["pending", "transform", "review", "validate", "merge", "test", "completed"]:
                cnt = step_counts.get(sn, 0)
                bl = int(cnt / total * 8) if total > 0 else 0
                bar = "█" * bl + "░" * (8 - bl)
                lines.append(f"{sn:10s}{bar}{cnt:>5d}")
        else:
            lines.append("[dim]No data[/dim]")

        lines.append("")
        lines.append("[bold]── Pipeline ──[/bold]")
        for name, label, _cmd, _req in STEPS:
            if name == self.running_step:
                icon = "🔄"
            else:
                done_map = {
                    "analyze": total > 0,
                    "transform": stats.get("transformed", 0) == total and total > 0,
                    "review": stats.get("reviewed", 0) == total and total > 0,
                    "validate": stats.get("validated", 0) == total and total > 0,
                    "merge": False,
                    "test": stats.get("tested", 0) == total and total > 0,
                }
                icon = "✅" if done_map.get(name, False) else "⏳"
            opt = "" if _req else "[dim]*[/dim]"
            lines.append(f" {icon} [bold]{name[0].upper()}[/bold] {label}{opt}")

        lines.append("")
        lines.append("[dim]1-6[/dim]:step [dim]R[/dim]:all [dim]S[/dim]:sql [dim]F[/dim]:fail [dim]Q[/dim]:quit")

        self.query_one("#dash-content", Static).update("\n".join(lines))


class ConsolePanel(RichLog):
    """Right panel — live CLI output."""
    pass


class SqlExplorerScreen(Screen):
    """SQL Explorer — full SQL list."""

    BINDINGS = [("escape", "pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Static("[bold]SQL Explorer[/bold]  [dim](Esc: back)[/dim]")
        yield DataTable(id="sql-table")

    def on_mount(self) -> None:
        table = self.query_one("#sql-table", DataTable)
        table.add_columns("Mapper", "SQL ID", "Type", "Step", "Result", "Notes")
        rows = get_sql_list()
        for r in rows:
            result = r.get("test_result") or "-"
            notes = (r.get("test_notes") or "")[:60]
            table.add_row(
                r["mapper_file"], r["sql_id"], r["sql_type"],
                r["current_step"], result, notes,
            )


class FailAnalysisScreen(Screen):
    """FAIL Analysis — categorized failures."""

    BINDINGS = [("escape", "pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Static("[bold]FAIL Analysis[/bold]  [dim](Esc: back)[/dim]")
        yield Static("", id="fail-cats")
        yield DataTable(id="fail-table")

    def on_mount(self) -> None:
        cats = get_fail_categories()
        if cats:
            lines = ["[bold]Category     Count[/bold]"]
            for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
                lines.append(f" {cat:12s}  {cnt}")
            self.query_one("#fail-cats", Static).update("\n".join(lines))
        else:
            self.query_one("#fail-cats", Static).update(" No failures")

        table = self.query_one("#fail-table", DataTable)
        table.add_columns("Mapper", "SQL ID", "Error")
        rows = get_sql_list(status="FAIL")
        for r in rows:
            notes = (r.get("test_notes") or "")[:80]
            table.add_row(r["mapper_file"], r["sql_id"], notes)


class OmaTuiApp(App):
    """OMA Pipeline TUI — Dashboard + Console."""

    CSS = """
    Screen {
        layout: horizontal;
    }
    DashboardPanel {
        width: 32;
        border: solid $primary;
        padding: 1 1;
    }
    #right-panel {
        width: 1fr;
    }
    ConsolePanel {
        height: 1fr;
        border: solid $secondary;
    }
    #cmd-input {
        dock: bottom;
        height: 3;
        border: solid $accent;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("s", "sql_explorer", "SQL Explorer"),
        ("f", "fail_analysis", "FAIL Analysis"),
        ("1", "run_step('analyze')", "Analyze"),
        ("2", "run_step('transform')", "Transform"),
        ("3", "run_step('review')", "Review"),
        ("4", "run_step('validate')", "Validate"),
        ("5", "run_step('merge')", "Merge"),
        ("6", "run_step('test')", "Test"),
        ("r", "run_step('all')", "Run All"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            yield DashboardPanel()
            with Vertical(id="right-panel"):
                yield ConsolePanel(id="console", highlight=True, markup=True)
                yield Input(placeholder="> command (e.g. transform --workers 4, skip sql_id, help)", id="cmd-input")
        yield Footer()

    COMMANDS_HELP = """[bold]Commands:[/bold]
  analyze, transform, review, validate, merge, test — run step
  transform sample=5                                — sample mode
  all                                               — run full pipeline
  skip [mapper] [sql_id] [reason]                   — skip a SQL
  skip_category [category]                          — skip by category
  classify                                          — classify test failures
  failures [step]                                   — show failures
  reset [step]                                      — reset step
  search [keyword]                                  — search SQL IDs
  status                                            — refresh dashboard
  help                                              — show this help"""

    def on_mount(self) -> None:
        self.title = "OMA Pipeline Dashboard"
        console = self.query_one("#console", ConsolePanel)
        console.write("[bold]OMA Pipeline Console[/bold]")
        console.write("─" * 50)
        console.write("Type commands below or use [bold]1-6/R/S/F/Q[/bold] keys")
        console.write("")
        self.set_interval(5.0, self._refresh_dashboard)
        self._refresh_dashboard()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command input."""
        cmd = event.value.strip()
        event.input.value = ""
        if not cmd:
            return

        console = self.query_one("#console", ConsolePanel)
        console.write(f"\n[bold]> {cmd}[/bold]")

        parts = cmd.split()
        verb = parts[0].lower()

        if verb == "help":
            console.write(self.COMMANDS_HELP)
        elif verb == "status":
            self._refresh_dashboard()
            console.write("[green]Dashboard refreshed[/green]")
        elif verb == "quit" or verb == "exit":
            self.exit()
        elif verb == "sql":
            self.push_screen(SqlExplorerScreen())
        elif verb == "fail":
            self.push_screen(FailAnalysisScreen())
        elif verb == "all":
            self._run_orchestrator_step("all", console)
        elif verb == "skip" and len(parts) >= 3:
            self._call_tool(console, "skip_sql", parts[1], parts[2], " ".join(parts[3:]) or "Manual skip via TUI")
        elif verb == "skip_category" and len(parts) >= 2:
            self._call_tool(console, "skip_by_category", parts[1])
        elif verb == "classify":
            self._call_tool(console, "classify_test_failures")
        elif verb == "failures":
            step = parts[1] if len(parts) > 1 else "all"
            self._call_tool(console, "get_failures", step)
        elif verb == "reset" and len(parts) >= 2:
            self._call_tool(console, "reset_step", parts[1])
        elif verb == "search" and len(parts) >= 2:
            self._call_tool(console, "search_sql_ids", " ".join(parts[1:]))
        elif verb == "report":
            self._call_tool(console, "generate_test_report")
        elif verb in ("analyze", "transform", "review", "validate", "merge", "test"):
            sample = 0
            for p in parts[1:]:
                if p.startswith("sample="):
                    sample = int(p.split("=")[1])
            self._run_orchestrator_step(verb, console, sample=sample)
        else:
            console.write(f"[red]Unknown: {verb}[/red] — type [bold]help[/bold]")

    def _call_tool(self, console: ConsolePanel, tool_name: str, *args) -> None:
        """Call an orchestrator tool function and display result."""
        try:
            from agents.orchestrator.tools import orchestrator_tools as ot
            func = getattr(ot, tool_name)
            result = func(*args)
            if isinstance(result, dict):
                for k, v in result.items():
                    if isinstance(v, dict):
                        console.write(f"  [bold]{k}:[/bold]")
                        for k2, v2 in v.items():
                            console.write(f"    {k2}: {v2}")
                    elif isinstance(v, list) and len(v) > 0:
                        console.write(f"  [bold]{k}:[/bold] ({len(v)} items)")
                        for item in v[:10]:
                            console.write(f"    {item}")
                        if len(v) > 10:
                            console.write(f"    ... +{len(v)-10} more")
                    else:
                        console.write(f"  [bold]{k}:[/bold] {v}")
            else:
                console.write(str(result))
            self._refresh_dashboard()
        except Exception as e:
            console.write(f"[red]Error: {e}[/red]")

    def _refresh_dashboard(self) -> None:
        try:
            self.query_one(DashboardPanel).refresh_data()
        except Exception:
            pass

    def action_sql_explorer(self) -> None:
        self.push_screen(SqlExplorerScreen())

    def action_fail_analysis(self) -> None:
        self.push_screen(FailAnalysisScreen())

    def action_run_step(self, step_name: str) -> None:
        console = self.query_one("#console", ConsolePanel)
        self._run_orchestrator_step(step_name, console)

    def _run_orchestrator_step(self, step_name: str, console: ConsolePanel, sample: int = 0) -> None:
        """Run a pipeline step via orchestrator tool (no subprocess)."""
        if step_name == "all":
            steps_to_run = [s[0] for s in STEPS]
        else:
            steps_to_run = [step_name]
        self._run_steps_sequence(steps_to_run, console, sample)

    @work(thread=True)
    def _run_steps_sequence(self, steps: list, console: ConsolePanel, sample: int = 0) -> None:
        import io
        import contextlib
        from agents.orchestrator.tools.orchestrator_tools import run_step as ot_run_step

        dashboard = self.query_one(DashboardPanel)

        for step_name in steps:
            self.call_from_thread(console.write, f"\n[bold cyan]> {step_name} started[/bold cyan]")
            self.call_from_thread(setattr, dashboard, "running_step", step_name)
            self.call_from_thread(self._refresh_dashboard)

            try:
                # Redirect stdout to TUI console
                class TuiStream(io.TextIOBase):
                    def __init__(self, app, console_widget):
                        self._app = app
                        self._console = console_widget
                        self._buf = ""
                    def write(self, s):
                        self._buf += s
                        while "\n" in self._buf:
                            line, self._buf = self._buf.split("\n", 1)
                            if line.strip():
                                self._app.call_from_thread(self._console.write, line)
                        return len(s)
                    def flush(self):
                        if self._buf.strip():
                            self._app.call_from_thread(self._console.write, self._buf)
                            self._buf = ""

                tui_stream = TuiStream(self, console)
                with contextlib.redirect_stdout(tui_stream):
                    if sample > 0 and step_name == "transform":
                        result = ot_run_step(step_name, sample=sample)
                    else:
                        result = ot_run_step(step_name)
                tui_stream.flush()

                status = result.get("status", "unknown")
                details = result.get("details", "")

                if status == "success":
                    self.call_from_thread(console.write, f"[bold green]✅ {step_name} completed[/bold green]")
                elif status == "skipped":
                    self.call_from_thread(console.write, f"[bold yellow]⏭️ {step_name} skipped: {details}[/bold yellow]")
                else:
                    self.call_from_thread(console.write, f"[bold red]❌ {step_name} failed: {details}[/bold red]")
                    break

            except Exception as e:
                self.call_from_thread(console.write, f"[bold red]❌ {step_name}: {e}[/bold red]")
                break
            finally:
                self.call_from_thread(setattr, dashboard, "running_step", "")
                self.call_from_thread(self._refresh_dashboard)


if __name__ == "__main__":
    app = OmaTuiApp()
    app.run()
