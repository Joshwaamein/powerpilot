"""power-profiles-daemon (PPD) backend for PowerPilot.

Uses DBus interface for unprivileged profile switching.
Falls back to powerprofilesctl CLI if DBus is unavailable.
"""

import logging
import subprocess

from .base import PowerBackend

log = logging.getLogger("powerpilot.backends.ppd")

# DBus constants
PPD_BUS_NAME = "net.hadess.PowerProfiles"
PPD_OBJECT_PATH = "/net/hadess/PowerProfiles"
PPD_INTERFACE = "net.hadess.PowerProfiles"


class PPDBackend(PowerBackend):
    """Backend using power-profiles-daemon."""

    def __init__(self) -> None:
        self._dbus_proxy = None
        self._init_dbus()

    @property
    def name(self) -> str:
        return "power-profiles-daemon"

    @property
    def backend_type(self) -> str:
        return "ppd"

    def _init_dbus(self) -> None:
        """Try to initialize DBus connection to PPD."""
        try:
            import dbus

            bus = dbus.SystemBus()
            self._dbus_proxy = bus.get_object(PPD_BUS_NAME, PPD_OBJECT_PATH)
            log.debug("Connected to PPD via DBus")
        except Exception as e:
            log.debug("DBus connection to PPD failed: %s. Using CLI fallback.", e)
            self._dbus_proxy = None

    def get_available_profiles(self) -> list[str]:
        """Get profiles available from PPD.

        Returns:
            List like ['power-saver', 'balanced', 'performance'].
        """
        # Try DBus first
        if self._dbus_proxy:
            try:
                import dbus

                props = dbus.Interface(
                    self._dbus_proxy, "org.freedesktop.DBus.Properties"
                )
                profiles = props.Get(PPD_INTERFACE, "Profiles")
                return [str(p.get("Profile", "")) for p in profiles if "Profile" in p]
            except Exception as e:
                log.debug("DBus get profiles failed: %s", e)

        # CLI fallback
        try:
            result = subprocess.run(
                ["powerprofilesctl", "list"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                profiles = []
                for line in result.stdout.splitlines():
                    line = line.strip().rstrip(":")
                    if line.startswith("*"):
                        line = line[1:].strip().rstrip(":")
                    if line in ("power-saver", "balanced", "performance"):
                        profiles.append(line)
                return profiles
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            log.error("Failed to list PPD profiles: %s", e)

        return ["power-saver", "balanced", "performance"]  # Assume defaults

    def get_active_profile(self) -> str | None:
        """Get the currently active PPD profile."""
        # Try DBus
        if self._dbus_proxy:
            try:
                import dbus

                props = dbus.Interface(
                    self._dbus_proxy, "org.freedesktop.DBus.Properties"
                )
                profile = str(props.Get(PPD_INTERFACE, "ActiveProfile"))
                return profile
            except Exception as e:
                log.debug("DBus get active profile failed: %s", e)

        # CLI fallback
        try:
            result = subprocess.run(
                ["powerprofilesctl", "get"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            log.error("Failed to get active PPD profile: %s", e)

        return None

    def set_profile(self, profile: str) -> bool:
        """Set the active PPD profile.

        Args:
            profile: One of 'power-saver', 'balanced', 'performance'.

        Returns:
            True if successful.
        """
        available = self.get_available_profiles()
        if profile not in available:
            log.error("Profile '%s' not available. Available: %s", profile, available)
            return False

        # Try DBus (no root needed!)
        if self._dbus_proxy:
            try:
                import dbus

                props = dbus.Interface(
                    self._dbus_proxy, "org.freedesktop.DBus.Properties"
                )
                props.Set(PPD_INTERFACE, "ActiveProfile", dbus.String(profile))
                log.info("Set PPD profile to '%s' via DBus", profile)
                return True
            except Exception as e:
                log.debug("DBus set profile failed: %s", e)

        # CLI fallback
        try:
            result = subprocess.run(
                ["powerprofilesctl", "set", profile],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                log.info("Set PPD profile to '%s' via CLI", profile)
                return True
            else:
                log.error("powerprofilesctl set failed: %s", result.stderr)
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            log.error("Failed to set PPD profile: %s", e)

        return False
