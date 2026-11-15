import csv
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from config import settings
from database import init_db, get_session
from models import Contact, ContactStatus
from importer import import_contacts_from_csv
from llm import get_llm_client, LLMError
from drafter import load_profile, build_draft_prompt, parse_and_validate_draft, PROFILE_PATH
from reviewer import review_loop, get_contacts_eligible_for_sending
from sender import (
    process_sending_batch,
    get_calendar_day_send_count,
    get_gmail_service
)

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

    table = Table(title="Contacts Import Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="bold")

    table.add_row("Total Processed", str(result.total_processed))
    table.add_row("Successfully Added", f"[green]{result.added}[/green]")
    table.add_row("Skipped (Duplicates)", f"[yellow]{len(result.skipped_duplicate)}[/yellow]")
    table.add_row("Skipped (Invalid/Errors)", f"[red]{len(result.skipped_invalid)}[/red]")
    console.print(table)

    if result.skipped_duplicate:
        console.print("\n[yellow bold]Skipped Duplicates:[/yellow bold]")
        for row_num, email, reason in result.skipped_duplicate:
            console.print(f"  • Row {row_num} [bold]{email}[/bold]: {reason}")

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


@app.command("generate-drafts")
def generate_drafts(
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Maximum number of 'new' contacts to process for draft generation."
    ),
    profile_file: Path = typer.Option(
        PROFILE_PATH,
        "--profile",
        "-p",
        help="Path to the applicant profile YAML file."
    )
):
    """
    Generate personalized email drafts for contacts with status 'new'.
    Validates output structure, word count (<130), and absence of links.
    Retries once on validation failure before marking as 'draft_failed'.
    """
    try:
        profile = load_profile(profile_file)
    except Exception as e:
        console.print(f"[bold red]Failed to load profile:[/bold red] {e}")
        raise typer.Exit(code=1)

    try:
        llm = get_llm_client()
    except Exception as e:
        console.print(f"[bold red]Failed to initialize LLM client:[/bold red] {e}")
        raise typer.Exit(code=1)

    with get_session() as session:
        query = session.query(Contact).filter(Contact.status == ContactStatus.NEW).order_by(Contact.id)
        if limit is not None and limit > 0:
            query = query.limit(limit)
        contacts = query.all()

        if not contacts:
            console.print("[yellow]No contacts found with status 'new'. Nothing to draft.[/yellow]")
            return

        console.print(f"[bold blue]Found {len(contacts)} contacts ready for drafting.[/bold blue]\n")

        drafted_count = 0
        failed_count = 0

        for idx, contact in enumerate(contacts, start=1):
            console.print(f"[cyan]({idx}/{len(contacts)}) Drafting for {contact.name} ({contact.email})...[/cyan]")
            prompt = build_draft_prompt(contact, profile)

            success = False
            last_err = ""

            for attempt in range(1, 3):
                try:
                    current_prompt = prompt
                    if attempt == 2:
                        console.print(f"  [yellow]↳ Retrying generation for {contact.name} (attempt 2/2)...[/yellow]")
                        current_prompt += (
                            f"\nIMPORTANT PREVIOUS ATTEMPT FAILED: {last_err}. "
                            "Please strictly adhere to the instructions: output MUST contain SUBJECT and BODY, "
                            "body MUST be under 130 words, and MUST NOT contain any links/URLs."
                        )

                    raw_output = llm.generate(current_prompt)
                    is_valid, subject, body, err = parse_and_validate_draft(raw_output)

                    if is_valid:
                        contact.draft_subject = subject
                        contact.draft_body = body
                        contact.status = ContactStatus.DRAFTED
                        drafted_count += 1
                        success = True
                        console.print(f"  [green]✓ Drafted successfully ({len(body.split())} words)[/green]")
                        break
                    else:
                        last_err = err
                        console.print(f"  [yellow]⚠ Validation failure (attempt {attempt}): {err}[/yellow]")
                except LLMError as e:
                    last_err = f"LLM error: {e}"
                    console.print(f"  [red]⚠ LLM Error (attempt {attempt}): {e}[/red]")

            if not success:
                contact.status = ContactStatus.DRAFT_FAILED
                failed_count += 1
                console.print(f"  [red]✗ Failed to draft after 2 attempts. Marked as 'draft_failed'. Reason: {last_err}[/red]")

        session.commit()

    table = Table(title="Draft Generation Summary")
    table.add_column("Result", style="cyan")
    table.add_column("Count", style="bold")
    table.add_row("Total Processed", str(len(contacts)))
    table.add_row("Drafted (Ready for Review)", f"[green]{drafted_count}[/green]")
    table.add_row("Draft Failed", f"[red]{failed_count}[/red]")
    console.print("\n", table)


@app.command("review")
def review(
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Maximum number of 'drafted' emails to review in this session."
    )
):
    """
    Interactively review drafted cold emails one by one.
    Keys:
      a = approve
      e = edit
      s = skip
      d = mark do_not_contact
      q = quit and save progress
    """
    with get_session() as session:
        query = (
            session.query(Contact)
            .filter(Contact.status == ContactStatus.DRAFTED)
            .order_by(Contact.id)
        )
        if limit is not None and limit > 0:
            query = query.limit(limit)

        contacts = query.all()

        if not contacts:
            console.print("[yellow]No contacts found with status 'drafted'. Nothing to review.[/yellow]")
            return

        console.print(f"[bold blue]Starting review for {len(contacts)} drafted emails...[/bold blue]")
        review_loop(session, contacts)


