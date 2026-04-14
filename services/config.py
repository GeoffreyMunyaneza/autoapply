"""
services/config.py — Config loading, saving, and .env injection.

Unified source of truth — replaces duplicated load_config / _inject_env
that previously lived in both main.py and app.py.
"""

import os
from pathlib import Path
from typing import Any

import yaml


def load_config(path: str = "config.yaml") -> dict:
    """Load and return config.yaml as a dict."""
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_config(config: dict, path: str = "config.yaml") -> None:
    """Write config dict back to config.yaml, preserving key order."""
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


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
