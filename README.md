# intern-outreach (warmreach)

A personal, approval-gated CLI tool that drafts personalized internship cold outreach emails and sends them only after explicit manual approval.

---

## Global Rules & Safety Architecture
- **Dry-run by default**: No real emails will ever be sent unless dry-run mode is explicitly disabled (`DRY_RUN=false` in `.env`) **AND** the `--confirm` CLI flag is passed.
- **Strict Approval Gate**: **ONLY** contacts with status `approved` can ever be sent. All other statuses (`new`, `drafted`, `draft_failed`, `sent`, `do_not_contact`, `bounced`) are strictly excluded.
- **Zero-Risk Credentials**: All passwords, API keys, and credential files are strictly ignored in `.gitignore`.
- **Daily Rate Cap**: Hard limit of 30 sends per calendar day (counted dynamically from the database).
- **Anti-Spam Throttling**: 60–180 second randomized delay between consecutive live sends.
- **Fail-Safe Abort**: Immediately aborts batch transmission on any error to protect sender reputation.
- **Validation Guardrails**: Output must strictly adhere to `SUBJECT:` and `BODY:` formats, be strictly under 130 words, and contain zero hyperlinks/URLs.

---

## Sending Methods: Choose What Works Best

You have two easy ways to send emails. **Method 1 (Gmail App Password) is recommended** because it takes 1 minute and requires zero Google Cloud or credit card setup:

### Method 1: Gmail App Password (Easiest & Free - Recommended)
1. Go to your Google Account App Passwords page: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
   *(Make sure 2-Step Verification is turned on in your Google account security settings).*
2. Name the app `intern-outreach` and click **Create**.
3. Google will give you a 16-character password (e.g. `abcd efgh ijkl mnop`).
4. In your `.env` file, set:
   ```env
   EMAIL_SEND_METHOD=smtp
   SENDER_EMAIL=your_email@gmail.com
   SENDER_APP_PASSWORD=abcdefghijklmnop
   ```

### Method 2: Google Cloud OAuth (`credentials.json`)
If you prefer official Google Cloud OAuth:
1. Go to [Google Cloud Console](https://console.cloud.google.com/) and create a project.
2. Enable the **Gmail API**.
3. Configure the **OAuth Consent Screen** (External, add scope `https://www.googleapis.com/auth/gmail.send`, add yourself as test user).
4. Create an **OAuth Client ID** for **Desktop App**, download it as `credentials.json`, and place it in this project folder.
5. In your `.env` file, set:
   ```env
   EMAIL_SEND_METHOD=oauth
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
Open `.env` and set:
- `LLM_PROVIDER`: `gemini` (free from [Google AI Studio](https://aistudio.google.com/app/apikey)) or `ollama`.
- `GEMINI_API_KEY`: Your Gemini key.
- `EMAIL_SEND_METHOD`: `smtp` (recommended) or `oauth`.
- `DRY_RUN`: Defaults to `true` for maximum safety.

---

## Commands & Usage Workflow

### Step 1: Import Contacts
Import contacts from CSV into the local SQLite database:
```bash
python cli.py import-contacts contacts.csv
```

### Step 2: Test LLM Connectivity
Test the connectivity of your LLM provider:
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
- `e`: **Edit** (opens draft in editor or interactive prompts, then re-displays for approval).
- `s`: **Skip** (leaves as `drafted` to decide later).
- `d`: **Do Not Contact** (marks status as `do_not_contact`).
- `q`: **Quit & Save** (commits all progress and exits).

### Step 5: Send Approved Emails

#### Dry-Run Mode (Default):
Test without sending any real emails. Prints all headers and body previews:
```bash
python cli.py send
```

#### Real Live Send Mode:
Only executes if `DRY_RUN=false` in `.env` **AND** `--confirm` is provided:
```bash
python cli.py send --confirm
```

---

## Running Tests

Run the complete test suite (34 unit, safety, and integration tests):
```bash
pytest -v
```
