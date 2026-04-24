"""
services/pipeline.py — Full pipeline orchestration.

Extracted from main.py; all business logic lives here.
Called by: main.py (CLI), gui/runner.py (GUI background thread),
           app.py (desktop app manual runs).

Public API:
    run_pipeline(config, api_key) -> int          # returns new jobs added
    run_submission_pass(config, api_key) -> int   # returns submitted count
"""

import logging
from pathlib import Path

from core.scraper import scrape_jobs
from core.matcher import score_job, passes_filter, select_resume_type
from core.tailor import tailor_resume
from core.tracker import load_seen_ids, add_job, COLUMNS
from core.notifier import notify_new_jobs, notify_pipeline_complete
from services.config import prepare_config

logger = logging.getLogger(__name__)


def _is_pending_resume(resume_path: str, pending_folder: str) -> bool:
    """Return True when the tailored resume was routed to the pending-review folder."""
    if not resume_path or not pending_folder:
        return False
    try:
        return Path(resume_path).resolve().is_relative_to(Path(pending_folder).resolve())
    except Exception:
        return False


def run_pipeline(config: dict, api_key: str) -> int:
    """
    Full discovery pipeline: scrape → filter → score → tailor → track → notify.
    Returns the number of new jobs added to the tracker.
    """
    config = prepare_config(config)

    logger.info("=" * 60)
    logger.info("AutoApply pipeline starting...")

    search_cfg   = config["search"]
    filter_cfg   = config["filter"]
    output_cfg   = config["output"]
    resumes_cfg  = config["resumes"]
    claude_cfg   = config.get("claude", {})
    notif_cfg    = config.get("notifications", {})
    cover_cfg    = config.get("cover_letter", {})
    review_cfg   = config.get("review", {})
    user_profile = config.get("user_profile", {})

    tracker_path   = output_cfg["tracker_file"]
    resumes_folder = output_cfg["resumes_folder"]
    pending_folder = output_cfg.get("pending_folder", "")
    gen_cover      = cover_cfg.get("auto_generate", False)
    auto_approve   = review_cfg.get("auto_approve", True)

    seen_ids = load_seen_ids(tracker_path)
    logger.info(f"Tracker has {len(seen_ids)} existing jobs.")

    new_jobs:  list = []
    new_count     = 0
    total_scraped = 0

    sources = search_cfg.get("sources", ["linkedin", "indeed"])

    for query_cfg in search_cfg["queries"]:
        query           = query_cfg["query"]
        resume_type_cfg = query_cfg.get("resume_type", "ml")

        logger.info(f"Searching: '{query}' across {len(sources)} source(s)")

        jobs = scrape_jobs(
            query=query,
            location=search_cfg.get("location", "United States"),
            results=search_cfg.get("results_per_query", 15),
            hours_old=search_cfg.get("hours_old", 24),
            remote_only=search_cfg.get("remote_only", False),
            sources=sources,
            job_type=search_cfg.get("job_type"),
            distance=search_cfg.get("distance_miles", 50),
            easy_apply_only=search_cfg.get("easy_apply_only", False),
            proxies=search_cfg.get("proxies") or None,
        )

        total_scraped += len(jobs)

        for job in jobs:
            if job.id in seen_ids:
                continue

            resume_type = select_resume_type(job, resume_type_cfg)
            job.resume_type = resume_type

            ok, reason = passes_filter(
                job,
                exclude_keywords=filter_cfg.get("exclude_keywords", []),
                min_desc_length=filter_cfg.get("min_description_length", 300),
            )
            if not ok:
                logger.debug(f"  Skipped '{job.title}' @ {job.company}: {reason}")
                seen_ids.add(job.id)
                continue

            score = score_job(job, resume_type, user_profile)
            if score < 0.1:
                logger.debug(f"  Low score ({score:.0%}) '{job.title}' @ {job.company}")
                seen_ids.add(job.id)
                continue

            logger.info(
                f"  >> [{score:.0%}] '{job.title}' @ {job.company} ({resume_type.upper()})"
            )

            resume_path  = ""
            cover_letter = ""

            if api_key:
                resume_path, cover_letter = tailor_resume(
                    job=job,
                    resume_type=resume_type,
                    resumes_config=resumes_cfg,
                    output_folder=resumes_folder,
                    claude_config=claude_cfg,
                    api_key=api_key,
                    auto_approve=auto_approve,
                    generate_cover=gen_cover,
                    pending_folder=pending_folder,
                    user_profile=user_profile,
                )
                resume_path = resume_path or ""
            else:
                logger.warning("  No ANTHROPIC_API_KEY — skipping resume tailoring")

            if cover_letter and resume_path:
                try:
                    cl_path = Path(resume_path).with_suffix(".cover_letter.txt")
                    cl_path.write_text(cover_letter, encoding="utf-8")
                    logger.info(f"  Cover letter saved: {cl_path.name}")
                except Exception as e:
                    logger.debug(f"  Could not save cover letter: {e}")

            status = "Pending Review" if _is_pending_resume(resume_path, pending_folder) else "Queued"

            add_job(
                tracker_path=tracker_path,
                job=job,
                match_score=score,
                resume_type=resume_type,
                resume_path=resume_path,
                status=status,
                notes=cover_letter[:300] if cover_letter else "",
            )

            seen_ids.add(job.id)
            new_count += 1
            job.match_score = score
            new_jobs.append(job)

    logger.info(f"Pipeline complete: {total_scraped} scraped, {new_count} new jobs added.")
    if new_count > 0:
        logger.info(f"Resumes saved to: {resumes_folder}/")
    logger.info(f"Tracker: {tracker_path}")
    logger.info("=" * 60)

    if new_jobs:
        notify_new_jobs(new_jobs, notif_cfg)
    notify_pipeline_complete(new_count, total_scraped, notif_cfg)

    return new_count


