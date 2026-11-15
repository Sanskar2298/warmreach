import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Contact, ContactType, ContactStatus
from importer import normalize_and_validate_email, import_contacts_from_csv


@pytest.fixture
def db_session():
    """In-memory SQLite database session for isolated testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_normalize_and_validate_email():
    # Valid emails
    valid, email, err = normalize_and_validate_email("test@example.com")
    assert valid is True
    assert email == "test@example.com"
    assert err is None

    # Case normalization and trimming
    valid, email, err = normalize_and_validate_email("  User.Name@Example.COM ")
    assert valid is True
    assert email == "user.name@example.com"
    assert err is None

    # Invalid emails
    valid, _, err = normalize_and_validate_email("invalid-email")
    assert valid is False
    assert err is not None

    valid, _, err = normalize_and_validate_email("")
    assert valid is False
    assert "missing or empty" in err.lower()

    valid, _, err = normalize_and_validate_email(None)
    assert valid is False
    assert "missing or empty" in err.lower()

    valid, _, err = normalize_and_validate_email("user@.com")
    assert valid is False


def test_import_contacts_success(tmp_path, db_session):
    csv_content = """name,email,organization,role,type,research_area_or_team,notes,source_url
Alice Smith,alice.smith@example.com,TechCorp,Recruiter,hr,Talent,Good contact,https://example.com/alice
Dr. John Doe,john.doe@example.com,MIT,Professor,professor,Robotics,Published paper,https://example.com/john
"""
    csv_file = tmp_path / "contacts.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    result = import_contacts_from_csv(csv_file, db_session)
    db_session.commit()

    assert result.added == 2
    assert len(result.skipped_duplicate) == 0
    assert len(result.skipped_invalid) == 0

    contacts = db_session.query(Contact).all()
    assert len(contacts) == 2

    c1 = db_session.query(Contact).filter_by(email="alice.smith@example.com").first()
    assert c1 is not None
    assert c1.name == "Alice Smith"
    assert c1.type == ContactType.HR
    assert c1.status == ContactStatus.NEW

    c2 = db_session.query(Contact).filter_by(email="john.doe@example.com").first()
    assert c2 is not None
    assert c2.name == "Dr. John Doe"
    assert c2.type == ContactType.PROFESSOR


def test_import_contacts_duplicate_within_csv(tmp_path, db_session):
    csv_content = """name,email,organization,role,type
Alice Smith,alice@example.com,TechCorp,Recruiter,hr
Alice Copy,ALICE@example.com,TechCorp 2,Recruiter,hr
"""
    csv_file = tmp_path / "duplicates.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    result = import_contacts_from_csv(csv_file, db_session)
    db_session.commit()

    assert result.added == 1
    assert len(result.skipped_duplicate) == 1
    assert result.skipped_duplicate[0][1] == "alice@example.com"
    assert "Duplicate email in CSV import file" in result.skipped_duplicate[0][2]

    contacts = db_session.query(Contact).all()
    assert len(contacts) == 1
    assert contacts[0].name == "Alice Smith"


def test_import_contacts_duplicate_against_existing_db(tmp_path, db_session):
    # Pre-populate database with an existing contact
    existing = Contact(
        name="Existing Lead",
        email="existing@example.com",
        type=ContactType.HR,
        status=ContactStatus.NEW
    )
    db_session.add(existing)
    db_session.commit()

    csv_content = """name,email,organization,role,type
New Person,new@example.com,Startup Inc,HR,hr
Existing Attempt,EXISTING@example.com,Other Inc,HR,hr
"""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    result = import_contacts_from_csv(csv_file, db_session)
    db_session.commit()

    assert result.added == 1
    assert len(result.skipped_duplicate) == 1
    assert result.skipped_duplicate[0][1] == "existing@example.com"
    assert "already exists in database" in result.skipped_duplicate[0][2]

    all_contacts = db_session.query(Contact).all()
    assert len(all_contacts) == 2


def test_import_contacts_invalid_email_and_missing_name(tmp_path, db_session):
    csv_content = """name,email,organization,role,type
,valid@example.com,TechCorp,Recruiter,hr
Bad Email Guy,not-an-email,TechCorp,Recruiter,hr
Good Contact,good@example.com,TechCorp,Recruiter,hr
"""
    csv_file = tmp_path / "invalid.csv"
    csv_file.write_text(csv_content, encoding="utf-8")

    result = import_contacts_from_csv(csv_file, db_session)
    db_session.commit()

    assert result.added == 1
    assert len(result.skipped_invalid) == 2
    # Missing name
    assert "name" in result.skipped_invalid[0][2].lower()
    # Invalid email
    assert "invalid email format" in result.skipped_invalid[1][2].lower()

    contacts = db_session.query(Contact).all()
    assert len(contacts) == 1
    assert contacts[0].email == "good@example.com"
