# intern-outreach (warmreach)

A personal, approval-gated CLI tool that drafts personalized internship cold outreach emails and sends them only after explicit manual approval.

---

## Global Rules & Safety Architecture
- **Dry-run by default**: No real emails will ever be sent unless dry-run mode is explicitly disabled (`DRY_RUN=false` in `.env`) **AND** the `--confirm` CLI flag is passed.
- **Strict Approval Gate**: **ONLY** contacts with status `approved` can ever be sent.
- **Global Inviolable Block**: Contacts marked `replied`, `bounced`, or `do_not_contact` are permanently and globally blocked from all sending pipelines.
- **Single Follow-Up Rule**: Exactly at most **one** follow-up can ever be sent per contact, gated by status `sent` for 7+ days with no reply and `followup_sent_at is None`. Follow-ups must pass standard review and approval.
- **Zero-Risk Credentials**: All passwords, API keys, and credential files are strictly ignored in `.gitignore`.
- **Daily Rate Cap**: Hard limit of 30 sends per calendar day (counted dynamically from the database).
- **Anti-Spam Throttling**: 60–180 second randomized delay between consecutive live sends.
- **Fail-Safe Abort**: Immediately aborts batch transmission on any error to protect sender reputation.
- **Validation Guardrails**:
  - Initial drafts: `<130 words`, no links, `SUBJECT:` + `BODY:`.
  - Follow-up drafts: `<60 words`, no links, `SUBJECT:` + `BODY:`.

---

## Project Structure

```text
.
├── config.py             # App configuration & settings (pydantic-settings)
├── database.py           # SQLite connection & database session management
├── models.py             # SQLAlchemy models (Contact, StatusEnum, ContactTypeEnum)
├── importer.py           # CSV contact import & validation logic
├── llm.py                # LLM client abstractions (GeminiClient, OllamaClient)
├── drafter.py            # Draft & follow-up prompt builders, parsers & length validators
├── reviewer.py           # Interactive terminal review loop & approval gatekeeper
├── sender.py             # Dispatcher (SMTP/OAuth), global block check, daily cap & pacing
├── cli.py                # Typer CLI application entry point
├── profile.yaml          # User profile configuration (name, degree, skills, projects, goal)
├── contacts.csv          # Sample CSV template with mock contacts
├── requirements.txt      # Python dependencies
├── .env.example          # Environment variables template
├── .gitignore            # Git exclusion rules
├── tests/                # Unit & integration test suite
│   ├── __init__.py
│   ├── test_contacts.py  # Email validation and duplicate handling tests
│   ├── test_llm.py       # Mocked tests for LLM client, retries, and pacing
│   ├── test_drafts.py    # Tests for draft generation, validation, and retry logic
│   ├── test_review.py    # Tests for interactive review actions and sending safety gate
│   ├── test_sender.py    # Tests for daily cap enforcement, dry-run, and live send logic
│   └── test_followups.py # Tests for follow-up qualification, 60-word cap, and global status blocking
└── README.md             # Documentation and testing instructions
```

---

## Setup Instructions

### 1. Prerequisites
- Python 3.11+
- Git

### 2. Virtual Environment Setup
```bash
# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment
Copy `.env.example` to `.env`:
```bash
# Windows
copy .env.example .env

# Linux / macOS
cp .env.example .env
```
Configure your `.env`:
- `LLM_PROVIDER`: `gemini` (free from [Google AI Studio](https://aistudio.google.com/app/apikey)) or `ollama`.
- `GEMINI_API_KEY`: Your Gemini key.
- `EMAIL_SEND_METHOD`: `smtp` (easiest via [Google App Password](https://myaccount.google.com/apppasswords)) or `oauth`.
- `DRY_RUN`: Defaults to `true` for maximum safety.

---

## Commands & Usage Workflow

### 1. Import Contacts
Import contacts from CSV into SQLite:
```bash
python cli.py import-contacts contacts.csv
```

### 2. Test LLM Connectivity
```bash
python cli.py test-llm "say hello"
```

### 3. Generate Initial Drafts
Draft personalized emails for contacts with status `new` (<130 words, no links):
```bash
python cli.py generate-drafts --limit 5
```

### 4. Review and Approve Drafts
Interactively review, edit, approve, or reject drafts in the terminal:
```bash
python cli.py review
```
Keybindings in review mode:
- `a`: **Approve** (marks status as `approved` — only state eligible for sending).
- `e`: **Edit** (opens draft in editor or interactive prompts, then re-displays for approval).
- `s`: **Skip** (leaves as `drafted` to decide later).
- `d`: **Do Not Contact** (marks status as `do_not_contact`).
- `q`: **Quit & Save** (commits all progress and exits).

### 5. Send Approved Emails
- **Dry-run mode (default)**:
  ```bash
  python cli.py send
  ```
- **Real live send mode** (requires `DRY_RUN=false` in `.env` AND `--confirm` flag):
  ```bash
  python cli.py send --confirm
  ```

### 6. Manage Contact Status
Update status for contacts who responded, bounced, or should not be contacted again:
```bash
python cli.py mark user@example.com replied
python cli.py mark bad@example.com bounced
python cli.py mark unsubscribe@example.com do_not_contact
```
*(Any contact with status `replied`, `bounced`, or `do_not_contact` is globally blocked by the sender).*

### 7. Automated Follow-Ups (7+ Days, Max 1 Follow-up)
Find contacts sent 7+ days ago with no reply and no previous follow-up. Generates a polite, short follow-up (<60 words, no links) and moves them to `drafted`:
```bash
python cli.py followups
```
After drafting follow-ups, simply run `python cli.py review` to approve and `python cli.py send` to dispatch!

---

## Running Tests

Run the complete test suite (41 unit, safety, and integration tests):
```bash
pytest -v
```
