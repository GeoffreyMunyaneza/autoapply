# AutoApply — Implementation Plan & Task Tracker

This document breaks down all tasks, requirements, and implementation approach derived from the AutoApply PRD. Each phase lists what must be built, what requirements must be met, and how each will be achieved.

---

## Phase 1 — Local Background Agent

**Goal:** Run on the user's machine, scrape jobs daily, tailor resumes with AI, track everything in Excel.

### Tasks

- [x] **Set up project environment**
  - Conda env `autoapply` with Python 3.11
  - Install all dependencies (`requirements.txt`)
  - `.env` file for secrets (git-ignored)

- [x] **Job scraping (`scraper.py`)**
  - Scrape 5 sources: LinkedIn, Indeed, ZipRecruiter, Glassdoor, Google Jobs
  - Each source scraped independently — one failure does not block others
  - Sources configurable in `config.yaml` under `search.sources`
  - Return normalized job objects: title, company, location, salary, description, URL, source, date posted

- [x] **Job filtering & scoring (`matcher.py`)**
  - Score jobs by keyword match against ML and PM profiles
  - Hard-filter: exclude internships, VP roles, security clearance, short descriptions, missing URLs
  - Auto-select resume type (ML vs PM) based on job title

- [x] **AI resume tailoring (`tailor.py`)**
  - Call Claude API per job
  - Inject missing JD keywords into existing bullet points naturally
  - Rewrite professional summary to mirror JD language
  - Optimize skills section
  - Preserve all formatting, metrics, and quantified achievements
  - Save tailored `.docx` per job to `output/resumes/`

- [x] **Resume formatting fidelity fix (`tailor.py`)**
  - **Problem was:** Implementation collapsed all runs into the first run, losing inline formatting (bold company names, italic text, mixed font sizes within a line)
  - **Fix applied:** Three-strategy run-aware approach:
    - Single run → direct text replace
    - All runs same format → collapse safely into first run
    - Mixed format → distribute new text proportionally across runs by word boundary, preserving bold/italic positions
  - **Root cause fixed:** `para.runs` returns new objects on each access; snapshotted once to avoid identity-comparison bug that was clearing all runs

- [x] **Job tracker (`tracker.py`)**
  - Create/update `output/tracker.xlsx`
  - Columns: ID, Title, Company, Location, Salary, Source, URL, Date Posted, Match Score, Resume Type, Status, Resume Path, Date Added, Notes
  - Color-code rows by status
  - Clickable hyperlinks for job URL and resume path

- [x] **Orchestrator + scheduler (`main.py`)**
  - Run full pipeline: scrape → filter → tailor → track
  - Skip jobs already in tracker (deduplication by ID)
  - Schedule daily runs via Python `schedule` library
  - Log all activity to `output/autoapply.log`

- [x] **Daily automation**
  - Windows Task Scheduler task (runs at 8 AM daily)
  - `start.bat` for manual one-click launch

- [x] **Configuration (`config.yaml`)**
  - Search queries with resume type mapping
  - Location, remote-only toggle, results per query, hours old
  - Exclude keyword list
  - Schedule interval
  - Claude model selection

### Requirements to Meet

| Requirement | How It Is Met |
|---|---|
| Only surface recent jobs | `hours_old: 24` — only jobs posted in the last 24 hours returned |
| No duplicate listings | Job ID = `source_company_title`; skip if already in tracker |
| Multiple job sources | 5 sources: LinkedIn, Indeed, ZipRecruiter, Glassdoor, Google Jobs |
| One source failure doesn't block run | Each source scraped in isolation with individual try/except |
| Never fabricate resume content | Claude system prompt explicitly forbids it; metrics preserved |
| Preserve resume formatting | Run-aware proportional distribution preserves bold/italic inline formatting within changed paragraphs |
| API key never committed | `.env` in `.gitignore`; loaded via `python-dotenv` |
| Handle locked files gracefully | `tailor.py` retries with versioned filename on `PermissionError` |
| Filter internships | "internship" and "intern " in `exclude_keywords` |

### Status: ✅ Complete

---

## Phase 2 — Automated Application Submission

**Goal:** Auto-fill and submit job applications on ATS platforms on behalf of the user.

### Tasks

