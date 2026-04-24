"""
main.py - AutoApply headless CLI entry point.

Usage:
  python main.py
  python main.py --submit
  python main.py --config path/to/config.yaml
"""

import argparse
import io
import logging
import os
import sys

from dotenv import load_dotenv

from services.config import load_runtime_config, resolve_runtime_path


LOG_PATH = resolve_runtime_path("output/autoapply.log", for_write=True)
NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "sentence_transformers",
    "transformers",
    "huggingface_hub",
    "filelock",
    "urllib3",
)


def _configure_logging() -> logging.Logger:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_PATH, encoding="utf-8"),
        ],
    )

    root_logger = logging.getLogger()
    if root_logger.handlers and hasattr(root_logger.handlers[0], "stream") and hasattr(sys.stdout, "buffer"):
        root_logger.handlers[0].stream = io.TextIOWrapper(
            sys.stdout.buffer,
            encoding="utf-8",
            errors="replace",
            line_buffering=True,
        )

    for logger_name in NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    return logging.getLogger(__name__)


logger = _configure_logging()


def _warm_screening_answers(config: dict) -> None:
    questions_file = config.get("screening", {}).get("questions_file", "questions.yaml")
    try:
        from core.submitter import _load_yaml_answers

        _load_yaml_answers(questions_file)
    except Exception:
        pass


def main() -> None:
    load_dotenv(dotenv_path=resolve_runtime_path(".env"))

    parser = argparse.ArgumentParser(description="AutoApply CLI")
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Submit queued applications after the discovery pass",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config.yaml",
    )
    args = parser.parse_args()

    from services.pipeline import run_pipeline, run_submission_pass

    config = load_runtime_config(args.config, with_env=True)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if not api_key:
        logger.warning(
            "ANTHROPIC_API_KEY not found; resume tailoring will be skipped.\n"
            "Add it to .env as ANTHROPIC_API_KEY=sk-ant-..."
        )

    _warm_screening_answers(config)

    try:
        run_pipeline(config, api_key)
        if args.submit:
            run_submission_pass(config, api_key)
    except RuntimeError as exc:
        logger.error(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
