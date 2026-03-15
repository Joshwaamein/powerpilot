"""Tests for powerpilot.profiles — Bug #3: active profile set on failure."""

import pytest
from powerpilot.profiles import ProfileManager


class TestProfileSwitching:
    """Test profile switching behavior."""

    def test_successful_switch_updates_active(self, default_config, mock_backend, mock_hardware):
        """Successful switch should update active profile."""
        mgr = ProfileManager(mock_backend, mock_hardware, default_config)

        assert mgr.active_profile is None

        result = mgr.switch_profile("balanced", user_initiated=True)

        assert result is True
        assert mgr.active_profile == "balanced"
        assert mgr.user_overridden is True

    def test_failed_switch_keeps_previous_profile(self, default_config, failing_backend, mock_hardware):
        """Bug #3: Failed switch should NOT update active profile."""
        mgr = ProfileManager(failing_backend, mock_hardware, default_config)

        # Set initial state
        mgr._active_profile = "balanced"
        mgr._user_overridden = False

        result = mgr.switch_profile("performance", user_initiated=True)

        assert result is False
        # Active profile should remain "balanced" — not changed to "performance"
        assert mgr.active_profile == "balanced"
        # User override should NOT be set on failure
        assert mgr.user_overridden is False

    def test_switch_nonexistent_profile(self, default_config, mock_backend, mock_hardware):
        """Switching to a nonexistent profile should fail gracefully."""
        mgr = ProfileManager(mock_backend, mock_hardware, default_config)
        mgr._active_profile = "balanced"

        result = mgr.switch_profile("nonexistent-profile", user_initiated=True)

        assert result is False
        assert mgr.active_profile == "balanced"

    def test_auto_switch_does_not_set_user_override(self, default_config, mock_backend, mock_hardware):
        """Auto-triggered switches should not set user_overridden."""
        mgr = ProfileManager(mock_backend, mock_hardware, default_config)

        result = mgr.switch_profile("power-saver", user_initiated=False)

        assert result is True
        assert mgr.active_profile == "power-saver"
        assert mgr.user_overridden is False

    def test_get_available_profiles_ppd(self, default_config, mock_backend, mock_hardware):
        """PPD backend should not show TLP-only profiles."""
        mgr = ProfileManager(mock_backend, mock_hardware, default_config)

        profiles = mgr.get_available_profiles()

        assert "power-saver" in profiles
        assert "balanced" in profiles
        assert "performance" in profiles
        assert "tlp-auto" not in profiles  # PPD backend — should be hidden

    def test_get_profile_info(self, default_config, mock_backend, mock_hardware):
        """get_profile_info should return config dict for valid profiles."""
        mgr = ProfileManager(mock_backend, mock_hardware, default_config)

        info = mgr.get_profile_info("balanced")
        assert info is not None
        assert info["label"] == "Balanced"

        info = mgr.get_profile_info("nonexistent")
        assert info is None

    def test_detect_current_profile(self, default_config, mock_backend, mock_hardware):
        """detect_current_profile should match backend profile to config."""
        mgr = ProfileManager(mock_backend, mock_hardware, default_config)

        current = mgr.detect_current_profile()
        assert current == "balanced"  # mock_backend defaults to "balanced"

    def test_reset_user_override(self, default_config, mock_backend, mock_hardware):
        """reset_user_override should clear the flag."""
        mgr = ProfileManager(mock_backend, mock_hardware, default_config)
        mgr.switch_profile("balanced", user_initiated=True)
        assert mgr.user_overridden is True

        mgr.reset_user_override()
        assert mgr.user_overridden is False
