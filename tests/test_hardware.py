"""Tests for powerpilot.hardware — Issue #13: brightness fallback."""

import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from powerpilot.hardware import BacklightInfo


class TestBrightnessFallback:
    """Test brightness setting with sysfs and brightnessctl fallback."""

    def _make_backlight(self, tmpdir):
        """Create a mock backlight in a temp directory."""
        bl_path = Path(tmpdir) / "test_backlight"
        bl_path.mkdir()
        (bl_path / "brightness").write_text("50")
        (bl_path / "max_brightness").write_text("100")
        (bl_path / "type").write_text("raw")
        return BacklightInfo(path=bl_path, max_brightness=100, name="test_backlight")

    def test_direct_write_works(self):
        """When sysfs is writable, direct write should work."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bl = self._make_backlight(tmpdir)

            bl.brightness = 75
            assert bl.brightness == 75

    def test_direct_write_clamps_max(self):
        """Brightness should be clamped to max_brightness."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bl = self._make_backlight(tmpdir)

            bl.brightness = 200  # Over max of 100
            assert bl.brightness == 100

    def test_direct_write_clamps_min(self):
        """Brightness should be clamped to 0 minimum."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bl = self._make_backlight(tmpdir)

            bl.brightness = -10
            assert bl.brightness == 0

    def test_set_percent(self):
        """set_percent should convert percentage to raw value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bl = self._make_backlight(tmpdir)

            bl.set_percent(50)
            assert bl.brightness == 50

            bl.set_percent(100)
            assert bl.brightness == 100

    def test_brightness_percent_property(self):
        """brightness_percent should return current value as percentage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bl = self._make_backlight(tmpdir)

            bl.brightness = 75
            assert bl.brightness_percent == 75

    @patch("powerpilot.hardware.BacklightInfo._set_brightness_ctl")
    def test_fallback_to_brightnessctl(self, mock_ctl):
        """When direct write fails with PermissionError, should fall back to brightnessctl."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bl = self._make_backlight(tmpdir)

            # Make the brightness file read-only
            os.chmod(bl.path / "brightness", 0o444)

            bl.brightness = 60

            # Should have called brightnessctl fallback
            mock_ctl.assert_called_once_with(60)

            # Restore permissions for cleanup
            os.chmod(bl.path / "brightness", 0o644)

    @patch("subprocess.run")
    def test_brightnessctl_called_correctly(self, mock_run):
        """_set_brightness_ctl should call brightnessctl with correct args."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bl = self._make_backlight(tmpdir)

            mock_run.return_value = MagicMock(returncode=0)
            bl._set_brightness_ctl(42)

            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args[0] == "brightnessctl"
            assert "42" in args

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_brightnessctl_not_installed(self, mock_run):
        """If brightnessctl is not installed, should raise PermissionError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bl = self._make_backlight(tmpdir)

            import pytest
            with pytest.raises(PermissionError, match="brightnessctl not installed"):
                bl._set_brightness_ctl(50)
