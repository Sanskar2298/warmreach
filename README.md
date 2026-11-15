# intern-outreach (warmreach)

A personal, approval-gated CLI tool that drafts personalized internship cold outreach emails and sends them only after explicit manual approval.

---

## Global Rules & Safety Architecture
- **Dry-run by default**: No real emails will ever be sent unless dry-run mode is explicitly disabled (`DRY_RUN=false` in `.env`) **AND** the `--confirm` CLI flag is passed.
- **Strict Approval Gate**: **ONLY** contacts with status `approved` can ever be sent. All other statuses (`new`, `drafted`, `draft_failed`, `sent`, `do_not_contact`, `bounced`) are strictly excluded.
- **Secret Security**: API keys, `credentials.json`, and `token.json` are strictly stored in `.env` and local files ignored in `.gitignore`. Secrets are never printed or logged.
- **Daily Rate Cap**: Hard limit of 30 sends per calendar day (counted dynamically from the database).
- **Anti-Spam Throttling**: 60–180 second randomized delay between consecutive live sends.
- **Fail-Safe Abort**: Immediately aborts batch transmission on any Gmail API error.
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
├── reviewer.py           # Interactive terminal review loop & approval gatekeeper
├── sender.py             # Gmail API OAuth sender, daily cap & delay enforcement
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
│   ├── test_drafts.py    # Tests for draft generation, validation, and retry logic
│   ├── test_review.py    # Tests for interactive review actions and sending safety gate
│   └── test_sender.py    # Tests for daily cap enforcement, dry-run, and live send logic
└── README.md             # Documentation and testing instructions
```

---

## Google Cloud Console & Gmail API Setup Walkthrough

To enable sending cold emails through your Gmail account, set up OAuth2 credentials:

### Step 1: Create a Project in Google Cloud
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Click the project dropdown at the top left and click **New Project**.
3. Name it `intern-outreach` (or any name) and click **Create**.

### Step 2: Enable the Gmail API
1. In your project dashboard, navigate to **APIs & Services** > **Library**.
2. Search for **Gmail API**.
3. Click **Gmail API** and click **Enable**.

### Step 3: Configure the OAuth Consent Screen
1. Go to **APIs & Services** > **OAuth consent screen**.
2. Select **External** and click **Create**.
3. Fill in required details:
   - **App name**: `intern-outreach`
   - **User support email**: Your email
   - **Developer contact email**: Your email
4. Click **Save and Continue**.
5. Under **Scopes**, click **Add or Remove Scopes**, add `https://www.googleapis.com/auth/gmail.send`, and click **Update**.
6. Under **Test Users**, add your personal Gmail address from which you will send emails.
7. Click **Save and Continue**.

### Step 4: Create OAuth 2.0 Credentials
1. Go to **APIs & Services** > **Credentials**.
2. Click **Create Credentials** > **OAuth client ID**.
3. Select **Desktop app** as the Application type.
4. Name it `intern-outreach-cli`.
5. Click **Create**.
6. Click **Download JSON** and save the file in your project root as:
   ```text
   credentials.json
   ```
*(Note: `credentials.json` and `token.json` are already listed in `.gitignore` so they will never be tracked or committed to Git).*

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
Open `.env` and configure your settings:
- `LLM_PROVIDER`: Set to `gemini` or `ollama`.
- `GEMINI_API_KEY`: If using Gemini, paste your API key.
- `DRY_RUN`: Defaults to `true` for maximum safety.

### 5. Configure Your Profile
Edit [profile.yaml](file:///c:/Users/sansk/OneDrive/Desktop/autoapply/profile.yaml) with your real details:
- `name`: Your full name.
- `degree`: Your educational degree and university.
- `skills`: List of technical skills.
- `projects`: High-impact projects with names and descriptions.
- `internship_goal`: The role and areas you are targeting.

---

## Commands & Usage Workflow

### Step 1: Import Contacts
Import contacts from CSV into the local SQLite database:
```bash
python cli.py import-contacts contacts.csv
```

### Step 2: Test LLM Connectivity
Test the connectivity and generation of your configured LLM provider:
```bash
python cli.py test-llm "say hello"
```

### Step 3: Generate Drafts
Draft personalized emails for contacts with status `new`:
```bash
python cli.py generate-drafts --limit 2
```

### Step 4: Review and Approve Drafts
Interactively review, edit, approve, or reject drafts in the terminal:
```bash
python cli.py review
```
Keybindings in review mode:
- `a`: **Approve** (marks status as `approved` — the only state eligible for sending).
- `e`: **Edit** (opens draft in `$EDITOR` or interactive text prompts, then re-displays for approval).
- `s`: **Skip** (leaves as `drafted` to decide later).
- `d`: **Do Not Contact** (marks status as `do_not_contact`).
- `q`: **Quit & Save** (commits all progress and exits).

### Step 5: Send Approved Emails

#### Dry-Run Mode (Default):
Test without sending any real emails. Prints all headers and body text:
```bash
python cli.py send
```

#### Real Live Send Mode:
Only executes if `DRY_RUN=false` in `.env` **AND** `--confirm` is provided:
```bash
python cli.py send --confirm
```
*Note: On your very first live send, a browser window will open asking you to authenticate with your Gmail account and save `token.json` locally.*

---

## Running Tests

Run the complete test suite (33 unit, safety, and integration tests):
```bash
pytest -v
```