@app.command("send")
def send(
    confirm: bool = typer.Option(
        False,
        "--confirm",
        help="Explicit confirmation required to perform real email transmission."
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-l",
        help="Maximum number of approved emails to process in this run."
    )
):
    """
    Send approved cold outreach emails via Gmail API.
    Dry-run mode is enabled by default. To perform real sending:
      1. Set DRY_RUN=false in .env
      2. Pass the --confirm flag
    Safety limits enforced:
      • Max 30 sends per calendar day (counted from DB)
      • 60-180 second randomized delay between sends
      • Abort immediately on any API transmission error
    """
    # Safety Check: Determine if live sending is authorized
    is_live_send = (settings.DRY_RUN is False) and (confirm is True)

    with get_session() as session:
        # Check current calendar day sends from DB
        today_sends = get_calendar_day_send_count(session)
        remaining_cap = max(0, settings.DAILY_EMAIL_CAP - today_sends)

        console.print(f"[bold blue]Daily Sending Status:[/bold blue] {today_sends}/{settings.DAILY_EMAIL_CAP} used today. Remaining: {remaining_cap}")

        if remaining_cap <= 0:
            console.print("[bold red]Daily cap reached for today! No more emails can be sent until tomorrow.[/bold red]")
            return

        query = (
            session.query(Contact)
            .filter(Contact.status == ContactStatus.APPROVED)
            .order_by(Contact.id)
        )
        if limit is not None and limit > 0:
            query = query.limit(limit)

        approved_contacts = query.all()

        if not approved_contacts:
            console.print("[yellow]No contacts found with status 'approved'. Nothing to send.[/yellow]")
            return

        if not is_live_send:
            console.print("\n[bold yellow]═══ RUNNING IN DRY-RUN MODE ═══[/bold yellow]")
            if settings.DRY_RUN:
                console.print("[dim]DRY_RUN is true in settings/.env.[/dim]")
            if not confirm:
                console.print("[dim]--confirm flag was not passed.[/dim]")
            console.print("[yellow]No real emails will be sent. Showing previews below:[/yellow]\n")

            for idx, c in enumerate(approved_contacts, start=1):
                panel_text = (
                    f"[bold cyan]To:[/bold cyan] {c.name} <{c.email}>\n"
                    f"[bold cyan]Subject:[/bold cyan] {c.draft_subject}\n\n"
                    f"[bold white]Body:[/bold white]\n{c.draft_body}"
                )
                console.print(Panel(panel_text, title=f"Dry-Run Preview ({idx}/{len(approved_contacts)})", border_style="yellow"))

            sent_count, skipped_cap, _ = process_sending_batch(
                session, approved_contacts, dry_run=True
            )
            console.print(f"\n[bold green]✓ Dry-run completed for {sent_count} approved emails.[/bold green]")
            return

        # LIVE SENDING
        console.print(f"\n[bold red]⚠️  LIVE SENDING MODE ACTIVATED ⚠️[/bold red]")
        console.print(f"[cyan]Method:[/cyan] {settings.EMAIL_SEND_METHOD.upper()}")
        console.print(f"Preparing to send up to {len(approved_contacts)} approved emails...\n")

        gmail_service = None
        if settings.EMAIL_SEND_METHOD.lower() == "oauth":
            try:
                gmail_service = get_gmail_service()
            except Exception as e:
                console.print(f"[bold red]Failed to initialize Gmail API service:[/bold red] {e}")
                raise typer.Exit(code=1)

        sent_count, skipped_cap, err_message = process_sending_batch(
            session=session,
            approved_contacts=approved_contacts,
            dry_run=False,
            gmail_service=gmail_service
        )

        table = Table(title="Live Send Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="bold")
        table.add_row("Successfully Sent", f"[green]{sent_count}[/green]")
        table.add_row("Skipped (Cap Reached)", f"[yellow]{skipped_cap}[/yellow]")
        console.print(table)

        if err_message:
            console.print(f"\n[bold red]Halted:[/bold red] {err_message}")
        else:
            console.print("\n[bold green]✓ All selected approved emails sent successfully.[/bold green]")


@app.command("export-drafts")
def export_drafts(
    output_file: Path = typer.Option(
        Path("drafts_review.csv"),
        "--output",
        "-o",
        help="Destination CSV file path."
    ),
    include_all_drafted: bool = typer.Option(
        False,
        "--all",
        help="Include all drafted contacts even if previously reviewed."
    )
):
    """
    Export all drafted contacts to drafts_review.csv for manual inspection.
    """
    with get_session() as session:
        contacts = (
            session.query(Contact)
            .filter(Contact.status == ContactStatus.DRAFTED)
            .order_by(Contact.id)
            .all()
        )

        if not contacts:
            console.print("[yellow]No contacts currently have status 'drafted'. Nothing to export.[/yellow]")
            return

        fieldnames = [
            "id",
            "name",
            "email",
            "organization",
            "role",
            "type",
            "research_area_or_team",
            "status",
            "draft_subject",
            "draft_body"
        ]

        with open(output_file, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for c in contacts:
                writer.writerow({
                    "id": c.id,
                    "name": c.name,
                    "email": c.email,
                    "organization": c.organization or "",
                    "role": c.role or "",
                    "type": c.type.value if hasattr(c.type, "value") else str(c.type),
                    "research_area_or_team": c.research_area_or_team or "",
                    "status": c.status.value if hasattr(c.status, "value") else str(c.status),
                    "draft_subject": c.draft_subject or "",
                    "draft_body": c.draft_body or ""
                })

        console.print(f"[bold green]✓ Successfully exported {len(contacts)} drafted contacts to:[/bold green] [cyan]{output_file}[/cyan]")


if __name__ == "__main__":
    app()
