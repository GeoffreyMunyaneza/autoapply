"""
matcher.py — Scores jobs against Geoffrey's profile and filters out bad matches.
"""

import re
import logging
from scraper import Job

logger = logging.getLogger(__name__)

# Keywords that boost match score for ML resume
ML_KEYWORDS = [
    "machine learning", "deep learning", "neural network", "computer vision",
    "nlp", "natural language", "llm", "large language model", "transformer",
    "pytorch", "tensorflow", "scikit-learn", "python", "data scientist",
    "ml engineer", "ai engineer", "applied scientist", "model training",
    "model deployment", "mlops", "sagemaker", "rag", "fine-tuning",
    "reinforcement learning", "time series", "forecasting", "yolo",
    "bert", "gpt", "diffusion", "generative ai", "opencv", "cuda",
]

# Keywords that boost match score for PM resume
PM_KEYWORDS = [
    "product manager", "product management", "product owner", "roadmap",
    "stakeholder", "go-to-market", "gtm", "user research", "discovery",
    "agile", "scrum", "kanban", "jira", "confluence", "okr", "kpi",
    "cross-functional", "backlog", "sprint", "mvp", "product strategy",
    "technical product", "ai product", "ml product", "data product",
]

# Geoffrey's strong differentiators — extra points if these appear
DIFFERENTIATORS = [
    "iso 30107", "biometric", "liveness detection", "presentation attack",
    "on-device", "sdk deployment", "rlhf", "responsible ai",
    "medical imaging", "ultrasound", "surgical", "clinical",
    "mba", "kenan-flagler", "cmu", "carnegie mellon",
]


def _count_keywords(text: str, keywords: list[str]) -> int:
    text = text.lower()
    return sum(1 for kw in keywords if kw in text)


def score_job(job: Job, resume_type: str) -> float:
    """
    Returns a match score 0.0–1.0.
    Uses the job title + description for scoring.
    """
    combined = f"{job.title} {job.description}".lower()

    if resume_type == "ml":
        primary_hits = _count_keywords(combined, ML_KEYWORDS)
        primary_total = len(ML_KEYWORDS)
    else:
        primary_hits = _count_keywords(combined, PM_KEYWORDS)
        primary_total = len(PM_KEYWORDS)

    diff_hits = _count_keywords(combined, DIFFERENTIATORS)

    # Normalize: primary keywords weighted 80%, differentiators 20%
    primary_score = min(primary_hits / max(primary_total * 0.15, 1), 1.0)  # cap at 1
    diff_score = min(diff_hits / max(len(DIFFERENTIATORS) * 0.1, 1), 1.0)

    score = 0.8 * primary_score + 0.2 * diff_score
    return round(min(score, 1.0), 3)


def passes_filter(job: Job, exclude_keywords: list[str], min_desc_length: int) -> tuple[bool, str]:
    """Returns (passes, reason_if_rejected)."""
    combined = f"{job.title} {job.description}".lower()

    for kw in exclude_keywords:
        if kw.lower() in combined:
            return False, f"excluded keyword: '{kw}'"

    if len(job.description) < min_desc_length:
        return False, f"description too short ({len(job.description)} chars)"

    if not job.url:
        return False, "no URL"

    return True, ""


def select_resume_type(job: Job, configured_type: str) -> str:
    """
    Double-check resume type selection based on job title.
    Overrides config if the title clearly points to one type.
    """
    title_lower = job.title.lower()
    pm_signals = ["product manager", "product owner", "head of product", "vp product"]
    ml_signals = ["machine learning", "ml engineer", "ai engineer", "data scientist",
                  "applied scientist", "research engineer", "research scientist"]

    if any(s in title_lower for s in pm_signals):
        return "pm"
    if any(s in title_lower for s in ml_signals):
        return "ml"
    return configured_type
