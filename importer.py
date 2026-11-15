import csv
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional
from email_validator import validate_email, EmailNotValidError
from sqlalchemy.orm import Session
from models import Contact, ContactType, ContactStatus


class ImportResult:
    def __init__(self):
        self.added: int = 0
        self.skipped_duplicate: List[Tuple[int, str, str]] = []  # (row_num, email, reason)
        self.skipped_invalid: List[Tuple[int, str, str]] = []    # (row_num, raw_identifier, reason)

    @property
    def total_processed(self) -> int:
        return self.added + len(self.skipped_duplicate) + len(self.skipped_invalid)

    @property
    def total_skipped(self) -> int:
        return len(self.skipped_duplicate) + len(self.skipped_invalid)


def normalize_and_validate_email(email_str: Optional[str]) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Validate and normalize an email address.
    Returns (is_valid, normalized_email, error_message).
    """
    if not email_str or not email_str.strip():
        return False, None, "Email address is missing or empty"

    cleaned = email_str.strip()
    try:
        # check_deliverability=False avoids blocking network DNS queries during import/tests
        valid = validate_email(cleaned, check_deliverability=False)
        return True, valid.normalized.lower(), None
    except EmailNotValidError as e:
        return False, cleaned, str(e)


def parse_contact_type(type_str: Optional[str]) -> ContactType:
    if not type_str:
        return ContactType.HR
    cleaned = type_str.strip().lower()
    if cleaned in ("professor", "prof", "faculty", "academic", "pi"):
        return ContactType.PROFESSOR
    return ContactType.HR


def import_contacts_from_csv(file_path: Path, session: Session) -> ImportResult:
    """
    Import contacts from a CSV file into the database.
    - Validates email format
    - Skips duplicate emails (both intra-file and already existing in DB)
    - Records detailed failure reasons
    """
    result = ImportResult()
    seen_in_batch = set()

    # Preload existing emails from database for duplicate checking
    existing_emails = {row[0].lower() for row in session.query(Contact.email).all()}

    with open(file_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return result

        # Normalize column header lookup (lowercase, stripped)
        field_map = {fn.strip().lower(): fn for fn in reader.fieldnames if fn}

        def get_field(row: Dict[str, Any], key: str, default: Optional[str] = None) -> Optional[str]:
            col_name = field_map.get(key.lower())
            if col_name and row.get(col_name) is not None:
                val = str(row[col_name]).strip()
                return val if val else default
            return default

        for row_index, row in enumerate(reader, start=2):  # row 1 is header
            raw_email = get_field(row, "email")
            name = get_field(row, "name")

            if not name:
                result.skipped_invalid.append((row_index, raw_email or f"Row {row_index}", "Missing required 'name' field"))
                continue

            is_valid, normalized_email, error = normalize_and_validate_email(raw_email)
            if not is_valid:
                result.skipped_invalid.append((row_index, raw_email or f"Row {row_index}", f"Invalid email format: {error}"))
                continue

            # Check if duplicate in current batch
            if normalized_email in seen_in_batch:
                result.skipped_duplicate.append((row_index, normalized_email, "Duplicate email in CSV import file"))
                continue

            # Check if duplicate in database
            if normalized_email in existing_emails:
                result.skipped_duplicate.append((row_index, normalized_email, "Contact already exists in database"))
                continue

            # Parse contact type
            raw_type = get_field(row, "type")
            contact_type = parse_contact_type(raw_type)

            contact = Contact(
                name=name,
                email=normalized_email,
                organization=get_field(row, "organization"),
                role=get_field(row, "role"),
                type=contact_type,
                research_area_or_team=get_field(row, "research_area_or_team") or get_field(row, "team"),
                notes=get_field(row, "notes"),
                source_url=get_field(row, "source_url"),
                status=ContactStatus.NEW
            )

            session.add(contact)
            seen_in_batch.add(normalized_email)
            existing_emails.add(normalized_email)
            result.added += 1

    return result
