"""
services/scheduler.py — Background automation scheduler.

Replaces the `schedule` library with APScheduler BackgroundScheduler.
Runs the full pipeline (and optionally auto-submit) on a cron schedule
defined in config.yaml under the `schedule:` key.

Config block expected in config.yaml:
    schedule:
      enabled: true
      cron: "0 */4 * * *"   # every 4 hours (standard cron syntax)
      auto_submit: false     # set true for fully automated apply

Threading contract:
  - APScheduler runs in a daemon thread; the pipeline runs in that thread.
  - GUI callbacks (on_run_start, on_run_done) are called in the scheduler
    thread. GUI code MUST wrap them with window.after(0, ...) — never call
    tkinter widget methods directly from these callbacks.

Usage:
    scheduler = AutoApplyScheduler(
        config_path="config.yaml",
        on_run_start=lambda: window.after(0, window.on_run_start),
        on_run_done=lambda n, e: window.after(0, lambda: window.on_run_done(n, e)),
    )
    scheduler.start()
    scheduler.trigger_now()        # manual immediate run
    scheduler.trigger_now(submit=True)   # manual run + submit
    scheduler.stop()
    scheduler.next_run_time()      # datetime | None
"""

import logging
import os
import threading
from datetime import datetime
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class AutoApplyScheduler:
    """
    Manages scheduled and on-demand pipeline runs.

    Parameters
    ----------
    config_path  : path to config.yaml (re-read on every run — picks up changes)
    on_run_start : callable() — fired when a run begins (in scheduler thread)
    on_run_done  : callable(new_count: int, error: str | None) — fired on completion
    """

    def __init__(
        self,
        config_path: str = "config.yaml",
        on_run_start: Optional[Callable[[], None]] = None,
        on_run_done: Optional[Callable[[int, Optional[str]], None]] = None,
    ):
        self._config_path = config_path
        self._on_run_start = on_run_start
        self._on_run_done = on_run_done
        self._scheduler = None
        self._run_lock = threading.Lock()   # prevent concurrent pipeline runs

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the scheduler. No-op if schedule.enabled=false in config."""
        from services.config import load_config
        config = load_config(self._config_path)
        schedule_cfg = config.get("schedule", {})

        if not schedule_cfg.get("enabled", False):
            logger.info("AutoApply scheduler disabled (schedule.enabled=false).")
            return

        cron_expr   = schedule_cfg.get("cron", "0 */4 * * *")
        auto_submit = schedule_cfg.get("auto_submit", False)

        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
        except ImportError:
            logger.warning("APScheduler not installed — scheduled runs unavailable. "
                           "Run: pip install apscheduler")
            return

        self._scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
        self._scheduler.add_job(
            func=self._run_job,
            trigger=CronTrigger.from_crontab(cron_expr),
            kwargs={"auto_submit": auto_submit},
            id="autoapply_pipeline",
            max_instances=1,   # never overlap two pipeline runs
            coalesce=True,     # skip missed fires (e.g. laptop was asleep)
            replace_existing=True,
        )
        self._scheduler.start()
        next_run = self.next_run_time()
        logger.info(
            f"Scheduler started. Cron: '{cron_expr}'. "
            f"Auto-submit: {auto_submit}. "
            f"Next run: {next_run.strftime('%Y-%m-%d %H:%M') if next_run else 'unknown'}"
        )

    def stop(self) -> None:
        """Gracefully stop the scheduler."""
        if self._scheduler and self._scheduler.running:
            try:
                self._scheduler.shutdown(wait=False)
                logger.info("Scheduler stopped.")
            except Exception as exc:
                logger.debug(f"Scheduler shutdown error: {exc}")

    def reschedule(self) -> None:
        """
        Re-read config.yaml and apply any schedule changes without restarting the app.
        Call this after the user saves new settings.
        """
        self.stop()
        self._scheduler = None
        self.start()

    def trigger_now(self, auto_submit: bool = False) -> None:
        """
        Fire the pipeline immediately in a background thread (bypasses cron).
        Safe to call from GUI or tray menu.
        """
        if self._run_lock.locked():
            logger.info("Pipeline already running — ignoring trigger_now().")
            return
        t = threading.Thread(
            target=self._run_job,
            kwargs={"auto_submit": auto_submit},
            daemon=True,
            name="AutoApplyManualRun",
        )
        t.start()

    def next_run_time(self) -> Optional[datetime]:
        """Return the datetime of the next scheduled run, or None."""
        if not self._scheduler:
            return None
        try:
            job = self._scheduler.get_job("autoapply_pipeline")
            return job.next_run_time if job else None
        except Exception:
            return None

    def is_running(self) -> bool:
        return self._run_lock.locked()

    # ── Core job ──────────────────────────────────────────────────────────────

    def _run_job(self, auto_submit: bool = False) -> None:
        """
        Executed in the scheduler/manual thread.
        Re-reads config + env on every invocation so settings changes take effect.
        NEVER calls tkinter methods directly.
        """
        if not self._run_lock.acquire(blocking=False):
            logger.info("Pipeline already running — skipping this invocation.")
            return

        try:
            from dotenv import load_dotenv
            from services.config import load_config, inject_env
            from services.pipeline import run_pipeline, run_submission_pass

            load_dotenv()
            config  = load_config(self._config_path)
            inject_env(config)
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")

            if self._on_run_start:
                self._on_run_start()

            error: Optional[str] = None
            new_count = 0
            try:
                new_count = run_pipeline(config, api_key)
                if auto_submit:
                    run_submission_pass(config, api_key)
            except Exception as exc:
                error = str(exc)
                logger.error(f"Pipeline run error: {exc}", exc_info=True)

        finally:
            self._run_lock.release()
            if self._on_run_done:
                try:
                    self._on_run_done(new_count, error)
                except Exception as exc:
                    logger.debug(f"on_run_done callback error: {exc}")
