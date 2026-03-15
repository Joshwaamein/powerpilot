"""Tests for powerpilot.inhibitor — Issue #11: process name matching."""

from unittest.mock import patch
from powerpilot.inhibitor import AppInhibitor


class TestProcessMatching:
    """Test substring-based process matching."""

    def _make_inhibitor(self, rules=None):
        return AppInhibitor(
            app_rules=rules or {"steam": "performance", "gamemoderun": "performance"},
            enabled=True,
        )

    @patch.object(AppInhibitor, "_get_running_processes")
    def test_exact_match(self, mock_ps):
        """Exact process name should match."""
        mock_ps.return_value = {"/usr/bin/steam", "/usr/bin/bash"}
        inhibitor = self._make_inhibitor()

        result = inhibitor.check_once()
        assert result == "performance"

    @patch.object(AppInhibitor, "_get_running_processes")
    def test_substring_match(self, mock_ps):
        """Substring of command line should match (e.g., steam-runtime)."""
        mock_ps.return_value = {
            "/home/user/.steam/steam-runtime/run.sh",
            "/usr/bin/bash",
        }
        inhibitor = self._make_inhibitor()

        result = inhibitor.check_once()
        assert result == "performance"

    @patch.object(AppInhibitor, "_get_running_processes")
    def test_case_insensitive(self, mock_ps):
        """Matching should be case-insensitive (rules are lowercased for comparison)."""
        # _get_running_processes lowercases all output, so mock returns lowercase
        mock_ps.return_value = {"/usr/bin/steam", "/usr/bin/bash"}
        # Rule has mixed case — should still match because check_once lowercases the needle
        inhibitor = self._make_inhibitor({"Steam": "performance"})

        result = inhibitor.check_once()
        assert result == "performance"

    @patch.object(AppInhibitor, "_get_running_processes")
    def test_no_match(self, mock_ps):
        """No matching process should return None."""
        mock_ps.return_value = {"/usr/bin/firefox", "/usr/bin/bash"}
        inhibitor = self._make_inhibitor()

        result = inhibitor.check_once()
        assert result is None

    @patch.object(AppInhibitor, "_get_running_processes")
    def test_empty_process_list(self, mock_ps):
        """Empty process list should return None."""
        mock_ps.return_value = set()
        inhibitor = self._make_inhibitor()

        result = inhibitor.check_once()
        assert result is None

    @patch.object(AppInhibitor, "_get_running_processes")
    def test_long_process_name_match(self, mock_ps):
        """Process names longer than 15 chars should match via args field."""
        mock_ps.return_value = {
            "/opt/resolve/bin/davinci-resolve-studio",
            "/usr/bin/bash",
        }
        inhibitor = self._make_inhibitor({"davinci-resolve": "performance"})

        result = inhibitor.check_once()
        assert result == "performance"

    def test_inhibitor_not_started_when_disabled(self):
        """Inhibitor should not start when disabled."""
        inhibitor = AppInhibitor({"steam": "performance"}, enabled=False)
        inhibitor.start()
        assert inhibitor._running is False

    def test_active_inhibitor_initially_none(self):
        """Active inhibitor should be None initially."""
        inhibitor = self._make_inhibitor()
        assert inhibitor.active_inhibitor is None
