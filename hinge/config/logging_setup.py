"""Central logging configuration for hinge.

Call ``setup_logging()`` once at process start (CLI entry-point or lib import).
Every module then does ``logger = logging.getLogger(__name__)`` and logs normally.

Environment variables
---------------------
HINGE_LOG_LEVEL   Verbosity for the hinge.* namespace. Default: INFO.
                  Values: DEBUG, INFO, WARNING, ERROR
HINGE_LOG_FILE    If set, logs are also written to this path in addition to
                  stderr. Useful for CI or long ingest runs.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

_FMT = "%(asctime)s %(levelname)-8s %(name)s — %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"
_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    level_name = os.environ.get("HINGE_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    formatter = logging.Formatter(_FMT, datefmt=_DATE_FMT)

    # stderr handler — always on
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    stderr_handler.setLevel(level)

    root = logging.getLogger("hinge")
    root.setLevel(level)
    root.addHandler(stderr_handler)

    # optional file handler
    log_file = os.environ.get("HINGE_LOG_FILE")
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)  # always full detail in the file
        root.addHandler(file_handler)

    # silence noisy third-party loggers unless user explicitly requests DEBUG
    if level > logging.DEBUG:
        logging.getLogger("dbt").setLevel(logging.WARNING)

    root.debug("logging initialised (level=%s)", level_name)
