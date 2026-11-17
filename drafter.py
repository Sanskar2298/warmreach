import re
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

PROFILE_PATH = Path("profile.yaml")

DRAFT_SYSTEM_INSTRUCTIONS = """You are an expert at drafting concise, highly personalized cold emails for internship inquiries.
Follow these strict guidelines:
1. The tone must be professional, humble, specific, and direct.
2. DO NOT include any hyperlinks, URLs, markdown links, or brackets like [link].
3. The body MUST be under 130 words.
4. Output EXACTLY in this format with no other commentary:
SUBJECT: <Subject Line>
BODY:
<Body text>"""

def load_profile(path: Path = PROFILE_PATH) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Profile configuration file '{path}' not found.")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data

def build_draft_prompt(contact: Any, profile: Dict[str, Any]) -> str:
    """Build the prompt for cold email drafting."""
    contact_name = getattr(contact, "name", "Contact")
    contact_org = getattr(contact, "organization", "Organization") or "Organization"
    contact_role = getattr(contact, "role", "") or ""
    contact_type = getattr(contact, "type", "hr")
    contact_type_val = contact_type.value if hasattr(contact_type, "value") else str(contact_type)
    research_or_team = getattr(contact, "research_area_or_team", "") or ""
    notes = getattr(contact, "notes", "") or ""

    user_name = profile.get("name", "Applicant")
    degree = profile.get("degree", "Computer Science")
    skills = profile.get("skills", [])
    skills_str = ", ".join(skills) if isinstance(skills, list) else str(skills)
    
    projects = profile.get("projects", [])
    if isinstance(projects, list):
        projects_str = "\n".join(
            [f"- {p.get('name')}: {p.get('description')}" if isinstance(p, dict) else f"- {p}" for p in projects]
        )
    else:
        projects_str = str(projects)
    
    goal = profile.get("internship_goal", "Seeking an internship position")

    prompt = f"""{DRAFT_SYSTEM_INSTRUCTIONS}

Applicant Profile:
- Name: {user_name}
- Degree/Background: {degree}
- Skills: {skills_str}
- Projects:
{projects_str}
- Internship Goal: {goal}

Recipient Information:
- Recipient Name: {contact_name}
- Organization/University: {contact_org}
- Role/Title: {contact_role}
- Recipient Type: {contact_type_val}
- Research Area or Team: {research_or_team}
- Extra Notes / Context: {notes}

Draft a tailored, compelling cold email from {user_name} to {contact_name}.
Connect the applicant's relevant project or skill directly to the recipient's team or research area.
Keep the email body strictly under 130 words.
Do NOT include any links or URLs.

Format:
SUBJECT: <Subject Line>
BODY:
<Body text>
"""
    return prompt

def parse_and_validate_draft(raw_text: str) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """
    Validates that:
    1. Output contains SUBJECT and BODY sections.
    2. Body is under 130 words.
    3. Contains no links / URLs (http, https, www, markdown links [..](..)).
    
    Returns (is_valid, subject, body, error_message)
    """
    if not raw_text or not raw_text.strip():
        return False, None, None, "Raw LLM output is empty"

    # Match SUBJECT: ... and BODY: ...
    subject_match = re.search(r"^SUBJECT:\s*(.*?)(?=\nBODY:|\r\nBODY:|\Z)", raw_text, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    body_match = re.search(r"BODY:\s*(.*)", raw_text, re.IGNORECASE | re.DOTALL)

    if not subject_match or not body_match:
        return False, None, None, "Output missing 'SUBJECT:' or 'BODY:' delimiter"

    subject = subject_match.group(1).strip()
    # If multiline in subject, take the first line or collapse whitespace
    subject = " ".join(subject.split())

    body = body_match.group(1).strip()

    if not subject:
        return False, None, None, "Parsed subject is empty"
    if not body:
        return False, None, None, "Parsed body is empty"

    # Check for URLs / links
    # Pattern detects http://, https://, www., or markdown links [text](url)
    link_pattern = re.compile(r"(https?://\S+|www\.\S+|\[.*?\]\(.*?\))", re.IGNORECASE)
    if link_pattern.search(subject) or link_pattern.search(body):
        return False, subject, body, "Draft contains URLs or markdown links, which are forbidden"

    # Count words in body
    word_count = len(body.split())
    if word_count > 130:
        return False, subject, body, f"Body length ({word_count} words) exceeds limit of 130 words"

    return True, subject, body, None


FOLLOWUP_SYSTEM_INSTRUCTIONS = """You are an expert at drafting polite, very short follow-up emails for internship inquiries.
Follow these strict guidelines:
1. The tone must be polite, concise, and respectful of their busy schedule.
2. DO NOT include any hyperlinks, URLs, markdown links, or brackets like [link].
3. The body MUST be under 60 words.
4. Reference the previous message briefly without repeating the whole pitch.
5. Output EXACTLY in this format with no other commentary:
SUBJECT: <Subject Line>
BODY:
<Body text>"""

def build_followup_prompt(contact: Any, profile: Dict[str, Any]) -> str:
    """Build the prompt for cold email follow-up."""
    contact_name = getattr(contact, "name", "Contact")
    contact_org = getattr(contact, "organization", "Organization") or "Organization"
    previous_subject = getattr(contact, "draft_subject", "") or "Internship Inquiry"
    user_name = profile.get("name", "Applicant")

    # Ensure subject has Re: or appropriate follow-up prefix
    suggested_subject = previous_subject if previous_subject.lower().startswith("re:") else f"Re: {previous_subject}"

    prompt = f"""{FOLLOWUP_SYSTEM_INSTRUCTIONS}

Applicant Name: {user_name}
Recipient Name: {contact_name}
Organization: {contact_org}
Original Subject: {suggested_subject}

Draft a brief, polite follow-up checking in on the previous note.
Keep the email body strictly under 60 words.
Do NOT include any links or URLs.

Format:
SUBJECT: {suggested_subject}
BODY:
<Body text>
"""
    return prompt

def parse_and_validate_followup(raw_text: str, default_subject: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """
    Validates that:
    1. Output contains SUBJECT and BODY sections (or uses default subject if specified).
    2. Body is under 60 words.
    3. Contains no links / URLs.
    
    Returns (is_valid, subject, body, error_message)
    """
    if not raw_text or not raw_text.strip():
        return False, None, None, "Raw LLM output is empty"

    subject_match = re.search(r"^SUBJECT:\s*(.*?)(?=\nBODY:|\r\nBODY:|\Z)", raw_text, re.IGNORECASE | re.DOTALL | re.MULTILINE)
    body_match = re.search(r"BODY:\s*(.*)", raw_text, re.IGNORECASE | re.DOTALL)

    if not body_match:
        return False, None, None, "Output missing 'BODY:' delimiter"

    if subject_match:
        subject = subject_match.group(1).strip()
        subject = " ".join(subject.split())
    else:
        subject = default_subject or "Follow-up regarding internship inquiry"

    body = body_match.group(1).strip()

    if not subject:
        return False, None, None, "Parsed subject is empty"
    if not body:
        return False, None, None, "Parsed body is empty"

    link_pattern = re.compile(r"(https?://\S+|www\.\S+|\[.*?\]\(.*?\))", re.IGNORECASE)
    if link_pattern.search(subject) or link_pattern.search(body):
        return False, subject, body, "Follow-up contains URLs or markdown links, which are forbidden"

    word_count = len(body.split())
    if word_count > 60:
        return False, subject, body, f"Follow-up body length ({word_count} words) exceeds limit of 60 words"

    return True, subject, body, None
