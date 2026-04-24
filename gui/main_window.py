"""
Main application window for the AutoApply desktop app.
"""

from __future__ import annotations

import queue
import threading
from datetime import datetime
import os
from pathlib import Path
from typing import Callable, Optional

import customtkinter as ctk
from dotenv import load_dotenv

from services.config import load_runtime_config, resolve_runtime_path

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

NAV_ITEMS = ["Dashboard", "Jobs", "Logs", "Settings"]
NAV_ICONS = {"Dashboard": "D", "Jobs": "J", "Logs": "L", "Settings": "S"}
APP_VERSION = "2.0"


class MainWindow(ctk.CTk):
    """Desktop window hosting the dashboard, jobs, logs, and settings views."""

    def __init__(
        self,
        config: dict,
        api_key: str,
        config_path: str = "config.yaml",
        on_quit: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__()
        self._config = config
        self._api_key = api_key
        self._config_path = config_path
        self._on_quit = on_quit

        self._runner: Optional[threading.Thread] = None
        self._log_queue: Optional[queue.Queue] = None

        tracker_path = config.get("output", {}).get(
            "tracker_file",
            str(resolve_runtime_path("output/tracker_v2.xlsx", for_write=True)),
        )
        self._tracker_path = str(Path(tracker_path))

        self._setup_window()
        self._build_sidebar()
        self._build_content()
        self._navigate("Dashboard")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_window(self) -> None:
        self.title("AutoApply")
        self.geometry("1150x720")
        self.minsize(900, 580)
        try:
            from gui.tray import _make_icon_image
            import io
            from tkinter import PhotoImage

            image = _make_icon_image()
            if image:
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                buffer.seek(0)
                self._icon_img = PhotoImage(data=buffer.read())
                self.iconphoto(True, self._icon_img)
        except Exception:
            pass

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(self, width=180, corner_radius=0, fg_color="#111827")
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        logo_row = ctk.CTkFrame(sidebar, fg_color="transparent", height=60)
        logo_row.pack(fill="x", padx=12, pady=(16, 4))
        ctk.CTkLabel(
            logo_row,
            text="AutoApply",
            font=("Segoe UI", 16, "bold"),
            text_color="#60A5FA",
        ).pack(side="left")
        ctk.CTkLabel(
            logo_row,
            text=f"v{APP_VERSION}",
            font=("Segoe UI", 10),
            text_color="#6B7280",
        ).pack(side="left", padx=(4, 0), pady=(4, 0))

        ctk.CTkFrame(sidebar, height=1, fg_color="#374151").pack(fill="x", padx=10, pady=(0, 8))

        self._nav_btns: dict[str, ctk.CTkButton] = {}
        for label in NAV_ITEMS:
            icon = NAV_ICONS.get(label, "-")
            button = ctk.CTkButton(
                sidebar,
                text=f"  {icon}  {label}",
                anchor="w",
                height=38,
                corner_radius=6,
                fg_color="transparent",
                hover_color="#1F2937",
                text_color="#9CA3AF",
                font=("Segoe UI", 13),
                command=lambda current=label: self._navigate(current),
            )
            button.pack(fill="x", padx=8, pady=2)
            self._nav_btns[label] = button

        ctk.CTkFrame(sidebar, fg_color="transparent").pack(fill="both", expand=True)

        self._sidebar_run_btn = ctk.CTkButton(
            sidebar,
            text="Run Pipeline",
            height=36,
            corner_radius=6,
            fg_color="#1D4ED8",
            hover_color="#1E40AF",
            font=("Segoe UI", 12, "bold"),
            command=self._run_pipeline,
        )
        self._sidebar_run_btn.pack(fill="x", padx=8, pady=(0, 8))

        self._sidebar_status = ctk.CTkLabel(
            sidebar,
            text="Idle",
            font=("Segoe UI", 11),
            text_color="#10B981",
        )
        self._sidebar_status.pack(pady=(0, 12))

    def _build_content(self) -> None:
        self._content = ctk.CTkFrame(self, corner_radius=0, fg_color="#0F172A")
        self._content.grid(row=0, column=1, sticky="nsew")
        self._content.grid_rowconfigure(0, weight=1)
        self._content.grid_columnconfigure(0, weight=1)

        from gui.dashboard_frame import DashboardFrame
        from gui.jobs_frame import JobsFrame
        from gui.log_frame import LogFrame
        from gui.settings_frame import SettingsFrame

        self._frames: dict[str, ctk.CTkFrame] = {
            "Dashboard": DashboardFrame(
                self._content,
                on_run=self._run_pipeline,
                on_run_submit=self._run_pipeline_and_submit,
                tracker_path=self._tracker_path,
            ),
            "Jobs": JobsFrame(self._content, tracker_path=self._tracker_path),
            "Logs": LogFrame(self._content),
            "Settings": SettingsFrame(
                self._content,
                config_path=self._config_path,
                on_save=self._on_settings_saved,
            ),
        }

        for frame in self._frames.values():
            frame.grid(row=0, column=0, sticky="nsew")

    def _navigate(self, label: str) -> None:
        for name, button in self._nav_btns.items():
            active = name == label
            button.configure(
                fg_color="#1F2937" if active else "transparent",
                text_color="#FFFFFF" if active else "#9CA3AF",
            )
        self._frames[label].tkraise()

    def _on_settings_saved(self) -> None:
        self._reload_runtime_config()
        self._frames["Dashboard"].refresh()
        self._frames["Jobs"].refresh()

    def _run_pipeline(self) -> None:
        self._start_pipeline_run(submit=False)

    def _run_pipeline_and_submit(self) -> None:
        self._start_pipeline_run(submit=True)

    def _start_pipeline_run(self, submit: bool) -> None:
        if self._runner and self._runner.is_alive():
            return

        self._reload_runtime_config()

        from gui.runner import PipelineRunner

        self._runner = PipelineRunner(
            config=self._config,
            api_key=self._api_key,
            submit=submit,
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

    def _handle_done(self, new_count: int, error: Optional[str]) -> None:
        self._set_running(False)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        message = f"Last run: {timestamp}"
        if error:
            message += f" - warning: {error[:60]}"
        else:
            message += f" - {new_count} new job{'s' if new_count != 1 else ''}"

        self._frames["Dashboard"].set_last_run(message)
        self._frames["Dashboard"].refresh()
        self._frames["Jobs"].refresh()
        self._runner = None

    def _reload_runtime_config(self) -> None:
        try:
            load_dotenv(dotenv_path=resolve_runtime_path(".env"))
            self._config = load_runtime_config(self._config_path, with_env=True)
            self._api_key = os.environ.get("ANTHROPIC_API_KEY", "")

            tracker_path = str(
                self._config.get("output", {}).get(
                    "tracker_file",
                    resolve_runtime_path("output/tracker_v2.xlsx", for_write=True),
                )
            )
            if tracker_path != self._tracker_path:
                self._tracker_path = tracker_path
                self._frames["Dashboard"].set_tracker_path(tracker_path)
                self._frames["Jobs"].set_tracker_path(tracker_path)
        except Exception:
            pass

    def _set_running(self, running: bool) -> None:
        self._frames["Dashboard"].set_running(running)
        if running:
            self._sidebar_run_btn.configure(state="disabled", text="Running...")
            self._sidebar_status.configure(text="Running", text_color="#FBBF24")
        else:
            self._sidebar_run_btn.configure(state="normal", text="Run Pipeline")
            self._sidebar_status.configure(text="Idle", text_color="#10B981")

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
