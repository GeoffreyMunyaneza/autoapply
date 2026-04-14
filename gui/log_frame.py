"""
gui/log_frame.py — Live log viewer tab.

Polls a queue for log lines and appends them to a scrollable text widget.
Lines are color-coded: INFO=white, WARNING=yellow, ERROR=red.
"""

from __future__ import annotations
import tkinter as tk
import queue
from typing import Optional

import customtkinter as ctk


# Text tag colors per log level
_LEVEL_COLORS = {
    "DEBUG":    "#6B7280",
    "INFO":     "#D1D5DB",
    "WARNING":  "#FBBF24",
    "ERROR":    "#F87171",
    "CRITICAL": "#EF4444",
}


class LogFrame(ctk.CTkFrame):
    """
    Tab content for live log streaming.
    Call attach_queue(q) to start reading from a PipelineRunner's log_queue.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._queue: Optional[queue.Queue] = None
        self._auto_scroll = tk.BooleanVar(value=True)
        self._polling = False
        self._build_ui()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Toolbar
        toolbar = ctk.CTkFrame(self, height=36, fg_color="transparent")
        toolbar.pack(fill="x", padx=12, pady=(8, 4))

        ctk.CTkLabel(toolbar, text="Pipeline Logs", font=("Segoe UI", 15, "bold")).pack(
            side="left"
        )

        ctk.CTkButton(
            toolbar, text="Clear", width=70, height=28,
            command=self._clear,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            toolbar, text="Copy All", width=80, height=28,
            command=self._copy_all,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            toolbar, text="Save", width=60, height=28,
            command=self._save_log,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkCheckBox(
            toolbar, text="Auto-scroll", variable=self._auto_scroll,
            width=110, height=28,
        ).pack(side="right", padx=(6, 0))

        # Text area
        self._textbox = ctk.CTkTextbox(
            self,
            font=("Consolas", 12),
            wrap="none",
            activate_scrollbars=True,
            state="disabled",
        )
        self._textbox.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # Configure color tags via the underlying tk.Text widget
        text_widget: tk.Text = self._textbox._textbox
        for level, color in _LEVEL_COLORS.items():
            text_widget.tag_configure(level, foreground=color)

    # ── Public API ────────────────────────────────────────────────────────────

    def attach_queue(self, log_queue: queue.Queue) -> None:
        """Start polling log_queue for ('log', level, text) tuples."""
        self._queue = log_queue
        if not self._polling:
            self._polling = True
            self._poll()

    def detach_queue(self) -> None:
        self._queue = None
        self._polling = False

    def append_line(self, level: str, text: str) -> None:
        """Append a colored line to the log."""
        tag = level if level in _LEVEL_COLORS else "INFO"
        tw: tk.Text = self._textbox._textbox
        self._textbox.configure(state="normal")
        tw.insert("end", text + "\n", tag)
        self._textbox.configure(state="disabled")
        if self._auto_scroll.get():
            tw.see("end")

    def clear(self) -> None:
        self._clear()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _poll(self) -> None:
        """Poll the queue every 100 ms and flush lines to the text widget."""
        if not self._polling:
            return
        if self._queue:
            try:
                while True:
                    item = self._queue.get_nowait()
                    if item[0] == "log":
                        _, level, text = item
                        self.append_line(level, text)
            except queue.Empty:
                pass
        self.after(100, self._poll)

    def _clear(self) -> None:
        self._textbox.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self._textbox.configure(state="disabled")

    def _copy_all(self) -> None:
        text = self._textbox._textbox.get("1.0", "end")
        self.clipboard_clear()
        self.clipboard_append(text)

    def _save_log(self) -> None:
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile="autoapply_log.txt",
            title="Save Log",
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._textbox._textbox.get("1.0", "end"))
