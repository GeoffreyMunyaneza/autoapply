# AutoApply

A local background agent that scrapes job boards daily, scores matches against your profile, and uses Claude AI to tailor your resume for each job — saving everything to an Excel tracker and a resumes folder.

## What It Does

1. **Scrapes** LinkedIn and Indeed for your target roles (ML Engineer, AI Engineer, Data Scientist, PM, etc.)
2. **Filters** out internships, irrelevant roles, and low-quality listings
3. **Scores** each job against your profile using keyword matching
4. **Tailors** your resume for each match using Claude AI (keyword injection, summary rewrite, skills optimization)
5. **Tracks** every job in `output/tracker.xlsx` with match score, salary, source, and a link to the tailored resume
6. **Runs daily** automatically via Windows Task Scheduler

## Project Structure

```
autoapply/
├── main.py               # Orchestrator + scheduler
├── scraper.py            # LinkedIn + Indeed scraper (python-jobspy)
├── matcher.py            # Keyword scoring + resume type selection
├── tailor.py             # Claude API resume tailoring
├── tracker.py            # Excel job tracker
├── config.yaml           # Search queries, filters, schedule
├── requirements.txt      # Python dependencies
├── start.bat             # Windows launcher (double-click to run)
├── autoapply_task.xml    # Windows Task Scheduler definition
└── output/               # Generated (git-ignored)
    ├── tracker.xlsx      # All tracked jobs
    ├── resumes/          # Tailored .docx resumes
    └── autoapply.log     # Run logs
```

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/GeoffreyMunyaneza/autoapply.git
cd autoapply
```

### 2. Create the conda environment

```bash
conda create -n autoapply python=3.11 -y
conda activate autoapply
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
pip install python-jobspy --no-deps
pip install pandas playwright requests beautifulsoup4 tls-client regex markdownify
```

### 4. Add your resumes

Place your base resume files in the project root:
- `Geoffrey_Munyaneza_ML_Resume_Final.docx` — used for ML/AI/Data Science roles
- `Geoffrey_Munyaneza_PM_Resume.docx` — used for Product Manager roles

Update `config.yaml` → `resumes` section if your filenames differ.

### 5. Add your Anthropic API key

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Get your key at [console.anthropic.com](https://console.anthropic.com). Add credits under **Settings → Billing**.

### 6. Register the daily Task Scheduler job (Windows)

```powershell
Register-ScheduledTask -TaskName "AutoApply" -Xml (Get-Content autoapply_task.xml -Raw) -Force
```

This runs the pipeline daily at 8 AM. Edit `autoapply_task.xml` to change the time.

## Running

```bash
# Run once (test mode)
python main.py --once

# Run continuously (checks every 24 hours)
python main.py

# Or double-click start.bat
```

## Configuration

Edit `config.yaml` to customize:

```yaml
search:
  queries:
    - query: "Machine Learning Engineer"
      resume_type: ml
    - query: "Technical Product Manager AI"
      resume_type: pm

  location: "United States"
  remote_only: true
  results_per_query: 20
  hours_old: 48             # only jobs posted in last N hours

filter:
  exclude_keywords:
    - "internship"
    - "security clearance required"

schedule:
  interval_hours: 24        # how often to re-run

claude:
  model: "claude-haiku-4-5-20251001"
```

## Output

| File | Description |
|------|-------------|
| `output/tracker.xlsx` | All matched jobs with status, score, salary, links |
| `output/resumes/` | Tailored `.docx` resume for each job |
| `output/autoapply.log` | Full run logs |

The tracker uses a Kanban-style status column: **Discovered → Queued → Applied → Interviewing → Offer / Rejected**. Update it manually as you progress through applications.

## Resume Tailoring

Claude modifies only:
- Professional summary (mirrors the job's language)
- Skills section (surfaces relevant skills you already have)
- Bullet points (injects missing keywords naturally)

It **never fabricates** experience, credentials, or metrics. All quantified achievements are preserved exactly.

## Tech Stack

- **Scraping:** [python-jobspy](https://github.com/Bunsly/JobSpy) — LinkedIn + Indeed
- **AI tailoring:** [Anthropic Claude](https://anthropic.com) (Haiku)
- **Tracker:** openpyxl (Excel)
- **Scheduling:** Windows Task Scheduler + Python `schedule`
- **Resume editing:** python-docx

## Phase Roadmap

- [x] **Phase 1** — Job discovery, resume tailoring, Excel tracker (current)
- [ ] **Phase 2** — Auto-fill and submit applications (Greenhouse, Lever, Workday)
- [ ] **Phase 3** — Web dashboard, email notifications, follow-up automation
