from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from models import Base, Contact, ContactType, ContactStatus
from sender import (
    get_calendar_day_send_count,
    build_email_message,
    process_sending_batch,
    GmailSendError
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_build_email_message():
    msg = build_email_message("target@example.com", "Test Subject", "Test Body Here")
    assert msg["To"] == "target@example.com"
    assert msg["Subject"] == "Test Subject"
    assert msg.get_content().strip() == "Test Body Here"


def test_get_calendar_day_send_count(db_session):
    today = datetime.now()
    yesterday = today - timedelta(days=1)

    # 2 sent today
    c1 = Contact(name="A", email="a@example.com", type=ContactType.HR, status=ContactStatus.SENT, sent_at=today)
    c2 = Contact(name="B", email="b@example.com", type=ContactType.HR, status=ContactStatus.SENT, sent_at=today)
    # 1 sent yesterday
    c3 = Contact(name="C", email="c@example.com", type=ContactType.HR, status=ContactStatus.SENT, sent_at=yesterday)
    # 1 approved but not sent
    c4 = Contact(name="D", email="d@example.com", type=ContactType.HR, status=ContactStatus.APPROVED)

    db_session.add_all([c1, c2, c3, c4])
    db_session.commit()

    count_today = get_calendar_day_send_count(db_session, target_date=today.date())
    assert count_today == 2

    count_yesterday = get_calendar_day_send_count(db_session, target_date=yesterday.date())
    assert count_yesterday == 1


def test_dry_run_mode_does_not_modify_status_or_call_api(db_session):
    contact = Contact(
        name="Alice",
        email="alice@example.com",
        type=ContactType.HR,
        status=ContactStatus.APPROVED,
        draft_subject="Subject",
        draft_body="Body"
    )
    db_session.add(contact)
    db_session.commit()

    mock_service = MagicMock()

    sent_count, skipped_cap, err = process_sending_batch(
        session=db_session,
        approved_contacts=[contact],
        dry_run=True,
        gmail_service=mock_service
    )

    assert sent_count == 1
    assert skipped_cap == 0
    assert err is None
    # In dry-run, Gmail API is NEVER called
    mock_service.users.assert_not_called()

    db_session.refresh(contact)
    # Contact status MUST remain APPROVED, not SENT
    assert contact.status == ContactStatus.APPROVED
    assert contact.sent_at is None


def test_live_send_updates_status_and_timestamps(db_session):
    contact = Contact(
        name="Alice",
        email="alice@example.com",
        type=ContactType.HR,
        status=ContactStatus.APPROVED,
        draft_subject="Subject",
        draft_body="Body"
    )
    db_session.add(contact)
    db_session.commit()

    mock_service = MagicMock()
    mock_messages = MagicMock()
    mock_send = MagicMock()
    mock_send.execute.return_value = {"id": "msg_12345"}
    mock_messages.send.return_value = mock_send
    mock_service.users().messages.return_value = mock_messages

    mock_sleep = MagicMock()

    sent_count, skipped_cap, err = process_sending_batch(
        session=db_session,
        approved_contacts=[contact],
        dry_run=False,
        gmail_service=mock_service,
        sleep_fn=mock_sleep
    )

    assert sent_count == 1
    assert skipped_cap == 0
    assert err is None

    db_session.refresh(contact)
    assert contact.status == ContactStatus.SENT
    assert contact.sent_at is not None
    assert isinstance(contact.sent_at, datetime)


def test_daily_cap_enforcement(db_session):
    # Pre-fill database with 30 sent emails today
    today = datetime.now()
    contacts_sent_today = [
        Contact(
            name=f"Person {i}",
            email=f"person{i}@example.com",
            type=ContactType.HR,
            status=ContactStatus.SENT,
            sent_at=today
        )
        for i in range(30)
    ]
    db_session.add_all(contacts_sent_today)
    db_session.commit()

    # Now attempt to send 2 new approved contacts
    c1 = Contact(name="New1", email="new1@example.com", type=ContactType.HR, status=ContactStatus.APPROVED)
    c2 = Contact(name="New2", email="new2@example.com", type=ContactType.HR, status=ContactStatus.APPROVED)
    db_session.add_all([c1, c2])
    db_session.commit()

    mock_service = MagicMock()

    with patch("config.settings.DAILY_EMAIL_CAP", 30):
        sent_count, skipped_cap, err = process_sending_batch(
            session=db_session,
            approved_contacts=[c1, c2],
            dry_run=False,
            gmail_service=mock_service
        )

        assert sent_count == 0
        assert skipped_cap == 2
        assert "Daily sending cap reached" in err
        mock_service.users.assert_not_called()

        db_session.refresh(c1)
        db_session.refresh(c2)
        assert c1.status == ContactStatus.APPROVED
        assert c2.status == ContactStatus.APPROVED


def test_immediate_stop_on_api_error(db_session):
    c1 = Contact(name="Fail Person", email="fail@example.com", type=ContactType.HR, status=ContactStatus.APPROVED)
    c2 = Contact(name="Second Person", email="sec@example.com", type=ContactType.HR, status=ContactStatus.APPROVED)
    db_session.add_all([c1, c2])
    db_session.commit()

    mock_service = MagicMock()
    # Force API execution to fail on first message
    mock_service.users().messages().send().execute.side_effect = RuntimeError("Gmail API 500 Server Error")

    sent_count, skipped_cap, err = process_sending_batch(
        session=db_session,
        approved_contacts=[c1, c2],
        dry_run=False,
        gmail_service=mock_service
    )

    # First send failed, loop aborted immediately, second was never processed
    assert sent_count == 0
    assert "Encountered error sending to fail@example.com" in err
    db_session.refresh(c1)
    db_session.refresh(c2)
    assert c1.status == ContactStatus.APPROVED
    assert c2.status == ContactStatus.APPROVED
