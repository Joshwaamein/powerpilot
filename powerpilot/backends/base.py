"""Abstract base class and sysfs fallback for power backends."""

import logging
from abc import ABC, abstractmethod

log = logging.getLogger("powerpilot.backends.base")


class PowerBackend(ABC):
    """Abstract base class for power management backends."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name."""
        ...

    @property
    @abstractmethod
    def backend_type(self) -> str:
        """Backend type identifier: 'tlp', 'ppd', or 'sysfs'."""
        ...

    @abstractmethod
    def get_available_profiles(self) -> list[str]:
        """Get list of power profiles supported by this backend.

        Returns:
            List of profile name strings.
        """
        ...

    @abstractmethod
    def get_active_profile(self) -> str | None:
        """Get the currently active power profile.

        Returns:
            Profile name string, or None if unknown.
        """
        ...

    @abstractmethod
    def set_profile(self, profile: str) -> bool:
        """Set the active power profile.

        Args:
            profile: Profile name to activate.

        Returns:
            True if successful.
        """
        ...

    @property
    def supports_tlp_auto(self) -> bool:
        """Whether this backend supports the TLP Auto mode."""
        return False

    def apply_tlp_auto(self) -> bool:
        """Switch to TLP auto mode (TLP default config).

        Returns:
            True if successful. False or raises if not supported.
        """
        return False


class SysfsBackend(PowerBackend):
    """Fallback backend that only reports — no profile switching.

    Used when neither TLP nor power-profiles-daemon is available.
    """

    @property
    def name(self) -> str:
        return "sysfs (no daemon)"

    @property
    def backend_type(self) -> str:
        return "sysfs"

    def get_available_profiles(self) -> list[str]:
        """Sysfs backend has no profiles to switch."""
        return []

    def get_active_profile(self) -> str | None:
        """No active profile in sysfs mode."""
        return None

    def set_profile(self, profile: str) -> bool:
        """Cannot set profiles in sysfs mode."""
        log.warning("sysfs backend cannot switch power profiles. Install TLP or power-profiles-daemon.")
        return False
