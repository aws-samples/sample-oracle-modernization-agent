"""OMA Pipeline TUI — Terminal UI for pipeline control and monitoring."""
import subprocess
import sys
import sqlite3
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, Container
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, Button, DataTable, Label, TabbedContent, TabPane
from textual.reactive import reactive
from textual.timer import Timer
from textual import work

from utils.project_paths import DB_PATH, SRC_DIR, LOGS_DIR


STEPS = [
    ("analyze", "Source Analysis", "run_source_analyzer.py", True),
    ("transform", "SQL Transform", "run_sql_transform.py --workers 8", True),
    ("review", "Multi-Perspective Review", "run_sql_review.py --workers 4 --max-rounds 3", False),
    ("validate", "Equivalence Validation", "run_sql_validate.py --workers 6", False),
    ("merge", "Mapper Merge", "run_sql_merge.py", True),
    ("test", "DB Execution Test", "run_sql_test.py --workers 6", True),
]

STEP_ICONS = {
    "completed": "✅",
    "running": "🔄",
    "fail": "❌",
    "pending": "⏳",
}


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


def get_sql_list(step: str = "", status: str = "", search: str = "", limit: int = 200) -> list:
    where = "1=1"
    params: list = []
    if step:
        where += " AND current_step = ?"
        params.append(step)
    if status:
        where += " AND test_result = ?"
        params.append(status)
    if search:
        where += " AND (sql_id LIKE ? OR mapper_file LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])
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
    """Left panel — pipeline status dashboard."""

    def compose(self) -> ComposeResult:
        yield Static("", id="dash-stats")
        yield Static("", id="dash-steps")
        yield Static("", id="dash-recent")

    def refresh_data(self) -> None:
        stats = get_pipeline_status()
        total = stats.get("total", 0)
        passed = stats.get("passed", 0)
        failed = stats.get("failed", 0)
        skipped = stats.get("skipped", 0)
        rate = round(passed / total * 100) if total > 0 else 0

        stats_text = (
            f"[bold]Total:[/bold] {total}  "
            f"[green]Pass:[/green] {passed}  "
            f"[red]Fail:[/red] {failed}  "
            f"[yellow]Skip:[/yellow] {skipped}\n"
            f"[bold]Pass Rate:[/bold] [{'green' if rate >= 90 else 'yellow' if rate >= 70 else 'red'}]{rate}%[/]"
        )
        self.query_one("#dash-stats", Static).update(stats_text)

        step_counts = get_step_counts()
        if step_counts and total > 0:
            lines = []
            for step in ["pending", "transform", "review", "validate", "merge", "test", "completed"]:
                cnt = step_counts.get(step, 0)
                bar_len = int(cnt / total * 30) if total > 0 else 0
                bar = "█" * bar_len + "░" * (30 - bar_len)
                lines.append(f"  {step:12s} {bar} {cnt:>4d}")
            self.query_one("#dash-steps", Static).update("\n".join(lines))
        else:
            self.query_one("#dash-steps", Static).update("  No data — run analyze first")


