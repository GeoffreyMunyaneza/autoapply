"""
gui/runner.py — Background pipeline execution thread.

Runs run_pipeline() and/or run_submission_pass() in a daemon thread,
capturing all log output via a logging.Handler and posting log lines
into a queue that the GUI polls.

Usage:
    runner = PipelineRunner(config, api_key, submit=False, on_done=callback)
    runner.log_queue  # Queue[str] — poll this for log lines
    runner.start()
    runner.cancel()   # request stop (best-effort)
"""

import logging
import queue
import threading
from typing import Callable, Optional


class _QueueHandler(logging.Handler):
    """Logging handler that writes formatted records to a queue."""

    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue
        fmt = logging.Formatter(
            "%(asctime)s  %(levelname)-8s  %(message)s",
            datefmt="%H:%M:%S",
        )
        self.setFormatter(fmt)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = self.format(record)
            self.log_queue.put(("log", record.levelname, line))
        except Exception:
            self.handleError(record)


class PipelineRunner(threading.Thread):
    """
    Daemon thread that runs the AutoApply pipeline.

    Posts tuples to self.log_queue:
      ("log",  levelname, text)   — a log line
      ("done", new_count, error)  — pipeline finished
    """

    def __init__(
        self,
        config: dict,
        api_key: str,
        submit: bool = False,
        on_done: Optional[Callable[[int, Optional[str]], None]] = None,
    ):
        super().__init__(daemon=True, name="PipelineRunner")
        self.config = config
        self.api_key = api_key
        self.submit = submit
        self.on_done = on_done
        self.log_queue: queue.Queue = queue.Queue()
        self._cancel_event = threading.Event()
        self._new_count = 0

    def cancel(self) -> None:
        self._cancel_event.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def run(self) -> None:
        handler = _QueueHandler(self.log_queue)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)

        error: Optional[str] = None
        new_count = 0
        try:
            from services.pipeline import run_pipeline, run_submission_pass

            new_count = run_pipeline(self.config, self.api_key)

            if self.submit and not self.cancelled:
                run_submission_pass(self.config, self.api_key)

        except Exception as exc:
            error = str(exc)
            logging.getLogger(__name__).error(f"Pipeline error: {exc}", exc_info=True)
        finally:
            root_logger.removeHandler(handler)
            self.log_queue.put(("done", new_count, error))
            if self.on_done:
                try:
                    self.on_done(self._new_count, error)
                except Exception:
                    pass
