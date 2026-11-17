import os
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple, Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from models import Contact, ContactStatus

console = Console()


def get_contacts_eligible_for_sending(contacts_iterable):
    """
    Core safety invariant rule:
    Only contacts with status == 'approved' can ever be sent.
    Any contacts with blocked status (replied, bounced, do_not_contact) are strictly rejected.
    """
    blocked = {ContactStatus.REPLIED, ContactStatus.BOUNCED, ContactStatus.DO_NOT_CONTACT}
    return [c for c in contacts_iterable if c.status == ContactStatus.APPROVED and c.status not in blocked]


def display_review_card(contact: Contact, current_idx: int, total_count: int) -> None:
    """Displays the recipient details and current draft in a formatted panel."""
    org = contact.organization or "N/A"
    role = contact.role or "N/A"
    team = contact.research_area_or_team or "N/A"
    notes = contact.notes or "None"
    url = contact.source_url or "None"

    header_text = (
        f"[bold cyan]Name:[/bold cyan] {contact.name}  |  [bold cyan]Email:[/bold cyan] {contact.email}\n"
        f"[bold cyan]Organization:[/bold cyan] {org}  |  [bold cyan]Role:[/bold cyan] {role}\n"
        f"[bold cyan]Research/Team:[/bold cyan] {team}\n"
        f"[bold cyan]Notes:[/bold cyan] {notes}\n"
        f"[bold cyan]Source URL:[/bold cyan] {url}"
    )

    draft_text = (
        f"[bold yellow]Subject:[/bold yellow] {contact.draft_subject or 'No subject'}\n\n"
        f"[bold yellow]Body:[/bold yellow]\n{contact.draft_body or 'No body'}"
    )

    full_display = f"{header_text}\n\n[bold white]─── Draft ───[/bold white]\n\n{draft_text}"

    console.print(
        Panel(
            full_display,
            title=f"[bold green]Review Draft ({current_idx}/{total_count})[/bold green]",
            border_style="blue",
            expand=False
        )
    )


def edit_draft_interactive(subject: str, body: str) -> Tuple[str, str]:
    """
    Edits draft subject and body. If $EDITOR is defined, opens in editor via a temp file.
    Otherwise, or if editor fails/empty, prompts interactively.
    """
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")

    if editor:
        initial_content = f"SUBJECT: {subject}\n\nBODY:\n{body}"
        with tempfile.NamedTemporaryFile("w+", suffix=".txt", delete=False, encoding="utf-8") as tf:
            tf.write(initial_content)
            temp_path = tf.name

        try:
            exit_code = subprocess.call([editor, temp_path])
            if exit_code == 0:
                edited_content = Path(temp_path).read_text(encoding="utf-8")
                # Parse subject and body from temp file
                if "BODY:" in edited_content:
                    parts = edited_content.split("BODY:", 1)
                    sub_part = parts[0].replace("SUBJECT:", "").strip()
                    body_part = parts[1].strip()
                    if sub_part and body_part:
                        return sub_part, body_part
        except Exception as e:
            console.print(f"[yellow]Could not launch editor ({editor}): {e}. Falling back to prompt.[/yellow]")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    # Interactive fallback prompt
    console.print("[dim]Leave input blank to keep current value.[/dim]")
    new_sub = Prompt.ask("Edit Subject", default=subject)
    console.print("Current body:\n" + body)
    change_body = Prompt.ask("Replace body text? (y/N)", default="n").strip().lower()
    if change_body == "y":
        console.print("[cyan]Enter new body text (type EOF or empty line + Enter on standalone prompt):[/cyan]")
        new_body = Prompt.ask("New Body", default=body)
        return new_sub, new_body
    return new_sub, body


def review_loop(session, contacts) -> None:
    """Runs the interactive review loop over drafted contacts."""
    total = len(contacts)
    approved_count = 0
    skipped_count = 0
    dnc_count = 0

    for idx, contact in enumerate(contacts, start=1):
        while True:
            display_review_card(contact, idx, total)
            choice = Prompt.ask(
                "[bold]Action[/bold] ([green]a[/green]=approve, "
                "[cyan]e[/cyan]=edit, [yellow]s[/yellow]=skip, "
                "[red]d[/red]=do_not_contact, [magenta]q[/magenta]=quit & save)",
                choices=["a", "e", "s", "d", "q"],
                default="a"
            ).strip().lower()

            if choice == "a":
                contact.status = ContactStatus.APPROVED
                session.commit()
                approved_count += 1
                console.print(f"[bold green]✓ Approved draft for {contact.name}[/bold green]\n")
                break

            elif choice == "e":
                new_sub, new_body = edit_draft_interactive(
                    contact.draft_subject or "",
                    contact.draft_body or ""
                )
                contact.draft_subject = new_sub
                contact.draft_body = new_body
                session.commit()
                console.print("[bold cyan]Draft updated. Re-displaying for confirmation...[/bold cyan]\n")
                # Loops back to show the card with updated draft
                continue

            elif choice == "s":
                # Leave status as 'drafted'
                skipped_count += 1
                console.print(f"[yellow]Skipped {contact.name} (remains drafted)[/yellow]\n")
                break

            elif choice == "d":
                contact.status = ContactStatus.DO_NOT_CONTACT
                session.commit()
                dnc_count += 1
                console.print(f"[red]Marked {contact.name} as do_not_contact[/red]\n")
                break

            elif choice == "q":
                session.commit()
                console.print("[magenta]Progress saved. Exiting review session.[/magenta]")
                console.print(
                    f"Summary: [green]{approved_count} approved[/green], "
                    f"[yellow]{skipped_count} skipped[/yellow], "
                    f"[red]{dnc_count} do_not_contact[/red]."
                )
                return

    session.commit()
    console.print("[bold green]All drafted contacts reviewed![/bold green]")
    console.print(
        f"Summary: [green]{approved_count} approved[/green], "
        f"[yellow]{skipped_count} skipped[/yellow], "
        f"[red]{dnc_count} do_not_contact[/red]."
    )
