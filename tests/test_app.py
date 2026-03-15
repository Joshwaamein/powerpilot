"""Tests for powerpilot.app — CLI args and parse_args."""

import pytest
from powerpilot.app import parse_args
from powerpilot import __version__


class TestCLIArgs:
    """Test command-line argument parsing."""

    def test_no_args(self):
        """No arguments should return defaults."""
        args = parse_args([])
        assert args.debug is False
        assert args.no_notify is False

    def test_debug_flag(self):
        """--debug should enable debug mode."""
        args = parse_args(["--debug"])
        assert args.debug is True

    def test_no_notify_flag(self):
        """--no-notify should disable notifications."""
        args = parse_args(["--no-notify"])
        assert args.no_notify is True

    def test_both_flags(self):
        """Both flags should work together."""
        args = parse_args(["--debug", "--no-notify"])
        assert args.debug is True
        assert args.no_notify is True

    def test_version_flag(self):
        """--version should raise SystemExit (argparse behavior)."""
        with pytest.raises(SystemExit) as exc_info:
            parse_args(["--version"])
        assert exc_info.value.code == 0

    def test_unknown_flag_fails(self):
        """Unknown flags should cause an error."""
        with pytest.raises(SystemExit) as exc_info:
            parse_args(["--unknown"])
        assert exc_info.value.code != 0


class TestConfigVersion:
    """Test config versioning."""

    def test_default_config_has_version(self):
        """Default config should include config_version."""
        from powerpilot.config import DEFAULT_CONFIG, CONFIG_VERSION
        assert "config_version" in DEFAULT_CONFIG
        assert DEFAULT_CONFIG["config_version"] == CONFIG_VERSION

    def test_config_version_is_positive_int(self):
        """Config version should be a positive integer."""
        from powerpilot.config import CONFIG_VERSION
        assert isinstance(CONFIG_VERSION, int)
        assert CONFIG_VERSION >= 1
