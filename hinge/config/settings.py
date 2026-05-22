from __future__ import annotations

import os
from pathlib import Path


def store_path() -> Path:
    return Path(os.environ.get("HINGE_STORE_PATH", "./network.duckdb"))


def log_level() -> str:
    """Verbosity for hinge.* loggers. Values: DEBUG, INFO, WARNING, ERROR."""
    return os.environ.get("HINGE_LOG_LEVEL", "INFO")


def log_file() -> Path | None:
    """Optional persistent log file. None means stderr only."""
    val = os.environ.get("HINGE_LOG_FILE")
    return Path(val) if val else None


def types_yaml_path() -> Path:
    return Path(__file__).with_name("types.yaml")
