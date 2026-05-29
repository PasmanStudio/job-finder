# Job Scraper 🔍

Automated UX/UI & Product Design job scraper that runs on **GitHub Actions** (free tier), deduplicates listings across runs, and sends an **email summary** after each run.

## Supported Job Boards

| Board | Method | Status |
|---|---|---|
| [RemoteOK](https://remoteok.com) | Public JSON API | ✅ Enabled by default |
| [We Work Remotely](https://weworkremotely.com) | RSS feed | ✅ Enabled by default |
| [LinkedIn](https://linkedin.com/jobs) | Playwright (headless) | ⚠️ Disabled — see notes |
| [Indeed](https://indeed.com) | HTTP scraping | ⚠️ Disabled — see notes |
| [Wellfound](https://wellfound.com) | Playwright (headless) | ⚠️ Disabled — see notes |

> **LinkedIn & Indeed notes:** Both platforms prohibit automated scraping in their ToS. Use at your own risk. LinkedIn requires account credentials stored as GitHub Secrets.

## How to Use

### 1. Fork / clone this repo

```bash
git clone https://github.com/mtotaro/job-scraper.git
cd job-scraper
pip install -r requirements.txt
```

### 2. Configure your search

Edit [`config/search_config.yaml`](config/search_config.yaml):

```yaml
search:
  keywords:
    - "UX designer"
    - "product designer"
    - "UI/UX"
    # add more...
  excluded_keywords:
    - "senior manager"
    - "sales"
```

### 3. Add your CV

Drop your CV into the `cv/` folder (PDF recommended). It will be attached to email-apply jobs automatically.

### 4. Set GitHub Secrets

Go to your repo → **Settings → Secrets and variables → Actions** and add:

| Secret | Description |
|---|---|
| `EMAIL_FROM` | Sender Gmail address |
| `EMAIL_TO` | Your email to receive summaries |
| `EMAIL_PASSWORD` | Gmail [App Password](https://support.google.com/accounts/answer/185833) |
| `LINKEDIN_EMAIL` | *(optional)* LinkedIn account email |
| `LINKEDIN_PASSWORD` | *(optional)* LinkedIn account password |

### 5. Run manually

Go to **Actions → Job Scraper → Run workflow**.

You can optionally specify:
- **boards**: `remoteok weworkremotely` (space-separated, leave empty for all)
- **dry_run**: check to preview without saving state or sending email

### 6. (Optional) Schedule automatic runs

Uncomment the `schedule:` block in [`.github/workflows/scrape.yml`](.github/workflows/scrape.yml):

```yaml
schedule:
  - cron: "0 9 * * 1,3,5"   # Mon / Wed / Fri at 09:00 UTC
```

## How Deduplication Works

After each run, the scraper saves a fingerprint (SHA-256 of board+URL) of every found job into `data/seen_jobs.json`. That file is **committed back to the repo** automatically. On the next run, only jobs NOT in that file are reported and emailed.

Entries older than `deduplication.retention_days` (default: 90) are pruned automatically.

## Project Structure

```
job-scraper/
├── .github/workflows/scrape.yml   # GitHub Actions workflow
├── config/search_config.yaml      # Your search preferences
├── cv/                            # Drop your CV here
├── data/seen_jobs.json            # Deduplication store (auto-managed)
├── src/
│   ├── core/
│   │   ├── models.py              # Job dataclass
│   │   ├── tracker.py             # Deduplication logic
│   │   ├── emailer.py             # Email summary
│   │   └── config.py             # Config loader
│   ├── scrapers/
│   │   ├── base.py                # Base scraper
│   │   ├── remoteok.py
│   │   ├── weworkremotely.py
│   │   ├── linkedin.py
│   │   ├── indeed.py
│   │   └── wellfound.py
│   └── main.py                   # Entry point
└── tests/
    └── test_tracker.py
```

## Running Locally

```bash
# Dry run (no state changes, no email)
python -m src.main --dry-run

# Run specific boards only
python -m src.main --boards remoteok weworkremotely

# Full run
python -m src.main
```

## Roadmap / Open Issues

See the [Issues tab](https://github.com/mtotaro/job-scraper/issues) for planned features including:
- Glassdoor scraper
- Dribbble Jobs scraper
- Coroflot scraper
- Auto-apply via email (for listings with a `mailto:` contact)
- LinkedIn Easy Apply automation

## Legal Disclaimer

This tool is for **personal use only**. Always review the Terms of Service of each job board before use. The authors are not responsible for any account bans or legal issues arising from its use.
