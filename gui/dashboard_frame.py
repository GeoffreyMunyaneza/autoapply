"""
gui/dashboard_frame.py — Dashboard tab.

Shows:
  - 5 stat cards (Total · Queued · Applied · Interviewing · Offers)
  - Run Pipeline / Run + Submit action buttons + progress bar
  - Recent 10 jobs table
"""

from __future__ import annotations
import tkinter as tk
import webbrowser
from pathlib import Path
from typing import Callable, Optional

import customtkinter as ctk

from core.tracker import COLUMNS, STATUS_COLORS


# Status categories for the stat cards
_STAT_GROUPS = {
    "Discovered": (["Discovered", "Pending Review"], "#6B7280"),
    "Queued":     (["Queued"],                        "#10B981"),
    "Applied":    (["Applied"],                       "#3B82F6"),
    "Interviews": (["Interviewing"],                  "#8B5CF6"),
    "Offers":     (["Offer"],                         "#F59E0B"),
}

_STATUS_HEX = {
    "Discovered":     "#78716C",
    "Pending Review": "#D97706",
    "Queued":         "#16A34A",
    "Applied":        "#2563EB",
    "Interviewing":   "#7C3AED",
    "Offer":          "#D97706",
    "Rejected":       "#DC2626",
    "Skipped":        "#6B7280",
}


class StatCard(ctk.CTkFrame):
    """A single stat tile with a large number + label."""

    def __init__(self, parent, label: str, color: str, **kwargs):
        super().__init__(parent, corner_radius=10, border_width=1,
                         border_color="#374151", **kwargs)
        self._count_var = tk.StringVar(value="—")
        ctk.CTkLabel(
            self, textvariable=self._count_var,
            font=("Segoe UI", 28, "bold"), text_color=color,
        ).pack(pady=(14, 2))
        ctk.CTkLabel(
            self, text=label, font=("Segoe UI", 12),
            text_color="#9CA3AF",
        ).pack(pady=(0, 12))

    def set(self, value: int) -> None:
        self._count_var.set(str(value))