class ControlPanel(Static):
    """Right panel — pipeline control."""

    running_step = reactive("")

    def compose(self) -> ComposeResult:
        yield Static("", id="ctrl-status")
        for name, label, _cmd, required in STEPS:
            req_badge = "[required]" if required else "[optional]"
            yield Button(f"{label} {req_badge}", id=f"btn-{name}", variant="primary")
        yield Static("───────────────────")
        yield Button("Run All Pipeline", id="btn-all", variant="success")
        yield Static("")
        yield Button("SQL Explorer", id="btn-sql-explorer", variant="default")
        yield Button("FAIL Analysis", id="btn-fail-analysis", variant="warning")
        yield Button("Quit", id="btn-quit", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "btn-quit":
            self.app.exit()
        elif btn_id == "btn-sql-explorer":
            self.app.push_screen(SqlExplorerScreen())
        elif btn_id == "btn-fail-analysis":
            self.app.push_screen(FailAnalysisScreen())
        elif btn_id.startswith("btn-"):
            step = btn_id[4:]
            if step == "all":
                self.run_step("all", "run_pipeline.py")
            else:
                for s_name, _label, cmd, _req in STEPS:
                    if s_name == step:
                        self.run_step(s_name, cmd)
                        break

    @work(thread=True)
    def run_step(self, step_name: str, command: str) -> None:
        self.running_step = step_name
        self.app.call_from_thread(self._update_status, f"🔄 Running: {step_name}...")

        cmd_parts = command.split()
        try:
            result = subprocess.run(
                [sys.executable] + cmd_parts,
                cwd=str(SRC_DIR),
                env={**__import__("os").environ, "PYTHONPATH": str(SRC_DIR)},
                capture_output=True, text=True, timeout=3600,
            )
            if result.returncode == 0:
                self.app.call_from_thread(self._update_status, f"✅ {step_name} completed")
            else:
                err = result.stderr[:200] if result.stderr else "unknown error"
                self.app.call_from_thread(self._update_status, f"❌ {step_name} failed: {err}")
        except subprocess.TimeoutExpired:
            self.app.call_from_thread(self._update_status, f"⏰ {step_name} timed out")
        except Exception as e:
            self.app.call_from_thread(self._update_status, f"❌ {step_name}: {e}")
        finally:
            self.running_step = ""

    def _update_status(self, msg: str) -> None:
        self.query_one("#ctrl-status", Static).update(msg)


class SqlExplorerScreen(Screen):
    """SQL Explorer — filterable SQL list with detail."""

    BINDINGS = [("escape", "pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Static("[bold]SQL Explorer[/bold]  (Esc: back)")
        yield DataTable(id="sql-table")

    def on_mount(self) -> None:
        table = self.query_one("#sql-table", DataTable)
        table.add_columns("Mapper", "SQL ID", "Type", "Step", "Result", "Notes")
        self._load_data()

    def _load_data(self) -> None:
        table = self.query_one("#sql-table", DataTable)
        table.clear()
        rows = get_sql_list()
        for r in rows:
            result = r.get("test_result") or "-"
            notes = (r.get("test_notes") or "")[:60]
            table.add_row(
                r["mapper_file"], r["sql_id"], r["sql_type"],
                r["current_step"], result, notes,
            )


class FailAnalysisScreen(Screen):
    """FAIL Analysis — categorized failure view."""

    BINDINGS = [("escape", "pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Static("[bold]FAIL Analysis[/bold]  (Esc: back)")
        yield Static("", id="fail-cats")
        yield DataTable(id="fail-table")

    def on_mount(self) -> None:
        cats = get_fail_categories()
        if cats:
            lines = ["[bold]FAIL by Category:[/bold]"]
            for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
                lines.append(f"  {cat:12s}  {cnt}")
            self.query_one("#fail-cats", Static).update("\n".join(lines))
        else:
            self.query_one("#fail-cats", Static).update("  No failures found")

        table = self.query_one("#fail-table", DataTable)
        table.add_columns("Mapper", "SQL ID", "Error")
        rows = get_sql_list(status="FAIL")
        for r in rows:
            notes = (r.get("test_notes") or "")[:80]
            table.add_row(r["mapper_file"], r["sql_id"], notes)


class OmaTuiApp(App):
    """OMA Pipeline TUI Application."""

    CSS = """
    Screen {
        layout: horizontal;
    }
    DashboardPanel {
        width: 1fr;
        border: solid $primary;
        padding: 1 2;
    }
    ControlPanel {
        width: 40;
        border: solid $secondary;
        padding: 1 2;
    }
    ControlPanel Button {
        width: 100%;
        margin: 0 0 1 0;
    }
    SqlExplorerScreen {
        width: 100%;
        height: 100%;
        padding: 1;
    }
    FailAnalysisScreen {
        width: 100%;
        height: 100%;
        padding: 1;
    }
    #dash-stats {
        margin-bottom: 1;
    }
    #dash-steps {
        margin-bottom: 1;
    }
    #ctrl-status {
        margin-bottom: 1;
        color: $text;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("s", "sql_explorer", "SQL Explorer"),
        ("f", "fail_analysis", "FAIL Analysis"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            yield DashboardPanel()
            yield ControlPanel()
        yield Footer()

    def on_mount(self) -> None:
        self.title = "OMA Pipeline Dashboard"
        self.set_interval(5.0, self._refresh_dashboard)
        self._refresh_dashboard()

    def _refresh_dashboard(self) -> None:
        try:
            self.query_one(DashboardPanel).refresh_data()
        except Exception:
            pass

    def action_sql_explorer(self) -> None:
        self.push_screen(SqlExplorerScreen())

    def action_fail_analysis(self) -> None:
        self.push_screen(FailAnalysisScreen())


if __name__ == "__main__":
    app = OmaTuiApp()
    app.run()
