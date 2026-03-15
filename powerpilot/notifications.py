"""Desktop notifications for PowerPilot.

Uses GNotification (GTK) or falls back to notify-send CLI.
"""

import logging
import subprocess

log = logging.getLogger("powerpilot.notifications")


class Notifier:
    """Sends desktop notifications."""

    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled
        self._gi_available = False
        self._try_init_gi()

    def _try_init_gi(self) -> None:
        """Try to initialize GI notification support."""
        try:
            import gi

            gi.require_version("Notify", "0.7")
            from gi.repository import Notify

            Notify.init("PowerPilot")
            self._gi_available = True
            log.debug("Notifications initialized (libnotify)")
        except Exception as e:
            log.debug("libnotify not available: %s. Using notify-send.", e)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    def notify(
        self,
        title: str,
        body: str,
        icon: str = "battery-good-symbolic",
        urgency: str = "normal",
    ) -> None:
        """Send a desktop notification.

        Args:
            title: Notification title.
            body: Notification body text.
            icon: Icon name (freedesktop icon theme).
            urgency: One of 'low', 'normal', 'critical'.
        """
        if not self._enabled:
            return

        if self._gi_available:
            self._notify_gi(title, body, icon, urgency)
        else:
            self._notify_cli(title, body, icon, urgency)

    def notify_profile_switch(self, profile_label: str, icon: str = "") -> None:
        """Send a notification about a profile switch.

        Args:
            profile_label: Human-readable profile name.
            icon: Profile icon name.
        """
        self.notify(
            title="PowerPilot",
            body=f"Switched to {profile_label}",
            icon=icon or "battery-good-symbolic",
        )

    def notify_low_battery(self, percent: int) -> None:
        """Send a low battery warning notification.

        Args:
            percent: Current battery percentage.
        """
        self.notify(
            title="PowerPilot — Low Battery",
            body=f"Battery at {percent}%. Switching to Power Saver.",
            icon="battery-caution-symbolic",
            urgency="critical",
        )

    def notify_power_source(self, on_ac: bool) -> None:
        """Send a notification about power source change.

        Args:
            on_ac: True if switched to AC, False for battery.
        """
        if on_ac:
            self.notify(
                title="PowerPilot",
                body="AC power connected",
                icon="battery-full-charged-symbolic",
                urgency="low",
            )
        else:
            self.notify(
                title="PowerPilot",
                body="Running on battery",
                icon="battery-good-symbolic",
                urgency="low",
            )

    def _notify_gi(
        self, title: str, body: str, icon: str, urgency: str
    ) -> None:
        """Send notification via libnotify / GI."""
        try:
            from gi.repository import Notify

            notification = Notify.Notification.new(title, body, icon)

            urgency_map = {
                "low": Notify.Urgency.LOW,
                "normal": Notify.Urgency.NORMAL,
                "critical": Notify.Urgency.CRITICAL,
            }
            notification.set_urgency(
                urgency_map.get(urgency, Notify.Urgency.NORMAL)
            )
            notification.show()
        except Exception as e:
            log.warning("GI notification failed: %s", e)
            self._notify_cli(title, body, icon, urgency)

    def _notify_cli(
        self, title: str, body: str, icon: str, urgency: str
    ) -> None:
        """Send notification via notify-send CLI."""
        try:
            cmd = [
                "notify-send",
                "--app-name=PowerPilot",
                f"--icon={icon}",
                f"--urgency={urgency}",
                title,
                body,
            ]
            subprocess.run(cmd, capture_output=True, timeout=5)
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            log.debug("notify-send failed: %s", e)