class DashboardFrame(ctk.CTkFrame):
    """Dashboard tab — stats, action buttons, recent jobs."""

    def __init__(
        self,
        parent,
        on_run: Callable,
        on_run_submit: Callable,
        tracker_path: str,
        **kwargs,
    ):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._on_run = on_run
        self._on_run_submit = on_run_submit
        self._tracker_path = tracker_path
        self._running = False

        self._build_ui()
        self.refresh()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── Title row ─────────────────────────────────────────────────────────
        title_row = ctk.CTkFrame(self, height=40, fg_color="transparent")
        title_row.pack(fill="x", padx=16, pady=(12, 0))
        ctk.CTkLabel(
            title_row, text="Dashboard", font=("Segoe UI", 18, "bold")
        ).pack(side="left")
        self._last_run_label = ctk.CTkLabel(
            title_row, text="Last run: never", font=("Segoe UI", 12),
            text_color="#9CA3AF",
        )
        self._last_run_label.pack(side="right")

        # ── Stat cards row ────────────────────────────────────────────────────
        cards_row = ctk.CTkFrame(self, fg_color="transparent")
        cards_row.pack(fill="x", padx=16, pady=(12, 0))
        cards_row.columnconfigure(list(range(5)), weight=1, uniform="cards")

        self._cards: dict[str, StatCard] = {}
        for col, (label, (_, color)) in enumerate(_STAT_GROUPS.items()):
            card = StatCard(cards_row, label=label, color=color)
            card.grid(row=0, column=col, padx=5, sticky="nsew")
            self._cards[label] = card

        # ── Action buttons ────────────────────────────────────────────────────
        action_row = ctk.CTkFrame(self, fg_color="transparent")
        action_row.pack(fill="x", padx=16, pady=(16, 0))

        self._run_btn = ctk.CTkButton(
            action_row, text="▶  Run Pipeline",
            width=160, height=38,
            font=("Segoe UI", 13, "bold"),
            command=self._on_run,
        )
        self._run_btn.pack(side="left", padx=(0, 8))

        self._run_submit_btn = ctk.CTkButton(
            action_row, text="▶  Run + Submit",
            width=160, height=38,
            font=("Segoe UI", 13, "bold"),
            fg_color="#7C3AED", hover_color="#6D28D9",
            command=self._on_run_submit,
        )
        self._run_submit_btn.pack(side="left", padx=(0, 16))

        self._status_label = ctk.CTkLabel(
            action_row, text="● Idle",
            font=("Segoe UI", 12), text_color="#10B981",
        )
        self._status_label.pack(side="left")

        # Progress bar (hidden until running)
        self._progress = ctk.CTkProgressBar(
            action_row, width=200, height=12, mode="indeterminate",
        )
        # Don't pack yet — shown when running

        self._cancel_btn = ctk.CTkButton(
            action_row, text="Cancel", width=80, height=38,
            fg_color="#DC2626", hover_color="#B91C1C",
        )
        # Not packed yet

        # ── Separator ─────────────────────────────────────────────────────────
        ctk.CTkFrame(self, height=1, fg_color="#374151").pack(
            fill="x", padx=16, pady=(14, 0)
        )

        # ── Recent matches ────────────────────────────────────────────────────
        ctk.CTkLabel(
            self, text="Recent Matches",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", padx=16, pady=(10, 6))

        # Use ttk.Treeview for the recent jobs table
        import tkinter.ttk as ttk

        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Dashboard.Treeview",
            background="#1F2937",
            foreground="#D1D5DB",
            fieldbackground="#1F2937",
            borderwidth=0,
            rowheight=26,
            font=("Segoe UI", 11),
        )
        style.configure(
            "Dashboard.Treeview.Heading",
            background="#111827",
            foreground="#9CA3AF",
            font=("Segoe UI", 11, "bold"),
            borderwidth=0,
        )
        style.map("Dashboard.Treeview", background=[("selected", "#3B4E6C")])

        frame = ctk.CTkFrame(self, fg_color="#1F2937", corner_radius=8)
        frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        columns = ("title", "company", "score", "status", "date")
        self._tree = ttk.Treeview(
            frame,
            columns=columns,
            show="headings",
            style="Dashboard.Treeview",
            height=10,
            selectmode="browse",
        )
        for col, heading, width in [
            ("title",   "Title",      280),
            ("company", "Company",    160),
            ("score",   "Score",       70),
            ("status",  "Status",     110),
            ("date",    "Date Added", 120),
        ]:
            self._tree.heading(col, text=heading)
            self._tree.column(col, width=width, minwidth=60)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._tree.bind("<Double-1>", self._on_row_double_click)

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Reload stats and recent jobs from the tracker."""
        rows = _load_tracker_rows(self._tracker_path)
        _update_stats(rows, self._cards)
        _populate_recent(rows, self._tree)

    def set_tracker_path(self, tracker_path: str) -> None:
        self._tracker_path = tracker_path
        self.refresh()

    def set_running(self, running: bool) -> None:
        self._running = running
        if running:
            self._run_btn.configure(state="disabled")
            self._run_submit_btn.configure(state="disabled")
            self._status_label.configure(text="● Running…", text_color="#FBBF24")
            self._progress.pack(side="left", padx=(8, 0))
            self._progress.start()
        else:
            self._run_btn.configure(state="normal")
            self._run_submit_btn.configure(state="normal")
            self._status_label.configure(text="● Idle", text_color="#10B981")
            self._progress.stop()
            self._progress.pack_forget()
            self.refresh()

    def set_last_run(self, text: str) -> None:
        self._last_run_label.configure(text=text)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _on_row_double_click(self, event) -> None:
        item = self._tree.focus()
        if not item:
            return
        values = self._tree.item(item, "values")
        # values[4] is date — we need the URL; stored in tag
        tags = self._tree.item(item, "tags")
        for tag in tags:
            if tag.startswith("url:"):
                url = tag[4:]
                if url:
                    webbrowser.open(url)
                return


# ── Data helpers ──────────────────────────────────────────────────────────────

def _load_tracker_rows(tracker_path: str) -> list[dict]:
    """Load all rows from tracker_v2.xlsx as list of dicts."""
    p = Path(tracker_path)
    if not p.exists():
        return []
    try:
        import openpyxl
        wb = openpyxl.load_workbook(tracker_path, read_only=True, data_only=True)
        ws = wb.active
        rows = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row[0]:
                continue
            rows.append(dict(zip(COLUMNS, row)))
        wb.close()
        return rows
    except Exception:
        return []


def _update_stats(rows: list[dict], cards: dict[str, StatCard]) -> None:
    counts: dict[str, int] = {k: 0 for k in _STAT_GROUPS}
    for row in rows:
        status = str(row.get("Status") or "")
        for label, (statuses, _) in _STAT_GROUPS.items():
            if status in statuses:
                counts[label] += 1
    for label, count in counts.items():
        cards[label].set(count)


def _populate_recent(rows: list[dict], tree) -> None:
    for item in tree.get_children():
        tree.delete(item)

    # Sort by Date Added descending, take last 20
    def _date_key(r):
        return str(r.get("Date Added") or "")

    recent = sorted(rows, key=_date_key, reverse=True)[:20]

    for row in recent:
        title   = str(row.get("Title") or "")[:50]
        company = str(row.get("Company") or "")[:30]
        score   = str(row.get("Match Score") or "")
        status  = str(row.get("Status") or "")
        date    = str(row.get("Date Added") or "")[:16]
        url     = str(row.get("URL") or "")

        # Status badge color tag
        tree.insert(
            "", "end",
            values=(title, company, score, status, date),
            tags=(f"url:{url}", f"status:{status}"),
        )
