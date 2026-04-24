"""
services/config.py — Config loading, saving, and .env injection.

Unified source of truth — replaces duplicated load_config / _inject_env
that previously lived in both main.py and app.py.
"""

import os
import shutil
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml


_DEFAULT_CONFIG: dict[str, Any] = {
    "search": {
        "queries": [],
        "sources": ["linkedin", "indeed"],
        "location": "United States",
        "remote_only": False,
        "results_per_query": 15,
        "hours_old": 24,
        "job_type": "fulltime",
        "distance_miles": 50,
        "easy_apply_only": False,
        "proxies": [],
    },
    "filter": {
        "exclude_keywords": [],
        "min_description_length": 300,
    },
    "output": {
        "tracker_file": "output/tracker_v2.xlsx",
        "resumes_folder": "output/resumes",
        "pending_folder": "output/pending",
    },
    "claude": {
        "model": "claude-3-5-haiku-20241022",
        "max_tokens": 4096,
    },
    "cover_letter": {
        "auto_generate": False,
    },
    "review": {
        "auto_approve": True,
    },
    "notifications": {
        "windows_toast": True,
        "email": {
            "enabled": False,
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
        },
    },
    "screening": {
        "questions_file": "questions.yaml",
    },
    "submission": {
        "enabled": False,
        "headless": False,
        "review_before_submit": True,
        "screenshots_folder": "output/screenshots",
        "profile": {},
        "linkedin": {},
    },
    "resumes": {},
    "user_profile": {},
}


def _app_base_dir() -> Path:
    """Return base directory for bundled exe or source checkout."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _packaged_roots() -> list[Path]:
    """Return candidate roots where bundled data files may live."""
    roots = [_app_base_dir()]

    # PyInstaller onedir often stores data under _internal.
    roots.append(_app_base_dir() / "_internal")

    # Onefile extracts to a temp directory exposed via _MEIPASS.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))

    return roots


def resolve_runtime_path(path: str, *, for_write: bool = False) -> Path:
    """
    Resolve a runtime path in source and packaged modes.

    - Absolute paths are returned as-is.
    - Existing relative paths in cwd win.
    - For writes, default to app base dir.
    - For reads, search packaged roots.
    """
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate

    cwd_path = (Path.cwd() / candidate)
    if cwd_path.exists():
        return cwd_path.resolve()

    app_path = (_app_base_dir() / candidate)
    if for_write:
        return app_path

    if app_path.exists():
        return app_path.resolve()

    for root in _packaged_roots():
        packaged = root / candidate
        if packaged.exists():
            return packaged.resolve()

    return app_path


def _bootstrap_default_file(path: str) -> Path | None:
    """Copy bundled default file into writable app dir if available."""
    rel = Path(path)
    if rel.is_absolute():
        return None

    target = resolve_runtime_path(path, for_write=True)
    if target.exists():
        return target

    for root in _packaged_roots():
        source = root / rel
        if source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            return target

    return None


def load_config(path: str = "config.yaml") -> dict:
    """Load and return config.yaml as a raw dict."""
    config_path = resolve_runtime_path(path)
    if not config_path.exists():
        # First run after install may only have config under packaged data location.
        bootstrapped = _bootstrap_default_file(path)
        if bootstrapped is not None:
            config_path = bootstrapped

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_config(config: dict, path: str = "config.yaml") -> None:
    """Write config dict back to config.yaml, preserving key order."""
    config_path = resolve_runtime_path(path, for_write=True)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _merge_defaults(config: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    """Recursively apply defaults without overwriting user-provided values."""
    for key, default_value in defaults.items():
        current = config.get(key)
        if isinstance(default_value, dict):
            if not isinstance(current, dict):
                current = {}
            config[key] = _merge_defaults(current, default_value)
        elif key not in config:
            config[key] = deepcopy(default_value)
    return config


def prepare_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """
    Return a runtime-safe config copy with defaults applied and file paths resolved.

    This keeps config.yaml portable while ensuring the running app always works with
    absolute paths in source mode, packaged mode, and when launched from another cwd.
    """
    runtime = deepcopy(config or {})
    _merge_defaults(runtime, _DEFAULT_CONFIG)

    output_cfg = runtime["output"]
    output_cfg["tracker_file"] = str(resolve_runtime_path(output_cfg["tracker_file"], for_write=True))
    output_cfg["resumes_folder"] = str(resolve_runtime_path(output_cfg["resumes_folder"], for_write=True))
    output_cfg["pending_folder"] = str(resolve_runtime_path(output_cfg["pending_folder"], for_write=True))

    submission_cfg = runtime["submission"]
    submission_cfg["screenshots_folder"] = str(
        resolve_runtime_path(submission_cfg["screenshots_folder"], for_write=True)
    )

    screening_cfg = runtime["screening"]
    screening_cfg["questions_file"] = str(resolve_runtime_path(screening_cfg["questions_file"]))

    resumes_cfg = runtime.get("resumes", {})
    for key, resume_path in list(resumes_cfg.items()):
        if resume_path:
            resumes_cfg[key] = str(resolve_runtime_path(str(resume_path)))

    Path(output_cfg["tracker_file"]).parent.mkdir(parents=True, exist_ok=True)
    Path(output_cfg["resumes_folder"]).mkdir(parents=True, exist_ok=True)
    Path(output_cfg["pending_folder"]).mkdir(parents=True, exist_ok=True)
    Path(submission_cfg["screenshots_folder"]).mkdir(parents=True, exist_ok=True)

    return runtime


def load_runtime_config(path: str = "config.yaml", *, with_env: bool = False) -> dict[str, Any]:
    """Load config.yaml, optionally inject env values, and return the runtime-safe copy."""
    config = load_config(path)
    if with_env:
        inject_env(config)
    return prepare_config(config)


def inject_env(config: dict) -> None:
    """
    Overlay sensitive fields from environment variables into config.
    .env values always win over anything written in config.yaml.
    Called once at startup after load_dotenv().
    """
    # Submission profile
    profile = config.setdefault("submission", {}).setdefault("profile", {})
    if os.environ.get("PROFILE_EMAIL"):
        profile["email"] = os.environ["PROFILE_EMAIL"]
    if os.environ.get("PROFILE_PHONE"):
        profile["phone"] = os.environ["PROFILE_PHONE"]

    # LinkedIn credentials
    linkedin = config["submission"].setdefault("linkedin", {})
    if os.environ.get("LINKEDIN_EMAIL"):
        linkedin["email"] = os.environ["LINKEDIN_EMAIL"]
    if os.environ.get("LINKEDIN_PASSWORD"):
        linkedin["password"] = os.environ["LINKEDIN_PASSWORD"]

    # Email digest SMTP
    email_cfg = config.setdefault("notifications", {}).setdefault("email", {})
    if os.environ.get("SMTP_FROM"):
        email_cfg["from_address"] = os.environ["SMTP_FROM"]
    if os.environ.get("SMTP_TO"):
        email_cfg["to_address"] = os.environ["SMTP_TO"]
    if os.environ.get("SMTP_PASSWORD"):
        email_cfg["password"] = os.environ["SMTP_PASSWORD"]
        if all(os.environ.get(k) for k in ("SMTP_FROM", "SMTP_TO", "SMTP_PASSWORD")):
            email_cfg["enabled"] = True
