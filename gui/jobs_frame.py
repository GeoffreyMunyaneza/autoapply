"""
gui/jobs_frame.py — Full jobs browser tab.

Reads from output/tracker_v2.xlsx and renders a sortable, filterable
Treeview table. Right-click or toolbar buttons open URLs, resumes, etc.
"""

from __future__ import annotations
import os
import subprocess
import tkinter as tk
import tkinter.ttk as ttk
import webbrowser
from pathlib import Path
from typing import Optional

import customtkinter as ctk

from core.tracker import COLUMNS


_DISPLAY_COLS = [
    ("Title",       "Title",       280),
    ("Company",     "Company",     160),
    ("Match Score", "Score",        70),
    ("Status",      "Status",      110),
    ("Source",      "Source",       90),
    ("Resume Type", "Type",         55),
    ("Date Added",  "Date Added",  120),
    ("Location",    "Location",    130),
]

_STATUS_OPTIONS = [
    "All",
    "Discovered", "Pending Review", "Queued", "Applied",
    "Interviewing", "Offer", "Rejected", "Skipped",
]
_SOURCE_OPTIONS = ["All", "linkedin", "indeed", "zip_recruiter", "glassdoor",
                   "google", "dice", "remoteok", "wellfound"]
_TYPE_OPTIONS   = ["All", "ML", "PM"]


