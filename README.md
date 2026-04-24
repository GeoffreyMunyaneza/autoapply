# AutoApply

AutoApply is a Windows desktop app and CLI for finding jobs, scoring them against your profile, tailoring resumes, generating cover letters, tracking applications, and optionally handing off browser-based submissions.

## What It Does

1. Scrapes jobs from LinkedIn, Indeed, ZipRecruiter, Google Jobs, and a few custom sources.
2. Scores jobs against your ML or PM profile.
3. Filters weak matches and duplicates.
4. Tailors resumes with Claude when an API key is available.
5. Generates optional cover letters.
6. Tracks everything in `output/tracker_v2.xlsx`.
7. Supports manual review before a tailored resume is queued.
8. Can fill many ATS flows with Playwright and pause for human review before submission.

## Project Structure

```text
app_tracker_apply/
|- app.py
|- main.py
|- review.py
|- config.yaml
|- questions.yaml
|- .env.example
|- requirements.txt
|- core/
|  |- scraper.py
|  |- matcher.py
|  |- tailor.py
|  |- tracker.py
|  |- submitter.py
|  `- notifier.py
|- services/
|  |- config.py
|  `- pipeline.py
|- gui/
|  |- main_window.py
|  |- dashboard_frame.py
|  |- jobs_frame.py
|  |- log_frame.py
|  |- settings_frame.py
|  |- runner.py
|  `- tray.py
`- output/
```

## Setup

### 1. Create and activate a Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
python -m playwright install chromium
```

`docx2pdf` needs Microsoft Word on Windows if you want PDF resume uploads.

### 3. Create your `.env`

Copy `.env.example` to `.env` and fill in the values you need.

Key fields:

- `ANTHROPIC_API_KEY` for resume tailoring and cover letters
- `PROFILE_EMAIL` and `PROFILE_PHONE` for application forms
- `LINKEDIN_EMAIL` and `LINKEDIN_PASSWORD` for LinkedIn Easy Apply
- `SMTP_*` only if you want email notifications

### 4. Add your base resumes

Put your base `.docx` resumes in the project root and point `config.yaml -> resumes` to them.

### 5. First open in the app

Launch the app:

```powershell
python app.py --show
```

Then open `Settings` and do this in order:

1. Click `Open config.yaml` and fill the `user_profile` template and resume paths.
2. Click `Open .env` and add your API key and contact info.
3. Click `Open questions.yaml` and fill common screening answers.
4. Return to `Settings` and tune search, review, notification, and submission options.
5. Go back to `Dashboard` and run the pipeline.

This is the intended first-step setup flow for the model and tailoring logic.

## Running

### Desktop app

```powershell
python app.py --show
python app.py --run
python app.py --run --submit
```

### CLI

```powershell
python main.py
python main.py --submit
```

### Review pending resumes

```powershell
python review.py
python review.py --list
python review.py --approve-all
```

If `review.auto_approve` is `false`, changed resumes land in `output/pending` until you approve them.

## Key Config Areas

- `user_profile`: profile text used for matching and Claude prompts
- `search`: job queries, sources, location, and search limits
- `filter`: exclusion rules and minimum description length
- `resumes`: base resume files for ML and PM roles
- `claude`: model and max token settings
- `cover_letter`: cover letter generation toggle
- `review`: whether tailored resumes are auto-approved
- `notifications`: toast and optional email notifications
- `screening`: path to `questions.yaml`
- `submission`: Playwright submission and applicant profile settings

## Testing

### Fast checks

```powershell
python -m compileall app.py main.py review.py core services gui
python app.py --help
python main.py --help
python review.py --help
```

### Smoke test without hitting job boards

Use a test config with no search queries and run:

```powershell
python main.py --config tests/fixtures/smoke_config.yaml
```

That validates config loading, logging, tracker initialization, and pipeline wiring without needing live network calls.

### Manual GUI test

1. Run `python app.py --show`.
2. Open `Settings`.
3. Use the setup buttons to open and fill `config.yaml`, `.env`, and `questions.yaml`.
4. Save settings.
5. From `Dashboard`, run `Run Pipeline`.
6. Check `Logs`, `Jobs`, and `output/tracker_v2.xlsx`.
7. If review mode is off, confirm resumes appear in `output/resumes`.
8. If review mode is on, confirm changed resumes appear in `output/pending`.

## Notes

- If `ANTHROPIC_API_KEY` is missing, the app still runs but skips tailoring.
- If `openpyxl` is missing, the tracker cannot run.
- If Playwright browsers are missing, install them with `python -m playwright install chromium`.
