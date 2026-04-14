"""
submitter.py — Automated application submission via Playwright.

Supported ATS platforms:
  LinkedIn Easy Apply  linkedin.com/jobs
  Greenhouse           boards.greenhouse.io / {co}.greenhouse.io
  Lever                jobs.lever.co
  Workday              {co}.wd*.myworkdayjobs.com
  Ashby                ashbyhq.com
  SmartRecruiters      jobs.smartrecruiters.com
  iCIMS                jobs.icims.com
  Jobvite              jobs.jobvite.com
  BambooHR             {co}.bamboohr.com/jobs
  Taleo (Oracle)       {co}.taleo.net
  Rippling             ats.rippling.com
  Wellfound            wellfound.com  (EasyApply-style inline modal)
  Indeed Apply         indeed.com     (IndeedApply multi-step modal)
  Glassdoor Apply      glassdoor.com
  Monster              monster.com
  Generic              best-effort fallback for any unknown portal

Screening questions:
  1. questions.yaml   — loaded once at startup; substring-match lookup
  2. Hard-coded rules — work auth, sponsorship, YOE, salary, etc.
  3. Claude API       — fallback for anything not covered above

Usage:
  from submitter import submit_application, detect_ats
  success = submit_application(job, resume_path, profile_cfg,
                               submission_cfg, tracker_path, api_key)
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

from core.scraper import Job
from core.tracker import update_status

logger = logging.getLogger(__name__)

# ── ATS detection ──────────────────────────────────────────────────────────────

ATS_PATTERNS = {
    "linkedin": [
        r"linkedin\.com/jobs",
    ],
    "greenhouse": [
        r"boards\.greenhouse\.io",
        r"\.greenhouse\.io",
        r"job_app\?for=",
    ],
    "lever": [
        r"jobs\.lever\.co",
        r"lever\.co/",
    ],
    "workday": [
        r"\.wd\d+\.myworkdayjobs\.com",
        r"myworkdayjobs\.com",
    ],
    "ashby": [
        r"ashbyhq\.com",
        r"jobs\.ashbyhq\.com",
    ],
    "smartrecruiters": [
        r"jobs\.smartrecruiters\.com",
    ],
    "icims": [
        r"jobs\.icims\.com",
        r"\.icims\.com/jobs",
    ],
    "jobvite": [
        r"jobs\.jobvite\.com",
        r"hire\.jobvite\.com",
    ],
    "bamboohr": [
        r"\.bamboohr\.com/jobs",
        r"\.bamboohr\.com/careers",
    ],
    "taleo": [
        r"\.taleo\.net",
        r"taleo\.net/careersection",
    ],
    "rippling": [
        r"ats\.rippling\.com",
        r"rippling\.com/jobs",
    ],
    "wellfound": [
        r"wellfound\.com/jobs",
        r"wellfound\.com/l/",
        r"angel\.co/l/",
    ],
    "indeed": [
        r"indeed\.com/viewjob",
        r"indeed\.com/jobs",
        r"smartapply\.indeed\.com",
    ],
    "glassdoor": [
        r"glassdoor\.com/job-listing",
        r"glassdoor\.com/Jobs",
    ],
    "monster": [
        r"monster\.com/jobs",
        r"monster\.com/job-openings",
    ],
}


def detect_ats(url: str) -> str:
    """Return the ATS platform name for a job URL, or 'generic'."""
    for ats, patterns in ATS_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return ats
    return "generic"


# ── Playwright helpers ─────────────────────────────────────────────────────────

def _get_browser(headless: bool = False):
    """Launch a Playwright Chromium browser. Caller must close it."""
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=headless, slow_mo=60)
        return pw, browser
    except ImportError:
        raise RuntimeError(
            "Playwright not installed. Run: pip install playwright && playwright install chromium"
        )


def _fill_field(page, selectors: list[str], value: str) -> bool:
    """Try a list of CSS selectors; fill the first visible one. Returns success."""
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.fill(value)
                return True
        except Exception:
            continue
    return False


def _upload_file(page, selectors: list[str], file_path: str) -> bool:
    """Try to set a file input to file_path."""
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el:
                el.set_input_files(file_path)
                return True
        except Exception:
            continue
    return False


def _human_delay(min_ms: int = 300, max_ms: int = 900) -> None:
    import random
    time.sleep(random.randint(min_ms, max_ms) / 1000)


# ── docx → PDF conversion ──────────────────────────────────────────────────────

def _to_pdf(docx_path: str) -> str:
    """
    Convert a .docx to PDF (Windows, requires Microsoft Word).
    Returns the PDF path on success, or the original .docx path on failure.
    """
    pdf_path = Path(docx_path).with_suffix(".pdf")
    if pdf_path.exists():
        return str(pdf_path)
    try:
        from docx2pdf import convert
        convert(docx_path, str(pdf_path))
        logger.info(f"  Converted to PDF: {pdf_path.name}")
        return str(pdf_path)
    except ImportError:
        logger.debug("docx2pdf not installed — using .docx for upload")
    except Exception as e:
        logger.debug(f"PDF conversion failed: {e} — using .docx")
    return docx_path


def _upload_resume(page, resume_path: str, selectors: list[str] | None = None) -> bool:
    """
    Upload resume, preferring PDF. Falls back to .docx if conversion fails.
    selectors: extra CSS selectors to try before defaults.
    """
    upload_path = _to_pdf(resume_path)
    default_sels = [
        "input[type='file'][name='resume']",
        "input[type='file'][accept*='pdf']",
        "input[type='file'][accept*='docx']",
        "input[type='file']",
    ]
    all_sels = (selectors or []) + default_sels
    return _upload_file(page, all_sels, upload_path)


# ── Claude-powered screening question answering ────────────────────────────────

_KNOWN_ANSWERS: dict[str, str] = {}  # question_key → answer cache

# ── questions.yaml loader ──────────────────────────────────────────────────────

_YAML_ANSWERS: dict[str, str] | None = None   # loaded once


def _load_yaml_answers(questions_file: str = "questions.yaml") -> dict[str, str]:
    """
    Load pre-answered questions from questions.yaml (singleton — loaded once).
    Returns a dict of {lowercase_question_fragment: answer}.
    """
    global _YAML_ANSWERS
    if _YAML_ANSWERS is not None:
        return _YAML_ANSWERS
    try:
        import yaml
        with open(questions_file, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        raw = data.get("answers", {})
        _YAML_ANSWERS = {k.lower(): str(v) for k, v in raw.items()}
        logger.info(f"Loaded {len(_YAML_ANSWERS)} pre-answered questions from {questions_file}")
    except FileNotFoundError:
        logger.debug(f"questions.yaml not found — using built-in answers only")
        _YAML_ANSWERS = {}
    except Exception as e:
        logger.warning(f"Could not load questions.yaml: {e}")
        _YAML_ANSWERS = {}
    return _YAML_ANSWERS


def _lookup_yaml(question_text: str) -> str | None:
    """Return a YAML-defined answer for question_text, or None if not found."""
    answers = _load_yaml_answers()
    q = question_text.lower()
    # Exact substring match — longest key wins to be more specific
    matches = [(k, v) for k, v in answers.items() if k in q]
    if not matches:
        return None
    # Pick the most specific (longest) match
    return max(matches, key=lambda x: len(x[0]))[1]


def _answer_question(
    question_text: str,
    field_type: str,
    options: list[str],
    job: "Job",
    profile: dict,
    api_key: str,
) -> str:
    """
    Return an answer for an ATS screening question.
    Priority: questions.yaml → hard-coded rules → Claude API.
    """
    q = question_text.lower().strip()

    # 1. questions.yaml lookup (fastest, fully customisable)
    yaml_answer = _lookup_yaml(q)
    if yaml_answer is not None:
        # For select/radio, verify the answer matches one of the options
        if options and yaml_answer:
            match = next((o for o in options if yaml_answer.lower() in o.lower()), None)
            if match:
                return match
            # If no exact match, fall through to rules/Claude for better option selection
        elif not options:
            return yaml_answer

    # 2. Hard-coded rules — always reliable
    if any(kw in q for kw in ["authorized to work", "authorised to work",
                                "legally authorized", "eligible to work in"]):
        return "Yes"
    if "sponsorship" in q and ("require" in q or "need" in q or "visa" in q):
        return "Yes" if profile.get("requires_sponsorship", True) else "No"
    if re.search(r"years.{0,20}experience", q):
        return "4"
    if "expected salary" in q or "desired salary" in q or "salary expectation" in q:
        return "130000"
    if "start date" in q or "available to start" in q or "when can you start" in q:
        return "Within 2 weeks"
    if "willing to relocate" in q or "open to relocation" in q:
        return "Yes"
    if "remote" in q and ("work" in q or "position" in q):
        return "Yes"
    if "highest level of education" in q or "degree" in q:
        return "Master's Degree" if not options else next(
            (o for o in options if "master" in o.lower()), options[-1])
    if "gender" in q:
        return "Prefer not to say" if not options else next(
            (o for o in options if "prefer" in o.lower()), options[0])
    if "race" in q or "ethnicity" in q:
        return "Black or African American" if not options else next(
            (o for o in options if "black" in o.lower() or "african" in o.lower()), options[-1])
    if "veteran" in q:
        return "No" if not options else next(
            (o for o in options if "not" in o.lower() or "no" in o.lower()), options[0])
    if "disability" in q:
        return "No" if not options else next(
            (o for o in options if "not" in o.lower() or "no" in o.lower()), options[0])

    # Skip optional cover letter fields
    if "cover letter" in q and "optional" in q:
        return ""

    # Cache check
    cache_key = f"{q[:80]}|{field_type}"
    if cache_key in _KNOWN_ANSWERS:
        return _KNOWN_ANSWERS[cache_key]

    if not api_key:
        return options[0] if options else ""

    # Use Claude for anything not covered above
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        options_str = f"\nOptions: {' | '.join(options)}" if options else ""
        name  = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip() or "the applicant"
        title = profile.get("current_title", "the applicant")
        auth  = profile.get("work_authorization", "authorized to work")
        sponsorship = "requires visa sponsorship" if profile.get("requires_sponsorship") else "no sponsorship needed"
        result = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            system=(
                f"You are filling out a job application for {name} "
                f"({title}, {auth}, {sponsorship}) "
                f"applying for '{job.title}' at '{job.company}'. "
                "Return ONLY the answer text — no explanation, no quotes."
            ),
            messages=[{"role": "user", "content":
                f"Question: {question_text}{options_str}\nField type: {field_type}"}],
        )
        answer = result.content[0].text.strip()
        _KNOWN_ANSWERS[cache_key] = answer
        return answer
    except Exception as e:
        logger.debug(f"Claude question answering failed: {e}")
        return options[0] if options else ""


# ── LinkedIn Easy Apply ────────────────────────────────────────────────────────

_LINKEDIN_COOKIES_FILE = Path(".linkedin_session.json")


def _linkedin_save_cookies(context) -> None:
    try:
        _LINKEDIN_COOKIES_FILE.write_text(
            json.dumps(context.cookies()), encoding="utf-8"
        )
        logger.debug("LinkedIn session cookies saved.")
    except Exception as e:
        logger.debug(f"Could not save LinkedIn cookies: {e}")


def _linkedin_load_cookies(context) -> bool:
    if not _LINKEDIN_COOKIES_FILE.exists():
        return False
    try:
        cookies = json.loads(_LINKEDIN_COOKIES_FILE.read_text(encoding="utf-8"))
        context.add_cookies(cookies)
        return True
    except Exception as e:
        logger.debug(f"Could not load LinkedIn cookies: {e}")
        return False


def _linkedin_login(page, credentials: dict) -> bool:
    """Log into LinkedIn with email/password. Returns True on success."""
    email = credentials.get("email", "")
    password = credentials.get("password", "")
    if not email or not password:
        logger.warning(
            "  LinkedIn credentials missing — set submission.linkedin.email / .password in config.yaml"
        )
        return False

    logger.info("  Logging into LinkedIn...")
    page.goto("https://www.linkedin.com/login", timeout=30_000)
    page.wait_for_load_state("networkidle", timeout=20_000)

    page.fill("#username", email)
    _human_delay(400, 700)
    page.fill("#password", password)
    _human_delay(300, 600)
    page.click("button[type='submit']")

    try:
        page.wait_for_url("**/feed**", timeout=25_000)
        logger.info("  LinkedIn login successful.")
        return True
    except Exception:
        if "checkpoint" in page.url or "challenge" in page.url:
            logger.warning("  LinkedIn security challenge — complete it manually then press Enter.")
            input("  >> Press Enter after completing the challenge: ")
            return True
        logger.warning(f"  LinkedIn login may have failed (url={page.url})")
        return False


def _linkedin_is_logged_in(page) -> bool:
    """Quick check via feed redirect."""
    try:
        page.goto("https://www.linkedin.com/feed", timeout=15_000)
        page.wait_for_load_state("networkidle", timeout=10_000)
        return "/feed" in page.url or "/in/" in page.url
    except Exception:
        return False


def _linkedin_fill_page(
    page,
    job: "Job",
    resume_path: str,
    profile: dict,
    api_key: str,
) -> None:
    """Fill all visible fields on the current LinkedIn Easy Apply modal page."""

    # ── Resume upload ──────────────────────────────────────────────────────
    upload_path = _to_pdf(resume_path)
    for fi in page.query_selector_all("input[type='file']"):
        try:
            fi.set_input_files(upload_path)
            _human_delay(600, 1200)
            break
        except Exception:
            continue

    # ── Text / number / tel / email inputs ────────────────────────────────
    for inp in page.query_selector_all(
        "input[type='text'], input[type='number'], input[type='tel'], input[type='email']"
    ):
        try:
            if not inp.is_visible():
                continue
            # Skip already-filled inputs
            try:
                if inp.input_value():
                    continue
            except Exception:
                pass

            label_text = _get_label(page, inp)
            if not label_text:
                continue
            answer = _answer_question(label_text, "text", [], job, profile, api_key)
            if answer:
                inp.fill(answer)
                _human_delay(200, 500)
        except Exception:
            continue

    # ── Textareas ─────────────────────────────────────────────────────────
    for ta in page.query_selector_all("textarea"):
        try:
            if not ta.is_visible():
                continue
            try:
                if ta.input_value():
                    continue
            except Exception:
                pass
            label_text = _get_label(page, ta)
            if not label_text:
                continue
            answer = _answer_question(label_text, "textarea", [], job, profile, api_key)
            if answer:
                ta.fill(answer)
                _human_delay(200, 500)
        except Exception:
            continue

    # ── Native <select> elements ──────────────────────────────────────────
    for sel in page.query_selector_all("select"):
        try:
            if not sel.is_visible():
                continue
            label_text = _get_label(page, sel)
            opts = sel.evaluate("el => [...el.options].map(o => o.text)")
            current = sel.input_value()
            if current and current not in ("", "Select an option"):
                continue
            answer = _answer_question(label_text, "select", opts, job, profile, api_key)
            if answer:
                try:
                    sel.select_option(label=answer)
                except Exception:
                    try:
                        sel.select_option(index=1)  # pick first real option
                    except Exception:
                        pass
                _human_delay(200, 400)
        except Exception:
            continue

    # ── Radio button groups (fieldsets) ──────────────────────────────────
    for fs in page.query_selector_all("fieldset"):
        try:
            legend = fs.query_selector("legend, h3, span[data-test-form-element-label]")
            if not legend:
                continue
            question = legend.inner_text().strip()
            radios = fs.query_selector_all("input[type='radio']")
            if not radios or any(r.is_checked() for r in radios):
                continue

            opts = []
            for r in radios:
                rid = r.get_attribute("id")
                if rid:
                    lbl = page.query_selector(f"label[for='{rid}']")
                    if lbl:
                        opts.append(lbl.inner_text().strip())

            answer = _answer_question(question, "radio", opts, job, profile, api_key)

            for r in radios:
                rid = r.get_attribute("id")
                if rid:
                    lbl = page.query_selector(f"label[for='{rid}']")
                    if lbl and answer.lower() in lbl.inner_text().lower():
                        lbl.click()
                        _human_delay(200, 400)
                        break
        except Exception:
            continue


def _get_label(page, element) -> str:
    """Extract a readable label for a form element."""
    try:
        el_id = element.get_attribute("id")
        if el_id:
            label = page.query_selector(f"label[for='{el_id}']")
            if label:
                return label.inner_text().strip()
    except Exception:
        pass
    for attr in ("aria-label", "placeholder", "name"):
        try:
            val = element.get_attribute(attr)
            if val:
                return val.strip()
        except Exception:
            pass
    return ""


def _submit_linkedin(
    page,
    job: "Job",
    resume_path: str,
    profile: dict,
    submission_cfg: dict,
    api_key: str = "",
) -> bool:
    """
    Submit via LinkedIn Easy Apply.
    Handles login, cookie persistence, and the multi-step modal form.
    """
    review_mode = submission_cfg.get("review_before_submit", True)
    linkedin_cfg = submission_cfg.get("linkedin", {})

    logger.info(f"  [LinkedIn Easy Apply] {job.title} @ {job.company}")

    # ── Ensure we're logged in ─────────────────────────────────────────────
    context = page.context
    cookies_loaded = _linkedin_load_cookies(context)

    # Navigate to the job URL directly to check login status
    page.goto(job.url, timeout=30_000)
    page.wait_for_load_state("networkidle", timeout=20_000)

    # If redirected to login page, we need to authenticate
    if "login" in page.url or "authwall" in page.url or not cookies_loaded:
        if not _linkedin_login(page, linkedin_cfg):
            logger.warning("  LinkedIn login failed — falling back to generic handler.")
            page.goto(job.url, timeout=30_000)
            page.wait_for_load_state("networkidle", timeout=20_000)
            return _submit_generic(page, job, resume_path, profile)
        _linkedin_save_cookies(context)
        # Navigate to the job page after login
        page.goto(job.url, timeout=30_000)
        page.wait_for_load_state("networkidle", timeout=20_000)

    _human_delay(1000, 2000)

    # ── Click Easy Apply button ────────────────────────────────────────────
    try:
        apply_btn = page.wait_for_selector(
            'button[aria-label*="Easy Apply"], '
            '.jobs-apply-button, '
            'button:has-text("Easy Apply")',
            timeout=10_000,
        )
        if not apply_btn or not apply_btn.is_visible():
            logger.warning("  Easy Apply button not visible — may be an external application.")
            return False
        apply_btn.click()
        _human_delay(800, 1500)
    except Exception as e:
        logger.warning(f"  Could not click Easy Apply: {e}")
        return False

    # ── Wait for modal ─────────────────────────────────────────────────────
    try:
        page.wait_for_selector(
            ".jobs-easy-apply-modal, [data-test-modal], "
            "[aria-label*='Apply'], .artdeco-modal",
            timeout=10_000,
        )
    except Exception:
        logger.warning("  Easy Apply modal did not appear.")
        return False

    # ── Multi-step form loop ───────────────────────────────────────────────
    for step in range(20):
        _human_delay(600, 1000)
        _linkedin_fill_page(page, job, resume_path, profile, api_key)
        _human_delay(500, 800)

        # Final submit button
        submit_btn = page.query_selector(
            'button[aria-label="Submit application"], '
            'button:has-text("Submit application")'
        )
        if submit_btn and submit_btn.is_visible():
            if review_mode:
                logger.info("  Form filled — browser open for your review.")
                try:
                    input("  >> Press Enter to submit, or Ctrl+C to cancel: ")
                    submit_btn.click()
                    page.wait_for_load_state("networkidle", timeout=15_000)
                    logger.info(f"  Submitted: {job.title} @ {job.company}")
                    _linkedin_save_cookies(context)
                    return True
                except KeyboardInterrupt:
                    logger.info("  Submission cancelled.")
                    return False
            else:
                submit_btn.click()
                page.wait_for_load_state("networkidle", timeout=15_000)
                logger.info(f"  Auto-submitted: {job.title} @ {job.company}")
                _linkedin_save_cookies(context)
                return True

        # Review step
        for aria in [
            'button[aria-label="Review your application"]',
            'button:has-text("Review")',
        ]:
            btn = page.query_selector(aria)
            if btn and btn.is_visible():
                btn.click()
                break
        else:
            # Next step
            next_found = False
            for aria in [
                'button[aria-label="Continue to next step"]',
                'button:has-text("Next")',
                'button[aria-label="Next"]',
            ]:
                btn = page.query_selector(aria)
                if btn and btn.is_visible():
                    btn.click()
                    next_found = True
                    break
            if not next_found:
                logger.warning(f"  Step {step}: no navigation button found — stopping.")
                break

    logger.warning("  LinkedIn Easy Apply: did not reach submit button.")
    return False


# ── Greenhouse ─────────────────────────────────────────────────────────────────

def _submit_greenhouse(page, job: "Job", resume_path: str, profile: dict) -> bool:
    logger.info(f"  [Greenhouse] {job.url}")
    page.goto(job.url, timeout=30_000)
    page.wait_for_load_state("networkidle", timeout=20_000)
    _human_delay()

    _fill_field(page, ["#first_name", "input[name='first_name']"], profile.get("first_name", ""))
    _fill_field(page, ["#last_name", "input[name='last_name']"], profile.get("last_name", ""))
    _fill_field(page, ["#email", "input[name='email']", "input[type='email']"], profile.get("email", ""))
    _fill_field(page, ["#phone", "input[name='phone']", "input[type='tel']"], profile.get("phone", ""))
    _fill_field(page, ["#linkedin_profile", "input[name='linkedin_profile']"], profile.get("linkedin", ""))
    _fill_field(page, ["input[name='website']", "#website"], profile.get("portfolio", ""))
    _human_delay()

    _upload_resume(page, resume_path)
    _human_delay(500, 1200)

    cover_letter = profile.get("cover_letter_text", "")
    if cover_letter:
        _fill_field(page, [
            "textarea[name='cover_letter']", "#cover_letter",
            "textarea[aria-label*='cover']",
        ], cover_letter)

    _fill_work_auth(page, profile)
    return True


# ── Lever ──────────────────────────────────────────────────────────────────────

def _submit_lever(page, job: "Job", resume_path: str, profile: dict) -> bool:
    logger.info(f"  [Lever] {job.url}")
    page.goto(job.url, timeout=30_000)
    page.wait_for_load_state("networkidle", timeout=20_000)
    _human_delay()

    full_name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
    _fill_field(page, ["input[name='name']", "#name"], full_name)
    _fill_field(page, ["input[name='email']", "#email", "input[type='email']"], profile.get("email", ""))
    _fill_field(page, ["input[name='phone']", "#phone", "input[type='tel']"], profile.get("phone", ""))
    _fill_field(page, ["input[name='org']", "#org"], profile.get("current_company", ""))
    _fill_field(page, ["input[name='urls[LinkedIn]']", "input[placeholder*='LinkedIn']"], profile.get("linkedin", ""))
    _fill_field(page, ["input[name='urls[GitHub]']", "input[placeholder*='GitHub']"], profile.get("github", ""))
    _human_delay()

    _upload_resume(page, resume_path)
    _human_delay(500, 1200)
    return True


# ── Workday ────────────────────────────────────────────────────────────────────

def _submit_workday(page, job: "Job", resume_path: str, profile: dict) -> bool:
    logger.info(f"  [Workday] {job.url}")
    page.goto(job.url, timeout=40_000)
    page.wait_for_load_state("networkidle", timeout=30_000)
    _human_delay(800, 1500)

    try:
        apply_btn = page.query_selector(
            "a[data-automation-id='applyButton'], button:has-text('Apply')"
        )
        if apply_btn and apply_btn.is_visible():
            apply_btn.click()
            page.wait_for_load_state("networkidle", timeout=20_000)
            _human_delay(500, 1000)
    except Exception:
        pass

    _fill_field(page, [
        "input[data-automation-id='legalNameSection_firstName']",
        "input[aria-label*='First Name']",
    ], profile.get("first_name", ""))
    _fill_field(page, [
        "input[data-automation-id='legalNameSection_lastName']",
        "input[aria-label*='Last Name']",
    ], profile.get("last_name", ""))
    _fill_field(page, [
        "input[data-automation-id='email']", "input[type='email']",
    ], profile.get("email", ""))
    _fill_field(page, [
        "input[data-automation-id='phone-number']", "input[type='tel']",
    ], profile.get("phone", ""))
    _human_delay()

    _upload_resume(page, resume_path, [
        "input[data-automation-id='file-upload-input-ref']",
    ])
    _human_delay(800, 1500)
    return True


# ── Ashby ──────────────────────────────────────────────────────────────────────

def _submit_ashby(page, job: "Job", resume_path: str, profile: dict) -> bool:
    logger.info(f"  [Ashby] {job.url}")
    page.goto(job.url, timeout=30_000)
    page.wait_for_load_state("networkidle", timeout=20_000)
    _human_delay()

    # Navigate to apply page if on a job detail page
    try:
        apply_btn = page.query_selector(
            "a[href*='apply'], button:has-text('Apply'), a:has-text('Apply')"
        )
        if apply_btn and apply_btn.is_visible():
            apply_btn.click()
            page.wait_for_load_state("networkidle", timeout=15_000)
            _human_delay(500, 1000)
    except Exception:
        pass

    full_name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
    _fill_field(page, [
        "input[name='_systemfield_name']",
        "input[placeholder*='Full name']",
        "input[placeholder*='Name']",
        "input[name='name']",
    ], full_name)
    _fill_field(page, [
        "input[name='_systemfield_email']", "input[type='email']",
    ], profile.get("email", ""))
    _fill_field(page, [
        "input[name='_systemfield_phone']", "input[type='tel']",
    ], profile.get("phone", ""))
    _fill_field(page, [
        "input[name='_systemfield_linkedin']",
        "input[placeholder*='LinkedIn']",
    ], profile.get("linkedin", ""))

    _human_delay()
    _upload_resume(page, resume_path, [
        "input[type='file'][name='_systemfield_resume']",
    ])
    _human_delay(500, 1200)
    return True


# ── SmartRecruiters ────────────────────────────────────────────────────────────

def _submit_smartrecruiters(page, job: "Job", resume_path: str, profile: dict) -> bool:
    logger.info(f"  [SmartRecruiters] {job.url}")
    page.goto(job.url, timeout=30_000)
    page.wait_for_load_state("networkidle", timeout=20_000)
    _human_delay()

    try:
        apply_btn = page.query_selector(
            "button[data-hook='apply'], a[data-hook='apply'], button:has-text('Apply')"
        )
        if apply_btn and apply_btn.is_visible():
            apply_btn.click()
            page.wait_for_load_state("networkidle", timeout=15_000)
            _human_delay(500, 1000)
    except Exception:
        pass

    _fill_field(page, ["input#firstName", "input[name='firstName']"], profile.get("first_name", ""))
    _fill_field(page, ["input#lastName", "input[name='lastName']"], profile.get("last_name", ""))
    _fill_field(page, [
        "input#email", "input[type='email']", "input[name='email']",
    ], profile.get("email", ""))
    _fill_field(page, [
        "input#phoneNumber", "input[type='tel']",
    ], profile.get("phone", ""))
    _human_delay()

    _upload_resume(page, resume_path, [
        "input[type='file'][data-hook='resume-upload']",
    ])
    _human_delay(500, 1200)
    return True


# ── iCIMS ──────────────────────────────────────────────────────────────────────

def _submit_icims(page, job: "Job", resume_path: str, profile: dict) -> bool:
    logger.info(f"  [iCIMS] {job.url}")
    page.goto(job.url, timeout=30_000)
    page.wait_for_load_state("networkidle", timeout=20_000)
    _human_delay()

    try:
        apply_btn = page.query_selector(
            ".iCIMS_Anchor, button:has-text('Apply'), a:has-text('Apply Now')"
        )
        if apply_btn and apply_btn.is_visible():
            apply_btn.click()
            page.wait_for_load_state("networkidle", timeout=15_000)
            _human_delay(500, 1000)
    except Exception:
        pass

    _fill_field(page, [
        "input[name='firstname']", "input[id*='firstname']",
    ], profile.get("first_name", ""))
    _fill_field(page, [
        "input[name='lastname']", "input[id*='lastname']",
    ], profile.get("last_name", ""))
    _fill_field(page, ["input[type='email']"], profile.get("email", ""))
    _fill_field(page, ["input[type='tel']"], profile.get("phone", ""))

    _upload_resume(page, resume_path)
    _human_delay(500, 1200)
    return True


# ── Jobvite ────────────────────────────────────────────────────────────────────

def _submit_jobvite(page, job: "Job", resume_path: str, profile: dict) -> bool:
    logger.info(f"  [Jobvite] {job.url}")
    page.goto(job.url, timeout=30_000)
    page.wait_for_load_state("networkidle", timeout=20_000)
    _human_delay()

    # Jobvite may show a job detail page first — click Apply
    try:
        btn = page.query_selector("a.jv-btn-apply, a[class*='apply'], button:has-text('Apply')")
        if btn and btn.is_visible():
            btn.click()
            page.wait_for_load_state("networkidle", timeout=15_000)
            _human_delay(500, 1000)
    except Exception:
        pass

    _fill_field(page, ["input[id='jv-field-fname']", "input[name='firstname']",
                        "input[placeholder*='First']"], profile.get("first_name", ""))
    _fill_field(page, ["input[id='jv-field-lname']", "input[name='lastname']",
                        "input[placeholder*='Last']"], profile.get("last_name", ""))
    _fill_field(page, ["input[id='jv-field-email']", "input[type='email']"],
                profile.get("email", ""))
    _fill_field(page, ["input[id='jv-field-phone']", "input[type='tel']"],
                profile.get("phone", ""))
    _fill_field(page, ["input[id='jv-field-linkedin']", "input[placeholder*='LinkedIn']"],
                profile.get("linkedin", ""))

    _human_delay()
    _upload_resume(page, resume_path, ["input[id='jv-field-resume']",
                                        "input[type='file'][name='resume']"])
    _human_delay(500, 1200)
    return True


# ── BambooHR ───────────────────────────────────────────────────────────────────

def _submit_bamboohr(page, job: "Job", resume_path: str, profile: dict) -> bool:
    logger.info(f"  [BambooHR] {job.url}")
    page.goto(job.url, timeout=30_000)
    page.wait_for_load_state("networkidle", timeout=20_000)
    _human_delay()

    # BambooHR application is usually in an iframe
    try:
        btn = page.query_selector("a[href*='apply'], button:has-text('Apply')")
        if btn and btn.is_visible():
            btn.click()
            page.wait_for_load_state("networkidle", timeout=15_000)
            _human_delay(500, 1000)
    except Exception:
        pass

    # Try main frame first, then iframe
    for frame in [page, *page.frames]:
        try:
            if _fill_field(frame, ["input[name='firstName']", "input[id*='firstName']",
                                    "input[placeholder*='First']"], profile.get("first_name", "")):
                _fill_field(frame, ["input[name='lastName']", "input[id*='lastName']",
                                     "input[placeholder*='Last']"], profile.get("last_name", ""))
                _fill_field(frame, ["input[type='email']", "input[name='email']"],
                            profile.get("email", ""))
                _fill_field(frame, ["input[type='tel']", "input[name='phone']"],
                            profile.get("phone", ""))
                _upload_resume(frame, resume_path)
                _human_delay(500, 1000)
                return True
        except Exception:
            continue

    return True


# ── Taleo (Oracle) ─────────────────────────────────────────────────────────────

def _submit_taleo(page, job: "Job", resume_path: str, profile: dict) -> bool:
    """
    Taleo is complex and varies widely by company. This covers the common
    'Apply Now' flow on taleo.net careersection pages.
    """
    logger.info(f"  [Taleo] {job.url}")
    page.goto(job.url, timeout=40_000)
    page.wait_for_load_state("networkidle", timeout=30_000)
    _human_delay(800, 1500)

    # Click Apply / Apply Now button
    for selector in [
        "a[title*='Apply']", "a:has-text('Apply Now')", "a:has-text('Apply')",
        "button:has-text('Apply')",
    ]:
        try:
            btn = page.query_selector(selector)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_load_state("networkidle", timeout=20_000)
                _human_delay(800, 1500)
                break
        except Exception:
            continue

    # Taleo multi-step: fill basic info on first page
    _fill_field(page, ["input[id*='firstName']", "input[name*='FirstName']"],
                profile.get("first_name", ""))
    _fill_field(page, ["input[id*='lastName']", "input[name*='LastName']"],
                profile.get("last_name", ""))
    _fill_field(page, ["input[type='email']", "input[id*='email']"],
                profile.get("email", ""))
    _fill_field(page, ["input[type='tel']", "input[id*='phone']"],
                profile.get("phone", ""))

    _upload_resume(page, resume_path)
    _human_delay(500, 1000)
    return True


# ── Rippling ───────────────────────────────────────────────────────────────────

def _submit_rippling(page, job: "Job", resume_path: str, profile: dict) -> bool:
    logger.info(f"  [Rippling] {job.url}")
    page.goto(job.url, timeout=30_000)
    page.wait_for_load_state("networkidle", timeout=20_000)
    _human_delay()

    try:
        btn = page.query_selector("button:has-text('Apply'), a:has-text('Apply')")
        if btn and btn.is_visible():
            btn.click()
            page.wait_for_load_state("networkidle", timeout=15_000)
            _human_delay(500, 1000)
    except Exception:
        pass

    _fill_field(page, ["input[placeholder*='First name']", "input[name*='firstName']"],
                profile.get("first_name", ""))
    _fill_field(page, ["input[placeholder*='Last name']", "input[name*='lastName']"],
                profile.get("last_name", ""))
    _fill_field(page, ["input[type='email']", "input[placeholder*='Email']"],
                profile.get("email", ""))
    _fill_field(page, ["input[type='tel']", "input[placeholder*='Phone']"],
                profile.get("phone", ""))
    _fill_field(page, ["input[placeholder*='LinkedIn']"],
                profile.get("linkedin", ""))

    _upload_resume(page, resume_path)
    _human_delay(500, 1000)
    return True


# ── Indeed Apply (IndeedApply multi-step modal) ────────────────────────────────

def _submit_indeed(page, job: "Job", resume_path: str, profile: dict,
                   submission_cfg: dict, api_key: str = "") -> bool:
    """
    Indeed Apply — the multi-step 'Apply now' modal on indeed.com.
    Navigates through up to 10 steps (contact → resume → questions → review).
    """
    review_mode = submission_cfg.get("review_before_submit", True)
    logger.info(f"  [Indeed Apply] {job.url}")

    page.goto(job.url, timeout=30_000)
    page.wait_for_load_state("networkidle", timeout=20_000)
    _human_delay(1000, 2000)

    # Click the Apply / Apply now button
    try:
        apply_btn = page.wait_for_selector(
            'button[id*="apply"], button:has-text("Apply now"), '
            'a[href*="apply"]:visible, #indeedApplyButton',
            timeout=10_000,
        )
        if apply_btn and apply_btn.is_visible():
            apply_btn.click()
            _human_delay(800, 1500)
    except Exception as e:
        logger.warning(f"  Indeed Apply button not found: {e}")
        return _submit_generic(page, job, resume_path, profile)

    # Wait for modal or redirect
    try:
        page.wait_for_selector(
            "[id*='apply-modal'], [class*='ApplyModal'], iframe[id*='indeed'], "
            "form[id*='apply'], [data-tn-element='applyModal']",
            timeout=10_000,
        )
    except Exception:
        pass  # may have redirected directly to form

    upload_path = _to_pdf(resume_path)

    for step in range(12):
        _human_delay(500, 900)

        # Handle any file upload fields (resume)
        for fi in page.query_selector_all("input[type='file']"):
            try:
                fi.set_input_files(upload_path)
                _human_delay(500, 1000)
                break
            except Exception:
                continue

        # Fill visible text/number fields
        for inp in page.query_selector_all("input[type='text'], input[type='email'], input[type='tel'], input[type='number']"):
            try:
                if not inp.is_visible():
                    continue
                try:
                    if inp.input_value():
                        continue
                except Exception:
                    pass
                label = _get_label(page, inp)
                if label:
                    ans = _answer_question(label, "text", [], job, profile, api_key)
                    if ans:
                        inp.fill(ans)
                        _human_delay(150, 400)
            except Exception:
                continue

        # Fill textareas
        for ta in page.query_selector_all("textarea:visible"):
            try:
                try:
                    if ta.input_value():
                        continue
                except Exception:
                    pass
                label = _get_label(page, ta)
                if label:
                    ans = _answer_question(label, "textarea", [], job, profile, api_key)
                    if ans:
                        ta.fill(ans)
                        _human_delay(150, 400)
            except Exception:
                continue

        # Radio/fieldset questions
        for fs in page.query_selector_all("fieldset:visible"):
            try:
                legend = fs.query_selector("legend")
                if not legend:
                    continue
                question = legend.inner_text().strip()
                radios = fs.query_selector_all("input[type='radio']")
                if not radios or any(r.is_checked() for r in radios):
                    continue
                opts = []
                for r in radios:
                    rid = r.get_attribute("id")
                    if rid:
                        lbl = page.query_selector(f"label[for='{rid}']")
                        if lbl:
                            opts.append(lbl.inner_text().strip())
                answer = _answer_question(question, "radio", opts, job, profile, api_key)
                for r in radios:
                    rid = r.get_attribute("id")
                    if rid:
                        lbl = page.query_selector(f"label[for='{rid}']")
                        if lbl and answer.lower() in lbl.inner_text().lower():
                            lbl.click()
                            _human_delay(200, 400)
                            break
            except Exception:
                continue

        _human_delay(400, 700)

        # Submit button
        submit_btn = page.query_selector(
            'button[type="submit"]:has-text("Submit"), '
            'button:has-text("Submit my application"), '
            'button[aria-label*="Submit"]'
        )
        if submit_btn and submit_btn.is_visible():
            if review_mode:
                logger.info("  Indeed form filled — browser open for review.")
                try:
                    input("  >> Press Enter to submit, or Ctrl+C to cancel: ")
                    submit_btn.click()
                    page.wait_for_load_state("networkidle", timeout=15_000)
                    return True
                except KeyboardInterrupt:
                    return False
            else:
                submit_btn.click()
                page.wait_for_load_state("networkidle", timeout=15_000)
                return True

        # Continue / Next button
        next_found = False
        for sel in [
            'button:has-text("Continue")', 'button:has-text("Next")',
            'button[type="submit"]:not(:has-text("Submit"))',
        ]:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                next_found = True
                break
        if not next_found:
            logger.debug(f"  Indeed step {step}: no navigation button")
            break

    return False


# ── Glassdoor Apply ────────────────────────────────────────────────────────────

def _submit_glassdoor(page, job: "Job", resume_path: str, profile: dict) -> bool:
    logger.info(f"  [Glassdoor] {job.url}")
    page.goto(job.url, timeout=30_000)
    page.wait_for_load_state("networkidle", timeout=20_000)
    _human_delay(800, 1500)

    # Glassdoor shows job detail — click Easy Apply or Apply
    try:
        btn = page.query_selector(
            'button[data-test="easyApply"], button:has-text("Easy Apply"), '
            'button:has-text("Apply"), a:has-text("Apply")'
        )
        if btn and btn.is_visible():
            btn.click()
            page.wait_for_load_state("networkidle", timeout=15_000)
            _human_delay(500, 1000)
    except Exception:
        pass

    # Glassdoor's apply form (may redirect to company ATS)
    _fill_field(page, ["input[name='firstName']", "input[placeholder*='First']"],
                profile.get("first_name", ""))
    _fill_field(page, ["input[name='lastName']", "input[placeholder*='Last']"],
                profile.get("last_name", ""))
    _fill_field(page, ["input[type='email']"], profile.get("email", ""))
    _fill_field(page, ["input[type='tel']"], profile.get("phone", ""))

    _upload_resume(page, resume_path)
    _human_delay(500, 1200)
    return True


# ── Monster ────────────────────────────────────────────────────────────────────

def _submit_monster(page, job: "Job", resume_path: str, profile: dict) -> bool:
    logger.info(f"  [Monster] {job.url}")
    page.goto(job.url, timeout=30_000)
    page.wait_for_load_state("networkidle", timeout=20_000)
    _human_delay(800, 1500)

    try:
        btn = page.query_selector(
            'button[data-testid="apply-button"], '
            'a[data-testid="apply-button"], '
            'button:has-text("Apply"), a:has-text("Apply Now")'
        )
        if btn and btn.is_visible():
            btn.click()
            page.wait_for_load_state("networkidle", timeout=15_000)
            _human_delay(500, 1000)
    except Exception:
        pass

    _fill_field(page, ["input[name='firstName']", "input[id='fname']"],
                profile.get("first_name", ""))
    _fill_field(page, ["input[name='lastName']", "input[id='lname']"],
                profile.get("last_name", ""))
    _fill_field(page, ["input[type='email']", "input[id='email']"],
                profile.get("email", ""))
    _fill_field(page, ["input[type='tel']", "input[id='phone']"],
                profile.get("phone", ""))

    _upload_resume(page, resume_path)
    _human_delay(500, 1200)
    return True


# ── Wellfound inline apply ─────────────────────────────────────────────────────

def _submit_wellfound(page, job: "Job", resume_path: str, profile: dict,
                      submission_cfg: dict, api_key: str = "") -> bool:
    """
    Wellfound has a sidebar / modal apply form on the job listing page.
    """
    review_mode = submission_cfg.get("review_before_submit", True)
    logger.info(f"  [Wellfound] {job.url}")

    page.goto(job.url, timeout=30_000)
    page.wait_for_load_state("networkidle", timeout=20_000)
    _human_delay(800, 1500)

    # Click Apply button
    try:
        btn = page.wait_for_selector(
            'button:has-text("Apply"), a:has-text("Apply")', timeout=8_000
        )
        if btn and btn.is_visible():
            btn.click()
            _human_delay(800, 1500)
    except Exception as e:
        logger.warning(f"  Wellfound Apply button not found: {e}")
        return _submit_generic(page, job, resume_path, profile)

    upload_path = _to_pdf(resume_path)

    # Upload resume
    for fi in page.query_selector_all("input[type='file']"):
        try:
            fi.set_input_files(upload_path)
            _human_delay(600, 1200)
            break
        except Exception:
            continue

    # Fill standard fields
    _fill_field(page, ["input[placeholder*='email']", "input[type='email']"],
                profile.get("email", ""))
    _fill_field(page, ["input[placeholder*='First']", "input[name*='first']"],
                profile.get("first_name", ""))
    _fill_field(page, ["input[placeholder*='Last']", "input[name*='last']"],
                profile.get("last_name", ""))
    _fill_field(page, ["input[placeholder*='LinkedIn']"],
                profile.get("linkedin", ""))
    _fill_field(page, ["input[placeholder*='GitHub']"],
                profile.get("github", ""))

    # Answer additional questions using yaml + claude
    for ta in page.query_selector_all("textarea:visible"):
        try:
            label = _get_label(page, ta)
            if label:
                ans = _answer_question(label, "textarea", [], job, profile, api_key)
                if ans:
                    ta.fill(ans)
                    _human_delay(200, 400)
        except Exception:
            continue

    _human_delay(500, 800)

    if review_mode:
        logger.info("  Wellfound form filled — browser open for review.")
        try:
            input("  >> Press Enter to submit, or Ctrl+C to cancel: ")
        except KeyboardInterrupt:
            return False

    return True


# ── Generic fallback ───────────────────────────────────────────────────────────

def _submit_generic(page, job: "Job", resume_path: str, profile: dict) -> bool:
    logger.info(f"  [Generic] {job.url}")
    page.goto(job.url, timeout=30_000)
    page.wait_for_load_state("networkidle", timeout=20_000)
    _human_delay()

    _fill_field(page, ["input[type='email']", "input[name*='email']", "input[id*='email']"],
                profile.get("email", ""))
    _fill_field(page, ["input[name*='first']", "input[id*='first']", "input[placeholder*='First']"],
                profile.get("first_name", ""))
    _fill_field(page, ["input[name*='last']", "input[id*='last']", "input[placeholder*='Last']"],
                profile.get("last_name", ""))
    _fill_field(page, ["input[type='tel']", "input[name*='phone']", "input[id*='phone']"],
                profile.get("phone", ""))

    _upload_resume(page, resume_path)
    _human_delay(500, 1000)
    return True


# ── Work authorisation helper ──────────────────────────────────────────────────

def _fill_work_auth(page, profile: dict) -> None:
    requires_sponsorship = profile.get("requires_sponsorship", True)

    try:
        yes_options = page.query_selector_all(
            "input[type='radio'][value*='yes'], input[type='radio'][value*='Yes'], "
            "input[type='radio'][value*='authorized'], input[type='radio'][value*='1']"
        )
        for opt in yes_options[:1]:
            label = page.query_selector(f"label[for='{opt.get_attribute('id')}']")
            label_text = label.inner_text().lower() if label else ""
            if any(kw in label_text for kw in ("authorized", "eligible", "yes")):
                opt.click()
                break
    except Exception:
        pass

    if requires_sponsorship:
        try:
            for opt in page.query_selector_all("input[type='radio'][value*='yes']"):
                label = page.query_selector(f"label[for='{opt.get_attribute('id')}']")
                label_text = label.inner_text().lower() if label else ""
                if "sponsor" in label_text:
                    opt.click()
                    break
        except Exception:
            pass


# ── Screenshot on failure ──────────────────────────────────────────────────────

def _save_screenshot(page, job: "Job", output_folder: str) -> None:
    try:
        safe = re.sub(r"[^\w]", "_", f"{job.company}_{job.title}")[:50]
        path = Path(output_folder) / f"screenshot_{safe}.png"
        page.screenshot(path=str(path), full_page=True)
        logger.info(f"  Screenshot saved: {path.name}")
    except Exception:
        pass


# ── Public API ─────────────────────────────────────────────────────────────────

def submit_application(
    job: "Job",
    resume_path: str,
    profile_cfg: dict,
    submission_cfg: dict,
    tracker_path: str = "",
    api_key: str = "",
) -> bool:
    """
    Submit an application for `job` using the appropriate ATS automation.

    Args:
        job:            Job dataclass (from scraper.py)
        resume_path:    Path to the tailored .docx resume (auto-converted to PDF)
        profile_cfg:    From config.yaml → submission.profile
        submission_cfg: From config.yaml → submission
        tracker_path:   Path to tracker.xlsx for status updates
        api_key:        Anthropic API key for screening question answering

    Returns True if the application was submitted (or form was filled in review mode).
    """
    if not resume_path or not Path(resume_path).exists():
        logger.error(f"  Resume not found: {resume_path}")
        return False

    ats = detect_ats(job.url)
    logger.info(f"  Submitting [{ats.upper()}] {job.title} @ {job.company}")

    headless = submission_cfg.get("headless", False)
    review_mode = submission_cfg.get("review_before_submit", True)
    output_folder = submission_cfg.get("screenshots_folder", "output/screenshots")
    Path(output_folder).mkdir(parents=True, exist_ok=True)

    pw = None
    browser = None
    try:
        pw, browser = _get_browser(headless=headless)
        context = browser.new_context(
            accept_downloads=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        success = False

        # ATS handlers that manage their own review/submit flow internally
        _self_submitting = {"linkedin", "indeed", "wellfound"}

        if ats == "linkedin":
            success = _submit_linkedin(page, job, resume_path, profile_cfg, submission_cfg, api_key)
        elif ats == "indeed":
            success = _submit_indeed(page, job, resume_path, profile_cfg, submission_cfg, api_key)
        elif ats == "wellfound":
            success = _submit_wellfound(page, job, resume_path, profile_cfg, submission_cfg, api_key)
        elif ats == "greenhouse":
            success = _submit_greenhouse(page, job, resume_path, profile_cfg)
        elif ats == "lever":
            success = _submit_lever(page, job, resume_path, profile_cfg)
        elif ats == "workday":
            success = _submit_workday(page, job, resume_path, profile_cfg)
        elif ats == "ashby":
            success = _submit_ashby(page, job, resume_path, profile_cfg)
        elif ats == "smartrecruiters":
            success = _submit_smartrecruiters(page, job, resume_path, profile_cfg)
        elif ats == "icims":
            success = _submit_icims(page, job, resume_path, profile_cfg)
        elif ats == "jobvite":
            success = _submit_jobvite(page, job, resume_path, profile_cfg)
        elif ats == "bamboohr":
            success = _submit_bamboohr(page, job, resume_path, profile_cfg)
        elif ats == "taleo":
            success = _submit_taleo(page, job, resume_path, profile_cfg)
        elif ats == "rippling":
            success = _submit_rippling(page, job, resume_path, profile_cfg)
        elif ats == "glassdoor":
            success = _submit_glassdoor(page, job, resume_path, profile_cfg)
        elif ats == "monster":
            success = _submit_monster(page, job, resume_path, profile_cfg)
        else:
            success = _submit_generic(page, job, resume_path, profile_cfg)

        if not success:
            _save_screenshot(page, job, output_folder)
            return False

        # Self-submitting handlers already handled review + tracker update internally
        if ats in _self_submitting:
            if success and tracker_path:
                update_status(tracker_path, job.id, "Applied")
            return success

        # For form-fill-only ATS: show browser for review or auto-click submit
        if ats not in _self_submitting:
            if review_mode:
                logger.info("  Form filled — browser open for review. Press Enter to submit.")
                try:
                    input("  >> Press Enter to submit, or Ctrl+C to skip: ")
                    submit_btn = page.query_selector(
                        "button[type='submit'], input[type='submit'], "
                        "button:has-text('Submit'), button:has-text('Apply')"
                    )
                    if submit_btn and submit_btn.is_visible():
                        submit_btn.click()
                        page.wait_for_load_state("networkidle", timeout=15_000)
                        logger.info(f"  Submitted: {job.title} @ {job.company}")
                        if tracker_path:
                            update_status(tracker_path, job.id, "Applied")
                        return True
                    else:
                        logger.warning("  Submit button not found — please submit manually.")
                        input("  >> Press Enter when done: ")
                        if tracker_path:
                            update_status(tracker_path, job.id, "Applied")
                        return True
                except KeyboardInterrupt:
                    logger.info("  Application cancelled.")
                    return False
            else:
                _human_delay(800, 1500)
                submit_btn = page.query_selector(
                    "button[type='submit'], input[type='submit'], "
                    "button:has-text('Submit'), button:has-text('Apply')"
                )
                if submit_btn and submit_btn.is_visible():
                    submit_btn.click()
                    page.wait_for_load_state("networkidle", timeout=15_000)
                    logger.info(f"  Auto-submitted: {job.title} @ {job.company}")
                    if tracker_path:
                        update_status(tracker_path, job.id, "Applied")
                    return True
                else:
                    logger.warning("  Could not locate submit button for auto-submit.")
                    _save_screenshot(page, job, output_folder)
                    return False
        return success  # should not be reached

    except RuntimeError as e:
        logger.error(str(e))
        return False
    except Exception as e:
        logger.error(f"  Submission error for {job.company}/{job.title}: {e}")
        if browser:
            try:
                p = browser.contexts[0].pages[0] if browser.contexts else None
                if p:
                    _save_screenshot(p, job, output_folder)
            except Exception:
                pass
        return False
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        if pw:
            try:
                pw.stop()
            except Exception:
                pass
