"""
scraper.py — Fetches job listings from multiple sources using python-jobspy.
Supported: linkedin, indeed, zip_recruiter, glassdoor, google
"""

import logging
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class Job:
    id: str
    title: str
    company: str
    location: str
    description: str
    url: str
    source: str
    salary: str = ""
    date_posted: str = ""
    resume_type: str = "ml"  # "ml" or "pm"


def scrape_jobs(
    query: str,
    location: str,
    results: int,
    hours_old: int,
    remote_only: bool,
    sources: list[str] | None = None,
) -> list[Job]:
    """
    Scrape multiple job boards for jobs matching the query.
    sources: list of site names — linkedin, indeed, zip_recruiter, glassdoor, google
    """
    try:
        from jobspy import scrape_jobs as _scrape
    except ImportError:
        logger.error("python-jobspy not installed. Run: pip install python-jobspy --no-deps")
        return []

    if sources is None:
        sources = ["linkedin", "indeed"]

    # Scrape each source separately so one failure doesn't block others
    all_dfs = []
    for source in sources:
        try:
            df = _scrape(
                site_name=[source],
                search_term=query,
                location=location,
                results_wanted=results,
                hours_old=hours_old,
                country_indeed="USA",
                linkedin_fetch_description=True,
                is_remote=remote_only,
                verbose=0,
            )
            if df is not None and not df.empty:
                all_dfs.append(df)
                logger.debug(f"    [{source}] {len(df)} results")
        except Exception as e:
            logger.warning(f"  [{source}] scrape failed for '{query}': {e}")
            continue

    if not all_dfs:
        return []

    import pandas as pd
    df = pd.concat(all_dfs, ignore_index=True)

    if df is None or df.empty:
        return []

    jobs: list[Job] = []
    for _, row in df.iterrows():
        description = str(row.get("description") or "")
        if not description or description == "nan":
            description = ""

        salary_parts = []
        min_sal = row.get("min_amount")
        max_sal = row.get("max_amount")
        currency = row.get("currency") or ""
        interval = row.get("interval") or ""
        if min_sal and str(min_sal) != "nan":
            salary_parts.append(f"{currency}{int(float(min_sal)):,}")
        if max_sal and str(max_sal) != "nan":
            salary_parts.append(f"{currency}{int(float(max_sal)):,}")
        salary = " - ".join(salary_parts)
        if salary and interval and str(interval) != "nan":
            salary += f" / {interval}"

        date_posted = str(row.get("date_posted") or "")
        if date_posted == "nan":
            date_posted = ""

        job_url = str(row.get("job_url") or "")
        if job_url == "nan":
            job_url = ""

        source = str(row.get("site") or "unknown")

        # Build a stable ID from company + title + source
        company = str(row.get("company") or "Unknown")
        title = str(row.get("title") or "Unknown")
        location_str = str(row.get("location") or "")
        job_id = f"{source}_{company}_{title}".lower().replace(" ", "_")[:80]

        jobs.append(Job(
            id=job_id,
            title=title,
            company=company,
            location=location_str,
            description=description,
            url=job_url,
            source=source,
            salary=salary,
            date_posted=date_posted,
        ))

    logger.info(f"  Scraped {len(jobs)} jobs for '{query}'")
    return jobs
