#!/usr/bin/env python3
"""Centralized best-effort logging for installer-owned Python helpers.

Every Python helper in this repository imports ``get_logger`` and ``log_call``
from this module. Logging writes under the repository ``.log/`` directory and
must never abort installer workflows.
"""

from __future__ import annotations

import functools
import inspect
import logging
from pathlib import Path
from typing import Any, Callable, TypeVar


LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
F = TypeVar("F", bound=Callable[..., Any])


def _repo_root() -> Path:
    """Return the repository root for scripts in this directory."""
    return Path(__file__).resolve().parents[1]


def get_logger(name: str, log_file: str) -> logging.Logger:
    """Return an idempotent logger that writes under the repository `.log/`.

    Args:
        name: Logger name used in each emitted record.
        log_file: File name within the repository `.log/` directory.

    Returns:
        A configured logger. If file setup fails, the logger falls back to a
        null handler so helper scripts keep installer workflows non-blocking.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    if logger.handlers:
        return logger

    try:
        log_dir = _repo_root() / ".log"
        log_dir.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.FileHandler(
            log_dir / log_file, encoding="utf-8"
        )
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
    except OSError:
        handler = logging.NullHandler()
    logger.addHandler(handler)
    return logger


def log_call(logger: logging.Logger, level: int = logging.DEBUG) -> Callable[[F], F]:
    """Trace a function by logging bound arguments on entry and return on exit.

    Args:
        logger: Centralized logger returned by ``get_logger``.
        level: Logging level for the entry and exit records.

    Returns:
        Decorator that records ``file:qualname`` with arguments and return value.
    """

    def decorator(func: F) -> F:
        location = f"{Path(func.__code__.co_filename).name}:{func.__qualname__}"
        signature = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            bound = signature.bind(*args, **kwargs)
            bound.apply_defaults()
            rendered = ", ".join(
                f"{name}={value!r}" for name, value in bound.arguments.items()
            )
            logger.log(level, "ENTER %s(%s)", location, rendered)
            result = func(*args, **kwargs)
            logger.log(level, "EXIT %s -> %r", location, result)
            return result

        return wrapper  # type: ignore[return-value]

    return decorator
