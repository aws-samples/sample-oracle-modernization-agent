"""TUI automated tests using Textual's built-in test framework."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from textual.widgets import Static, Button, DataTable

from run_tui import OmaTuiApp, SqlExplorerScreen, FailAnalysisScreen


@pytest.mark.asyncio
async def test_app_loads():
    """App starts and shows both panels."""
    async with OmaTuiApp().run_test() as pilot:
        app = pilot.app
        assert app.title == "OMA Pipeline Dashboard"
        assert app.query("DashboardPanel")
        assert app.query("ControlPanel")


@pytest.mark.asyncio
async def test_dashboard_has_stats():
    """Dashboard panel shows stats area."""
    async with OmaTuiApp().run_test() as pilot:
        app = pilot.app
        stats = app.query_one("#dash-stats", Static)
        assert stats is not None


@pytest.mark.asyncio
async def test_dashboard_has_step_distribution():
    """Dashboard panel shows step distribution."""
    async with OmaTuiApp().run_test() as pilot:
        app = pilot.app
        steps = app.query_one("#dash-steps", Static)
        assert steps is not None


@pytest.mark.asyncio
async def test_control_has_step_buttons():
    """Control panel has buttons for each pipeline step."""
    async with OmaTuiApp().run_test() as pilot:
        app = pilot.app
        for step_name in ["analyze", "transform", "review", "validate", "merge", "test"]:
            btn = app.query_one(f"#btn-{step_name}", Button)
            assert btn is not None


@pytest.mark.asyncio
async def test_control_has_run_all_button():
    """Control panel has Run All button."""
    async with OmaTuiApp().run_test() as pilot:
        app = pilot.app
        btn = app.query_one("#btn-all", Button)
        assert btn is not None


@pytest.mark.asyncio
async def test_control_has_navigation_buttons():
    """Control panel has SQL Explorer, FAIL Analysis, Quit buttons."""
    async with OmaTuiApp().run_test() as pilot:
        app = pilot.app
        assert app.query_one("#btn-sql-explorer", Button)
        assert app.query_one("#btn-fail-analysis", Button)
        assert app.query_one("#btn-quit", Button)


@pytest.mark.asyncio
async def test_sql_explorer_screen():
    """SQL Explorer screen opens with DataTable."""
    async with OmaTuiApp().run_test() as pilot:
        await pilot.press("s")
        await pilot.pause()
        app = pilot.app
        screen = app.screen
        assert "SqlExplorer" in type(screen).__name__


@pytest.mark.asyncio
async def test_fail_analysis_screen():
    """FAIL Analysis screen opens."""
    async with OmaTuiApp().run_test() as pilot:
        await pilot.press("f")
        await pilot.pause()
        app = pilot.app
        screen = app.screen
        assert "FailAnalysis" in type(screen).__name__


@pytest.mark.asyncio
async def test_quit_keybinding():
    """Q key exits the app."""
    async with OmaTuiApp().run_test() as pilot:
        await pilot.press("q")
        assert pilot.app._exit


@pytest.mark.asyncio
async def test_escape_from_sql_explorer():
    """Escape returns from SQL Explorer."""
    async with OmaTuiApp().run_test() as pilot:
        await pilot.press("s")
        await pilot.press("escape")
        app = pilot.app
        assert app.query("DashboardPanel")


@pytest.mark.asyncio
async def test_escape_from_fail_analysis():
    """Escape returns from FAIL Analysis."""
    async with OmaTuiApp().run_test() as pilot:
        await pilot.press("f")
        await pilot.press("escape")
        app = pilot.app
        assert app.query("DashboardPanel")
