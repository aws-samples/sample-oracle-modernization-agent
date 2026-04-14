"""Rich-based display utilities for OMA pipeline progress."""
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, BarColumn, TextColumn, MofNCompleteColumn, TimeElapsedColumn
from rich.panel import Panel

# Use stderr to avoid conflict with stdout capture in MCP
console_err = Console(stderr=True)


def print_pipeline_status(status: dict) -> None:
    """Display pipeline status as a rich table.

    Args:
        status: dict with keys like extracted, transformed, reviewed, validated, tested,
                source_analyzed, review_failed, transform_complete, review_complete,
                validate_complete, test_complete, merge_complete, merged.
    """
    total = status.get('extracted', 0)

    table = Table(title="OMA Pipeline Summary", show_header=True, header_style="bold cyan")
    table.add_column("Step", style="bold")
    table.add_column("Progress", justify="right")
    table.add_column("Status", justify="center")

    # Source Analyzed
    source_count = status.get('source_analyzed', 0) or 0
    analyzed = source_count > 0
    table.add_row(
        "Source Analyze",
        f"{source_count} mappers / {total} SQLs" if analyzed else "-",
        "[green]Done[/green]" if analyzed else "[dim]Pending[/dim]",
    )

    # Transform
    transformed = status.get('transformed', 0)
    table.add_row(
        "Transform",
        f"{transformed}/{total}",
        _status_style(transformed, total, status.get('transform_complete', False)),
    )

    # Review
    reviewed = status.get('reviewed', 0)
    review_failed = status.get('review_failed', 0)
    review_warnings = status.get('review_warnings', 0)
    review_extras = []
    if review_failed > 0:
        review_extras.append(f"[red]{review_failed} FAIL[/red]")
    if review_warnings > 0:
        review_extras.append(f"[yellow]{review_warnings} WARN[/yellow]")
    review_extra = f" ({', '.join(review_extras)})" if review_extras else ""
    table.add_row(
        "Review",
        f"{reviewed}/{total}{review_extra}",
        _status_style(reviewed, total, status.get('review_complete', False)),
    )

    # Validate
    validated = status.get('validated', 0)
    validate_failed = status.get('validate_failed', 0)
    validate_extra = f" [red]({validate_failed} FAIL)[/red]" if validate_failed > 0 else ""
    table.add_row(
        "Validate",
        f"{validated}/{total}{validate_extra}",
        _status_style(validated, total, status.get('validate_complete', False)),
    )

    # Test — denominator excludes non-testable types (sql, resultMap)
    tested = status.get('tested', 0)
    test_failed = status.get('test_failed', 0)
    test_skipped = status.get('test_skipped', 0)
    test_extras = []
    if test_failed > 0:
        test_extras.append(f"[red]{test_failed} FAIL[/red]")
    if test_skipped > 0:
        test_extras.append(f"[dim]{test_skipped} SKIP[/dim]")
    test_extra = f" ({', '.join(test_extras)})" if test_extras else ""
    testable_total = total - test_skipped
    table.add_row(
        "Test",
        f"{tested}/{testable_total}{test_extra}",
        _status_style(tested, total, status.get('test_complete', False)),
    )

    # Merge — count is mapper files, not individual SQLs
    merged = status.get('merged', 0)
    merge_progress = f"{merged}/{source_count} files" if source_count else f"{merged} files"
    table.add_row(
        "Merge",
        merge_progress,
        "[green]Done[/green]" if status.get('merge_complete', False) else "[dim]Pending[/dim]",
    )

    console_err.print(table)


def _status_style(done: int, total: int, complete: bool) -> str:
    if complete:
        return "[green]Done[/green]"
    if done > 0:
        return "[yellow]In Progress[/yellow]"
    return "[dim]Pending[/dim]"


def create_step_progress() -> Progress:
    """Create a rich Progress instance for a pipeline step.

    Returns a Progress context manager that renders to stderr.
    Usage:
        with create_step_progress() as progress:
            task = progress.add_task("Transform", total=42)
            progress.update(task, advance=1, description="Transform: selectUser")
    """
    return Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=30),
        MofNCompleteColumn(),
        TextColumn("[bold]{task.percentage:>5.1f}%"),
        TimeElapsedColumn(),
        console=Console(stderr=True),
        transient=False,
    )


def print_step_result(title: str, rows: list[tuple[str, str]]) -> None:
    """Print a step result summary as a rich panel with key-value rows.

    Args:
        title: Panel title (e.g. "Transform Result")
        rows: list of (label, value) tuples
    """
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="bold")
    table.add_column("Value")
    for label, value in rows:
        table.add_row(label, value)

    console_err.print(Panel(table, title=f"[bold]{title}[/bold]", border_style="green"))
