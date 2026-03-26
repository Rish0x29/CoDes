# Auto Job Application Bot - AI Self-Prompt

You are building and maintaining an **Auto Job Application Bot** — a Python tool that connects to a user's iOS Mail (iCloud IMAP), scans for job opportunity emails, and automatically applies to matching positions.

---

## System Architecture

```
┌──────────────────────────────────────────────────────┐
│                    run.py (Entry Point)               │
│                         │                             │
│                   main.py (Orchestrator)              │
│                    ┌────┼────┐                        │
│                    │    │    │                         │
│            ┌───────┘    │    └───────┐                │
│            ▼            ▼            ▼                │
│     email_reader    job_parser    config.py           │
│     (IMAP fetch)    (classify)   (YAML loader)       │
│            │            │                             │
│            ▼            ▼                             │
│     ┌──────────────────────┐                         │
│     │  application_tracker │  (SQLite DB)            │
│     └──────────────────────┘                         │
│            │            │                             │
│            ▼            ▼                             │
│     cover_letter    auto_applier                     │
│     (AI/template)   (Playwright)                     │
│            │            │                             │
│            └─────┬──────┘                            │
│                  ▼                                    │
│             notifier.py                              │
│           (email summary)                            │
└──────────────────────────────────────────────────────┘
```

## Module Descriptions

### `config.py`
- Loads `config.yaml` (YAML format)
- Supports environment variable overrides for secrets (`JOB_BOT_EMAIL_PASSWORD`, `JOB_BOT_AI_API_KEY`)
- Validates required fields
- See `config.example.yaml` for all options

### `email_reader.py`
- Connects to iCloud Mail via IMAP4_SSL (`imap.mail.me.com:993`)
- Requires an **app-specific password** (generate at https://appleid.apple.com)
- Fetches emails from the last N days
- Parses: subject, sender, date, text body, HTML body, links
- Supports `mark_as_read` option

### `job_parser.py`
- **Classification**: Scores emails 0-1 on likelihood of being a job opportunity
  - Checks sender against known job platforms (LinkedIn, Indeed, Glassdoor, etc.)
  - Keyword matching in subject/body
  - Application link detection
- **Extraction**: Pulls structured data — job title, company, location, salary, requirements, application URL
- **Filtering**: Matches jobs against user preferences (desired roles, locations, blacklists, salary)

### `application_tracker.py`
- SQLite database with two tables:
  - `applications` — tracks each job applied to (company, title, status, cover letter, timestamps)
  - `email_log` — tracks processed emails to avoid re-processing
- Prevents duplicate applications
- Provides stats and listing views

### `cover_letter.py`
- Template-based (Jinja2) cover letter generation as fallback
- AI-powered generation via OpenAI or Anthropic APIs
- Tailors letters using job details + user profile

### `auto_applier.py`
- Uses Playwright for browser automation
- Detects common form fields (name, email, phone, LinkedIn, etc.) by name/placeholder/label
- Uploads resume automatically
- Fills cover letter textareas
- **DRY RUN MODE** (default): Simulates without submitting
- Pauses for user review before final submission

### `notifier.py`
- Generates run summary (emails scanned, jobs found, applications made)
- Sends email summary via SMTP
- Rich console output

### `main.py`
- CLI with argparse: `--dry-run`, `--stats`, `--list`, `--scan-only`, `--config`
- 5-step pipeline: Connect → Scan → Filter → Apply → Summarize
- Rich console tables and progress output

---

## How to Extend This Bot

### Add a New Job Platform Parser
1. Add platform-specific sender patterns to `JOB_PLATFORM_SENDERS` in `job_parser.py`
2. Add URL patterns to `APPLICATION_URL_PATTERNS`
3. If the platform has a unique email format, add a specialized parser method

### Add Direct API Integration (LinkedIn, Indeed, etc.)
1. Create a new module `api_applier.py`
2. Implement platform-specific API clients
3. Add API credentials to `config.yaml`
4. Call from `main.py` as an alternative to browser-based application

### Add Resume Tailoring
1. Create `resume_tailor.py` module
2. Use AI to modify resume bullet points based on job requirements
3. Generate a PDF per application
4. Update `auto_applier.py` to use tailored resume

### Add Scheduling
1. Use the `schedule` library (already in requirements)
2. Add a `--daemon` flag to `main.py`
3. Run `run_bot()` on the configured interval

### Add Web Dashboard
1. Create a Flask/FastAPI app that reads from the SQLite DB
2. Show application stats, timeline, status updates
3. Allow manual status updates (interview, offer, rejected)

---

## Running the Bot

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Copy and edit config
cp config.example.yaml config.yaml
# Edit config.yaml with your details

# Dry run (default - no actual applications)
python run.py --dry-run

# Scan emails only
python run.py --scan-only

# Full run
python run.py

# View stats
python run.py --stats

# List all applications
python run.py --list
```

## Key Design Decisions
- **Dry run by default**: Safety first — `bot.dry_run: true` in config
- **No auto-submit**: Browser pauses for human review
- **Deduplication**: Tracks processed emails and applied jobs in SQLite
- **Modular**: Each component works independently and can be tested/replaced
- **Multi-provider AI**: Supports both OpenAI and Anthropic for cover letters

## Security Notes
- Never commit `config.yaml` (it contains passwords) — it's in `.gitignore`
- Use app-specific passwords for iCloud (not your Apple ID password)
- Use environment variables for secrets in CI/production
- The bot never auto-submits without `dry_run: false` explicitly set
