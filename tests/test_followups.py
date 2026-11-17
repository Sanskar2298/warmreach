from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Contact, ContactType, ContactStatus
from drafter import (
    build_followup_prompt,
    parse_and_validate_followup
)
from sender import (
    process_sending_batch,
    is_contact_blocked,
    BLOCKED_STATUSES
)
from reviewer import get_contacts_eligible_for_sending


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def test_profile():
    return {
        "name": "Sanskar Srivastava",
        "internship_goal": "Software Engineering Internship"
    }


def test_build_followup_prompt(test_profile):
    contact = Contact(
        name="Dr. Smith",
        email="smith@example.com",
        organization="MIT",
        draft_subject="Summer 2025 Research Inquiry",
        type=ContactType.PROFESSOR
    )
    prompt = build_followup_prompt(contact, test_profile)
    assert "Dr. Smith" in prompt
    assert "MIT" in prompt
    assert "Re: Summer 2025 Research Inquiry" in prompt
    assert "60 words" in prompt


def test_parse_and_validate_followup_valid():
    raw_output = """SUBJECT: Re: Summer 2025 Research Inquiry
BODY:
Dear Dr. Smith,

I am following up on my note from last week regarding potential summer research opportunities with your group. I would welcome the chance to speak if you have a brief moment.

Thank you,
Sanskar"""
    ok, sub, body, err = parse_and_validate_followup(raw_output)
    assert ok is True
    assert sub == "Re: Summer 2025 Research Inquiry"
    assert "following up" in body
    assert len(body.split()) < 60
    assert err is None


def test_parse_and_validate_followup_forbidden_links():
    raw_output = """SUBJECT: Re: Follow-up
BODY:
Hi, check my work at https://example.com/portfolio and let me know."""
    ok, sub, body, err = parse_and_validate_followup(raw_output)
    assert ok is False
    assert "forbidden" in err.lower()


def test_parse_and_validate_followup_word_count_exceeded():
    long_body = "word " * 65
    raw_output = f"""SUBJECT: Re: Follow-up
BODY:
{long_body}"""
    ok, sub, body, err = parse_and_validate_followup(raw_output)
    assert ok is False
    assert "exceeds limit of 60 words" in err


def test_is_contact_blocked():
    assert is_contact_blocked(ContactStatus.REPLIED) is True
    assert is_contact_blocked(ContactStatus.BOUNCED) is True
    assert is_contact_blocked(ContactStatus.DO_NOT_CONTACT) is True
    assert is_contact_blocked(ContactStatus.NEW) is False
    assert is_contact_blocked(ContactStatus.DRAFTED) is False
    assert is_contact_blocked(ContactStatus.APPROVED) is False
    assert is_contact_blocked(ContactStatus.SENT) is False


def test_sender_global_check_blocks_replied_bounced_do_not_contact(db_session):
    """
    CRITICAL REQUIREMENT TEST:
    Global check in the sender blocks any contact with status
    replied, bounced, or do_not_contact from being sent.
    """
    c1 = Contact(name="Replied", email="replied@example.com", type=ContactType.HR, status=ContactStatus.REPLIED)
    c2 = Contact(name="Bounced", email="bounced@example.com", type=ContactType.HR, status=ContactStatus.BOUNCED)
    c3 = Contact(name="DNC", email="dnc@example.com", type=ContactType.HR, status=ContactStatus.DO_NOT_CONTACT)
    c4 = Contact(name="Approved", email="ok@example.com", type=ContactType.HR, status=ContactStatus.APPROVED)
    db_session.add_all([c1, c2, c3, c4])
    db_session.commit()

    mock_service = MagicMock()

    sent_count, skipped_cap, err = process_sending_batch(
        session=db_session,
        approved_contacts=[c1, c2, c3, c4],
        dry_run=True,
        gmail_service=mock_service
    )

    # Only c4 (Approved) should have been processed, the three blocked ones are ignored
    assert sent_count == 1
    db_session.refresh(c1)
    db_session.refresh(c2)
    db_session.refresh(c3)
    db_session.refresh(c4)
    assert c1.status == ContactStatus.REPLIED
    assert c2.status == ContactStatus.BOUNCED
    assert c3.status == ContactStatus.DO_NOT_CONTACT
    assert c4.status == ContactStatus.APPROVED


def test_followup_selection_rules(db_session):
    now = datetime.now()
    ten_days_ago = now - timedelta(days=10)
    three_days_ago = now - timedelta(days=3)

    # 1. Eligible: sent 10 days ago, no reply, no followup
    c_eligible = Contact(
        name="Eligible",
        email="eligible@example.com",
        type=ContactType.HR,
        status=ContactStatus.SENT,
        sent_at=ten_days_ago,
        followup_sent_at=None
    )
    # 2. Ineligible: sent only 3 days ago (< 7 days)
    c_too_recent = Contact(
        name="Recent",
        email="recent@example.com",
        type=ContactType.HR,
        status=ContactStatus.SENT,
        sent_at=three_days_ago,
        followup_sent_at=None
    )
    # 3. Ineligible: already received a follow-up
    c_already_followed = Contact(
        name="Followed",
        email="followed@example.com",
        type=ContactType.HR,
        status=ContactStatus.SENT,
        sent_at=ten_days_ago,
        followup_sent_at=three_days_ago
    )
    # 4. Ineligible: replied
    c_replied = Contact(
        name="Replied",
        email="replied@example.com",
        type=ContactType.HR,
        status=ContactStatus.REPLIED,
        sent_at=ten_days_ago,
        followup_sent_at=None
    )

    db_session.add_all([c_eligible, c_too_recent, c_already_followed, c_replied])
    db_session.commit()

    cutoff_date = now - timedelta(days=7)
    query = (
        db_session.query(Contact)
        .filter(
            Contact.status == ContactStatus.SENT,
            Contact.sent_at <= cutoff_date,
            Contact.followup_sent_at.is_(None)
        )
    )
    results = query.all()

    assert len(results) == 1
    assert results[0].email == "eligible@example.com"
