"""QD CLI main entry point.

Provides command-line interface for executing HAR templates,
managing plugins, and interacting with QD2.
"""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from qd_cli import __version__

app = typer.Typer(
    name="qd",
    help="QD2 - HTTP Request Scheduled Task Automation Framework",
    no_args_is_help=True,
)
console = Console()


@app.command()
def version() -> None:
    """Show QD CLI version."""
    console.print(f"[bold green]QD CLI[/] version [cyan]{__version__}[/]")


@app.command()
def run(
    template: str = typer.Argument(..., help="Path to HAR template file"),
    variable: Optional[list[str]] = typer.Option(
        None, "-v", "--var", help="Template variables (key=value)"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Parse and validate without executing"),
) -> None:
    """Execute a HAR template.

    Example:
        qd run template.har -v token=abc123 -v user=test
    """
    from qd_core.client.har import HARParser

    console.print(f"[bold blue]Loading template:[/] {template}")

    try:
        tmpl = HARParser.parse_file(template)
    except FileNotFoundError:
        console.print(f"[bold red]Error:[/] Template file not found: {template}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[bold red]Error:[/] Failed to parse template: {e}")
        raise typer.Exit(1)

    # Parse variables
    variables = {}
    if variable:
        for v in variable:
            if "=" in v:
                key, value = v.split("=", 1)
                variables[key] = value

    console.print(f"[bold green]Template:[/] {tmpl.name}")
    console.print(f"[bold green]Requests:[/] {len(tmpl.requests)}")

    if dry_run:
        console.print("[bold yellow]Dry run - not executing[/]")
        return

    # Execute template
    import asyncio
    from qd_core.client.fetcher import QDFetcher

    fetcher = QDFetcher()
    fetcher.variables.update(tmpl.variables)
    fetcher.variables.update(variables)

    console.print("[bold blue]Executing requests...[/]")

    results = asyncio.run(fetcher.execute_template(tmpl))

    # Display results
    for i, result in enumerate(results):
        if result.get("status") == "success":
            console.print(
                f"  [green]✓[/] Request {i + 1}: {result.get('status_code', '?')} "
                f"{result.get('url', '')}"
            )
        else:
            console.print(
                f"  [red]✗[/] Request {i + 1}: {result.get('error', 'Unknown error')}"
            )

    console.print("[bold green]Done![/]")


@app.command()
def parse(
    template: str = typer.Argument(..., help="Path to HAR template file"),
) -> None:
    """Parse and display template information.

    Example:
        qd parse template.har
    """
    from qd_core.client.har import HARParser

    try:
        tmpl = HARParser.parse_file(template)
    except FileNotFoundError:
        console.print(f"[bold red]Error:[/] Template file not found: {template}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[bold red]Error:[/] Failed to parse template: {e}")
        raise typer.Exit(1)

    # Display template info
    console.print(f"\n[bold]Template Information[/]")
    console.print(f"  Name:        {tmpl.name}")
    console.print(f"  Description: {tmpl.description or '(none)'}")
    console.print(f"  Version:     {tmpl.version}")
    console.print(f"  Author:      {tmpl.author or '(none)'}")
    console.print(f"  Enabled:     {tmpl.enabled}")
    console.print(f"  Tags:        {', '.join(tmpl.tags) if tmpl.tags else '(none)'}")

    # Display variables
    if tmpl.variables:
        console.print(f"\n[bold]Variables[/]")
        for key, value in tmpl.variables.items():
            console.print(f"  {key}: {value}")

    # Display requests
    console.print(f"\n[bold]Requests ({len(tmpl.requests)})[/]")
    for i, req in enumerate(tmpl.requests):
        console.print(f"  [{i + 1}] {req.method.value} {req.url}")


@app.command()
def plugin(
    action: str = typer.Argument(..., help="Plugin action: list, install, uninstall"),
    name: Optional[str] = typer.Argument(None, help="Plugin name"),
) -> None:
    """Manage QD plugins.

    Example:
        qd plugin list
        qd plugin install qd-plugin-xxx
        qd plugin uninstall qd-plugin-xxx
    """
    from qd_core.plugins.manager import QDPluginManager

    pm = QDPluginManager("qd.plugins")

    if action == "list":
        plugins = pm.list_plugins()
        table = Table(title="QD Plugins")
        table.add_column("Name", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Type")

        for pname, info in plugins.items():
            status = "✓ Enabled" if info["enabled"] else "✗ Disabled"
            ptype = "Default" if info["default"] else "Third-party"
            table.add_row(pname, status, ptype)

        console.print(table)

    elif action == "install":
        if not name:
            console.print("[bold red]Error:[/] Plugin name required")
            raise typer.Exit(1)
        console.print(f"[bold blue]Installing plugin:[/] {name}")
        import asyncio
        success = asyncio.run(pm.install_plugin(name))
        if success:
            console.print(f"[bold green]✓[/] Plugin installed successfully")
        else:
            console.print(f"[bold red]✗[/] Failed to install plugin")
            raise typer.Exit(1)

    elif action == "uninstall":
        if not name:
            console.print("[bold red]Error:[/] Plugin name required")
            raise typer.Exit(1)
        console.print(f"[bold blue]Uninstalling plugin:[/] {name}")
        import asyncio
        asyncio.run(pm.uninstall_plugin(name))
        console.print(f"[bold green]✓[/] Plugin uninstalled")

    else:
        console.print(f"[bold red]Error:[/] Unknown action: {action}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
