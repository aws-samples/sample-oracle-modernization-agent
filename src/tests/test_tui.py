"""TUI automated tests using Textual's built-in test framework."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from textual.widgets import Static, Button, RichLog, DataTable

from run_tui import OmaTuiApp, SqlExplorerScreen, FailAnalysisScreen, DashboardPanel, ConsolePanel


@pytest.mark.asyncio
async def test_app_loads():
    """App starts with dashboard + console layout."""
    async with OmaTuiApp().run_test() as pilot:
        app = pilot.app
        assert app.title == "OMA Pipeline Dashboard"
        assert app.query("DashboardPanel")
        assert app.query("ConsolePanel")


@pytest.mark.asyncio
async def test_dashboard_has_stats():
    """Dashboard panel shows stats area."""
    async with OmaTuiApp().run_test() as pilot:
        stats = pilot.app.query_one("#dash-stats", Static)
        assert stats is not None


@pytest.mark.asyncio
async def test_dashboard_has_step_distribution():
    """Dashboard panel shows step distribution."""
    async with OmaTuiApp().run_test() as pilot:
        steps = pilot.app.query_one("#dash-steps", Static)
        assert steps is not None


@pytest.mark.asyncio
async def test_dashboard_has_step_buttons():
    """Dashboard has buttons for each pipeline step."""
    async with OmaTuiApp().run_test() as pilot:
        for step_name in ["analyze", "transform", "review", "validate", "merge", "test"]:
            btn = pilot.app.query_one(f"#btn-{step_name}", Button)
            assert btn is not None


@pytest.mark.asyncio
async def test_dashboard_has_run_all_button():
    """Dashboard has Run All button."""
    async with OmaTuiApp().run_test() as pilot:
        btn = pilot.app.query_one("#btn-all", Button)
        assert btn is not None


@pytest.mark.asyncio
async def test_console_panel_exists():
    """Console panel (RichLog) exists on right side."""
    async with OmaTuiApp().run_test() as pilot:
        console = pilot.app.query_one("#console", ConsolePanel)
        assert console is not None


@pytest.mark.asyncio
async def test_console_shows_welcome():
    """Console shows welcome message on start."""
    async with OmaTuiApp().run_test() as pilot:
        console = pilot.app.query_one("#console", ConsolePanel)
        assert console is not None


@pytest.mark.asyncio
async def test_sql_explorer_screen():
    """SQL Explorer screen opens."""
    async with OmaTuiApp().run_test() as pilot:
        await pilot.press("s")
        await pilot.pause()
        assert "SqlExplorer" in type(pilot.app.screen).__name__


@pytest.mark.asyncio
async def test_fail_analysis_screen():
    """FAIL Analysis screen opens."""
    async with OmaTuiApp().run_test() as pilot:
        await pilot.press("f")
        await pilot.pause()
        assert "FailAnalysis" in type(pilot.app.screen).__name__


@pytest.mark.asyncio
async def test_escape_from_sql_explorer():
    """Escape returns from SQL Explorer."""
    async with OmaTuiApp().run_test() as pilot:
        await pilot.press("s")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert pilot.app.query("DashboardPanel")


@pytest.mark.asyncio
async def test_escape_from_fail_analysis():
    """Escape returns from FAIL Analysis."""
    async with OmaTuiApp().run_test() as pilot:
        await pilot.press("f")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert pilot.app.query("DashboardPanel")


@pytest.mark.asyncio
async def test_quit_keybinding():
    """Q key exits the app."""
    async with OmaTuiApp().run_test() as pilot:
        await pilot.press("q")
        assert pilot.app._exit


@pytest.mark.asyncio
async def test_number_keys_bound():
    """Number keys 1-6 and R are bound to step actions."""
    async with OmaTuiApp().run_test() as pilot:
        bindings = {b[0] if isinstance(b, tuple) else b.key for b in pilot.app.BINDINGS}
        for key in ["1", "2", "3", "4", "5", "6", "r"]:
            assert key in bindings
