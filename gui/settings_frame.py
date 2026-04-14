"""
gui/settings_frame.py — Config editor tab.

Reads config.yaml → renders form fields → writes back on Save.
Sections: Search · Filter · AI/Claude · Notifications · Submission
"""

from __future__ import annotations
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import Any

import customtkinter as ctk
import yaml


# Available sources (checkbox list)
_ALL_SOURCES = [
    "linkedin", "indeed", "zip_recruiter", "glassdoor",
    "google", "dice", "remoteok", "wellfound",
]

# Claude model options
_CLAUDE_MODELS = [
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-6",
]


class SettingsFrame(ctk.CTkFrame):
    """Form-based editor for config.yaml."""

    def __init__(self, parent, config_path: str, on_save=None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._config_path = config_path
        self._on_save = on_save    # called after successful save
        self._config: dict = {}
        self._widgets: dict[str, Any] = {}
        self._query_rows: list[dict] = []
        self._source_vars: dict[str, tk.BooleanVar] = {}
        self._exclude_tags: list[str] = []

        self._build_ui()
        self._load()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Header
        hdr = ctk.CTkFrame(self, height=40, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(12, 0))
        ctk.CTkLabel(hdr, text="Settings", font=("Segoe UI", 18, "bold")).pack(side="left")
        ctk.CTkButton(
            hdr, text="💾  Save Settings", width=140, height=32,
            command=self._save,
        ).pack(side="right")
        ctk.CTkButton(
            hdr, text="↺  Reload", width=90, height=32,
            command=self._load,
        ).pack(side="right", padx=(0, 8))

        # Scrollable content area
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True, padx=8, pady=(8, 8))

        self._build_automation_section()
        self._build_search_section()
        self._build_filter_section()
        self._build_ai_section()
        self._build_notifications_section()
        self._build_submission_section()

    # ── Section: Automation ───────────────────────────────────────────────────

    def _build_automation_section(self) -> None:
        sec = self._section("Automation Schedule")

        ctk.CTkLabel(
            sec,
            text="AutoApply runs the pipeline automatically on the configured schedule.\n"
                 "Uses standard cron syntax (minute hour day month weekday).",
            font=("Segoe UI", 11), text_color="#9CA3AF", wraplength=700, justify="left",
        ).pack(anchor="w", pady=(0, 8))

        row1 = ctk.CTkFrame(sec, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 8))
        self._w("schedule_enabled", tk.BooleanVar())
        ctk.CTkCheckBox(
            row1, text="Enable automatic runs",
            variable=self._widgets["schedule_enabled"],
        ).pack(side="left", padx=(0, 20))
        self._w("schedule_auto_submit", tk.BooleanVar())
        ctk.CTkCheckBox(
            row1, text="Auto-submit queued jobs after each run  ⚠ use carefully",
            variable=self._widgets["schedule_auto_submit"],
        ).pack(side="left")

        row2 = ctk.CTkFrame(sec, fg_color="transparent")
        row2.pack(fill="x")
        ctk.CTkLabel(row2, text="Cron expression:", text_color="#9CA3AF").pack(side="left")
        self._w("schedule_cron", ctk.CTkEntry(row2, width=160, height=30))
        self._widgets["schedule_cron"].pack(side="left", padx=(6, 20))
        ctk.CTkLabel(
            row2,
            text="e.g.  0 */4 * * *  = every 4 h     0 8 * * *  = daily 8 AM",
            font=("Segoe UI", 11), text_color="#6B7280",
        ).pack(side="left")

    # ── Section: Search ───────────────────────────────────────────────────────

    def _build_search_section(self) -> None:
        sec = self._section("Search Queries & Sources")

        # Queries
        ctk.CTkLabel(sec, text="Search Queries", font=("Segoe UI", 12, "bold"),
                     text_color="#D1D5DB").pack(anchor="w", pady=(4, 4))
        ctk.CTkLabel(sec, text="Add one query per line. Prefix with [ML] or [PM] for resume type.",
                     font=("Segoe UI", 11), text_color="#9CA3AF").pack(anchor="w")

        self._queries_text = ctk.CTkTextbox(sec, height=140, font=("Consolas", 12))
        self._queries_text.pack(fill="x", pady=(4, 10))

        # Sources
        ctk.CTkLabel(sec, text="Job Sources", font=("Segoe UI", 12, "bold"),
                     text_color="#D1D5DB").pack(anchor="w", pady=(4, 4))
        src_frame = ctk.CTkFrame(sec, fg_color="transparent")
        src_frame.pack(fill="x")
        for i, src in enumerate(_ALL_SOURCES):
            var = tk.BooleanVar(value=False)
            self._source_vars[src] = var
            ctk.CTkCheckBox(src_frame, text=src, variable=var, width=130).grid(
                row=i // 4, column=i % 4, sticky="w", padx=8, pady=2
            )

        # Location + toggles
        row2 = ctk.CTkFrame(sec, fg_color="transparent")
        row2.pack(fill="x", pady=(10, 4))
        ctk.CTkLabel(row2, text="Location:", text_color="#9CA3AF").pack(side="left")
        self._w("location", ctk.CTkEntry(row2, width=200, height=30))
        self._widgets["location"].pack(side="left", padx=(6, 20))

        self._w("remote_only", tk.BooleanVar())
        ctk.CTkCheckBox(row2, text="Remote Only", variable=self._widgets["remote_only"]).pack(
            side="left", padx=(0, 20)
        )

        ctk.CTkLabel(row2, text="Results/query:", text_color="#9CA3AF").pack(side="left")
        self._w("results_per_query", ctk.CTkEntry(row2, width=60, height=30))
        self._widgets["results_per_query"].pack(side="left", padx=(6, 20))

        ctk.CTkLabel(row2, text="Hours old:", text_color="#9CA3AF").pack(side="left")
        self._w("hours_old", ctk.CTkEntry(row2, width=60, height=30))
        self._widgets["hours_old"].pack(side="left", padx=(6, 0))

    # ── Section: Filter ───────────────────────────────────────────────────────

    def _build_filter_section(self) -> None:
        sec = self._section("Job Filters")

        ctk.CTkLabel(sec, text="Exclude Keywords (one per line):",
                     font=("Segoe UI", 12), text_color="#D1D5DB").pack(anchor="w", pady=(4, 4))
        self._w("exclude_keywords", ctk.CTkTextbox(sec, height=80, font=("Consolas", 12)))
        self._widgets["exclude_keywords"].pack(fill="x", pady=(0, 10))

        row = ctk.CTkFrame(sec, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(row, text="Min description length:", text_color="#9CA3AF").pack(side="left")
        self._w("min_desc_length", ctk.CTkEntry(row, width=80, height=30))
        self._widgets["min_desc_length"].pack(side="left", padx=(6, 0))

    # ── Section: AI / Claude ──────────────────────────────────────────────────

    def _build_ai_section(self) -> None:
        sec = self._section("AI / Claude")

        row = ctk.CTkFrame(sec, fg_color="transparent")
        row.pack(fill="x", pady=(4, 8))
        ctk.CTkLabel(row, text="Model:", text_color="#9CA3AF").pack(side="left")
        self._w("claude_model", ctk.CTkOptionMenu(row, values=_CLAUDE_MODELS, width=230, height=30))
        self._widgets["claude_model"].pack(side="left", padx=(6, 20))

        ctk.CTkLabel(row, text="Max tokens:", text_color="#9CA3AF").pack(side="left")
        self._w("claude_max_tokens", ctk.CTkEntry(row, width=80, height=30))
        self._widgets["claude_max_tokens"].pack(side="left", padx=(6, 0))

        row2 = ctk.CTkFrame(sec, fg_color="transparent")
        row2.pack(fill="x")
        self._w("auto_cover_letter", tk.BooleanVar())
        ctk.CTkCheckBox(
            row2, text="Auto-generate cover letters per job",
            variable=self._widgets["auto_cover_letter"],
        ).pack(side="left")

    # ── Section: Notifications ────────────────────────────────────────────────

    def _build_notifications_section(self) -> None:
        sec = self._section("Notifications")

        row1 = ctk.CTkFrame(sec, fg_color="transparent")
        row1.pack(fill="x", pady=(4, 8))
        self._w("windows_toast", tk.BooleanVar())
        ctk.CTkCheckBox(
            row1, text="Windows toast notifications",
            variable=self._widgets["windows_toast"],
        ).pack(side="left")

        row2 = ctk.CTkFrame(sec, fg_color="transparent")
        row2.pack(fill="x", pady=(0, 4))
        self._w("email_enabled", tk.BooleanVar())
        ctk.CTkCheckBox(
            row2, text="Email digest", variable=self._widgets["email_enabled"],
        ).pack(side="left", padx=(0, 20))

        for label, key, width in [
            ("SMTP Host:", "smtp_host", 180),
            ("Port:",      "smtp_port", 70),
        ]:
            ctk.CTkLabel(row2, text=label, text_color="#9CA3AF").pack(side="left")
            self._w(key, ctk.CTkEntry(row2, width=width, height=30))
            self._widgets[key].pack(side="left", padx=(6, 16))

        row3 = ctk.CTkFrame(sec, fg_color="transparent")
        row3.pack(fill="x")
        for label, key in [("From:", "smtp_from"), ("To:", "smtp_to")]:
            ctk.CTkLabel(row3, text=label, text_color="#9CA3AF").pack(side="left")
            self._w(key, ctk.CTkEntry(row3, width=220, height=30))
            self._widgets[key].pack(side="left", padx=(6, 20))

        ctk.CTkLabel(sec,
                     text="Note: SMTP password should be set in .env as SMTP_PASSWORD",
                     font=("Segoe UI", 11), text_color="#6B7280").pack(anchor="w", pady=(6, 0))

    # ── Section: Submission ───────────────────────────────────────────────────

    def _build_submission_section(self) -> None:
        sec = self._section("Auto-Submission")

        row1 = ctk.CTkFrame(sec, fg_color="transparent")
        row1.pack(fill="x", pady=(4, 8))
        self._w("submission_enabled", tk.BooleanVar())
        ctk.CTkCheckBox(
            row1, text="Enable auto-submit",
            variable=self._widgets["submission_enabled"],
        ).pack(side="left", padx=(0, 20))
        self._w("submission_headless", tk.BooleanVar())
        ctk.CTkCheckBox(
            row1, text="Run browser in background (headless)",
            variable=self._widgets["submission_headless"],
        ).pack(side="left")

        # Profile fields
        ctk.CTkLabel(sec, text="Applicant Profile",
                     font=("Segoe UI", 12, "bold"), text_color="#D1D5DB").pack(
            anchor="w", pady=(6, 4)
        )
        grid = ctk.CTkFrame(sec, fg_color="transparent")
        grid.pack(fill="x")
        profile_fields = [
            ("First Name:",   "first_name",  160),
            ("Last Name:",    "last_name",   160),
            ("LinkedIn URL:", "linkedin",    260),
            ("GitHub URL:",   "github",      260),
            ("Current Company:", "current_company", 220),
            ("Work Auth:",    "work_auth",   100),
        ]
        for i, (label, key, width) in enumerate(profile_fields):
            r, c = divmod(i, 2)
            ctk.CTkLabel(grid, text=label, text_color="#9CA3AF").grid(
                row=r, column=c * 3, sticky="e", padx=(8, 4), pady=4
            )
            self._w(key, ctk.CTkEntry(grid, width=width, height=30))
            self._widgets[key].grid(row=r, column=c * 3 + 1, sticky="w", padx=(0, 20), pady=4)

        row_sp = ctk.CTkFrame(sec, fg_color="transparent")
        row_sp.pack(fill="x", pady=(4, 4))
        self._w("requires_sponsorship", tk.BooleanVar())
        ctk.CTkCheckBox(
            row_sp, text="Requires visa sponsorship",
            variable=self._widgets["requires_sponsorship"],
        ).pack(side="left")

        ctk.CTkLabel(sec,
                     text="Note: LinkedIn email/password should be set in .env as LINKEDIN_EMAIL / LINKEDIN_PASSWORD",
                     font=("Segoe UI", 11), text_color="#6B7280").pack(anchor="w", pady=(6, 0))

    # ── Load / Save ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}
        except FileNotFoundError:
            messagebox.showerror("Error", f"config.yaml not found: {self._config_path}")
            return

        cfg = self._config

        # Automation
        sched = cfg.get("schedule", {})
        self._widgets["schedule_enabled"].set(bool(sched.get("enabled", False)))
        self._widgets["schedule_auto_submit"].set(bool(sched.get("auto_submit", False)))
        self._set_entry("schedule_cron", sched.get("cron", "0 */4 * * *"))

        # Queries
        search = cfg.get("search", {})
        self._queries_text.delete("1.0", "end")
        for q in search.get("queries", []):
            rtype = q.get("resume_type", "ml").upper()
            self._queries_text.insert("end", f"[{rtype}] {q.get('query', '')}\n")

        # Sources
        enabled_sources = set(search.get("sources", []))
        for src, var in self._source_vars.items():
            var.set(src in enabled_sources)

        self._set_entry("location", search.get("location", ""))
        self._widgets["remote_only"].set(bool(search.get("remote_only", False)))
        self._set_entry("results_per_query", str(search.get("results_per_query", 15)))
        self._set_entry("hours_old", str(search.get("hours_old", 24)))

        # Filter
        filt = cfg.get("filter", {})
        self._widgets["exclude_keywords"].delete("1.0", "end")
        for kw in filt.get("exclude_keywords", []):
            self._widgets["exclude_keywords"].insert("end", kw + "\n")
        self._set_entry("min_desc_length", str(filt.get("min_description_length", 300)))

        # Claude
        claude = cfg.get("claude", {})
        self._widgets["claude_model"].set(claude.get("model", _CLAUDE_MODELS[0]))
        self._set_entry("claude_max_tokens", str(claude.get("max_tokens", 4096)))
        cover = cfg.get("cover_letter", {})
        self._widgets["auto_cover_letter"].set(bool(cover.get("auto_generate", False)))

        # Notifications
        notif = cfg.get("notifications", {})
        self._widgets["windows_toast"].set(bool(notif.get("windows_toast", True)))
        email = notif.get("email", {})
        self._widgets["email_enabled"].set(bool(email.get("enabled", False)))
        self._set_entry("smtp_host", email.get("smtp_host", "smtp.gmail.com"))
        self._set_entry("smtp_port", str(email.get("smtp_port", 587)))
        self._set_entry("smtp_from", email.get("from_address", ""))
        self._set_entry("smtp_to",   email.get("to_address", ""))

        # Submission
        sub = cfg.get("submission", {})
        self._widgets["submission_enabled"].set(bool(sub.get("enabled", False)))
        self._widgets["submission_headless"].set(bool(sub.get("headless", False)))
        profile = sub.get("profile", {})
        self._set_entry("first_name", profile.get("first_name", ""))
        self._set_entry("last_name",  profile.get("last_name", ""))
        self._set_entry("linkedin",   profile.get("linkedin", ""))
        self._set_entry("github",     profile.get("github", ""))
        self._set_entry("current_company", profile.get("current_company", ""))
        self._set_entry("work_auth",  profile.get("work_authorization", ""))
        self._widgets["requires_sponsorship"].set(
            bool(profile.get("requires_sponsorship", False))
        )

    def _save(self) -> None:
        cfg = dict(self._config)  # shallow copy to preserve unrelated keys

        # Automation
        cfg["schedule"] = {
            "enabled":     self._widgets["schedule_enabled"].get(),
            "cron":        self._get_entry("schedule_cron") or "0 */4 * * *",
            "auto_submit": self._widgets["schedule_auto_submit"].get(),
        }

        # Queries
        queries = []
        for line in self._queries_text.get("1.0", "end").strip().splitlines():
            line = line.strip()
            if not line:
                continue
            if line.upper().startswith("[ML]"):
                queries.append({"query": line[4:].strip(), "resume_type": "ml"})
            elif line.upper().startswith("[PM]"):
                queries.append({"query": line[4:].strip(), "resume_type": "pm"})
            else:
                queries.append({"query": line, "resume_type": "ml"})

        sources = [src for src, var in self._source_vars.items() if var.get()]

        cfg["search"] = {
            "queries":          queries,
            "sources":          sources,
            "location":         self._get_entry("location"),
            "remote_only":      self._widgets["remote_only"].get(),
            "results_per_query": int(self._get_entry("results_per_query") or 15),
            "hours_old":        int(self._get_entry("hours_old") or 24),
            "job_type":         cfg.get("search", {}).get("job_type", "fulltime"),
            "distance_miles":   cfg.get("search", {}).get("distance_miles", 50),
            "easy_apply_only":  cfg.get("search", {}).get("easy_apply_only", False),
            "proxies":          cfg.get("search", {}).get("proxies", []),
        }

        # Filter
        kw_text = self._widgets["exclude_keywords"].get("1.0", "end")
        keywords = [k.strip() for k in kw_text.splitlines() if k.strip()]
        cfg["filter"] = {
            "exclude_keywords":    keywords,
            "min_description_length": int(self._get_entry("min_desc_length") or 300),
        }

        # Claude
        cfg["claude"] = {
            "model":      self._widgets["claude_model"].get(),
            "max_tokens": int(self._get_entry("claude_max_tokens") or 4096),
        }
        cfg["cover_letter"] = {"auto_generate": self._widgets["auto_cover_letter"].get()}

        # Notifications
        cfg["notifications"] = {
            "windows_toast": self._widgets["windows_toast"].get(),
            "email": {
                "enabled":      self._widgets["email_enabled"].get(),
                "smtp_host":    self._get_entry("smtp_host"),
                "smtp_port":    int(self._get_entry("smtp_port") or 587),
                "from_address": self._get_entry("smtp_from"),
                "to_address":   self._get_entry("smtp_to"),
            },
        }

        # Submission
        sub = cfg.get("submission", {})
        sub["enabled"]  = self._widgets["submission_enabled"].get()
        sub["headless"] = self._widgets["submission_headless"].get()
        profile = sub.setdefault("profile", {})
        profile["first_name"]          = self._get_entry("first_name")
        profile["last_name"]           = self._get_entry("last_name")
        profile["linkedin"]            = self._get_entry("linkedin")
        profile["github"]              = self._get_entry("github")
        profile["current_company"]     = self._get_entry("current_company")
        profile["work_authorization"]  = self._get_entry("work_auth")
        profile["requires_sponsorship"]= self._widgets["requires_sponsorship"].get()
        cfg["submission"] = sub

        # Preserve resumes + screening sections
        cfg.setdefault("resumes", self._config.get("resumes", {}))
        cfg.setdefault("screening", self._config.get("screening", {}))
        cfg.setdefault("output", self._config.get("output", {}))

        with open(self._config_path, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        messagebox.showinfo("Saved", "Settings saved to config.yaml")
        self._config = cfg
        if self._on_save:
            self._on_save()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _section(self, title: str) -> ctk.CTkFrame:
        """Create a titled section card in the scroll area."""
        card = ctk.CTkFrame(self._scroll, fg_color="#1F2937", corner_radius=8)
        card.pack(fill="x", padx=4, pady=(0, 12))
        ctk.CTkLabel(
            card, text=title, font=("Segoe UI", 13, "bold"),
            text_color="#60A5FA",
        ).pack(anchor="w", padx=14, pady=(10, 4))
        ctk.CTkFrame(card, height=1, fg_color="#374151").pack(fill="x", padx=14, pady=(0, 8))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=(0, 12))
        return inner

    def _w(self, key: str, widget) -> None:
        self._widgets[key] = widget

    def _set_entry(self, key: str, value: str) -> None:
        w = self._widgets.get(key)
        if isinstance(w, ctk.CTkEntry):
            w.delete(0, "end")
            w.insert(0, value)

    def _get_entry(self, key: str) -> str:
        w = self._widgets.get(key)
        if isinstance(w, ctk.CTkEntry):
            return w.get()
        return ""
