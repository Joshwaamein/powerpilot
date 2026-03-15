"""Comprehensive tests for powerpilot.battery — Battery monitoring and power events."""

import tempfile
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

from powerpilot.hardware import BatteryInfo
from powerpilot.battery import BatteryMonitor


class TestBatteryInfo:
    """Test BatteryInfo data class with mock sysfs."""

    def _make_battery(self, tmpdir, **files):
        """Create a mock battery sysfs directory."""
        bat_path = Path(tmpdir) / "BAT0"
        bat_path.mkdir()
        defaults = {
            "type": "Battery",
            "status": "Discharging",
            "energy_now": "23000000",
            "energy_full": "46000000",
            "energy_full_design": "57000000",
            "power_now": "15000000",
            "capacity": "50",
        }
        defaults.update(files)
        for name, content in defaults.items():
            (bat_path / name).write_text(content)
        return BatteryInfo(path=bat_path, name="BAT0")

    def test_present_when_battery_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bat = self._make_battery(tmpdir)
            assert bat.present is True

    def test_not_present_when_status_unknown_no_energy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bat_path = Path(tmpdir) / "BAT0"
            bat_path.mkdir()
            (bat_path / "status").write_text("Unknown")
            bat = BatteryInfo(path=bat_path, name="BAT0")
            assert bat.present is False

    def test_status_discharging(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bat = self._make_battery(tmpdir, status="Discharging")
            assert bat.status == "Discharging"

    def test_status_charging(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bat = self._make_battery(tmpdir, status="Charging")
            assert bat.status == "Charging"

    def test_status_full(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bat = self._make_battery(tmpdir, status="Full")
            assert bat.status == "Full"

    def test_status_not_charging(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bat = self._make_battery(tmpdir, status="Not charging")
            assert bat.status == "Not charging"

    def test_status_returns_unknown_on_read_error(self):
        bat = BatteryInfo(path=Path("/nonexistent/path"), name="BAT0")
        assert bat.status == "Unknown"

    def test_charge_percent_from_energy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bat = self._make_battery(tmpdir, energy_now="23000000", energy_full="46000000")
            assert bat.charge_percent == 50

    def test_charge_percent_100(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bat = self._make_battery(tmpdir, energy_now="46000000", energy_full="46000000")
            assert bat.charge_percent == 100

    def test_charge_percent_0(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bat = self._make_battery(tmpdir, energy_now="0", energy_full="46000000")
            assert bat.charge_percent == 0

    def test_charge_percent_falls_back_to_capacity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bat_path = Path(tmpdir) / "BAT0"
            bat_path.mkdir()
            (bat_path / "status").write_text("Discharging")
            (bat_path / "capacity").write_text("75")
            bat = BatteryInfo(path=bat_path, name="BAT0")
            assert bat.charge_percent == 75

    def test_charge_percent_none_when_no_data(self):
        bat = BatteryInfo(path=Path("/nonexistent"), name="BAT0")
        assert bat.charge_percent is None

    def test_power_draw_watts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bat = self._make_battery(tmpdir, power_now="15000000")
            assert bat.power_draw_watts == 15.0

    def test_power_draw_watts_fractional(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bat = self._make_battery(tmpdir, power_now="14800000")
            assert bat.power_draw_watts == 14.8

    def test_power_draw_watts_none_on_error(self):
        bat = BatteryInfo(path=Path("/nonexistent"), name="BAT0")
        assert bat.power_draw_watts is None

    def test_time_remaining_discharging(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 23Wh remaining at 15W = ~1.5 hours
            bat = self._make_battery(tmpdir, status="Discharging",
                                     energy_now="23000000", power_now="15000000")
            remaining = bat.time_remaining_hours
            assert remaining is not None
            assert 1.4 <= remaining <= 1.6

    def test_time_remaining_none_when_charging(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bat = self._make_battery(tmpdir, status="Charging")
            assert bat.time_remaining_hours is None

    def test_time_remaining_none_when_full(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bat = self._make_battery(tmpdir, status="Full")
            assert bat.time_remaining_hours is None

    def test_health_percent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bat = self._make_battery(tmpdir,
                                     energy_full="46000000",
                                     energy_full_design="57000000")
            health = bat.health_percent
            assert health is not None
            assert 80 <= health <= 81  # 46/57 ≈ 80.7%

    def test_health_percent_none_on_error(self):
        bat = BatteryInfo(path=Path("/nonexistent"), name="BAT0")
        assert bat.health_percent is None

    def test_on_ac_when_charging(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bat = self._make_battery(tmpdir, status="Charging")
            assert bat.on_ac is True

    def test_on_ac_when_full(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bat = self._make_battery(tmpdir, status="Full")
            assert bat.on_ac is True

    def test_on_ac_when_not_charging(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bat = self._make_battery(tmpdir, status="Not charging")
            assert bat.on_ac is True

    def test_not_on_ac_when_discharging(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bat = self._make_battery(tmpdir, status="Discharging")
            assert bat.on_ac is False


class TestBatteryMonitor:
    """Test BatteryMonitor event handling."""

    def test_initial_state(self):
        mon = BatteryMonitor()
        assert mon.on_ac is None
        assert mon._running is False

    def test_set_threshold(self):
        mon = BatteryMonitor()
        mon.set_threshold(15)
        assert mon._low_battery_threshold == 15

    def test_set_threshold_clamped_low(self):
        mon = BatteryMonitor()
        mon.set_threshold(1)
        assert mon._low_battery_threshold == 5

    def test_set_threshold_clamped_high(self):
        mon = BatteryMonitor()
        mon.set_threshold(99)
        assert mon._low_battery_threshold == 50

    def test_register_power_change_callback(self):
        mon = BatteryMonitor()
        cb = MagicMock()
        mon.on_power_change(cb)
        assert cb in mon._power_change_callbacks

    def test_register_low_battery_callback(self):
        mon = BatteryMonitor()
        cb = MagicMock()
        mon.on_low_battery(cb)
        assert cb in mon._low_battery_callbacks

    def test_multiple_callbacks_registered(self):
        mon = BatteryMonitor()
        cb1, cb2 = MagicMock(), MagicMock()
        mon.on_power_change(cb1)
        mon.on_power_change(cb2)
        assert len(mon._power_change_callbacks) == 2

    def test_start_sets_running(self):
        mon = BatteryMonitor()
        with patch.object(mon, "_monitor_loop"):
            mon.start()
            assert mon._running is True
            mon.stop()

    def test_stop_clears_running(self):
        mon = BatteryMonitor()
        mon._running = True
        mon._thread = MagicMock()
        mon.stop()
        assert mon._running is False

    def test_start_idempotent(self):
        """Starting twice should not create two threads."""
        mon = BatteryMonitor()
        mon._running = True
        mon.start()  # Should no-op since already running
        assert mon._thread is None  # No new thread created

    def test_power_change_callbacks_called(self):
        """Simulate a power change and verify callbacks fire."""
        mon = BatteryMonitor()
        cb = MagicMock()
        mon.on_power_change(cb)
        mon._on_ac = False

        # Simulate UPower property change
        mon._on_upower_properties_changed(
            "org.freedesktop.UPower",
            {"OnBattery": False},  # on_battery=False means on_ac=True
            [],
        )

        cb.assert_called_once_with(True)
        assert mon._on_ac is True

    def test_power_change_resets_low_battery_trigger(self):
        """Plugging in should reset the low battery trigger."""
        mon = BatteryMonitor()
        mon._low_battery_triggered = True
        mon._on_ac = False

        mon._on_upower_properties_changed(
            "org.freedesktop.UPower",
            {"OnBattery": False},
            [],
        )

        assert mon._low_battery_triggered is False

    def test_low_battery_callback_fires_at_threshold(self):
        """Low battery callback should fire when percentage drops to threshold."""
        mon = BatteryMonitor()
        mon._low_battery_threshold = 20
        mon._on_ac = False
        mon._low_battery_triggered = False

        cb = MagicMock()
        mon.on_low_battery(cb)

        mon._on_battery_properties_changed(
            "org.freedesktop.UPower.Device",
            {"Percentage": 20},
            [],
        )

        cb.assert_called_once_with(20)
        assert mon._low_battery_triggered is True

    def test_low_battery_not_triggered_on_ac(self):
        """Low battery should NOT trigger when on AC power."""
        mon = BatteryMonitor()
        mon._low_battery_threshold = 20
        mon._on_ac = True
        mon._low_battery_triggered = False

        cb = MagicMock()
        mon.on_low_battery(cb)

        mon._on_battery_properties_changed(
            "org.freedesktop.UPower.Device",
            {"Percentage": 10},
            [],
        )

        cb.assert_not_called()

    def test_low_battery_only_fires_once(self):
        """Low battery should only trigger once per discharge cycle."""
        mon = BatteryMonitor()
        mon._low_battery_threshold = 20
        mon._on_ac = False
        mon._low_battery_triggered = True  # Already triggered

        cb = MagicMock()
        mon.on_low_battery(cb)

        mon._on_battery_properties_changed(
            "org.freedesktop.UPower.Device",
            {"Percentage": 15},
            [],
        )

        cb.assert_not_called()

    def test_low_battery_above_threshold_no_trigger(self):
        """Battery above threshold should not trigger."""
        mon = BatteryMonitor()
        mon._low_battery_threshold = 20
        mon._on_ac = False
        mon._low_battery_triggered = False

        cb = MagicMock()
        mon.on_low_battery(cb)

        mon._on_battery_properties_changed(
            "org.freedesktop.UPower.Device",
            {"Percentage": 50},
            [],
        )

        cb.assert_not_called()

    def test_callback_error_does_not_crash(self):
        """A failing callback should not crash the monitor."""
        mon = BatteryMonitor()
        mon._on_ac = False

        bad_cb = MagicMock(side_effect=RuntimeError("test error"))
        good_cb = MagicMock()
        mon.on_power_change(bad_cb)
        mon.on_power_change(good_cb)

        # Should not raise
        mon._on_upower_properties_changed(
            "org.freedesktop.UPower",
            {"OnBattery": False},
            [],
        )

        bad_cb.assert_called_once()
        good_cb.assert_called_once()

    def test_no_change_when_same_state(self):
        """Callbacks should not fire if power state hasn't actually changed."""
        mon = BatteryMonitor()
        mon._on_ac = True  # Already on AC

        cb = MagicMock()
        mon.on_power_change(cb)

        mon._on_upower_properties_changed(
            "org.freedesktop.UPower",
            {"OnBattery": False},  # Still on AC
            [],
        )

        cb.assert_not_called()