def run_submission_pass(config: dict, api_key: str = "") -> int:
    """
    Submit all Queued jobs in the tracker.
    Returns the number of jobs successfully submitted.
    """
    config = prepare_config(config)

    submission_cfg = config.get("submission", {})
    if not submission_cfg.get("enabled"):
        logger.info("Submission disabled (submission.enabled=false). Skipping.")
        return 0

    try:
        from core.submitter import submit_application, _load_yaml_answers
        import openpyxl
    except ImportError as e:
        logger.error(f"Submission requires Playwright: {e}")
        return 0

    output_cfg   = config["output"]
    tracker_path = output_cfg["tracker_file"]
    profile_cfg  = submission_cfg.get("profile", {})
    questions_file = config.get("screening", {}).get("questions_file", "questions.yaml")

    try:
        _load_yaml_answers(questions_file)
    except Exception as exc:
        logger.debug(f"Could not preload screening answers from {questions_file}: {exc}")

    if not Path(tracker_path).exists():
        logger.info("Tracker not found — nothing to submit.")
        return 0

    wb = openpyxl.load_workbook(tracker_path)
    ws = wb.active
    status_col  = COLUMNS.index("Status") + 1
    resume_col  = COLUMNS.index("Resume Path") + 1
    url_col     = COLUMNS.index("URL") + 1
    title_col   = COLUMNS.index("Title") + 1
    company_col = COLUMNS.index("Company") + 1
    id_col      = COLUMNS.index("ID") + 1

    from core.scraper import Job

    queued = [row for row in ws.iter_rows(min_row=2, values_only=True)
              if str(row[status_col - 1] or "").strip() == "Queued"]

    if not queued:
        logger.info("No Queued applications to submit.")
        return 0

    logger.info(f"Found {len(queued)} Queued application(s) to submit.")
    submitted = 0
    for row in queued:
        resume_path = str(row[resume_col - 1] or "")

        cover_letter_text = profile_cfg.get("cover_letter_text", "")
        if resume_path:
            cl_path = Path(resume_path).with_suffix(".cover_letter.txt")
            if cl_path.exists():
                try:
                    cover_letter_text = cl_path.read_text(encoding="utf-8")
                except Exception:
                    pass

        job_profile = dict(profile_cfg)
        if cover_letter_text:
            job_profile["cover_letter_text"] = cover_letter_text

        job = Job(
            id=str(row[id_col - 1] or ""),
            title=str(row[title_col - 1] or ""),
            company=str(row[company_col - 1] or ""),
            location="",
            description="",
            url=str(row[url_col - 1] or ""),
            source="",
        )
        success = submit_application(
            job=job,
            resume_path=resume_path,
            profile_cfg=job_profile,
            submission_cfg=submission_cfg,
            tracker_path=tracker_path,
            api_key=api_key,
        )
        if success:
            submitted += 1

    logger.info(f"Submission pass complete: {submitted}/{len(queued)} submitted.")
    return submitted
