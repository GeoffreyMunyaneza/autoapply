"""
scraper.py — Fetches job listings from multiple sources.

Built-in via python-jobspy (single call per source):
  linkedin, indeed, zip_recruiter, glassdoor, google, bayt, naukri, bdjobs

Custom scrapers (Playwright / public APIs):
  wellfound   — wellfound.com (startup / ML roles, formerly AngelList)
  dice        — dice.com JSON API (tech-focused board)
  remoteok    — remoteok.com public API (remote-only roles)

All sources return a flat list of Job objects with a consistent schema.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ── Job dataclass ──────────────────────────────────────────────────────────────

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
    resume_type: str = "ml"   # "ml" or "pm", set by matcher
    match_score: float = 0.0  # set by matcher


# ── Source routing ─────────────────────────────────────────────────────────────

# Sources handled natively by python-jobspy
_JOBSPY_SOURCES = {"linkedin", "indeed", "zip_recruiter", "glassdoor", "google",
                   "bayt", "naukri", "bdjobs"}

# Sources with custom scrapers in this file
_CUSTOM_SOURCES = {"wellfound", "dice", "remoteok"}


def scrape_jobs(
    query: str,
    location: str,
    results: int,
    hours_old: int,
    remote_only: bool,
    sources: list[str] | None = None,
    job_type: str | None = None,          # fulltime, parttime, internship, contract
    distance: int = 50,                   # radius in miles (jobspy only)
    easy_apply_only: bool = False,        # only easy-apply jobs where supported
    proxies: list[str] | None = None,     # ["http://user:pass@host:port", ...]
) -> list[Job]:
    """
    Scrape multiple job boards for jobs matching the query.

    sources: any mix of jobspy sources + custom sources.
             Falls back to ["linkedin", "indeed"] if not specified.
    """
    if sources is None:
        sources = ["linkedin", "indeed"]

    jobspy_srcs = [s for s in sources if s in _JOBSPY_SOURCES]
    custom_srcs  = [s for s in sources if s in _CUSTOM_SOURCES]
    unknown_srcs = [s for s in sources if s not in _JOBSPY_SOURCES and s not in _CUSTOM_SOURCES]
    if unknown_srcs:
        logger.warning(f"Unknown sources (ignored): {unknown_srcs}")

    all_jobs: list[Job] = []

    # ── python-jobspy sources ──────────────────────────────────────────────────
    if jobspy_srcs:
        all_jobs.extend(
            _scrape_jobspy(
                query=query,
                location=location,
                results=results,
                hours_old=hours_old,
                remote_only=remote_only,
                sources=jobspy_srcs,
                job_type=job_type,
                distance=distance,
                easy_apply_only=easy_apply_only,
                proxies=proxies,
            )
        )

    # ── Custom scrapers ────────────────────────────────────────────────────────
    for src in custom_srcs:
        try:
            if src == "wellfound":
                all_jobs.extend(_scrape_wellfound(query, location, results, remote_only))
            elif src == "dice":
                all_jobs.extend(_scrape_dice(query, location, results, hours_old, job_type))
            elif src == "remoteok":
                all_jobs.extend(_scrape_remoteok(query, results))
        except Exception as e:
            logger.warning(f"  [{src}] custom scrape failed for '{query}': {e}")

    logger.info(f"  Total scraped for '{query}': {len(all_jobs)} jobs")
    return all_jobs


# ── python-jobspy wrapper ──────────────────────────────────────────────────────

def _scrape_jobspy(
    query: str,
    location: str,
    results: int,
    hours_old: int,
    remote_only: bool,
    sources: list[str],
    job_type: str | None,
    distance: int,
    easy_apply_only: bool,
    proxies: list[str] | None,
) -> list[Job]:
    try:
        from jobspy import scrape_jobs as _scrape
    except ImportError:
        logger.error("python-jobspy not installed. Run: pip install python-jobspy")
        return []

    import pandas as pd

    all_dfs = []
    for source in sources:
        try:
            # Glassdoor rejects broad locations like "United States" — omit it
            src_location = "" if source == "glassdoor" else location

            kwargs: dict = dict(
                site_name=[source],
                search_term=query,
                location=src_location,
                results_wanted=results,
                hours_old=hours_old,
                country_indeed="USA",
                linkedin_fetch_description=True,
                is_remote=remote_only,
                distance=distance,
                verbose=0,
            )
            if job_type:
                kwargs["job_type"] = job_type
            if easy_apply_only and source == "linkedin":
                kwargs["easy_apply"] = True
            if proxies:
                kwargs["proxies"] = proxies

            df = _scrape(**kwargs)
            if df is not None and not df.empty:
                all_dfs.append(df)
                logger.debug(f"    [{source}] {len(df)} results")
        except Exception as e:
            logger.warning(f"  [{source}] scrape failed for '{query}': {e}")
            continue

    if not all_dfs:
        return []

    df = pd.concat(all_dfs, ignore_index=True)
    if df is None or df.empty:
        return []

    return _df_to_jobs(df)


def _df_to_jobs(df) -> list[Job]:
    """Convert a jobspy DataFrame to a list of Job objects."""
    jobs: list[Job] = []
    for _, row in df.iterrows():
        description = str(row.get("description") or "")
        if description == "nan":
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
        company = str(row.get("company") or "Unknown")
        title = str(row.get("title") or "Unknown")
        location_str = str(row.get("location") or "")
        job_id = _make_id(source, company, title)

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
    return jobs


def _make_id(source: str, company: str, title: str) -> str:
    raw = f"{source}_{company}_{title}".lower()
    return re.sub(r"[^\w]", "_", raw)[:80]


# ── Wellfound (formerly AngelList) ────────────────────────────────────────────

def _scrape_wellfound(
    query: str,
    location: str,
    results: int,
    remote_only: bool,
) -> list[Job]:
    """
    Scrape Wellfound via their public GraphQL API (no login required).
    Falls back gracefully if the endpoint changes or blocks.
    """
    import requests

    # Wellfound's public job search endpoint (unauthenticated)
    remote_filter = "remote" if remote_only else ""
    api_url = "https://wellfound.com/graphql"
    query_gql = """
    query JobSearchResults($query: String!, $locationSlug: String, $remote: Boolean) {
      startups(filters: { jobQuery: $query, locationSlugs: [$locationSlug], remote: $remote }) {
        startupRoles(first: 20) {
          nodes {
            title
            slug
            applyUrl
            description
            jobType
            compensation
            remote
            startup {
              name
              locationName
            }
          }
        }
      }
    }
    """
    try:
        resp = requests.post(
            api_url,
            json={
                "query": query_gql,
                "variables": {
                    "query": query,
                    "remote": remote_only if remote_only else None,
                },
            },
            headers={
                "User-Agent": "Mozilla/5.0",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            raise ValueError(f"HTTP {resp.status_code}")

        data = resp.json()
        nodes = (
            data.get("data", {})
            .get("startups", {})
            .get("startupRoles", {})
            .get("nodes", [])
        ) or []

        jobs: list[Job] = []
        for node in nodes[:results]:
            title   = node.get("title", "")
            startup = node.get("startup") or {}
            company = startup.get("name", "Unknown")
            loc     = startup.get("locationName") or ("Remote" if node.get("remote") else location)
            slug    = node.get("slug", "")
            url     = node.get("applyUrl") or (f"https://wellfound.com/jobs/{slug}" if slug else "")
            desc    = node.get("description") or ""
            salary  = node.get("compensation") or ""

            if not title or not url:
                continue

            jobs.append(Job(
                id=_make_id("wellfound", company, title),
                title=title,
                company=company,
                location=loc,
                description=desc[:5000],
                url=url,
                source="wellfound",
                salary=salary,
                date_posted="",
            ))

        logger.info(f"  [wellfound] {len(jobs)} jobs for '{query}'")
        return jobs

    except Exception as e:
        logger.debug(f"  [wellfound] skipped: {e}")
        return []


# ── Dice ──────────────────────────────────────────────────────────────────────

def _scrape_dice(
    query: str,
    location: str,
    results: int,
    hours_old: int,
    job_type: str | None,
) -> list[Job]:
    """
    Scrape Dice.com using their public JSON search API.
    No auth required. Returns up to `results` Job objects.
    """
    import requests

    # Map our job_type values to Dice equivalents
    employment_map = {
        "fulltime": "FULLTIME",
        "parttime": "PARTTIME",
        "contract": "CONTRACTS",
        "internship": "INTERN",
    }
    emp_type = employment_map.get((job_type or "").lower(), "FULLTIME")

    # Map hours_old to Dice's postedDate filter
    if hours_old <= 1:
        posted = "ONE"
    elif hours_old <= 24:
        posted = "ONE"
    elif hours_old <= 72:
        posted = "THREE"
    elif hours_old <= 168:
        posted = "SEVEN"
    else:
        posted = "THIRTY"

    page_size = min(results, 50)
    jobs: list[Job] = []

    try:
        # Dice public search endpoint (no API key required)
        api_url = "https://job-search-api.svc.dhigroupinc.com/v1/dice/jobs/search"
        params: dict = {
            "q": query,
            "countryCode": "US",
            "radius": "50",
            "radiusUnit": "mi",
            "page": 1,
            "pageSize": page_size,
            "language": "en",
            "postedDate": posted,
            "employmentType": emp_type,
            "iadPref": "none",
        }
        if location and location.lower() not in ("united states", "us", "usa"):
            params["location"] = location

        resp = requests.get(
            api_url,
            params=params,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Origin": "https://www.dice.com",
                "Referer": "https://www.dice.com/",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        for item in data.get("data", [])[:results]:
            title = item.get("title", "")
            company = item.get("organizationName") or item.get("hiringOrganization", {}).get("name", "Unknown")
            job_url = item.get("applyUrl") or item.get("url", "")
            location_str = item.get("location", location)
            salary_str = ""
            salary_info = item.get("salary")
            if salary_info:
                salary_str = str(salary_info)
            posted_date = str(item.get("postedDate", ""))[:10]
            description = item.get("jobDescription", "")

            if not title or not job_url:
                continue

            jobs.append(Job(
                id=_make_id("dice", company, title),
                title=title,
                company=company,
                location=location_str,
                description=description[:5000] if description else "",
                url=job_url,
                source="dice",
                salary=salary_str,
                date_posted=posted_date,
            ))
    except Exception as e:
        logger.warning(f"  [dice] API error: {e}")

    logger.info(f"  [dice] {len(jobs)} jobs for '{query}'")
    return jobs


# ── RemoteOK ──────────────────────────────────────────────────────────────────

# RemoteOK uses short tag slugs — map common queries to their closest tag
_REMOTEOK_TAG_MAP: dict[str, str] = {
    "machine learning engineer":       "machine-learning",
    "ml engineer llm":                 "machine-learning",
    "ai engineer":                     "ai",
    "data scientist":                  "data-science",
    "applied scientist":               "machine-learning",
    "software engineer":               "software-dev",
    "backend engineer":                "backend",
    "frontend engineer":               "frontend",
    "technical product manager ai":    "product",
    "product manager machine learning":"product",
    "devops engineer":                 "devops",
    "nlp engineer":                    "nlp",
    "llm engineer":                    "machine-learning",
}


def _remoteok_tag(query: str) -> str:
    """Convert a free-text query to the best RemoteOK tag slug."""
    q = query.lower().strip()
    if q in _REMOTEOK_TAG_MAP:
        return _REMOTEOK_TAG_MAP[q]
    # fallback: first two words joined by hyphen
    words = q.split()[:2]
    return "-".join(words)


def _scrape_remoteok(query: str, results: int) -> list[Job]:
    """
    Scrape RemoteOK.com using their public JSON API.
    Only returns remote jobs. Free, no auth required.
    """
    import requests

    tag = _remoteok_tag(query)
    url = f"https://remoteok.com/api?tags={tag}"

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "AutoApply/2.0 (personal job search tool)"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        # First element is a legal disclaimer object — skip it
        items = [x for x in data if isinstance(x, dict) and x.get("position")]

        jobs: list[Job] = []
        today = date.today()

        for item in items[:results]:
            title = item.get("position", "")
            company = item.get("company", "Unknown")
            job_url = item.get("url") or item.get("apply_url", "")
            description = item.get("description", "")
            tags = " ".join(item.get("tags", []))
            posted_epoch = item.get("epoch")
            date_posted = ""
            if posted_epoch:
                try:
                    import datetime as _dt
                    date_posted = _dt.datetime.fromtimestamp(int(posted_epoch)).strftime("%Y-%m-%d")
                except Exception:
                    pass

            salary_str = ""
            salary_min = item.get("salary_min")
            salary_max = item.get("salary_max")
            if salary_min and salary_max:
                salary_str = f"${int(salary_min):,} - ${int(salary_max):,} / year"
            elif salary_min:
                salary_str = f"${int(salary_min):,}+ / year"

            if not title:
                continue

            jobs.append(Job(
                id=_make_id("remoteok", company, title),
                title=title,
                company=company,
                location="Remote",
                description=f"{description}\nSkills: {tags}"[:5000],
                url=job_url,
                source="remoteok",
                salary=salary_str,
                date_posted=date_posted,
            ))
        logger.info(f"  [remoteok] {len(jobs)} jobs for '{query}'")
        return jobs

    except Exception as e:
        logger.warning(f"  [remoteok] API error: {e}")
        return []
