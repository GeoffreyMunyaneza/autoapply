"""
matcher.py — Scores jobs and filters out bad matches.

Phase 2 upgrade: semantic scoring via sentence-transformers (all-MiniLM-L6-v2).
Falls back to keyword-only scoring if the model is unavailable.
Final score = 60% semantic + 40% keyword (or 100% keyword if no model).

Match profiles (ml_match_profile, pm_match_profile) and differentiator_keywords
are read from config.yaml → user_profile at runtime, so nothing personal is
hardcoded here.
"""

import logging
from core.scraper import Job

logger = logging.getLogger(__name__)

# ── Semantic model (lazy-loaded) ───────────────────────────────────────────────
_semantic_model = None
_SEMANTIC_AVAILABLE = None  # None = not yet checked


def _get_semantic_model():
    global _semantic_model, _SEMANTIC_AVAILABLE
    if _SEMANTIC_AVAILABLE is not None:
        return _semantic_model

    try:
        from sentence_transformers import SentenceTransformer
        _semantic_model = SentenceTransformer("all-MiniLM-L6-v2")
        _SEMANTIC_AVAILABLE = True
        logger.info("Semantic matching enabled (all-MiniLM-L6-v2)")
    except Exception as e:
        _SEMANTIC_AVAILABLE = False
        logger.info(f"Semantic model unavailable — using keyword scoring only ({e})")

    return _semantic_model


# ── Keyword banks ──────────────────────────────────────────────────────────────

ML_KEYWORDS = [
    "machine learning", "deep learning", "neural network", "computer vision",
    "nlp", "natural language", "llm", "large language model", "transformer",
    "pytorch", "tensorflow", "scikit-learn", "python", "data scientist",
    "ml engineer", "ai engineer", "applied scientist", "model training",
    "model deployment", "mlops", "sagemaker", "rag", "fine-tuning",
    "reinforcement learning", "time series", "forecasting", "yolo",
    "bert", "gpt", "diffusion", "generative ai", "opencv", "cuda",
]

PM_KEYWORDS = [
    "product manager", "product management", "product owner", "roadmap",
    "stakeholder", "go-to-market", "gtm", "user research", "discovery",
    "agile", "scrum", "kanban", "jira", "confluence", "okr", "kpi",
    "cross-functional", "backlog", "sprint", "mvp", "product strategy",
    "technical product", "ai product", "ml product", "data product",
]

# Default differentiators — extra points if these appear in a job description.
# Override in config.yaml → user_profile.differentiator_keywords
DIFFERENTIATORS: list[str] = []

# Default reference texts for semantic matching — loaded from config at runtime.
# Override in config.yaml → user_profile.ml_match_profile / pm_match_profile
_DEFAULT_ML_PROFILE = (
    "Machine learning engineer with experience in deep learning, computer vision, NLP, "
    "LLMs, PyTorch, TensorFlow, MLOps, model deployment, generative AI, and on-device ML. "
    "Looking for ML Engineer, AI Engineer, Applied Scientist, or Data Scientist roles."
)

_DEFAULT_PM_PROFILE = (
    "Technical product manager with experience in AI/ML product strategy, roadmap, "
    "stakeholder management, agile, go-to-market, OKRs, and cross-functional leadership. "
    "Looking for Senior Product Manager or Technical PM roles in AI/ML."
)


# ── Scoring helpers ────────────────────────────────────────────────────────────

def _count_keywords(text: str, keywords: list[str]) -> int:
    text = text.lower()
    return sum(1 for kw in keywords if kw in text)


def _keyword_score(combined: str, resume_type: str, differentiators: list[str]) -> float:
    if resume_type == "ml":
        hits = _count_keywords(combined, ML_KEYWORDS)
        total = len(ML_KEYWORDS)
    else:
        hits = _count_keywords(combined, PM_KEYWORDS)
        total = len(PM_KEYWORDS)

    diff_hits = _count_keywords(combined, differentiators) if differentiators else 0

    primary_score = min(hits / max(total * 0.15, 1), 1.0)
    if differentiators:
        diff_score = min(diff_hits / max(len(differentiators) * 0.1, 1), 1.0)
        return round(0.8 * primary_score + 0.2 * diff_score, 4)
    return round(primary_score, 4)


def _semantic_score(job: "Job", resume_type: str, user_profile: dict) -> float | None:
    """
    Returns cosine similarity between job description and the user's profile text,
    or None if the model is unavailable.
    Profile text is read from user_profile.ml_match_profile / pm_match_profile.
    """
    model = _get_semantic_model()
    if model is None:
        return None

    try:
        from sentence_transformers import util

        if resume_type == "ml":
            profile_text = user_profile.get("ml_match_profile", _DEFAULT_ML_PROFILE)
        else:
            profile_text = user_profile.get("pm_match_profile", _DEFAULT_PM_PROFILE)

        jd_text = f"{job.title} {job.description}"[:2000]

        embeddings = model.encode([profile_text, jd_text], convert_to_tensor=True)
        similarity = float(util.cos_sim(embeddings[0], embeddings[1]))
        # Cosine similarity is [-1, 1]; normalise to [0, 1]
        return round(max(0.0, (similarity + 1) / 2), 4)
    except Exception as e:
        logger.debug(f"Semantic scoring failed: {e}")
        return None


# ── Public API ─────────────────────────────────────────────────────────────────

def score_job(job: "Job", resume_type: str, user_profile: dict | None = None) -> float:
    """
    Returns a match score 0.0–1.0.
    Combines semantic similarity (60%) and keyword overlap (40%) when the
    sentence-transformers model is available; falls back to keyword-only.

    user_profile: dict from config.yaml → user_profile (ml_match_profile,
                  pm_match_profile, differentiator_keywords).
    """
    profile = user_profile or {}
    differentiators = profile.get("differentiator_keywords", [])

    combined = f"{job.title} {job.description}".lower()
    kw = _keyword_score(combined, resume_type, differentiators)

    sem = _semantic_score(job, resume_type, profile)
    if sem is not None:
        score = 0.6 * sem + 0.4 * kw
    else:
        score = kw

    return round(min(score, 1.0), 3)


def passes_filter(job: "Job", exclude_keywords: list[str], min_desc_length: int) -> tuple[bool, str]:
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


def select_resume_type(job: "Job", configured_type: str) -> str:
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
