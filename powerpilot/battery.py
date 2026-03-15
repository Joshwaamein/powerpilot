"""Battery monitoring and power source event handling for PowerPilot.

Listens to UPower DBus signals for AC/battery transitions and
monitors battery level for auto low-battery switching.
"""

import logging
import threading
from typing import Callable

log = logging.getLogger("powerpilot.battery")

# UPower DBus constants
UPOWER_BUS_NAME = "org.freedesktop.UPower"
UPOWER_OBJECT_PATH = "/org/freedesktop/UPower"
UPOWER_INTERFACE = "org.freedesktop.UPower"
UPOWER_DEVICE_INTERFACE = "org.freedesktop.UPower.Device"


class BatteryMonitor:
    """Monitors battery state via UPower DBus signals.

    Calls registered callbacks when:
    - Power source changes (AC <-> battery)
    - Battery drops below a threshold
    """

    def __init__(self) -> None:
        self._on_ac: bool | None = None
        self._power_change_callbacks: list[Callable[[bool], None]] = []
        self._low_battery_callbacks: list[Callable[[int], None]] = []
        self._low_battery_threshold: int = 20
        self._low_battery_triggered: bool = False
        self._running: bool = False
        self._thread: threading.Thread | None = None
        self._dbus_loop = None

    def on_power_change(self, callback: Callable[[bool], None]) -> None:
        """Register a callback for power source changes.

        Args:
            callback: Called with True when switching to AC, False for battery.
        """
        self._power_change_callbacks.append(callback)

    def on_low_battery(self, callback: Callable[[int], None]) -> None:
        """Register a callback for low battery events.

        Args:
            callback: Called with current battery percentage.
        """
        self._low_battery_callbacks.append(callback)

    @property
    def on_ac(self) -> bool | None:
        """Whether the system is currently on AC power."""
        return self._on_ac

    def set_threshold(self, threshold: int) -> None:
        """Set the low battery threshold percentage."""
        self._low_battery_threshold = max(5, min(50, threshold))

    def start(self) -> None:
        """Start monitoring battery events in a background thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        log.info("Battery monitor started")

    def stop(self) -> None:
        """Stop the battery monitor."""
        self._running = False
        if self._dbus_loop:
            try:
                self._dbus_loop.quit()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=5)
        log.info("Battery monitor stopped")

    def _monitor_loop(self) -> None:
        """Main monitoring loop running in a background thread."""
        try:
            self._monitor_dbus()
        except Exception as e:
            log.warning("DBus monitoring failed: %s. Falling back to polling.", e)
            self._monitor_polling()

    def _monitor_dbus(self) -> None:
        """Monitor power changes via UPower DBus signals."""
        import dbus
        from dbus.mainloop.glib import DBusGMainLoop
        from gi.repository import GLib

        DBusGMainLoop(set_as_default=True)
        bus = dbus.SystemBus()

        # Get initial state
        try:
            upower = bus.get_object(UPOWER_BUS_NAME, UPOWER_OBJECT_PATH)
            props = dbus.Interface(upower, "org.freedesktop.DBus.Properties")
            self._on_ac = bool(props.Get(UPOWER_INTERFACE, "OnBattery")) is False
            log.info("Initial power state: %s", "AC" if self._on_ac else "battery")
        except Exception as e:
            log.warning("Could not get initial UPower state: %s", e)

        # Listen for property changes on UPower
        bus.add_signal_receiver(
            self._on_upower_properties_changed,
            signal_name="PropertiesChanged",
            dbus_interface="org.freedesktop.DBus.Properties",
            bus_name=UPOWER_BUS_NAME,
            path=UPOWER_OBJECT_PATH,
        )

        # Also monitor battery device for level changes
        self._setup_battery_level_monitor(bus)

        self._dbus_loop = GLib.MainLoop()
        log.debug("Entering UPower DBus event loop")
        self._dbus_loop.run()

    def _on_upower_properties_changed(
        self, interface: str, changed: dict, invalidated: list
    ) -> None:
        """Handle UPower property changes."""
        if "OnBattery" in changed:
            on_battery = bool(changed["OnBattery"])
            on_ac = not on_battery
            if on_ac != self._on_ac:
                self._on_ac = on_ac
                log.info(
                    "Power source changed: %s", "AC" if on_ac else "battery"
                )
                # Reset low battery trigger when plugging in
                if on_ac:
                    self._low_battery_triggered = False

                for cb in self._power_change_callbacks:
                    try:
                        cb(on_ac)
                    except Exception as e:
                        log.error("Power change callback error: %s", e)

    def _setup_battery_level_monitor(self, bus) -> None:
        """Set up monitoring for battery level changes."""
        import dbus

        try:
            upower = bus.get_object(UPOWER_BUS_NAME, UPOWER_OBJECT_PATH)
            device_paths = upower.EnumerateDevices(
                dbus_interface=UPOWER_INTERFACE
            )

            for path in device_paths:
                device = bus.get_object(UPOWER_BUS_NAME, str(path))
                props = dbus.Interface(device, "org.freedesktop.DBus.Properties")
                try:
                    dev_type = int(props.Get(UPOWER_DEVICE_INTERFACE, "Type"))
                    if dev_type == 2:  # Battery
                        bus.add_signal_receiver(
                            self._on_battery_properties_changed,
                            signal_name="PropertiesChanged",
                            dbus_interface="org.freedesktop.DBus.Properties",
                            bus_name=UPOWER_BUS_NAME,
                            path=str(path),
                        )
                        log.debug("Monitoring battery device: %s", path)
                except Exception:
                    pass
        except Exception as e:
            log.warning("Could not enumerate UPower devices: %s", e)

    def _on_battery_properties_changed(
        self, interface: str, changed: dict, invalidated: list
    ) -> None:
        """Handle battery device property changes."""
        if "Percentage" in changed:
            percent = int(changed["Percentage"])
            if (
                not self._on_ac
                and percent <= self._low_battery_threshold
                and not self._low_battery_triggered
            ):
                self._low_battery_triggered = True
                log.warning(
                    "Low battery: %d%% (threshold: %d%%)",
                    percent,
                    self._low_battery_threshold,
                )
                for cb in self._low_battery_callbacks:
                    try:
                        cb(percent)
                    except Exception as e:
                        log.error("Low battery callback error: %s", e)

    def _monitor_polling(self) -> None:
        """Fallback: poll battery status periodically."""
        import time
        from pathlib import Path

        poll_interval = 30  # seconds

        while self._running:
            try:
                # Check AC status
                for ps in Path("/sys/class/power_supply").iterdir():
                    ps_type = (ps / "type").read_text().strip()
                    if ps_type == "Battery":
                        status = (ps / "status").read_text().strip()
                        on_ac = status in ("Charging", "Full", "Not charging")

                        if self._on_ac is not None and on_ac != self._on_ac:
                            self._on_ac = on_ac
                            log.info(
                                "Power source changed (poll): %s",
                                "AC" if on_ac else "battery",
                            )
                            if on_ac:
                                self._low_battery_triggered = False
                            for cb in self._power_change_callbacks:
                                try:
                                    cb(on_ac)
                                except Exception as e:
                                    log.error("Power change callback error: %s", e)
                        elif self._on_ac is None:
                            self._on_ac = on_ac

                        # Check battery level
                        try:
                            capacity = int((ps / "capacity").read_text().strip())
                            if (
                                not on_ac
                                and capacity <= self._low_battery_threshold
                                and not self._low_battery_triggered
                            ):
                                self._low_battery_triggered = True
                                log.warning("Low battery (poll): %d%%", capacity)
                                for cb in self._low_battery_callbacks:
                                    try:
                                        cb(capacity)
                                    except Exception as e:
                                        log.error(
                                            "Low battery callback error: %s", e
                                        )
                        except (OSError, ValueError):
                            pass

                        break  # Only need the first battery
            except Exception as e:
                log.debug("Polling error: %s", e)

            time.sleep(poll_interval)
