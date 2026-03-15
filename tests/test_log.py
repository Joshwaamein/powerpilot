"""Tests for powerpilot.log — Bug #1: import order crash."""

import logging
import tempfile
import os
from unittest.mock import patch


def test_setup_logging_without_journal():
    """Bug #1: setup_logging should work when journald is unavailable.

    Previously, `import logging.handlers` was at the bottom of log.py,
    causing RotatingFileHandler to crash if journald was unavailable.
    """
    # Clear any existing handlers
    logger = logging.getLogger("powerpilot")
    logger.handlers.clear()

    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = os.path.join(tmpdir, "powerpilot")

        # Mock both journal handlers to fail, forcing file fallback
        with patch.dict(os.environ, {"XDG_STATE_HOME": tmpdir}):
            with patch("powerpilot.log._try_journal_handler", return_value=None):
                from powerpilot.log import setup_logging

                result = setup_logging(debug=False)

                assert result is not None
                assert isinstance(result, logging.Logger)
                assert result.name == "powerpilot"
                # Should have at least one handler (file handler)
                assert len(result.handlers) >= 1

    # Cleanup
    logger.handlers.clear()


def test_setup_logging_debug_mode():
    """setup_logging with debug=True should add stderr handler."""
    logger = logging.getLogger("powerpilot")
    logger.handlers.clear()

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"XDG_STATE_HOME": tmpdir}):
            with patch("powerpilot.log._try_journal_handler", return_value=None):
                from powerpilot.log import setup_logging

                result = setup_logging(debug=True)

                assert result.level == logging.DEBUG
                # Should have file handler + stderr handler
                assert len(result.handlers) >= 2

    logger.handlers.clear()


def test_setup_logging_idempotent():
    """Calling setup_logging twice should not duplicate handlers."""
    logger = logging.getLogger("powerpilot")
    logger.handlers.clear()

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"XDG_STATE_HOME": tmpdir}):
            with patch("powerpilot.log._try_journal_handler", return_value=None):
                from powerpilot.log import setup_logging

                result1 = setup_logging(debug=False)
                handler_count = len(result1.handlers)

                result2 = setup_logging(debug=False)
                assert len(result2.handlers) == handler_count

    logger.handlers.clear()
