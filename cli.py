from pathlib import Path
import typer
from rich.console import Console
from rich.table import Table

from database import init_db, get_session
from importer import import_contacts_from_csv
from llm import get_llm_client, LLMError

app = typer.Typer(
    name="intern-outreach",
    help="Personalized internship cold email outreach tool (safe, approval-gated).",
    no_args_is_help=True
)

console = Console()


@app.callback()
def main():
    """Ensure database schema is ready."""
    init_db()


@app.command("import-contacts")
def import_contacts(
    csv_file: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to the contacts CSV file to import."
    )
):
    """
    Import contacts from a CSV file.
    Validates emails, skips duplicates, and reports summary.
    """
    console.print(f"[bold blue]Starting import from:[/bold blue] {csv_file}")

    with get_session() as session:
        result = import_contacts_from_csv(csv_file, session)

    # Summary table
    table = Table(title="Contacts Import Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="bold")

    table.add_row("Total Processed", str(result.total_processed))
    table.add_row("Successfully Added", f"[green]{result.added}[/green]")
    table.add_row("Skipped (Duplicates)", f"[yellow]{len(result.skipped_duplicate)}[/yellow]")
    table.add_row("Skipped (Invalid/Errors)", f"[red]{len(result.skipped_invalid)}[/red]")
    console.print(table)

    # Details on skipped duplicates
    if result.skipped_duplicate:
        console.print("\n[yellow bold]Skipped Duplicates:[/yellow bold]")
        for row_num, email, reason in result.skipped_duplicate:
            console.print(f"  • Row {row_num} [bold]{email}[/bold]: {reason}")

    # Details on invalid entries
    if result.skipped_invalid:
        console.print("\n[red bold]Skipped Invalid Entries:[/red bold]")
        for row_num, identifier, reason in result.skipped_invalid:
            console.print(f"  • Row {row_num} [bold]{identifier}[/bold]: {reason}")

    console.print("\n[bold green]Import finished successfully.[/bold green]")


@app.command("test-llm")
def test_llm(
    prompt: str = typer.Argument(
        "say hello",
        help="The test prompt to send to the configured LLM provider."
    )
):
    """
    Test the connection and generation capabilities of the configured LLM provider.
    """
    console.print(f"[bold blue]Initializing LLM provider...[/bold blue]")
    try:
        client = get_llm_client()
        provider_name = client.__class__.__name__
        console.print(f"[cyan]Provider:[/cyan] {provider_name}")
        console.print(f"[cyan]Prompt:[/cyan] [italic]\"{prompt}\"[/italic]")
        console.print("[dim]Waiting for LLM response...[/dim]")

        response = client.generate(prompt)

        console.print("\n[bold green]✓ LLM Response Received:[/bold green]")
        console.print(f"[white]{response}[/white]\n")
    except LLMError as e:
        console.print(f"\n[bold red]LLM Error:[/bold red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
