"""
main.py — AutoApply headless CLI entry point.

Delegates entirely to services/. No business logic lives here.

Usage:
  python main.py              # run pipeline once, no submission
  python main.py --submit     # run pipeline + submit all Queued jobs
  python main.py --config path/to/config.yaml
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
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("output/autoapply.log", encoding="utf-8"),
    ],
)
if hasattr(logging.getLogger().handlers[0], "stream"):
    import io
    logging.getLogger().handlers[0].stream = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
    )

for _noisy in ("httpx", "httpcore", "sentence_transformers", "transformers",
               "huggingface_hub", "filelock", "urllib3"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="AutoApply CLI")
    parser.add_argument("--submit", action="store_true",
                        help="Submit Queued applications after pipeline")
    parser.add_argument("--config", default="config.yaml",
                        help="Path to config.yaml")
    args = parser.parse_args()

    from services.config import load_config, inject_env
    from services.pipeline import run_pipeline, run_submission_pass

    config  = load_config(args.config)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    inject_env(config)

    if not api_key:
        logger.warning(
            "ANTHROPIC_API_KEY not found — resume tailoring will be skipped.\n"
            "Add it to .env: ANTHROPIC_API_KEY=sk-ant-..."
        )

    # Pre-load questions.yaml answers for instant first submission
    questions_file = config.get("screening", {}).get("questions_file", "questions.yaml")
    try:
        from core.submitter import _load_yaml_answers
        _load_yaml_answers(questions_file)
    except Exception:
        pass

    run_pipeline(config, api_key)

    if args.submit:
        run_submission_pass(config, api_key)


if __name__ == "__main__":
    main()
