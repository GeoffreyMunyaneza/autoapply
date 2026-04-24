"""
Background pipeline execution thread for the GUI.
"""

import logging
import queue
import threading
from typing import Optional


class QueueHandler(logging.Handler):
    """Logging handler that forwards formatted log lines into a queue."""

    def __init__(self, log_queue: queue.Queue) -> None:
        super().__init__()
        self.log_queue = log_queue
        self.setFormatter(
            logging.Formatter(
                "%(asctime)s  %(levelname)-8s  %(message)s",
                datefmt="%H:%M:%S",
            )
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.log_queue.put(("log", record.levelname, self.format(record)))
        except Exception:
            self.handleError(record)


class PipelineRunner(threading.Thread):
    """
    Run the pipeline in a daemon thread and stream logs back to the GUI.

    Queue items:
      ("log", levelname, text)
      ("done", new_count, error)
    """

    def __init__(self, config: dict, api_key: str, submit: bool = False) -> None:
        super().__init__(daemon=True, name="PipelineRunner")
        self.config = config
        self.api_key = api_key
        self.submit = submit
        self.log_queue: queue.Queue = queue.Queue()
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def run(self) -> None:
        handler = QueueHandler(self.log_queue)
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
            logging.getLogger(__name__).error("Pipeline error: %s", exc, exc_info=True)
        finally:
            root_logger.removeHandler(handler)
            self.log_queue.put(("done", new_count, error))
