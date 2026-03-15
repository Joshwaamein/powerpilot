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


class TestKbdBacklight:
    """Test keyboard backlight controls."""

    def _make_kbd(self, tmpdir, brightness="1", max_brightness="2"):
        from powerpilot.hardware import KbdBacklightInfo
        kbd_path = Path(tmpdir) / "kbd_backlight"
        kbd_path.mkdir()
        (kbd_path / "brightness").write_text(brightness)
        (kbd_path / "max_brightness").write_text(max_brightness)
        return KbdBacklightInfo(path=kbd_path, max_brightness=int(max_brightness), name="kbd_backlight")

    def test_read_brightness(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            kbd = self._make_kbd(tmpdir, brightness="1")
            assert kbd.brightness == 1

    def test_write_brightness(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            kbd = self._make_kbd(tmpdir)
            kbd.brightness = 2
            assert kbd.brightness == 2

    def test_clamp_to_max(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            kbd = self._make_kbd(tmpdir, max_brightness="2")
            kbd.brightness = 5
            assert kbd.brightness == 2

    def test_clamp_to_zero(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            kbd = self._make_kbd(tmpdir)
            kbd.brightness = -1
            assert kbd.brightness == 0


class TestWifiInfo:
    """Test Wi-Fi power save controls."""

    @patch("subprocess.run")
    def test_power_save_on(self, mock_run):
        from powerpilot.hardware import WifiInfo
        mock_run.return_value = MagicMock(returncode=0, stdout="Power save: on")
        wifi = WifiInfo(interface="wlan0")
        assert wifi.power_save is True

    @patch("subprocess.run")
    def test_power_save_off(self, mock_run):
        from powerpilot.hardware import WifiInfo
        mock_run.return_value = MagicMock(returncode=0, stdout="Power save: off")
        wifi = WifiInfo(interface="wlan0")
        assert wifi.power_save is False

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_power_save_iw_missing(self, mock_run):
        from powerpilot.hardware import WifiInfo
        wifi = WifiInfo(interface="wlan0")
        assert wifi.power_save is None

    @patch("subprocess.run")
    def test_set_power_save_success(self, mock_run):
        from powerpilot.hardware import WifiInfo
        mock_run.return_value = MagicMock(returncode=0)
        wifi = WifiInfo(interface="wlan0")
        assert wifi.set_power_save(True) is True
        args = mock_run.call_args[0][0]
        assert "on" in args

    @patch("subprocess.run")
    def test_set_power_save_failure(self, mock_run):
        from powerpilot.hardware import WifiInfo
        mock_run.return_value = MagicMock(returncode=1)
        wifi = WifiInfo(interface="wlan0")
        assert wifi.set_power_save(True) is False


class TestBluetoothInfo:
    """Test Bluetooth controls."""

    @patch("subprocess.run")
    def test_bluetooth_enabled(self, mock_run):
        from powerpilot.hardware import BluetoothInfo
        mock_run.return_value = MagicMock(returncode=0, stdout="Soft blocked: no\nHard blocked: no")
        bt = BluetoothInfo(rfkill_index=0)
        assert bt.enabled is True

    @patch("subprocess.run")
    def test_bluetooth_disabled(self, mock_run):
        from powerpilot.hardware import BluetoothInfo
        mock_run.return_value = MagicMock(returncode=0, stdout="Soft blocked: yes\nHard blocked: no")
        bt = BluetoothInfo(rfkill_index=0)
        assert bt.enabled is False

    def test_bluetooth_not_available(self):
        from powerpilot.hardware import BluetoothInfo
        bt = BluetoothInfo(rfkill_index=None)
        assert bt.available is False

    def test_bluetooth_available(self):
        from powerpilot.hardware import BluetoothInfo
        bt = BluetoothInfo(rfkill_index=0)
        assert bt.available is True

    @patch("subprocess.run")
    def test_set_enabled_block(self, mock_run):
        from powerpilot.hardware import BluetoothInfo
        mock_run.return_value = MagicMock(returncode=0)
        bt = BluetoothInfo(rfkill_index=0)
        assert bt.set_enabled(False) is True
        args = mock_run.call_args[0][0]
        assert "block" in args

    @patch("subprocess.run")
    def test_set_enabled_unblock(self, mock_run):
        from powerpilot.hardware import BluetoothInfo
        mock_run.return_value = MagicMock(returncode=0)
        bt = BluetoothInfo(rfkill_index=0)
        assert bt.set_enabled(True) is True
        args = mock_run.call_args[0][0]
        assert "unblock" in args

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_rfkill_missing(self, mock_run):
        from powerpilot.hardware import BluetoothInfo
        bt = BluetoothInfo(rfkill_index=0)
        assert bt.set_enabled(True) is False


class TestHardwareCapabilities:
    """Test the capabilities summary."""

    def test_summary_all_none(self):
        from powerpilot.hardware import HardwareCapabilities
        hw = HardwareCapabilities()
        summary = hw.summary()
        assert all(v is False for v in summary.values())

    def test_summary_with_battery(self):
        from powerpilot.hardware import HardwareCapabilities, BatteryInfo
        hw = HardwareCapabilities()
        hw.battery = BatteryInfo(path=Path("/fake"), name="BAT0")
        summary = hw.summary()
        assert summary["battery"] is True
        assert summary["screen_backlight"] is False
