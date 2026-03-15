"""Tests for powerpilot.notifications — Desktop notification delivery."""

from unittest.mock import patch, MagicMock

from powerpilot.notifications import Notifier


class TestNotifier:
    """Test notification delivery."""

    def test_disabled_does_not_send(self):
        notifier = Notifier(enabled=False)
        with patch.object(notifier, "_notify_cli") as mock_cli:
            with patch.object(notifier, "_notify_gi") as mock_gi:
                notifier.notify("Title", "Body")
                mock_cli.assert_not_called()
                mock_gi.assert_not_called()

    def test_enabled_sends(self):
        notifier = Notifier(enabled=True)
        notifier._gi_available = False  # Force CLI path
        with patch.object(notifier, "_notify_cli") as mock_cli:
            notifier.notify("Title", "Body", icon="test-icon")
            mock_cli.assert_called_once()

    def test_enable_disable_toggle(self):
        notifier = Notifier(enabled=True)
        assert notifier.enabled is True
        notifier.enabled = False
        assert notifier.enabled is False

    @patch("subprocess.run")
    def test_notify_cli_calls_notify_send(self, mock_run):
        notifier = Notifier(enabled=True)
        notifier._gi_available = False
        notifier.notify("PowerPilot", "Test message", icon="battery-good-symbolic")

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "notify-send"
        assert "PowerPilot" in args
        assert "Test message" in args

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_cli_fallback_handles_missing_notify_send(self, mock_run):
        """Should not crash if notify-send is not installed."""
        notifier = Notifier(enabled=True)
        notifier._gi_available = False
        # Should not raise
        notifier.notify("Title", "Body")

    def test_profile_switch_notification(self):
        notifier = Notifier(enabled=True)
        with patch.object(notifier, "notify") as mock:
            notifier.notify_profile_switch("Balanced", "battery-good-symbolic")
            mock.assert_called_once()
            # Check body contains the profile name (positional or keyword arg)
            call_args = mock.call_args
            body = call_args.kwargs.get("body", "")
            if not body and len(call_args.args) > 1:
                body = call_args.args[1]
            assert "Balanced" in body

    def test_low_battery_notification(self):
        notifier = Notifier(enabled=True)
        with patch.object(notifier, "notify") as mock:
            notifier.notify_low_battery(15)
            mock.assert_called_once()
            call_kwargs = mock.call_args.kwargs
            assert call_kwargs.get("urgency") == "critical"

    def test_power_source_ac_notification(self):
        notifier = Notifier(enabled=True)
        with patch.object(notifier, "notify") as mock:
            notifier.notify_power_source(on_ac=True)
            mock.assert_called_once()
            assert "AC" in mock.call_args.kwargs.get("body", "")

    def test_power_source_battery_notification(self):
        notifier = Notifier(enabled=True)
        with patch.object(notifier, "notify") as mock:
            notifier.notify_power_source(on_ac=False)
            mock.assert_called_once()
            assert "battery" in mock.call_args.kwargs.get("body", "").lower()