class JobsFrame(ctk.CTkFrame):
    """Full jobs browser — filter bar + sortable table + context menu."""

    def __init__(self, parent, tracker_path: str, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._tracker_path = tracker_path
        self._all_rows: list[dict] = []
        self._filtered: list[dict] = []
        self._sort_col: Optional[str] = None
        self._sort_rev = False

        self._build_ui()
        self.refresh()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Title + refresh
        hdr = ctk.CTkFrame(self, height=40, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(12, 0))
        ctk.CTkLabel(hdr, text="Jobs", font=("Segoe UI", 18, "bold")).pack(side="left")
        ctk.CTkButton(
            hdr, text="⟳ Refresh", width=90, height=28, command=self.refresh,
        ).pack(side="right", padx=(6, 0))
        ctk.CTkButton(
            hdr, text="Open in Excel", width=110, height=28,
            command=self._open_excel,
        ).pack(side="right", padx=(6, 0))
        ctk.CTkButton(
            hdr, text="Export CSV", width=95, height=28,
            command=self._export_csv,
        ).pack(side="right", padx=(6, 0))

        # Filter bar
        filter_bar = ctk.CTkFrame(self, height=36, fg_color="transparent")
        filter_bar.pack(fill="x", padx=16, pady=(8, 4))

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filters())
        ctk.CTkEntry(
            filter_bar, textvariable=self._search_var,
            placeholder_text="Search title / company…",
            width=220, height=30,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkLabel(filter_bar, text="Status:", text_color="#9CA3AF").pack(side="left")
        self._status_var = tk.StringVar(value="All")
        ctk.CTkOptionMenu(
            filter_bar, variable=self._status_var,
            values=_STATUS_OPTIONS, width=130, height=30,
            command=lambda _: self._apply_filters(),
        ).pack(side="left", padx=(4, 8))

        ctk.CTkLabel(filter_bar, text="Source:", text_color="#9CA3AF").pack(side="left")
        self._source_var = tk.StringVar(value="All")
        ctk.CTkOptionMenu(
            filter_bar, variable=self._source_var,
            values=_SOURCE_OPTIONS, width=120, height=30,
            command=lambda _: self._apply_filters(),
        ).pack(side="left", padx=(4, 8))

        ctk.CTkLabel(filter_bar, text="Type:", text_color="#9CA3AF").pack(side="left")
        self._type_var = tk.StringVar(value="All")
        ctk.CTkOptionMenu(
            filter_bar, variable=self._type_var,
            values=_TYPE_OPTIONS, width=80, height=30,
            command=lambda _: self._apply_filters(),
        ).pack(side="left", padx=(4, 8))

        self._count_label = ctk.CTkLabel(
            filter_bar, text="", font=("Segoe UI", 11), text_color="#9CA3AF",
        )
        self._count_label.pack(side="right")

        # Table style
        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "Jobs.Treeview",
            background="#1F2937",
            foreground="#D1D5DB",
            fieldbackground="#1F2937",
            borderwidth=0,
            rowheight=24,
            font=("Segoe UI", 11),
        )
        style.configure(
            "Jobs.Treeview.Heading",
            background="#111827",
            foreground="#9CA3AF",
            font=("Segoe UI", 11, "bold"),
            borderwidth=0,
            relief="flat",
        )
        style.map("Jobs.Treeview", background=[("selected", "#3B4E6C")])

        # Table container
        frame = ctk.CTkFrame(self, fg_color="#1F2937", corner_radius=8)
        frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        col_ids = [c[0] for c in _DISPLAY_COLS]
        self._tree = ttk.Treeview(
            frame, columns=col_ids, show="headings",
            style="Jobs.Treeview", selectmode="extended",
        )
        for col_id, heading, width in _DISPLAY_COLS:
            self._tree.heading(
                col_id, text=heading,
                command=lambda c=col_id: self._sort_by(c),
            )
            self._tree.column(col_id, width=width, minwidth=50)

        vsb = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        hsb.pack(side="bottom", fill="x")
        vsb.pack(side="right",  fill="y")
        self._tree.pack(fill="both", expand=True)

        # Context menu
        self._menu = tk.Menu(self._tree, tearoff=0, bg="#1F2937", fg="#D1D5DB",
                             activebackground="#3B4E6C")
        self._menu.add_command(label="Open URL in Browser", command=self._open_url)
        self._menu.add_command(label="Open Resume (.docx)",  command=self._open_resume)
        self._menu.add_command(label="Open Cover Letter",    command=self._open_cover)
        self._menu.add_separator()
        status_menu = tk.Menu(self._menu, tearoff=0, bg="#1F2937", fg="#D1D5DB",
                              activebackground="#3B4E6C")
        for s in _STATUS_OPTIONS[1:]:
            status_menu.add_command(
                label=s, command=lambda st=s: self._change_status(st)
            )
        self._menu.add_cascade(label="Change Status →", menu=status_menu)
        self._menu.add_separator()
        self._menu.add_command(label="Copy URL", command=self._copy_url)

        self._tree.bind("<Button-3>", self._show_context_menu)
        self._tree.bind("<Double-1>", lambda e: self._open_url())

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        self._all_rows = _load_rows(self._tracker_path)
        self._apply_filters()

    # ── Filtering + sorting ───────────────────────────────────────────────────

    def _apply_filters(self) -> None:
        search  = self._search_var.get().lower()
        status  = self._status_var.get()
        source  = self._source_var.get()
        rtype   = self._type_var.get()

        filtered = []
        for row in self._all_rows:
            if status != "All" and row.get("Status") != status:
                continue
            if source != "All" and row.get("Source", "").lower() != source.lower():
                continue
            if rtype != "All" and row.get("Resume Type", "").upper() != rtype.upper():
                continue
            if search:
                haystack = (
                    str(row.get("Title", "")) + " " + str(row.get("Company", ""))
                ).lower()
                if search not in haystack:
                    continue
            filtered.append(row)

        self._filtered = filtered
        if self._sort_col:
            self._filtered.sort(
                key=lambda r: str(r.get(self._sort_col) or "").lower(),
                reverse=self._sort_rev,
            )

        self._repopulate()
        self._count_label.configure(
            text=f"Showing {len(filtered):,} of {len(self._all_rows):,} jobs"
        )

    def _sort_by(self, col_id: str) -> None:
        if self._sort_col == col_id:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col_id
            self._sort_rev = False
        self._apply_filters()

    def _repopulate(self) -> None:
        for item in self._tree.get_children():
            self._tree.delete(item)
        for row in self._filtered:
            vals = tuple(
                str(row.get(col_id, "") or "")[:80]
                for col_id, *_ in _DISPLAY_COLS
            )
            self._tree.insert("", "end", values=vals)

    # ── Row actions ───────────────────────────────────────────────────────────

    def _selected_row(self) -> Optional[dict]:
        items = self._tree.selection()
        if not items:
            return None
        idx = self._tree.index(items[0])
        if idx < len(self._filtered):
            return self._filtered[idx]
        return None

    def _open_url(self) -> None:
        row = self._selected_row()
        if row:
            url = str(row.get("URL") or "")
            if url:
                webbrowser.open(url)

    def _open_resume(self) -> None:
        row = self._selected_row()
        if row:
            path = str(row.get("Resume Path") or "")
            if path and Path(path).exists():
                os.startfile(path)

    def _open_cover(self) -> None:
        row = self._selected_row()
        if row:
            resume = str(row.get("Resume Path") or "")
            if resume:
                cl = Path(resume).with_suffix(".cover_letter.txt")
                if cl.exists():
                    os.startfile(str(cl))

    def _copy_url(self) -> None:
        row = self._selected_row()
        if row:
            url = str(row.get("URL") or "")
            self.clipboard_clear()
            self.clipboard_append(url)

    def _change_status(self, new_status: str) -> None:
        row = self._selected_row()
        if row:
            job_id = str(row.get("ID") or "")
            from core.tracker import update_status
            if update_status(self._tracker_path, job_id, new_status):
                self.refresh()

    def _show_context_menu(self, event) -> None:
        item = self._tree.identify_row(event.y)
        if item:
            self._tree.selection_set(item)
            self._menu.post(event.x_root, event.y_root)

    def _open_excel(self) -> None:
        p = Path(self._tracker_path)
        if p.exists():
            os.startfile(str(p))

    def _export_csv(self) -> None:
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="autoapply_export.csv",
            title="Export Jobs to CSV",
        )
        if not path:
            return
        import csv
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerows(self._filtered)


# ── Data helper ───────────────────────────────────────────────────────────────

def _load_rows(tracker_path: str) -> list[dict]:
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
