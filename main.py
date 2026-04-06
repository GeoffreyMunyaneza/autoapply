"""
main.py — AutoApply Phase 1 orchestrator.

Runs in the background, scraping jobs on a schedule, tailoring resumes,
and tracking everything in an Excel spreadsheet.

Usage:
  python main.py              # run once immediately, then on schedule
  python main.py --once       # run once and exit (good for testing)
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

import schedule
import yaml
from dotenv import load_dotenv

from scraper import scrape_jobs
from matcher import score_job, passes_filter, select_resume_type
from tailor import tailor_resume
from tracker import load_seen_ids, add_job

# ── Logging setup ──────────────────────────────────────────────────────────────
log_dir = Path("output")
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("output/autoapply.log", encoding="utf-8"),
    ],
)
# Fix Windows console encoding so non-ASCII chars don't crash the logger
if hasattr(logging.getLogger().handlers[0], 'stream'):
    import io
    logging.getLogger().handlers[0].stream = io.TextIOWrapper(
        sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True
    )
logger = logging.getLogger(__name__)


# ── Config loading ─────────────────────────────────────────────────────────────
def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Core pipeline ──────────────────────────────────────────────────────────────
def run_pipeline(config: dict, api_key: str) -> None:
    logger.info("=" * 60)
    logger.info("AutoApply pipeline starting...")

    search_cfg = config["search"]
    filter_cfg = config["filter"]
    output_cfg = config["output"]
    resumes_cfg = config["resumes"]
    claude_cfg = config.get("claude", {})

    tracker_path = output_cfg["tracker_file"]
    resumes_folder = output_cfg["resumes_folder"]

    # Load jobs we've already seen so we don't duplicate
    seen_ids = load_seen_ids(tracker_path)
    logger.info(f"Tracker has {len(seen_ids)} existing jobs.")

    new_count = 0
    total_scraped = 0

    for query_cfg in search_cfg["queries"]:
        query = query_cfg["query"]
        configured_resume_type = query_cfg.get("resume_type", "ml")

        logger.info(f"Searching: '{query}'")

        jobs = scrape_jobs(
            query=query,
            location=search_cfg.get("location", "United States"),
            results=search_cfg.get("results_per_query", 20),
            hours_old=search_cfg.get("hours_old", 48),
            remote_only=search_cfg.get("remote_only", True),
        )

        total_scraped += len(jobs)

        for job in jobs:
            # Skip if already tracked
            if job.id in seen_ids:
                continue

            # Determine resume type from job title (may override config)
            resume_type = select_resume_type(job, configured_resume_type)
            job.resume_type = resume_type

            # Filter
            ok, reason = passes_filter(
                job,
                exclude_keywords=filter_cfg.get("exclude_keywords", []),
                min_desc_length=filter_cfg.get("min_description_length", 300),
            )
            if not ok:
                logger.debug(f"  Skipped '{job.title}' @ {job.company}: {reason}")
                seen_ids.add(job.id)  # don't re-evaluate
                continue

            # Score
            score = score_job(job, resume_type)
            if score < 0.1:
                logger.debug(f"  Low score ({score:.0%}) for '{job.title}' @ {job.company}")
                seen_ids.add(job.id)
                continue

            logger.info(f"  >> New match [{score:.0%}] '{job.title}' @ {job.company} ({resume_type.upper()} resume)")

            # Tailor resume
            resume_path = ""
            if api_key:
                resume_path = tailor_resume(
                    job=job,
                    resume_type=resume_type,
                    resumes_config=resumes_cfg,
                    output_folder=resumes_folder,
                    claude_config=claude_cfg,
                    api_key=api_key,
                ) or ""
            else:
                logger.warning("  No ANTHROPIC_API_KEY — skipping resume tailoring")

            # Add to tracker
            add_job(
                tracker_path=tracker_path,
                job=job,
                match_score=score,
                resume_type=resume_type,
                resume_path=resume_path,
                status="Discovered",
            )

            seen_ids.add(job.id)
            new_count += 1

    logger.info(f"Pipeline complete: {total_scraped} scraped, {new_count} new jobs added.")
    logger.info(f"Tracker: {tracker_path}")
    if new_count > 0:
        logger.info(f"Resumes: {resumes_folder}/")
    logger.info("=" * 60)


# ── Entry point ────────────────────────────────────────────────────────────────
def main():
    load_dotenv()  # loads .env file if present

    parser = argparse.ArgumentParser(description="AutoApply Phase 1")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning(
            "ANTHROPIC_API_KEY not found. Resume tailoring will be skipped.\n"
            "Add it to .env file: ANTHROPIC_API_KEY=sk-ant-..."
        )

    interval_hours = config.get("schedule", {}).get("interval_hours", 2)

    # Run immediately on start
    run_pipeline(config, api_key)

    if args.once:
        return

    # Schedule recurring runs
    logger.info(f"Scheduling next run every {interval_hours} hour(s). Press Ctrl+C to stop.")
    schedule.every(interval_hours).hours.do(run_pipeline, config=config, api_key=api_key)

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("AutoApply stopped.")


if __name__ == "__main__":
    main()
