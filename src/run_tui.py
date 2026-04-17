"""OMA Pipeline TUI — Terminal UI for pipeline control and monitoring."""
import os
import subprocess
import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from textual.app import App, ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, Button, DataTable, RichLog
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
    """Left panel — stats + step buttons."""

    running_step = reactive("")

    def compose(self) -> ComposeResult:
        yield Static("", id="dash-stats")
        yield Static("", id="dash-steps")
        yield Static("─" * 36, id="dash-sep")
        for name, label, _cmd, required in STEPS:
            tag = "" if required else " [dim](opt)[/dim]"
            yield Button(f"{label}{tag}", id=f"btn-{name}", variant="primary")
        yield Static("")
        yield Button("Run All", id="btn-all", variant="success")
        yield Static("")
        yield Button("SQL Explorer", id="btn-sql-explorer", variant="default")
        yield Button("FAIL Analysis", id="btn-fail-analysis", variant="warning")

    def refresh_data(self) -> None:
        stats = get_pipeline_status()
        total = stats.get("total", 0)
        passed = stats.get("passed", 0)
        failed = stats.get("failed", 0)
        skipped = stats.get("skipped", 0)
        rate = round(passed / total * 100) if total > 0 else 0

        color = "green" if rate >= 90 else "yellow" if rate >= 70 else "red"
        stats_text = (
            f"[bold]Total:[/bold] {total}  "
            f"[green]Pass:[/green] {passed}  "
            f"[red]Fail:[/red] {failed}  "
            f"[yellow]Skip:[/yellow] {skipped}\n"
            f"[bold]Pass Rate:[/bold] [{color}]{rate}%[/]"
        )
        self.query_one("#dash-stats", Static).update(stats_text)

        step_counts = get_step_counts()
        if step_counts and total > 0:
            lines = []
            for step_name in ["pending", "transform", "review", "validate", "merge", "test", "completed"]:
                cnt = step_counts.get(step_name, 0)
                bar_len = int(cnt / total * 20) if total > 0 else 0
                bar = "█" * bar_len + "░" * (20 - bar_len)
                lines.append(f" {step_name:11s} {bar} {cnt:>3d}")
            self.query_one("#dash-steps", Static).update("\n".join(lines))
        else:
            self.query_one("#dash-steps", Static).update(" No data")

        # Update step button icons
        for name, _label, _cmd, _req in STEPS:
            btn = self.query_one(f"#btn-{name}", Button)
            if name == self.running_step:
                btn.label = f"🔄 {_label}"
            else:
                step_map = {
                    "analyze": total > 0,
                    "transform": stats.get("transformed", 0) == total and total > 0,
                    "review": stats.get("reviewed", 0) == total and total > 0,
                    "validate": stats.get("validated", 0) == total and total > 0,
                    "merge": False,
                    "test": stats.get("tested", 0) == total and total > 0,
                }
                done = step_map.get(name, False)
                icon = "✅" if done else "⏳"
                tag = "" if _req else " [dim](opt)[/dim]"
                btn.label = f"{icon} {_label}{tag}"


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
        width: 38;
        border: solid $primary;
        padding: 1 1;
    }
    DashboardPanel Button {
        width: 100%;
        margin: 0 0;
        min-height: 1;
        height: 1;
    }
    ConsolePanel {
        width: 1fr;
        border: solid $secondary;
    }
    #dash-stats {
        margin-bottom: 1;
    }
    #dash-steps {
        margin-bottom: 0;
    }
    #dash-sep {
        margin: 0;
        color: $text-muted;
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
            yield ConsolePanel(id="console", highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "OMA Pipeline Dashboard"
        console = self.query_one("#console", ConsolePanel)
        console.write("[bold]OMA Pipeline Console[/bold]")
        console.write("─" * 50)
        console.write("Press [bold]1-6[/bold] to run steps, [bold]R[/bold] = Run All")
        console.write("Press [bold]S[/bold] = SQL Explorer, [bold]F[/bold] = FAIL Analysis, [bold]Q[/bold] = Quit")
        console.write("")
        self.set_interval(5.0, self._refresh_dashboard)
        self._refresh_dashboard()

    def _refresh_dashboard(self) -> None:
        try:
            self.query_one(DashboardPanel).refresh_data()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "btn-sql-explorer":
            self.push_screen(SqlExplorerScreen())
        elif btn_id == "btn-fail-analysis":
            self.push_screen(FailAnalysisScreen())
        elif btn_id == "btn-all":
            self.action_run_step("all")
        elif btn_id.startswith("btn-"):
            step = btn_id[4:]
            self.action_run_step(step)

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
