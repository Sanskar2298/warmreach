import base64
import os
import random
import time
import logging
from datetime import datetime, date
from email.message import EmailMessage
from pathlib import Path
from typing import Optional, List, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session

from config import settings
from models import Contact, ContactStatus

logger = logging.getLogger(__name__)

# Gmail send scope
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


class GmailSendError(Exception):
    """Exception raised when Gmail API send operation fails."""
    pass


class DailyCapExceededError(Exception):
    """Exception raised when daily sending limit is reached."""
    pass


def get_calendar_day_send_count(session: Session, target_date: Optional[date] = None) -> int:
    """
    Counts how many emails were sent on the given calendar day (defaults to today)
    directly queried from the SQLite database.
    """
    day = target_date or datetime.now().date()
    start_of_day = datetime.combine(day, datetime.min.time())
    end_of_day = datetime.combine(day, datetime.max.time())

    count = (
        session.query(func.count(Contact.id))
        .filter(
            Contact.status == ContactStatus.SENT,
            Contact.sent_at >= start_of_day,
            Contact.sent_at <= end_of_day
        )
        .scalar()
    )
    return count or 0


def build_email_message(to_email: str, subject: str, body: str) -> EmailMessage:
    """Creates a standard MIME email message."""
    message = EmailMessage()
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    return message


def get_gmail_service(
    credentials_path: Path = Path(settings.GMAIL_CLIENT_SECRET_FILE),
    token_path: Path = Path(settings.GMAIL_TOKEN_FILE)
):
    """
    Initializes and authenticates the Gmail API service using OAuth2 credentials.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), GMAIL_SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not credentials_path.exists():
                raise FileNotFoundError(
                    f"Gmail OAuth client credentials file '{credentials_path}' not found. "
                    "Follow the setup instructions in README.md to download credentials.json."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)

        # Save credentials for next run
        with open(token_path, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def execute_gmail_send(service, to_email: str, subject: str, body: str) -> str:
    """
    Sends an email using the Gmail API service.
    Returns the sent message ID.
    """
    try:
        msg = build_email_message(to_email, subject, body)
        raw_b64 = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        send_body = {"raw": raw_b64}
        sent = service.users().messages().send(userId="me", body=send_body).execute()
        return sent.get("id", "unknown_id")
    except Exception as e:
        raise GmailSendError(f"Gmail API transmission failed: {e}") from e


def process_sending_batch(
    session: Session,
    approved_contacts: List[Contact],
    dry_run: bool = True,
    gmail_service=None,
    sleep_fn=time.sleep
) -> Tuple[int, int, Optional[str]]:
    """
    Executes sending for a batch of approved contacts with all safety controls:
    - Verifies status is ContactStatus.APPROVED
    - Respects daily cap (settings.DAILY_EMAIL_CAP) counted from DB
    - In dry_run mode, prints email without sending
    - In live mode, performs real send via Gmail API
    - Waits random delay (settings.DELAY_MIN_SECONDS to settings.DELAY_MAX_SECONDS) between live sends
    - Aborts immediately on any API error
    - Logs timestamp and sets status = 'sent' on success
    """
    sent_in_batch = 0
    skipped_cap = 0
    err_message = None

    for idx, contact in enumerate(approved_contacts):
        # Double check invariant
        if contact.status != ContactStatus.APPROVED:
            continue

        # Check calendar day limit from DB
        today_count = get_calendar_day_send_count(session)
        if today_count >= settings.DAILY_EMAIL_CAP:
            err_message = (
                f"Daily sending cap reached ({today_count}/{settings.DAILY_EMAIL_CAP} today). "
                "Halting further sends."
            )
            logger.warning(err_message)
            skipped_cap = len(approved_contacts) - idx
            break

        subject = contact.draft_subject or ""
        body = contact.draft_body or ""

        if dry_run:
            # DRY RUN MODE: Do not touch Gmail API, do not mark as sent
            sent_in_batch += 1
            logger.info(f"[DRY RUN] Would send to {contact.email} ({contact.name})")
        else:
            # LIVE SEND MODE
            try:
                execute_gmail_send(gmail_service, contact.email, subject, body)
                contact.sent_at = datetime.now()
                contact.status = ContactStatus.SENT
                session.commit()
                sent_in_batch += 1

                # If there are subsequent contacts to send, wait random delay
                if idx < len(approved_contacts) - 1:
                    delay = random.uniform(settings.DELAY_MIN_SECONDS, settings.DELAY_MAX_SECONDS)
                    logger.info(f"Pacing delay: sleeping {delay:.1f}s before next send...")
                    sleep_fn(delay)
            except Exception as e:
                err_message = f"Encountered error sending to {contact.email}: {e}. Halting immediately."
                logger.error(err_message)
                break

    return sent_in_batch, skipped_cap, err_message
