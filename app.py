"""
app.py — AutoApply Windows Desktop App entry point.

Starts:
  1. APScheduler   — background automation (cron-driven pipeline + auto-submit)
  2. System tray   — pystray icon, right-click menu
  3. Main window   — CustomTkinter dashboard (hidden in tray by default)

Launch modes:
  python app.py                 → start in tray (window hidden)
  python app.py --show          → start with window visible
  python app.py --run           → start + immediately trigger one pipeline run
  python app.py --run --submit  → start + pipeline + auto-submit

Headless CLI (no GUI):
  python main.py                → run pipeline once
  python main.py --submit       → run pipeline + submit
"""

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# ── Logging ────────────────────────────────────────────────────────────────────
Path("output").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("output/autoapply.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
for _noisy in ("httpx", "httpcore", "sentence_transformers", "transformers",
               "huggingface_hub", "filelock", "urllib3", "apscheduler"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="AutoApply Desktop")
    parser.add_argument("--show",   action="store_true", help="Show window on launch")
    parser.add_argument("--run",    action="store_true", help="Trigger pipeline immediately")
    parser.add_argument("--submit", action="store_true", help="Also auto-submit when --run is used")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    args = parser.parse_args()

    config_path = args.config
    api_key     = os.environ.get("ANTHROPIC_API_KEY", "")

    if not api_key:
        logger.warning(
            "ANTHROPIC_API_KEY not set — resume tailoring will be skipped. "
            "Add it to .env: ANTHROPIC_API_KEY=sk-ant-..."
        )

    from services.config import load_config, inject_env
    config = load_config(config_path)
    inject_env(config)

    # ── Scheduler ──────────────────────────────────────────────────────────────
    from services.scheduler import AutoApplyScheduler

    # Callbacks are wired to window.after() after window creation (see below)
    scheduler = AutoApplyScheduler(config_path=config_path)

    # ── Main window ────────────────────────────────────────────────────────────
    from gui.main_window import MainWindow

    tray_holder: list = []   # mutable ref for on_quit closure

    def on_quit() -> None:
        scheduler.stop()
        if tray_holder:
            tray_holder[0].stop()

    window = MainWindow(
        config=config,
        api_key=api_key,
        config_path=config_path,
        scheduler=scheduler,
        on_quit=on_quit,
    )

    # Wire scheduler callbacks → window.after() (thread-safe bridge)
    scheduler._on_run_start = lambda: window.after(0, window.on_scheduled_run_start)
    scheduler._on_run_done  = lambda n, e: window.after(0, lambda: window._on_pipeline_done(n, e))

    # ── Tray ───────────────────────────────────────────────────────────────────
    from gui.tray import TrayApp

    tray = TrayApp(
        on_show=lambda: window.after(0, window.toggle),
        on_run=lambda: window.after(0, window._run_pipeline),
        on_run_submit=lambda: window.after(0, window._run_pipeline_and_submit),
        on_quit=lambda: window.after(0, window.quit_app),
    )
    tray.start()
    tray_holder.append(tray)

    # ── Start scheduler (background thread) ────────────────────────────────────
    scheduler.start()

    # ── Show / hide window ─────────────────────────────────────────────────────
    if args.show:
        window.show()
    else:
        window.withdraw()   # live in tray by default

    # ── Optional immediate run ─────────────────────────────────────────────────
    if args.run:
        window.after(800, lambda: scheduler.trigger_now(auto_submit=args.submit))

    logger.info("AutoApply Desktop started. Right-click tray icon to interact.")
    window.mainloop()


if __name__ == "__main__":
    main()
