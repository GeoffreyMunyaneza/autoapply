"""
Desktop entry point for the AutoApply GUI.

Launch modes:
  python app.py                 -> start in tray with the window hidden
  python app.py --show          -> start with the window visible
  python app.py --run           -> start and trigger one pipeline run
  python app.py --run --submit  -> start and trigger run + submit
"""

import argparse
import logging
import os
import sys

from dotenv import load_dotenv

from services.config import load_runtime_config, resolve_runtime_path

LOG_PATH = resolve_runtime_path("output/autoapply.log", for_write=True)
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

for noisy_logger in (
    "httpx",
    "httpcore",
    "sentence_transformers",
    "transformers",
    "huggingface_hub",
    "filelock",
    "urllib3",
):
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv(dotenv_path=resolve_runtime_path(".env"))

    parser = argparse.ArgumentParser(description="AutoApply Desktop")
    parser.add_argument("--show", action="store_true", help="Show window on launch")
    parser.add_argument("--run", action="store_true", help="Trigger pipeline immediately")
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Also auto-submit when --run is used",
    )
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument(
        "--install-browsers",
        action="store_true",
        help="Install Playwright browser engines and exit",
    )
    args = parser.parse_args()

    if args.install_browsers:
        from install_browsers import install_chromium

        success = install_chromium(silent=False)
        sys.exit(0 if success else 1)

    try:
        from install_browsers import ensure_chromium

        ensure_chromium(silent=True)
    except Exception:
        pass

    config = load_runtime_config(args.config, with_env=True)
    config_path = str(resolve_runtime_path(args.config, for_write=True))
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if not api_key:
        logger.warning(
            "ANTHROPIC_API_KEY not set - resume tailoring will be skipped. "
            "Add it to .env as ANTHROPIC_API_KEY=..."
        )

    from gui.main_window import MainWindow
    from gui.tray import TrayApp

    tray_holder: list[TrayApp] = []

    def on_quit() -> None:
        if tray_holder:
            tray_holder[0].stop()

    window = MainWindow(
        config=config,
        api_key=api_key,
        config_path=config_path,
        on_quit=on_quit,
    )

    tray = TrayApp(
        on_show=lambda: window.after(0, window.toggle),
        on_run=lambda: window.after(0, window._run_pipeline),
        on_run_submit=lambda: window.after(0, window._run_pipeline_and_submit),
        on_quit=lambda: window.after(0, window.quit_app),
    )
    tray.start()
    tray_holder.append(tray)

    if args.show:
        window.show()
    else:
        window.withdraw()

    if args.run:
        window.after(800, window._run_pipeline_and_submit if args.submit else window._run_pipeline)

    logger.info("AutoApply Desktop started. Right-click tray icon to interact.")
    window.mainloop()


if __name__ == "__main__":
    main()
