# intern-outreach (warmreach)

A personal, approval-gated CLI tool that drafts personalized internship cold outreach emails and sends them only after explicit manual approval.

---

## Global Rules & Safety Architecture
- **Dry-run by default**: No real emails will ever be sent unless dry-run mode is explicitly disabled.
- **Approval-gated**: Emails transition through `drafted` -> `approved` -> `sent`. Nothing is sent without review.
- **Secret security**: API keys and OAuth tokens are strictly loaded from `.env` and local credential files which are ignored in `.gitignore`. Secrets are never printed or logged.
- **Throttling & Pacing**: Conservative daily sending caps (30 emails/day), 5-second pacing between LLM calls, and randomized delays (60–180 seconds).

---

## Project Structure

```text
.
├── config.py             # App configuration & settings (pydantic-settings)
├── database.py           # SQLite connection & database session management
├── models.py             # SQLAlchemy models (Contact, StatusEnum, ContactTypeEnum)
├── importer.py           # CSV contact import & validation logic
├── llm.py                # LLM client abstractions (GeminiClient, OllamaClient)
├── cli.py                # Typer CLI application entry point
├── contacts.csv          # Sample CSV template with mock contacts
├── requirements.txt      # Python dependencies
├── .env.example          # Environment variables template
├── .gitignore            # Git exclusion rules
├── tests/                # Unit & integration test suite
│   ├── __init__.py
│   ├── test_contacts.py  # Tests for email validation and duplicate handling
│   └── test_llm.py       # Mocked tests for LLM client, retries, and pacing
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

---

## Commands & Usage

### Stage 1: Contacts & Database
Import contacts from a CSV file into the database:
```bash
python cli.py import-contacts contacts.csv
```

### Stage 2: Test LLM Connection
Test the connectivity and generation of your configured LLM provider:
```bash
# Using default prompt "say hello"
python cli.py test-llm

# Or pass a custom prompt
python cli.py test-llm "Explain recursion in 1 sentence"
```

---

## Running Tests

Run the complete test suite (all LLM external calls are mocked):
```bash
pytest -v
```
