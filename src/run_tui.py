"""OMA Pipeline TUI — Terminal UI for pipeline control and monitoring."""
import os
import subprocess
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
        transformed = stats.get("transformed", 0)
        reviewed = stats.get("reviewed", 0)
        validated = stats.get("validated", 0)
        tested = stats.get("tested", 0)
        rate = round(passed / total * 100) if total > 0 else 0

        color = "green" if rate >= 90 else "yellow" if rate >= 70 else "red"
        lines = [
            f"[bold]── Overview ──[/bold]",
            f"  Total SQL    : [bold]{total:>5d}[/bold]",
            f"  [green]Pass[/green]         : [green]{passed:>5d}[/green]",
            f"  [red]Fail[/red]         : [red]{failed:>5d}[/red]",
            f"  [yellow]Skip[/yellow]         : [yellow]{skipped:>5d}[/yellow]",
            f"  Pass Rate    : [{color}][bold]{rate}%[/bold][/]",
            "",
            f"[bold]── Pipeline Steps ──[/bold]",
            f"  Transformed  : {transformed:>5d}/{total}",
            f"  Reviewed     : {reviewed:>5d}/{total}",
            f"  Validated    : {validated:>5d}/{total}",
            f"  Tested       : {tested:>5d}/{total}",
            "",
        ]

        step_counts = get_step_counts()
        if step_counts and total > 0:
            lines.append(f"[bold]── Current Step Distribution ──[/bold]")
            for sn in ["pending", "transform", "review", "validate", "merge", "test", "completed"]:
                cnt = step_counts.get(sn, 0)
                pct = round(cnt / total * 100) if total > 0 else 0
                bl = int(cnt / total * 20) if total > 0 else 0
                bar = "█" * bl + "░" * (20 - bl)
                lines.append(f"  {sn:10s} {bar} {cnt:>5d} ({pct:>2d}%)")
        else:
            lines.append("[dim]  No data — run analyze first[/dim]")

        lines.append("")
        lines.append(f"[bold]── Controls ──[/bold]")
        for name, label, _cmd, _req in STEPS:
            if name == self.running_step:
                icon = "🔄"
            else:
                done_map = {
                    "analyze": total > 0,
                    "transform": transformed == total and total > 0,
                    "review": reviewed == total and total > 0,
                    "validate": validated == total and total > 0,
                    "merge": False,
                    "test": tested == total and total > 0,
                }
                icon = "✅" if done_map.get(name, False) else "⏳"
            opt = "" if _req else " [dim](opt)[/dim]"
            lines.append(f"  {icon} [{name[0].upper()}] {label}{opt}")

        lines.append("")
        lines.append("[dim]1-6:step  R:all  S:sql  F:fail  Q:quit[/dim]")

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
        width: 1fr;
        border: solid $primary;
        padding: 1 1;
        max-width: 60;
    }
    #right-panel {
        width: 2fr;
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
  analyze, transform, review, validate, merge, test  — run step
  transform --workers 4 --sample 5                   — with options
  all                                                — run full pipeline
  skip [mapper] [sql_id]                             — skip a SQL
  status                                             — refresh dashboard
  help                                               — show this help"""

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
            self._execute_step("all", "run_pipeline.py")
        elif verb == "skip" and len(parts) >= 3:
            self._skip_sql(parts[1], parts[2], console)
        elif verb in ("analyze", "transform", "review", "validate", "merge", "test"):
            # Build command with extra args
            for s_name, _label, s_cmd, _req in STEPS:
                if s_name == verb:
                    extra = " ".join(parts[1:])
                    full_cmd = f"{s_cmd} {extra}".strip() if extra else s_cmd
                    self._execute_step(verb, full_cmd)
                    break
        else:
            console.write(f"[red]Unknown command: {verb}[/red] — type [bold]help[/bold]")

    def _skip_sql(self, mapper: str, sql_id: str, console: ConsolePanel) -> None:
        """Mark a SQL as SKIP."""
        try:
            with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
                conn.execute(
                    "UPDATE transform_target_list SET tested='Y', test_result='SKIP', "
                    "test_notes='Manual skip via TUI', current_step='completed' "
                    "WHERE mapper_file LIKE ? AND sql_id=?",
                    (f"%{mapper}%", sql_id)
                )
                if conn.total_changes > 0:
                    console.write(f"[yellow]Skipped: {mapper}/{sql_id}[/yellow]")
                else:
                    console.write(f"[red]Not found: {mapper}/{sql_id}[/red]")
                conn.commit()
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
        if step_name == "all":
            cmd = "run_pipeline.py"
        else:
            cmd = None
            for s_name, _label, s_cmd, _req in STEPS:
                if s_name == step_name:
                    cmd = s_cmd
                    break
        if cmd:
            self._execute_step(step_name, cmd)

    @work(thread=True)
    def _execute_step(self, step_name: str, command: str) -> None:
        console = self.query_one("#console", ConsolePanel)
        dashboard = self.query_one(DashboardPanel)

        self.call_from_thread(console.write, f"\n[bold cyan]> {step_name} started[/bold cyan]")
        self.call_from_thread(setattr, dashboard, "running_step", step_name)
        self.call_from_thread(self._refresh_dashboard)

        cmd_parts = command.split()
        try:
            proc = subprocess.Popen(
                [sys.executable] + cmd_parts,
                cwd=str(SRC_DIR),
                env={**os.environ, "PYTHONPATH": str(SRC_DIR)},
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            for line in iter(proc.stdout.readline, ""):
                stripped = line.rstrip()
                if stripped:
                    self.call_from_thread(console.write, stripped)

            proc.wait()

            if proc.returncode == 0:
                self.call_from_thread(console.write, f"[bold green]✅ {step_name} completed[/bold green]")
            else:
                self.call_from_thread(console.write, f"[bold red]❌ {step_name} failed (exit {proc.returncode})[/bold red]")

        except Exception as e:
            self.call_from_thread(console.write, f"[bold red]❌ {step_name}: {e}[/bold red]")
        finally:
            self.call_from_thread(setattr, dashboard, "running_step", "")
            self.call_from_thread(self._refresh_dashboard)


if __name__ == "__main__":
    app = OmaTuiApp()
    app.run()
