"""
Settings editor for config.yaml.
"""

from __future__ import annotations

import os
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import Any

import customtkinter as ctk

from services.config import load_config, resolve_runtime_path, save_config

ALL_SOURCES = [
    "linkedin",
    "indeed",
    "zip_recruiter",
    "glassdoor",
    "google",
    "dice",
    "remoteok",
    "wellfound",
]

CLAUDE_MODELS = [
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
    "claude-3-haiku-20240307",
]


class SettingsFrame(ctk.CTkFrame):
    """Form-based editor for the core runtime settings."""

    def __init__(self, parent, config_path: str, on_save=None, **kwargs) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._config_path = config_path
        self._on_save = on_save
        self._config: dict[str, Any] = {}
        self._widgets: dict[str, Any] = {}
        self._source_vars: dict[str, tk.BooleanVar] = {}

        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        header = ctk.CTkFrame(self, height=40, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(12, 0))
        ctk.CTkLabel(header, text="Settings", font=("Segoe UI", 18, "bold")).pack(side="left")
        ctk.CTkButton(header, text="Save Settings", width=140, height=32, command=self._save).pack(side="right")
        ctk.CTkButton(header, text="Reload", width=90, height=32, command=self._load).pack(
            side="right",
            padx=(0, 8),
        )

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.pack(fill="both", expand=True, padx=8, pady=(8, 8))

        self._build_setup_section()
        self._build_search_section()
        self._build_filter_section()
        self._build_ai_section()
        self._build_notifications_section()
        self._build_submission_section()

    def _build_setup_section(self) -> None:
        section = self._section("First Use")
        ctk.CTkLabel(
            section,
            text=(
                "Start here after opening the app:\n"
                "1. Open config.yaml and fill the user_profile template and resume paths.\n"
                "2. Open .env and add your API key and contact details.\n"
                "3. Open questions.yaml and set your screening answers.\n"
                "4. Return here to tune search and submission settings, then run the pipeline."
            ),
            font=("Segoe UI", 11),
            text_color="#9CA3AF",
            justify="left",
            wraplength=720,
        ).pack(anchor="w", pady=(0, 10))

        button_row = ctk.CTkFrame(section, fg_color="transparent")
        button_row.pack(fill="x")
        ctk.CTkButton(button_row, text="Open config.yaml", width=140, command=self._open_config).pack(
            side="left",
            padx=(0, 8),
        )
        ctk.CTkButton(button_row, text="Open .env", width=110, command=self._open_env).pack(
            side="left",
            padx=(0, 8),
        )
        ctk.CTkButton(
            button_row,
            text="Open questions.yaml",
            width=150,
            command=self._open_questions,
        ).pack(side="left")

    def _build_search_section(self) -> None:
        section = self._section("Search")

        ctk.CTkLabel(
            section,
            text="Queries",
            font=("Segoe UI", 12, "bold"),
            text_color="#D1D5DB",
        ).pack(anchor="w", pady=(4, 4))
        ctk.CTkLabel(
            section,
            text="Add one query per line. Prefix with [ML] or [PM] to choose the resume type.",
            font=("Segoe UI", 11),
            text_color="#9CA3AF",
        ).pack(anchor="w")
        self._queries_text = ctk.CTkTextbox(section, height=140, font=("Consolas", 12))
        self._queries_text.pack(fill="x", pady=(4, 10))

        ctk.CTkLabel(
            section,
            text="Sources",
            font=("Segoe UI", 12, "bold"),
            text_color="#D1D5DB",
        ).pack(anchor="w", pady=(4, 4))
        source_frame = ctk.CTkFrame(section, fg_color="transparent")
        source_frame.pack(fill="x")
        for index, source in enumerate(ALL_SOURCES):
            var = tk.BooleanVar(value=False)
            self._source_vars[source] = var
            ctk.CTkCheckBox(source_frame, text=source, variable=var, width=130).grid(
                row=index // 4,
                column=index % 4,
                sticky="w",
                padx=8,
                pady=2,
            )

        row = ctk.CTkFrame(section, fg_color="transparent")
        row.pack(fill="x", pady=(10, 4))
        ctk.CTkLabel(row, text="Location:", text_color="#9CA3AF").pack(side="left")
        self._register_widget("location", ctk.CTkEntry(row, width=200, height=30))
        self._widgets["location"].pack(side="left", padx=(6, 20))

        self._register_widget("remote_only", tk.BooleanVar())
        ctk.CTkCheckBox(row, text="Remote Only", variable=self._widgets["remote_only"]).pack(
            side="left",
            padx=(0, 20),
        )

        ctk.CTkLabel(row, text="Results/query:", text_color="#9CA3AF").pack(side="left")
        self._register_widget("results_per_query", ctk.CTkEntry(row, width=60, height=30))
        self._widgets["results_per_query"].pack(side="left", padx=(6, 20))

        ctk.CTkLabel(row, text="Hours old:", text_color="#9CA3AF").pack(side="left")
        self._register_widget("hours_old", ctk.CTkEntry(row, width=60, height=30))
        self._widgets["hours_old"].pack(side="left", padx=(6, 0))

    def _build_filter_section(self) -> None:
        section = self._section("Filters")
        ctk.CTkLabel(
            section,
            text="Exclude Keywords (one per line):",
            font=("Segoe UI", 12),
            text_color="#D1D5DB",
        ).pack(anchor="w", pady=(4, 4))
        self._register_widget("exclude_keywords", ctk.CTkTextbox(section, height=80, font=("Consolas", 12)))
        self._widgets["exclude_keywords"].pack(fill="x", pady=(0, 10))

        row = ctk.CTkFrame(section, fg_color="transparent")
        row.pack(fill="x")
        ctk.CTkLabel(row, text="Min description length:", text_color="#9CA3AF").pack(side="left")
        self._register_widget("min_desc_length", ctk.CTkEntry(row, width=80, height=30))
        self._widgets["min_desc_length"].pack(side="left", padx=(6, 0))

    def _build_ai_section(self) -> None:
        section = self._section("AI")

        row = ctk.CTkFrame(section, fg_color="transparent")
        row.pack(fill="x", pady=(4, 8))
        ctk.CTkLabel(row, text="Model:", text_color="#9CA3AF").pack(side="left")
        self._register_widget("claude_model", ctk.CTkOptionMenu(row, values=CLAUDE_MODELS, width=230, height=30))
        self._widgets["claude_model"].pack(side="left", padx=(6, 20))

        ctk.CTkLabel(row, text="Max tokens:", text_color="#9CA3AF").pack(side="left")
        self._register_widget("claude_max_tokens", ctk.CTkEntry(row, width=80, height=30))
        self._widgets["claude_max_tokens"].pack(side="left", padx=(6, 0))

        toggle_row = ctk.CTkFrame(section, fg_color="transparent")
        toggle_row.pack(fill="x")
        self._register_widget("auto_cover_letter", tk.BooleanVar())
        ctk.CTkCheckBox(
            toggle_row,
            text="Auto-generate cover letters per job",
            variable=self._widgets["auto_cover_letter"],
        ).pack(side="left", padx=(0, 20))

        self._register_widget("review_auto_approve", tk.BooleanVar())
        ctk.CTkCheckBox(
            toggle_row,
            text="Auto-approve tailored resumes",
            variable=self._widgets["review_auto_approve"],
        ).pack(side="left")

        ctk.CTkLabel(
            section,
            text="Turn auto-approve off to route changed resumes into output/pending for review.",
            font=("Segoe UI", 11),
            text_color="#6B7280",
        ).pack(anchor="w", pady=(6, 0))

    def _build_notifications_section(self) -> None:
        section = self._section("Notifications")

        row = ctk.CTkFrame(section, fg_color="transparent")
        row.pack(fill="x", pady=(4, 8))
        self._register_widget("windows_toast", tk.BooleanVar())
        ctk.CTkCheckBox(
            row,
            text="Windows toast notifications",
            variable=self._widgets["windows_toast"],
        ).pack(side="left")

        email_row = ctk.CTkFrame(section, fg_color="transparent")
        email_row.pack(fill="x", pady=(0, 4))
        self._register_widget("email_enabled", tk.BooleanVar())
        ctk.CTkCheckBox(email_row, text="Email digest", variable=self._widgets["email_enabled"]).pack(
            side="left",
            padx=(0, 20),
        )

        for label, key, width in (("SMTP Host:", "smtp_host", 180), ("Port:", "smtp_port", 70)):
            ctk.CTkLabel(email_row, text=label, text_color="#9CA3AF").pack(side="left")
            self._register_widget(key, ctk.CTkEntry(email_row, width=width, height=30))
            self._widgets[key].pack(side="left", padx=(6, 16))

        address_row = ctk.CTkFrame(section, fg_color="transparent")
        address_row.pack(fill="x")
        for label, key in (("From:", "smtp_from"), ("To:", "smtp_to")):
            ctk.CTkLabel(address_row, text=label, text_color="#9CA3AF").pack(side="left")
            self._register_widget(key, ctk.CTkEntry(address_row, width=220, height=30))
            self._widgets[key].pack(side="left", padx=(6, 20))

        ctk.CTkLabel(
            section,
            text="Set SMTP_PASSWORD in .env if you want email notifications.",
            font=("Segoe UI", 11),
            text_color="#6B7280",
        ).pack(anchor="w", pady=(6, 0))

    def _build_submission_section(self) -> None:
        section = self._section("Submission")

        row = ctk.CTkFrame(section, fg_color="transparent")
        row.pack(fill="x", pady=(4, 8))
        self._register_widget("submission_enabled", tk.BooleanVar())
        ctk.CTkCheckBox(
            row,
            text="Enable auto-submit",
            variable=self._widgets["submission_enabled"],
        ).pack(side="left", padx=(0, 20))
        self._register_widget("submission_headless", tk.BooleanVar())
        ctk.CTkCheckBox(
            row,
            text="Run browser headless",
            variable=self._widgets["submission_headless"],
        ).pack(side="left")

        ctk.CTkLabel(
            section,
            text="Applicant Profile",
            font=("Segoe UI", 12, "bold"),
            text_color="#D1D5DB",
        ).pack(anchor="w", pady=(6, 4))

        grid = ctk.CTkFrame(section, fg_color="transparent")
        grid.pack(fill="x")
        profile_fields = [
            ("First Name:", "first_name", 160),
            ("Last Name:", "last_name", 160),
            ("LinkedIn URL:", "linkedin", 260),
            ("GitHub URL:", "github", 260),
            ("Current Company:", "current_company", 220),
            ("Work Auth:", "work_auth", 100),
        ]
        for index, (label, key, width) in enumerate(profile_fields):
            row_index, column_index = divmod(index, 2)
            ctk.CTkLabel(grid, text=label, text_color="#9CA3AF").grid(
                row=row_index,
                column=column_index * 3,
                sticky="e",
                padx=(8, 4),
                pady=4,
            )
            self._register_widget(key, ctk.CTkEntry(grid, width=width, height=30))
            self._widgets[key].grid(
                row=row_index,
                column=column_index * 3 + 1,
                sticky="w",
                padx=(0, 20),
                pady=4,
            )

        sponsor_row = ctk.CTkFrame(section, fg_color="transparent")
        sponsor_row.pack(fill="x", pady=(4, 4))
        self._register_widget("requires_sponsorship", tk.BooleanVar())
        ctk.CTkCheckBox(
            sponsor_row,
            text="Requires visa sponsorship",
            variable=self._widgets["requires_sponsorship"],
        ).pack(side="left")

        ctk.CTkLabel(
            section,
            text="Set LinkedIn credentials in .env if you want LinkedIn Easy Apply support.",
            font=("Segoe UI", 11),
            text_color="#6B7280",
        ).pack(anchor="w", pady=(6, 0))

    def _load(self) -> None:
        try:
            self._config = load_config(self._config_path)
        except Exception as exc:
            messagebox.showerror("Error", f"Failed to load config: {exc}")
            return

        config = self._config
        search = config.get("search", {})
        filters = config.get("filter", {})
        claude = config.get("claude", {})
        cover_letter = config.get("cover_letter", {})
        review = config.get("review", {})
        notifications = config.get("notifications", {})
        email = notifications.get("email", {})
        submission = config.get("submission", {})
        profile = submission.get("profile", {})

        self._queries_text.delete("1.0", "end")
        for query_cfg in search.get("queries", []):
            resume_type = query_cfg.get("resume_type", "ml").upper()
            self._queries_text.insert("end", f"[{resume_type}] {query_cfg.get('query', '')}\n")

        enabled_sources = set(search.get("sources", []))
        for source, var in self._source_vars.items():
            var.set(source in enabled_sources)

        self._set_entry("location", search.get("location", ""))
        self._widgets["remote_only"].set(bool(search.get("remote_only", False)))
        self._set_entry("results_per_query", str(search.get("results_per_query", 15)))
        self._set_entry("hours_old", str(search.get("hours_old", 24)))

        self._widgets["exclude_keywords"].delete("1.0", "end")
        for keyword in filters.get("exclude_keywords", []):
            self._widgets["exclude_keywords"].insert("end", keyword + "\n")
        self._set_entry("min_desc_length", str(filters.get("min_description_length", 300)))

        self._widgets["claude_model"].set(claude.get("model", CLAUDE_MODELS[0]))
        self._set_entry("claude_max_tokens", str(claude.get("max_tokens", 4096)))
        self._widgets["auto_cover_letter"].set(bool(cover_letter.get("auto_generate", False)))
        self._widgets["review_auto_approve"].set(bool(review.get("auto_approve", True)))

        self._widgets["windows_toast"].set(bool(notifications.get("windows_toast", True)))
        self._widgets["email_enabled"].set(bool(email.get("enabled", False)))
        self._set_entry("smtp_host", email.get("smtp_host", "smtp.gmail.com"))
        self._set_entry("smtp_port", str(email.get("smtp_port", 587)))
        self._set_entry("smtp_from", email.get("from_address", ""))
        self._set_entry("smtp_to", email.get("to_address", ""))

        self._widgets["submission_enabled"].set(bool(submission.get("enabled", False)))
        self._widgets["submission_headless"].set(bool(submission.get("headless", False)))
        self._set_entry("first_name", profile.get("first_name", ""))
        self._set_entry("last_name", profile.get("last_name", ""))
        self._set_entry("linkedin", profile.get("linkedin", ""))
        self._set_entry("github", profile.get("github", ""))
        self._set_entry("current_company", profile.get("current_company", ""))
        self._set_entry("work_auth", profile.get("work_authorization", ""))
        self._widgets["requires_sponsorship"].set(bool(profile.get("requires_sponsorship", False)))

    def _save(self) -> None:
        config = dict(self._config)

        try:
            results_per_query = int(self._get_entry("results_per_query") or 15)
            hours_old = int(self._get_entry("hours_old") or 24)
            min_desc_length = int(self._get_entry("min_desc_length") or 300)
            claude_max_tokens = int(self._get_entry("claude_max_tokens") or 4096)
            smtp_port = int(self._get_entry("smtp_port") or 587)
        except ValueError:
            messagebox.showerror(
                "Invalid Settings",
                "Results/query, Hours old, Min description length, Max tokens, and SMTP port must be whole numbers.",
            )
            return

        queries = []
        for raw_line in self._queries_text.get("1.0", "end").strip().splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.upper().startswith("[ML]"):
                queries.append({"query": line[4:].strip(), "resume_type": "ml"})
            elif line.upper().startswith("[PM]"):
                queries.append({"query": line[4:].strip(), "resume_type": "pm"})
            else:
                queries.append({"query": line, "resume_type": "ml"})

        config["search"] = {
            "queries": queries,
            "sources": [source for source, var in self._source_vars.items() if var.get()],
            "location": self._get_entry("location"),
            "remote_only": self._widgets["remote_only"].get(),
            "results_per_query": results_per_query,
            "hours_old": hours_old,
            "job_type": config.get("search", {}).get("job_type", "fulltime"),
            "distance_miles": config.get("search", {}).get("distance_miles", 50),
            "easy_apply_only": config.get("search", {}).get("easy_apply_only", False),
            "proxies": config.get("search", {}).get("proxies", []),
        }

        config["filter"] = {
            "exclude_keywords": [
                keyword.strip()
                for keyword in self._widgets["exclude_keywords"].get("1.0", "end").splitlines()
                if keyword.strip()
            ],
            "min_description_length": min_desc_length,
        }

        config["claude"] = {
            "model": self._widgets["claude_model"].get(),
            "max_tokens": claude_max_tokens,
        }
        config["cover_letter"] = {"auto_generate": self._widgets["auto_cover_letter"].get()}
        config["review"] = {"auto_approve": self._widgets["review_auto_approve"].get()}

        config["notifications"] = {
            "windows_toast": self._widgets["windows_toast"].get(),
            "email": {
                "enabled": self._widgets["email_enabled"].get(),
                "smtp_host": self._get_entry("smtp_host"),
                "smtp_port": smtp_port,
                "from_address": self._get_entry("smtp_from"),
                "to_address": self._get_entry("smtp_to"),
            },
        }

        submission = config.get("submission", {})
        submission["enabled"] = self._widgets["submission_enabled"].get()
        submission["headless"] = self._widgets["submission_headless"].get()
        profile = submission.setdefault("profile", {})
        profile["first_name"] = self._get_entry("first_name")
        profile["last_name"] = self._get_entry("last_name")
        profile["linkedin"] = self._get_entry("linkedin")
        profile["github"] = self._get_entry("github")
        profile["current_company"] = self._get_entry("current_company")
        profile["work_authorization"] = self._get_entry("work_auth")
        profile["requires_sponsorship"] = self._widgets["requires_sponsorship"].get()
        config["submission"] = submission

        config.pop("schedule", None)
        config.setdefault("resumes", self._config.get("resumes", {}))
        config.setdefault("screening", self._config.get("screening", {}))
        config.setdefault("output", self._config.get("output", {}))
        config.setdefault("user_profile", self._config.get("user_profile", {}))

        try:
            save_config(config, self._config_path)
            messagebox.showinfo("Saved", "Settings saved successfully.")
        except Exception as exc:
            messagebox.showerror("Error", f"Could not save settings: {exc}")
            return

        self._config = config
        if self._on_save:
            self._on_save()

    def _open_config(self) -> None:
        self._open_file(resolve_runtime_path(self._config_path, for_write=True))

    def _open_env(self) -> None:
        env_path = resolve_runtime_path(".env", for_write=True)
        if not env_path.exists():
            example_path = resolve_runtime_path(".env.example")
            if example_path.exists():
                shutil.copy2(example_path, env_path)
            else:
                env_path.touch()
        self._open_file(env_path)

    def _open_questions(self) -> None:
        self._open_file(resolve_runtime_path("questions.yaml", for_write=True))

    def _open_file(self, path: Path) -> None:
        try:
            os.startfile(str(path))
        except Exception as exc:
            messagebox.showerror("Open File", f"Could not open {path.name}: {exc}")

    def _section(self, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(self._scroll, fg_color="#1F2937", corner_radius=8)
        card.pack(fill="x", padx=4, pady=(0, 12))
        ctk.CTkLabel(
            card,
            text=title,
            font=("Segoe UI", 13, "bold"),
            text_color="#60A5FA",
        ).pack(anchor="w", padx=14, pady=(10, 4))
        ctk.CTkFrame(card, height=1, fg_color="#374151").pack(fill="x", padx=14, pady=(0, 8))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=(0, 12))
        return inner

    def _register_widget(self, key: str, widget) -> None:
        self._widgets[key] = widget

    def _set_entry(self, key: str, value: str) -> None:
        widget = self._widgets.get(key)
        if isinstance(widget, ctk.CTkEntry):
            widget.delete(0, "end")
            widget.insert(0, value)

    def _get_entry(self, key: str) -> str:
        widget = self._widgets.get(key)
        if isinstance(widget, ctk.CTkEntry):
            return widget.get()
        return ""
