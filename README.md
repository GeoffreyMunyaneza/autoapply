# AutoApply

A fully automated job application platform that scrapes multiple job boards daily, scores matches against your profile, tailors your resume with Claude AI, generates cover letters, and auto-submits applications to 15+ ATS platforms — all from a Windows desktop app.

## What It Does

1. **Scrapes** LinkedIn, Indeed, ZipRecruiter, Google Jobs, and more via python-jobspy
2. **Scores** each job using semantic similarity + keyword matching (sentence-transformers)
3. **Filters** out irrelevant roles, internships, and stub listings
4. **Tailors** your resume per job using Claude AI (summary, skills, bullet keywords)
5. **Generates** a personalized cover letter per job (optional)
6. **Tracks** everything in `output/tracker_v2.xlsx` with color-coded statuses
7. **Notifies** you via Windows toast notification when new matches are found
8. **Submits** applications automatically via Playwright — Greenhouse, Lever, Workday, LinkedIn Easy Apply, Ashby, SmartRecruiters, iCIMS, Jobvite, BambooHR, Taleo, Rippling, Indeed Apply, and more
9. **Answers** ATS screening questions using `questions.yaml` + Claude fallback
10. **Runs on a schedule** — configurable cron expression, managed from the desktop app

---

## Project Structure

```
app_tracker_apply/
├── app.py                    # Desktop app entry point (CustomTkinter + tray)
├── main.py                   # Headless CLI entry point
├── config.yaml               # All settings — edit this first
├── questions.yaml            # Pre-answered ATS screening questions
├── requirements.txt          # Python dependencies
├── .env                      # Secrets (create from .env.example)
│
├── core/                     # Business logic
│   ├── scraper.py            # Multi-source job scraper (jobspy + custom)
│   ├── matcher.py            # Semantic + keyword scoring
│   ├── tailor.py             # Claude resume tailoring + cover letter generation
│   ├── tracker.py            # Excel job tracker (openpyxl)
│   ├── submitter.py          # Playwright ATS automation (15+ platforms)
│   └── notifier.py           # Windows toast + email notifications
│
├── services/                 # Orchestration layer
│   ├── pipeline.py           # Full scrape → score → tailor → track pipeline
│   ├── scheduler.py          # APScheduler cron automation
│   └── config.py             # Config load/save/inject helpers
│
├── gui/                      # Desktop UI (CustomTkinter)
│   ├── main_window.py        # Main window with sidebar navigation
│   ├── dashboard_frame.py    # Stats cards + pipeline controls
│   ├── jobs_frame.py         # Sortable/filterable job table
│   ├── log_frame.py          # Live log streaming
│   ├── settings_frame.py     # Config editor with save + scheduler reload
│   ├── runner.py             # Background pipeline thread
│   └── tray.py               # System tray icon (pystray)
│
└── output/                   # Auto-created on first run
    ├── tracker_v2.xlsx        # All tracked jobs
    ├── resumes/               # Tailored resumes (ready to submit)
    ├── pending/               # Resumes awaiting review + diff files
    ├── screenshots/           # Browser screenshots on submission failure
    └── autoapply.log          # Full run logs
```

---

## Quick Start

### Step 1 — Create the Python environment

```bash
conda create -n autoapply python=3.11 -y
conda activate autoapply
```

### Step 2 — Install dependencies

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

> **Note:** `docx2pdf` requires Microsoft Word installed on Windows (converts resumes to PDF before upload).

### Step 3 — Add your resumes

Place your base resume `.docx` files in the project root and update `config.yaml` under `resumes:`:

```yaml
resumes:
  ml: "Your_ML_Resume.docx"    # ML / AI / Data Science roles
  pm: "Your_PM_Resume.docx"    # Product Manager roles
```

### Step 4 — Create your `.env` file

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

All sensitive credentials live in `.env` — never in `config.yaml`.

```bash
# Required for resume tailoring + cover letters
ANTHROPIC_API_KEY=sk-ant-...

# Your contact info — used to fill ATS application forms
PROFILE_EMAIL=you@email.com
PROFILE_PHONE=555-555-5555

# Required for LinkedIn Easy Apply submissions
LINKEDIN_EMAIL=you@linkedin.com
LINKEDIN_PASSWORD=yourpassword

# Optional — email digest on pipeline completion
SMTP_FROM=you@gmail.com
SMTP_TO=you@gmail.com
SMTP_PASSWORD=your-gmail-app-password
```

### Step 5 — Configure your profile

Edit `config.yaml` → `user_profile:` with your background. This is passed to Claude on every tailoring call — the more detail you provide, the better the output.

```yaml
user_profile:
  name: "Your Name"
  background: |
    [Your title] with [X]+ years of [domain] experience.
    Key strengths: [skill1], [skill2], [skill3].
    Previous roles: [Company 1 — role], [Company 2 — role].
    Education: [Degree] from [School].
    Work authorization: [OPT / H1B / EAD / US Citizen / Green Card].
    Location: [City, State].
  differentiator_keywords:
    - "your niche skill"
  ml_match_profile: >
    Machine learning engineer with experience in ...
  pm_match_profile: >
    Technical product manager with experience in ...
```

### Step 6 — Configure screening questions

Edit `questions.yaml` to set your personal answers (current employer, city, state, zip, salary expectations, etc.). These are used to answer ATS form fields without calling Claude.

