"""Main PowerPilot application.

System tray application with AppIndicator for profile switching.
"""

import argparse
import logging
import signal
import sys

from . import __version__

log = logging.getLogger("powerpilot.app")


class PowerPilotApp:
    """Main application class — system tray power profile manager."""

    def __init__(self) -> None:
        from .config import load_config, validate_config
        from .log import setup_logging

        # Load config first
        self._config = load_config()
        general = self._config.get("general", {})

        # Setup logging
        self._logger = setup_logging(debug=general.get("debug", False))
        log.info("PowerPilot starting...")

        # Validate config
        warnings = validate_config(self._config)
        if warnings:
            log.warning("Config has %d warning(s)", len(warnings))

        # Detect hardware
        from .hardware import detect_hardware

        self._hardware = detect_hardware()

        # Detect and init backend
        from .backends import detect_backend

        preferred_backend = general.get("backend", "auto")
        self._backend = detect_backend(preferred_backend)
        log.info("Using backend: %s (%s)", self._backend.name, self._backend.backend_type)

        # Profile manager
        from .profiles import ProfileManager

        self._profile_mgr = ProfileManager(
            backend=self._backend,
            hardware=self._hardware,
            config=self._config,
        )

        # Detect current profile
        current = self._profile_mgr.detect_current_profile()
        if current:
            self._profile_mgr._active_profile = current
            log.info("Detected current profile: %s", current)

        # Notifications
        from .notifications import Notifier

        self._notifier = Notifier(
            enabled=general.get("show_notifications", True)
        )

        # Battery monitor
        self._battery_monitor = None
        if self._hardware.battery:
            from .battery import BatteryMonitor

            self._battery_monitor = BatteryMonitor()
            self._battery_monitor.set_threshold(
                general.get("low_battery_threshold", 20)
            )

            # Auto-switch on power source change
            if general.get("auto_switch_on_ac", True):
                self._battery_monitor.on_power_change(self._on_power_change)

            # Auto low-battery switch
            if general.get("auto_power_saver", True):
                self._battery_monitor.on_low_battery(self._on_low_battery)

        # App inhibitor
        self._inhibitor = None
        inhibit_cfg = self._config.get("inhibit", {})
        if inhibit_cfg.get("enabled", False):
            from .inhibitor import AppInhibitor

            self._inhibitor = AppInhibitor(
                app_rules=inhibit_cfg.get("apps", {}),
                enabled=True,
            )
            self._inhibitor.on_inhibit(self._on_app_inhibit)
            self._inhibitor.on_release(self._on_app_release)

        # Store the previous profile for inhibitor restore
        self._pre_inhibit_profile: str | None = None

        # GTK / AppIndicator setup
        self._indicator = None
        self._gtk_app = None
        self._battery_label = None

    def run(self) -> None:
        """Run the application main loop."""
        import gi

        gi.require_version("Gtk", "3.0")

        # Try AppIndicator libraries (GTK3-based first for compatibility)
        AppIndicator = None
        for lib_name, lib_version in [
            ("AyatanaAppIndicator3", "0.1"),
            ("AppIndicator3", "0.1"),
        ]:
            try:
                gi.require_version(lib_name, lib_version)
                AppIndicator = __import__(
                    "gi.repository", fromlist=[lib_name]
                )
                AppIndicator = getattr(AppIndicator, lib_name)
                log.info("Using AppIndicator library: %s %s", lib_name, lib_version)
                break
            except (ValueError, ImportError, AttributeError):
                continue

        if AppIndicator is None:
            log.error(
                "No AppIndicator library found. "
                "Install gir1.2-ayatanaappindicator3-0.1 or "
                "gir1.2-appindicator3-0.1"
            )
            sys.exit(1)

        from gi.repository import Gtk, GLib

        # Handle SIGINT/SIGTERM gracefully
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self._quit)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self._quit)

        # Create indicator
        self._indicator = AppIndicator.Indicator.new(
            "powerpilot",
            self._get_battery_icon(),
            AppIndicator.IndicatorCategory.HARDWARE,
        )
        self._indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self._indicator.set_title("PowerPilot")

        # Build menu
        self._rebuild_menu()

        # Start background services
        if self._battery_monitor:
            self._battery_monitor.start()
        if self._inhibitor:
            self._inhibitor.start()

        # Periodic UI refresh (battery info)
        if self._hardware.battery:
            GLib.timeout_add_seconds(30, self._refresh_battery_label)

        log.info("PowerPilot running")
        Gtk.main()

    def _rebuild_menu(self) -> None:
        """Build or rebuild the indicator menu."""
        from gi.repository import Gtk

        menu = Gtk.Menu()

        # Header
        header = Gtk.MenuItem(label="⚡ PowerPilot")
        header.set_sensitive(False)
        menu.append(header)

        # Backend info
        backend_item = Gtk.MenuItem(
            label=f"    Backend: {self._backend.name}"
        )
        backend_item.set_sensitive(False)
        menu.append(backend_item)

        menu.append(Gtk.SeparatorMenuItem())

        # Battery info
        if self._hardware.battery:
            battery = self._hardware.battery
            charge = battery.charge_percent
            status = battery.status
            power = battery.power_draw_watts
            remaining = battery.time_remaining_hours

            battery_text = f"🔋 {charge}%" if charge is not None else "🔋 --"
            if status == "Charging":
                battery_text += " ⚡ Charging"
            elif status == "Discharging" and power:
                battery_text += f" ({power}W)"
                if remaining:
                    hours = int(remaining)
                    mins = int((remaining - hours) * 60)
                    battery_text += f" ~{hours}h{mins:02d}m"

            self._battery_label = Gtk.MenuItem(label=battery_text)
            self._battery_label.set_sensitive(False)
            menu.append(self._battery_label)
            menu.append(Gtk.SeparatorMenuItem())

        # Profile items
        available = self._profile_mgr.get_available_profiles()
        active = self._profile_mgr.active_profile

        for profile_name in available:
            info = self._profile_mgr.get_profile_info(profile_name)
            if not info:
                continue

            label = info.get("label", profile_name)
            icon_prefix = "  ✓ " if profile_name == active else "     "
            item = Gtk.MenuItem(label=f"{icon_prefix}{label}")
            item.connect("activate", self._on_profile_selected, profile_name)
            menu.append(item)

        # Inhibitor status
        if self._inhibitor and self._inhibitor.active_inhibitor:
            menu.append(Gtk.SeparatorMenuItem())
            inhibit_item = Gtk.MenuItem(
                label=f"    🎮 Forced by: {self._inhibitor.active_inhibitor}"
            )
            inhibit_item.set_sensitive(False)
            menu.append(inhibit_item)

        menu.append(Gtk.SeparatorMenuItem())

        # Switch backend option
        from .switcher import BackendSwitcher
        switcher = BackendSwitcher()
        alt = switcher.get_alternative_backend()
        if alt:
            alt_label = "TLP" if alt == "tlp" else "power-profiles-daemon"
            switch_item = Gtk.MenuItem(label=f"    🔄 Switch to {alt_label}")
            switch_item.connect("activate", self._on_switch_backend, alt)
            menu.append(switch_item)

        menu.append(Gtk.SeparatorMenuItem())

        # Quit
        quit_item = Gtk.MenuItem(label="    Quit")
        quit_item.connect("activate", lambda _: self._quit())
        menu.append(quit_item)

        menu.show_all()
        self._indicator.set_menu(menu)

    def _on_profile_selected(self, widget, profile_name: str) -> None:
        """Handle profile selection from menu."""
        from gi.repository import GLib

        info = self._profile_mgr.get_profile_info(profile_name)
        if not info:
            return

        log.info("User selected profile: %s", profile_name)

        success = self._profile_mgr.switch_profile(profile_name, user_initiated=True)

        if success:
            self._notifier.notify_profile_switch(
                info.get("label", profile_name),
                info.get("icon", ""),
            )

        # Rebuild menu on next idle to update checkmark
        GLib.idle_add(self._rebuild_menu)
        GLib.idle_add(self._update_icon)

    def _on_power_change(self, on_ac: bool) -> None:
        """Handle AC/battery power source change."""
        from gi.repository import GLib

        log.info("Power source changed: %s", "AC" if on_ac else "battery")

        # Don't auto-switch if user manually selected a profile
        if self._profile_mgr.user_overridden:
            log.info("Skipping auto-switch (user override active)")
            return

        # Don't auto-switch if an app inhibitor is active
        if self._inhibitor and self._inhibitor.active_inhibitor:
            log.info("Skipping auto-switch (app inhibitor active)")
            return

        general = self._config.get("general", {})
        if on_ac:
            target = general.get("ac_profile", "balanced")
        else:
            target = general.get("battery_profile", "power-saver")

        info = self._profile_mgr.get_profile_info(target)
        if info:
            self._profile_mgr.switch_profile(target, user_initiated=False)
            self._notifier.notify_power_source(on_ac)
            GLib.idle_add(self._rebuild_menu)
            GLib.idle_add(self._update_icon)

    def _on_low_battery(self, percent: int) -> None:
        """Handle low battery event."""
        from gi.repository import GLib

        log.warning("Low battery triggered at %d%%", percent)

        # Use configured battery profile, fall back to "power-saver"
        general = self._config.get("general", {})
        target = general.get("battery_profile", "power-saver")

        # Verify the target profile exists
        info = self._profile_mgr.get_profile_info(target)
        if not info:
            log.error("Low battery profile '%s' not found in config", target)
            # Try "power-saver" as last resort
            target = "power-saver"
            info = self._profile_mgr.get_profile_info(target)
            if not info:
                log.error("No suitable low battery profile found")
                return

        self._notifier.notify_low_battery(percent)
        self._profile_mgr.switch_profile(target, user_initiated=False)
        GLib.idle_add(self._rebuild_menu)
        GLib.idle_add(self._update_icon)

    def _on_switch_backend(self, widget, target: str) -> None:
        """Handle backend switch request from menu."""
        from gi.repository import GLib

        from .switcher import BackendSwitcher

        switcher = BackendSwitcher()
        can_switch, reason = switcher.can_switch_to(target)
        if not can_switch:
            self._notifier.notify(
                title="PowerPilot",
                body=f"Cannot switch: {reason}",
                icon="dialog-error-symbolic",
                urgency="normal",
            )
            return

        alt_label = "TLP" if target == "tlp" else "power-profiles-daemon"
        self._notifier.notify(
            title="PowerPilot",
            body=f"Switching to {alt_label}... This may take a moment.",
            icon="system-software-install-symbolic",
        )

        # Run in background thread to avoid freezing the UI
        import threading

        def _do_switch():
            success, msg = switcher.switch_to(target)
            if success:
                GLib.idle_add(
                    self._notifier.notify,
                    "PowerPilot",
                    f"Switched to {alt_label}! Restarting...",
                    "emblem-ok-symbolic",
                    "normal",
                )
                # Give notification time to show, then restart
                import time
                time.sleep(2)
                # Stop background services before restart
                if self._battery_monitor:
                    self._battery_monitor.stop()
                if self._inhibitor:
                    self._inhibitor.stop()
                switcher.restart_app()
            else:
                GLib.idle_add(
                    self._notifier.notify,
                    "PowerPilot",
                    f"Switch failed: {msg}",
                    "dialog-error-symbolic",
                    "critical",
                )

        thread = threading.Thread(target=_do_switch, daemon=True)
        thread.start()

    def _on_app_inhibit(self, process_name: str, target_profile: str) -> None:
        """Handle app inhibitor activation."""
        from gi.repository import GLib

        self._pre_inhibit_profile = self._profile_mgr.active_profile
        self._profile_mgr.switch_profile(target_profile, user_initiated=False)

        self._notifier.notify(
            title="PowerPilot",
            body=f"'{process_name}' detected — switching to {target_profile}",
            icon="applications-games-symbolic",
        )

        GLib.idle_add(self._rebuild_menu)
        GLib.idle_add(self._update_icon)

    def _on_app_release(self) -> None:
        """Handle app inhibitor release."""
        from gi.repository import GLib

        if self._pre_inhibit_profile:
            self._profile_mgr.switch_profile(
                self._pre_inhibit_profile, user_initiated=False
            )
            self._pre_inhibit_profile = None

        self._notifier.notify(
            title="PowerPilot",
            body="App inhibitor released — profile restored",
            icon="battery-good-symbolic",
            urgency="low",
        )

        GLib.idle_add(self._rebuild_menu)
        GLib.idle_add(self._update_icon)

    def _refresh_battery_label(self) -> bool:
        """Refresh battery info text and icon without rebuilding the full menu."""
        try:
            if self._battery_label and self._hardware.battery:
                battery = self._hardware.battery
                charge = battery.charge_percent
                status = battery.status
                power = battery.power_draw_watts
                remaining = battery.time_remaining_hours

                text = f"🔋 {charge}%" if charge is not None else "🔋 --"
                if status == "Charging":
                    text += " ⚡ Charging"
                elif status == "Discharging" and power:
                    text += f" ({power}W)"
                    if remaining:
                        hours = int(remaining)
                        mins = int((remaining - hours) * 60)
                        text += f" ~{hours}h{mins:02d}m"

                self._battery_label.set_label(text)

            self._update_icon()
        except Exception as e:
            log.debug("Battery refresh error: %s", e)
        return True  # Keep the timer running

    def _get_battery_icon(self) -> str:
        """Get an icon name reflecting the current battery level and charging state."""
        if not self._hardware.battery:
            return "battery-missing-symbolic"

        battery = self._hardware.battery
        charge = battery.charge_percent
        status = battery.status

        if charge is None:
            return "battery-missing-symbolic"

        # Round to nearest 10 for icon name
        level = round(charge / 10) * 10
        level = max(0, min(100, level))

        if status == "Charging" or status == "Full":
            return f"battery-level-{level}-charging-symbolic"
        else:
            return f"battery-level-{level}-symbolic"

    def _update_icon(self) -> None:
        """Update the tray icon to reflect current battery level."""
        if self._indicator:
            icon = self._get_battery_icon()
            self._indicator.set_icon_full(icon, "PowerPilot")

    def _quit(self, *args) -> bool:
        """Clean shutdown. Returns False for GLib signal handler."""
        log.info("PowerPilot shutting down...")

        if self._battery_monitor:
            self._battery_monitor.stop()
        if self._inhibitor:
            self._inhibitor.stop()

        from gi.repository import Gtk

        Gtk.main_quit()
        return False  # GLib.SOURCE_REMOVE


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="powerpilot",
        description="PowerPilot — A universal power profile manager for Linux",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"PowerPilot {__version__}",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging (overrides config)",
    )
    parser.add_argument(
        "--no-notify",
        action="store_true",
        help="Disable desktop notifications",
    )
    parser.add_argument(
        "--switch-backend",
        choices=["tlp", "ppd"],
        metavar="BACKEND",
        help="Switch power backend to tlp or ppd (requires root)",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Entry point for PowerPilot."""
    args = parse_args()

    # Handle --switch-backend before starting the GUI
    if args.switch_backend:
        from .switcher import BackendSwitcher

        switcher = BackendSwitcher()
        can_switch, reason = switcher.can_switch_to(args.switch_backend)
        if not can_switch:
            print(f"Cannot switch: {reason}", file=sys.stderr)
            sys.exit(1)

        print(f"Switching backend to {args.switch_backend}...")
        success, msg = switcher.switch_to(args.switch_backend)
        if success:
            print(f"✓ {msg}")
            print("Restart PowerPilot to use the new backend.")
        else:
            print(f"✗ {msg}", file=sys.stderr)
            sys.exit(1)
        return

    app = PowerPilotApp()

    # Apply CLI overrides
    if args.debug:
        app._config.setdefault("general", {})["debug"] = True
        from .log import setup_logging
        # Re-init logging with debug
        logging.getLogger("powerpilot").handlers.clear()
        setup_logging(debug=True)

    if args.no_notify:
        app._notifier.enabled = False

    try:
        app.run()
    except KeyboardInterrupt:
        app._quit()
    except Exception as e:
        log.critical("Fatal error: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
