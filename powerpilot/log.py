"""Logging setup for PowerPilot.

Uses systemd journal if available, falls back to file logging.
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path


def setup_logging(debug: bool = False) -> logging.Logger:
    """Configure and return the application logger.

    Args:
        debug: If True, set log level to DEBUG. Otherwise INFO.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger("powerpilot")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)

    # Avoid duplicate handlers on re-init
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Try systemd journal first
    journal_handler = _try_journal_handler()
    if journal_handler:
        journal_handler.setLevel(logging.DEBUG if debug else logging.INFO)
        logger.addHandler(journal_handler)
        logger.debug("Logging to systemd journal")
    else:
        # Fall back to file logging
        log_dir = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "powerpilot"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "powerpilot.log"

        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=1_000_000, backupCount=3
        )
        file_handler.setLevel(logging.DEBUG if debug else logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.debug("Logging to %s", log_file)

    # Always add stderr in debug mode
    if debug:
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.DEBUG)
        stderr_handler.setFormatter(formatter)
        logger.addHandler(stderr_handler)

    return logger


def _try_journal_handler() -> logging.Handler | None:
    """Try to create a systemd journal log handler."""
    try:
        from systemd.journal import JournalHandler

        handler = JournalHandler(SYSLOG_IDENTIFIER="powerpilot")
        return handler
    except ImportError:
        pass

    try:
        # Alternative: logging to journal via syslog
        handler = logging.handlers.SysLogHandler(address="/dev/log")
        handler.ident = "powerpilot: "
        return handler
    except (OSError, FileNotFoundError):
        pass

    return None


