"""Tests for powerpilot.switcher — Backend switching logic."""

from unittest.mock import patch, MagicMock
from powerpilot.switcher import BackendSwitcher


class TestBackendSwitcher:
    """Test backend switching logic."""

    @patch.object(BackendSwitcher, "_is_service_active")
    @patch.object(BackendSwitcher, "_is_tlp_enabled", return_value=False)
    def test_detect_ppd_backend(self, mock_tlp, mock_svc):
        """Should detect PPD when its service is active."""
        mock_svc.side_effect = lambda s: s == "power-profiles-daemon"
        switcher = BackendSwitcher()
        assert switcher.get_current_backend() == "ppd"

    @patch.object(BackendSwitcher, "_is_service_active")
    @patch.object(BackendSwitcher, "_is_tlp_enabled", return_value=False)
    def test_detect_tlp_backend(self, mock_tlp, mock_svc):
        """Should detect TLP when its service is active."""
        mock_svc.side_effect = lambda s: s == "tlp"
        switcher = BackendSwitcher()
        assert switcher.get_current_backend() == "tlp"

    @patch.object(BackendSwitcher, "_is_service_active", return_value=False)
    @patch.object(BackendSwitcher, "_is_tlp_enabled", return_value=False)
    def test_detect_no_backend(self, mock_tlp, mock_svc):
        """Should return 'none' when no backend is active."""
        switcher = BackendSwitcher()
        assert switcher.get_current_backend() == "none"

    @patch.object(BackendSwitcher, "get_current_backend", return_value="ppd")
    def test_alternative_when_ppd(self, mock_current):
        """Alternative to PPD should be TLP."""
        switcher = BackendSwitcher()
        assert switcher.get_alternative_backend() == "tlp"

    @patch.object(BackendSwitcher, "get_current_backend", return_value="tlp")
    def test_alternative_when_tlp(self, mock_current):
        """Alternative to TLP should be PPD."""
        switcher = BackendSwitcher()
        assert switcher.get_alternative_backend() == "ppd"

    @patch.object(BackendSwitcher, "get_current_backend", return_value="none")
    def test_alternative_when_none(self, mock_current):
        """No alternative when no backend is active."""
        switcher = BackendSwitcher()
        assert switcher.get_alternative_backend() is None

    @patch.object(BackendSwitcher, "get_current_backend", return_value="ppd")
    def test_cannot_switch_to_same(self, mock_current):
        """Should refuse to switch to the already-active backend."""
        switcher = BackendSwitcher()
        can, reason = switcher.can_switch_to("ppd")
        assert can is False
        assert "Already using" in reason

    def test_cannot_switch_to_invalid(self):
        """Should refuse invalid backend names."""
        switcher = BackendSwitcher()
        can, reason = switcher.can_switch_to("invalid")
        assert can is False
        assert "Invalid backend" in reason

    @patch("shutil.which", return_value=None)
    @patch.object(BackendSwitcher, "get_current_backend", return_value="ppd")
    def test_cannot_switch_without_apt(self, mock_current, mock_which):
        """Should refuse if apt is not available."""
        switcher = BackendSwitcher()
        can, reason = switcher.can_switch_to("tlp")
        assert can is False
        assert "apt" in reason.lower()

    @patch.object(BackendSwitcher, "_find_helper", return_value="/usr/lib/powerpilot/powerpilot-helper")
    @patch("shutil.which", return_value="/usr/bin/apt")
    @patch.object(BackendSwitcher, "get_current_backend", return_value="ppd")
    def test_can_switch_when_ready(self, mock_current, mock_which, mock_helper):
        """Should allow switch when all prerequisites are met."""
        # Mock pkexec too
        with patch("shutil.which", side_effect=lambda x: "/usr/bin/" + x):
            switcher = BackendSwitcher()
            can, reason = switcher.can_switch_to("tlp")
            assert can is True
            assert "Ready" in reason


class TestCLISwitchBackend:
    """Test --switch-backend CLI flag."""

    def test_switch_backend_arg_parsed(self):
        """--switch-backend should be parsed correctly."""
        from powerpilot.app import parse_args
        args = parse_args(["--switch-backend", "tlp"])
        assert args.switch_backend == "tlp"

        args = parse_args(["--switch-backend", "ppd"])
        assert args.switch_backend == "ppd"

    def test_no_switch_backend_by_default(self):
        """Without --switch-backend, it should be None."""
        from powerpilot.app import parse_args
        args = parse_args([])
        assert args.switch_backend is None
