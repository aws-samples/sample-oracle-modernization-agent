"""TUI automated tests using Textual's built-in test framework."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from textual.widgets import Static, RichLog

from run_tui import OmaTuiApp, ConsolePanel


@pytest.mark.asyncio
async def test_app_loads():
    """App starts with dashboard + console layout."""
    async with OmaTuiApp().run_test() as pilot:
        app = pilot.app
        assert app.title == "OMA Pipeline Dashboard"
        assert app.query("DashboardPanel")
        assert app.query("ConsolePanel")


@pytest.mark.asyncio
async def test_dashboard_content():
    """Dashboard panel shows content area."""
    async with OmaTuiApp().run_test() as pilot:
        content = pilot.app.query_one("#dash-content", Static)
        assert content is not None


@pytest.mark.asyncio
async def test_console_panel_exists():
    """Console panel (RichLog) exists."""
    async with OmaTuiApp().run_test() as pilot:
        console = pilot.app.query_one("#console", ConsolePanel)
        assert console is not None


@pytest.mark.asyncio
async def test_sql_explorer_screen():
    """SQL Explorer screen opens with S key."""
    async with OmaTuiApp().run_test() as pilot:
        await pilot.press("s")
        await pilot.pause()
        assert "SqlExplorer" in type(pilot.app.screen).__name__


@pytest.mark.asyncio
async def test_fail_analysis_screen():
    """FAIL Analysis screen opens with F key."""
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
async def test_keybindings_exist():
    """Keys 1-6, R, S, F, Q are bound."""
    async with OmaTuiApp().run_test() as pilot:
        bindings = {b[0] if isinstance(b, tuple) else b.key for b in pilot.app.BINDINGS}
        for key in ["1", "2", "3", "4", "5", "6", "r", "s", "f", "q"]:
            assert key in bindings
