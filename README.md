# intern-outreach (warmreach)

A personal, approval-gated CLI tool that drafts personalized internship cold outreach emails and sends them only after explicit manual approval.

---

## Global Rules & Safety Architecture
- **Dry-run by default**: No real emails will ever be sent unless dry-run mode is explicitly disabled.
- **Approval-gated**: Emails transition through `drafted` -> `approved` -> `sent`. Nothing is sent without review.
- **Secret security**: API keys and OAuth tokens are strictly loaded from `.env` and local credential files which are ignored in `.gitignore`. Secrets are never printed or logged.
- **Throttling & Pacing**: Conservative daily sending caps (30 emails/day), 5-second pacing between LLM calls, and randomized delays (60–180 seconds).
- **Validation Guardrails**: Output must strictly adhere to `SUBJECT:` and `BODY:` formats, be strictly under 130 words, and contain zero hyperlinks/URLs.

---

## Project Structure

```text
.
├── config.py             # App configuration & settings (pydantic-settings)
├── database.py           # SQLite connection & database session management
├── models.py             # SQLAlchemy models (Contact, StatusEnum, ContactTypeEnum)
├── importer.py           # CSV contact import & validation logic
├── llm.py                # LLM client abstractions (GeminiClient, OllamaClient)
├── drafter.py            # Draft prompt templating, parser & validator (<130 words, no links)
├── cli.py                # Typer CLI application entry point
├── profile.yaml          # User profile configuration (name, degree, skills, projects, goal)
├── contacts.csv          # Sample CSV template with mock contacts
├── requirements.txt      # Python dependencies
├── .env.example          # Environment variables template
├── .gitignore            # Git exclusion rules
├── tests/                # Unit & integration test suite
│   ├── __init__.py
│   ├── test_contacts.py  # Tests for email validation and duplicate handling
│   ├── test_llm.py       # Mocked tests for LLM client, retries, and pacing
│   └── test_drafts.py    # Tests for draft generation, validation, and retry logic
└── README.md             # Documentation and testing instructions
```

---

## Setup Instructions

### 1. Prerequisites
- Python 3.11+
- Git

### 2. Virtual Environment Setup
Create and activate a virtual environment:

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
Open `.env` and configure:
- `LLM_PROVIDER`: Set to `gemini` or `ollama`.
- `GEMINI_API_KEY`: If using Gemini, paste your API key.
- `OLLAMA_BASE_URL` and `OLLAMA_MODEL`: If using Ollama (default `http://localhost:11434`, `llama3.2`).

### 5. Configure Your Profile
Edit [profile.yaml](file:///c:/Users/sansk/OneDrive/Desktop/autoapply/profile.yaml) with your real details:
- `name`: Your full name.
- `degree`: Your educational degree and university.
- `skills`: List of technical skills.
- `projects`: High-impact projects with names and descriptions.
- `internship_goal`: The role and areas you are targeting.

---

## Commands & Usage

### 1. Import Contacts
Import contacts from CSV into the local SQLite database:
```bash
python cli.py import-contacts contacts.csv
```

### 2. Test LLM Connectivity
Test the connectivity and generation of your configured LLM provider:
```bash
python cli.py test-llm "say hello"
```

### 3. Generate Drafts
Draft personalized emails for contacts with status `new`:
```bash
# Draft all new contacts
python cli.py generate-drafts

# Or limit to N contacts (e.g., test with 1 or 2 first)
python cli.py generate-drafts --limit 2
```
*Note: Drafts are validated to ensure they contain `SUBJECT:` and `BODY:`, are under 130 words, and contain no links. If an attempt fails validation, it retries once with feedback. If both fail, it is marked as `draft_failed`.*

### 4. Export Drafts for Review
Export all drafted emails to CSV for manual approval:
```bash
python cli.py export-drafts
```
*Creates `drafts_review.csv`.*

---

## Running Tests

Run the complete unit test suite (all LLM external calls are mocked):
```bash
pytest -v
```
