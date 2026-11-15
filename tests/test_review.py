from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Contact, ContactType, ContactStatus
from reviewer import (
    get_contacts_eligible_for_sending,
    review_loop,
    edit_draft_interactive
)


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_only_approved_contacts_can_be_sent():
    """
    CRITICAL SAFETY RULE TEST:
    Only contacts with status == 'approved' can ever be sent.
    All other statuses ('new', 'drafted', 'draft_failed', 'sent', 'replied',
    'bounced', 'do_not_contact') MUST be rejected.
    """
    contacts = [
        Contact(id=1, name="New Guy", email="new@example.com", status=ContactStatus.NEW, type=ContactType.HR),
        Contact(id=2, name="Drafted Person", email="drafted@example.com", status=ContactStatus.DRAFTED, type=ContactType.HR),
        Contact(id=3, name="Approved Person", email="approved@example.com", status=ContactStatus.APPROVED, type=ContactType.HR),
        Contact(id=4, name="Failed Draft Person", email="failed@example.com", status=ContactStatus.DRAFT_FAILED, type=ContactType.HR),
        Contact(id=5, name="Already Sent", email="sent@example.com", status=ContactStatus.SENT, type=ContactType.HR),
        Contact(id=6, name="Do Not Contact", email="dnc@example.com", status=ContactStatus.DO_NOT_CONTACT, type=ContactType.HR),
        Contact(id=7, name="Bounced Contact", email="bounced@example.com", status=ContactStatus.BOUNCED, type=ContactType.HR),
        Contact(id=8, name="Second Approved", email="approved2@example.com", status=ContactStatus.APPROVED, type=ContactType.PROFESSOR),
    ]

    eligible = get_contacts_eligible_for_sending(contacts)

    assert len(eligible) == 2
    assert all(c.status == ContactStatus.APPROVED for c in eligible)
    eligible_ids = {c.id for c in eligible}
    assert eligible_ids == {3, 8}


def test_review_action_approve(db_session):
    contact = Contact(
        name="Review Candidate",
        email="rev@example.com",
        type=ContactType.HR,
        status=ContactStatus.DRAFTED,
        draft_subject="Subject Test",
        draft_body="Body Test"
    )
    db_session.add(contact)
    db_session.commit()

    with patch("rich.prompt.Prompt.ask", return_value="a"):
        review_loop(db_session, [contact])

    db_session.refresh(contact)
    assert contact.status == ContactStatus.APPROVED


def test_review_action_skip(db_session):
    contact = Contact(
        name="Skip Candidate",
        email="skip@example.com",
        type=ContactType.HR,
        status=ContactStatus.DRAFTED,
        draft_subject="Subject",
        draft_body="Body"
    )
    db_session.add(contact)
    db_session.commit()

    with patch("rich.prompt.Prompt.ask", return_value="s"):
        review_loop(db_session, [contact])

    db_session.refresh(contact)
    assert contact.status == ContactStatus.DRAFTED  # Status remains unchanged


def test_review_action_do_not_contact(db_session):
    contact = Contact(
        name="DNC Candidate",
        email="dnc@example.com",
        type=ContactType.HR,
        status=ContactStatus.DRAFTED,
        draft_subject="Subject",
        draft_body="Body"
    )
    db_session.add(contact)
    db_session.commit()

    with patch("rich.prompt.Prompt.ask", return_value="d"):
        review_loop(db_session, [contact])

    db_session.refresh(contact)
    assert contact.status == ContactStatus.DO_NOT_CONTACT


def test_review_action_edit_and_approve(db_session):
    contact = Contact(
        name="Edit Candidate",
        email="edit@example.com",
        type=ContactType.HR,
        status=ContactStatus.DRAFTED,
        draft_subject="Old Subject",
        draft_body="Old Body"
    )
    db_session.add(contact)
    db_session.commit()

    # Sequence: first prompt chooses 'e' (edit), then prompt chooses 'a' (approve)
    # Inside edit_draft_interactive, mocks prompts for new subject and new body
    with patch("reviewer.edit_draft_interactive", return_value=("Edited Subject", "Edited Body")), \
         patch("rich.prompt.Prompt.ask", side_effect=["e", "a"]):
        review_loop(db_session, [contact])

    db_session.refresh(contact)
    assert contact.status == ContactStatus.APPROVED
    assert contact.draft_subject == "Edited Subject"
    assert contact.draft_body == "Edited Body"


def test_review_action_quit_and_save(db_session):
    c1 = Contact(name="C1", email="c1@example.com", type=ContactType.HR, status=ContactStatus.DRAFTED)
    c2 = Contact(name="C2", email="c2@example.com", type=ContactType.HR, status=ContactStatus.DRAFTED)
    db_session.add_all([c1, c2])
    db_session.commit()

    # Sequence: Approve C1, then choose Quit on C2
    with patch("rich.prompt.Prompt.ask", side_effect=["a", "q"]):
        review_loop(db_session, [c1, c2])

    db_session.refresh(c1)
    db_session.refresh(c2)

    assert c1.status == ContactStatus.APPROVED
    assert c2.status == ContactStatus.DRAFTED  # Unreviewed item remains drafted
