from unittest.mock import MagicMock, patch
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, Contact, ContactType, ContactStatus
from drafter import build_draft_prompt, parse_and_validate_draft, load_profile


@pytest.fixture
def test_profile():
    return {
        "name": "Sanskar",
        "degree": "B.Tech in Computer Science",
        "skills": ["Python", "PyTorch", "FastAPI"],
        "projects": [
            {"name": "Warmreach", "description": "CLI cold outreach tool with safety limits."},
            {"name": "AI Benchmark", "description": "LLM evaluation pipeline."}
        ],
        "internship_goal": "Summer 2025 AI Systems Internship"
    }


@pytest.fixture
def sample_contact():
    return Contact(
        name="Dr. Alan Turing",
        email="alan.turing@example.com",
        organization="Cambridge University",
        role="Professor",
        type=ContactType.PROFESSOR,
        research_area_or_team="Theory of Computation",
        notes="Seminal paper on computing machinery",
        status=ContactStatus.NEW
    )


def test_build_draft_prompt(sample_contact, test_profile):
    prompt = build_draft_prompt(sample_contact, test_profile)
    assert "Sanskar" in prompt
    assert "Dr. Alan Turing" in prompt
    assert "Cambridge University" in prompt
    assert "Theory of Computation" in prompt
    assert "SUBJECT:" in prompt
    assert "BODY:" in prompt
    assert "130 words" in prompt


def test_parse_and_validate_draft_valid():
    raw_output = """SUBJECT: Summer 2025 Internship Inquiry - Theory of Computation

BODY:
Dear Dr. Turing,

I have followed your pioneering work on computation with great admiration. As a Computer Science undergraduate skilled in Python and machine learning infrastructure, I built Warmreach, an approval-gated outreach tool with strict safety controls. 

I would love to contribute to your research team as a research intern this coming summer. Would you have 10 minutes next week for a brief conversation regarding potential openings?

Best regards,
Sanskar"""

    is_valid, subject, body, err = parse_and_validate_draft(raw_output)
    assert is_valid is True
    assert subject == "Summer 2025 Internship Inquiry - Theory of Computation"
    assert "Dear Dr. Turing" in body
    assert err is None
    assert len(body.split()) < 130


def test_parse_and_validate_draft_missing_headers():
    raw_output = "Hello Dr. Turing, I want an internship please hire me."
    is_valid, subject, body, err = parse_and_validate_draft(raw_output)
    assert is_valid is False
    assert "missing" in err.lower()
    assert "subject" in err.lower() or "body" in err.lower()


def test_parse_and_validate_draft_forbidden_links():
    raw_output = """SUBJECT: Internship Inquiry
BODY:
Hi, check out my portfolio at https://github.com/myuser and hire me!"""
    is_valid, subject, body, err = parse_and_validate_draft(raw_output)
    assert is_valid is False
    assert "links" in err.lower()

    # Markdown link
    raw_output_md = """SUBJECT: Internship Inquiry
BODY:
Hi, check out my [portfolio](https://myportfolio.com) and let me know."""
    is_valid, subject, body, err = parse_and_validate_draft(raw_output_md)
    assert is_valid is False
    assert "links" in err.lower()


def test_parse_and_validate_draft_word_count_exceeded():
    long_body = "word " * 135
    raw_output = f"""SUBJECT: Research Internship
BODY:
{long_body}"""
    is_valid, subject, body, err = parse_and_validate_draft(raw_output)
    assert is_valid is False
    assert "exceeds limit of 130 words" in err


def test_generate_drafts_logic_retry_and_success(tmp_path, test_profile):
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    contact = Contact(
        name="Elena Rostova",
        email="elena@example.com",
        type=ContactType.HR,
        status=ContactStatus.NEW
    )
    session.add(contact)
    session.commit()

    # Mock LLM that fails first attempt (link present), then succeeds on retry
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = [
        "SUBJECT: Invalid Draft\nBODY: Check my link https://example.com please.",  # attempt 1 invalid
        "SUBJECT: Valid Draft\nBODY: Dear Elena, I am excited about early career roles. Best, Sanskar."  # attempt 2 valid
    ]

    # Run drafting loop manually as implemented in CLI
    from drafter import build_draft_prompt, parse_and_validate_draft

    prompt = build_draft_prompt(contact, test_profile)
    success = False
    for attempt in range(1, 3):
        raw = mock_llm.generate(prompt)
        is_valid, subject, body, err = parse_and_validate_draft(raw)
        if is_valid:
            contact.draft_subject = subject
            contact.draft_body = body
            contact.status = ContactStatus.DRAFTED
            success = True
            break

    session.commit()

    assert success is True
    assert contact.status == ContactStatus.DRAFTED
    assert contact.draft_subject == "Valid Draft"
    assert mock_llm.generate.call_count == 2
    session.close()


def test_generate_drafts_logic_retry_and_mark_failed(tmp_path, test_profile):
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    contact = Contact(
        name="Elena Rostova",
        email="elena2@example.com",
        type=ContactType.HR,
        status=ContactStatus.NEW
    )
    session.add(contact)
    session.commit()

    # Mock LLM that fails both attempts (exceeds word limit)
    mock_llm = MagicMock()
    mock_llm.generate.return_value = "SUBJECT: Too long\nBODY:\n" + ("word " * 150)

    prompt = build_draft_prompt(contact, test_profile)
    success = False
    for attempt in range(1, 3):
        raw = mock_llm.generate(prompt)
        is_valid, subject, body, err = parse_and_validate_draft(raw)
        if is_valid:
            contact.status = ContactStatus.DRAFTED
            success = True
            break

    if not success:
        contact.status = ContactStatus.DRAFT_FAILED

    session.commit()

    assert success is False
    assert contact.status == ContactStatus.DRAFT_FAILED
    assert mock_llm.generate.call_count == 2
    session.close()
