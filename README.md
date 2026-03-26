# Auto Job Application Bot

A Python bot that scans your iOS Mail (iCloud IMAP) for job opportunity emails and automatically applies to matching positions.

## Features

- **Email Scanning** — Connects to iCloud/iOS Mail via IMAP, fetches and parses job emails
- **Smart Classification** — Scores emails using keyword matching and sender analysis to identify job opportunities
- **Job Extraction** — Pulls structured data: title, company, location, salary, requirements, application URL
- **Preference Filtering** — Matches jobs against your desired roles, locations, salary, and blacklists
- **Auto-Application** — Fills out web forms using Playwright browser automation
- **Cover Letters** — Generates tailored cover letters via AI (OpenAI/Anthropic) or templates
- **Application Tracking** — SQLite database tracks all applications and prevents duplicates
- **Notifications** — Email summaries after each run

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Configure
cp config.example.yaml config.yaml
# Edit config.yaml with your iCloud credentials, profile, and preferences

# Run in dry-run mode (default — no actual applications)
python run.py

# Scan emails only
python run.py --scan-only

# View tracked applications
python run.py --list

# View statistics
python run.py --stats
```

## Setup

1. **iCloud App-Specific Password**: Go to [appleid.apple.com](https://appleid.apple.com) → Sign-In and Security → App-Specific Passwords → Generate one for this bot
2. **Fill `config.yaml`**: Your profile, skills, job preferences, and email credentials
3. **Resume**: Place your resume PDF at the path specified in config

## Architecture

See [PROMPT.md](PROMPT.md) for full architecture documentation and extension guide.

## Safety

- **Dry run by default** — Set `bot.dry_run: false` to enable real applications
- **No auto-submit** — Browser pauses for your review before submission
- **Deduplication** — Never applies to the same job twice
- **Secrets** — Use environment variables (`JOB_BOT_EMAIL_PASSWORD`, `JOB_BOT_AI_API_KEY`) instead of config file
