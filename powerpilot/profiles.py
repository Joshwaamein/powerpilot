"""Profile management for PowerPilot.

Coordinates switching between profiles by applying backend changes
and hardware tweaks (brightness, keyboard, bluetooth, wifi).
"""

import logging

from .backends.base import PowerBackend
from .config import get_profile_names
from .hardware import HardwareCapabilities

log = logging.getLogger("powerpilot.profiles")


class ProfileManager:
    """Manages power profile switching.

    Coordinates the backend (PPD/TLP) with hardware-level tweaks.
    """

    def __init__(
        self,
        backend: PowerBackend,
        hardware: HardwareCapabilities,
        config: dict,
    ) -> None:
        self._backend = backend
        self._hw = hardware
        self._config = config
        self._active_profile: str | None = None
        self._user_overridden = False  # True if user manually switched

    @property
    def backend(self) -> PowerBackend:
        """The active power backend."""
        return self._backend

    @property
    def active_profile(self) -> str | None:
        """Currently active PowerPilot profile name."""
        return self._active_profile

    @property
    def user_overridden(self) -> bool:
        """Whether the user manually switched profiles (inhibits auto-switch)."""
        return self._user_overridden

    def get_available_profiles(self) -> list[str]:
        """Get list of available profile names for the current backend."""
        tlp_available = self._backend.backend_type == "tlp"
        return get_profile_names(self._config, tlp_available=tlp_available)

    def get_profile_info(self, name: str) -> dict | None:
        """Get profile configuration by name."""
        profiles = self._config.get("profiles", {})
        return profiles.get(name)

    def switch_profile(self, name: str, user_initiated: bool = True) -> bool:
        """Switch to a named profile.

        Applies backend profile change + hardware tweaks.

        Args:
            name: Profile name from config.
            user_initiated: True if the user manually switched (vs auto).

        Returns:
            True if all changes were applied successfully.
        """
        profile = self.get_profile_info(name)
        if profile is None:
            log.error("Profile '%s' not found in config", name)
            return False

        # Check if this profile requires TLP
        if profile.get("requires_tlp") and self._backend.backend_type != "tlp":
            log.warning("Profile '%s' requires TLP backend", name)
            return False

        log.info("Switching to profile: %s (%s)", name, profile.get("label", name))

        success = True

        # Handle TLP Auto mode specially
        if profile.get("tlp_auto"):
            if self._backend.supports_tlp_auto:
                if not self._backend.apply_tlp_auto():
                    log.error("Failed to apply TLP auto mode")
                    success = False
            else:
                log.warning("Backend doesn't support TLP auto mode")
                success = False
        else:
            # Apply backend power profile
            power_profile = profile.get("power_profile")
            if power_profile:
                if not self._backend.set_profile(power_profile):
                    log.error("Failed to set backend profile: %s", power_profile)
                    success = False

            # Apply hardware tweaks
            self._apply_hardware_tweaks(profile)

        if success:
            self._active_profile = name
            self._user_overridden = user_initiated
            log.info("Profile '%s' applied successfully", name)
        else:
            log.warning("Profile '%s' applied with some failures", name)
            self._active_profile = name  # Still track it

        return success

    def _apply_hardware_tweaks(self, profile: dict) -> None:
        """Apply hardware-level settings from a profile.

        Args:
            profile: Profile configuration dictionary.
        """
        # Screen brightness
        brightness = profile.get("screen_brightness_percent")
        if brightness is not None and self._hw.backlight:
            try:
                self._hw.backlight.set_percent(brightness)
                log.debug("Set screen brightness to %d%%", brightness)
            except (OSError, IOError) as e:
                log.warning("Failed to set screen brightness: %s", e)

        # Keyboard backlight
        kbd_level = profile.get("keyboard_backlight")
        if kbd_level is not None and self._hw.kbd_backlight:
            try:
                self._hw.kbd_backlight.brightness = kbd_level
                log.debug("Set keyboard backlight to %d", kbd_level)
            except (OSError, IOError) as e:
                log.warning("Failed to set keyboard backlight: %s", e)

        # Wi-Fi power save
        wifi_ps = profile.get("wifi_power_save")
        if wifi_ps is not None and self._hw.wifi:
            if not self._hw.wifi.set_power_save(wifi_ps):
                log.warning("Failed to set Wi-Fi power save to %s", wifi_ps)
            else:
                log.debug("Set Wi-Fi power save to %s", wifi_ps)

        # Bluetooth
        bt = profile.get("bluetooth")
        if bt is not None and self._hw.bluetooth and self._hw.bluetooth.available:
            if not self._hw.bluetooth.set_enabled(bt):
                log.warning("Failed to set Bluetooth to %s", bt)
            else:
                log.debug("Set Bluetooth to %s", "on" if bt else "off")

    def detect_current_profile(self) -> str | None:
        """Try to detect which profile matches the current system state.

        Returns:
            Profile name that best matches, or None.
        """
        backend_profile = self._backend.get_active_profile()
        if backend_profile is None:
            return None

        # Find a PowerPilot profile that matches the backend profile
        profiles = self._config.get("profiles", {})
        for name, profile in profiles.items():
            if profile.get("tlp_auto") and backend_profile == "tlp-auto":
                return name
            if profile.get("power_profile") == backend_profile:
                return name

        return None

    def reset_user_override(self) -> None:
        """Reset the user override flag (allows auto-switching again)."""
        self._user_overridden = False