### Step 7 — Launch

**Desktop app (recommended):**
```bash
python app.py --show
```

**Headless CLI:**
```bash
# Run pipeline once — scrape, score, tailor, track. No submission.
python main.py

# Run pipeline + submit all Queued applications
python main.py --submit
```

---

## Desktop App

The Windows desktop app provides a full GUI for managing the pipeline:

- **Dashboard** — stats cards (Discovered / Queued / Applied / Interviews / Offers), one-click pipeline runs, recent jobs table
- **Jobs** — sortable/filterable table of all tracked jobs, right-click to open resume, cover letter, or job URL, change status
- **Logs** — live streaming log output with color-coded levels
- **Settings** — edit all config.yaml fields including automation schedule, search queries, Claude model, cover letter toggle

The app lives in the system tray when minimized. Right-click the tray icon to run the pipeline or open the window.

---

## Automation Schedule

Set up hands-free operation from the Settings tab or directly in `config.yaml`:

```yaml
schedule:
  enabled: true          # flip to true to enable background automation
  cron: "0 */4 * * *"   # every 4 hours  |  "0 8 * * *" = daily at 8 AM
  auto_submit: false     # true = fully automated: scrape → tailor → submit
```

---

## Enabling Auto-Submit

Submission is **disabled by default**. To turn it on:

1. Run the pipeline at least once to build up Queued applications
2. In `config.yaml`, set:

```yaml
submission:
  enabled: true
  headless: false            # keep false — allows you to handle CAPTCHAs
  review_before_submit: true # browser pauses before final click
  profile:
    first_name: "Your"
    last_name:  "Name"
    linkedin:   "https://www.linkedin.com/in/yourprofile"
    work_authorization:   "US Citizen"
    requires_sponsorship: false
```

3. Fill in `LINKEDIN_EMAIL` / `LINKEDIN_PASSWORD` in `.env`
4. Run: `python main.py --submit`

---

## Review Workflow

When `auto_approve: true` (default), tailored resumes go directly to `output/resumes/`. To review changes before use, set `auto_approve: false` via the Settings tab — resumes go to `output/pending/` with a `.diff.txt` showing exactly what changed.

```bash
# Interactive review — approve, reject, or open in Word
python review.py

# List pending resumes
python review.py --list

# Approve all pending resumes
python review.py --approve-all
```

---

## Configuration Reference

All settings live in `config.yaml`. Key sections:

| Section | Description |
|---|---|
| `user_profile` | Your name, background, and match profiles — fed to Claude |
| `search.queries` | Job search queries with `resume_type: ml` or `pm` |
| `search.sources` | Active job boards: linkedin, indeed, zip_recruiter, google, etc. |
| `filter` | Exclude keywords and minimum description length |
| `resumes` | Paths to your base `.docx` resume files |
| `claude` | Model and token settings for AI tailoring |
| `cover_letter` | Toggle auto cover letter generation |
| `schedule` | Cron schedule for automated pipeline runs |
| `submission` | Playwright auto-submit settings and applicant profile |
| `notifications` | Windows toast and email digest settings |

---

## How Resume Tailoring Works

Claude modifies **only**:
- Professional summary — mirrors the job's language
- Skills section — surfaces relevant skills you already have
- Individual bullet points — injects missing keywords naturally

It **never** fabricates experience, credentials, or metrics. All quantified achievements are preserved exactly. A `.diff.txt` is generated for every change so you can see exactly what moved.

---

## Supported ATS Platforms

| Platform | Detection |
|---|---|
| LinkedIn Easy Apply | `linkedin.com/jobs` |
| Greenhouse | `boards.greenhouse.io` |
| Lever | `jobs.lever.co` |
| Workday | `*.wd*.myworkdayjobs.com` |
| Ashby | `ashbyhq.com` |
| SmartRecruiters | `jobs.smartrecruiters.com` |
| iCIMS | `jobs.icims.com` |
| Jobvite | `jobs.jobvite.com` |
| BambooHR | `*.bamboohr.com/jobs` |
| Taleo (Oracle) | `*.taleo.net` |
| Rippling | `ats.rippling.com` |
| Wellfound | `wellfound.com/jobs` |
| Indeed Apply | `indeed.com/viewjob` |
| Glassdoor | `glassdoor.com/job-listing` |
| Monster | `monster.com/jobs` |
| Generic | any other URL (best-effort) |

---

## Tech Stack

| Component | Library |
|---|---|
| Desktop UI | [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) |
| System tray | [pystray](https://github.com/moses-palmer/pystray) + Pillow |
| Job scraping | [python-jobspy](https://github.com/speedyapply/JobSpy) |
| Semantic scoring | [sentence-transformers](https://sbert.net/) (`all-MiniLM-L6-v2`) |
| AI tailoring & Q&A | [Anthropic Claude](https://anthropic.com) (Haiku / Sonnet) |
| Browser automation | [Playwright](https://playwright.dev/python/) (Chromium) |
| Resume editing | python-docx |
| PDF conversion | docx2pdf (requires Word on Windows) |
| Tracker | openpyxl (Excel) |
| Scheduling | [APScheduler](https://apscheduler.readthedocs.io/) |
| Notifications | plyer (Windows toast) |