- [ ] **User profile store**
  - Store personal info: name, email, phone, location, LinkedIn URL, GitHub URL
  - Work authorization details (OPT status, start date, duration)
  - Standard application answers (years of experience, salary expectation, visa sponsorship)

- [ ] **ATS platform adapters**
  - Greenhouse: API-based form fill + resume upload
  - Lever: API-based form fill + resume upload
  - Workday: Playwright headless browser automation
  - LinkedIn Easy Apply: Playwright automation
  - Indeed Quick Apply: Playwright automation

- [ ] **Cover letter generation**
  - Claude generates a tailored 3-paragraph cover letter per job
  - Grounded in user's real experience — no fabrication
  - Saved alongside tailored resume in `output/resumes/`

- [ ] **CAPTCHA handling**
  - Detect CAPTCHA during form fill
  - Pause session, send push notification to user's phone
  - Hold session open for 10 minutes awaiting manual solve
  - Timeout and log if not resolved

- [ ] **Application submission logging**
  - Update tracker status to "Applied" on successful submission
  - Record: submission timestamp, ATS platform, cover letter used, form fields submitted

- [ ] **Feedback loop for matching**
  - User actions (approve / skip / reject) on tracker update match model weights
  - Retrain keyword scoring based on historical approve/reject signals

### Requirements to Meet

| Requirement | How It Will Be Met |
|---|---|
| Support Greenhouse, Lever, Workday, LinkedIn, Indeed | One Playwright adapter per platform |
| Pre-fill identical fields once | Central user profile YAML/JSON loaded per submission |
| Resume PDF upload per job | Convert tailored `.docx` to PDF before submission |
| CAPTCHA not auto-bypassed | Human-in-the-loop: pause + push notification |
| Application not double-submitted | Check tracker status before submitting; skip if already "Applied" |
| Cover letter grounded in real experience | Claude instructed with same guardrails as resume tailoring |

### Status: 🔲 Not Started

---

## Phase 3 — Web Dashboard & Analytics

**Goal:** Replace the Excel tracker with a live web app; add notifications, analytics, and follow-up automation.

### Tasks

- [ ] **Backend API (`FastAPI`)**
  - REST endpoints for jobs, applications, resumes, analytics
  - PostgreSQL database for persistent storage
  - Auth (single-user JWT for personal use)

- [ ] **React frontend**
  - Kanban board: Discovered → Queued → Applied → Interviewing → Offer / Rejected / Withdrawn
  - Each card: company logo, title, salary, match score, applied date, resume version
  - Filters: date range, company, match score, status, source platform

- [ ] **Notifications**
  - Email or Slack alert when a new high-match job (>80%) is discovered
  - Daily digest of new jobs found

- [ ] **Follow-up automation**
  - Auto-draft follow-up email 7 days after application with no response
  - Draft saved to dashboard for user review and one-click send

- [ ] **Weekly analytics report**
  - Applications sent, callback rate, top-performing resume variants
  - Most-matched skills across accepted vs rejected applications
  - Response rate by company size, source platform, match score

- [ ] **Database migration from Excel**
  - Import `output/tracker.xlsx` into PostgreSQL on first launch

### Requirements to Meet

| Requirement | How It Will Be Met |
|---|---|
| Single source of truth for all applications | PostgreSQL replaces Excel; all pipeline writes go to DB |
| Kanban status tracking | React drag-and-drop board synced to DB |
| Follow-up at 7 days | Scheduled job checks `applied_date`; drafts email via Claude |
| Analytics on callback rate | Store outcome per application; compute rates on dashboard |
| No data loss from Excel phase | Migration script reads tracker.xlsx → inserts into DB |

### Status: 🔲 Not Started

---

## Non-Functional Requirements (All Phases)

| Requirement | Approach |
|---|---|
| Runs locally on Windows (Phase 1–2) | Python + Windows Task Scheduler; no server needed |
| No ATS bans | Rate limiting + respectful polling intervals |
| Secrets never exposed | `.env` + `.gitignore`; no hardcoded keys anywhere |
| Resilient to file locks | PermissionError fallback with versioned filenames |
| Logs for debugging | Rotating log file at `output/autoapply.log` |
| Reproducible setup | `requirements.txt` + conda env + README setup steps |
| Works after laptop restart | Task Scheduler persists across reboots |
