"""
gui/main_window.py — AutoApply main application window.

Layout:
  ┌────────────┬──────────────────────────────────┐
  │  Sidebar   │  Content area (swappable frames)  │
  │  (180px)   │                                   │
  └────────────┴──────────────────────────────────┘

Navigation: Dashboard · Jobs · Logs · Settings
"""

from __future__ import annotations
import os
import queue
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import customtkinter as ctk

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

_NAV_ITEMS  = ["Dashboard", "Jobs", "Logs", "Settings"]
_NAV_ICONS  = {"Dashboard": "⊞", "Jobs": "☰", "Logs": "≡", "Settings": "⚙"}
APP_VERSION = "2.0"


class MainWindow(ctk.CTk):
    """
    The main AutoApply desktop window.

    Integrates with AutoApplyScheduler for automatic pipeline runs.
    All scheduler callbacks arrive via window.after() — tkinter-safe.

    Parameters
    ----------
    config       : dict — loaded from config.yaml
    api_key      : str  — ANTHROPIC_API_KEY
    config_path  : str  — path to config.yaml
    scheduler    : AutoApplyScheduler | None — starts automation countdown
    on_quit      : Callable — called when the user actually quits
    """

    def __init__(
        self,
        config: dict,
        api_key: str,
        config_path: str = "config.yaml",
        scheduler=None,
        on_quit: Optional[Callable] = None,
    ):
        super().__init__()
        self._config      = config
        self._api_key     = api_key
        self._config_path = config_path
        self._scheduler   = scheduler
        self._on_quit     = on_quit

        self._runner: Optional[threading.Thread] = None
        self._log_queue: Optional[queue.Queue]   = None

        tracker_path = config.get("output", {}).get("tracker_file", "output/tracker_v2.xlsx")
        self._tracker_path = str(Path(tracker_path).resolve())

        self._setup_window()
        self._build_sidebar()
        self._build_content()
        self._navigate("Dashboard")

        # Start the next-run countdown ticker (updates every 30 s)
        self._tick_countdown()

        # Intercept close → minimize to tray
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Window setup ──────────────────────────────────────────────────────────

    def _setup_window(self) -> None:
        self.title("AutoApply")
        self.geometry("1150x720")
        self.minsize(900, 580)
        try:
            from gui.tray import _make_icon_image
            import io
            img = _make_icon_image()
            if img:
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                buf.seek(0)
                from tkinter import PhotoImage
                self._icon_img = PhotoImage(data=buf.read())
                self.iconphoto(True, self._icon_img)
        except Exception:
            pass
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

    # ── Sidebar ───────────────────────────────────────────────────────────────

    def _build_sidebar(self) -> None:
        sb = ctk.CTkFrame(self, width=180, corner_radius=0, fg_color="#111827")
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)

        # Logo
        logo_row = ctk.CTkFrame(sb, fg_color="transparent", height=60)
        logo_row.pack(fill="x", padx=12, pady=(16, 4))
        ctk.CTkLabel(logo_row, text="AutoApply",
                     font=("Segoe UI", 16, "bold"), text_color="#60A5FA").pack(side="left")
        ctk.CTkLabel(logo_row, text=f"v{APP_VERSION}",
                     font=("Segoe UI", 10), text_color="#6B7280").pack(side="left", padx=(4, 0), pady=(4, 0))

        ctk.CTkFrame(sb, height=1, fg_color="#374151").pack(fill="x", padx=10, pady=(0, 8))

        # Nav
        self._nav_btns: dict[str, ctk.CTkButton] = {}
        for label in _NAV_ITEMS:
            icon = _NAV_ICONS.get(label, "•")
            btn = ctk.CTkButton(
                sb, text=f"  {icon}  {label}", anchor="w", height=38,
                corner_radius=6, fg_color="transparent", hover_color="#1F2937",
                text_color="#9CA3AF", font=("Segoe UI", 13),
                command=lambda lbl=label: self._navigate(lbl),
            )
            btn.pack(fill="x", padx=8, pady=2)
            self._nav_btns[label] = btn

        ctk.CTkFrame(sb, fg_color="transparent").pack(fill="both", expand=True)

        # Automation countdown
        ctk.CTkFrame(sb, height=1, fg_color="#374151").pack(fill="x", padx=10, pady=(0, 6))
        self._countdown_label = ctk.CTkLabel(
            sb, text="Next run: —",
            font=("Segoe UI", 10), text_color="#6B7280", wraplength=160,
        )
        self._countdown_label.pack(pady=(0, 4))

        # Run + status
        self._sidebar_run_btn = ctk.CTkButton(
            sb, text="▶  Run Pipeline", height=36, corner_radius=6,
            fg_color="#1D4ED8", hover_color="#1E40AF",
            font=("Segoe UI", 12, "bold"),
            command=self._run_pipeline,
        )
        self._sidebar_run_btn.pack(fill="x", padx=8, pady=(0, 8))

        self._sidebar_status = ctk.CTkLabel(
            sb, text="● Idle", font=("Segoe UI", 11), text_color="#10B981",
        )
        self._sidebar_status.pack(pady=(0, 12))

    # ── Content area ──────────────────────────────────────────────────────────

    def _build_content(self) -> None:
        self._content = ctk.CTkFrame(self, corner_radius=0, fg_color="#0F172A")
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.grid_rowconfigure(0, weight=1)
        self._content.grid_columnconfigure(0, weight=1)

        from gui.dashboard_frame import DashboardFrame
        from gui.jobs_frame      import JobsFrame
        from gui.log_frame       import LogFrame
        from gui.settings_frame  import SettingsFrame

        self._frames: dict[str, ctk.CTkFrame] = {
            "Dashboard": DashboardFrame(
                self._content,
                on_run=self._run_pipeline,
                on_run_submit=self._run_pipeline_and_submit,
                tracker_path=self._tracker_path,
            ),
            "Jobs": JobsFrame(self._content, tracker_path=self._tracker_path),
            "Logs": LogFrame(self._content),
            "Settings": SettingsFrame(self._content, config_path=self._config_path,
                                      on_save=self._on_settings_saved),
        }
        for frame in self._frames.values():
            frame.grid(row=0, column=0, sticky="nsew")

    # ── Navigation ────────────────────────────────────────────────────────────

    def _navigate(self, label: str) -> None:
        for name, btn in self._nav_btns.items():
            active = (name == label)
            btn.configure(
                fg_color="#1F2937" if active else "transparent",
                text_color="#FFFFFF" if active else "#9CA3AF",
            )
        self._frames[label].tkraise()

    # ── Scheduler integration ─────────────────────────────────────────────────

    def on_scheduled_run_start(self) -> None:
        """Called by AutoApplyScheduler (via window.after). Marks UI as running."""
        self._set_running(True)

    def _tick_countdown(self) -> None:
        """Update the 'Next run' label every 30 seconds."""
        if self._scheduler:
            nxt = self._scheduler.next_run_time()
            if nxt:
                delta = nxt - datetime.now(tz=nxt.tzinfo)
                total_s = int(delta.total_seconds())
                if total_s > 0:
                    h, rem = divmod(total_s, 3600)
                    m, s = divmod(rem, 60)
                    label = f"Next run: {h:02d}:{m:02d}:{s:02d}"
                else:
                    label = "Next run: soon"
                self._countdown_label.configure(text=label, text_color="#60A5FA")
            else:
                self._countdown_label.configure(text="Scheduler: off", text_color="#6B7280")
        self.after(30_000, self._tick_countdown)

    def _on_settings_saved(self) -> None:
        """Called after user saves settings — reschedule if cron changed."""
        if self._scheduler:
            self._scheduler.reschedule()

    # ── Pipeline execution ────────────────────────────────────────────────────

    def _run_pipeline(self) -> None:
        if self._scheduler and not self._scheduler.is_running():
            self._set_running(True)
            self._scheduler.trigger_now(auto_submit=False)
        else:
            self._start_gui_runner(submit=False)

    def _run_pipeline_and_submit(self) -> None:
        if self._scheduler and not self._scheduler.is_running():
            self._set_running(True)
            self._scheduler.trigger_now(auto_submit=True)
        else:
            self._start_gui_runner(submit=True)

    def _start_gui_runner(self, submit: bool = False) -> None:
        """Fallback: run pipeline via GUI runner thread (used when scheduler is off)."""
        if self._runner and self._runner.is_alive():
            return

        try:
            import yaml, os as _os
            from dotenv import load_dotenv
            load_dotenv()
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f)
            self._api_key = _os.environ.get("ANTHROPIC_API_KEY", "")
        except Exception:
            pass

        from gui.runner import PipelineRunner
        self._runner = PipelineRunner(
            config=self._config,
            api_key=self._api_key,
            submit=submit,
            on_done=self._on_pipeline_done,
        )
        self._log_queue = self._runner.log_queue
        self._frames["Logs"].attach_queue(self._log_queue)
        self._set_running(True)
        self._runner.start()
        self._poll_runner()

    def _poll_runner(self) -> None:
        if self._log_queue is None:
            return
        try:
            while True:
                item = self._log_queue.get_nowait()
                if item[0] == "done":
                    _, new_count, error = item
                    self._handle_done(new_count, error)
                    return
        except queue.Empty:
            pass
        self.after(200, self._poll_runner)

    def _on_pipeline_done(self, new_count: int, error: Optional[str]) -> None:
        """Scheduler/runner callback — always routed through after() for thread safety."""
        self.after(0, lambda: self._handle_done(new_count, error))

    def _handle_done(self, new_count: int, error: Optional[str]) -> None:
        self._set_running(False)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        msg = f"Last run: {now}"
        if error:
            msg += f" — ⚠ {error[:60]}"
        elif new_count is not None:
            msg += f" — {new_count} new job{'s' if new_count != 1 else ''}"
        self._frames["Dashboard"].set_last_run(msg)
        self._frames["Dashboard"].refresh()
        self._frames["Jobs"].refresh()

    def _set_running(self, running: bool) -> None:
        self._frames["Dashboard"].set_running(running)
        if running:
            self._sidebar_run_btn.configure(state="disabled", text="⏳ Running…")
            self._sidebar_status.configure(text="● Running", text_color="#FBBF24")
        else:
            self._sidebar_run_btn.configure(state="normal", text="▶  Run Pipeline")
            self._sidebar_status.configure(text="● Idle", text_color="#10B981")

    # ── Window management ─────────────────────────────────────────────────────

    def _on_close(self) -> None:
        self.withdraw()

    def show(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def hide(self) -> None:
        self.withdraw()

    def toggle(self) -> None:
        if self.winfo_viewable():
            self.hide()
        else:
            self.show()

    def quit_app(self) -> None:
        if self._on_quit:
            self._on_quit()
        self.destroy()
